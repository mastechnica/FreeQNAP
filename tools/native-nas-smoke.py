#!/usr/bin/env python3
"""Explicit disposable-loop/native-service smoke test; never touches physical disks.

Requires root, Linux namespaces, installed NAS dependencies, and --confirm-loop-fixture.
Physical disk failure/rebuild and real client playback are separate acceptance tests.
"""
import argparse
import base64
import grp
import hashlib
import json
import os
import pwd
import secrets
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from freeqnap.nas.common import Context
from freeqnap.nas.filebackup import FileBackups
from freeqnap.nas.files import Files,MAX_CHUNK
from freeqnap.nas.sharing import render
from freeqnap.nas.media import Media
from freeqnap.nas.storage import Storage

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--confirm-loop-fixture',action='store_true',required=True);a=p.parse_args()
if os.geteuid()!=0 or sys.platform!='linux':raise SystemExit('Run explicitly as root on a disposable Linux test system')
ident=secrets.token_hex(4);pool_name='fq-test-'+ident
root=Path('/var/lib/freeqnap-validation')/ident;root.mkdir(mode=0o700,parents=True)
mount=Path('/srv/freeqnap/volumes')/pool_name;mount.mkdir(mode=0o700,parents=True)
loops=[];children=[];namespace=None;md='/dev/md/'+pool_name;mapping='fq-test-'+ident
mounted=False;array_created=False;opened=False;created_user=False;test_user='fqt'+ident
result={'fixture':ident,'physical_disks_written':False,'results':{},'acceptance_limits':['No physical rebuild/failure acceptance','NFS RPC only; no client file I/O','AFP status only; no client login/file I/O','DLNA configuration only; no player playback']}

def run(*command,data=None,env=None,timeout=120,**kwargs):
    value=subprocess.run(command,input=data,capture_output=True,env=env,timeout=timeout,**kwargs)
    if value.returncode:
        (root/'last-command-error.json').write_text(json.dumps({'command':command,'stdout':value.stdout.decode(errors='replace')[-6000:],'stderr':value.stderr.decode(errors='replace')[-6000:]},indent=2))
        raise RuntimeError(Path(command[0]).name+' failed; private diagnostic retained under '+str(root))
    return value.stdout.decode(errors='replace')

def safe_loop(device):
    rows=json.loads(run('losetup','--json','--list','--output','NAME,BACK-FILE',device))['loopdevices']
    if len(rows)!=1 or rows[0]['name']!=device or Path(rows[0]['back-file']).parent!=root:
        raise RuntimeError('Loop backing identity changed; refusing block operation')

def start(command):
    logfile=(root/('service-'+str(len(children))+'.log')).open('wb')
    child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=logfile,stderr=subprocess.STDOUT,start_new_session=True)
    logfile.close();children.append(child);return child

def inside(*command,**kwargs):return run('nsenter','--target',str(namespace.pid),'--net','--',*command,**kwargs)

def wait_port(port):
    code='import socket,time\nfor _ in range(40):\n try:\n  s=socket.create_connection(("127.0.0.1",'+str(port)+'),.3);s.close();break\n except OSError:time.sleep(.25)\nelse:raise SystemExit(1)'
    inside('python3','-c',code,timeout=20)

