#!/usr/bin/env python3
"""Install only a bound, explicitly erased OS-mirror plan from the RAM tools.

Flash is deliberately outside this program. This initial version stops on an
interrupted/failed operation and requires inspection; it never resumes blindly.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


def run(*arguments,timeout=120):
    return subprocess.run(arguments,check=True,text=True,capture_output=True,timeout=timeout).stdout.strip()


def identity(device):
    raw=(device/'device/vpd_pg80').read_bytes()
    if len(raw)<5 or raw[1]!=0x80 or int.from_bytes(raw[2:4],'big')!=len(raw)-4:
        raise ValueError('Invalid live disk identity framing')
    serial=raw[4:].decode('ascii').strip()
    wwid=(device/'device/wwid').read_text().strip()
    if not re.fullmatch(r'[A-Za-z0-9_. -]{1,64}',serial) or not re.fullmatch(r'naa\.[0-9a-f]{16}',wwid):
        raise ValueError('Unusable live disk identity')
    return {'serial':serial,'wwn':'0x'+wwid[4:],'size':int((device/'size').read_text())*512}


def validate_plan(plan,observed,fingerprint):
    if plan.get('schema')!=1 or plan.get('unit_fingerprint')!=fingerprint:
        raise ValueError('Plan belongs to a different NAS')
    if not re.fullmatch('[0-9a-f]{32}',plan.get('install_id','')):raise ValueError('Invalid installation ID')
    if plan.get('os_mirror_member_bytes')!=128*1024**3 or plan.get('boot_partition_bytes')!=512*1024**2:
        raise ValueError('Fresh reviewed 128 GiB OS layout required; old or missing geometry is refused')
    members=plan.get('os_mirror_serials',[]);rows=plan.get('erase_disks',[])
    serials=[r.get('serial') for r in rows]
    if len(members)!=2 or len(set(members))!=2 or not set(members)<=set(serials):raise ValueError('Two selected OS disks required')
    if not 2<=len(rows)<=4 or len(set(serials))!=len(rows):raise ValueError('Invalid explicit erase set')
    resolved=[]
    for row in rows:
        matches=[d for d in observed if d['serial']==row['serial']]
        if len(matches)!=1:raise ValueError('Disk serial missing or ambiguous')
        disk=matches[0]
        if any(disk[k]!=row[k] for k in ('serial','wwn','size')):raise ValueError('Live disk differs from approved identity')
        if disk['size']<(130 if disk['serial'] in members else 16)*1024**3 or not disk['internal_sata'] or disk['readonly'] or disk['busy']:
            raise ValueError('Disk is too small, external, read-only or in use')
        resolved.append(disk)
    artifacts=plan.get('artifacts',{})
    if set(artifacts)!={'debian-armhf-base.tar.gz','uImage'}:raise ValueError('Both pinned OS artifacts required')
    for record in artifacts.values():
        if not re.fullmatch('[0-9a-f]{64}',record.get('sha256','')) or not 0<record.get('bytes',0)<400000000:
            raise ValueError('Invalid artifact record')
    if plan.get('root_password_method') not in ('installer','first-login','deferred-key-only'):raise ValueError('Root password method required')
    return resolved


def preflight(plan):
    if os.geteuid()!=0:raise ValueError('Root required in the RAM setup environment')
    # statfs identifies the actual chroot backing filesystem, not a parsed path
    # in /proc/mounts that can refer to paths outside this RAM tools chroot.
    stat=ctypes.create_string_buffer(256)
    if ctypes.CDLL(None,use_errno=True).statfs(b'/',stat) or ctypes.c_long.from_buffer(stat).value!=0x01021994:
        raise ValueError('This installer must run from the temporary RAM tools filesystem')
    if Path('/proc/device-tree/compatible').read_bytes().split(b'\0')[0]!=b'qnap,ts-431xeu':raise ValueError('Wrong hardware')
    if not os.uname().release.startswith('6.12.114-eyeq-ts431xeu-freeqnap'):raise ValueError('Wrong kernel')
    if not Path('/run/freeqnap-cooling-ack').is_file() or not Path('/run/freeqnap-macs-verified').is_file():raise ValueError('Hardware startup checks not satisfied')
    temperatures=[int(p.read_text()) for p in Path('/sys/class/thermal').glob('thermal_zone*/temp')]
    if not temperatures or any(not 0<t<70000 for t in temperatures):raise ValueError('Thermal installation limit exceeded or unavailable')
    macs=sorted({p.read_text().strip() for p in Path('/sys/class/net').glob('*/address') if re.fullmatch(r'24:5e:be(:[0-9a-f]{2}){3}',p.read_text().strip())})
    if len(macs)!=3:raise ValueError('Missing factory identities')
    fingerprint=hashlib.sha256('\n'.join(macs).encode()).hexdigest()
    if Path('/run/freeqnap-ram-installer').read_text().strip()!=fingerprint:raise ValueError('RAM session identity mismatch')
    if any(p.name.startswith('md') for p in Path('/sys/class/block').iterdir()):raise ValueError('Active RAID device; reconcile before erasure')
    if len(Path('/proc/swaps').read_text().splitlines())!=1:raise ValueError('Active swap; reconcile before erasure')
    mounted={line.split()[2] for line in Path('/proc/self/mountinfo').read_text().splitlines()}
    observed=[]
    for path in sorted(Path('/sys/class/block').glob('sd[a-z]')):
        if '/0000:00:09.0/' not in str((path/'device').resolve()):continue
        disk=identity(path);nodes=[path,*path.glob(path.name+'[0-9]*')]
        disk.update(path='/dev/'+path.name,
            internal_sata='/0000:00:09.0/' in str((path/'device').resolve()),
            readonly=(path/'ro').read_text().strip()!='0',
            busy=any((p/'dev').read_text().strip() in mounted or any((p/'holders').iterdir()) for p in nodes))
        observed.append(disk)
    rows=validate_plan(plan,observed,fingerprint)
    for name,record in plan['artifacts'].items():
        p=Path('/source')/name
        if not p.is_file() or p.is_symlink() or p.stat().st_size!=record['bytes']:raise ValueError('Missing pinned OS artifact')
        digest=hashlib.sha256()
        with p.open('rb') as source:
            for chunk in iter(lambda:source.read(1024*1024),b''):digest.update(chunk)
        if digest.hexdigest()!=record['sha256']:raise ValueError('OS artifact checksum mismatch')
    if Path('/target').is_mount():raise ValueError('Previous installation still mounted; inspect before continuing')
    return rows


def write(path,value,mode=0o644):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value);p.chmod(mode)


def install(plan,disks):
    def progress(event,**details):
        print(json.dumps({'event':event,'at':time.time(),**details}),flush=True)
    members=plan['os_mirror_serials'];install_id=plan['install_id']
    progress('erase-start',disks=[d['serial'] for d in disks],install_id=install_id)
    for d in disks:
        device=d['path'];sysfs=Path('/sys/class/block')/Path(device).name
        # Repeat immutable identities immediately before this disk's first write.
        if identity(sysfs)!={k:d[k] for k in ('serial','wwn','size')}:raise ValueError('Disk changed before erasure')
        for part in sorted(sysfs.glob(sysfs.name+'[0-9]*')):run('wipefs','--all','/dev/'+part.name)
        run('wipefs','--all',device);run('sgdisk','--zap-all',device);run('sgdisk','--clear',device)
        if d['serial'] in members:
            run('sgdisk','--new=1:2048:+512M','--typecode=1:8300','--change-name=1:FREEQNAP_BOOT',
                '--new=2:0:+128G','--typecode=2:fd00','--change-name=2:FREEQNAP_ROOT',device)
        run('blockdev','--rereadpt',device)
        progress('partitioned',serial=d['serial'],os_member=d['serial'] in members)
    roots=[next(d['path']+'2' for d in disks if d['serial']==s) for s in members]
    deadline=time.monotonic()+10
    while not all(Path(p).is_block_device() for p in roots):
        if time.monotonic()>deadline:raise ValueError('New partitions did not appear')
        time.sleep(.1)
    Path('/dev/md').mkdir(exist_ok=True)
    run('mdadm','--create','/dev/md/freeqnap-root','--metadata=1.2','--level=1','--raid-devices=2',
        '--bitmap=internal','--name=freeqnap-root','--homehost=freeqnap','--run',*roots)
    run('mkfs.ext4','-F','-L','FREEQNAP_ROOT','/dev/md/freeqnap-root')
    Path('/target').mkdir(exist_ok=True)
    run('mount','-t','ext4','/dev/md/freeqnap-root','/target')
    progress('root-filesystem-created')
    run('tar','--numeric-owner','--xattrs','--acls','-xzf','/source/debian-armhf-base.tar.gz','-C','/target',timeout=300)
    root=Path('/target');md=run('mdadm','--detail','--export','/dev/md/freeqnap-root')
    md_uuid=next(line[8:] for line in md.splitlines() if line.startswith('MD_UUID='))
    fs_uuid=run('blkid','-s','UUID','-o','value','/dev/md/freeqnap-root')
    if not re.fullmatch(r'[0-9a-f]{8}(:[0-9a-f]{8}){3}',md_uuid) or not re.fullmatch(r'[0-9a-f-]{36}',fs_uuid):raise ValueError('Invalid generated filesystem identity')
    mac=min(p.read_text().strip().replace(':','') for p in Path('/sys/class/net').glob('*/address') if p.read_text().startswith('24:5e:be:'))
    hostname='freeqnap-'+mac[-6:]
    write(root/'etc/hostname',hostname+'\n');write(root/'etc/hosts','127.0.0.1 localhost\n127.0.1.1 '+hostname+'\n')
    write(root/'etc/freeqnap-install-id',install_id+'\n')
    write(root/'etc/mdadm/mdadm.conf','DEVICE /dev/sd*2\nHOMEHOST <ignore>\nAUTO -all\nARRAY /dev/md/freeqnap-root UUID='+md_uuid+'\nPROGRAM /usr/local/sbin/eyeq-raid-event\n')
    write(root/'etc/fstab','UUID='+fs_uuid+' / ext4 defaults,noatime 0 1\n')
    write(root/'root/.ssh/authorized_keys',Path('/root/.ssh/authorized_keys').read_text(),0o600)
    (root/'root/.ssh').chmod(0o700)
    write(root/'etc/freeqnap/require-root-password','Choose a private root password before regular login.\n',0o600)
    if plan['root_password_method']=='deferred-key-only':
        run('python3','/usr/local/lib/freeqnap/credentials.py','--root','/target','--expected-install-id',install_id,'--defer')
    write(root/'etc/freeqnap/installation.json',json.dumps({'schema':1,'install_id':install_id,'unit_fingerprint':plan['unit_fingerprint'],
        'root_password_method':plan['root_password_method'],'os_mirror_serials':members,'erase_disks':plan['erase_disks'],
        'artifacts':plan['artifacts'],'flash_installed':False},indent=2)+'\n',0o600)
    record='FORMAT=1\nMODEL=TS-431XeU\nINSTALL_ID='+install_id+'\nUNIT_MAC='+mac+'\nROOT_MD_UUID='+md_uuid+'\nROOT_FS_UUID='+fs_uuid+'\n'
    for index,serial in enumerate(members):
        boot=next(d['path']+'1' for d in disks if d['serial']==serial)
        run('mkfs.ext4','-F','-L','FREEQNAP_BOOT_'+str(index+1),boot)
        directory=Path('/run/freeqnap-boot-'+str(index+1));directory.mkdir(exist_ok=True)
        run('mount','-t','ext4',boot,str(directory))
        write(directory/'freeqnap/installation.conf',record,0o600)
        # Preserve the checked bootstrap as a recovery artifact on both members.
        run('cp','/source/uImage',str(directory/'freeqnap/uImage'))
        run('sync');run('umount',str(directory))
    run('sync')
    # The optional private password step chroots into this installed root.
    # Supply its device files without starting any installed OS service.
    run('mount','--bind','/dev','/target/dev')
    progress('disk-os-installed',install_id=install_id,root_md_uuid=md_uuid,root_fs_uuid=fs_uuid,
        root_password_set=False,flash_written=False,root_left_mounted='/target')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--erase-confirmation',help='The exact installation ID; omit for read-only preflight')
    a=p.parse_args();plan=json.loads(a.plan.read_text());rows=preflight(plan)
    if a.erase_confirmation is None:
        print(json.dumps({'preflight_passed':True,'disks':rows,'writes_performed':False}));return
    if a.erase_confirmation!=plan['install_id']:raise ValueError('Erase confirmation does not match this plan')
    install(plan,rows)


if __name__=='__main__':main()
