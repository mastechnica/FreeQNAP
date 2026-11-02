#!/usr/bin/env python3
"""Attended stale-sensor/controller-stop cooling checks; full speed on cleanup.

Default is read-only preflight. Requires a fresh private exact-install plan.
Never stops fans, changes boot/RAID metadata or opens the hardware watchdog.
"""
import argparse,hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from freeqnap import cooling
from freeqnap.state import atomic
from freeqnap.nas.common import canonical

def read_plan(path):
    info=path.lstat()
    if path.is_symlink() or info.st_uid!=0 or info.st_mode&0o077:raise ValueError('Private root-owned plan required')
    p=json.loads(path.read_text());b=p['body'];cooling.board()
    if p.get('consumed') or p.get('owner_approved') is not True or not 0<=time.time()-p['created_at']<900 or p['digest']!=hashlib.sha256(canonical(b)).hexdigest():raise ValueError('Fresh approved unconsumed plan required')
    if b['install_id']!=Path('/etc/freeqnap-install-id').read_text().strip() or b['owner_watching'] is not True or b['scenario'] not in ('stale-inventory','controller-stop'):raise ValueError('Exact attended scope required')
    if not isinstance(b['id'],str) or len(b['id'])!=32 or any(c not in '0123456789abcdef' for c in b['id']):raise ValueError('Invalid generation')
    return p

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--apply',action='store_true');a=parser.parse_args();os.umask(0o027)
    p=read_plan(a.plan);b=p['body'];r=a.plan.parent
    if cooling.configuration()['mode']!='full' or cooling.attended_trial():raise ValueError('Fixed full speed with no other trial required')
    v=cooling.sample()
    if v['level']!=7 or v['cpu_c']>55 or max(v['disks_c'])>45 or cooling.decide(v,enabled=True)['fault']:raise ValueError('Cool healthy full-speed preflight required')
    if not a.apply:print(json.dumps({'preflight_passed':True,'no_changes':True}));return
    p['consumed']=True;atomic(a.plan,p);started=time.monotonic();trial={**cooling.owner_identity(),'generation':b['id'],'install_id':b['install_id'],'owner_watching':True,'started':started,'deadline':started+120,'lease_expires':started+3};stopped=None;injected=False;result={};error=None;written=False
    def tick():
        nonlocal written
        if written and not (cooling.RUNTIME/'trial.json').exists():raise ValueError('Trial cancelled')
        if (cooling.RUNTIME/'trial.json').exists() and cooling.trusted(cooling.RUNTIME/'trial.json')['generation']!=b['id']:raise ValueError('Trial replaced')
        trial['lease_expires']=time.monotonic()+3;atomic(cooling.RUNTIME/'trial.json',trial,mode=0o640);written=True
    def status():return cooling.trusted(cooling.RUNTIME/'status.json')
    def mode():
        with cooling.board()() as m:return int(m.exchange('@FS',4,b'@F')[2:3])
    def interrupt(*_):raise RuntimeError('Attended fault test interrupted')
    signal.signal(signal.SIGTERM,interrupt);signal.signal(signal.SIGINT,interrupt)
    try:
        tick();end=time.monotonic()+6
        while time.monotonic()<end:
            tick();s=status()
            if s.get('attended_trial') and s.get('level')==6 and time.monotonic()-s['monotonic']<2:break
            time.sleep(.1)
        else:raise ValueError('High-speed entry not established')
        if mode()!=6:raise ValueError('Physical high-speed readback missing')
        if b['scenario']=='stale-inventory':
            inventory=Path('/run/freeqnap/inventory.json');value=cooling.trusted(inventory)
            if os.getegid()!=inventory.stat().st_gid:raise ValueError('Run with the inventory group to preserve ownership')
            value['sampled_at']=time.time()-121;tick();injected=True;atomic(inventory,value,mode=0o640);event=time.monotonic();end=event+5
            while time.monotonic()<end:
                tick();s=status()
                if s.get('fault') and s.get('reason')=='disk-temperature-unavailable-or-stale' and s.get('level')==7:break
                time.sleep(.1)
            else:raise ValueError('Actual controller stale-sensor response not established')
            if mode()!=7:raise ValueError('Full mode readback missing')
            result={'scenario':b['scenario'],'controller_fault_observed':True,'mode_full_observed_seconds':round(time.monotonic()-event,3),'controller_status':s}
        else:
            owner=cooling.trusted(cooling.RUNTIME/'lease.json')
            unit_pid=int(subprocess.check_output(['systemctl','show','freeqnap-cooling.service','--property=MainPID','--value'],timeout=5))
            if not cooling.alive(owner) or owner.get('generation')!=b['id'] or owner['pid']!=unit_pid:raise ValueError('Controller owner changed')
            stopped=owner;event=time.monotonic();os.kill(owner['pid'],signal.SIGSTOP);end=event+5
            while time.monotonic()<end:
                tick()
                try:observed=mode()
                except TimeoutError as exc:
                    if str(exc)!='MCU is busy':raise
                    observed=None
                if observed==7:break
                time.sleep(.1)
            else:raise ValueError('Independent full-speed recovery not established within five seconds')
            result={'scenario':b['scenario'],'mode_full_observed_seconds':round(time.monotonic()-event,3),'guard_fault':cooling.trusted(cooling.RUNTIME/'fault.json')}
            if result['guard_fault'].get('generation')!=b['id'] or result['guard_fault'].get('full_verified') is not True:raise ValueError('Independent guard result missing')
            end=time.monotonic()+10
            while time.monotonic()<end:
                tick();new=cooling.trusted(cooling.RUNTIME/'lease.json');s=status()
                if new['pid']!=owner['pid'] and cooling.alive(new) and s.get('level')==7 and s.get('fault') is True:break
                time.sleep(.2)
            else:raise ValueError('Restarted controller did not retain fault-latched full speed')
            result.update(restarted_fault_latched=True,controller_status=s)
    except Exception as exc:error=str(exc)
    finally:
        # A stopped owner must release its command/TTY locks before cleanup.
        if stopped and cooling.alive(stopped):os.kill(stopped['pid'],signal.SIGKILL)
        with cooling.control_lock():
            try:
                if cooling.trusted(cooling.RUNTIME/'trial.json')['generation']==b['id']:(cooling.RUNTIME/'trial.json').unlink()
            except FileNotFoundError:pass
            cooling.full()
        if injected:subprocess.run(['systemctl','start','freeqnap-collect.service'],check=True,timeout=100)
        result.update(passed=error is None,error=error,after=cooling.sample(),permanent_acceptance_created=False)
        atomic(r/'result.json',result);print(json.dumps({'passed':result['passed'],'error':error,'scenario':b['scenario'],'full_restored':result['after']['level']==7}))
    if error:raise SystemExit(1)
if __name__=='__main__':main()
