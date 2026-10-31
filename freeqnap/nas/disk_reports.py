"""Identity-bound SATA SMART reports and opt-in maintenance schedules."""
import json,time,datetime,re,threading,functools
from pathlib import Path
def synchronized(method):
 @functools.wraps(method)
 def wrapped(self,*args,**kwargs):
  with self._lock:return method(self,*args,**kwargs)
 return wrapped

class DiskReports:
 def __init__(self,ctx):
  self.ctx=ctx;self._lock=threading.RLock()
  with ctx.state.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS disk_reports(serial TEXT,time REAL,data TEXT,PRIMARY KEY(serial,time))')
 def inventory(self):
  from ..inventory import snapshot
  x=snapshot('/run/freeqnap/inventory.json')
  if x['stale']:raise ValueError('Disk inventory is stale; no test will start')
  return x
 def status(self,request=None):
  x=self.inventory();return {'disks':[{'serial':d.get('serial'),'device':d['path'],'model':d.get('model'),'eligible':d.get('tran')!='usb' and bool(d.get('serial'))} for d in x['disks'] if d['type']=='disk'],'schedules':self.ctx.state.setting('smart_schedules',{}),'test_state':self.ctx.state.setting('smart_test_state',{}),'history_days':30,'schedule_note':'Intervals are measured from the last start; first test waits its interval. Tests are deferred during RAID maintenance and when the drive is in standby.'}
 def history(self,request):
  serial=request.get('serial')
  if not isinstance(serial,str) or not 1<=len(serial)<=128:raise ValueError('Choose a disk serial')
  offset=request.get('offset',0)
  if type(offset) is not int or not 0<=offset<=10000:raise ValueError('Invalid report page')
  with self.ctx.state.connect() as db:
   rows=db.execute('SELECT time,data FROM disk_reports WHERE serial=? ORDER BY time DESC LIMIT 24 OFFSET ?',(serial,offset)).fetchall()
   total=db.execute('SELECT count(*) FROM disk_reports WHERE serial=?',(serial,)).fetchone()[0]
  return {'serial':serial,'reports':[{'time':r[0],**json.loads(r[1])} for r in rows],'total':total,'next_offset':offset+len(rows) if offset+len(rows)<total else None}
 @synchronized
 def save(self,request):
  serial=request.get('serial');short=request.get('short_days',7);long=request.get('long_days',30);enabled=request.get('enabled')
  if type(enabled) is not bool or any(type(v) is not int or not 1<=v<=365 for v in (short,long)):raise ValueError('Choose test intervals from 1–365 days')
  x=self.inventory();rows=[d for d in x['disks'] if d.get('serial')==serial and d.get('tran')!='usb' and d.get('type')=='disk']
  if len(rows)!=1:raise ValueError('Only an exactly identified internal SATA disk is supported')
  cfg=self.ctx.state.setting('smart_schedules',{});old=cfg.get(serial,{});cfg[serial]={'enabled':enabled,'short_days':short,'long_days':long,'next_short':old.get('next_short',time.time()+short*86400),'next_long':old.get('next_long',time.time()+long*86400)};self.ctx.state.set('smart_schedules',cfg);return {'saved':True,'test_started':False}
 @synchronized
 def tick(self):
  x=self.inventory();now=time.time();schedule=self.ctx.state.setting('smart_schedules',{});states=self.ctx.state.setting('smart_test_state',{})
  pending=any(row.get('pending') for row in states.values())
  for d in x['disks']:
   serial=d.get('serial')
   if d.get('type')!='disk' or not serial or d.get('tran')=='usb':continue
   smart=next((s for s in x['smart'] if s['device']==d['path']),None)
   if smart:
    with self.ctx.state.connect() as db:
     last=db.execute('SELECT max(time) FROM disk_reports WHERE serial=?',(serial,)).fetchone()[0]
     if last is None or now-last>=3600:db.execute('INSERT INTO disk_reports VALUES(?,?,?)',(serial,now,json.dumps(smart)))
     db.execute('DELETE FROM disk_reports WHERE time<?',(now-30*86400,))
   if states.get(serial,{}).get('pending'):
    fresh=json.loads(self.ctx.run('lsblk','-J','-d','-o','PATH,SERIAL,TRAN',d['path']))['blockdevices']
    if len(fresh)!=1 or fresh[0].get('serial')!=serial or fresh[0].get('tran')!='sata':raise ValueError('Scheduled disk identity changed')
    report=json.loads(self.ctx.run('smartctl','-c','-j','-n','standby',d['path']))
    active=report.get('ata_smart_data',{}).get('self_test',{}).get('status',{}).get('value')
    if active is None:
     states[serial]['status']='Test state unavailable; new tests remain paused'
    elif active>>4==15:states[serial]['status']='Self-test running; see report history for results'
    elif now-states[serial]['time']>=60:
     states[serial].update(pending=False,status='Self-test no longer running; inspect the SMART log for its result')
    self.ctx.state.set('smart_test_state',states)
   cfg=schedule.get(serial)
   if not cfg or not cfg['enabled']:continue
   kind='long' if now>=cfg['next_long'] else 'short' if now>=cfg['next_short'] else None
   if not kind:continue
   if pending:continue
   if any(a.get('sync_action') not in ('idle','frozen') or a.get('degraded') for a in x['arrays']):states[serial]={'status':'Deferred: RAID maintenance or incomplete redundancy','time':now};continue
   # Re-read identity through lsblk immediately before fixed smartctl operations.
   fresh=json.loads(self.ctx.run('lsblk','-J','-d','-o','PATH,SERIAL,TRAN',d['path']))['blockdevices']
   if len(fresh)!=1 or fresh[0].get('serial')!=serial or fresh[0].get('tran')!='sata':raise ValueError('Scheduled disk identity changed')
   identity=json.loads(self.ctx.run('smartctl','-i','-j','-n','standby',d['path']))
   if identity.get('serial_number')!=serial:states[serial]={'status':'Deferred: identity unavailable or drive in standby','time':now};continue
   report=json.loads(self.ctx.run('smartctl','-c','-j','-n','standby',d['path']))
   if report.get('ata_smart_data',{}).get('self_test',{}).get('status',{}).get('value',0)>>4==15:states[serial]={'status':'Deferred: a self-test is already running','time':now};continue
   result=self.ctx.run('smartctl','-t',kind,'-j','-n','standby',d['path'])
   cfg['next_'+kind]=now+cfg[kind+'_days']*86400
   states[serial]={'status':kind+' test requested; completion is recorded by subsequent SMART reports','time':now,'pending':True}
   break # Never start a second test in this pass.
  self.ctx.state.set('smart_schedules',schedule);self.ctx.state.set('smart_test_state',states)
