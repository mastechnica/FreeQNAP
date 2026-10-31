#!/usr/bin/env python3
"""Owned-loop single-survivor RAID1 validation; never assembles physical devices."""
import argparse,hashlib,json,os,secrets,shutil,subprocess,sys,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--confirm-loop-fixture',action='store_true',required=True);p.parse_args()
if os.geteuid()!=0 or sys.platform!='linux':raise SystemExit('Explicit Linux root fixture required')
root=Path('/var/lib/freeqnap-validation')/('survivor-'+secrets.token_hex(8));root.mkdir(mode=0o700,parents=True);policy=Path(__file__).resolve().parents[1]/'installer/target/boot-policy.sh'
if not policy.is_file():raise SystemExit('Run from a checkout including installer bootstrap source')
results=[]
def run(*args,timeout=60):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 if p.returncode:raise ValueError(Path(args[0]).name+' failed in root-survivor fixture')
 return p.stdout.strip()
def exact(loop,folder):
 rows=json.loads(run('losetup','--json','--list','--output','NAME,BACK-FILE',loop))['loopdevices']
 if len(rows)!=1 or Path(rows[0]['back-file']).parent!=folder:raise ValueError('Owned loop identity changed')
for survivor in (0,1):
 folder=root/str(survivor);folder.mkdir(mode=0o700);mount=folder/'mount';mount.mkdir();loops=[];md='/dev/md/fq-survivor-'+secrets.token_hex(4);assembled=False;mounted=False
 try:
  for n in range(2):
   file=folder/(str(n)+'.img')
   with file.open('xb') as stream:stream.truncate(128*1024**2)
   loop=run('losetup','--find','--show',str(file));loops.append(loop);exact(loop,folder)
  run('mdadm','--create',md,'--metadata=1.2','--level=1','--raid-devices=2','--bitmap=internal','--run',*loops);assembled=True
  fields=dict(x.split('=',1) for x in run('mdadm','--detail','--export',md).splitlines() if '=' in x);uuid=fields['MD_UUID'];device=Path(md).resolve().name
  for _ in range(120):
   if (Path('/sys/class/block')/device/'md/sync_action').read_text().strip()=='idle':break
   time.sleep(.1)
  else:raise ValueError('Fixture initial sync did not finish')
  run('mkfs.ext4','-q',md);fs_uuid=run('blkid','-s','UUID','-o','value',md);run('mount','-t','ext4',md,str(mount));mounted=True
  install=secrets.token_hex(16);(mount/'etc').mkdir();(mount/'etc/freeqnap-install-id').write_text(install);data=b'FreeQNAP survivor fixture\n'*4096
  with (mount/'proof.bin').open('xb') as out:out.write(data);out.flush();os.fsync(out.fileno())
  run('umount',str(mount));mounted=False;run('mdadm','--stop',md);assembled=False
  candidate=loops[survivor];exact(candidate,folder);metadata=folder/'member-export';metadata.write_text(run('mdadm','--examine','--export',candidate))
  run('sh','-c','. "$1"; root_member_metadata "$2" "$3"','test',str(policy),str(metadata),uuid)
  run('mdadm','--assemble','--run','--readonly',md,'--uuid='+uuid,candidate);assembled=True;device=Path(md).resolve().name
  assert (Path('/sys/class/block')/device/'md/degraded').read_text().strip()=='1';assert run('blkid','-s','UUID','-o','value',md)==fs_uuid
  run('mount','-t','ext4','-o','ro,noload',md,str(mount));mounted=True;assert (mount/'etc/freeqnap-install-id').read_text()==install;assert hashlib.sha256((mount/'proof.bin').read_bytes()).digest()==hashlib.sha256(data).digest();run('umount',str(mount));mounted=False
  run('mdadm','--readwrite',md);check=subprocess.run(['e2fsck','-p',md],capture_output=True);assert check.returncode in (0,1)
  results.append({'survivor_member_index':survivor,'exact_uuid_readonly_assembly':True,'filesystem_installation_and_data_verified':True,'fsck_passed':True})
 finally:
  if mounted:run('umount',str(mount))
  if assembled:run('mdadm','--stop',md)
  for loop in loops:exact(loop,folder);run('losetup','--detach',loop)
if len(results)==2:shutil.rmtree(root)
print(json.dumps({'owned_loop_results':results,'physical_disks_written':False,'installed_boot_image_changed':False,'physical_degraded_boot_accepted':False},indent=2))
