"""Account-scoped watched import folders using existing authorized broker jobs.

The catalog remains private. Sources are never moved/deleted; copied originals
are deduplicated by the native importer. No broker restart or new disk authority.
"""
import json, secrets, threading, time
from . import accounts
from .nas.files import relative
_LOCKS={}
_LOCK=threading.Lock()
def lock(key):
    with _LOCK:return _LOCKS.setdefault(key,threading.RLock())

def context(gateway,kind,write=False):
    if kind not in ('radio','photos'):raise ValueError('Choose My Radio or Personal Photos')
    session=gateway.session()
    if not session or session['user']['must_change']:raise PermissionError('Sign in again')
    if gateway.share:raise PermissionError('Shared libraries are read-only')
    user=session['user'];owner=user['id']
    if gateway.managed:
        if user['role']!='administrator':raise PermissionError('Administrator access required')
        owner=gateway.managed
    needed=('myradio' if kind=='radio' else 'photos')+('.write' if write else '.read')
    if user['role']!='administrator' and not accounts.permitted(user,needed):raise PermissionError('Library permission not granted')
    # The existing gateway resolves managed accounts, disabled accounts, storage
    # assignments and encrypted-volume ownership independently on every call.
    status=gateway._request('myradio.status' if kind=='radio' else 'photos.status',{})
    return owner,status

