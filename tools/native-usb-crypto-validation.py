#!/usr/bin/env python3
"""Fresh-plan, owner-approved disposable USB encryption campaign.

Never selects by /dev name alone. The private plan pins the USB descriptor,
serial/capacity/attachment sequence, stable link, existing registration and both
healthy internal arrays. Default is preflight only. A consumed or failed campaign
must be reconciled, never blindly retried. Temporary secrets are not logged.
"""
import argparse,base64,fcntl,hashlib,json,mmap,os,secrets,stat,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from freeqnap.nas.common import Context,canonical
from freeqnap.nas.external import External
from freeqnap.nas.storage import Storage
from freeqnap.nas.fileops import FileManager
from freeqnap.nas.broker import Client
from freeqnap.nas.crypto_profiles import profile
from freeqnap.state import atomic

CONFIRM='VALIDATE DISPOSABLE USB ENCRYPTION'
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan',required=True,type=Path);parser.add_argument('--confirmation',required=True);parser.add_argument('--apply',action='store_true');a=parser.parse_args()
 if sys.platform!='linux' or os.geteuid()!=0 or Path('/proc/device-tree/compatible').read_bytes().split(b'\0')[0]!=b'qnap,ts-431xeu':raise ValueError('Root on the supported NAS required')
 os.umask(0o077);s=a.plan.stat()
 if a.plan.is_symlink() or s.st_uid!=0 or s.st_mode&0o077:raise ValueError('Private root-owned plan required')
 plan=json.loads(a.plan.read_text());digest=hashlib.sha256(canonical({k:v for k,v in plan.items() if k!='digest'})).hexdigest()
 if digest!=plan['digest'] or a.confirmation!=CONFIRM or not plan['owner_approved'] or plan.get('consumed') or not 0<=time.time()-plan['created_at']<900:raise ValueError('Fresh approved unconsumed plan required')
 if plan['profiles']!=['aes256-xts','aes128-xts'] or plan['cycles']!=4 or plan['proof_bytes']!=8*1024**2:raise ValueError('Unexpected test scope')
 ctx=Context();external=External(ctx);storage=Storage(ctx);files=FileManager(ctx);root=a.plan.parent;old_name=plan['old_pool']['name'] if plan['old_pool'] else None;result={'stage':'preflight','profiles':[],'internal_arrays_changed':False,'tr004_changed':False};keyfile=None
 def checkpoint(stage):result.update(stage=stage,updated_at=time.time());atomic(root/'result.json',result)
 def guard():
  row=external.select(plan['usb']['id'])
  for k in ('identity','bytes','disk_sequence','enclosure_id'):
   if row['usb'][k]!=plan['usb'][k]:raise ValueError('Approved USB identity/attachment changed')
  if {k:row['disk'].get(k) for k in ('path','serial','size')}!=plan['disk']:raise ValueError('Approved USB disk identity changed')
  if external.stable_path(row)!=plan['stable_path'] or Path(plan['stable_path']).resolve()!=Path(plan['disk']['path']):raise ValueError('Stable USB link changed')
  for md,expected in plan['arrays'].items():
   d=Path('/sys/class/block')/md
   if (d/'md/uuid').read_text().strip()!=expected['uuid'] or {p.name for p in (d/'slaves').iterdir()}!=set(expected['members']):raise ValueError('Internal array identity/membership changed')
   if (d/'md/degraded').read_text().strip()!='0' or (d/'md/sync_action').read_text().strip()!='idle':raise ValueError('Healthy idle internal arrays required')
  return row
 def reviewed(p):return {'plan_id':p['id'],'digest':p['digest'],'confirmation':p['confirmation']}
 def dependencies(names):
  names=[n for n in names if n is not None]
  c=ctx.config()
  if any(v.get('pool') in names for key in ('shares','libraries','repositories') for v in c.get(key,{}).values()):raise ValueError('USB has configured consumers; no automatic service disruption')
  if (ctx.state.setting('downloads_settings') or {}).get('pool') in names:raise ValueError('Download consumer found')
 def unchanged_other_pools():
  actual={k:v for k,v in ctx.config()['pools'].items() if k not in plan['test_names'] and k!=old_name}
  expected={k:v for k,v in plan['config']['pools'].items() if k!=old_name}
  if actual!=expected:raise ValueError('An unrelated pool configuration changed')
  for key,value in plan['config'].items():
   if key!='pools' and ctx.config().get(key)!=value:raise ValueError('An unrelated NAS configuration changed')
 def unlock(ident,credential):
  guard();start=time.monotonic();storage.unlock({'pool':ident,'secret':credential});pool,mount=ctx.volume(ident)
  if pool['luks_uuid']!=ctx.run('cryptsetup','luksUUID',external.resolve(pool)).strip():raise ValueError('Unlock identity changed')
  return mount,round(time.monotonic()-start,3)
 def lock(ident):
  guard();storage.lock({'pool':ident},lambda:dependencies([ident]))
  if Path('/dev/mapper/freeqnap-'+ident).exists():raise ValueError('Mapper remained after locking')
 def direct(path,pool,expected):
  _,mount=ctx.volume(pool);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_DIRECT)
  try:
   info=os.fstat(fd)
   if not stat.S_ISREG(info.st_mode) or info.st_dev!=mount.stat().st_dev or info.st_size!=plan['proof_bytes'] or info.st_ino!=expected['inode']:raise ValueError('Proof identity changed')
   h=hashlib.sha256()
   with mmap.mmap(-1,1024**2) as b:
    for offset in range(0,plan['proof_bytes'],1024**2):
     if os.preadv(fd,[b],offset)!=1024**2:raise ValueError('Short direct USB read')
     h.update(b)
   if h.hexdigest()!=expected['sha256']:raise ValueError('USB proof checksum mismatch')
  finally:os.close(fd)
 def forget(ident):
  p=external.forget_plan({'pool':ident});external.forget(reviewed(p))
 def reject(ident,credential):
  try:storage.unlock({'pool':ident,'secret':credential})
  except ValueError as error:
   if 'cryptsetup failed (exit 2)' not in str(error):raise
  else:raise ValueError('Wrong credential was accepted')
  if Path('/dev/mapper/freeqnap-'+ident).exists():raise ValueError('Rejected unlock left a mapper')
 def upload(ident,name,data):
  start=time.monotonic();r=files.upload_begin({'share':'pool:'+ident,'path':name,'bytes':len(data)});chain='0'*64
  for offset in range(0,len(data),r['chunk_bytes']):
   chunk=data[offset:offset+r['chunk_bytes']];sha=hashlib.sha256(chunk).hexdigest();files.upload_chunk({'upload_id':r['upload_id'],'offset':offset,'data_base64':base64.b64encode(chunk).decode(),'sha256':sha});chain=hashlib.sha256((chain+sha).encode()).hexdigest()
  files.upload_finish({'upload_id':r['upload_id'],'hash_chain':chain});return round(time.monotonic()-start,3)
 lockfile=(root/'campaign.lock').open('a');fcntl.flock(lockfile,fcntl.LOCK_EX|fcntl.LOCK_NB)
 guard();dependencies([old_name]);unchanged_other_pools()
 if (ctx.config()['pools'].get(old_name) if old_name else None)!=plan['old_pool']:raise ValueError('Original USB registration changed')
 if any(j['status'] in ('queued','running') for j in ctx.state.jobs()):raise ValueError('Active NAS job found')
 if not a.apply:print(json.dumps({'preflight_passed':True,'disk_writes':False}));return
 plan['consumed']=True;plan['started_at']=time.time();atomic(a.plan,plan);checkpoint('approved-plan-consumed')
 try:
  if old_name:
   p=external.eject_plan({'id':plan['usb']['id']});external.eject(reviewed(p),dependencies);forget(old_name)
  else:external.idle(guard())
  checkpoint('old-usb-registration-removed')
  for index,method in enumerate(plan['profiles']):
   ident=plan['test_names'][index];guard();password=secrets.token_urlsafe(24);key=secrets.token_bytes(64);keyfile=Path('/run')/('freeqnap-usb-test-'+secrets.token_hex(12)+'.key')
   fd=os.open(keyfile,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
   with os.fdopen(fd,'wb') as stream:stream.write(key)
   password_secret={'password':password};key_secret={'key_base64':base64.b64encode(keyfile.read_bytes()).decode()};initial=password_secret if index==0 else key_secret;alternate=key_secret if index==0 else password_secret
   checkpoint(method+':creating');p=external.create_plan({'id':plan['usb']['id'],'name':ident,'encrypted':True,'encryption_profile':method});atomic(root/(method+'-create-plan.json'),p)
   if p['body']['disk_identity']['usb']['identity']!=plan['usb']['identity']:raise ValueError('Reviewed format identity mismatch')
   external.create({**reviewed(p),'secret':initial});pool,mount=ctx.volume(ident);partition=external.resolve(pool)
   metadata=json.loads(ctx.run('cryptsetup','luksDump','--dump-json-metadata',partition));expected_profile=profile(method)
   if metadata['segments']['0']['encryption']!=expected_profile['cipher'] or any(v['key_size']*8!=expected_profile['key_bits'] or v['kdf']['type']!='argon2id' for v in metadata['keyslots'].values()):raise ValueError('Created encryption profile differs from review')
   p=storage.key_plan({'pool':ident});storage.add_key({**reviewed(p),'existing_secret':initial,'new_secret':alternate})
   files.mkdir({'share':'pool:'+ident,'path':'','name':'Café_测试'});data=secrets.token_bytes(plan['proof_bytes']);sha=hashlib.sha256(data).hexdigest();relative='Café_测试/proof.bin';seconds=upload(ident,relative,data);proof=mount/relative;expected={'sha256':sha,'inode':proof.stat().st_ino};direct(proof,ident,expected)
   report={'profile':method,'created_with':'password' if index==0 else 'key-file','alternate_secret_added':True,'key_file_bytes':64,'proof_bytes':len(data),'upload_seconds':seconds,'cycles':[]};result['profiles'].append(report);checkpoint(method+':proof-written')
   # An open descriptor must prevent normal unmount; no force/lazy fallback.
   held=os.open(proof,os.O_RDONLY)
   try:
    try:storage.lock({'pool':ident},lambda:dependencies([ident]))
    except ValueError:pass
    else:raise ValueError('Busy filesystem unexpectedly unmounted')
    ctx.volume(ident);report['busy_unmount_refused']=True
   finally:os.close(held)
   lock(ident);reject(ident,{'password':secrets.token_urlsafe(24)});reject(ident,{'key_base64':base64.b64encode(secrets.token_bytes(64)).decode()});report['wrong_password_and_key_rejected']=True
   for cycle in range(plan['cycles']):
    credential=password_secret if cycle%2==0 else key_secret;mount,elapsed=unlock(ident,credential);proof=mount/relative;direct(proof,ident,expected)
    marker=mount/('cycle-'+str(cycle)+'.txt');fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(b'cycle write verified\n');stream.flush();os.fsync(stream.fileno())
    report['cycles'].append({'credential':'password' if cycle%2==0 else 'key-file','unlock_seconds':elapsed,'direct_hash_match':True});lock(ident);checkpoint(method+':cycle-'+str(cycle+1))
   # Import/unlock read-only mode must reject writes, then be lockable normally.
   cfg=ctx.config();cfg['pools'][ident]['read_only']=True;ctx.save(cfg);mount,_=unlock(ident,password_secret);direct(mount/relative,ident,expected)
   try:(mount/'must-not-write').write_bytes(b'no')
   except OSError as error:
    if error.errno!=30:raise
   else:raise ValueError('Read-only mount accepted a write')
   report['read_only_write_refused']=True;lock(ident);cfg=ctx.config();cfg['pools'][ident]['read_only']=False;ctx.save(cfg)
   # Final password/key reopen verifies all cycle writes survived another mount.
   mount,_=unlock(ident,key_secret)
   for cycle in range(plan['cycles']):
    if (mount/('cycle-'+str(cycle)+'.txt')).read_bytes()!=b'cycle write verified\n':raise ValueError('Cycle write did not persist')
   direct(mount/relative,ident,expected);lock(ident);forget(ident);keyfile.unlink();keyfile=None;password_secret=key_secret=initial=alternate=password=key=data=None;report['all_cycle_writes_survived']=True;checkpoint(method+':passed-and-locked')
  # Both cycles are accepted; erase only the approved disposable USB layout.
  row=guard();external.idle(row);partition=plan['disk']['path']+'1'
  if Path(partition).exists():guard();ctx.run('wipefs','--all',partition)
  guard();ctx.run('wipefs','--all',plan['stable_path']);guard();ctx.run('sgdisk','--zap-all',plan['stable_path']);ctx.run('blockdev','--rereadpt',plan['disk']['path']);ctx.run('udevadm','settle','--timeout=15')
  guard();result['final_flush']=external.flush(plan['disk']['path']);unchanged_other_pools();fresh=external.select(plan['usb']['id']);external.idle(fresh)
  if fresh['disk'].get('children') or json.loads(ctx.run('wipefs','--json','--no-act',plan['stable_path']))['signatures']:raise ValueError('Test layout cleanup not complete')
  result.update(temporary_secrets_deleted=True,usb_left_blank_and_unmounted=True,unrelated_configuration_unchanged=True,elapsed_seconds=round(time.time()-plan['started_at'],3));checkpoint('PASSED');print(json.dumps(result,indent=2))
 except Exception as error:
  result['error_type']=type(error).__name__;checkpoint('FAILED; reconcile private evidence; do not repeat format');raise
 finally:
  if keyfile is not None:keyfile.unlink(missing_ok=True)
if __name__=='__main__':main()
