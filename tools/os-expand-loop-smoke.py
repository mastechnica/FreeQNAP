"""Bounded disposable-loop rehearsal; never selects physical disks."""
import argparse,hashlib,json,os,secrets,shutil,subprocess,sys,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--confirm-loop-fixture',action='store_true',required=True);p.parse_args()
if sys.platform!='linux' or os.geteuid()!=0:raise SystemExit('Explicit Linux root fixture required')
root=Path('/var/lib/freeqnap-validation')/('os-expand-loop-'+secrets.token_hex(6));root.mkdir(mode=0o700)
assert shutil.disk_usage(root).free>2*1024**3
loops=[];arrays=[];mounts=[];report={}

def run(*args,timeout=120):
 r=subprocess.run(args,capture_output=True,timeout=timeout)
 if r.returncode:raise RuntimeError(Path(args[0]).name+' fixture failed: '+r.stderr.decode()[-1200:])
 return r.stdout.decode().strip()
def safe():
 for dev in loops:
  rows=json.loads(run('losetup','-J','--list','--output','NAME,BACK-FILE',dev))['loopdevices']
  assert len(rows)==1 and Path(rows[0]['back-file']).parent==root and Path(dev).name.startswith('loop')
def idle(md):
 p=Path('/sys/class/block')/Path(md).resolve().name/'md';deadline=time.monotonic()+120
 while time.monotonic()<deadline:
  degraded=(p/'degraded').read_text().strip();action=(p/'sync_action').read_text().strip()
  if action=='idle' and degraded=='0':return
  if degraded not in ('0','1'):raise RuntimeError('Unexpected fixture membership fault')
  time.sleep(.2)
 raise RuntimeError('Fixture sync did not finish')
def table(d):return json.loads(run('sfdisk','--json',d))['partitiontable']
def create_data(md):
 safe();parts=[d+('p3' if i<2 else 'p1') for i,d in enumerate(loops)]
 run('mdadm','--create',md,'--metadata=1.2','--level=5','--raid-devices=4','--size=65536','--data-offset=8M','--bitmap=internal','--name='+Path(md).name,'--homehost=freeqnap','--run',*parts);arrays.append(md);idle(md);return parts
try:
 for i in range(4):
  image=root/('member-'+str(i)+'.img')
  with image.open('xb') as f:f.truncate(512*1024**2)
  d=run('losetup','--find','--show','--partscan',str(image));loops.append(d);safe();run('sgdisk','--clear',d)
  if i<2:run('sgdisk','--new=1:2048:+8M','--typecode=1:8300','--new=2:0:+64M','--typecode=2:fd00','--new=3:0:0','--typecode=3:fd00',d)
  else:run('sgdisk','--new=1:2048:0','--typecode=1:fd00',d)
  run('partx','-u',d)
 rootmd='/dev/md/'+root.name+'r';datamd='/dev/md/'+root.name+'d'
 assert not Path(rootmd).exists() and not Path(datamd).exists()
 run('mdadm','--create',rootmd,'--metadata=1.2','--level=1','--raid-devices=2','--data-offset=8M','--bitmap=internal','--name='+Path(rootmd).name,'--homehost=freeqnap','--run',loops[0]+'p2',loops[1]+'p2');arrays.append(rootmd);idle(rootmd)
 run('mkfs.ext4','-q',rootmd);target=root/'os';target.mkdir();run('mount',rootmd,str(target));mounts.append(target)
 payload=os.urandom(1024**2);(target/'proof').write_bytes(payload);os.sync();root_uuid=run('blkid','-s','UUID','-o','value',rootmd);old_size=int(run('blockdev','--getsize64',rootmd));inode=(target/'proof').stat().st_ino
 before=[table(d) for d in loops[:2]];boot_hashes=[hashlib.sha256(Path(d+'p1').read_bytes()).hexdigest() for d in loops[:2]]
 parts=create_data(datamd)
 run('mdadm','--stop',datamd);arrays.remove(datamd)
 for p in parts:safe();run('mdadm','--zero-superblock',p)
 for i,d in enumerate(loops[:2]):
  safe();old=before[i]['partitions'][1];run('partx','-d','-n','3',d)
  run('sgdisk','--delete=3','--delete=2','--new=2:'+str(old['start'])+':+128M','--typecode=2:fd00','--partition-guid=2:'+old['uuid'],'--change-name=2:FREEQNAP_ROOT',d)
  run('partx','-u','-n','2',d)
  assert int(run('blockdev','--getsize64',d+'p2'))==128*1024**2
  now=table(d);assert now['id']==before[i]['id'] and now['partitions'][0]==before[i]['partitions'][0]
  assert now['partitions'][1]['uuid']==old['uuid'] and now['partitions'][1]['start']==old['start']
 safe();run('mdadm','--grow',rootmd,'--size=max');idle(rootmd)
 run('umount',str(target));mounts.remove(target);run('e2fsck','-f','-p',rootmd);run('resize2fs',rootmd);run('mount',rootmd,str(target));mounts.append(target)
 assert run('blkid','-s','UUID','-o','value',rootmd)==root_uuid and (target/'proof').stat().st_ino==inode and (target/'proof').read_bytes()==payload
 assert int(run('blockdev','--getsize64',rootmd))>old_size
 assert [hashlib.sha256(Path(d+'p1').read_bytes()).hexdigest() for d in loops[:2]]==boot_hashes
 for d in loops[:2]:safe();run('sgdisk','--new=3:0:0','--typecode=3:fd00',d);run('partx','-a','-n','3',d)
 create_data(datamd);run('mkfs.ext4','-q',datamd);data=root/'data';data.mkdir();run('mount',datamd,str(data));mounts.append(data);(data/'proof').write_bytes(payload);os.sync();assert (data/'proof').read_bytes()==payload
 report={'owned_loop_only':True,'mounted_root_member_partition_growth':True,'root_md_and_offline_ext4_growth':True,'online_ext4_growth_accepted':False,'root_uuid_inode_and_payload_preserved':True,'boot_partition_bytes_and_guids_preserved':True,'data_raid5_recreated_and_file_verified':True,'physical_os_resize_accepted':False}
finally:
 for target in reversed(mounts):run('umount',str(target))
 for md in reversed(arrays):safe();run('mdadm','--stop',md)
 for dev in reversed(loops):safe();run('losetup','--detach',dev);loops.remove(dev)
 if report:shutil.rmtree(root)
if report:print(json.dumps(report,indent=2))
