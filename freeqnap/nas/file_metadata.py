"""Reviewed, non-destructive XMP edits. Never rewrites original photo/video bytes."""
import datetime,hashlib,json,math,os,re,secrets,stat,threading
from pathlib import Path
from xml.etree import ElementTree as ET
from .files import relative
from .personal_metadata import inspect
SLOTS=threading.BoundedSemaphore(2)
NS={'x':'adobe:ns:meta/','rdf':'http://www.w3.org/1999/02/22-rdf-syntax-ns#','dc':'http://purl.org/dc/elements/1.1/','exif':'http://ns.adobe.com/exif/1.0/','tiff':'http://ns.adobe.com/tiff/1.0/','aux':'http://ns.adobe.com/exif/1.0/aux/'}
for prefix,uri in NS.items():ET.register_namespace(prefix,uri)
FIELDS={'title':500,'description':5000,'creator':500,'copyright':500,'make':200,'camera':200,'lens':200}
TAGS={key:'{'+NS[ns]+'}'+tag for key,ns,tag in [('title','dc','title'),('description','dc','description'),('creator','dc','creator'),('copyright','dc','rights'),('tags','dc','subject'),('taken','exif','DateTimeOriginal'),('latitude','exif','GPSLatitude'),('longitude','exif','GPSLongitude'),('altitude','exif','GPSAltitude'),('make','tiff','Make'),('camera','tiff','Model'),('lens','aux','Lens')]}

def clean(value):
 if not isinstance(value,dict) or set(value)-set(TAGS):raise ValueError('Unknown metadata field')
 result={}
 for key,limit in FIELDS.items():
  v=value.get(key,'')
  if not isinstance(v,str) or len(v)>limit or any(ord(c)<32 and c not in '\n\t' for c in v):raise ValueError('Invalid '+key)
  result[key]=v.strip()
 date=value.get('taken') or None
 if date is not None:
  if not isinstance(date,str) or len(date)>40:raise ValueError('Enter an ISO capture date/time')
  try:date=datetime.datetime.fromisoformat(date.replace('Z','+00:00')).isoformat()
  except ValueError:raise ValueError('Enter an ISO capture date/time') from None
 result['taken']=date
 for key,low,high in [('latitude',-90,90),('longitude',-180,180),('altitude',-12000,100000)]:
  v=value.get(key)
  if v in ('',None):v=None
  if v is not None and (type(v) not in (int,float) or not math.isfinite(v) or not low<=v<=high):raise ValueError('Invalid '+key)
  result[key]=v
 if (result['latitude'] is None)!=(result['longitude'] is None):raise ValueError('Enter both latitude and longitude, or clear both')
 tags=value.get('tags',[])
 if not isinstance(tags,list) or len(tags)>64 or any(not isinstance(v,str) or len(v)>100 or any(ord(c)<32 for c in v) for v in tags):raise ValueError('Choose up to 64 short tags')
 result['tags']=list(dict.fromkeys(v.strip() for v in tags if v.strip()));return result

