"""Bounded local system history; no disk polling, probes or external telemetry."""
import json,time,os
from pathlib import Path

def rates(previous,current,elapsed):
 if elapsed<=0:return None
 return (current-previous)/elapsed if current>=previous else None

class Metrics:
 def __init__(self,ctx):
  self.ctx=ctx;self.previous=None
  with ctx.state.connect() as db:
   db.execute('CREATE TABLE IF NOT EXISTS system_metrics(time REAL PRIMARY KEY,data TEXT NOT NULL)')
   db.execute('CREATE TABLE IF NOT EXISTS network_hours(hour INTEGER PRIMARY KEY,rx REAL NOT NULL,tx REAL NOT NULL,seconds REAL NOT NULL)')
 def sample(self):
  now=time.time();mono=time.monotonic();cpu=list(map(int,Path('/proc/stat').read_text().splitlines()[0].split()[1:9]));total=sum(cpu);idle=cpu[3]+cpu[4]
  mem={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.split(':')[0] in ('MemTotal','MemAvailable')}
  net={}
  for p in Path('/sys/class/net').iterdir():
   if not (p/'device').exists():continue
   try:net[p.name]=[int((p/'statistics/rx_bytes').read_text()),int((p/'statistics/tx_bytes').read_text())]
   except OSError:pass
  temperatures=[]
  for p in Path('/sys/class/thermal').glob('thermal_zone*/temp'):
   try:
    v=int(p.read_text())/1000
    if -20<=v<=150:temperatures.append(v)
   except (OSError,ValueError):pass
  point={'time':now,'cpu':None,'memory':(mem['MemTotal']-mem.get('MemAvailable',0))/mem['MemTotal']*100,'memory_total':mem['MemTotal'],'temperature':max(temperatures) if temperatures else None,'rx':None,'tx':None,'interfaces':{},'load':os.getloadavg()[0],'cores':os.cpu_count(),'uptime':float(Path('/proc/uptime').read_text().split()[0])}
  if self.previous:
   old=self.previous;dt=mono-old['mono'];delta=total-old['total']
   if delta>0 and 0<dt<=120:point['cpu']=max(0,min(100,100*(1-(idle-old['idle'])/delta)))
   if 0<dt<=120:
    for name,values in net.items():
     if name in old['net']:point['interfaces'][name]={'rx':rates(old['net'][name][0],values[0],dt),'tx':rates(old['net'][name][1],values[1],dt)}
    if point['interfaces']:
     for key in ('rx','tx'):
      values=[v[key] for v in point['interfaces'].values()]
      point[key]=sum(values) if all(v is not None for v in values) else None
  self.previous={'mono':mono,'total':total,'idle':idle,'net':net}
  with self.ctx.state.connect() as db:
   if self.previous and point['rx'] is not None and point['tx'] is not None:
    self.accumulate(db,now-dt,now,point['rx'],point['tx'])
   db.execute('DELETE FROM network_hours WHERE hour<?',(now-366*86400,))
   db.execute('INSERT OR REPLACE INTO system_metrics VALUES(?,?)',(now,json.dumps(point)));db.execute('DELETE FROM system_metrics WHERE time<?',(now-86400,))
  return point
 def history(self,request):
  hours=request.get('hours',1)
  if hours not in (1,6,24):raise ValueError('Choose 1, 6 or 24 hours')
  with self.ctx.state.connect() as db:rows=db.execute('SELECT data FROM system_metrics WHERE time>=? ORDER BY time LIMIT 3000',(time.time()-hours*3600,)).fetchall()
  points=[json.loads(r[0]) for r in rows]
  return {'points':points,'sample_seconds':30,'retention_hours':24,'stale':not points or time.time()-points[-1]['time']>90}

 @staticmethod
 def accumulate(db,start,end,rx,tx):
  # Weighted elapsed coverage, split at hour boundaries; gaps/reset samples excluded.
  while start<end:
   hour=int(start//3600)*3600;stop=min(end,hour+3600);seconds=stop-start
   db.execute('INSERT INTO network_hours VALUES(?,?,?,?) ON CONFLICT(hour) DO UPDATE SET rx=rx+excluded.rx,tx=tx+excluded.tx,seconds=seconds+excluded.seconds',(hour,rx*seconds,tx*seconds,seconds));start=stop
 def network_history(self,request=None):
  now=time.time()
  with self.ctx.state.connect() as db:
   rows=db.execute('SELECT * FROM network_hours ORDER BY hour').fetchall()
  periods=[]
  for label,days in [('Daily',1),('Weekly',7),('Monthly',30),('Yearly',365)]:
   selected=[r for r in rows if r['hour']>=int((now-days*86400)//3600)*3600]
   seconds=sum(r['seconds'] for r in selected);rx=sum(r['rx'] for r in selected);tx=sum(r['tx'] for r in selected)
   periods.append({'label':label,'days':days,'rx_bytes':rx,'tx_bytes':tx,'observed_seconds':seconds,'rx_average':rx/seconds if seconds else None,'tx_average':tx/seconds if seconds else None})
  recent=self.history({'hours':24})
  links=[]
  for p in sorted(Path('/sys/class/net').glob('*')):
   if not (p/'device').exists():continue
   def read(file):
    try:return (p/file).read_text().strip()
    except OSError:return None
   speed=read('speed');speed=int(speed) if speed and speed.isdigit() and int(speed)>0 else None
   links.append({'interface':p.name,'carrier':read('carrier')=='1','state':read('operstate'),'speed_mbps':speed})
  return {'periods':periods,'points':[{k:p.get(k) for k in ('time','rx','tx','interfaces')} for p in recent['points']],'stale':recent['stale'],'links':links,'sample_seconds':30,'retention_days':366,'note':'Physical interfaces combined; receive and send counted separately. Rolling windows use hourly buckets. Averages cover observed time only, excluding downtime and collection gaps. Month = 30 days; year = 365 days. History begins when collection is enabled.'}
