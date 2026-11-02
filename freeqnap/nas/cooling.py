"""Fixed cooling controls and read-only watchdog status; no raw MCU access."""
import secrets
import json
import math
import os
import stat
import time
from pathlib import Path
from .. import cooling
from ..state import atomic

WATCHDOG_CONFIG=Path('/etc/systemd/system.conf.d/80-freeqnap-watchdog.conf')
WATCHDOG_SYSFS=Path('/sys/class/watchdog/watchdog0')
HISTORY_DIRECTORY=Path('/var/lib/freeqnap-cooling')

class Cooling:
    def status(self,request=None):
        try:config=cooling.configuration()
        except (ValueError,OSError):config={'mode':'full','generation':'unavailable'}
        result={'configured_mode':config['mode'],'automatic_accepted':cooling.accepted(),'available':False,'sample':None,'guard':None,'limits':{'minimum_level':6,'full_level':7,'cpu_full_c':60,'disk_full_c':48}}
        for name,key in [('status.json','controller'),('guard.json','guard')]:
            try:
                value=cooling.trusted(cooling.RUNTIME/name)
                age=time.monotonic()-value['monotonic']
                if value['boot_id']!=cooling.boot_id() or not 0<=age<5:raise ValueError('Stale cooling status')
                result[key]=value
                if key=='controller':result.update(available=True,sample=value.get('sample'),level=value['level'],fault=value.get('fault',False),reason=value.get('reason'))
            except (OSError,ValueError,KeyError,TypeError):pass
        result['watchdog']=self.watchdog()
        return result

    def mode(self,request):
        if set(request)!={'mode'} or request['mode'] not in ('full','auto'):raise ValueError('Choose Full speed or Automatic')
        if request['mode']=='auto' and not cooling.accepted():raise ValueError('Automatic cooling is unavailable until this NAS passes thermal and failure validation')
        cooling.board()
        with cooling.control_lock():
            if request['mode']=='full':(cooling.RUNTIME/'trial.json').unlink(missing_ok=True)
            # Retain the operator's full-speed intent even if the hardware request fails.
            atomic(cooling.CONFIG,{'mode':request['mode'],'generation':secrets.token_hex(16)},mode=0o640)
            if request['mode']=='full':cooling.full()
        return {'saved':True,'mode':request['mode'],'applied':request['mode']=='full','note':'Automatic mode is applied by the independent local controller; check current status'}

    def watchdog(self,request=None):
        result={'available':False,'expected_enabled':WATCHDOG_CONFIG.exists(),'policy':'Service-manager hardware supervision; application faults use service recovery rather than deliberate hardware reset'}
        try:
            base=WATCHDOG_SYSFS
            result.update(available=True,identity=(base/'identity').read_text().strip(),state=(base/'state').read_text().strip(),timeout_seconds=int((base/'timeout').read_text()),nowayout=(base/'nowayout').read_text().strip()=='1')
        except (OSError,ValueError):pass
        return result

    def health(self):
        from .health import fault
        if not cooling.RUNTIME.exists():return []
        value=self.status()
        if not value['available']:return [fault('controller','critical','Cooling controller telemetry is unavailable')]
        if not value.get('guard') or not value['guard'].get('ready'):return [fault('guard','critical','Independent cooling guard needs attention')]
        if value.get('fault'):return [fault('controller','critical','Cooling has requested full speed after a fault',{'reason':value.get('reason'),'level':value.get('level')})]
        return []

    def watchdog_health(self):
        from .health import fault
        value=self.watchdog()
        if value['expected_enabled'] and (not value['available'] or value.get('state')!='active'):
            return [fault('supervision','critical','Configured hardware watchdog is not active')]
        return []

    def history(self,request):
        if set(request)-{'limit'}:raise ValueError('Unknown cooling-history option')
        limit=request.get('limit',120)
        if type(limit) is not int or not 1<=limit<=240:raise ValueError('Choose 1–240 history samples')
        points=[]
        number=lambda x:type(x) in (int,float) and math.isfinite(x)
        for name in ('history.previous.jsonl','history.jsonl'):
            try:fd=os.open(HISTORY_DIRECTORY/name,os.O_RDONLY|os.O_NOFOLLOW)
            except FileNotFoundError:continue
            with os.fdopen(fd,'rb') as stream:
                info=os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('Untrusted cooling history')
                offset=max(0,info.st_size-512*1024);stream.seek(offset)
                if offset:stream.readline()
                data=stream.read(512*1024)
            for line in data.splitlines():
                try:
                    row=json.loads(line);stamp=row.get('time');sample=row.get('sample') or {}
                    if not number(stamp) or not 0<=time.time()-stamp<=48*3600:continue
                    point={'time':stamp,'level':row.get('level') if row.get('level') in (6,7) else None,'fault':row.get('fault') is True,'attended_trial':row.get('attended_trial') is True,'temperature':sample.get('cpu_c') if number(sample.get('cpu_c')) else None}
                    disks=sample.get('disks_c');point['hottest_disk']=max(disks) if isinstance(disks,list) and len(disks)==4 and all(number(v) for v in disks) else None
                    fans=sample.get('fans') or []
                    for i in range(3):point['fan'+str(i)]=fans[i].get('rpm') if len(fans)>i and isinstance(fans[i],dict) and number(fans[i].get('rpm')) else None
                    points.append(point)
                except (ValueError,KeyError,TypeError,AttributeError):continue
        points=sorted(points,key=lambda p:p['time'])[-limit:]
        return {'points':points,'sample_interval_seconds':30,'stale':not points or time.time()-points[-1]['time']>90}
