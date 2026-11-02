"""Conservative two-level cooling policy; no hardware I/O on import.

Level 7 is the accepted full-speed setting. Level 6 is never operationally
accepted by this policy alone: each appliance needs attended hardware acceptance.
Unknown, stale or faulty inputs always request full cooling.
"""
import math

def finite(value):return type(value) in (int,float) and math.isfinite(value)

def decide(sample,previous=7,enabled=False):
    full=lambda why:{'level':7,'reason':why,'fault':why not in ('fixed-full','warm','hysteresis')}
    if enabled is not True:return full('fixed-full')
    if not isinstance(sample,dict):return full('invalid-sample')
    cpu=sample.get('cpu_c');age=sample.get('cpu_age');disk_age=sample.get('disk_age');disks=sample.get('disks_c');fans=sample.get('fans')
    if not finite(cpu) or not -10<=cpu<=110 or not finite(age) or not 0<=age<=3:return full('cpu-unavailable-or-stale')
    if not finite(disk_age) or not 0<=disk_age<=90 or not isinstance(disks,list) or len(disks)!=4 or any(not finite(t) or not 0<=t<=85 for t in disks):return full('disk-temperature-unavailable-or-stale')
    if not isinstance(fans,list) or len(fans)!=3 or any(not isinstance(f,dict) or not finite(f.get('rpm')) or not 5500<=f['rpm']<=30000 or f.get('state')!=48 for f in fans):return full('fan-feedback-unavailable-or-fault')
    if cpu>=60 or max(disks)>=48:return full('warm')
    if cpu<=52 and max(disks)<=42:return {'level':6,'reason':'cool-high-airflow-step','fault':False}
    return {'level':6 if previous==6 else 7,'reason':'hysteresis','fault':False}
