"""Account-authorized final destinations; aria2 remains confined to private staging."""
import contextlib,hashlib,json,os,re,secrets,sqlite3,time
from pathlib import Path
from ..access_scope import current,using
from .fileops import FileManager
from .files import relative

class DownloadDestinations:
 def __init__(self,backend,console_database='/var/lib/freeqnap/state.sqlite3'):
  self.backend=backend;self.manager=backend.downloads;self.console_database=Path(console_database)
 def authorize(self,write=False):
  actor=current()
  if not isinstance(actor,str) or not re.fullmatch('user:[a-f0-9]{32}',actor):raise ValueError('Sign in with a NAS account to choose a destination')
  with contextlib.closing(sqlite3.connect(self.console_database.as_uri()+'?mode=ro',uri=True)) as db:
   db.row_factory=sqlite3.Row;user=db.execute('SELECT id,label,role,permissions,enabled FROM local_accounts WHERE id=?',(actor[5:],)).fetchone()
   if not user or not user['enabled']:raise ValueError('Account access is disabled')
   rights=json.loads(user['permissions'])
   if user['role']!='administrator' and ('downloads.use' not in rights or write and 'files.write' not in rights):raise ValueError('This account cannot save downloads to folders')
   assignment=db.execute('SELECT assignments FROM account_storage WHERE user_id=?',(user['id'],)).fetchone()
  scope=self.backend.personal.get(user['id'],user['label'])
  scope['ctx'].state.set('assigned-shares',json.loads(assignment[0]) if assignment else [])
  return user,scope
 def resolve(self,location):
  if not isinstance(location,dict) or set(location)-{'share','path'} or not isinstance(location.get('share'),str):raise ValueError('Choose a folder from your available locations')
  user,scope=self.authorize(True);request={'share':location['share'],'path':location.get('path','')}
  if user['role']=='administrator':return self.backend.files.destination(request)
  # This invokes the same own-folder/assigned-share, USB privacy, encrypted lease,
  # path, writable-volume and descriptor checks used by normal member file writes.
  return self.backend.personal.dispatch(scope,'files.destination',request)
 def descriptor(self,binding,token=None,available=True):
  return {'location':{k:binding[k] for k in ('share','path')},'label':binding['label'],'token':token,'available':available}
 def checked(self,binding):
  fresh=self.resolve({k:binding[k] for k in ('share','path')})
  if any(fresh[k]!=binding[k] for k in ('share','path','pool','filesystem_uuid','identity')):raise ValueError('The selected destination changed; choose it again')
  return fresh
 def selected(self):
  if not isinstance(current(),str) or not current().startswith('user:'):return None
  try:_,scope=self.authorize()
  except (ValueError,OSError,sqlite3.Error):return None
  token=scope['ctx'].state.setting('downloads-destination-selection')
  record=scope['ctx'].state.setting('downloads-destinations',{}).get(token)
  if not record:return None
  try:self.checked(record['binding']);available=True
  except (ValueError,OSError):available=False
  return self.descriptor(record['binding'],token,available)
 def binding(self,request):
  if 'save_to' not in request:
   if isinstance(current(),str) and current().startswith('user:'):
    _,scope=self.authorize();token=scope['ctx'].state.setting('downloads-destination-selection')
   else:token=None
  else:token=request['save_to']
  if token is None:return None
  if not isinstance(token,str) or not re.fullmatch('[a-f0-9]{32}',token):raise ValueError('Use a destination selected by this account')
  _,scope=self.authorize(True);record=scope['ctx'].state.setting('downloads-destinations',{}).get(token)
  if not record:raise ValueError('Destination selection is unavailable; choose it again')
  self.checked(record['binding']);return record['binding']
 def choose(self,request):
  if set(request)-{'save_to','id','temporary'} or 'save_to' not in request:raise ValueError('Choose a destination for new downloads or one of your jobs')
  temporary=request.get('temporary',False)
  if type(temporary)is not bool or 'temporary' in request and 'id' in request:raise ValueError('Choose a temporary selection or an existing job, not both')
  _,scope=self.authorize();binding=self.resolve(request['save_to']) if request['save_to'] is not None else None
  if 'id' in request:
   if not isinstance(request['id'],str) or not re.fullmatch('[a-f0-9]{32}',request['id']):raise ValueError('Choose one of your download jobs')
   with self.manager.ctx.lock():
    rows=self.manager.jobs();row=rows.get(request['id'])
    if not row or row.get('actor')!=current():raise ValueError('Download not available to this account')
    if (row.get('delivery') or {}).get('state')=='copying':raise ValueError('Wait for the current save operation to finish')
    if (row.get('delivery') or {}).get('state')=='delivered':raise ValueError('This download has already been saved; its files were retained')
    row['save_to']=binding;row['delivery']={'state':'pending'} if binding else None;self.manager.ctx.state.set('downloads_jobs',rows)
   return {'saved':True,'job_id':row['id'],'destination':self.descriptor(binding) if binding else None}
  with self.manager.ctx.lock():
   state=scope['ctx'].state;records=state.setting('downloads-destinations',{});token=None
   if binding:
    token=secrets.token_hex(16);records[token]={'binding':binding,'created':time.time()}
    selected=state.setting('downloads-destination-selection');pinned=records.get(selected) if temporary else None
    records=dict(sorted(records.items(),key=lambda item:item[1]['created'],reverse=True)[:32])
    if pinned and selected not in records:
     records.pop(next(reversed(records)));records[selected]=pinned
   state.set('downloads-destinations',records)
   if not temporary:state.set('downloads-destination-selection',token)
  return {'saved':True,'temporary':temporary,'destination':self.descriptor(binding,token) if binding else None}
 def update(self,ident,value):
  with self.manager.ctx.lock():
   for key in ('downloads_jobs','downloads_retained_files'):
    rows=self.manager.ctx.state.setting(key,{})
    if ident in rows:rows[ident]['delivery']=value;self.manager.ctx.state.set(key,rows);return
 def recover(self):
  for row in [*self.manager.jobs().values(),*self.manager.ctx.state.setting('downloads_retained_files',{}).values()]:
   if (row.get('delivery') or {}).get('state')=='copying':self.update(row['id'],{'state':'needs-attention','message':'Saving was interrupted. Private files and any published copies were retained; inspect them before choosing a destination again.'})
 def view(self,row,scope):
  owner=self;manager=self.manager;binding=row['save_to'];ident=row['id'];alias='download:'+ident
  class DeliveryContext:
   def __init__(self):self.base=scope['ctx'].base;self.last_operation=None
   def __getattr__(self,key):return getattr(scope['ctx'],key)
   def operation(self,kind,payload):
    operation=secrets.token_hex(16);now=time.time()
    with self.state.connect() as db:
     db.execute('BEGIN IMMEDIATE')
     if db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]>=128:raise ValueError('Account job capacity reached')
     db.execute('INSERT INTO jobs(id,kind,payload,status,created,updated,attempts) VALUES(?,?,?,?,?,?,1)',(operation,'download-delivery',json.dumps(payload),'running',now,now));db.execute('INSERT INTO job_principals VALUES(?,?)',(operation,current()))
    self.last_operation=operation;owner.update(ident,{'state':'copying','operation_id':operation});return operation
  context=DeliveryContext()
  def checked_target():
   live=manager.jobs().get(ident)
   if not live or live.get('actor')!=current() or live.get('desired')!='running' or live.get('save_to')!=binding:raise ValueError('Download access or destination changed')
   owner.checked(binding);user,fresh_scope=owner.authorize(True)
   return owner.backend.files if user['role']=='administrator' else fresh_scope['files']
  class View(FileManager):
   def writable(self,share):
    if share!=binding['share']:raise ValueError('Destination does not match this download')
    return checked_target().writable(share)
   def mapping(self,share):
    if share==alias:
     base=manager.target(row['destination']);return {'name':alias,'path':str(base),'pool':row['destination']['pool'],'read_only':True,'gid':os.getegid()}
    return checked_target().mapping(share)
   @contextlib.contextmanager
   def directory(self,share,path=''):
    if share!=alias:
     files=checked_target()
     if share!=binding['share'] or path not in ('',binding['path']):raise ValueError('Destination path changed')
     with files.directory(share,path) as value:yield value
     return
    if row.get('actor')!=current():raise ValueError('Download belongs to another account')
    parts=relative(path);source=self.mapping(share)
    if not parts:
     base=manager.target(row['destination']);fd=os.open(base,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
     try:yield fd,source,manager.ctx.volume(row['destination']['pool'])[0]
     finally:os.close(fd)
    elif parts==(ident,):
     with manager.file_view({'id':ident}).directory('download','') as (fd,_,pool):yield fd,source,pool
    else:raise ValueError('Source path is outside this download')
  return View(context)
 def one(self):
  for candidate in sorted(self.manager.jobs().values(),key=lambda row:row['created']):
   if candidate.get('state')!='complete' or candidate.get('desired')!='running' or not candidate.get('save_to') or (candidate.get('delivery') or {}).get('state')!='pending':continue
   ident=candidate['id'];view=None
   try:
    with self.manager.ctx.lock():
     rows=self.manager.jobs();row=rows.get(ident)
     if not row or (row.get('delivery') or {}).get('state')!='pending':continue
     row['delivery']={'state':'copying'};self.manager.ctx.state.set('downloads_jobs',rows)
    with using(row['actor']):
     _,scope=self.authorize(True);self.checked(row['save_to']);view=self.view(row,scope)
     with self.manager.file_view({'id':ident}).directory('download','') as (fd,_,_):names=sorted(name for name in os.listdir(fd) if not name.endswith('.aria2'))
     if not names:raise ValueError('No completed files are available to save')
     request={'share':'download:'+ident,'paths':[ident+'/'+name for name in names] if len(names)<=200 else [ident],'target_share':row['save_to']['share'],'target_path':row['save_to']['path'],'mode':'copy'}
     if len(names)>200:request['new_name']='Download-'+ident[:8]
     plan=view.transfer_plan(request);result=view.transfer({'plan_id':plan['id'],'digest':plan['digest'],'confirmation':plan['confirmation']})
     self.update(ident,{'state':'delivered','operation_id':view.ctx.last_operation,'published':result['published'],'finished_at':time.time()})
   except Exception:
    if view and view.ctx.last_operation:view.ctx.state.finish(view.ctx.last_operation,error='Saving the download failed; private downloads, published files and any staging were retained. Review destination access before trying again.')
    self.update(ident,{'state':'needs-attention','message':'Could not save to the chosen folder. Check current access, volume availability and conflicting filenames. Private downloads and any published copies were retained.'})
   return True
  return False
