"""Local board cooling owner and independent lease guard; defaults to full speed.

Only stock high-airflow levels 6/7 are allowed. Automatic mode additionally needs
an exact-install acceptance receipt; configuration alone cannot bypass that gate.
"""
import argparse
import contextlib
import fcntl
import importlib.util
import json
import os
import signal
import stat
import subprocess
import time
from pathlib import Path
from .cooling_policy import decide
from .state import atomic

RUNTIME=Path('/run/freeqnap-cooling')
CONFIG=Path('/etc/freeqnap/cooling.json')
ACCEPTANCE=Path('/var/lib/freeqnap-cooling/acceptance.json')
FULL='/usr/local/sbin/eyeq-mcu-safe-full'

def trusted(path):
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022 or info.st_size>1024*1024:
        raise ValueError('Untrusted cooling state')
    return json.loads(path.read_text())

def boot_id():return Path('/proc/sys/kernel/random/boot_id').read_text().strip()
def ticks(pid):return Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[19]
def owner_identity():return {'pid':os.getpid(),'start_ticks':ticks(os.getpid()),'boot_id':boot_id()}
def alive(owner):
    try:return type(owner['pid']) is int and owner['pid']>1 and owner['boot_id']==boot_id() and ticks(owner['pid'])==owner['start_ticks']
    except (OSError,KeyError,ValueError,TypeError):return False

