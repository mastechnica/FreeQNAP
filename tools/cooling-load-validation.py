#!/usr/bin/env python3
"""Attended cooling load validation. Default is read-only preflight.

Requires a fresh private exact-install/array/disk plan. Disk traffic is direct
read-only; no filesystems, metadata, RAID membership or boot settings are changed.
Adaptive trials expire automatically and never create permanent acceptance.
"""
import argparse,hashlib,json,mmap,multiprocessing,os,signal,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from freeqnap import cooling
from freeqnap.state import atomic
from freeqnap.nas.common import canonical

def burn(stop):
    data=b'x'*(1024*1024)
    while not stop.is_set():hashlib.sha256(data).digest()

def disk_identity(path):
    value=json.loads(subprocess.check_output(['lsblk','-J','-d','-b','-o','PATH,TRAN,SERIAL,SIZE',path],timeout=5))['blockdevices']
    if len(value)!=1:raise ValueError('Ambiguous disk')
    d=value[0]
    return {'path':d['path'],'serial':d['serial'],'size':d['size'],'tran':d['tran']}

def read_disk(expected,stop):
    if disk_identity(expected['path'])!=expected:raise ValueError('Disk identity changed')
    fd=os.open(expected['path'],os.O_RDONLY|os.O_DIRECT);buf=mmap.mmap(-1,4*1024*1024);i=0
    try:
        while not stop.is_set():
            os.lseek(fd,1024**3+(i%128)*len(buf),os.SEEK_SET)
            if os.readv(fd,[buf])!=len(buf):raise ValueError('Short direct disk read')
            i+=1;stop.wait(.2)
    finally:buf.close();os.close(fd)

def arrays_ok(arrays):
    for array in arrays:
        base=Path('/sys/block')/array['device']/'md'
        if (base/'uuid').read_text().strip()!=array['uuid'] or (base/'degraded').read_text().strip()!='0' or (base/'sync_action').read_text().strip()!='idle':raise ValueError('Array identity/health changed')

def thermal_scope(body,kernel_trip=None):
    if type(body.get('cpu_stop_c')) is not int or type(body.get('disk_stop_c')) is not int or body['disk_stop_c']!=48:return False
    if body['cpu_stop_c']==65:return True
    return body['cpu_stop_c']==70 and body.get('thermal_basis')=='stock-dts-105-current-trip-80' and kernel_trip==80000

