"""Explicit, identity-bound recovery of registered four-member RAID5 arrays.

No scan assembly, recreation, member replacement, filesystem repair or retry loop.
An override always starts read-only; writable recovery requires a second plan.
"""
import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import tarfile
import time
from pathlib import Path
from .common import canonical, name

HEADER_BYTES = 8 * 1024**2

def normal(value):
    return re.sub('[^a-f0-9]', '', str(value).lower())

def parse_member(text):
    fields = dict((a.strip(), b.strip()) for a, b in
                  (line.split(':', 1) for line in text.splitlines() if ':' in line))
    def number(key, required=True):
        value = fields.get(key, '')
        match = re.match(r'([0-9]+)(?:\s|$)', value)
        if not match:
            if required:raise ValueError('Incomplete RAID metadata: ' + key)
            return None
        return int(match[1])
    role = re.fullmatch(r'Active device ([0-9]+)', fields.get('Device Role', ''))
    if not role or not re.fullmatch(r'[a-fA-F0-9]+ - correct', fields.get('Checksum', '')):
        raise ValueError('A member has an invalid checksum or unsupported role')
    value = {'uuid': normal(fields.get('Array UUID')), 'member_uuid': normal(fields.get('Device UUID')),
             'level': fields.get('Raid Level'), 'devices': number('Raid Devices'),
             'events': number('Events'), 'role': int(role[1]), 'component_sectors': number('Used Dev Size'),
             'data_offset_sectors': number('Data Offset'), 'recovery_start': number('Recovery Offset', False),
             'state': fields.get('State'), 'layout': fields.get('Layout'), 'chunk': fields.get('Chunk Size'),
             'version': fields.get('Version')}
    if len(value['uuid']) != 32 or len(value['member_uuid']) != 32:
        raise ValueError('Incomplete member UUID')
    return value

def validate_members(members, expected_uuid, live=False):
    if len(members) != 4:raise ValueError('This guided recovery requires all four original members')
    first = members[0]['metadata']
    for member in members:
        value = member['metadata']
        if value['uuid'] != normal(expected_uuid) or value['version'] != '1.2' or value['level'] != 'raid5' or value['devices'] != 4:
            raise ValueError('Array identity, format or RAID level changed')
        for key in ('events', 'component_sectors', 'data_offset_sectors', 'layout', 'chunk'):
            if live and key=='events':continue
            if value[key] != first[key]:raise ValueError('Member metadata disagrees; specialist recovery is required')
        if value['data_offset_sectors'] * 512 < HEADER_BYTES:
            raise ValueError('This metadata layout is not supported by the bounded backup workflow')
        checkpoint = value['recovery_start']
        if checkpoint is not None and not 0 <= checkpoint < value['component_sectors']:
            raise ValueError('Invalid rebuild checkpoint')
    if {m['metadata']['role'] for m in members} != set(range(4)) or len({m['metadata']['member_uuid'] for m in members}) != 4:
        raise ValueError('Missing, repeated or ambiguous member roles')
    rebuilding = [m for m in members if m['metadata']['recovery_start'] is not None]
    if len(rebuilding) > 1:raise ValueError('More than one rebuilding member is outside this guided workflow')
    return {'rebuilding_members': len(rebuilding), 'checkpoint_sectors': rebuilding[0]['metadata']['recovery_start'] if rebuilding else None,
            'force_required': bool(rebuilding and any(m['metadata']['state'] != 'clean' for m in members))}

