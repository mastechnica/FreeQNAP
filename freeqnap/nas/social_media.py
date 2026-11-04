"""Private, bounded sharing copies. No public links or external delivery."""
import base64,contextlib,hashlib,json,os,re,secrets,stat,threading,time
from pathlib import Path
from .files import relative
from .personal_metadata import decode
LIMIT=128*1024**2
WORKERS=threading.BoundedSemaphore(1)

class SocialMedia:
 def __init__(self,backend):self.backend=backend;self.root=backend.ctx.directory/'social-copies';self.root.mkdir(mode=0o700,exist_ok=True);self.records={};self.lock=threading.RLock()
 def cleanup(self):
  with self.lock:self._cleanup()
 def _cleanup(self):
  now=time.time()
  for p in self.root.iterdir():
   if re.fullmatch('[a-f0-9]{32}',p.name) and p.is_file() and not p.is_symlink() and p.stat().st_mtime<now-1200:p.unlink()
  self.records={k:v for k,v in self.records.items() if v['expires']>now}
 @contextlib.contextmanager
 def opened(self,r):
  b=self.backend;s=None if r['primary'] else b.personal.get(r['owner'])
  if s is not None:s['ctx'].state.set('assigned-shares',r.get('assignments',[]))
  source=r['source']
  if source['type']=='photos':
   photos=b.personal_photos if s is None else s['photos']
   with photos.opened(photos.asset(source['id'])) as fd:yield fd
  else:
   files=b.files if s is None else s['files'];parts=relative(source['path'])
   if not parts:raise ValueError('Choose a file')
   with files.directory(source['share'],str(Path(*parts[:-1]))) as (parent,_,_):
    fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
    try:
     st=os.fstat(fd)
     if not stat.S_ISREG(st.st_mode) or st.st_dev!=os.fstat(parent).st_dev:raise ValueError('Choose a regular media file')
     yield fd
    finally:os.close(fd)
 def prepare(self,r):
  if not WORKERS.acquire(False):raise ValueError('Another sharing copy is being prepared. Please wait.')
  try:
   with self.lock:
    self.cleanup()
    if len(self.records)>=8 or sum(v['recipient']==r['recipient'] for v in self.records.values())>=2:raise ValueError('Close or finish existing sharing copies first')
   with self.opened(r) as fd:
    before=os.fstat(fd)
    if before.st_size>LIMIT:raise ValueError('Sharing copies are limited to 128 MiB. Download larger originals instead.')
    worker=str(Path(__file__).with_name('social_worker.py'))
    raw=decode(fd,'python3',[worker,'/proc/self/fd/'+str(fd)],timeout=180,memory_limit=384*1024**2,output_limit=LIMIT+32)
    after=os.fstat(fd)
    if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):raise ValueError('Original changed during preparation')
   header,raw=raw.split(b'\n',1)
   if header not in (b'image/jpeg',b'video/mp4') or not 0<len(raw)<=LIMIT:raise ValueError('Sharing copy could not be verified')
   ident=secrets.token_hex(16);target=self.root/ident
   with target.open('xb') as stream:os.chmod(target,0o600);stream.write(raw)
   try:
    with target.open('rb') as stream:
     report=decode(stream.fileno(),'exiftool',['-json','-G1','-a','-n','-'],timeout=35,memory_limit=192*1024**2)
    verify_tags(report)
   except Exception:
    target.unlink(missing_ok=True);raise ValueError('Metadata removal could not be independently verified') from None
   value={'id':ident,'recipient':r['recipient'],'source':r['source'],'owner':r['owner'],'primary':r['primary'],'expires':time.time()+1200,'bytes':len(raw),'mime':header.decode(),'filename':'shared-photo.jpg' if header==b'image/jpeg' else 'shared-video.mp4','etag':hashlib.sha256(raw).hexdigest()}
   with self.lock:self.records[ident]=value
   return {k:v for k,v in value.items() if k not in ('recipient','source','owner','primary')}
  finally:WORKERS.release()
 def read(self,r):
  with self.lock:
   self.cleanup();v=self.records.get(r.get('id'))
   if not v or any(v[k]!=r[k] for k in ('recipient','source','owner','primary')):raise PermissionError('Sharing copy expired or unavailable')
   offset=r.get('offset',0);count=r.get('count',512*1024)
   if type(offset)!=int or offset<0 or type(count)!=int or not 1<=count<=512*1024:raise ValueError('Invalid sharing range')
   with (self.root/v['id']).open('rb') as stream:stream.seek(offset);data=stream.read(count)
   return {**{k:x for k,x in v.items() if k not in ('recipient','source','owner','primary')},'data_base64':base64.b64encode(data).decode()}
 def discard(self,r):
  with self.lock:
   v=self.records.get(r.get('id'))
   if v and v['recipient']==r['recipient']:(self.root/v['id']).unlink(missing_ok=True);self.records.pop(v['id'],None)
  return {'deleted':True}


def verify_tags(raw):
 rows=json.loads(raw,object_pairs_hook=lambda pairs:pairs)
 if not rows:raise ValueError('No metadata verification result')
 for key,value in rows[0]:
  group,_,tag=key.partition(':')
  if group in ('System','ExifTool') or value in ('',None,[],{}):continue
  if re.search(r'gps|location|latitude|longitude|make$|model$|serial|title|author|creator|artist|description|copyright|keyword|comment|identifier|owner|xmp|iptc|makernote',tag,re.I) or group.startswith(('XMP','IPTC','EXIF')):raise ValueError('Private metadata remains')
  if re.search(r'date|timeoriginal',tag,re.I):
   if str(value) not in ('0000:00:00 00:00:00','0','0000:00:00 00:00:00+00:00'):raise ValueError('Capture timestamps remain')
