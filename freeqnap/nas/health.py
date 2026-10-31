"""Durable local health incidents. Acknowledgment never hides an active fault."""
import json, math, re, secrets, stat, threading, time
from pathlib import Path

DEFAULTS={'space_warning_percent':90,'space_critical_percent':97,'temperature_warning_c':75,'temperature_critical_c':85}

def policy(value):
    if not isinstance(value,dict) or set(value)!=set(DEFAULTS):raise ValueError('Choose all health thresholds')
    if any(type(v) is not int for v in value.values()):raise ValueError('Health thresholds must be whole numbers')
    if not 50<=value['space_warning_percent']<value['space_critical_percent']<=99:raise ValueError('Space thresholds must increase from 50 through 99 percent')
    if not 50<=value['temperature_warning_c']<value['temperature_critical_c']<=105:raise ValueError('Temperature thresholds must increase from 50 through 105 C')
    return dict(value)

def number(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError('Invalid monitor measurement')
    return value

def fault(source,severity,title,details=None):return {'source':source,'severity':severity,'title':title,'details':details or {}}

class Health:
    def __init__(self,ctx,inventory='/run/freeqnap/inventory.json',schedules=None):
        self.ctx=ctx;self.inventory=Path(inventory);self.schedules=schedules;self.lock=threading.Lock();self.optional_checks={}
        with ctx.state.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS health_alerts(id TEXT PRIMARY KEY,scope TEXT NOT NULL,source TEXT NOT NULL,severity TEXT NOT NULL,title TEXT NOT NULL,details TEXT NOT NULL,first_seen REAL NOT NULL,last_seen REAL NOT NULL,resolved_at REAL,acknowledged_at REAL);
            CREATE UNIQUE INDEX IF NOT EXISTS health_one_active ON health_alerts(scope,source) WHERE resolved_at IS NULL;
            CREATE TABLE IF NOT EXISTS health_events(id INTEGER PRIMARY KEY AUTOINCREMENT,alert_id TEXT NOT NULL,kind TEXT NOT NULL,severity TEXT NOT NULL,title TEXT NOT NULL,created REAL NOT NULL);''')
    def settings(self,request=None):
        if request is not None:
            value=policy(request);self.ctx.state.set('health_policy',value)
        return policy(self.ctx.state.setting('health_policy',DEFAULTS))
    def reconcile(self,scope,observations,now):
        # Reconcile only a completely evaluated scope. Missing telemetry is never recovery.
        sources={};rank={'info':0,'warning':1,'critical':2}
        for item in observations:
            if item['source'] in sources or item['severity'] not in rank:raise ValueError('Ambiguous health observation')
            sources[item['source']]=item
        with self.ctx.state.connect() as db:
            db.execute('BEGIN IMMEDIATE');active={r['source']:dict(r) for r in db.execute('SELECT * FROM health_alerts WHERE scope=? AND resolved_at IS NULL',(scope,))}
            def event(ident,kind,item):db.execute('INSERT INTO health_events(alert_id,kind,severity,title,created) VALUES(?,?,?,?,?)',(ident,kind,item['severity'],item['title'],now))
            for source,item in sources.items():
                old=active.pop(source,None);details=json.dumps(item['details'],sort_keys=True)
                if old:
                    escalated=rank[item['severity']]>rank[old['severity']]
                    db.execute('UPDATE health_alerts SET severity=?,title=?,details=?,last_seen=?,acknowledged_at=? WHERE id=?',(item['severity'],item['title'],details,now,None if escalated else old['acknowledged_at'],old['id']))
                    if escalated:event(old['id'],'escalated',item)
                else:
                    ident=secrets.token_hex(16);db.execute('INSERT INTO health_alerts(id,scope,source,severity,title,details,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?)',(ident,scope,source,item['severity'],item['title'],details,now,now));event(ident,'opened',item)
            for item in active.values():db.execute('UPDATE health_alerts SET resolved_at=? WHERE id=?',(now,item['id']));event(item['id'],'resolved',item)
    def acknowledge(self,request):
        if set(request)!={'id'} or not isinstance(request['id'],str) or not re.fullmatch('[a-f0-9]{32}',request['id']):raise ValueError('Choose an active alert')
        with self.ctx.state.connect() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM health_alerts WHERE id=? AND resolved_at IS NULL',(request['id'],)).fetchone()
            if row is None:raise ValueError('Alert is no longer active')
            if row['acknowledged_at'] is None:
                now=time.time();db.execute('UPDATE health_alerts SET acknowledged_at=? WHERE id=?',(now,row['id']));db.execute('INSERT INTO health_events(alert_id,kind,severity,title,created) VALUES(?,?,?,?,?)',(row['id'],'acknowledged',row['severity'],row['title'],now))
        return {'acknowledged':request['id'],'fault_cleared':False}
    def list(self,request=None):
        with self.ctx.state.connect() as db:
            rows=db.execute('SELECT * FROM health_alerts ORDER BY resolved_at IS NULL DESC,first_seen DESC LIMIT 1000').fetchall()
            counts={r['severity']:r['count'] for r in db.execute('SELECT severity,count(*) AS count FROM health_alerts WHERE resolved_at IS NULL GROUP BY severity')}
        items=[]
        for r in rows:
            value=dict(r);value['details']=json.loads(value['details']);items.append(value)
        monitor=self.ctx.state.setting('health_monitor',{})
        return {'items':items,'active_counts':counts,'active_total':sum(counts.values()),'monitor':monitor,'monitor_stale':not 0<=time.time()-monitor.get('checked_at',0)<120,'policy':self.settings(),'external_delivery_enabled':False,'acknowledgment_hides_fault':False}
    def read_inventory(self,now):
        info=self.inventory.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size>4*1024**2:raise ValueError('Invalid inventory file')
        data=json.loads(self.inventory.read_text());age=now-number(data['sampled_at'])
        if not isinstance(data.get('errors'),list) or data['errors']:raise ValueError('Inventory is incomplete')
        if not 0<=age<120:raise ValueError('Inventory is stale or in the future')
        return data
    def raid(self,data,limits,now):
        out=[]
        for row in data['arrays']:
            missing=number(row['degraded']);action=row['sync_action'];source=row['uuid']
            if missing<0 or not isinstance(source,str) or not isinstance(action,str):raise ValueError('Invalid RAID telemetry')
            if missing:out.append(fault(source,'critical','RAID disk-failure protection is incomplete',{'array':row['device'],'missing_or_rebuilding':missing,'operation':action}))
            elif action not in ('idle','frozen'):out.append(fault(source,'warning','RAID maintenance is running',{'array':row['device'],'operation':action}))
        normalize=lambda value:value.lower().replace(':','').replace('-','')
        known={normalize(row['uuid']) for row in data['arrays']}
        for pool in self.ctx.config()['pools'].values():
            if pool.get('md_uuid') and pool.get('kind')!='usb' and normalize(pool['md_uuid']) not in known:
                out.append(fault(pool['md_uuid'],'critical','A registered RAID array is missing',{'pool':pool['name']}))
        return out
    def smart(self,data,limits,now):
        out=[]
        for row in data['smart']:
            if row.get('not_polled'):continue
            if row.get('passed') is False:out.append(fault(row['device'],'critical','A SATA drive reports failed SMART health',{'device':row['device']}))
            elif row.get('available') is not True or row.get('passed') is not True:out.append(fault(row['device'],'warning','SATA SMART health is unavailable or the drive is in standby',{'device':row['device']}))
            raw=row.get('raw',{});attrs=raw.get('ata_smart_attributes',{}).get('table',[])
            bad={str(a.get('id')):a.get('raw',{}).get('value',0) for a in attrs if a.get('id') in (5,197,198) and isinstance(a.get('raw',{}).get('value'),(int,float)) and a['raw']['value']>0}
            if bad:out.append(fault(row['device']+':sectors','warning','A disk reports reallocated, pending or uncorrectable sectors',{'device':row['device'],'attributes':bad}))
            temperature=row.get('temperature')
            if isinstance(temperature,(int,float)) and temperature>=50:out.append(fault(row['device']+':temperature','critical' if temperature>=60 else 'warning','Disk temperature is high',{'device':row['device'],'celsius':temperature}))
            tests=raw.get('ata_smart_self_test_log',{}).get('standard',{}).get('table',[])
            if tests and tests[0].get('status',{}).get('passed') is False:out.append(fault(row['device']+':selftest','critical','The latest disk self-test failed',{'device':row['device']}))
        return out
    def space(self,data,limits,now):
        out=[];seen=set()
        for row in data['volumes']:
            target=row['target']
            if target!='/' and not target.startswith('/srv/freeqnap/volumes/'):continue
            identity=(row.get('uuid'),target)
            if identity in seen:continue
            seen.add(identity);total=number(row['total_bytes']);free=number(row['available_bytes'])
            if total<=0 or not 0<=free<=total:raise ValueError('Invalid capacity telemetry')
            used=100*(1-free/total);severity='critical' if used>=limits['space_critical_percent'] or target=='/' and free<512*1024**2 else 'warning' if used>=limits['space_warning_percent'] or target=='/' and free<1024**3 else None
            if severity:out.append(fault(target,severity,'Filesystem capacity needs attention',{'mountpoint':target,'used_percent':round(used,2),'available_bytes':free}))
        if not any(target=='/' for _,target in seen):raise ValueError('Root filesystem capacity unavailable')
        return out
    def temperature(self,data,limits,now):
        out=[]
        if not data['temperatures']:return [fault('unavailable','warning','CPU temperature telemetry is unavailable')]
        for row in data['temperatures']:
            value=number(row['celsius'])
            if not -20<=value<=150:raise ValueError('Invalid temperature telemetry')
            severity='critical' if value>=limits['temperature_critical_c'] else 'warning' if value>=limits['temperature_warning_c'] else None
            if severity:out.append(fault(row['name'],severity,'CPU temperature is high',{'celsius':value}))
        return out
    def jobs(self,data,limits,now):
        with self.ctx.state.connect() as db:rows=db.execute("SELECT id,kind,status,error FROM jobs WHERE kind LIKE 'backup.%' OR kind LIKE 'backup-%' OR kind='system-local-capture'").fetchall()
        return [fault(r['id'],'warning','A backup, check or restore needs reconciliation',{'job_id':r['id'],'operation':r['kind']}) for r in rows if r['status']!='succeeded' and r['error'] is not None]
    def scheduled(self,data,limits,now):
        out=[];first_seen=self.ctx.state.setting('health_schedule_first_seen',{});seen=set()
        for row in self.schedules.list()['items'] if self.schedules else []:
            if not row['enabled']:continue
            ident=row['name'];seen.add(ident);first_seen.setdefault(ident,now);baseline=row.get('last_backup_success') or first_seen[ident]
            age=now-number(baseline)
            if age < -300:out.append(fault(ident,'warning','A backup timestamp is ahead of the system clock',{'schedule':ident}));continue
            if age>row['interval_hours']*3600*2:out.append(fault(ident,'warning','A scheduled backup is overdue',{'schedule':ident,'last_success':row.get('last_backup_success')}))
        self.ctx.state.set('health_schedule_first_seen',{k:v for k,v in first_seen.items() if k in seen})
        return out
    def services(self,data,limits,now):
        out=[]
        for name in ('freeqnap-broker','freeqnap-console','freeqnap-collect.timer','eyeq-cooling'):
            value=self.ctx.run('systemctl','show',name,'--property=ActiveState','--value').strip()
            if value!='active':out.append(fault(name,'critical','A required NAS service is unavailable',{'service':name,'state':value}))
        return out
    def tick(self,now=None):
        if not self.lock.acquire(blocking=False):return
        try:
            now=time.time() if now is None else now;limits=self.settings();errors=[];data=None
            try:data=self.read_inventory(now);self.reconcile('inventory',[],now)
            except (OSError,ValueError,KeyError,TypeError):self.reconcile('inventory',[fault('unavailable','critical','Hardware inventory is missing, stale or invalid')],now)
            for scope,check,requires_inventory in [('raid',self.raid,True),('smart',self.smart,True),('space',self.space,True),('temperature',self.temperature,True),('jobs',self.jobs,False),('schedules',self.scheduled,False),('services',self.services,False)]:
                if requires_inventory and data is None:continue
                try:
                    observed=check(data,limits,now);self.reconcile(scope,observed,now);self.reconcile('monitor-'+scope,[],now)
                except (OSError,ValueError,KeyError,TypeError):
                    errors.append(scope);self.reconcile('monitor-'+scope,[fault('unavailable','warning','Health check could not complete: '+scope)],now)
            for scope,check in self.optional_checks.items():
                try:self.reconcile(scope,check(),now);self.reconcile('monitor-'+scope,[],now)
                except (OSError,ValueError,KeyError,TypeError):
                    errors.append(scope);self.reconcile('monitor-'+scope,[fault('unavailable','warning','Health check could not complete: '+scope)],now)
            self.ctx.state.set('health_monitor',{'checked_at':now,'inventory_sampled_at':data.get('sampled_at') if data else None,'failed_scopes':errors})
        finally:self.lock.release()