class ArrayRecovery:
    def __init__(self, ctx, storage):
        self.ctx, self.storage = ctx, storage
        self.directory = ctx.directory / 'array-recovery'

    def pools(self, ident):
        pool = self.ctx.config()['pools'].get(name(ident))
        if not pool or pool.get('kind') == 'usb' or not pool.get('regions'):
            raise ValueError('Choose an existing registered internal data array')
        group = [p for p in self.ctx.config()['pools'].values() if p.get('md_uuid') == pool['md_uuid'] and p.get('kind') != 'usb']
        return pool, group

    def root_members(self):
        root = os.stat('/')
        start = Path('/sys/dev/block') / f'{os.major(root.st_dev)}:{os.minor(root.st_dev)}'
        if not start.exists():raise ValueError('Running root ancestry cannot be verified')
        protected = set()
        def walk(node):
            node = node.resolve();protected.add('/dev/' + node.name)
            for child in (node / 'slaves').glob('*'):walk(child)
            if (node / 'partition').exists():protected.add('/dev/' + node.parent.name)
        walk(start)
        return protected

    def snapshot(self, ident, headers=False, live=False):
        pool, group = self.pools(ident)
        disks = self.storage.collect()
        if disks.get('errors') or not disks.get('root',{}).get('uuid') or not 0<=time.time()-disks.get('sampled_at',0)<120:raise ValueError('Complete, fresh disk identification is unavailable')
        protected = self.root_members();members = []
        for record in pool['regions']:
            original = record['disk']
            matches = [d for d in disks['disks'] if all(d.get(k) == original.get(k) for k in ('serial', 'wwn', 'size'))]
            if len(matches) != 1 or not self.storage.internal_validator(matches[0]['path']):
                raise ValueError('An original internal disk is missing or its identity changed')
            device = matches[0]['path'] + str(record['number'])
            if device in protected or (matches[0]['path'] in protected and record['number']<3):raise ValueError('Recovery cannot operate on the running OS or its ancestors')
            table=json.loads(self.ctx.run('sfdisk','--json',matches[0]['path'],timeout=5))['partitiontable']
            parts=[p for p in table.get('partitions',[]) if p.get('node')==device]
            if table.get('label')!='gpt' or table.get('sectorsize')!=512 or len(parts)!=1:raise ValueError('Member partition layout cannot be verified')
            part=parts[0]
            if (part.get('start'),part.get('size'))!=(record['start'],record['end']-record['start']+1) or not part.get('uuid'):raise ValueError('Member partition geometry changed')
            metadata = parse_member(self.ctx.run('mdadm', '--examine', device, timeout=5))
            value = {'device': device, 'disk': original, 'partition':part, 'metadata': metadata}
            if headers:
                with open(device, 'rb', buffering=0) as stream:data = stream.read(HEADER_BYTES)
                if len(data) != HEADER_BYTES:raise ValueError('Short metadata read')
                value['header_sha256'] = hashlib.sha256(data).hexdigest()
            members.append(value)
        safety = validate_members(members, pool['md_uuid'],live=live)
        try:
            array = self.storage.inspect_array(pool)
            array['read_only'] = self.ctx.run('blockdev', '--getro', array['device']).strip() == '1'
        except ValueError:array = None
        if live and (not array or array['read_only'] or set(array['members'])!={m['device'] for m in members}):raise ValueError('Live mount inspection requires the exact writable array and all original members')
        allowed = {Path(array['device']).name} if array else set()
        for member in members:
            holders = {p.name for p in (Path('/sys/class/block') / Path(member['device']).name / 'holders').glob('*')}
            if holders - allowed:raise ValueError('A member has an unexpected active holder')
        return {'pool': pool['name'], 'group': pool.get('group', pool['name']), 'uuid': pool['md_uuid'],
                'members': members, 'volumes': [{k: p.get(k) for k in ('name', 'filesystem_uuid', 'partition_uuid', 'array_partition', 'mountpoint', 'encrypted', 'read_only')} for p in group],
                'root_uuid': disks['root']['uuid'], 'array': array, **safety}

    def status(self, request=None):
        groups = [];seen = set()
        for pool in self.ctx.config()['pools'].values():
            if pool.get('kind') == 'usb' or not pool.get('regions') or pool.get('md_uuid') in seen:continue
            seen.add(pool['md_uuid'])
            value = {'pool': pool['name'], 'name': pool.get('group', pool['name']), 'volumes': [], 'available_actions': []}
            try:
                try:array = self.storage.inspect_array(pool)
                except ValueError:array = None
                if array:
                    array['read_only'] = self.ctx.run('blockdev', '--getro', array['device'], timeout=4).strip() == '1'
                    value['array'] = array
                    value['state'] = 'read-only' if array['read_only'] else 'rebuilding' if array['sync_action'] != 'idle' else 'degraded' if array['degraded'] else 'online'
                    value['available_actions'] = ['resume'] if array['read_only'] else ['mount']
                else:
                    value['state'] = 'stopped';value['available_actions'] = ['readonly']
                _, pools = self.pools(pool['name'])
                for p in pools:
                    mounted = False
                    try:self.ctx.volume(p['name']);mounted = True
                    except (ValueError, OSError):pass
                    value['volumes'].append({'name': p['name'], 'mounted': mounted, 'encrypted': p['encrypted']})
                value['last_operation'] = self.ctx.state.setting('array-recovery:' + normal(pool['md_uuid']))
            except (ValueError, OSError) as error:value.update(state='needs-attention', error=str(error))
            groups.append(value)
        return {'arrays': groups, 'policy': 'Registered data arrays only. Inspect read-only first; writable resume requires a separate reviewed plan.',
                'root_protected': True, 'automatic_force': False}

    def plan(self, request):
        if set(request) - {'pool', 'mode', 'mount_volumes'}:raise ValueError('Unknown recovery settings')
        mode = request.get('mode')
        if mode not in ('readonly', 'resume', 'mount'):raise ValueError('Choose read-only recovery, resume rebuilding, or mount existing volumes')
        snapshot = self.snapshot(request.get('pool'), headers=mode != 'mount',live=mode=='mount');array = snapshot['array']
        if mode == 'readonly' and array:raise ValueError('The array is already assembled; inspect its current state')
        if mode == 'resume' and (not array or not array['read_only']):raise ValueError('Resume requires the exact array to be assembled read-only')
        if mode == 'mount' and (not array or array['read_only']):raise ValueError('Mount requires an existing writable array')
        for p in snapshot['volumes']:
            if p['encrypted']:raise ValueError('Unlock encrypted volumes separately; this workflow never stores unlock secrets')
        backup = self.backup(secrets.token_hex(16), snapshot) if mode != 'mount' else None
        body = {'metadata_backup': backup, 'mode': mode, 'snapshot': snapshot, 'mount_volumes': request.get('mount_volumes', True) is True,
                'risk': 'An unclean degraded array can contain inconsistent parity or damaged files. Sample checks do not prove all data is intact. Metadata backups are not file backups.',
                'writes': 'RAID metadata only; array remains read-only and no volumes are mounted' if mode == 'readonly' else 'Existing data members; normal ext4 journal replay and rebuild writes may occur',
                'excluded': ['Formatting', 'Repartitioning', 'Member removal/re-add', 'OS mirror', 'USB disks', 'Automatic retries', 'Arbitrary filesystem repair']}
        phrase = {'readonly': 'RECOVER READ ONLY ', 'resume': 'RESUME REBUILD ', 'mount': 'MOUNT VOLUMES '}[mode] + snapshot['group']
        return self.ctx.plan('array-recovery', body, phrase)

    def backup(self, ident, snapshot):
        existing = list(self.directory.glob('*/metadata.tar'))
        if len(existing) >= 16 or shutil.disk_usage(self.ctx.directory).free < 512 * 1024**2:
            raise ValueError('Recovery backup capacity reached; retain/download your current backup and remove older backups before continuing')
        target = self.directory / ident;target.mkdir(parents=True, mode=0o700, exist_ok=False)
        for member in snapshot['members']:
            with open(member['device'], 'rb', buffering=0) as source:data = source.read(HEADER_BYTES)
            if hashlib.sha256(data).hexdigest() != member['header_sha256']:raise ValueError('Metadata changed while taking recovery backup')
            path = target / ('member-' + str(member['metadata']['role']) + '.bin')
            with path.open('xb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
            path.chmod(0o600)
            if hashlib.sha256(path.read_bytes()).hexdigest() != member['header_sha256']:raise ValueError('Metadata backup verification failed')
        manifest = target / 'manifest.json';manifest.write_text(json.dumps(snapshot, indent=2));manifest.chmod(0o600)
        with manifest.open('rb') as stream:os.fsync(stream.fileno())
        archive = target / 'metadata.tar'
        with tarfile.open(archive, 'x') as tar:
            for path in sorted(target.iterdir()):
                if path != archive:tar.add(path, arcname=path.name, recursive=False)
        archive.chmod(0o600)
        with archive.open('rb') as stream:os.fsync(stream.fileno())
        fd=os.open(target,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
        return {'id': ident, 'bytes': archive.stat().st_size, 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'scope': 'RAID metadata only; no file-content backup'}

    def apply(self, request, expected_mode):
        with self.ctx.lock():
            path, plan = self.ctx.reviewed(request, 'array-recovery');body = plan['body'];expected = body['snapshot'];mode = body['mode']
            if mode != expected_mode:raise ValueError('This permission cannot apply another recovery phase')
            backup = body.get('metadata_backup')
            if mode != 'mount':
                if request.get('backup_acknowledged') is not True:raise ValueError('Acknowledge the saved metadata backup before continuing')
                if not backup or not re.fullmatch('[a-f0-9]{32}', backup['id']):raise ValueError('Verified metadata backup is missing')
                archive=self.directory/backup['id']/'metadata.tar'
                if archive.is_symlink() or hashlib.sha256(archive.read_bytes()).hexdigest()!=backup['sha256']:raise ValueError('Recovery metadata backup changed')
            current = self.snapshot(expected['pool'], headers=mode != 'mount',live=mode=='mount')
            if mode=='mount' and (not current['array'] or current['array']['read_only']):raise ValueError('The writable array is no longer available')
            if current['array'] and set(current['array']['members'])!={m['device'] for m in current['members']}:raise ValueError('Active array membership changed')
            # Live progress may advance while planning an ordinary mount. Every
            # immutable disk, member, partition and root identity still matches.
            if mode == 'mount':
                for value in (current, expected):
                    value.pop('array', None)
                    for k in ('checkpoint_sectors','rebuilding_members','force_required'):value.pop(k,None)
                    for m in value['members']:
                        for k in ('events','state','recovery_start'):m['metadata'].pop(k,None)
            if canonical(current) != canonical(expected):raise ValueError('Recovery identities or state changed; inspect and make a fresh plan')
            self.ctx.consume(path, plan)
            result = {'id': plan['id'], 'mode': mode, 'phase': 'prepared', 'array_uuid': current['uuid'], 'parity_verified': False}
            key = 'array-recovery:' + normal(current['uuid'])
            def checkpoint(phase):
                result.update(phase=phase, updated_at=time.time());self.ctx.state.set(key, result)
            checkpoint('metadata-backup-verified' if mode != 'mount' else 'mounts-reviewed')
            try:
                if mode != 'mount':result['backup'] = backup
                pool, volumes = self.pools(current['pool'])
                if mode == 'readonly':
                    target = '/dev/md/fq-recover-' + normal(current['uuid'])[:12]
                    args = ['mdadm', '--assemble', '--readonly', target, '--uuid=' + current['uuid']]
                    if current['force_required']:args.append('--force')
                    result['metadata_clean_override'] = current['force_required']
                    checkpoint('read-only-assembly-requested')
                    self.ctx.run(*args, *[m['device'] for m in current['members']], timeout=30)
                    device = self.storage.array_device(pool)
                    if self.ctx.run('blockdev', '--getro', device).strip() != '1':raise ValueError('Read-only state was not verified; no further operation attempted')
                    result['array'] = self.storage.inspect_array(pool);checkpoint('read-only-inspection-ready')
                    return result
                device = self.storage.array_device(pool)
                if mode == 'resume':
                    checkpoint('writable-resume-requested');self.ctx.run('mdadm', '--readwrite', device, timeout=15)
                result['mounts'] = []
                if body['mount_volumes']:
                    for volume in volumes:
                        try:self.ctx.volume(volume['name']);result['mounts'].append({'name': volume['name'], 'state': 'mounted'});continue
                        except (ValueError, OSError):pass
                        block = self.storage.data_device(volume)
                        if self.ctx.run('blkid', '-s', 'UUID', '-o', 'value', block).strip() != volume['filesystem_uuid']:raise ValueError('Filesystem identity changed')
                        unit = self.ctx.run('systemd-escape', '--path', '--suffix=mount', volume['mountpoint']).strip()
                        props = dict(line.split('=', 1) for line in self.ctx.run('systemctl', 'show', unit, '-p', 'ActiveState', '-p', 'Job').splitlines() if '=' in line)
                        if props.get('ActiveState') == 'failed':raise ValueError('An existing mount failed; inspect its service log before a new recovery plan')
                        if not props.get('Job'):
                            target = Path(volume['mountpoint']);target.mkdir(mode=0o000, parents=True, exist_ok=True)
                            self.ctx.run('systemd-mount', '--collect', '--no-block', '--type=ext4', '--options=nodev,nosuid,noexec', block, str(target), timeout=10)
                        result['mounts'].append({'name': volume['name'], 'state': 'requested; filesystem check may still be running'})
                checkpoint('submitted');result['completed'] = False
                return result
            except Exception as error:
                result['error'] = str(error);checkpoint('needs-inspection');raise

    def backup_list(self, request=None):
        items=[]
        for folder in self.directory.glob('*'):
            if not folder.is_dir() or folder.is_symlink() or not re.fullmatch('[a-f0-9]{32}',folder.name):continue
            try:
                archive=folder/'metadata.tar';manifest=folder/'manifest.json'
                if archive.is_symlink() or manifest.is_symlink():continue
                value=json.loads(manifest.read_text());info=archive.stat()
                items.append({'id':folder.name,'bytes':info.st_size,'created_at':info.st_mtime,'array_uuid':value['uuid'],'group':value['group']})
            except (OSError,ValueError,KeyError):continue
        items.sort(key=lambda x:x['created_at'],reverse=True)
        newest={}
        for item in items:
            item['protected']=item['array_uuid'] not in newest
            newest[item['array_uuid']]=True
        return {'items':items,'retention':'The latest complete metadata backup for each array is always retained. Download older backups before deleting them.'}

    def backup_remove(self, request):
        ident=request.get('id')
        if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{32}',ident) or request.get('confirmation')!='DELETE METADATA '+ident or request.get('backup_copied') is not True:raise ValueError('Confirm this exact metadata backup and its independent saved copy')
        with self.ctx.lock():
            items=self.backup_list()['items'];item=next((v for v in items if v['id']==ident),None)
            if not item or item['protected']:raise ValueError('The latest complete metadata backup must be retained')
            # A new plan or active operation may still need this backup.
            for path in (self.ctx.directory/'plans').glob('*.json'):
                plan=json.loads(path.read_text());backup=plan.get('body',{}).get('metadata_backup') or {}
                if not plan.get('consumed') and 0<=time.time()-plan.get('created_at',0)<600 and backup.get('id')==ident:raise ValueError('This backup belongs to a current recovery plan')
            last=self.ctx.state.setting('array-recovery:'+normal(item['array_uuid']),{})
            if (last.get('backup') or {}).get('id')==ident:raise ValueError('This backup belongs to the latest recorded recovery; retain it for inspection')
            folder=self.directory/ident
            for path in folder.iterdir():
                if path.is_symlink() or not path.is_file() or path.name not in {'metadata.tar','manifest.json',*[f'member-{n}.bin' for n in range(4)]}:raise ValueError('Unexpected backup contents; no files deleted')
            shutil.rmtree(folder)
        return {'deleted':ident,'latest_backup_retained':True}

    def download(self, request):
        ident = request.get('id', '')
        if not isinstance(ident, str) or not re.fullmatch('[a-f0-9]{32}', ident):raise ValueError('Choose a recovery metadata backup')
        path = self.directory / ident / 'metadata.tar'
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd);offset = request.get('offset', 0);count = request.get('count', 512 * 1024)
            if not stat.S_ISREG(info.st_mode) or type(offset) is not int or offset < 0 or type(count) is not int or not 1 <= count <= 512 * 1024:raise ValueError('Invalid backup read')
            return {'filename': 'raid-metadata-' + ident[:8] + '.tar', 'total_bytes': info.st_size,
                    'etag': f'{info.st_ino}:{info.st_size}:{info.st_mtime_ns}', 'data_base64': base64.b64encode(os.pread(fd, count, offset)).decode()}
        finally:os.close(fd)