def board():
    if os.geteuid()!=0 or Path('/proc/device-tree/compatible').read_bytes().split(b'\0')[0]!=b'qnap,ts-431xeu':
        raise ValueError('Requires the exact QNAP board and root')
    spec=importlib.util.spec_from_file_location('freeqnap_board_mcu','/usr/local/share/eyeq/eyeq-hwctl.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.Mcu

def sample():
    with board()() as mcu:
        level=int(mcu.exchange('@FS',4,b'@F')[2:3]);fans=[]
        for i in range(3):
            raw=mcu.exchange('@F'+chr(65+i),7,('@F'+str(i)).encode())
            fans.append({'channel':i,'rpm':int.from_bytes(raw[3:5],'big')*30,'state':raw[5]})
    cpu=int(Path('/sys/class/thermal/thermal_zone0/temp').read_text())/1000
    inventory=trusted(Path('/run/freeqnap/inventory.json'))
    disks=[d for d in inventory['disks'] if d.get('type')=='disk' and d.get('tran')=='sata']
    if len(disks)!=4 or len({d.get('serial') for d in disks if d.get('serial')})!=4:
        raise ValueError('Four distinct internal disk identities required')
    reports={r['device']:r for r in inventory['smart']}
    temps=[reports[d['path']].get('temperature') for d in disks]
    return {'level':level,'fans':fans,'cpu_c':cpu,'cpu_age':0,'disks_c':temps,'disk_age':time.time()-inventory['sampled_at']}

def set_level(level):
    if type(level) is not int or level not in (6,7):raise ValueError('Only accepted high-airflow levels are permitted')
    with board()() as mcu:
        mcu.ack('@F'+str(level))
        if mcu.exchange('@FS',4,b'@F')[2:3]!=str(level).encode():raise ValueError('Fan mode readback mismatch')

def full():
    deadline=time.monotonic()+1
    while True:
        p=subprocess.run([FULL],capture_output=True,timeout=8)
        if not p.returncode:return
        error=p.stderr.decode(errors='replace').strip()
        if error.startswith('MCU lock:') and time.monotonic()<deadline:
            time.sleep(.05);continue
        raise ValueError('Full-speed cooling not verified: '+error)

@contextlib.contextmanager
def control_lock():
    RUNTIME.mkdir(mode=0o750,exist_ok=True)
    fd=os.open(RUNTIME/'control.lock',os.O_RDWR|os.O_CREAT,0o600)
    try:
        deadline=time.monotonic()+3
        while True:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:
                if time.monotonic()>=deadline:raise TimeoutError('Cooling command owner is busy')
                time.sleep(.05)
        yield
    finally:os.close(fd)

def configuration():
    try:
        c=trusted(CONFIG)
        if c.get('mode') not in ('full','auto') or not isinstance(c.get('generation'),str):raise ValueError('Invalid cooling configuration')
        return c
    except FileNotFoundError:return {'mode':'full','generation':'default'}

def accepted():
    try:
        receipt=trusted(ACCEPTANCE)
        return receipt.get('install_id')==Path('/etc/freeqnap-install-id').read_text().strip() and receipt.get('high_speed_minimum_validated') is True and receipt.get('controller_failure_validated') is True and receipt.get('thermal_load_validated') is True
    except (OSError,ValueError,KeyError,TypeError):return False

def trial_valid(value,now,boot,install_id):
    if not isinstance(value,dict):return False
    start=value.get('started');end=value.get('deadline');generation=value.get('generation');lease=value.get('lease_expires')
    return (value.get('owner_watching') is True and value.get('boot_id')==boot
            and value.get('install_id')==install_id and isinstance(generation,str)
            and len(generation)==32 and all(c in '0123456789abcdef' for c in generation)
            and type(start) in (int,float) and type(end) in (int,float)
            and 0<=now-start and 0<end-now and 0<end-start<=1800
            and type(lease) in (int,float) and 0<=lease-now<=3)

def attended_trial():
    try:
        value=trusted(RUNTIME/'trial.json')
        if trial_valid(value,time.monotonic(),boot_id(),Path('/etc/freeqnap-install-id').read_text().strip()) and alive(value):return value
    except (OSError,ValueError,KeyError,TypeError):pass
    return None

def guardian_valid(value,now,boot):
    return isinstance(value,dict) and value.get('boot_id')==boot and type(value.get('monotonic')) in (int,float) and 0<=now-value['monotonic']<2 and value.get('ready') is True

def lease_valid(value,now,boot):
    return isinstance(value,dict) and value.get('boot_id')==boot and type(value.get('expires')) in (int,float) and 0<=value['expires']-now<=3 and value.get('level') in (6,7)

def publish(name,value):atomic(RUNTIME/name,value,mode=0o640)
def singleton(name):
    fd=os.open(RUNTIME/name,os.O_RDWR|os.O_CREAT,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    return fd

def controller():
    board();RUNTIME.mkdir(mode=0o750,exist_ok=True);lock=singleton('controller.lock');stop=False
    def halt(*_):
        nonlocal stop
        stop=True
    signal.signal(signal.SIGTERM,halt);signal.signal(signal.SIGINT,halt)
    identity=owner_identity();previous=7;full();last_history=0;last_trial=None
    try:
        while not stop:
            started=time.monotonic();config=configuration();trial=attended_trial();generation=trial['generation'] if trial else config['generation']
            publish('lease.json',{**identity,'generation':generation,'expires':started+3,'level':previous})
            try:
                guard=trusted(RUNTIME/'guard.json');latch=trusted(RUNTIME/'fault.json') if (RUNTIME/'fault.json').exists() else {}
                enable=((config['mode']=='auto' and accepted()) or trial is not None) and guardian_valid(guard,started,identity['boot_id']) and latch.get('generation')!=generation
                value=sample()
                # Attended validation may start only the proven high-airflow step
                # in a cool envelope; normal automatic entry thresholds stay unchanged.
                if trial and last_trial!=generation and value['cpu_c']<=55 and all(type(t) in (int,float) and t<=45 for t in value['disks_c']):previous=6
                if not trial and last_trial is not None:previous=7
                last_trial=generation if trial else None
                decision=decide(value,previous,enable)
                if (config['mode']=='auto' or trial is not None) and not enable:decision={'level':7,'reason':'automatic-mode-not-accepted-or-guard-unavailable','fault':True}
                target=decision['level']
                if target==6:
                    # Serialize cancellation with the final authorization check/write.
                    with control_lock():
                        current_trial=attended_trial();current_config=configuration()
                        current_generation=current_trial['generation'] if current_trial else current_config['generation']
                        if current_generation!=generation or not ((current_trial is not None) or (current_config['mode']=='auto' and accepted())):raise ValueError('Reduced-speed permission cancelled')
                        if not guardian_valid(trusted(RUNTIME/'guard.json'),time.monotonic(),identity['boot_id']):raise ValueError('Independent guard heartbeat missing')
                        current_latch=trusted(RUNTIME/'fault.json') if (RUNTIME/'fault.json').exists() else {}
                        if current_latch.get('generation')==generation:raise ValueError('Reduced-speed generation is fault-latched')
                        if target!=value['level']:set_level(target)
                elif target!=value['level']:set_level(target)
                previous=target
                status={'time':time.time(),'boot_id':identity['boot_id'],'monotonic':time.monotonic(),'configured_mode':config['mode'],'automatic_accepted':accepted(),'attended_trial':trial is not None,**decision,'sample':value,'level':target}
            except Exception as exc:
                full();previous=7
                status={'time':time.time(),'boot_id':identity['boot_id'],'monotonic':time.monotonic(),'configured_mode':config['mode'],'level':7,'fault':True,'reason':str(exc)}
            publish('status.json',status)
            publish('lease.json',{**identity,'generation':generation,'expires':time.monotonic()+3,'level':previous})
            if time.monotonic()-last_history>=30:
                history=Path('/var/lib/freeqnap-cooling/history.jsonl')
                if history.exists() and history.stat().st_size>3*1024**2:history.replace(history.with_suffix('.previous.jsonl'))
                with history.open('a') as f:f.write(json.dumps(status)+'\n')
                last_history=time.monotonic()
            time.sleep(max(.05,1-(time.monotonic()-started)))
    finally:
        full();publish('status.json',{'time':time.time(),'boot_id':identity['boot_id'],'monotonic':time.monotonic(),'level':7,'fault':False,'reason':'controller-stopped-full-speed'});os.close(lock)

def guardian():
    board();RUNTIME.mkdir(mode=0o750,exist_ok=True);lock=singleton('guard.lock');full();boot=boot_id();last_restore=0
    while True:
        now=time.monotonic();ready=True;reason=None
        try:
            lease=trusted(RUNTIME/'lease.json')
            if not lease_valid(lease,now,boot) or not alive(lease):
                reason='controller-heartbeat-lost'
                publish('guard.json',{'boot_id':boot,'monotonic':time.monotonic(),'ready':False,'reason':reason})
                publish('fault.json',{'time':time.time(),'generation':lease.get('generation'),'reason':reason,'full_verified':False})
                if alive(lease):os.kill(lease['pid'],signal.SIGKILL)
                full();last_restore=time.monotonic()
                publish('fault.json',{'time':time.time(),'generation':lease.get('generation'),'reason':reason,'full_verified':True})
        except FileNotFoundError:
            if now-last_restore>=5:full();last_restore=time.monotonic()
        except Exception as exc:
            ready=False;reason=str(exc)
            # Any malformed lease/state requires full cooling; preserve failures.
            try:full();last_restore=time.monotonic()
            except Exception as restore:reason+='; '+str(restore)
        publish('guard.json',{'boot_id':boot,'monotonic':time.monotonic(),'ready':ready,'reason':reason})
        time.sleep(.2)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=['controller','guard','sample','full']);args=parser.parse_args();os.umask(0o027)
    if args.operation=='sample':print(json.dumps(sample()))
    elif args.operation=='full':board();full()
    elif args.operation=='guard':guardian()
    else:controller()
if __name__=='__main__':main()