def raw_sidecar(parent,leaf):
 try:fd=os.open(leaf+'.xmp',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
 except FileNotFoundError:return b''
 try:
  info=os.fstat(fd)
  if not stat.S_ISREG(info.st_mode) or info.st_dev!=os.fstat(parent).st_dev or info.st_size>256*1024:raise ValueError('Sidecar is not a bounded regular file')
  return os.read(fd,256*1024+1)
 finally:os.close(fd)

def gps(value):
 v=value or ''
 try:return float(v)
 except ValueError:
  m=re.fullmatch(r'(\d+),(\d+(?:\.\d+)?)([NSEW])',v)
  if not m:raise ValueError('Unsupported XMP GPS coordinate')
  return (int(m[1])+float(m[2])/60)*(-1 if m[3] in 'SW' else 1)

def read_xmp(parent,leaf):
 raw=raw_sidecar(parent,leaf)
 if not raw:return {}
 if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('XMP entities are not supported')
 try:root=ET.fromstring(raw)
 except ET.ParseError:raise ValueError('Existing XMP is invalid; it was not overwritten') from None
 result={}
 for key,tag in TAGS.items():
  node=root.find('.//'+tag)
  if node is None:
   attribute=next((e.attrib[tag] for e in root.iter() if tag in e.attrib),None)
   if attribute is None:continue
   node=ET.Element(tag);node.text=attribute
  values=[v.text or '' for v in node.iter('{'+NS['rdf']+'}li')];value=values[0] if values else node.text or ''
  if key=='tags':result[key]=values
  elif key in ('latitude','longitude'):result[key]=gps(value) if value else None
  elif key=='altitude':
   try:
    result[key]=float(value.split('/')[0])/float(value.split('/')[1]) if '/' in value else float(value) if value else None
    ref=root.find('.//{'+NS['exif']+'}GPSAltitudeRef')
    if result[key] is not None and ref is not None and ref.text=='1':result[key]=-abs(result[key])
   except (ValueError,ZeroDivisionError):raise ValueError('Unsupported XMP altitude') from None
  elif key=='taken':result[key]=value or None
  else:result[key]=value
 return {k:v for k,v in clean(result).items() if k in result}

def etag(fd,raw,extra=None):
 i=os.fstat(fd);return hashlib.sha256(json.dumps([i.st_dev,i.st_ino,i.st_size,i.st_mtime_ns,hashlib.sha256(raw).hexdigest(),extra],sort_keys=True).encode()).hexdigest()

def current(fd,parent,leaf,extra=None):
 if not SLOTS.acquire(False):raise ValueError('Metadata reader is busy; try again shortly')
 try:
  before=os.fstat(fd);info=inspect(fd);after=os.fstat(fd)
  if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):raise ValueError('File changed during metadata reading')
  info.update(extra or {});info.update(read_xmp(parent,leaf));value=clean({k:v for k,v in info.items() if k in TAGS});raw=raw_sidecar(parent,leaf)
  return {'metadata':value,'etag':etag(fd,raw,extra),'technical':{k:v for k,v in info.items() if k in ('width','height','duration','metadata_unavailable')},'storage':'XMP sidecar; original embedded EXIF stays unchanged'}
 finally:SLOTS.release()

