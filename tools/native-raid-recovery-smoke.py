#!/usr/bin/env python3
"""Bounded RAID5 failure/rebuild/reassembly using only identity-checked owned loop files.

Writes disposable files on one explicitly identified internal data filesystem.
Never changes membership of a physical array, formats a physical device, or reboots.
"""
import argparse,hashlib,json,mmap,os,secrets,shutil,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from freeqnap.nas.common import Context,name
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--pool',required=True);p.add_argument('--filesystem-uuid',required=True)
p.add_argument('--confirm-owned-loop-fixture',action='store_true',required=True);a=p.parse_args()
if sys.platform!='linux' or os.geteuid()!=0:raise SystemExit('Explicit native Linux root fixture required')
live=Context();pool,mount=live.volume(name(a.pool))
if pool.get('filesystem_uuid')!=a.filesystem_uuid or pool.get('kind')=='usb' or pool.get('read_only') or not pool.get('md_uuid'):raise SystemExit('Exact writable internal data filesystem required')
if mount==Path('/') or shutil.disk_usage(mount).free<2*1024**3:raise SystemExit('Non-root data filesystem with 2 GiB free required')
base=mount/'.freeqnap'/'validation'
for directory in (base.parent,base):
 if directory.is_symlink():raise SystemExit('Fixture parent cannot be a symlink')
 directory.mkdir(mode=0o700,exist_ok=True)
 if directory.resolve()!=directory:raise SystemExit('Fixture parent cannot escape the data filesystem')
root=base/('raid-recovery-'+secrets.token_hex(8));root.mkdir(mode=0o700);root_id=root.stat();target=root/'mount';target.mkdir()
md='/dev/md/fq-recovery-'+secrets.token_hex(4);loops=[];owned={};array_uuid=None;assembled=False;mounted=False;passed=False;report={}
def run(*args,timeout=45):
 r=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 if r.returncode:raise ValueError(Path(args[0]).name+' failed in owned-loop recovery fixture: '+r.stderr[-600:])
 return r.stdout.strip()
def filesystem_guard():
 p,m=live.volume(a.pool)
 if p['filesystem_uuid']!=a.filesystem_uuid or m!=mount or root.stat().st_ino!=root_id.st_ino or root.stat().st_dev!=root_id.st_dev:raise ValueError('Backing filesystem or fixture identity changed')
def loop_guard(loop):
 filesystem_guard();rows=json.loads(run('losetup','--json','--list','--output','NAME,BACK-FILE',loop))['loopdevices']
 if len(rows)!=1 or Path(rows[0]['back-file'])!=owned[loop]['path']:raise ValueError('Loop backing identity changed')
 f=owned[loop]['path'];st=f.stat()
 if f.is_symlink() or st.st_ino!=owned[loop]['inode'] or st.st_dev!=root_id.st_dev or st.st_size!=160*1024**2:raise ValueError('Fixture backing file changed')
def fields():return dict(x.split('=',1) for x in run('mdadm','--detail','--export',md).splitlines() if '=' in x)
def array_guard():
 for loop in loops:loop_guard(loop)
 if fields()['MD_UUID']!=array_uuid:raise ValueError('Fixture array UUID changed')
 block=Path('/sys/class/block')/Path(md).resolve().name
 members={str(Path('/dev')/x.name) for x in (block/'slaves').iterdir()}
 if not members or not members<=set(loops):raise ValueError('Array contains an unowned member')
 return block/'md'
def add_loop(index):
 filesystem_guard();file=root/('member-'+str(index)+'.img')
 with file.open('xb') as stream:stream.truncate(160*1024**2)
 loop=run('losetup','--find','--show',str(file));owned[loop]={'path':file,'inode':file.stat().st_ino};loops.append(loop);loop_guard(loop);return loop
def settle():
 deadline=time.monotonic()+180
 while time.monotonic()<deadline:
  d=array_guard()
  if (d/'sync_action').read_text().strip()=='idle' and (d/'degraded').read_text().strip()=='0':return
  time.sleep(.25)
 raise ValueError('Owned-loop recovery did not complete within 180 seconds')
def write_proof(path,seed):
 with path.open('xb') as out:
  for _ in range(4):out.write(seed)
  out.flush();os.fsync(out.fileno())
 return hashlib.sha256(seed*4).hexdigest()
def direct(path):
 fd=os.open(path,os.O_RDONLY|os.O_DIRECT);sha=hashlib.sha256()
 try:
  with mmap.mmap(-1,1024**2) as buffer:
   for offset in range(0,4*1024**2,1024**2):
    if os.preadv(fd,[buffer],offset)!=1024**2:raise ValueError('Short direct read')
    sha.update(buffer)
 finally:os.close(fd)
 return sha.hexdigest()
try:
 if os.path.lexists(md):raise ValueError('Fixture array name already exists')
 for n in range(4):add_loop(n)
 run('mdadm','--create',md,'--metadata=1.2','--level=5','--raid-devices=4','--size=131072','--data-offset=16M','--bitmap=internal','--run',*loops);assembled=True;array_uuid=fields()['MD_UUID'];settle();array_guard()
 run('mkfs.ext4','-q',md);run('mount','-t','ext4',md,str(target));mounted=True
 expected={'before.bin':write_proof(target/'before.bin',secrets.token_bytes(1024**2))};assert direct(target/'before.bin')==expected['before.bin']
 array_guard();failed=loops[3];run('mdadm',md,'--fail',failed);array_guard();run('mdadm',md,'--remove',failed)
 d=array_guard();assert (d/'degraded').read_text().strip()=='1';assert direct(target/'before.bin')==expected['before.bin'];report['degraded_direct_read_hash']=True
 expected['during.bin']=write_proof(target/'during.bin',secrets.token_bytes(1024**2));assert direct(target/'during.bin')==expected['during.bin'];report['degraded_write_and_direct_read_hash']=True
 replacement=add_loop(4);array_guard();run('mdadm',md,'--add',replacement);settle()
 for name,sha in expected.items():assert direct(target/name)==sha
 report['replacement_rebuild_and_both_hashes']=True
 run('umount',str(target));mounted=False;array_guard();run('mdadm','--stop',md);assembled=False
 survivors=[loop for loop in loops if loop!=failed]
 for loop in survivors:loop_guard(loop)
 run('mdadm','--assemble','--readonly','--run',md,'--uuid='+array_uuid,*survivors);assembled=True;d=array_guard();assert (d/'degraded').read_text().strip()=='0'
 run('mount','-t','ext4','-o','ro,noload',md,str(target));mounted=True
 for name,sha in expected.items():assert direct(target/name)==sha
 report.update(exact_uuid_readonly_reassembly_and_hashes=True,owned_loop_members=5,backing_member_bytes=160*1024**2,raw_physical_device_operations=False,physical_array_membership_changed=False,boot_or_flash_changed=False,physical_failure_rebuild_accepted=False,backing_files_on_internal_data_filesystem=True)
 passed=True
finally:
 if mounted:run('umount',str(target))
 if assembled:array_guard();run('mdadm','--stop',md)
 for loop in loops:loop_guard(loop);run('losetup','--detach',loop)
 if passed:
  filesystem_guard();shutil.rmtree(root)
if passed:print(json.dumps(report,indent=2))
