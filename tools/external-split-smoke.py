#!/usr/bin/env python3
"""Split external-volume workflow on an explicitly owned loop fixture, not a physical USB acceptance.

Injects synthetic enclosure identity only into this harness; real GPT/LUKS/ext4,
mount, read-only import/unlock and safe-unmount operations run on one owned image.
"""
import argparse,hashlib,json,os,secrets,subprocess,sys,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from freeqnap.nas.common import Context,canonical
from freeqnap.nas.external import External
from freeqnap.nas.storage import Storage

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--confirm-loop-fixture',action='store_true');a=p.parse_args()
if not a.confirm_loop_fixture or os.geteuid()!=0:raise SystemExit('Explicit local-root loop fixture confirmation required')
token=secrets.token_hex(4);root=Path('/var/lib/freeqnap-validation')/('usb-'+token);root.mkdir(mode=0o700,parents=True)
image=root/'owned.img';image.touch(mode=0o600)
with image.open('r+b') as f:f.truncate(3*1024**3)
loop=None;names=['fqusb'+token,'fqusb-ro'+token];targets=[Path('/srv/freeqnap/volumes')/n for n in names];flush_calls=[]
def run(*args,data=None,timeout=120,**kwargs):
 if any(str(v).startswith('/dev/sd') for v in args):raise ValueError('Physical disk reference refused by loop fixture')
 if args[0]=='sg_sync':flush_calls.append(args);return ''
 result=subprocess.run(args,input=data,capture_output=True,timeout=timeout,**kwargs)
 if result.returncode:
  (root/'last-error.json').write_text(json.dumps({'command':args,'stderr':result.stderr.decode(errors='replace')[-3000:]},indent=2));raise ValueError(Path(args[0]).name+' failed in private fixture')
 return result.stdout.decode()
def safe_loop():
 rows=json.loads(run('losetup','--list','--json','--output','NAME,BACK-FILE',loop))['loopdevices']
 if len(rows)!=1 or Path(rows[0]['back-file'])!=image:raise ValueError('Loop backing identity changed')
class Fixture(Context):
 def volume(self,ident):
  pool=self.config()['pools'][ident];target=Path(pool['mountpoint'])
  rows=json.loads(run('findmnt','-J','-M',str(target),'-o','TARGET,SOURCE,UUID,FSTYPE,FSROOT,OPTIONS'))['filesystems']
  rows=list({json.dumps(row,sort_keys=True):row for row in rows}.values())
  if len(rows)!=1 or rows[0]['uuid']!=pool['filesystem_uuid'] or rows[0]['fstype']!='ext4' or rows[0]['fsroot']!='/':raise ValueError('Fixture filesystem identity mismatch')
  return pool,target
try:
 loop=run('losetup','--find','--show','--partscan',str(image)).strip();safe_loop();context=Fixture(root/'state',runner=run)
 identity={'vendor_id':'ffff','product_id':'0001','serial':'SPLIT-LOOP-ONLY','interface':'00','channel':'0','target':'0','lun':'0'}
 usb={'identity':identity,'id':hashlib.sha256(canonical(identity)).hexdigest()[:32],'enclosure_id':'e'*32,'stable':True,'bytes':image.stat().st_size,'driver':'loop-fixture','product':'Synthetic enclosure, not hardware acceptance','speed_mbps':'not-tested'}
 def collect():
  safe_loop();disk=json.loads(run('lsblk','-J','-b','-o','NAME,PATH,TYPE,SIZE,MODEL,SERIAL,WWN,FSTYPE,UUID,PARTUUID,MOUNTPOINTS,RO',loop))['blockdevices'][0];disk['type']='disk'
  return {'disks':[disk],'root':{'uuid':'ROOT-NOT-A-CANDIDATE'},'sampled_at':time.time(),'errors':[]}
 external=External(context,collector=collect,probe=lambda dev:dict(usb),path_validator=lambda dev:dev==loop)
 group='fqsplit'+token;names=[group+'-1',group+'-2'];targets=[Path('/srv/freeqnap/volumes')/n for n in names]
 plan=external.create_plan({'id':usb['id'],'name':group,'encrypted':False,'volume_count':2})
 result=external.create({'plan_id':plan['id'],'digest':plan['digest'],'confirmation':plan['confirmation']})
 assert result['volumes']==names
 validation=run('sgdisk','--verify',loop);assert 'No problems found' in validation,validation
 hashes=[]
 for target,n in zip(targets,names):
  payload=os.urandom(1024**2);(target/'proof.bin').write_bytes(payload);run('sync','-f',str(target))
  hashes.append(hashlib.sha256(payload).hexdigest());run('systemd-mount','--umount',str(target))
  pool=context.config()['pools'][n];pool['read_only']=True;context.save({**context.config(),'pools':{**context.config()['pools'],n:pool}})
  Storage(context).mount(pool);assert hashlib.sha256((target/'proof.bin').read_bytes()).hexdigest()==hashes[-1]
  try:(target/'must-not-write').write_bytes(b'no')
  except OSError:pass
  else:raise AssertionError('Read-only split volume accepted write')
 original=json.loads((context.directory/'external-preformat'/plan['id']/'manifest.json').read_text());assert len(original['regions'])==2
 eject=external.eject_plan({'id':usb['id']});external.eject({'plan_id':eject['id'],'digest':eject['digest'],'confirmation':eject['confirmation']},lambda pools:None)
 assert all(not context.config()['pools'][n].get('encrypted') for n in names);assert flush_calls
 print(json.dumps({'two_native_ext4_volumes':True,'both_gpt_copies_crc_valid':True,'direct_metadata_backups':True,'both_remount_hashes_match':True,'both_read_only_writes_refused':True,'enclosure_eject':True,'physical_usb_acceptance':False}),flush=True)
finally:
 for target,n in zip(targets,names):
  if subprocess.run(['findmnt','-M',str(target)],capture_output=True).returncode==0:run('systemd-mount','--umount',str(target))
 if loop:safe_loop();run('losetup','--detach',loop)
 image.unlink(missing_ok=True)
 for target in targets:
  if target.exists():target.rmdir()
