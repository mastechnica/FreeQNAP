#!/usr/bin/env python3
"""Attended high-speed fan-step acceptance, with an independent full-speed guard.

Default is read-only preflight. Exact per-unit plan and watching operator required.
Only the stock-supported global levels 6 and 7 are implemented; never stops fans.
"""
import argparse,hashlib,importlib.util,json,os,signal,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from freeqnap.state import atomic
from freeqnap.nas.common import canonical
FULL='/usr/local/sbin/eyeq-mcu-safe-full'
def read_plan(path):
 s=path.lstat()
 if path.is_symlink() or s.st_uid!=0 or s.st_mode&0o077:raise ValueError('Private root-owned plan required')
 p=json.loads(path.read_text())
 if p['digest']!=hashlib.sha256(canonical(p['body'])).hexdigest():raise ValueError('Plan body changed')
 b=p['body']
 if os.geteuid()!=0 or Path('/proc/device-tree/compatible').read_bytes().split(b'\0')[0]!=b'qnap,ts-431xeu' or Path('/etc/freeqnap-install-id').read_text().strip()!=b['install_id']:raise ValueError('Exact installed NAS identity required')
 if b['level']!=6 or b['seconds']!=10 or b['mode'] not in ('step','lost-heartbeat') or b['owner_watching'] is not True:raise ValueError('Unexpected attended test scope')
 return p

