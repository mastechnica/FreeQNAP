"""Durable recurring shared-file backups/checks; no secrets or automatic pruning."""
import json,secrets,time
from .common import name
from .storage_boundary import shared,tokens

KEY='backup_schedules'
ACTIVE=('queued','running')

class BackupSchedules:
    def __init__(self,ctx):self.ctx=ctx
    def records(self):return self.ctx.state.setting(KEY,{})
    def bindings(self,config,cfg):
        repo=cfg['repositories'].get(config['repository'])
        if not repo or not repo.get('initialized'):raise ValueError('Choose an initialized backup repository')
        result={'repository':{k:repo.get(k) for k in ('name','kind','pool','filesystem_uuid','path','host','user','port','remote_path','repository')},'shares':{}}
        if repo['kind']=='local':
            if repo.get('pool') not in cfg['pools']:raise ValueError('Repository pool is no longer registered')
            result['repository']['storage_boundaries']=[list(token) for token in sorted(tokens(cfg['pools'][repo['pool']]))]
        for ident in config['shares'] if config.get('scope','files')=='files' else []:
            share=cfg['shares'].get(ident)
            if not share or share['pool'] not in cfg['pools']:raise ValueError('Choose existing shares on registered pools')
            pool=cfg['pools'][share['pool']]
            result['shares'][ident]={'path':share['path'],'pool':share['pool'],'filesystem_uuid':pool['filesystem_uuid'],'storage_boundaries':[list(token) for token in sorted(tokens(pool))]}
            if repo['kind']=='local' and shared(pool,cfg['pools'][repo['pool']]) and not config['same_pool_acknowledged']:raise ValueError('A backup sharing a filesystem, RAID, enclosure or physical disk requires explicit acknowledgement; use an independent destination for disaster protection')
        return result
    def validate(self,request):
        ident=name(request.get('name'));repository=name(request.get('repository'));shares=request.get('shares');enabled=request.get('enabled',False);interval=request.get('interval_hours',24);check=request.get('full_check_days',7);scope=request.get('scope','files');same=request.get('same_pool_acknowledged',False)
        if scope not in ('files','system'):raise ValueError('Choose shared files or NAS recovery configuration')
        if not isinstance(shares,list) or not (1 if scope=='files' else 0)<=len(shares)<=100 or len(set(shares))!=len(shares):raise ValueError('Select 1–100 distinct shares')
        for share in shares:name(share)
        if not isinstance(enabled,bool) or not isinstance(same,bool) or isinstance(interval,bool) or not isinstance(interval,int) or not 1<=interval<=168 or isinstance(check,bool) or not isinstance(check,int) or not 1<=check<=90:raise ValueError('Choose 1–168 hours, a 1–90 day full check, and explicit boolean options')
        return ident,{'scope':scope,'repository':repository,'shares':sorted(shares),'enabled':enabled,'interval_hours':interval,'full_check_days':check,'same_pool_acknowledged':same}
    def plan(self,request):
        ident,config=self.validate(request);records=self.records();before=records.get(ident)
        if not before and len(records)>=32:raise ValueError('At most 32 schedules are supported')
        try:bindings=self.bindings(config,self.ctx.config())
        except (ValueError,KeyError):
            if config['enabled']:raise
            bindings=None
        return self.ctx.plan('backup-schedule',{'name':ident,'config':config,'bindings':bindings,'before_revision':before['revision'] if before else None,'review':'Recurring shared-file backups, not console-only snapshots. One missed interval coalesces into one job; active repository work never overlaps. Failures remain durable and later due backups continue. Full-data checks run after the first successful backup and periodically. Existing snapshots are never automatically deleted: retention/pruning remains a separate reviewed operation. Secrets remain in the repository configuration, never this policy. A system-recovery schedule includes private keys and credentials inside encrypted repository snapshots; those can only be restored privately, not published as shares. Keep the repository password independently.'},'SAVE BACKUP SCHEDULE '+ident)
    def apply(self,request):
        with self.ctx.lock():
            path,plan=self.ctx.reviewed(request,'backup-schedule');b=plan['body'];records=self.records();old=records.get(b['name'])
            if (old['revision'] if old else None)!=b['before_revision']:raise ValueError('Schedule changed since review')
            if b['config']['enabled'] and self.bindings(b['config'],self.ctx.config())!=b['bindings']:raise ValueError('Repository/share mapping changed since review')
            self.ctx.consume(path,plan);now=time.time();runtime=dict(old.get('runtime',{})) if old and old.get('bindings')==b['bindings'] else {}
            runtime.update(next_backup_at=now+b['config']['interval_hours']*3600,next_check_at=now,last_clock=now,run_requested=False)
            records[b['name']]={'name':b['name'],'revision':secrets.token_hex(16),'config':b['config'],'bindings':b['bindings'],'runtime':runtime};self.ctx.state.set(KEY,records)
        return self.list()
    def list(self,request=None):
        records=self.records();items=[]
        with self.ctx.state.connect() as db:
            for ident,record in sorted(records.items()):
                value={'name':ident,**record['config'],**record.get('runtime',{})}
                for kind in ('backup','check'):
                    job=db.execute('SELECT id,status,updated,error FROM jobs WHERE id=?',(record.get('runtime',{}).get('last_'+kind+'_job'),)).fetchone()
                    value['last_'+kind]=dict(job) if job else None
                items.append(value)
        return {'items':items,'automatic_pruning':False,'default_enabled':False}
    def run_now(self,request):
        ident=name(request.get('name'))
        with self.ctx.lock():
            records=self.records();record=records.get(ident)
            if not record:raise ValueError('Choose a saved backup schedule')
            if self.bindings(record['config'],self.ctx.config())!=record['bindings']:raise ValueError('Review this schedule against the current repository/share mapping')
            with self.ctx.state.connect() as db:active=db.execute('SELECT id FROM jobs WHERE id=? AND status IN (?,?)',(record['runtime'].get('last_backup_job'),*ACTIVE)).fetchone()
            if active:return {'job_id':active['id'],'existing_job':True}
            record['runtime']['run_requested']=True;self.ctx.state.set(KEY,records)
        self.tick();value=next(v for v in self.list()['items'] if v['name']==ident)
        return {'run_requested':value.get('run_requested',False),'job_id':value.get('last_backup_job'),'message':value.get('message')}
    def delete_plan(self,request):
        ident=name(request.get('name'));record=self.records().get(ident)
        if not record:raise ValueError('Choose a saved schedule')
        return self.ctx.plan('backup-schedule-delete',{'name':ident,'revision':record['revision'],'review':'Remove only this recurring policy. Backup snapshots, credentials, job history and any active job remain.'},'DELETE BACKUP SCHEDULE '+ident)
    def delete(self,request):
        with self.ctx.lock():
            path,plan=self.ctx.reviewed(request,'backup-schedule-delete');b=plan['body'];records=self.records()
            if b['name'] not in records or records[b['name']]['revision']!=b['revision']:raise ValueError('Schedule changed')
            self.ctx.consume(path,plan);del records[b['name']];self.ctx.state.set(KEY,records)
        return {'removed':b['name'],'snapshots_kept':True}
    def tick(self,now=None):
        now=time.time() if now is None else now;queued=[]
        with self.ctx.state.connect() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT value FROM settings WHERE key=?',(KEY,)).fetchone()
            if not row:return []
            records=json.loads(row['value']);cfgrow=db.execute("SELECT value FROM settings WHERE key='nas'").fetchone();cfg=json.loads(cfgrow['value']) if cfgrow else {'repositories':{},'shares':{},'pools':{}}
            active=db.execute("SELECT kind,payload FROM jobs WHERE status IN ('queued','running')").fetchall();active_count=len(active);busy=set()
            for job in active:
                if job['kind'] not in ('backup.run','backup.system-run','backup.check','backup.restore'):continue
                try:busy.add(json.loads(job['payload'])['repository'])
                except (ValueError,KeyError,TypeError):continue
            for ident,record in sorted(records.items()):
                config=record['config'];runtime=record['runtime']
                for kind in ('backup','check'):
                    jid=runtime.get('last_'+kind+'_job')
                    if not jid:continue
                    job=db.execute('SELECT status,updated,error FROM jobs WHERE id=?',(jid,)).fetchone()
                    if not job or job['status'] in ACTIVE:continue
                    observed=[jid,job['status'],job['updated']]
                    if runtime.get('observed_'+kind+'_result')==observed:continue
                    runtime['observed_'+kind+'_result']=observed;runtime['last_'+kind+'_error']=job['error']
                    if job['status']=='succeeded':runtime['last_'+kind+'_success']=job['updated'];runtime[kind+'_consecutive_failures']=0
                    else:runtime[kind+'_consecutive_failures']=runtime.get(kind+'_consecutive_failures',0)+1
                if now<runtime.get('last_clock',now)-300:
                    runtime['next_backup_at']=min(runtime.get('next_backup_at',now),now+config['interval_hours']*3600)
                    runtime['next_check_at']=min(runtime.get('next_check_at',now),now+config['full_check_days']*86400);runtime['clock_changed_at']=now
                runtime['last_clock']=now
                if not config['enabled'] and not runtime.get('run_requested'):runtime['message']='Disabled';continue
                try:
                    if self.bindings(config,cfg)!=record['bindings']:raise ValueError('Repository/share identity changed; review the schedule again')
                except (ValueError,KeyError) as error:runtime['message']=str(error);continue
                if config['repository'] in busy:runtime['message']='Waiting for active repository work';continue
                kind='backup' if runtime.get('run_requested') or now>=runtime.get('next_backup_at',now) else 'check' if runtime.get('last_backup_success') and now>=runtime.get('next_check_at',now) else None
                if kind is None:runtime['message']='Waiting for next due time';continue
                if active_count>=128:runtime['message']='Queue full; due job retained for a later scheduler pass';continue
                payload={'repository':config['repository']}
                if kind=='backup':
                    if config.get('scope','files')=='files':payload['shares']=config['shares']
                    if config.get('scope','files')=='files' and config['same_pool_acknowledged']:payload['same_pool_confirmation']='SAME POOL '+config['repository']
                else:payload['read_data']=True
                jid=secrets.token_hex(16);db.execute('INSERT INTO jobs(id,kind,payload,status,created,updated) VALUES(?,?,?,?,?,?)',(jid,('backup.system-run' if config.get('scope','files')=='system' else 'backup.run') if kind=='backup' else 'backup.check',json.dumps(payload),'queued',now,now))
                runtime['last_'+kind+'_job']=jid;runtime['last_'+kind+'_queued_at']=now;runtime['next_'+kind+'_at']=now+(config['interval_hours']*3600 if kind=='backup' else config['full_check_days']*86400)
                if kind=='backup':runtime['run_requested']=False
                runtime['message']='Queued '+kind;busy.add(config['repository']);active_count+=1;queued.append(jid)
            db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(KEY,json.dumps(records)))
        return queued
