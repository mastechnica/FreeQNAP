"""Narrow album-only companion. Uses temporary copies of saved Apple sessions."""
import contextlib,fcntl,json,logging,os,re,shutil,sqlite3,stat,subprocess,tempfile,time
from pathlib import Path
from .common import Context
from .personal import PersonalContext
from .personal_photos import PersonalPhotos,digest
from .icloud_albums import sync,attach_available
from ..access_scope import using

CONSOLE=Path('/var/lib/freeqnap')

def saved(db,key,default):
 row=db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone();return json.loads(row[0]) if row else default

def publish(owner,value):
 # Never write the console ledger as root.
 code="import json,sys;from freeqnap.state import State;r=json.load(sys.stdin);State('/var/lib/freeqnap').set('photos-albums-status:'+r['owner'],r['value'])"
 subprocess.run(['runuser','-u','freeqnap','--','/usr/bin/python3','-c',code],input=json.dumps({'owner':owner,'value':value}),text=True,check=True,stdout=subprocess.DEVNULL)

def session_copy(source,target):
 if not source.is_dir() or source.is_symlink():raise ValueError('Saved session unavailable')
 total=0;count=0
 for parent,dirs,files in os.walk(source,followlinks=False):
  if any((Path(parent)/d).is_symlink() for d in dirs):raise ValueError('Session link refused')
  dest=target/Path(parent).relative_to(source);dest.mkdir(mode=0o700,parents=True,exist_ok=True)
  for name in files:
   original=Path(parent)/name;fd=os.open(original,os.O_RDONLY|os.O_NOFOLLOW)
   try:
    info=os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_size>2*1024**2:raise ValueError('Invalid session file')
    total+=info.st_size;count+=1
    if total>16*1024**2 or count>64:raise ValueError('Session copy limit')
    out=os.open(dest/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(out,'wb') as f:
     while True:
      raw=os.read(fd,65536)
      if not raw:break
      f.write(raw)
   finally:os.close(fd)

def run():
 os.umask(0o077);lock=Path('/run/freeqnap/icloud-albums.lock');lock.parent.mkdir(mode=0o750,parents=True,exist_ok=True)
 with lock.open('a') as guard:
  try:fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:return
  with sqlite3.connect('file:'+str(CONSOLE/'state.sqlite3')+'?mode=ro',uri=True) as db:
   db.row_factory=sqlite3.Row
   users=[dict(v) for v in db.execute('SELECT id,role,permissions,enabled,must_change,primary_admin FROM local_accounts')]
   rows=[]
   for user in users:
    rights=json.loads(user['permissions']);owner=user['id'];cfg=saved(db,'photos-albums-config:'+owner,{'enabled':False,'interval_hours':6})
    if not user['enabled'] or user['must_change'] or not cfg.get('enabled') or user['role']!='administrator' and not {'photos.read','photos.write','photos.icloud'}<=set(rights):continue
    if not re.fullmatch('[a-f0-9]{32}',owner):continue
    rows.append((user,cfg,saved(db,'photos-albums-request:'+owner,{}),saved(db,'photos-albums-status:'+owner,{})))
  base=Context()
  for user,cfg,request,previous in rows:
   owner=user['id'];ctx=base if user['primary_admin'] else PersonalContext(base,owner);cloud=ctx.state.setting('personal-icloud',{});account=cloud.get('account','');photo_cfg=ctx.state.setting('personal-photos',{})
   if not account or not photo_cfg.get('location_selected'):continue
   photos=PersonalPhotos(ctx);now=time.time();nonce=request.get('id');requested=bool(nonce and nonce!=previous.get('request_id'));interval=cfg.get('interval_hours',6)
   if type(interval)is not int or not 1<=interval<=24:interval=6
   with using('user:'+owner):
    phase='archive-identity'
    try:
     with photos.root():pass
     phase='local-membership'
     linked=attach_available(ctx.state)
     if not requested and now-previous.get('finished',0)<interval*3600:
      if any(previous.get(k)!=v for k,v in linked.items()):publish(owner,{**previous,**linked})
      continue
     state={'state':'running','started':now,'request_id':nonce,'message':'Reading iCloud album memberships. Originals and existing albums are retained.','retention':'add-only'};publish(owner,state);last=[0]
     def progress(stats):
      if time.monotonic()-last[0]>=5:publish(owner,{**state,**stats});last[0]=time.monotonic()
     # The active downloader's cookie directory is never used as this client's
     # writable session store. Temporary credentials are removed after this pass.
     phase='saved-session'
     source=ctx.directory/'personal-icloud-sessions'/digest(account)
     with tempfile.TemporaryDirectory(prefix='freeqnap-album-session-') as temp:
      session_copy(source,Path(temp))
      for name in ('pyicloud_ipd','icloudpd'):
       logger=logging.getLogger(name);logger.setLevel(logging.CRITICAL+1);logger.propagate=False
      from pyicloud_ipd.base import PyiCloudService
      api=PyiCloudService('com',account,lambda:None,None,cookie_directory=temp)
      if api.requires_2fa or getattr(api,'requires_2sa',False):raise PermissionError('Saved session needs user verification')
      phase='remote-albums'
      result=sync(photos,account,api.photos,progress=progress)
     publish(owner,{**state,**result,'finished':time.time(),'state':'complete-with-errors' if result['failed_albums'] else 'complete','message':(str(result['failed_albums'])+' album(s) need another pass; existing memberships are retained. Other albums imported.' if result['failed_albums'] else 'Album memberships imported. Photos still downloading will be attached automatically.')})
    except Exception as error:
     # Connector exception strings may contain account details or signed URLs.
     publish(owner,{**previous,'finished':time.time(),'request_id':nonce,'state':'needs-attention','phase':phase,'error_type':type(error).__name__,'message':{'archive-identity':'The photo archive is unavailable or its identity check failed. Check storage before retrying album import.','local-membership':'The local album index is unavailable. Existing albums are retained.','saved-session':'Saved iCloud sign-in could not be used for album import. Check saved sign-in, then retry.','remote-albums':'iCloud albums could not be read. Existing memberships are retained. Check the connection or Apple sign-in, then retry.'}[phase]})
if __name__=='__main__':run()