class Sources:
    def __init__(self,gateway,kind):
        self.g=gateway;self.kind=kind;self.owner,self.library=context(gateway,kind)
        self.key='library-sources:'+self.owner+':'+kind
    def config(self):return self.g.state.setting(self.key,{'enabled':False,'interval_minutes':15,'sources':[]})
    def run(self):return self.g.state.setting(self.key+':run',{'state':'idle'})
    def put_run(self,value):self.g.state.set(self.key+':run',{**value,'updated':time.time()})
    def suggestions(self):
        rows=[]
        for kind,op,share in [('radio','myradio.status','my-radio'),('photos','photos.status','my-photos'),('files','library.files-status','my-files')]:
            try:
                cfg=(self.library if kind==self.kind else self.g._request(op,{})).get('config') or {}
                if not cfg.get('location_selected'):continue
                folders=[('Music','music'),('Books','books'),('Podcasts','podcasts')] if kind=='radio' else [('Imports','photos')] if kind=='photos' else [('',None)]
                existing=self.g._request('files.list',{'share':share,'path':'','limit':1000}).get('entries',[])
                folders=[(next((e['name'] for e in existing if e.get('directory') and not e.get('symlink') and e['name'].casefold()==path.casefold()),path),category) for path,category in folders]
                for path,category in folders:rows.append({'share':share,'path':path,'label':('My Radio' if kind=='radio' else 'Personal Photos' if kind=='photos' else 'Personal files')+(' / '+path if path else ''),'category':category,'pool':cfg['pool']})
            except (ValueError,PermissionError,OSError):continue
        return rows
    def status(self):
        return {'kind':self.kind,'config':self.config(),'run':{k:v for k,v in self.run().items() if k!='tasks'},'suggestions':self.suggestions(),'library_location':{k:self.library.get('config',{}).get(k) for k in ('pool','location_folder','location_selected')},'folder_setup':self.g.state.setting('library-folders-followup:'+self.owner,{}),'catalog_counts':self.library.get('counts',{}),'current_scanner':self.library.get('scanner',self.library.get('operation',{})),'copy_into_private_catalog':True,'online_metadata':'Local tags and embedded artwork are read on import. Internet title/cover lookups remain separately opt-in.'}
    def ensure(self):
        cfg=self.library.get('config') or {}
        if not cfg.get('location_selected'):raise ValueError('Choose and save the main library location first')
        share='my-radio' if self.kind=='radio' else 'my-photos'
        entries=[];offset=0
        while True:
            page=self.g._request('files.list',{'share':share,'path':'','offset':offset,'limit':1000});entries+=page['entries']
            if page.get('next_offset') is None:break
            offset=page['next_offset']
            if offset>10000:raise ValueError('Library root is too large to prepare default folders')
        for name in (('Music','Books','Podcasts') if self.kind=='radio' else ('Imports',)):
            found=next((r for r in entries if r['name'].casefold()==name.casefold()),None)
            if found:
                if not found.get('directory') or found.get('symlink'):raise ValueError('The required library folder name is occupied by a file or link')
            else:self.g._request('files.mkdir',{'share':share,'path':'','name':name})
    def expand(self,rows):
        # An artist/album tree is split before invoking the existing bounded
        # importer. This avoids sending an entire large collection as one job.
        from .nas.myradio import AUDIO,BOOKS
        tasks=[]
        for row in rows:
            entries=[];offset=0
            while True:
                page=self.g._request('files.list',{'share':row['share'],'path':row['path'],'offset':offset,'limit':1000});entries+=page['entries']
                if page.get('next_offset') is None:break
                offset=page['next_offset']
                if offset>10000:raise ValueError('Too many immediate source entries; use more specific scan folders')
            directories=[r for r in entries if r.get('directory') and not r.get('symlink')]
            loose=any(not r.get('directory') and not r.get('symlink') and __import__('pathlib').Path(r['name']).suffix.lower() in AUDIO|BOOKS for r in entries)
            if self.kind=='radio' and directories and not loose:
                tasks.extend({**row,'path':row['path'].rstrip('/')+'/'+r['name'] if row['path'] else r['name'],'label':row['label']+' / '+r['name']} for r in directories)
            else:tasks.append(row)
        if len(tasks)>10000:raise ValueError('Too many scan tasks; use more specific scan folders')
        return tasks
    def save(self,payload):
        context(self.g,self.kind,True)
        if set(payload)-{'kind','enabled','interval_minutes','sources'}:raise ValueError('Unknown scan-folder setting')
        interval=payload.get('interval_minutes',15);rows=payload.get('sources');enabled=payload.get('enabled',False)
        if type(enabled)is not bool or type(interval)is not int or not 5<=interval<=1440 or not isinstance(rows,list) or len(rows)>32:raise ValueError('Choose up to 32 folders and a scan interval of 5–1440 minutes')
        checked=[];seen=set()
        with lock(self.key):
            if self.run().get('state') in ('submitting','waiting-job','waiting-photo','running','uncertain','maintenance'):raise ValueError('A folder scan is active. Wait for it to finish before changing sources.')
            self.ensure()
            for row in rows:
                if not isinstance(row,dict) or set(row)-{'share','path','category','enabled','label','id'}:raise ValueError('Invalid source folder')
                share=row.get('share');path=row.get('path','');category=row.get('category','music') if self.kind=='radio' else 'photos'
                if not isinstance(share,str) or not share or type(row.get('enabled',True))is not bool or category not in ('music','books','podcasts','photos') or self.kind=='radio' and category=='photos':raise ValueError('Choose a drive, folder and collection')
                relative(path)
                if self.kind=='photos' and not path:raise ValueError('Choose a folder inside the photo source drive')
                key=(share,path,category)
                if key in seen:raise ValueError('This folder is already assigned to this collection')
                seen.add(key)
                self.g._request('files.list',{'share':share,'path':path,'limit':1})
                label=row.get('label') or share+' / '+path
                if not isinstance(label,str) or len(label)>500 or any(ord(c)<32 for c in label):raise ValueError('Invalid folder label')
                checked.append({'id':secrets.token_hex(8),'share':share,'path':path,'category':category,'enabled':row.get('enabled',True),'label':label})
            value={'enabled':enabled,'interval_minutes':interval,'sources':checked,'saved':time.time()}
            self.g.state.set(self.key,value);self.put_run({'state':'scheduled' if enabled else 'disabled','next':0,'requested':time.time()})
        return self.status()
    def request_scan(self):
        context(self.g,self.kind,True)
        with lock(self.key):
            if self.run().get('state') in ('submitting','waiting-job','waiting-photo','running','uncertain','maintenance'):raise ValueError('A scan is active or needs attention; check its status before starting another')
            if not any(r['enabled'] for r in self.config()['sources']):raise ValueError('Add and save at least one scan folder first')
            self.put_run({'state':'scheduled','next':0,'requested':time.time(),'manual':True})
        return self.status()
    def tick(self):
        with lock(self.key):
            cfg=self.config();run=self.run();state=run.get('state','idle')
            if state in ('uncertain','failed','maintenance'):return
            if state in ('idle','complete','disabled'):
                if not cfg['enabled'] or time.time()-run.get('finished',0)<cfg['interval_minutes']*60:return
                run={'state':'scheduled','next':0,'requested':time.time()}
            context(self.g,self.kind,True)
            # A previously recorded enqueue without a receipt is never replayed.
            if state=='submitting':self.put_run({**run,'state':'uncertain','message':'Submission receipt unavailable. Check Activity; no automatic retry.'});return
            if run.get('job_id'):
                jobs=self.g.jobs().get('jobs',[]);job=next((j for j in jobs if j['id']==run['job_id']),None)
                if not job:self.put_run({**run,'state':'uncertain','message':'Saved job is no longer in the recent job list. Check Activity.'});return
                if job['status'] in ('queued','running'):return
                if job['status']!='succeeded':self.put_run({**run,'state':'failed','message':'Import stopped; originals and prior catalog entries are retained. Check Activity.'});return
                run={k:v for k,v in run.items() if k!='job_id'};run['next']=run.get('next',0)+1
            if run.get('photo_pending'):
                if self.g._request('photos.icloud-status',{}).get('download_running'):return
                op=self.g._request('photos.status',{}).get('operation',{})
                if op.get('state')!='complete':self.put_run({**run,'state':'failed','message':'Photo import did not complete cleanly. Check Import & iCloud; originals are retained.'});return
                run.pop('photo_pending');run['next']=run.get('next',0)+1
            rows=run.get('tasks')
            if rows is not None and run.get('next',0)>=len(rows):self.put_run({'state':'complete','finished':time.time(),'folders':len(rows)});return
            if any(j['status'] in ('queued','running') for j in self.g._request('files.transfers',{}).get('transfers',[])):
                self.put_run({**run,'state':'waiting-transfers','message':'Waiting for your file transfers to finish. Partial staging is not scanned.'});return
            if self.kind=='radio' and not self.library.get('config',{}).get('scan_enabled'):
                self.put_run({**run,'state':'disabled','message':'My Radio folder scanning is disabled.'});return
            if self.kind=='photos' and self.g._request('photos.icloud-status',{}).get('download_running'):
                self.put_run({**run,'state':'waiting-photos','message':'Waiting for the current photo/iCloud import to finish.'});return
            if rows is None:
                rows=self.expand([r for r in cfg['sources'] if r['enabled'] and (self.kind!='radio' or self.library.get('config',{}).get('folders',{}).get(r['category'],True))]);run['tasks']=rows
                if not rows:self.put_run({'state':'complete','finished':time.time(),'folders':0});return
            row=rows[run.get('next',0)]
            self.g._request('files.list',{'share':row['share'],'path':row['path'],'limit':1})
            pending={**run,'state':'submitting','source':row['label']};self.put_run(pending)
            try:
                if self.kind=='radio':
                    result=self.g._request('myradio.import-folder',{'category':row['category'],'share':row['share'],'path':row['path']})
                    if not result.get('job_id'):raise ValueError('No import receipt')
                    self.put_run({**pending,'state':'waiting-job','job_id':result['job_id']})
                else:
                    result=self.g._request('photos.import-folder',{'share':row['share'],'folder':row['path']})
                    if not result.get('started'):raise ValueError('No photo import receipt')
                    self.put_run({**pending,'state':'waiting-photo','photo_pending':True})
            except Exception:
                self.put_run({**pending,'state':'uncertain','message':'The last submission may have reached the NAS. Check Activity; no automatic retry.'});raise