def write(parent,leaf,value,gid=None):
 value=clean(value);old=raw_sidecar(parent,leaf)
 if old:
  if b'<!DOCTYPE' in old.upper() or b'<!ENTITY' in old.upper():raise ValueError('XMP entities are not supported')
  try:root=ET.fromstring(old)
  except ET.ParseError:raise ValueError('Existing XMP is invalid; original retained') from None
 else:root=ET.Element('{'+NS['x']+'}xmpmeta');ET.SubElement(root,'{'+NS['rdf']+'}RDF')
 rdf=root.find('.//{'+NS['rdf']+'}RDF')
 if rdf is None:raise ValueError('Existing sidecar has no XMP RDF container')
 desc=rdf.find('{'+NS['rdf']+'}Description')
 if desc is None:desc=ET.SubElement(rdf,'{'+NS['rdf']+'}Description',{'{'+NS['rdf']+'}about':''})
 for key,tag in TAGS.items():
  for description in rdf.findall('{'+NS['rdf']+'}Description'):
   for node in list(description):
    if node.tag==tag:description.remove(node)
   description.attrib.pop(tag,None)
  node=ET.SubElement(desc,tag);v=value[key]
  if key in ('title','description','copyright'):
   alt=ET.SubElement(node,'{'+NS['rdf']+'}Alt');ET.SubElement(alt,'{'+NS['rdf']+'}li',{'{http://www.w3.org/XML/1998/namespace}lang':'x-default'}).text=v
  elif key in ('creator','tags'):
   seq=ET.SubElement(node,'{'+NS['rdf']+'}'+('Seq' if key=='creator' else 'Bag'))
   for part in ([v] if key=='creator' else v):ET.SubElement(seq,'{'+NS['rdf']+'}li').text=part
  elif key in ('latitude','longitude'):
   if v is not None:
    n=abs(v);node.text=str(int(n))+','+format((n-int(n))*60,'.8f')+('S' if v<0 and key=='latitude' else 'W' if v<0 else 'N' if key=='latitude' else 'E')
  elif key=='altitude':node.text=str(round(abs(v)*1000))+'/1000' if v is not None else ''
  else:node.text=str(v) if v is not None else ''
 for node in list(desc):
  if node.tag=='{'+NS['exif']+'}GPSAltitudeRef':desc.remove(node)
 ET.SubElement(desc,'{'+NS['exif']+'}GPSAltitudeRef').text='1' if value['altitude'] is not None and value['altitude']<0 else '0'
 raw=ET.tostring(root,encoding='utf-8',xml_declaration=True)
 if len(raw)>256*1024:raise ValueError('Metadata sidecar is too large')
 if old:
  backup='.freeqnap-xmp-backup-'+secrets.token_hex(16);out=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600,dir_fd=parent)
  try:
   with os.fdopen(out,'wb') as stream:stream.write(old);stream.flush();os.fsync(stream.fileno())
  except Exception:raise
 stage='.freeqnap-xmp-next-'+secrets.token_hex(16);out=os.open(stage,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600,dir_fd=parent)
 with os.fdopen(out,'wb') as stream:
  stream.write(raw);stream.flush();os.fsync(stream.fileno())
  if gid is not None:os.fchown(stream.fileno(),0,gid);os.fchmod(stream.fileno(),0o660)
 os.rename(stage,leaf+'.xmp',src_dir_fd=parent,dst_dir_fd=parent);os.fsync(parent)
 return {'saved':True,'original_unchanged':True,'sidecar':leaf+'.xmp','previous_sidecar_retained':bool(old)}

class FileMetadata:
 def __init__(self,ctx,files):self.ctx=ctx;self.files=files
 def read(self,r):
  parts=relative(r.get('path',''))
  if not parts:raise ValueError('Choose a photo or video')
  from ..media_http import kind
  if kind(parts[-1]) not in ('image','video'):raise ValueError('Metadata editor supports photos and videos')
  with self.files.directory(r['share'],str(Path(*parts[:-1]))) as (parent,share,_):
   fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
   try:
    if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_dev!=os.fstat(parent).st_dev:raise ValueError('Choose a regular media file')
    result=current(fd,parent,parts[-1]);result['read_only']=bool(share.get('read_only'));return result
   finally:os.close(fd)
 def plan(self,r):
  if set(r)!={'share','path','etag','metadata'}:raise ValueError('Choose a media file and metadata')
  self.files.writable(r['share']);fresh=self.read(r)
  if fresh['etag']!=r['etag']:raise ValueError('File or sidecar changed; reopen the editor')
  return self.ctx.plan('file-metadata',{'share':r['share'],'path':r['path'],'etag':r['etag'],'metadata':clean(r['metadata']),'review':'Save standard XMP beside the original. Original photo/video bytes and embedded EXIF remain unchanged; previous sidecar is retained.'},'SAVE FILE METADATA')
 def apply(self,r):
  with self.ctx.lock():
   path,plan=self.ctx.reviewed(r,'file-metadata');b=plan['body'];self.files.writable(b['share']);fresh=self.read(b)
   if fresh['etag']!=b['etag']:raise ValueError('File or sidecar changed after review')
   parts=relative(b['path'])
   with self.files.directory(b['share'],str(Path(*parts[:-1]))) as (parent,share,_):
    self.ctx.consume(path,plan);return write(parent,parts[-1],b['metadata'],share.get('gid'))