def mcu():
 spec=importlib.util.spec_from_file_location('board_hwctl','/usr/local/share/eyeq/eyeq-hwctl.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m.Mcu()
def snapshot():
 with mcu() as c:
  level=c.exchange('@FS',4,b'@F')[2:3].decode();fans=[]
  for i in range(3):
   f=c.exchange('@F'+chr(65+i),7,('@F'+str(i)).encode());fans.append({'channel':i,'rpm':int.from_bytes(f[3:5],'big')*30,'state':f[5]})
 return {'level':int(level),'fans':fans,'cpu_c':int(Path('/sys/class/thermal/thermal_zone0/temp').read_text())/1000}
def full():
 deadline=time.monotonic()+4
 while True:
  r=subprocess.run([FULL],capture_output=True,timeout=8)
  if not r.returncode:return snapshot()
  error=r.stderr.decode(errors='replace').strip()
  # Existing LED/tach readers share this lock. Retry only explicit lock contention.
  if error.startswith('MCU lock:') and time.monotonic()<deadline:
   time.sleep(.05);continue
  raise ValueError('Full-speed helper failed: '+error)
def set_six():
 with mcu() as c:
  c.ack('@F6')
  if c.exchange('@FS',4,b'@F')!=bytes([64,70,54,48]):raise ValueError('High fan-step readback mismatch')
def ticks(pid):return Path('/proc') .joinpath(str(pid),'stat').read_text().rsplit(')',1)[1].split()[19]
def guard(path):
 p=read_plan(path);r=path.parent;state=json.loads((r/'owner.json').read_text());started=time.monotonic();atomic(r/'guard-ready.json',{'at':started});reason=''
 while True:
  try:
   lease=json.loads((r/'lease.json').read_text());now=time.monotonic()
   if lease.get('done'):reason='normal-completion';break
   alive=state['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip() and ticks(state['pid'])==state['start_ticks']
   if not alive or not 0<=lease['expires']-now<=3 or now-started>30:reason='lost-or-invalid-heartbeat';break
  except (OSError,ValueError,KeyError,TypeError):reason='missing-or-invalid-owner';break
  time.sleep(.1)
 detected=time.monotonic()
 if reason!='normal-completion':
  try:
   if state['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip() and ticks(state['pid'])==state['start_ticks']:os.kill(state['pid'],signal.SIGKILL)
  except (OSError,ProcessLookupError):pass
 try:
  v=full();atomic(r/'guard-result.json',{'reason':reason,'full_verified':v['level']==7,'restore_after_detection_seconds':round(time.monotonic()-detected,3),'snapshot':v})
 except Exception as exc:
  atomic(r/'guard-result.json',{'reason':reason,'full_verified':False,'operator_action_required':True,'error':str(exc)});raise

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--guard',action='store_true');parser.add_argument('--apply',action='store_true');a=parser.parse_args();os.umask(0o077)
 if a.guard:guard(a.plan);return
 p=read_plan(a.plan);r=a.plan.parent;b=p['body'];before=snapshot()
 if p.get('consumed') or not p.get('owner_approved') or not 0<=time.time()-p['created_at']<900:raise ValueError('Fresh approved unconsumed plan required')
 if before['level']!=7 or before['cpu_c']>=60 or any(f['rpm']<3000 or f['state']!=48 for f in before['fans']):raise ValueError('Stable full cooling and nonzero fan feedback required')
 if not a.apply:print(json.dumps({'preflight_passed':True,'no_speed_change':True,'snapshot':before}));return
 p['consumed']=True;atomic(a.plan,p);atomic(r/'owner.json',{'pid':os.getpid(),'start_ticks':ticks(os.getpid()),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()});atomic(r/'lease.json',{'expires':time.monotonic()+2.5,'done':False})
 unit='freeqnap-fan-guard-'+b['id'];subprocess.run(['systemd-run','--unit='+unit,'--property=Type=exec','--property=Restart=no','--property=RuntimeMaxSec=45','--setenv=PYTHONPATH='+str(Path(sys.modules['freeqnap.state'].__file__).resolve().parents[1]),'/usr/bin/python3',str(Path(__file__).resolve()),'--guard','--plan',str(a.plan.resolve())],check=True,capture_output=True)
 deadline=time.monotonic()+3
 while not (r/'guard-ready.json').exists():
  if time.monotonic()>deadline:raise ValueError('Independent guard not ready; no reduction authorized')
  atomic(r/'lease.json',{'expires':time.monotonic()+2.5,'done':False});time.sleep(.1)
 result={'before':before,'samples':[],'mode':b['mode'],'full_speed_default_unchanged':True};changed=False
 try:
  atomic(r/'lease.json',{'expires':time.monotonic()+2.5,'done':False});changed=True;set_six();start=time.monotonic();atomic(r/'stage.json',{'stage':'level-6-applied','at':time.time()})
  if b['mode']=='lost-heartbeat':
   while True:time.sleep(1) # The independent guard must kill only this test owner and restore full.
  while time.monotonic()-start<10:
   atomic(r/'lease.json',{'expires':time.monotonic()+2.5,'done':False});value=snapshot();result['samples'].append(value)
   if value['level']!=6 or value['cpu_c']>=65 or any(f['state']!=48 or f['rpm']<before['fans'][i]['rpm']*.7 for i,f in enumerate(value['fans'])):raise ValueError('Fan/temperature guard tripped')
   time.sleep(.5)
 finally:
  if changed:
   result['after']=full();atomic(r/'lease.json',{'expires':time.monotonic()+2.5,'done':True});atomic(r/'result.json',result)
 if not result['samples'] or not all(any(s['fans'][i]['rpm']<before['fans'][i]['rpm']*.98 for s in result['samples']) for i in range(3)):raise ValueError('Actual speed response not established on all three fans')
 deadline=time.monotonic()+6
 while any(f['rpm']<before['fans'][i]['rpm']*.97 for i,f in enumerate(result['after']['fans'])) and time.monotonic()<deadline:
  time.sleep(.5);result['after']=snapshot()
 if any(f['rpm']<before['fans'][i]['rpm']*.97 for i,f in enumerate(result['after']['fans'])):raise ValueError('Full-speed RPM recovery not established')
 result['full_rpm_recovered']=True;result['step_passed']=True;atomic(r/'result.json',result);print(json.dumps({'step_passed':True,'samples':len(result['samples']),'full_restored':result['after']['level']==7}))
if __name__=='__main__':main()