try:
    for number in range(2):
        path=root/('disk'+str(number)+'.img')
        with path.open('xb') as stream:stream.truncate(384*1024**2)
        device=run('losetup','--find','--show',str(path)).strip();loops.append(device);safe_loop(device)
    if Path(md).exists():raise RuntimeError('Fixture array name unexpectedly exists')
    array_created=True
    run('mdadm','--create',md,'--metadata=1.2','--level=1','--raid-devices=2','--bitmap=internal','--run',*loops)
    array_created=True
    password=secrets.token_urlsafe(32).encode()
    run('cryptsetup','luksFormat','--type','luks2','--batch-mode','--pbkdf','argon2id','--pbkdf-memory','65536','--pbkdf-parallel','1','--iter-time','500','--key-file','-',md,data=password)
    run('cryptsetup','open','--key-file','-',md,mapping,data=password);opened=True
    run('mkfs.ext4','-q','/dev/mapper/'+mapping)
    run('mount','-t','ext4','-o','nodev,nosuid,noexec','/dev/mapper/'+mapping,str(mount));mounted=True
    fs_uuid=run('blkid','-s','UUID','-o','value','/dev/mapper/'+mapping).strip()
    ctx=Context(root/'state',runner=run)
    config=ctx.config();config['pools'][pool_name]={'name':pool_name,'mountpoint':str(mount),'filesystem_uuid':fs_uuid,'encrypted':True,'level':'mirror','md_device':md,'md_uuid':dict(line.split('=',1) for line in run('mdadm','--detail','--export',md).splitlines() if '=' in line)['MD_UUID'],'luks_uuid':run('cryptsetup','luksUUID',md).strip(),'block_device':'/dev/mapper/'+mapping};ctx.save(config)
    encryption=Storage(ctx);keyplan=encryption.key_plan({'pool':pool_name});newkey=os.urandom(64)
    keyresult=encryption.add_key({'plan_id':keyplan['id'],'digest':keyplan['digest'],'confirmation':keyplan['confirmation'],'existing_secret':{'password':password.decode()},'new_secret':{'key_base64':base64.b64encode(newkey).decode()}})
    assert keyresult['new_key_verified'];result['results']['luks_recovery_key_added_and_verified']=True
    header=encryption.header_backup({'pool':pool_name});part=encryption.artifact_read({'id':header['artifact_id'],'offset':0,'count':512})
    assert part['total_bytes']==header['bytes'] and len(base64.b64decode(part['data_base64']))==512;result['results']['luks_header_backup_readback']=True
    folder=mount/'files';folder.mkdir()
    payload=os.urandom(1024*1024);(folder/'original.bin').write_bytes(payload)
    config=ctx.config();config['shares']['files']={'name':'files','pool':pool_name,'path':str(folder),'gid':0};ctx.save(config)
    files=Files(ctx);upload=files.upload_begin({'share':'files','path':'uploaded.bin','bytes':len(payload)})
    chain='0'*64
    for offset in range(0,len(payload),MAX_CHUNK):
        chunk=payload[offset:offset+MAX_CHUNK];sha=hashlib.sha256(chunk).hexdigest()
        files.upload_chunk({'upload_id':upload['upload_id'],'offset':offset,'data_base64':base64.b64encode(chunk).decode(),'sha256':sha})
        chain=hashlib.sha256((chain+sha).encode()).hexdigest()
    verified=files.upload_finish({'upload_id':upload['upload_id'],'hash_chain':chain})
    assert verified['sha256']==hashlib.sha256(payload).hexdigest();result['results']['chunked_upload_readback']=True
    backup=FileBackups(ctx)
    backup.repository({'name':'fixture','kind':'local','pool':pool_name,'password':secrets.token_urlsafe(32)})
    snapshot=backup.backup({'repository':'fixture','shares':['files'],'same_pool_confirmation':'SAME POOL fixture'})
    (folder/'original.bin').write_bytes(b'changed after snapshot')
    restored=backup.restore({'repository':'fixture','snapshot':snapshot['snapshot_id'],'pool':pool_name},'restore-fixture')
    restored_file=Path(restored['staging_directory'])/str(folder/'original.bin').lstrip('/')
    assert restored_file.read_bytes()==payload and (folder/'original.bin').read_bytes()!=payload
    result['results']['restic_backup_restore_verified_no_live_overwrite']=True
    # Namespace prevents these temporary service tests from advertising or binding on the LAN.
    marker=root/'namespace-ready'
    namespace=start(['unshare','--net','python3','-c','import subprocess,pathlib,time;subprocess.run(["ip","link","set","lo","up"],check=True);pathlib.Path('+repr(str(marker))+').write_text("ready");time.sleep(1200)'])
    for _ in range(50):
        if marker.exists():break
        if namespace.poll() is not None:raise RuntimeError('Disposable network namespace failed')
        time.sleep(.1)
    else:raise RuntimeError('Network namespace not ready')
    try:pwd.getpwnam(test_user)
    except KeyError:pass
    else:raise RuntimeError('Fixture account name unexpectedly exists')
    run('useradd','--no-create-home','--shell','/usr/sbin/nologin',test_user);created_user=True
    user_password=secrets.token_urlsafe(24).encode()
    run('chpasswd',data=test_user.encode()+b':'+user_password+b'\n')
    run('smbpasswd','-s','-a',test_user,data=user_password+b'\n'+user_password+b'\n')
    account=pwd.getpwnam(test_user);os.chown(folder,account.pw_uid,account.pw_gid);folder.chmod(0o770)
    (folder/'original.bin').chmod(0o644);(folder/'uploaded.bin').chmod(0o644)
    spec={'name':'files','path':str(folder),'users':[test_user],'protocols':['smb','nfs','afp'],'read_only':False,'nfs_clients':['127.0.0.1/32'],'nfs_user':test_user,'gid':account.pw_gid,'export_id':1123}
    rendered=render({'users':{test_user:{'uid':account.pw_uid}}},[spec],'freeqnap-test')
    smb=root/'smb.conf';smb.write_text(rendered['smb'].replace('  interfaces = lo enp0s1','  interfaces = lo\n  smb ports = 1445').replace('  force group = fq-files','  force group = '+grp.getgrgid(account.pw_gid).gr_name))
    run('testparm','-s',str(smb))
    smbd=start(['nsenter','--target',str(namespace.pid),'--net','--','/usr/sbin/smbd','--foreground','--no-process-group','--configfile='+str(smb)]);wait_port(1445)
    credentials=root/'smb-auth';credentials.write_bytes(b'username = '+test_user.encode()+b'\npassword = '+user_password+b'\n');credentials.chmod(0o600)
    input_file=root/'client-input';input_file.write_bytes(payload);output_file=root/'client-output'
    inside('smbclient','//127.0.0.1/files','-p','1445','-A',str(credentials),'--client-protection=encrypt','-m','SMB3','-c','put '+str(input_file)+' smb-file.bin; get smb-file.bin '+str(output_file))
    assert output_file.read_bytes()==payload;result['results']['smb3_encrypted_write_read_sha256']=True
    ganesha=root/'ganesha.conf';ganesha.write_text(rendered['nfs'])
    nfs=start(['nsenter','--target',str(namespace.pid),'--net','--','/usr/bin/ganesha.nfsd','-F','-x','-L','STDERR','-f',str(ganesha),'-p',str(root/'ganesha.pid')]);wait_port(2049)
    ping='import socket,struct;body=struct.pack(">10I",71,0,2,100003,4,0,0,0,0,0);s=socket.create_connection(("127.0.0.1",2049));s.sendall(struct.pack(">I",0x80000000|len(body))+body);data=s.recv(512);assert len(data)>=28 and struct.unpack(">3I",data[4:16])==(71,1,0) and struct.unpack(">I",data[24:28])[0]==0;print("NFSv4 RPC replied")'
    inside('python3','-c',ping);result['results']['nfsv4_rpc_reply']=True
    afp=root/'afp.conf';afp.write_text(rendered['afp'].replace('  zeroconf = yes','  zeroconf = no\n  afp port = 5548\n  afp listen = 127.0.0.1'))
    afpd=start(['nsenter','--target',str(namespace.pid),'--net','--','/usr/sbin/netatalk','-d','-F',str(afp)]);wait_port(5548)
    status='import socket,struct;s=socket.create_connection(("127.0.0.1",5548));s.sendall(struct.pack(">BBHIII",0,3,1,0,0,0));data=s.recv(16384);assert len(data)>16 and data[0]==1 and data[1]==3;print("AFP DSI status replied")'
    inside('python3','-c',status);result['results']['afp_status_reply']=True
    run('ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=160x90:d=1','-an','-c:v','mpeg4','-q:v','8',str(folder/'clip.mp4'))
    (folder/'clip.nfo').write_text('<movie><title>Local fixture title</title><year>2026</year></movie>')
    media=Media(ctx);media.library({'name':'fixture','share':'files','online_metadata':False,'dlna':True,'public_lan_confirmation':'SHARE MEDIA fixture'})
    scan=media.scan({'library':'fixture'});assert scan['complete']
    catalog=media.catalog({'library':'fixture'});assert any(item['title']=='Local fixture title' for item in catalog['entries'])
    result['results']['native_media_scan_ffprobe_local_nfo']=True
    xml,libraries=media.dlna_config();xml=xml.replace('/var/lib/freeqnap-media',str(root/'media-home'))
    (root/'media-home').mkdir();gerbera=root/'gerbera.xml';gerbera.write_text(xml)
    run('gerbera','--check-config','--config',str(gerbera));result['results']['dlna_config_accepted']=True
    for child in reversed(children):
        if child.poll() is None:
            os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=10)
    # Reopen the same LUKS filesystem and verify retained data, with wrong-key refusal.
    run('umount',str(mount));mounted=False
    run('cryptsetup','close',mapping);opened=False
    bad=subprocess.run(['cryptsetup','open','--key-file','-',md,mapping],input=b'deliberately-wrong-fixture-password',capture_output=True)
    assert bad.returncode!=0
    run('cryptsetup','open','--key-file','-',md,mapping,data=password);opened=True
    run('mount','-t','ext4','/dev/mapper/'+mapping,str(mount));mounted=True
    assert (folder/'uploaded.bin').read_bytes()==payload;result['results']['luks_wrong_key_refused_and_correct_key_reopened']=True
    result['passed']=True
except Exception as error:
    result['passed']=False;result['error']=str(error)
finally:
    for child in reversed(children):
        if child.poll() is None:
            try:os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=10)
            except (ProcessLookupError,subprocess.TimeoutExpired):
                try:os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError:pass
    if created_user:
        try:run('smbpasswd','-x',test_user)
        except Exception:pass
        try:run('userdel',test_user)
        except Exception:pass
    cleanup=[]
    if mounted:
        try:run('umount',str(mount));mounted=False
        except Exception as error:cleanup.append(str(error))
    if opened and not mounted:
        try:run('cryptsetup','close',mapping);opened=False
        except Exception as error:cleanup.append(str(error))
    if array_created and not opened:
        try:run('mdadm','--stop',md);array_created=False
        except Exception as error:cleanup.append(str(error))
    if not array_created:
        for device in loops:
            try:safe_loop(device);run('losetup','--detach',device)
            except Exception as error:cleanup.append(str(error))
    result['cleanup_errors']=cleanup
    if not cleanup and not array_created and not opened and not mounted:
        for number in range(2):
            (root/('disk'+str(number)+'.img')).unlink(missing_ok=True)
        result['disposable_backing_images_removed']=True
    (root/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if not result.get('passed') or cleanup:raise SystemExit(1)
