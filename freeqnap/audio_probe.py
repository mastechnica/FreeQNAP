"""Read-only music tags/artwork in a bounded, unprivileged network namespace.

The parent passes open descriptors; the decoder receives no filesystem paths.
Mutagen and Pillow are optional distribution packages, never downloaded at runtime.
"""
import array,base64,ctypes,hashlib,io,json,os,pwd,resource,signal,socket,struct,warnings

def _read(s,n):
 out=b''
 while len(out)<n:
  raw=s.recv(n-len(out))
  if not raw:raise EOFError('Music metadata worker closed')
  out+=raw
 return out

def _text(v):
 if hasattr(v,'text'):v=v.text
 if hasattr(v,'value'):v=v.value
 if isinstance(v,(list,tuple)):return '; '.join(_text(x) for x in v)[:10000]
 return str(v)[:10000] if v is not None and not isinstance(v,bytes) else ''

def _worker(s):
 os.chdir('/');os.umask(0o077)
 for fd in range(3,1024):
  if fd!=s.fileno():
   try:os.close(fd)
   except OSError:pass
 libc=ctypes.CDLL(None,use_errno=True)
 if libc.unshare(0x40000000)!=0:raise OSError(ctypes.get_errno(),'Private decoder network unavailable')
 u=pwd.getpwnam('nobody');os.setgroups([]);os.setgid(u.pw_gid);os.setuid(u.pw_uid)
 if libc.prctl(38,1,0,0,0)!=0:raise OSError('Decoder restrictions unavailable')
 resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2));resource.setrlimit(resource.RLIMIT_FSIZE,(1024**2,1024**2));resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))
 import mutagen
 from PIL import Image,ImageOps
 Image.MAX_IMAGE_PIXELS=16*1024**2;warnings.simplefilter('error',Image.DecompressionBombWarning)
 cache={}
 def thumbnail(raw):
  if not 0<len(raw)<=8*1024**2:raise ValueError('Artwork exceeds local decoder limit')
  digest=hashlib.sha256(raw).hexdigest()
  if digest in cache:return cache[digest]
  with Image.open(io.BytesIO(raw)) as image:
   image.seek(0);image.thumbnail((384,384));image=ImageOps.exif_transpose(image).convert('RGB');out=io.BytesIO();image.save(out,'JPEG',quality=82);result=out.getvalue()
  if len(result)>256*1024:raise ValueError('Artwork exceeds thumbnail limit')
  if len(cache)>=64:cache.pop(next(iter(cache)))
  cache[digest]=result;return result
 def alarm(*_):raise TimeoutError('Metadata read time limit')
 signal.signal(signal.SIGALRM,alarm)
 while True:
  header,ancillary,_,_=s.recvmsg(4,socket.CMSG_SPACE(4))
  if not header:return
  if len(header)<4:header+=_read(s,4-len(header))
  length=struct.unpack('!I',header)[0]
  if length>1024:raise ValueError('Invalid metadata command')
  command=json.loads(_read(s,length));handles=[]
  for level,kind,data in ancillary:
   if level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS:
    a=array.array('i');a.frombytes(data[:len(data)//a.itemsize*a.itemsize]);handles.extend(a)
  if len(handles)!=1:raise ValueError('One source descriptor required')
  fd=handles[0];signal.alarm(5)
  try:
   with os.fdopen(fd,'rb') as stream:
    if command.get('kind')=='image':result={'cover':base64.b64encode(thumbnail(stream.read(8*1024**2+1))).decode()}
    else:
     if command.get('format')=='.flac':
      from mutagen.flac import FLAC
      obj=FLAC(stream)
     else:obj=mutagen.File(stream)
     tags=obj.tags if obj is not None and obj.tags else {};lower={k.lower():v for k,v in tags.items()};metadata={}
     keys={'title':['TIT2','©nam','title'],'artist':['TPE1','©ART','artist','Author'],'album':['TALB','©alb','album','WM/AlbumTitle'],'album_artist':['TPE2','aART','albumartist','album artist','WM/AlbumArtist'],'genre':['TCON','©gen','genre','WM/Genre'],'year':['TDRC','©day','date','year','WM/Year'],'track':['TRCK','tracknumber','WM/TrackNumber'],'disc':['TPOS','discnumber'],'composer':['TCOM','©wrt','composer','WM/Composer'],'description':['COMM::eng','©cmt','description','comment']}
     for key,names in keys.items():
      metadata[key]=next((_text(lower[n.lower()]).strip()[:10000 if key=='description' else 500] for n in names if n.lower() in lower),'')
     for source,dest in [('trkn','track'),('disk','disc')]:
      if source in tags and tags[source]:metadata[dest]='/'.join(str(x) for x in tags[source][0] if x)
     if obj is not None:
      info=obj.info;metadata['duration']=float(getattr(info,'length',0));metadata['codec']=type(obj).__module__.split('.')[-1]
     cover=None
     if obj is not None and getattr(obj,'pictures',None):
      pictures=sorted(obj.pictures,key=lambda p:p.type!=3);cover=pictures[0].data
     elif 'covr' in tags and tags['covr']:cover=bytes(tags['covr'][0])
     elif hasattr(tags,'getall'):
      pictures=sorted(tags.getall('APIC'),key=lambda p:p.type!=3)
      if pictures:cover=pictures[0].data
     result={'metadata':metadata,'recognized':obj is not None}
     if cover:
      try:result['cover']=base64.b64encode(thumbnail(cover)).decode()
      except Exception:result['artwork_error']=True
  except Exception as e:result={'error':type(e).__name__+': '+str(e)[:160]}
  finally:signal.alarm(0)
  raw=json.dumps(result,ensure_ascii=False).encode()
  if len(raw)>512*1024:raw=b'{"error":"Metadata output limit"}'
  s.sendall(struct.pack('!I',len(raw))+raw)

class Probe:
 def __enter__(self):
  self.parent,child=socket.socketpair();self.pid=os.fork()
  if self.pid==0:
   self.parent.close()
   try:_worker(child)
   finally:os._exit(0)
  child.close();self.parent.settimeout(12);return self
 def read(self,fd,kind='audio',format_hint=None):
  raw=json.dumps({'kind':kind,'format':format_hint}).encode();self.parent.sendmsg([struct.pack('!I',len(raw))],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[fd]))]);self.parent.sendall(raw)
  length=struct.unpack('!I',_read(self.parent,4))[0]
  if length>512*1024:raise ValueError('Metadata output limit')
  return json.loads(_read(self.parent,length))
 def __exit__(self,*_):
  self.parent.close();os.waitpid(self.pid,0)
