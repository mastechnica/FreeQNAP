#!/usr/bin/env python3
"""External-volume workflow on an explicitly owned loop fixture, not a physical USB acceptance.

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
with image.open('r+b') as f:f.truncate(1536*1024**2)
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
 identity={'vendor_id':'ffff','product_id':'0001','serial':'SYNTHETIC-LOOP-ONLY','interface':'00','channel':'0','target':'0','lun':'0'}
 usb={'identity':identity,'id':hashlib.sha256(canonical(identity)).hexdigest()[:32],'enclosure_id':'e'*32,'stable':True,'bytes':image.stat().st_size,'driver':'loop-fixture','product':'Synthetic enclosure, not hardware acceptance','speed_mbps':'not-tested'}
 def collect():
  safe_loop();disk=json.loads(run('lsblk','-J','-b','-o','NAME,PATH,TYPE,SIZE,MODEL,SERIAL,WWN,FSTYPE,UUID,PARTUUID,MOUNTPOINTS,RO',loop))['blockdevices'][0]
  disk['type']='disk'
  return {'disks':[disk],'root':{'uuid':'ROOT-NOT-A-CANDIDATE'},'sampled_at':time.time(),'errors':[]}
 external=External(context,collector=collect,probe=lambda dev:dict(usb),path_validator=lambda dev:dev==loop)
 plan=external.create_plan({'id':usb['id'],'name':names[0],'encrypted':True});password=secrets.token_urlsafe(32)
 external.create({'plan_id':plan['id'],'digest':plan['digest'],'confirmation':plan['confirmation'],'secret':{'password':password}})
 payload=os.urandom(256*1024);(targets[0]/'proof.bin').write_bytes(payload)
 pool=context.config()['pools'][names[0]];luks_uuid=pool['luks_uuid'];fs_uuid=pool['filesystem_uuid']
 run('systemd-mount','--umount',str(targets[0]));run('cryptsetup','close','freeqnap-'+names[0])
 cfg=context.config();cfg['pools']={};context.save(cfg)
 plan=external.import_plan({'id':usb['id'],'name':names[1],'uuid':luks_uuid})
 imported=external.import_volume({'plan_id':plan['id'],'digest':plan['digest'],'confirmation':plan['confirmation']})
 assert imported['read_only'] and not imported['data_formatted']
 with patch('freeqnap.nas.external.External',return_value=external):Storage(context).unlock({'pool':names[1],'secret':{'password':password}})
 assert (targets[1]/'proof.bin').read_bytes()==payload;assert context.config()['pools'][names[1]]['filesystem_uuid']==fs_uuid
 readonly=False
 try:(targets[1]/'must-not-write').write_bytes(b'not allowed')
 except OSError:readonly=True
 assert readonly,'imported read-only volume accepted a write'
 plan=external.eject_plan({'id':usb['id']});result=external.eject({'plan_id':plan['id'],'digest':plan['digest'],'confirmation':plan['confirmation']},lambda pools:None)
 assert result['safe_to_unplug'];assert not Path('/dev/mapper/freeqnap-'+names[1]).exists();assert flush_calls
 output={'real_gpt_luks2_ext4_creation_on_owned_loop':True,'read_only_import_unlock_preserved_data':True,'read_only_write_refused':True,'external_safe_unmount_closed_crypto':True,'physical_disks_written':False,'physical_usb_bridge_and_flush_tested':False}
 (root/'result.json').write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output,indent=2),flush=True)
finally:
 for target,n in zip(targets,names):
  if subprocess.run(['findmnt','-M',str(target)],capture_output=True).returncode==0:run('systemd-mount','--umount',str(target))
  if Path('/dev/mapper/freeqnap-'+n).exists():run('cryptsetup','close','freeqnap-'+n)
 if loop:safe_loop();run('losetup','--detach',loop)
 image.unlink(missing_ok=True)
 for target in targets:
  if target.exists():target.rmdir()
