#!/usr/bin/env python3
"""Test PID1 mount visibility under the retained broker isolation, on one owned loop file.

No real disk, data pool, user, share, flash or VPN configuration is changed.
"""
import argparse
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

def command(*args,check=True):
 r=subprocess.run(args,capture_output=True,text=True,timeout=120)
 if check and r.returncode:raise ValueError(str(args[:4])+': '+r.stdout[:2000]+r.stderr[:2000])
 return r

INNER='''import sys,json
from pathlib import Path
from freeqnap.nas.common import Context
from freeqnap.nas.storage import Storage
from freeqnap.state import atomic
root,device,target,uuid=map(str,sys.argv[1:])
context=Context(root)
pool={'name':'fixture','mountpoint':target,'filesystem_uuid':uuid,'block_device':device,'encrypted':False}
context.save({'pools':{'fixture':pool},'shares':{},'users':{},'repositories':{},'libraries':{}})
try:Storage(context).mount(pool)
except Exception:
 print('PRIVATE NAMESPACE',context.run('findmnt','-J','-M',target,'-o','TARGET,SOURCE,FSTYPE,UUID,OPTIONS'),flush=True)
 print('DEVICE UUID',context.run('blkid','-s','UUID','-o','value',device),flush=True)
 raise
Path(target,'proof.txt').write_text('FreeQNAP private fixture, host mount visibility')
atomic(Path(root)/'inner-result.json',{'private_namespace_mount_uuid_verified':True})
'''

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--confirm-loop-fixture',action='store_true');a=p.parse_args()
 if not a.confirm_loop_fixture or os.geteuid()!=0:raise SystemExit('Explicit local-root loop-fixture confirmation required')
 token=secrets.token_hex(6);root=Path('/var/lib/freeqnap-system')/('mount-fixture-'+token);root.mkdir(mode=0o700)
 image=root/'owned.img';target=Path('/srv/freeqnap/volumes')/('mount-fixture-'+token)
 image.touch(mode=0o600)
 with image.open('r+b') as f:f.truncate(96*1024**2)
 device=None;error=None
 try:
  device=command('losetup','--find','--show',str(image)).stdout.strip()
  identity=json.loads(command('losetup','--list','--json','--output','NAME,BACK-FILE',device).stdout)['loopdevices']
  if len(identity)!=1 or Path(identity[0]['back-file']).resolve()!=image.resolve():raise ValueError('Loop backing-file identity differs')
  command('mkfs.ext4','-q','-F',device)
  uuid=command('blkid','-s','UUID','-o','value',device).stdout.strip()
  command('systemd-run','--pipe','--wait','--collect','--unit=freeqnap-mount-fixture-'+token,
    '--property=User=root','--property=Group=freeqnap','--property=WorkingDirectory=/opt/freeqnap/current',
    '--property=ProtectSystem=strict','--property=ProtectHome=yes','--property=PrivateTmp=yes','--property=NoNewPrivileges=yes',
    '--property=ReadWritePaths=/etc /var/lib/freeqnap-system /srv/freeqnap /run /dev',
    '/usr/bin/python3','-B','-c',INNER,str(root),device,str(target),uuid)
  mounted=json.loads(command('findmnt','-J','-M',str(target),'-o','UUID').stdout)['filesystems']
  if len(mounted)!=1 or mounted[0]['uuid']!=uuid:raise ValueError('Host did not see the verified fixture mount')
  if (target/'proof.txt').read_text()!='FreeQNAP private fixture, host mount visibility':raise ValueError('Host marker differs')
  result={'private_namespace_mount_uuid_verified':True,'host_mount_uuid_verified':True,'host_file_readback_verified':True,'retained_broker_isolation':True,'real_disk_writes':False}
  (root/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
 except Exception as e:error=e;raise
 finally:
  if command('findmnt','-M',str(target),check=False).returncode==0:command('systemd-mount','--umount',str(target))
  if device:
   identity=json.loads(command('losetup','--list','--json','--output','NAME,BACK-FILE',device).stdout)['loopdevices']
   if len(identity)!=1 or Path(identity[0]['back-file']).resolve()!=image.resolve():raise ValueError('Refusing cleanup of a changed loop identity')
   command('losetup','--detach',device)
  image.unlink(missing_ok=True)
  if target.exists():target.rmdir()
if __name__=='__main__':main()
