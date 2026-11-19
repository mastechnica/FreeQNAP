"""Bounded, same-site discovery of linked files; preview only, never a download job."""
import hashlib
import time
from collections import deque
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import urlsplit,urlunsplit,urljoin,urldefrag,unquote
from . import public_http

def origin(url):
 p=urlsplit(url);return (p.scheme,p.hostname,p.port or (443 if p.scheme=='https' else 80))

class Links(HTMLParser):
 def __init__(self):super().__init__();self.links=[];self.base=None
 def handle_starttag(self,tag,attrs):
  if tag=='base' and self.base is None and 'href' in dict(attrs):self.base=dict(attrs)['href']
  if tag=='a':
   a=dict(attrs)
   if a.get('href'):self.links.append(a['href'])

def discover(request,opener=None,clock=time.monotonic):
 if set(request)-{'url','depth','offset'}:raise ValueError('Choose a starting URL and link depth')
 offset=request.get('offset',0)
 if type(offset) is not int or offset<0:raise ValueError('Invalid preview offset')
 start=request.get('url');depth=request.get('depth',0)
 if type(depth)is not int or not 0<=depth<=5:raise ValueError('Link depth must be from 0 to 5')
 if not isinstance(start,str):raise ValueError('Enter a public HTTP(S) starting URL')
 start=urldefrag(start)[0];p=urlsplit(start)
 if p.scheme not in ('http','https') or not p.hostname or p.username is not None or p.password is not None:raise ValueError('Use a public HTTP(S) URL without a login')
 site=origin(start);prefix=p.path if p.path.endswith('/') else p.path.rsplit('/',1)[0]+'/'
 def in_scope(value):
  try:
   v=urlsplit(value);path=unquote(v.path)
   return origin(value)==site and not v.username and not v.password and path.startswith(unquote(prefix)) and '..' not in PurePosixPath(path).parts and '\\' not in path
  except ValueError:return False
 queue=deque([(start,0)]);seen=set();found=set();items=[];more=False;page_bytes=0;errors=0;pages=0;truncated=False;end=clock()+30
 def add_file(value):
  nonlocal more,page_bytes
  digest=hashlib.sha256(value.encode()).digest()
  if digest in found:return
  found.add(digest)
  if len(found)<=offset:return
  filename=unquote(urlsplit(value).path.rsplit('/',1)[-1]) or 'download'
  size=6*(len(value)+len(filename))+64
  if len(items)>=500 or (items and page_bytes+size>1024*1024):
   more=True;return
  items.append({'url':value,'name':filename});page_bytes+=size
 opener=opener or public_http.open_url
 while queue and len(seen)<100 and not more and clock()<end:
  current,level=queue.popleft()
  if current in seen or not in_scope(current):continue
  seen.add(current)
  try:
   with opener(current,timeout=max(.1,min(5,end-clock())),allowed_origin=site) as (response,resolved):
    if not in_scope(resolved):continue
    kind=(response.getheader('Content-Type') or '').split(';')[0].lower()
    if kind not in ('text/html','application/xhtml+xml'):
     add_file(resolved);continue
    if level>depth:continue
    raw=bytearray()
    while len(raw)<=1024*1024 and clock()<end:
     chunk=response.read1(min(65536,1024*1024+1-len(raw)))
     if not chunk:break
     raw.extend(chunk)
    if len(raw)>1024*1024 or clock()>=end:truncated=True;continue
    parser=Links();parser.feed(raw.decode('utf-8','replace'));pages+=1
    base=urldefrag(urljoin(resolved,parser.base))[0] if parser.base is not None else resolved
    if not in_scope(base):errors+=1;continue
    for href in parser.links:
     value=urldefrag(urljoin(base,href))[0]
     if not in_scope(value) or value in seen:continue
     path=urlsplit(value).path;suffix=PurePosixPath(path).suffix.lower()
     if suffix and suffix not in ('.html','.htm','.php','.asp','.aspx','.jsp') and not path.endswith('/'):
      add_file(value)
      if more:break
     elif level<depth or not path.endswith('/'):
      if len(queue)<5000:queue.append((value,level+1))
      else:truncated=True
  except (ValueError,OSError):
   if current==start:raise ValueError('Could not read the starting URL. Use a publicly accessible file listing without a login.') from None
   errors+=1
 truncated=truncated or bool(queue) or clock()>=end
 return {'source_page':start,'items':items,'next_offset':offset+len(items) if more else None,'depth':depth,'pages_scanned':pages,'failed_pages':errors,'truncated':truncated or more,'scope':'Same origin and starting folder only; linked files, without login cookies or JavaScript execution.','preview_only':True}
