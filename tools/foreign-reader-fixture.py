#!/usr/bin/env python3
"""Read-only driver/session test on an explicitly owned loop image, never USB."""
import argparse,base64,hashlib,json,os,secrets,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from freeqnap.nas.common import Context
from freeqnap.nas.foreign import Foreign
from freeqnap.nas.storage import walk
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--confirm-loop-fixture',action='store_true',required=True);p.add_argument('--image',type=Path,required=True);p.add_argument('--format',choices=['apfs','bitlk'],required=True);p.add_argument('--password-file',type=Path,required=True);p.add_argument('--expected-sha256');p.add_argument('--crypto-only',action='store_true',help='Check an official BitLocker crypto vector without claiming it contains a mountable filesystem');a=p.parse_args()
if os.geteuid()!=0 or not a.image.resolve().is_relative_to('/var/lib/freeqnap-validation') or a.image.stat().st_uid!=0 or a.image.parent.stat().st_mode&0o077:raise SystemExit('Only root-owned private validation images are permitted')
root=a.image.parent;password=a.password_file.read_text().strip();loop=None;active=None;ctx=Context(root/('state-'+secrets.token_hex(4)))
def run(*args):
 r=subprocess.run(args,capture_output=True,timeout=120)
 if r.returncode:raise RuntimeError(args[0]+' failed: '+r.stderr.decode()[-300:])
 return r.stdout.decode().strip()
def owned():
 rows=json.loads(run('losetup','--json','--list','--output','NAME,BACK-FILE,RO',loop))['loopdevices'];assert len(rows)==1 and Path(rows[0]['back-file']).resolve()==a.image.resolve() and rows[0]['ro']
try:
 loop=run('losetup','--find','--show','--read-only','--partscan',str(a.image));owned();run('udevadm','settle','--timeout=15');tree=json.loads(run('lsblk','-J','-b','--tree','-o','PATH,TYPE,SIZE,UUID,PARTUUID,FSTYPE',loop))['blockdevices'][0];items=[r for r in walk(tree) if r.get('fstype')==('apfs' if a.format=='apfs' else 'BitLocker')];assert len(items)==1;item=items[0];row={'id':'a'*32,'disk':tree,'usb':{'id':'a'*32,'identity':{'fixture':True},'bytes':int(tree['size']),'disk_sequence':'owned-loop'}}
 class External:
  def select(self,ident):owned();return row
 class Fixture(Foreign):
  def source(self,request):owned();assert request['source']==item['path'];return row,item
 f=Fixture(ctx,External())
 if a.crypto_only:
  if a.format!='bitlk' or not a.expected_sha256:raise ValueError('Crypto-only requires a BitLocker known-hash fixture')
  mapping='fq-vector-'+secrets.token_hex(8)
  try:
   bad=subprocess.run(['cryptsetup','open','--type','bitlk','--readonly','--tries','1','--test-passphrase',loop],input=('wrong-'+secrets.token_hex(8)+'\n').encode(),capture_output=True,timeout=120);assert bad.returncode!=0
   good=subprocess.run(['cryptsetup','open','--type','bitlk','--readonly','--tries','1',loop,mapping],input=(password+'\n').encode(),capture_output=True,timeout=120);assert good.returncode==0
   assert run('blockdev','--getro','/dev/mapper/'+mapping)=='1';digest=hashlib.sha256()
   with open('/dev/mapper/'+mapping,'rb') as data:
    while chunk:=data.read(1024*1024):digest.update(chunk)
   assert digest.hexdigest()==a.expected_sha256
   print(json.dumps({'format':'bitlk','official_decrypted_hash_verified':True,'wrong_password_refused':True,'read_only_mapping':True,'filesystem_browsing_accepted':False,'physical_disks_written':False},indent=2))
  finally:
   if Path('/dev/mapper/'+mapping).exists():run('cryptsetup','close',mapping)
  raise SystemExit(0)
 def review(password):
  plan=f.plan({'id':'a'*32,'source':item['path']});return {'plan_id':plan['id'],'digest':plan['digest'],'confirmation':plan['confirmation'],'secret':{'password':password}}
 try:f.unlock(review('wrong-'+secrets.token_hex(10)))
 except ValueError:pass
 else:raise RuntimeError('Wrong password was accepted')
 opened=f.unlock(review(password));active=f.record(opened['session']);f.validate(active);listing=f.files({'session':active['id'],'path':''});result={'format':a.format,'wrong_password_refused':True,'unlocked_read_only':True,'root_entries':len(listing['entries']),'physical_disks_written':False}
 if a.format=='apfs':
  assert base64.b64decode(f.files({'session':active['id'],'path':'proof.txt'},True)['data_base64'])==b'FreeQNAP software-encrypted APFS fixture'
  result['file_content_verified']=True
 elif a.expected_sha256:
  digest=hashlib.sha256()
  with open('/dev/mapper/'+active['mapping'],'rb') as data:
   while chunk:=data.read(1024*1024):digest.update(chunk)
  assert digest.hexdigest()==a.expected_sha256;result['complete_decrypted_hash_verified']=True
 try:(Path(active['mountpoint'])/'denied.txt').write_text('must fail')
 except OSError:result['writes_denied']=True
 else:raise RuntimeError('Read-only session permitted a write')
 f.lock({'session':active['id']});active=None;result['locked_cleanly']=True
 for path in [ctx.state.database,*ctx.directory.rglob('*.json')]:assert password.encode() not in path.read_bytes()
 result['secret_not_persisted']=True;print(json.dumps(result,indent=2))
finally:
 if active:
  try:f.lock({'session':active['id']})
  except Exception:pass
 if loop:owned();run('losetup','--detach',loop)
