"""Validated native SMB/NFS/AFP configurations; selected, mounted shares only."""
import grp
import ipaddress
import json
import os
import pwd
import re
import secrets
import socket
from pathlib import Path
from xml.etree import ElementTree as ET
from .common import name, secret
from ..state import atomic

SERVICES = ('freeqnap-smb', 'freeqnap-nfs', 'freeqnap-afp', 'freeqnap-dlna', 'freeqnap-discovery')

def quote(value):
    if not isinstance(value, str) or any(c in value for c in ('\n', '\r', '\x00', '"', '\\', ';', '{', '}')):
        raise ValueError('Unsupported configuration text')
    return '"' + value + '"'

def render(config, active, hostname):
    """Pure renderers make protocol defaults and export boundaries reviewable."""
    hostname = name(hostname)
    smb = ['[global]', '  server role = standalone server', '  security = user',
           '  map to guest = Never', '  server min protocol = SMB3_00',
           '  server signing = mandatory', '  smb encrypt = required',
           '  load printers = no', '  disable spoolss = yes', '  usershare allow guests = no',
           '  unix extensions = no', '  wide links = no', '  bind interfaces only = yes',
           '  interfaces = lo enp0s1', '  netbios name = ' + hostname[:15].upper(),
           '  ea support = yes', '  vfs objects = catia fruit streams_xattr',
           '  fruit:metadata = netatalk', '  fruit:resource = file', '']
    nfs = ['NFS_Core_Param { Protocols = 4; NFS_Port = 2049; Enable_NLM = false; Enable_RQUOTA = false; }',
           'NFSv4 { Minor_Versions = 1,2; }']
    afp = ['[Global]', '  hostname = ' + hostname, '  log level = default:warn',
           '  uam list = uams_dhx2.so', '  guest account = nobody', '  zeroconf = yes', '']
    discovery = ET.Element('service-group')
    ET.SubElement(discovery, 'name', {'replace-wildcards': 'yes'}).text = '%h FreeQNAP'
    protocols = set()
    for index, share in enumerate(sorted(active, key=lambda row: row['name']), 1):
        share_name = name(share['name'])
        path = share['path']
        if not re.fullmatch('/srv/freeqnap/volumes/[a-z][a-z0-9-]{0,30}/[a-z][a-z0-9-]{0,30}', path):
            raise ValueError('Invalid managed share path')
        # Protocol users are root-owned validated identifiers, never raw config fragments.
        users = [name(user) for user in share['users']]
        if not users:
            raise ValueError('At least one allowed NAS user is required')
        if 'smb' in share['protocols']:
            protocols.add('smb')
            smb += ['[' + share_name + ']', '  path = ' + path,
                    '  valid users = ' + ' '.join(users), '  guest ok = no',
                    '  read only = ' + ('yes' if share['read_only'] else 'no'),
                    '  follow symlinks = no', '  create mask = 0660', '  directory mask = 0770',
                    '  force group = fq-' + share_name, '  inherit acls = yes']
            if share.get('time_machine'):
                smb += ['  fruit:time machine = yes', '  fruit:time machine max size = ' + str(share['time_machine_gib']) + 'G']
            smb.append('')
        if 'nfs' in share['protocols']:
            protocols.add('nfs')
            clients = [str(ipaddress.ip_network(network, strict=True)) for network in share['nfs_clients']]
            if not clients:
                raise ValueError('NFS needs an explicit client subnet allowlist')
            user = config['users'][share['nfs_user']]
            export_id = share['export_id']
            nfs.append('EXPORT { Export_Id = ' + str(export_id) + '; Path = ' + quote(path) +
                       '; Pseudo = ' + quote('/' + share_name) + '; Access_Type = None; Protocols = 4; Transports = TCP;' +
                       ' SecType = sys; Squash = All_Squash; Anonymous_Uid = ' + str(user['uid']) +
                       '; Anonymous_Gid = ' + str(share['gid']) + '; FSAL { Name = VFS; } CLIENT { Clients = ' +
                       ','.join(clients) + '; Access_Type = ' + ('RO' if share['read_only'] else 'RW') + '; } }')
        if 'afp' in share['protocols']:
            protocols.add('afp')
            afp += ['[' + share_name + ']', '  path = ' + path, '  valid users = ' + ' '.join(users),
                    '  unix priv = yes', '  file perm = 0660', '  directory perm = 0770',
                    '  read only = ' + ('yes' if share['read_only'] else 'no'), '']
    for protocol, service_type, port in (('smb', '_smb._tcp', 445), ('nfs', '_nfs._tcp', 2049)):
        if protocol in protocols:
            item = ET.SubElement(discovery, 'service')
            ET.SubElement(item, 'type').text = service_type
            ET.SubElement(item, 'port').text = str(port)
    return {'smb': '\n'.join(smb) + '\n', 'nfs': '\n'.join(nfs) + '\n',
            'afp': '\n'.join(afp) + '\n', 'discovery': ET.tostring(discovery, encoding='unicode'),
            'protocols': sorted(protocols)}

