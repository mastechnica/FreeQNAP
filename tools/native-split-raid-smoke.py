#!/usr/bin/env python3
"""Explicit owned-loop RAID5/GPT/two-ext4 validation; no physical data disk writes."""
import argparse,hashlib,json,os,secrets,shutil,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from freeqnap.nas.common import Context
from freeqnap.nas.storage import Storage,identity
from freeqnap.nas import gpt
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--confirm-loop-fixture',action='store_true',required=True);p.parse_args()
if os.geteuid()!=0 or sys.platform!='linux':raise SystemExit('Explicit disposable Linux root fixture required')
ident='fqsplit-'+secrets.token_hex(4);root=Path('/var/lib/freeqnap-validation')/ident;root.mkdir(mode=0o700,parents=True);loops=[];md='/dev/md/'+ident;created=False
if shutil.disk_usage(root).free<2*1024**3:raise SystemExit('At least 2 GiB free space required')
def run(*args,data=None,timeout=120,**kw):
 p=subprocess.run(args,input=data,capture_output=True,timeout=timeout)
 if p.returncode:raise ValueError(Path(args[0]).name+' failed in disposable split-array test')
 return p.stdout.decode()
def safe(device):
 rows=json.loads(run('losetup','--json','--list','--output','NAME,BACK-FILE',device))['loopdevices']
 if len(rows)!=1 or Path(rows[0]['back-file']).parent!=root:raise ValueError('Fixture loop identity changed')
def guard_loops():
 for loop in loops:safe(loop)
ctx=Context(root/'state',runner=run);store=None;volumes=[];report={}
try:
 for n in range(4):
  image=root/('member-'+str(n)+'.img')
  with image.open('xb') as stream:stream.truncate(1280*1024**2)
  loop=run('losetup','--find','--show',str(image)).strip();loops.append(loop);safe(loop)
 guard_loops();run('mdadm','--create',md,'--metadata=1.2','--level=5','--raid-devices=4','--size=1048576','--data-offset=128M','--bitmap=internal','--name='+ident,'--homehost=freeqnap','--run',*loops);created=True
 detail=dict(line.split('=',1) for line in run('mdadm','--detail','--export',md).splitlines() if '=' in line)
 diskrows=[{'path':loop,'serial':'fixture-'+str(n),'wwn':'fixture-'+str(n),'size':1280*1024**2,'model':'owned loop'} for n,loop in enumerate(loops)]
 def collector():
  guard_loops();return {'errors':[],'root':{'uuid':'fixture-root'},'disks':diskrows}
 store=Storage(ctx,collector,lambda dev:dev in loops)
 layout=gpt.layout(3*1024**3,512,[ident+'-1',ident+'-2']);volumes=layout['volumes'];body={'name':ident,'root_uuid':'fixture-root','layout':layout,'encrypted':False,'level':'raid5'}
 regions=[{'disk':identity(row),'partition':row['path'],'number':1} for row in diskrows]
 operation=ctx.operation('owned-loop-split',{});result=store.create_split(body,regions,md,detail,operation,lambda _:None,None)
 payload=hashlib.sha256(b'FreeQNAP owned split-array fixture').digest()*32768;checks={}
 for v in volumes:
  pool,target=ctx.volume(v['name']);file=target/'known-file.bin'
  with file.open('xb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
  checks[v['name']]=hashlib.sha256(file.read_bytes()).hexdigest()
  run('systemd-mount','--umount',str(target));pool['block_device']=store.data_device(pool);store.mount(pool);assert hashlib.sha256(file.read_bytes()).hexdigest()==checks[v['name']]
 assert len(set(p['md_uuid'] for p in ctx.config()['pools'].values()))==1
 assert len(set(p['partition_uuid'] for p in ctx.config()['pools'].values()))==2
 # New Context and exact recorded array lookup simulate data volume startup resolution.
 fresh=Storage(Context(root/'state',runner=run),collector,lambda dev:dev in loops)
 for pool in fresh.ctx.config()['pools'].values():assert run('blkid','-s','PARTUUID','-o','value',fresh.data_device(pool)).strip()==pool['partition_uuid']
 report={'raid5_owned_loop':True,'one_array_two_distinct_gpt_filesystems':True,'both_known_file_hashes_match_after_remount':True,'fresh_context_uuid_resolution':True,'initial_sync_action':store.inspect_array(next(iter(ctx.config()['pools'].values())))['sync_action'],'physical_disks_written':False,'physical_failure_rebuild_accepted':False}
finally:
 if store:
  for pool in ctx.config()['pools'].values():
   target=Path(pool['mountpoint'])
   if target.exists():
    run('systemd-mount','--umount',str(target));target.rmdir()
 if created:guard_loops();run('mdadm','--stop',md)
 for loop in loops:safe(loop);run('losetup','--detach',loop)
 if report:shutil.rmtree(root)
if report:print(json.dumps(report,indent=2))
