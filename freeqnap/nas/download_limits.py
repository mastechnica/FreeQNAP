"""Account queue limits layered beneath the administrator's engine limits."""
import re,os,secrets,time
from pathlib import Path
from ..access_scope import current
def write_config(path,text):
 path.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
 old=path.stat() if path.exists() else None;temp=path.with_name(path.name+'.'+secrets.token_hex(8)+'.next')
 try:
  fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,old.st_mode&0o777 if old else 0o644)
  with os.fdopen(fd,'w') as stream:
   if old and os.geteuid()==0:os.fchown(stream.fileno(),old.st_uid,old.st_gid)
   stream.write(text);stream.flush();os.fsync(stream.fileno())
  os.replace(temp,path)
  fd=os.open(path.parent,os.O_RDONLY)
  try:os.fsync(fd)
  finally:os.close(fd)
 finally:
  if temp.exists():temp.unlink()


DEFAULT={'concurrent':0,'download_kib':0}
def actor():
 value=current()
 if not isinstance(value,str) or not re.fullmatch('user:[a-f0-9]{32}',value):raise ValueError('Sign in with a NAS account to set download limits')
 return value

def selected(manager):
 return manager.ctx.state.setting('downloads_account_limits',{}).get(current(),dict(DEFAULT))

def save(manager,request):
 if set(request)!={'scope','concurrent','download_kib'} or request['scope'] not in ('account','global'):raise ValueError('Choose account or global download limits')
 options={}
 for key,maximum in (('concurrent',512),('download_kib',1000000)):
  value=request[key]
  if type(value)is not int or not 0<=value<=maximum:raise ValueError('Invalid '+key)
  options[key]=value
 who=actor()
 if not manager.destinations:raise ValueError('Account authorization is unavailable')
 user,_=manager.destinations.authorize()
 if request['scope']=='global' and user['role']!='administrator':raise ValueError('Global download limits require an administrator')
 with manager.ctx.lock():
  if request['scope']=='account':
   rows=manager.ctx.state.setting('downloads_account_limits',{});rows[who]=options;manager.ctx.state.set('downloads_account_limits',rows)
   return {'saved':True,'scope':'account','limits':options}
  old=manager.settings()
  if not old:raise ValueError('An administrator must configure Downloads first')
  manager.target(old)
  updated={**old,'options':{**old['options'],**options}}
  def rpc_options(value):return {'max-concurrent-downloads':str(value['concurrent'] or 512),'max-overall-download-limit':str(value['download_kib'])+'K'}
  conf=getattr(manager,'limits_drop',Path('/etc/systemd/system/freeqnap-downloads.service.d/limits.conf'));previous=conf.read_text() if conf.exists() else None
  text='[Service]\nExecStart=\nExecStart=/usr/bin/aria2c --conf-path=/var/lib/freeqnap-downloads/aria2.conf --max-concurrent-downloads='+str(options['concurrent'] or 512)+' --max-overall-download-limit='+str(options['download_kib'])+'K\n'
  # Live RPC does not restart the engine. A fixed-argument service override makes
  # the same caps survive restart without writing the engine's private directory.
  manager.rpc('changeGlobalOption',[rpc_options(options)])
  try:
   write_config(conf,text);manager.ctx.run('systemctl','daemon-reload');manager.ctx.state.set('downloads_settings',updated)
  except Exception:
   if previous is None:conf.unlink(missing_ok=True)
   else:write_config(conf,previous)
   manager.rpc('changeGlobalOption',[rpc_options(old['options'])]);manager.ctx.run('systemctl','daemon-reload');raise
  return {'saved':True,'scope':'global','limits':options,'engine_restarted':False}

def plan(manager):
 limits=manager.ctx.state.setting('downloads_account_limits',{});jobs=manager.jobs();result={}
 for who,options in limits.items():
  rows=sorted((r for r in jobs.values() if r.get('actor')==who and r.get('state')!='complete' and r.get('desired')=='running' and not r.get('recovery_required') and not r.get('attention_required') and not (r.get('state') in ('error','removed') and r.get('next_retry',0)>time.time())),key=lambda r:(r.get('created',0),r['id']))
  slots=options['concurrent'] or len(rows)
  if options['download_kib']:
   # aria2 interprets a per-transfer rate of zero as unlimited.
   slots=min(slots,options['download_kib']*1024)
  allowed=rows[:slots]
  rate=options['download_kib']*1024//max(1,len(allowed)) if options['download_kib'] else 0
  permitted={r['id'] for r in allowed}
  for row in jobs.values():
   if row.get('actor')==who:result[row['id']]={'run':row['id'] in permitted,'rate':rate}
 return result

def enforce(manager,decisions):
 if not decisions:return
 # tellWaiting includes paused entries. Only active/waiting GIDs can be paused.
 statuses=manager.rpc('tellActive',[['gid','status']])
 offset=0
 while True:
  page=manager.rpc('tellWaiting',[offset,256,['gid','status']])
  statuses.extend(page)
  if len(page)<256:break
  offset+=len(page)
 active={row['gid'] for row in statuses if row.get('status') in ('active','waiting')};jobs=manager.jobs()
 def change(row,method,params):
  try:manager.rpc(method,params)
  except ValueError:
   # Transfers can finish or change state after the queue snapshot. Harmless
   # state races must not prevent later jobs from reconciling or being delivered.
   fresh=manager.rpc('tellStatus',[row['gid'],['status']])
   if fresh is not None and fresh.get('status') not in ('paused','complete','error','removed'):raise
 for ident,choice in decisions.items():
  row=jobs[ident]
  if row['gid'] in active and not choice['run']:change(row,'forcePause',[row['gid']])
 for ident,choice in decisions.items():
  row=jobs[ident]
  if row['gid'] in active and choice['run']:change(row,'changeOption',[row['gid'],{'max-download-limit':str(choice['rate'])}])
