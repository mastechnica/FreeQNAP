"""Restic repositories, durable backup jobs and non-destructive staged restores."""
import json
import os
import re
import secrets
import stat
import shlex
import time
from pathlib import Path
from .common import name, secret
from .storage_boundary import shared

SNAPSHOT = re.compile(r'[0-9a-f]{64}\Z')

class FileBackups:
    def __init__(self, context):
        self.ctx = context
        self.secrets = context.directory / 'secrets'
        self.secrets.mkdir(mode=0o700, exist_ok=True)

    def _store_secret(self, filename, data):
        path = self.secrets / filename
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        return str(path)

    def repository(self, request):
        ident = name(request.get('name'))
        password = secret({'password': request.get('password')})
        with self.ctx.lock():
            config = self.ctx.config()
            if ident in config['repositories']:
                raise ValueError('Repository already exists; use its saved configuration')
            kind = request.get('kind', 'local')
            entry = {'name': ident, 'kind': kind, 'created_at': time.time(), 'initialized': False}
            if kind == 'local':
                pool, mount = self.ctx.volume(name(request.get('pool')))
                destination = mount / '.freeqnap' / 'backups' / ident
                destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                if destination.is_symlink():raise ValueError('Repository destination cannot be a symbolic link')
                if destination.exists() and not request.get('import_existing'):
                    raise ValueError('Destination exists; import it instead of initializing over existing data')
                entry.update(pool=pool['name'], filesystem_uuid=pool['filesystem_uuid'], path=str(destination))
            elif kind == 'sftp':
                host = request.get('host', '')
                user = request.get('user', '')
                path = request.get('path', '')
                port = int(request.get('port', 22))
                if not re.fullmatch('[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}', host) or not re.fullmatch('[a-z_][a-z0-9_-]{0,31}', user) or not re.fullmatch('/[a-zA-Z0-9_./-]{1,512}', path) or '..' in Path(path).parts or not 1 <= port <= 65535:
                    raise ValueError('Use a valid SFTP host/user/absolute path/port')
                key = request.get('ssh_key', '')
                hostkey = request.get('host_public_key', '').strip()
                if not isinstance(key, str) or len(key) > 32768 or not key.startswith('-----BEGIN OPENSSH PRIVATE KEY-----'):
                    raise ValueError('A dedicated OpenSSH private key is required')
                if not re.fullmatch(r'(ssh-ed25519|ecdsa-sha2-nistp256|ssh-rsa) [A-Za-z0-9+/=]{20,2000}', hostkey):
                    raise ValueError('Pin the SFTP server public host key; automatic trust is forbidden')
                keypath = self._store_secret(ident + '.ssh-key', key.encode())
                knownhost = host if port == 22 else '[' + host + ']:' + str(port)
                knownpath = self._store_secret(ident + '.known-hosts', (knownhost + ' ' + hostkey + '\n').encode())
                command = ['ssh', '-F', '/dev/null', '-i', keypath, '-o', 'IdentitiesOnly=yes',
                           '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + knownpath,
                           '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=10',
                           '-o', 'ServerAliveCountMax=3', '-p', str(port), user + '@' + host, '-s', 'sftp']
                entry.update(host=host, user=user, port=port, remote_path=path,
                             repository='sftp:' + user + '@' + host + ':' + path,
                             ssh_command=shlex.join(command))
            else:
                raise ValueError('Choose a mounted local volume or pinned SFTP destination')
            entry['password_file'] = self._store_secret(ident + '.restic-password', password)
            config['repositories'][ident] = entry;self.ctx.save(config)
            try:
                self.command(entry, *(['cat', 'config'] if request.get('import_existing') else ['init']))
                entry['initialized'] = True
                config['repositories'][ident] = entry;self.ctx.save(config)
            except Exception:
                # Keep the exact credentials/configuration for explicit init reconciliation.
                raise ValueError('Repository initialization failed. Configuration and private credentials were retained; inspect before retrying.')
            return self.public(entry)

    @staticmethod
    def public(entry):
        return {key: value for key, value in entry.items() if key not in ('password_file', 'ssh_command')}

    def get(self, ident):
        entry = self.ctx.config()['repositories'].get(name(ident))
        if not entry:
            raise ValueError('Unknown backup repository')
        if entry['kind'] == 'local':
            pool, _ = self.ctx.volume(entry['pool'])
            if pool['filesystem_uuid'] != entry['filesystem_uuid']:
                raise ValueError('Repository volume identity changed')
        return entry

    def command(self, entry, *args, timeout=86400):
        if entry['kind'] == 'local':
            pool, _ = self.ctx.volume(entry['pool'])
            if pool['filesystem_uuid'] != entry['filesystem_uuid']:
                raise ValueError('Repository volume is unavailable or changed')
        env = {**os.environ, 'RESTIC_REPOSITORY': entry.get('repository', entry.get('path', '')),
               'RESTIC_PASSWORD_FILE': entry['password_file'], 'GOMAXPROCS': '2', 'GOGC': '50',
               'RESTIC_CACHE_DIR': str(self.ctx.directory / 'restic-cache')}
        command = ['restic', '--json']
        if entry['kind'] == 'sftp':
            command += ['-o', 'sftp.command=' + entry['ssh_command']]
        return self.ctx.run(*command, *args, env=env, timeout=timeout)

    def snapshots(self, ident):
        entry = self.get(ident)
        rows = json.loads(self.command(entry, 'snapshots', timeout=60)) or []
        accepted = self.ctx.state.setting('successful_snapshots', {})
        with self.ctx.state.connect() as db:system_records=[json.loads(r[0]) for r in db.execute("SELECT value FROM settings WHERE key LIKE 'system_backup:%'")]
        system_ids={r['snapshot_id'] for r in system_records if r['repository']==ident}
        return [{**row, 'system_recovery_snapshot':'freeqnap-system' in row.get('tags',[]), 'freeqnap_successful_backup': row['id'] in accepted.get(ident, []) or row['id'] in system_ids} for row in rows[-200:]]

    def backup(self, request):
        ident = name(request.get('repository'))
        entry = self.get(ident)
        shares = request.get('shares', [])
        config = self.ctx.config()
        if not isinstance(shares, list) or not shares or not all(s in config['shares'] for s in shares):
            raise ValueError('Select existing shared folders')
        paths = [];source_bindings=[]
        for share_id in shares:
            share = config['shares'][share_id]
            pool, mount = self.ctx.volume(share['pool'])
            if entry['kind'] == 'local' and shared(pool,config['pools'][entry['pool']]) and request.get('same_pool_confirmation') != 'SAME POOL ' + entry['name']:
                raise ValueError('Backups sharing a filesystem, RAID, enclosure or physical disk need explicit acknowledgement; they do not protect against loss of that storage')
            if Path(share['path']).parent != mount or Path(share['path']).is_symlink():
                raise ValueError('Share root identity changed')
            info=Path(share['path']).lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_dev!=mount.stat().st_dev:
                raise ValueError('Backup source root is not a directory on the selected filesystem')
            paths.append(share['path']);source_bindings.append({'share':share_id,'pool':pool['name'],'filesystem_uuid':pool['filesystem_uuid'],'path':share['path'],'device':info.st_dev,'inode':info.st_ino})
        output = self.command(entry, 'backup', '--quiet', '--tag', 'freeqnap', '--', *paths)
        summaries = [json.loads(line) for line in output.splitlines() if line.strip()]
        summary = next((row for row in reversed(summaries) if row.get('message_type') == 'summary'), None)
        if not summary or not SNAPSHOT.fullmatch(summary.get('snapshot_id', '')):
            raise ValueError('Restic did not return an unambiguous successful snapshot')
        # A vanished/replaced source must not turn an empty/partial walk into
        # an accepted backup, even if Restic returned a snapshot identifier.
        def verify_sources():
            for binding in source_bindings:
                current=self.ctx.config()['shares'].get(binding['share'])
                if not current or current['pool']!=binding['pool'] or current['path']!=binding['path']:raise ValueError('Backup source mapping changed; snapshot remains unaccepted')
                pool,_=self.ctx.volume(binding['pool'])
                if pool['filesystem_uuid']!=binding['filesystem_uuid']:raise ValueError('Backup source filesystem changed; snapshot remains unaccepted')
                info=Path(binding['path']).lstat()
                if not stat.S_ISDIR(info.st_mode) or info.st_dev!=binding['device'] or info.st_ino!=binding['inode']:
                    raise ValueError('Backup source directory changed; snapshot remains unaccepted')
        verify_sources()
        # Exit 3/permission failures are exceptions; partial snapshots never become accepted.
        self.command(entry, 'check', timeout=3600)
        verify_sources()
        accepted = self.ctx.state.setting('successful_snapshots', {})
        accepted.setdefault(ident, []).append(summary['snapshot_id'])
        self.ctx.state.set('successful_snapshots', accepted)
        return {'repository': ident, 'snapshot_id': summary['snapshot_id'],
                'files_processed': summary.get('total_files_processed'), 'repository_metadata_checked': True,
                'full_restore_tested': False, 'independent_disaster_backup':False, 'destination_scope':'local NAS storage' if entry['kind']=='local' else 'owner-selected SFTP; physical independence not verified'}

    def check(self, request):
        entry = self.get(request['repository'])
        read_data = request.get('read_data') is True
        args = ['check'] + (['--read-data'] if read_data else [])
        self.command(entry, *args)
        result = {'checked_at': time.time(), 'read_all_data': read_data}
        self.ctx.state.set('repository_check:' + entry['name'], result)
        return result

    def restore(self, request, operation):
        entry = self.get(request['repository'])
        snapshot = request.get('snapshot', '')
        if not SNAPSHOT.fullmatch(snapshot):
            raise ValueError('Select a full immutable snapshot ID; latest is not accepted')
        metadata=json.loads(self.command(entry,'snapshots',snapshot,timeout=60)) or []
        if len(metadata)!=1 or metadata[0].get('id')!=snapshot:raise ValueError('Snapshot identity/metadata is missing or ambiguous')
        recovery_only='freeqnap-system' in metadata[0].get('tags',[]) or any(str(p).startswith('/var/lib/freeqnap-system/system-recovery/') for p in metadata[0].get('paths',[]))
        pool, mount = self.ctx.volume(name(request.get('pool')))
        stage = mount / '.freeqnap' / 'restores' / operation
        stage.mkdir(mode=0o700, parents=True, exist_ok=False)
        include = request.get('include')
        args = ['restore', snapshot, '--target', str(stage), '--verify']
        if include:
            if not isinstance(include, str) or len(include) > 2048 or '..' in Path(include).parts:
                raise ValueError('Invalid snapshot path')
            args += ['--include', include]
        self.command(entry, *args)
        self.ctx.volume(pool['name'])
        # Restore is staged only; no live file or share is overwritten.
        return {'repository': entry['name'], 'snapshot': snapshot, 'pool': pool['name'],
                'staging_directory': str(stage), 'restored_content_verified': True,
                'live_files_replaced': False,'system_recovery_only':recovery_only}

    def prune_plan(self, request):
        entry = self.get(request['repository'])
        scope=request.get('scope','files')
        if scope not in ('files','system'):raise ValueError('Choose shared-file or system-recovery retention')
        tag='freeqnap-system' if scope=='system' else 'freeqnap'
        keep = int(request.get('keep_last', 7))
        if not 1 <= keep <= 365:
            raise ValueError('Keep 1–365 snapshots')
        check = self.ctx.state.setting('repository_check:' + entry['name'], {})
        if not check.get('read_all_data') or not 0 <= time.time() - check['checked_at'] < 86400:
            raise ValueError('A successful full-data repository check within 24 hours is required before pruning')
        output = self.command(entry, 'forget', '--dry-run', '--keep-last', str(keep), '--tag', tag)
        return self.ctx.plan('backup-prune', {'repository': entry['name'], 'scope':scope,'keep_last': keep,
                                           'review': json.loads(output)}, ('PRUNE SYSTEM BACKUPS ' if scope=='system' else 'PRUNE ') + entry['name'])

    def prune(self, request):
        with self.ctx.lock():
            path, plan = self.ctx.reviewed(request, 'backup-prune')
            entry = self.get(plan['body']['repository'])
            tag='freeqnap-system' if plan['body'].get('scope')=='system' else 'freeqnap'
            fresh = json.loads(self.command(entry, 'forget', '--dry-run', '--keep-last', str(plan['body']['keep_last']), '--tag', tag))
            if fresh != plan['body']['review']:
                raise ValueError('Repository snapshot set changed since review')
            self.ctx.consume(path, plan)
            self.command(entry, 'forget', '--keep-last', str(plan['body']['keep_last']), '--tag', tag, '--prune')
            return {'pruned': True, 'repository': entry['name']}
