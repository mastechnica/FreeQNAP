"""Bounded, no-follow background accounting. Never reads file contents."""
import os,stat,time,threading,re
from pathlib import Path
from ..access_scope import metadata
KINDS={'images':{'jpg','jpeg','png','heic','heif','webp','gif','tif','tiff','raw','dng'},'video':{'mp4','mov','mkv','avi','m4v','webm','mts'},'audio':{'mp3','m4a','m4b','flac','wav','ogg','aac','opus'},'books':{'epub','pdf','txt','docx','azw','azw3','kpf'}}
def measure(root,seen=None,seconds=10,limit=100000):
 seen=seen if seen is not None else set();result={'bytes':0,'allocated_bytes':0,'files':0,'types':{},'complete':True};started=time.monotonic();count=0
 def walk(fd,device):
  nonlocal count
  with os.scandir(fd) as entries:
   for item in entries:
    count+=1
    if count>limit or time.monotonic()-started>seconds:result['complete']=False;return
    try:
     info=item.stat(follow_symlinks=False)
     if info.st_dev!=device or stat.S_ISLNK(info.st_mode):continue
     if stat.S_ISDIR(info.st_mode):
      child=os.open(item.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
      try:walk(child,device)
      finally:os.close(child)
     elif stat.S_ISREG(info.st_mode) and (info.st_dev,info.st_ino) not in seen:
      seen.add((info.st_dev,info.st_ino));kind=next((k for k,v in KINDS.items() if item.name.rsplit('.',1)[-1].lower() in v),'other');result['types'][kind]=result['types'].get(kind,0)+info.st_size;result['bytes']+=info.st_size;result['allocated_bytes']+=getattr(info,'st_blocks',0)*512;result['files']+=1
    except OSError:result['complete']=False
    if not result['complete'] and (count>limit or time.monotonic()-started>seconds):return
 fd=os.dup(root) if isinstance(root,int) else os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:walk(fd,os.fstat(fd).st_dev)
 finally:os.close(fd)
 return result
class Usage:
 def __init__(self,backend):self.backend=backend;self.ctx=backend.ctx;self.lock=threading.Lock()
 def status(self,r):
  if set(r)-{'users','refresh'}:raise ValueError('Invalid usage request')
  users=r.get('users',[])
  if not isinstance(users,list) or len(users)>32:raise ValueError('Invalid user list')
  if any(not isinstance(v,dict) or set(v)-{'id','primary_admin'} or not re.fullmatch('[a-f0-9]{32}',str(v.get('id',''))) for v in users):raise ValueError('Invalid account identity')
  if r.get('refresh') and self.lock.acquire(False):threading.Thread(target=self.run,args=(users,),daemon=True).start()
  return {'running':self.lock.locked(),'snapshot':self.ctx.state.setting('user-usage',{}),'scope':'Logical file sizes and allocated bytes in configured personal locations. Shared media is separate; hard links count once in each scan. Unavailable or partially scanned locations are never reported as verified zero. No quotas are enforced.'}
 def run(self,users):
  try:
   results=[]
   for user in users:
    owner=user['id'];scope=self.backend.ctx if user.get('primary_admin') else self.backend.personal.get(owner)['ctx'];seen=set();sections=[]
    for key,label in [('personal-photos','Personal Photos & Videos'),('myradio','My Radio'),('personal-files','Personal files')]:
     cfg=scope.state.setting(key,{})
     if not cfg.get('location_selected'):sections.append({'section':label,'state':'not-configured'});continue
     for index,location in enumerate([cfg]+cfg.get('previous_locations',[])):
      row={'section':label+(' · retained previous location' if index else ''),'state':'unavailable'}
      try:
       with metadata():pool,mount=self.ctx.volume(location['pool'])
       if pool['filesystem_uuid']!=location['filesystem_uuid']:raise ValueError('Identity changed')
       parts=Path(location.get('location_folder') or location['folder']).parts
       if Path(*parts).is_absolute() or '..' in parts:raise ValueError('Invalid location')
       # Open every component without following links, including intermediate ones.
       fd=os.open(mount,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
       try:
        device=os.fstat(fd).st_dev
        for part in parts:
         nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=nxt
         if os.fstat(fd).st_dev!=device:raise ValueError('Nested filesystem')
        stats=measure(fd,seen)
       finally:os.close(fd)
       row.update(stats,state='complete' if stats['complete'] else 'partial')
      except (OSError,ValueError,KeyError):pass
      sections.append(row)
    results.append({'id':owner,'sections':sections})
   shared=[];seen=set()
   for library in self.ctx.config()['libraries'].values():
    row={'section':'Media Library · '+library['name'],'state':'unavailable'}
    try:
     with metadata():pool,mount=self.ctx.volume(library['pool'])
     if pool['filesystem_uuid']!=library['filesystem_uuid']:raise ValueError('Identity changed')
     parts=Path(library['path']).relative_to(mount).parts
     fd=os.open(mount,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
     try:
      device=os.fstat(fd).st_dev
      for part in parts:
       nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=nxt
       if os.fstat(fd).st_dev!=device:raise ValueError('Nested filesystem')
      stats=measure(fd,seen)
     finally:os.close(fd)
     row.update(stats,state='complete' if stats['complete'] else 'partial')
    except (OSError,ValueError,KeyError):pass
    shared.append(row)
   self.ctx.state.set('user-usage',{'at':time.time(),'users':results,'shared_media':shared})
  except Exception:
   previous=self.ctx.state.setting('user-usage',{});self.ctx.state.set('user-usage',{**previous,'error':'Storage accounting could not complete; last verified report retained'})
  finally:self.lock.release()
