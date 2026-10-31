#!/usr/bin/env python3
"""Explicit disposable loop-only encryption/read-only tests; no physical disks."""
import argparse,base64,json,os,secrets,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from freeqnap.nas.common import Context
from freeqnap.nas.foreign import Foreign
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--confirm-loop-fixture',action='store_true',required=True);a=p.parse_args()
if os.geteuid()!=0 or sys.platform!='linux':raise SystemExit('Requires root on Linux')
ident=secrets.token_hex(4);root=Path('/var/lib/freeqnap-validation')/('foreign-'+ident);root.mkdir(mode=0o700,parents=True);result={'physical_disks_written':False,'cases':[]}
def run(*args,data=None,timeout=120):
 r=subprocess.run(args,input=data,capture_output=True,timeout=timeout)
 if r.returncode:
  if args[0] in ('mount','umount','losetup'):raise RuntimeError(args[0]+' failed: '+r.stderr.decode()[-600:])
  raise RuntimeError(Path(args[0]).name+' failed (no secret diagnostics returned)')
 return r.stdout.decode().strip()
def owned(loop):
 info=json.loads(run('losetup','--json','--list','--output','NAME,BACK-FILE',loop))['loopdevices']
 if len(info)!=1 or Path(info[0]['back-file']).parent!=root:raise RuntimeError('Loop ownership changed')
for version,filesystem in [('luks1','ext4'),('luks2','ext4'),('luks2','ntfs')]:
 image=root/(version+'-'+filesystem+'.img');image.touch();os.truncate(image,256*1024**2);loop=run('losetup','--find','--show',str(image));mapping='fq-fixture-'+ident;mnt=root/'seed';mnt.mkdir(exist_ok=True);ctx=Context(root/(version+'-'+filesystem+'-state'));active=None;password=secrets.token_hex(20).encode();disk={'path':loop,'fstype':'crypto_LUKS','uuid':'fixture-'+ident,'size':256*1024**2};row={'id':'a'*32,'disk':disk,'usb':{'id':'a'*32}}
 class Fixture(Foreign):
  def source(self,request):owned(loop);return row,disk
  def validate(self,record):
   owned(loop);rows=json.loads(run('findmnt','-J','-M',record['mountpoint'],'-o','TARGET,SOURCE,FSROOT,OPTIONS'))['filesystems'];assert len(rows)==1 and {'ro','nodev','nosuid','noexec'}<=set(rows[0]['options'].split(','));assert run('blockdev','--getro','/dev/mapper/'+record['mapping'])=='1';return record
 f=Fixture(ctx,None)
 try:
  owned(loop);args=['cryptsetup','luksFormat','--type',version,'--batch-mode','--key-file','-']
  if version=='luks2':args+=['--pbkdf','pbkdf2','--iter-time','100']
  run(*args,loop,data=password);run('cryptsetup','open','--key-file','-',loop,mapping,data=password)
  device='/dev/mapper/'+mapping
  run('mkfs.ext4','-q','-F',device) if filesystem=='ext4' else run('mkfs.ntfs','-Q','-F',device)
  if filesystem=='ext4':
   run('mount','-t','ext4',device,str(mnt));(mnt/'proof.txt').write_bytes(b'FreeQNAP encrypted fixture');run('umount',str(mnt))
  else:
   seed=root/'ntfs-seed';seed.write_bytes(b'FreeQNAP encrypted fixture');run('ntfscp',device,str(seed),'/proof.txt')
  run('cryptsetup','close',mapping)
  plan=f.plan({'id':'a'*32,'source':loop});review={'plan_id':plan['id'],'digest':plan['digest'],'confirmation':plan['confirmation'],'secret':{'password':password.decode()}};opened=f.unlock(review);active=f.record(opened['session']);data=f.files({'session':opened['session'],'path':'proof.txt'},True);assert base64.b64decode(data['data_base64'])==b'FreeQNAP encrypted fixture'
  try:(Path(active['mountpoint'])/'denied.txt').write_text('must fail')
  except OSError:pass
  else:raise RuntimeError('Read-only mount permitted writes')
  f.lock({'session':opened['session']});assert not Path('/dev/mapper/'+active['mapping']).exists();active=None
  assert password not in ctx.state.database.read_bytes();result['cases'].append({'encryption':version,'filesystem':filesystem,'unlock_read_lock':True,'writes_denied':True,'secret_not_persisted':True})
 finally:
  if active:
   try:f.lock({'session':active['id']})
   except Exception:pass
  if os.path.ismount(mnt):run('umount',str(mnt))
  if Path('/dev/mapper/'+mapping).exists():run('cryptsetup','close',mapping)
  owned(loop);run('losetup','--detach',loop)
print(json.dumps(result,indent=2))