def plan(path):
    info=path.lstat()
    if path.is_symlink() or info.st_uid!=0 or info.st_mode&0o077:raise ValueError('Private root-owned plan required')
    p=json.loads(path.read_text());b=p['body']
    if p['digest']!=hashlib.sha256(canonical(b)).hexdigest() or p.get('consumed') or p.get('owner_approved') is not True or not 0<=time.time()-p['created_at']<900:raise ValueError('Fresh approved immutable plan required')
    cooling.board()
    if b['install_id']!=Path('/etc/freeqnap-install-id').read_text().strip() or b['owner_watching'] is not True:raise ValueError('Exact install and attended owner required')
    if b['mode'] not in ('full','adaptive') or b['seconds'] not in (600,1200) or b['cpu_workers'] not in (0,1,3) or b['cpu_stop_c'] not in (65,70) or b['disk_stop_c']!=48:raise ValueError('Unexpected bounded load scope')
    trip=int(Path('/sys/class/thermal/thermal_zone0/trip_point_0_temp').read_text()) if b['cpu_stop_c']==70 else None
    if not thermal_scope(b,trip):raise ValueError('Reviewed thermal basis and unchanged 80 C kernel trip required')
    if len(b['disks'])!=4 or len({d['serial'] for d in b['disks']})!=4 or len(b['arrays'])!=2:raise ValueError('Expected four distinct internal disks and two healthy arrays')
    for d in b['disks']:
        if d['tran']!='sata' or not d['path'].startswith('/dev/sd') or d['size']<9*1000**4 or disk_identity(d['path'])!=d:raise ValueError('Internal disk identity mismatch')
    arrays_ok(b['arrays'])
    return p

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True);p.add_argument('--apply',action='store_true');a=p.parse_args();os.umask(0o077)
    record=plan(a.plan);b=record['body'];r=a.plan.parent;value=cooling.sample()
    decision=cooling.decide(value,enabled=True)
    if value['level']!=7 or value['cpu_c']>=60 or decision['fault']:raise ValueError('Fresh healthy full-speed preflight required')
    if b['mode']=='adaptive' and (value['cpu_c']>55 or max(value['disks_c'])>45):raise ValueError('Cool attended entry envelope required')
    if not a.apply:print(json.dumps({'preflight_passed':True,'no_speed_change':True,'sample':value}));return
    record['consumed']=True;atomic(a.plan,record)
    stop=multiprocessing.Event();children=[];rows=[];started=time.monotonic();error=None;trial=None
    def halt(*_):stop.set()
    signal.signal(signal.SIGTERM,halt);signal.signal(signal.SIGINT,halt)
    try:
        if b['mode']=='adaptive':
            trial={**cooling.owner_identity(),'lease_expires':started+3,'generation':b['id'],'owner_watching':True,'install_id':b['install_id'],'boot_id':cooling.boot_id(),'started':started,'deadline':started+b['seconds']+30}
            if cooling.attended_trial():raise ValueError('Another attended trial is active')
            atomic(cooling.RUNTIME/'trial.json',trial,mode=0o640)
        for _ in range(b['cpu_workers']):
            child=multiprocessing.Process(target=burn,args=(stop,));child.start();children.append(child)
        for d in b['disks']:
            child=multiprocessing.Process(target=read_disk,args=(d,stop));child.start();children.append(child)
        while time.monotonic()-started<b['seconds']:
            if stop.is_set():raise ValueError('Campaign interrupted')
            if trial:
                current=cooling.trusted(cooling.RUNTIME/'trial.json')
                if current['generation']!=trial['generation']:raise ValueError('Attended trial cancelled or replaced')
                trial['lease_expires']=time.monotonic()+3
                atomic(cooling.RUNTIME/'trial.json',trial,mode=0o640)
            arrays_ok(b['arrays']);value=cooling.sample();guard=cooling.trusted(cooling.RUNTIME/'guard.json')
            if not cooling.guardian_valid(guard,time.monotonic(),cooling.boot_id()):raise ValueError('Independent guard unavailable')
            value.update(elapsed=round(time.monotonic()-started,3),load=os.getloadavg()[0])
            rows.append(value);atomic(r/'latest.json',value)
            with (r/'samples.jsonl').open('a') as f:f.write(json.dumps(value)+'\n')
            if cooling.decide(value,enabled=True)['fault']:raise ValueError('Sensor/tach health failed')
            if value['cpu_c']>=b['cpu_stop_c'] or max(value['disks_c'])>=b['disk_stop_c']:raise ValueError('Conservative thermal stop threshold reached')
            if b['mode']=='full' and value['level']!=7:raise ValueError('Full-mode mismatch')
            if value['level'] not in (6,7):raise ValueError('Unexpected fan level')
            if any(child.exitcode is not None for child in children):raise ValueError('Load worker failed')
            for d in b['disks']:
                if disk_identity(d['path'])!=d:raise ValueError('Disk identity changed')
            stop.wait(1)
        if b['mode']=='adaptive' and not any(v['level']==6 for v in rows):raise ValueError('High-speed response was not observed')
    except Exception as exc:error=str(exc)
    finally:
        stop.set()
        for child in children:
            child.join(3)
            if child.is_alive():child.terminate();child.join(2)
        with cooling.control_lock():
            if trial:
                try:
                    current=cooling.trusted(cooling.RUNTIME/'trial.json')
                    if current['generation']==trial['generation']:(cooling.RUNTIME/'trial.json').unlink()
                except FileNotFoundError:pass
            cooling.full()
        after=cooling.sample()
        if after['level']!=7:error='Full-speed cleanup readback failed'
        result={'passed':error is None,'error':error,'mode':b['mode'],'seconds':round(time.monotonic()-started,3),'samples':len(rows),'high_speed_samples':sum(v['level']==6 for v in rows),'observed_high_interval_seconds':sum(n['elapsed']-p['elapsed'] for p,n in zip(rows,rows[1:]) if p['level']==6 and n['level']==6),'peak_cpu_c':max([v['cpu_c'] for v in rows],default=None),'peak_disk_c':max([max(v['disks_c']) for v in rows],default=None),'after':after,'writes_issued':False,'permanent_acceptance_created':False}
        atomic(r/'result.json',result);print(json.dumps(result))
    if error:raise SystemExit(1)
if __name__=='__main__':main()
