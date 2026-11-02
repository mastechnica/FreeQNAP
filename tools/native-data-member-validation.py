#!/usr/bin/env python3
"""Operator-approved logical RAID5 data-member failure/re-add validation.

Default is preflight only. Requires a private fresh identity-bound plan, exact
confirmation, existing independent proof copies and root on the supported board.
Never formats, wipes, forces assembly, changes boot/root membership or unplugs a disk.
Run --apply as a non-restarting supervised service so SSH loss cannot abort recovery.
"""
import argparse,fcntl,hashlib,json,mmap,os,secrets,signal,stat,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from freeqnap.nas.common import Context
from freeqnap.nas.broker import Client
from freeqnap.state import atomic

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True);p.add_argument('--confirmation',required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
 if sys.platform!='linux' or os.geteuid()!=0 or Path('/proc/device-tree/compatible').read_bytes().split(b'\0')[0]!=b'qnap,ts-431xeu':raise SystemExit('Root on the supported NAS required')
 os.umask(0o077);st=a.plan.stat()
 if a.plan.is_symlink() or st.st_uid!=0 or st.st_mode&0o077:raise ValueError('Private root-owned regular plan required')
 plan=json.loads(a.plan.read_text());digest=hashlib.sha256(json.dumps({k:v for k,v in plan.items() if k!='plan_sha256'},sort_keys=True).encode()).hexdigest()
 if digest!=plan['plan_sha256'] or not 0<=time.time()-plan['created_at']<900 or a.confirmation!=plan['confirmation'] or a.confirmation!='VALIDATE RAID5 DATA MEMBER':raise ValueError('Plan digest, freshness or confirmation mismatch')
 if not plan.get('owner_approved') or plan.get('consumed'):raise ValueError('Unapproved or already consumed plan')
 ctx=Context();md=plan['array']['device'];member=plan['member']['path'];disk=plan['member']['disk'];expected=set(plan['array']['members']);result={'plan_sha256':digest,'started_at':time.time(),'physical_unplug':False,'os_mirror_changed':False,'usb_changed':False,'flash_changed':False};degraded_started=False;new_proof=None
 def run(*args,check=True):
  r=subprocess.run(args,capture_output=True,text=True,timeout=45)
  if check and r.returncode:raise ValueError(Path(args[0]).name+' failed; inspect the private journal')
  return r
 def text(*args):return run(*args).stdout.strip()
 def fields(*args):return dict(x.split('=',1) for x in text(*args).splitlines() if '=' in x)
 def norm(x):return x.replace(':','').replace('-','').lower()
 def guard():
  info=fields('mdadm','--detail','--export',md)
  if norm(info['MD_UUID'])!=norm(plan['array_uuid']) or info['MD_LEVEL']!='raid5' or info['MD_DEVICES']!='4':raise ValueError('Data array identity changed')
  current=json.loads(text('lsblk','-J','-d','-b','-o','PATH,SERIAL,WWN,SIZE',disk['path']))['blockdevices']
  if len(current)!=1 or current[0]!=disk:raise ValueError('Selected whole-disk identity changed')
  if text('blkid','-s','PARTUUID','-o','value',member)!=plan['member']['partuuid'] or not stat.S_ISBLK(os.stat(member).st_mode):raise ValueError('Selected partition identity changed')
  if '/dev/'+text('lsblk','-n','-d','-o','PKNAME',member)!=disk['path']:raise ValueError('Selected partition parent changed')
  if norm(fields('mdadm','--examine','--export',member)['MD_UUID'])!=norm(plan['array_uuid']):raise ValueError('Member metadata belongs to another array')
  root=Path(text('findmnt','-rn','-M','/','-o','SOURCE')).resolve().name
  roots={x.name for x in (Path('/sys/class/block')/root/'slaves').iterdir()}
  if root!=plan['root_device'] or roots!=set(plan['root_members_excluded']):raise ValueError('OS mirror identity changed')
  for r in roots:
   if '/dev/'+text('lsblk','-n','-d','-o','PKNAME','/dev/'+r)==disk['path']:raise ValueError('Selected disk also hosts the running OS')
  directory=Path('/sys/class/block')/Path(md).resolve().name
  members={'/dev/'+x.name for x in (directory/'slaves').iterdir()}
  if not expected-{member}<=members or not members<=expected:raise ValueError('Unexpected physical member set')
  return directory/'md',members
 def proof_guard(proof):
  pool,mount=ctx.volume(proof['pool']);file=Path(proof['path']);folder=file.parent
  if pool['filesystem_uuid']!=proof['filesystem_uuid'] or norm(pool['md_uuid'])!=norm(plan['array_uuid']) or not proof['independent_copy_verified']:raise ValueError('Proof filesystem identity changed')
  relative=folder.relative_to(mount/'.freeqnap'/'validation')
  if len(relative.parts)!=1 or not relative.name.startswith('physical-proof-') or file.name!='proof.bin' or file.is_symlink() or folder.is_symlink() or file.resolve()!=file:raise ValueError('Proof path is outside the owned fixture')
  fs=folder.stat();s=file.stat()
  if fs.st_ino!=proof['folder_inode'] or s.st_ino!=proof['file_inode'] or s.st_dev!=proof['device'] or s.st_size!=16777216:raise ValueError('Proof file identity changed')
  return file
 def direct(file):
  fd=os.open(file,os.O_RDONLY|os.O_DIRECT|os.O_NOFOLLOW);sha=hashlib.sha256()
  try:
   with mmap.mmap(-1,1024**2) as buffer:
    for offset in range(0,16777216,1024**2):
     if os.preadv(fd,[buffer],offset)!=1024**2:raise ValueError('Short proof direct read')
     sha.update(buffer)
  finally:os.close(fd)
  return sha.hexdigest()
 def verify_proofs():
  for proof in plan['proofs']:
   if direct(proof_guard(proof))!=proof['sha256']:raise ValueError('Saved proof hash mismatch')
 lock=Path('/run/lock/freeqnap-physical-raid-validation.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 directory,members=guard()
 if (directory/'degraded').read_text().strip()!='0' or (directory/'sync_action').read_text().strip()!='idle' or members!=expected:raise ValueError('A complete idle array is required')
 if len(plan['proofs'])!=2 or plan['max_new_degraded_data_bytes']!=16777216:raise ValueError('Unexpected proof/write scope')
 verify_proofs();n=Client().request('notifications.status');b=Client().request('notifications.rules')['buzzer']
 if any(c.get('enabled') for c in n['config'].values()) or b['enabled']:raise ValueError('Enabled external notifications or buzzer require separate test authorization')
 if not a.apply:print(json.dumps({'preflight_passed':True,'proof_hashes_match':True,'physical_membership_changed':False}));return
 record=Path('/var/lib/freeqnap-validation')/('physical-member-'+secrets.token_hex(8));record.mkdir(mode=0o700)
 def checkpoint(stage):result['stage']=stage;result['updated_at']=time.time();atomic(record/'result.json',result);print(json.dumps({'stage':stage,'record':str(record)}),flush=True)
 def rejoin():
  directory,members=guard();state=directory/('dev-'+Path(member).name)/'state'
  if member in members:
   value=state.read_text().strip()
   if 'faulty' not in value:return 'already-present'
   run('mdadm',md,'--remove',member);guard()
  r=run('mdadm',md,'--re-add',member,check=False);directory,members=guard()
  if member in members:return 're-add'
  if r.returncode==0:raise ValueError('Re-add reported success without the expected member')
  # The reviewed plan permits one ordinary add after an exact identity recheck.
  run('mdadm',md,'--add',member);guard();return 'standard-add'
 def interrupted(signum,frame):raise RuntimeError('Validation interrupted; reconcile/rejoin the exact original member')
 signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGHUP,interrupted)
 error=None
 with ctx.lock():
  guard();plan['consumed']=True;plan['started_at']=time.time();atomic(a.plan,plan);checkpoint('preflight-complete')
  try:
   degraded_started=True;run('mdadm',md,'--fail',member);directory,_=guard()
   if (directory/'degraded').read_text().strip()!='1':raise ValueError('Expected exactly one degraded member')
   run('mdadm',md,'--remove',member);guard();checkpoint('member-removed')
   verify_proofs();result['degraded_read_hashes_match']=True
   file=proof_guard(plan['proofs'][0]).parent/('degraded-'+secrets.token_hex(8)+'.bin');seed=secrets.token_bytes(1024**2);sha=hashlib.sha256()
   with file.open('xb') as out:
    for _ in range(16):out.write(seed);sha.update(seed)
    out.flush();os.fsync(out.fileno())
   new_proof={'path':str(file),'sha256':sha.hexdigest(),'inode':file.stat().st_ino,'device':file.stat().st_dev,'bytes':16777216};result['new_proof']=new_proof
   if direct(file)!=new_proof['sha256']:raise ValueError('Degraded write direct-read mismatch')
   result['degraded_write_hash_matches']=True;checkpoint('degraded-io-verified')
  except Exception as e:error=str(e);result['test_error']=error
  finally:
   if degraded_started:
    try:result['rejoin_method']=rejoin();checkpoint('member-rejoin-requested')
    except Exception as e:result['rejoin_error']=str(e);checkpoint('NEEDS-RECONCILIATION');raise
 # Do not hold the NAS operations lock for a possibly lengthy rebuild.
 deadline=time.monotonic()+24*3600;last=0
 while time.monotonic()<deadline:
  directory,members=guard();degraded=int((directory/'degraded').read_text());sync=(directory/'sync_action').read_text().strip()
  if degraded==0 and sync=='idle' and members==expected:break
  if time.monotonic()-last>15:
   result['recovery_progress']={'degraded':degraded,'action':sync,'completed':(directory/'sync_completed').read_text().strip()};checkpoint('recovering');last=time.monotonic()
  time.sleep(1)
 else:checkpoint('recovery-still-pending');raise ValueError('Recovery did not finish within the observation window')
 verify_proofs()
 if new_proof:
  file=Path(new_proof['path']);s=file.stat()
  if file.is_symlink() or s.st_ino!=new_proof['inode'] or s.st_dev!=new_proof['device'] or direct(file)!=new_proof['sha256']:raise ValueError('Post-recovery new proof mismatch')
 result.update(final_degraded=0,final_sync_action='idle',all_proof_hashes_match=True,elapsed_seconds=time.time()-result['started_at'],full_replacement_rebuild_accepted=False,physical_hot_unplug_accepted=False)
 checkpoint('PASSED' if error is None else 'RECOVERED-WITH-TEST-ERROR')
 if error:raise ValueError(error)
 print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