def handle(gateway,operation,payload):
    sources=Sources(gateway,payload.get('kind','radio'))
    if operation=='library.sources-status':return sources.status()
    if operation=='library.sources-save':return sources.save(payload)
    if operation=='library.sources-scan':return sources.request_scan()
    raise ValueError('Unknown scan-folder operation')

def tick_all(state,nas):
    from .personal_access import Gateway
    with state.connect() as db:
        keys=[r[0] for r in db.execute("SELECT key FROM settings WHERE key LIKE 'library-sources:%' AND key NOT LIKE '%:run'")]
    with state.connect() as db:
        pending=[(r[0],json.loads(r[1])) for r in db.execute("SELECT key,value FROM settings WHERE key LIKE 'library-folders-followup:%'")]
    for key,run in pending:
        if run.get('state')!='waiting-job':continue
        owner=key.split(':')[1]
        with state.connect() as db:row=db.execute('SELECT * FROM local_accounts WHERE id=? AND enabled=1',(owner,)).fetchone()
        if not row:continue
        user=dict(row);user['permissions']=json.loads(user['permissions']);g=Gateway(nas,state,lambda:{'user':user})
        try:
            job=next((j for j in g.jobs().get('jobs',[]) if j['id']==run['job_id']),None)
            if not job:raise ValueError('Library setup job receipt is unavailable')
            if job['status'] in ('queued','running'):continue
            if job['status']!='succeeded':raise ValueError('Library setup did not finish')
            result=json.loads(job['result']) if isinstance(job.get('result'),str) else job.get('result') or {}
            cfg=result.get('config',{});kind='radio' if cfg.get('library_id') else 'photos' if cfg.get('archive_id') else None
            if not kind:raise ValueError('Library setup did not provide a location identity')
            source=Sources(g,kind);live=source.library.get('config',{})
            if any(live.get(k)!=cfg.get(k) for k in ('pool','folder','filesystem_uuid')):raise ValueError('Library location changed again')
            source.ensure();state.set(key,{**run,'state':'complete','finished':time.time()})
        except (ValueError,PermissionError,OSError):state.set(key,{**run,'state':'needs-attention','message':'The main library is retained. Use Save scan folders to prepare its source folders.','updated':time.time()})
    for key in keys:
        _,owner,kind=key.split(':')
        with state.connect() as db:row=db.execute('SELECT * FROM local_accounts WHERE id=? AND enabled=1',(owner,)).fetchone()
        if not row:continue
        user=dict(row);user['permissions']=json.loads(user['permissions'])
        try:Sources(Gateway(nas,state,lambda:{'user':user}),kind).tick()
        except (ValueError,PermissionError,OSError,RuntimeError) as error:
            previous=state.setting(key+':run',{})
            if previous.get('state')!='uncertain':state.set(key+':run',{**previous,'state':'failed','message':'Source unavailable or access changed; check the folder and scan settings.','updated':time.time()})