class Sharing:
    def __init__(self, context, config_dir='/etc/freeqnap'):
        self.ctx = context
        self.config_dir = Path(config_dir)

    def user(self, request):
        username = name(request.get('name'))
        if username in ('root', 'admin', 'freeqnap', 'gerbera', 'nobody') or username.startswith(('freeqnap-','systemd-')):
            raise ValueError('Reserved account name')
        password = secret({'password': request.get('password')})
        with self.ctx.lock():
            config = self.ctx.config()
            exists = username in config['users']
            if not exists:
                try:pwd.getpwnam(username)
                except KeyError:pass
                else:raise ValueError('An unmanaged OS account already uses that name')
                self.ctx.run('useradd', '--no-create-home', '--shell', '/usr/sbin/nologin', username)
            self.ctx.run('chpasswd', data=username.encode() + b':' + password + b'\n')
            self.ctx.run('smbpasswd', '-s', '-a', username, data=password + b'\n' + password + b'\n')
            account = pwd.getpwnam(username)
            config['users'][username] = {'name': username, 'uid': account.pw_uid, 'gid': account.pw_gid,
                                         'login_shell': '/usr/sbin/nologin', 'enabled': True}
            self.ctx.save(config)
        return {'name': username, 'password_saved_in_job': False}

    def share(self, request):
        share_name = name(request.get('name'))
        pool, mount = self.ctx.volume(name(request.get('pool')))
        users = request.get('users', [])
        protocols = request.get('protocols', [])
        config = self.ctx.config()
        if not isinstance(users, list) or not users or not all(u in config['users'] for u in users):
            raise ValueError('Choose existing NAS users')
        if not isinstance(protocols, list) or not protocols or set(protocols) - {'smb', 'nfs', 'afp'}:
            raise ValueError('Choose SMB, NFS and/or AFP')
        clients = [str(ipaddress.ip_network(n, strict=True)) for n in request.get('nfs_clients', [])]
        nfs_user = request.get('nfs_user', users[0])
        if 'nfs' in protocols and (not clients or nfs_user not in users):
            raise ValueError('NFS requires explicit client networks and an allowed mapped NAS user')
        if request.get('time_machine') and 'smb' not in protocols:
            raise ValueError('Time Machine is provided through SMB')
        limit = int(request.get('time_machine_gib', 500))
        if not 1 <= limit <= 100000:
            raise ValueError('Invalid Time Machine quota')
        with self.ctx.lock():
            config = self.ctx.config()
            old = config['shares'].get(share_name)
            if old and old['pool'] != pool['name']:
                raise ValueError('An existing share cannot silently move to another pool')
            folder = mount / share_name
            if folder.is_symlink():
                raise ValueError('Share root may not be a symbolic link')
            folder.mkdir(mode=0o770, exist_ok=True)
            try:group = grp.getgrnam('fq-' + share_name)
            except KeyError:
                self.ctx.run('groupadd', 'fq-' + share_name);group = grp.getgrnam('fq-' + share_name)
            os.chown(folder, 0, group.gr_gid)
            folder.chmod(0o2770)
            self.ctx.run('setfacl', '-m', 'g::rwx,d:u::rwx,d:g::rwx,d:o::---', str(folder))
            for user in config['users']:
                current = self.ctx.run('id', '-nG', user).split()
                wanted = set(current) - {'fq-' + share_name}
                if user in users:wanted.add('fq-' + share_name)
                self.ctx.run('usermod', '-G', ','.join(sorted(wanted)), user)
            config['shares'][share_name] = {'name': share_name, 'pool': pool['name'], 'path': str(folder),
                'users': users, 'protocols': protocols, 'read_only': bool(request.get('read_only')),
                'nfs_clients': clients, 'nfs_user': nfs_user, 'gid': group.gr_gid,
                'export_id': old['export_id'] if old else secrets.randbelow(60000) + 1000,
                'time_machine': bool(request.get('time_machine')), 'time_machine_gib': limit,
                'enabled': request.get('enabled', True) is True}
            self.ctx.save(config)
            return self.apply()

    def toggle(self, request):
        with self.ctx.lock():
            config=self.ctx.config();ident=name(request.get('name'))
            if ident not in config['shares']:raise ValueError('Unknown share')
            config['shares'][ident]['enabled']=request.get('enabled') is True
            self.ctx.save(config)
            return self.apply()

    def remove(self, request):
        with self.ctx.lock():
            ident=name(request.get('name'))
            if request.get('confirmation')!='REMOVE SHARE '+ident:raise ValueError('Type the share removal confirmation')
            config=self.ctx.config()
            if ident not in config['shares']:raise ValueError('Unknown share')
            if any(library['share']==ident for library in config['libraries'].values()):raise ValueError('Remove its media library first')
            del config['shares'][ident];self.ctx.save(config)
            return {**self.apply(),'data_deleted':False}

    def active(self):
        active = []
        for share in self.ctx.config()['shares'].values():
            if not share['enabled']:continue
            try:
                pool, mount = self.ctx.volume(share['pool'])
                if Path(share['path']).parent != mount or Path(share['path']).is_symlink():
                    continue
                active.append(share)
            except (ValueError, OSError):continue
        return active

    def stop(self):
        for service in SERVICES:
            self.ctx.run('systemctl', 'stop', service, timeout=45)

    def apply(self):
        config = self.ctx.config()
        active = self.active()
        rendered = render(config, active, socket.gethostname().split('.')[0])
        self.config_dir.mkdir(mode=0o750, exist_ok=True)
        # Stop before replacing exports, including on a disappeared/locked mount.
        for service in ('freeqnap-smb', 'freeqnap-nfs', 'freeqnap-afp'):
            self.ctx.run('systemctl', 'stop', service, timeout=45)
        paths = {'smb': 'smb.conf', 'nfs': 'ganesha.conf', 'afp': 'afp.conf'}
        for kind, filename in paths.items():
            path = self.config_dir / filename
            temporary = path.with_name(path.name + '.next')
            temporary.write_text(rendered[kind]);temporary.chmod(0o600)
            if kind == 'smb':self.ctx.run('testparm', '-s', str(temporary))
            os.replace(temporary, path)
        discovery = Path('/etc/avahi/services')
        discovery.mkdir(mode=0o755, exist_ok=True)
        (discovery / 'freeqnap.service').write_text(rendered['discovery'])
        for kind, service in (('smb', 'freeqnap-smb'), ('nfs', 'freeqnap-nfs'), ('afp', 'freeqnap-afp')):
            if kind in rendered['protocols']:self.ctx.run('systemctl', 'start', service, timeout=45)
        return {'active_shares': [s['name'] for s in active], 'protocols': rendered['protocols']}
