"""Local music tags and bounded, read-only text extraction for personal books."""
import html.parser
import io
import json
import math
import os
import re
import struct
import pwd
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET
from .personal_metadata import decode,managed_decoder,managed_decode

AUDIO = {'.mp3','.m4a','.m4b','.aac','.flac','.ogg','.opus','.wav','.aiff','.aif','.wma','.ape'}
BOOKS = {'.epub','.pdf','.txt','.docx','.azw','.azw3','.mobi','.kpf','.aax'}
MAX_TEXT = 8 * 1024**2

class PlainText(html.parser.HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.parts=[];self.hidden=0
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style'):self.hidden+=1
        if tag in ('p','br','div','h1','h2','h3','li'):self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script','style') and self.hidden:self.hidden-=1
    def handle_data(self, value):
        if not self.hidden:self.parts.append(value)

def plain(value):
    parser=PlainText();parser.feed(value[:MAX_TEXT]);return re.sub(r'\n[ \t]*\n[ \t]*\n+', '\n\n', ''.join(parser.parts)).strip()[:MAX_TEXT]

def xml(raw):
    if len(raw)>MAX_TEXT or b'<!DOCTYPE' in raw.replace(b'\x00',b'').upper() or b'<!ENTITY' in raw.replace(b'\x00',b'').upper():raise ValueError('Book XML is too large or contains an unsafe declaration')
    return ET.fromstring(raw)

@__import__('contextlib').contextmanager
def book_zip(fd):
    size=os.fstat(fd).st_size
    tail=os.pread(fd,min(size,65557),max(0,size-65557));offset=tail.rfind(b'PK\x05\x06')
    if offset<0 or len(tail)-offset<22:raise ValueError('Invalid book ZIP directory')
    record=struct.unpack_from('<4s4H2LH',tail,offset)
    if record[1] or record[2] or record[3]!=record[4] or record[4]>5000 or record[5]>2*1024**2 or record[6]+record[5]>size:
        raise ValueError('Book ZIP directory exceeds safe limits')
    try:
        with os.fdopen(os.dup(fd),'rb') as stream,zipfile.ZipFile(stream) as archive:yield archive
    except (zipfile.BadZipFile,RuntimeError) as error:raise ValueError('This book archive is invalid or encrypted') from error

def mobi_text(fd):
    """Use Debian's external libmobi tool on a private, disposable input copy."""
    executable=shutil.which('mobitool')
    if not executable:raise ValueError('Install the optional libmobi-tools package to read DRM-free Kindle editions')
    size=os.fstat(fd).st_size
    if size>64*1024**2:raise ValueError('This Kindle book exceeds the 64 MB local conversion limit; use a readable companion')
    if managed_decoder():
        # The service manager drops UID before its set-ID syscall restrictions.
        # This worker handles only a disposable input copy inside PrivateTmp.
        worker="""import os,sys,tempfile,subprocess,stat
with tempfile.TemporaryDirectory() as work:
 os.chdir(work)
 with open('input.mobi','xb') as target:
  total=0
  while True:
   raw=os.read(0,1048576)
   if not raw:break
   total+=len(raw)
   if total>67108864:raise SystemExit(2)
   target.write(raw)
 r=subprocess.run([sys.argv[1],'-d','-o','.','input.mobi'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 if r.returncode:raise SystemExit(3)
 fd=os.open('input.rawml',os.O_RDONLY|os.O_NOFOLLOW)
 try:
  info=os.fstat(fd)
  if not stat.S_ISREG(info.st_mode) or info.st_size>8388608:raise SystemExit(4)
  while True:
   raw=os.read(fd,1048576)
   if not raw:break
   sys.stdout.buffer.write(raw)
 finally:os.close(fd)
"""
        raw=managed_decode(fd,shutil.which('python3'),['-c',worker,executable],40,256*1024**2)
        text=plain(raw.decode('utf-8',errors='replace'))
        if not text:raise ValueError('This Kindle edition did not contain readable text')
        return {'text':text,'chapters':[{'title':'Book','start':0}]}
    with tempfile.TemporaryDirectory(prefix='freeqnap-book-') as parent:
        folder=__import__('pathlib').Path(parent)/'work';folder.mkdir(mode=0o700)
        source=folder/'input.mobi'
        with source.open('xb') as stream:
            position=0
            while position<size:
                raw=os.pread(fd,min(1024**2,size-position),position)
                if not raw:raise ValueError('Short Kindle input read')
                stream.write(raw);position+=len(raw)
        prefix=[]
        if os.geteuid()==0:
            user=pwd.getpwnam('nobody');os.chown(folder,user.pw_uid,user.pw_gid);os.chown(source,user.pw_uid,user.pw_gid)
            if any(not shutil.which(k) for k in ('unshare','setpriv','prlimit')):raise ValueError('Book decoder isolation is unavailable')
            prefix=['unshare','--net','--pid','--fork','--mount-proc','--kill-child=KILL','--','setpriv','--reuid='+str(user.pw_uid),'--regid='+str(user.pw_gid),'--clear-groups','--no-new-privs']
        source.chmod(0o400);directory_fd=os.open(folder,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
        try:
            if shutil.which('prlimit'):prefix+=['prlimit','--as='+str(256*1024**2),'--cpu=30','--fsize='+str(MAX_TEXT),'--']
            program='import os,subprocess,sys;os.fchdir('+str(directory_fd)+');r=subprocess.run([sys.argv[1],"-d","-o",".","input.mobi"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);raise SystemExit(r.returncode)'
            process=subprocess.Popen(prefix+[shutil.which('python3'),'-c',program,executable],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,pass_fds=(directory_fd,))
            try:code=process.wait(timeout=40)
            except subprocess.TimeoutExpired:process.kill();process.wait();raise ValueError('Kindle conversion exceeded its time limit') from None
            if code:raise ValueError('This Kindle edition is encrypted, unsupported or damaged; use a readable companion')
            output=folder/'input.rawml'
            if output.is_symlink() or not output.is_file() or output.stat().st_size>MAX_TEXT:raise ValueError('Invalid Kindle conversion result')
            text=plain(output.read_bytes().decode('utf-8',errors='replace'))
            if not text:raise ValueError('This Kindle edition did not contain readable text')
            return {'text':text,'chapters':[{'title':'Book','start':0}]}
        finally:os.close(directory_fd)

def zip_member(archive, path):
    p=PurePosixPath(path)
    if p.is_absolute() or '..' in p.parts or '\\' in path:raise ValueError('Unsafe book archive path')
    info=archive.getinfo(path)
    if info.flag_bits & 1:raise ValueError('This book is encrypted; upload a readable edition')
    if info.file_size>MAX_TEXT or info.file_size>max(1,info.compress_size)*250:raise ValueError('Book archive member exceeds limits')
    return archive.read(info)

def extract_book(fd, extension):
    if extension=='.txt':
        raw=os.pread(fd,MAX_TEXT+1,0)
        if len(raw)>MAX_TEXT:raise ValueError('Book text exceeds the supported size')
        if raw.startswith((b'\xff\xfe',b'\xfe\xff')):text=raw.decode('utf-16')
        else:text=raw.decode('utf-8-sig',errors='replace')
        return {'text':text,'chapters':[{'title':'Book','start':0}]}
    if extension in ('.epub','.docx'):
        with book_zip(fd) as archive:
            if len(archive.infolist())>5000:raise ValueError('Book archive contains too many entries')
            if extension=='.docx':
                root=xml(zip_member(archive,'word/document.xml'))
                parts=[''.join(n.itertext()) for n in root.iter() if n.tag.endswith('}p')]
                return {'text':'\n\n'.join(parts)[:MAX_TEXT],'chapters':[{'title':'Book','start':0}]}
            if 'META-INF/encryption.xml' in archive.namelist():raise ValueError('This EPUB contains encrypted resources; use a readable edition')
            container=xml(zip_member(archive,'META-INF/container.xml'))
            rootfile=next((n.get('full-path') for n in container.iter() if n.tag.endswith('rootfile')),None)
            if not rootfile:raise ValueError('EPUB reading order is missing')
            opf=xml(zip_member(archive,rootfile));base=PurePosixPath(rootfile).parent
            manifest={n.get('id'):n.get('href') for n in opf.iter() if n.tag.endswith('}item')}
            order=[n.get('idref') for n in opf.iter() if n.tag.endswith('}itemref')]
            text='';chapters=[]
            for index,ident in enumerate(order[:1000]):
                href=manifest.get(ident)
                if not href:continue
                raw=zip_member(archive,str(base/PurePosixPath(href.split('#')[0])))
                value=plain(raw.decode('utf-8',errors='replace'))
                if not value:continue
                chapters.append({'title':value.splitlines()[0][:120] or 'Chapter '+str(index+1),'start':len(text)})
                text+=value+'\n\n'
                if len(text)>MAX_TEXT:raise ValueError('Book text exceeds the supported size')
            return {'text':text,'chapters':chapters}
    if extension=='.pdf':
        raw=decode(fd,'pdftotext',['-layout','-','-'],timeout=45,memory_limit=256*1024**2)
        value=raw.decode('utf-8',errors='replace')
        if not value.strip():raise ValueError('This PDF needs OCR before it can be read aloud')
        pages=value.split('\f');text='';chapters=[]
        for index,page in enumerate(pages):chapters.append({'title':'Page '+str(index+1),'start':len(text)});text+=page+'\n\n'
        return {'text':text[:MAX_TEXT],'chapters':chapters[:5000]}
    if extension in ('.mobi','.azw','.azw3'):return mobi_text(fd)
    raise ValueError('This Kindle edition needs local conversion or a readable EPUB/TXT companion; the original is retained')

def audio_metadata(fd):
    try:
        raw=decode(fd,'ffprobe',['-v','error','-protocol_whitelist','fd,pipe','-fd',str(fd),'-i','fd:','-show_entries','format=duration:format_tags=title,artist,album,album_artist,genre,date,track,composer,author,comment','-of','json'],timeout=20,memory_limit=256*1024**2)
        value=json.loads(raw).get('format',{});tags={k.lower():v[:10000] for k,v in value.get('tags',{}).items() if isinstance(v,str)}
        result={k:tags.get(k,'') for k in ('title','artist','album','album_artist','genre','track','composer','author')}
        result['year']=tags.get('date','')[:4];result['description']=tags.get('comment','')
        try:
            duration=float(value.get('duration',0));result['duration']=max(0,min(30*86400,duration)) if math.isfinite(duration) else 0
        except (ValueError,TypeError):result['duration']=0
        return result
    except (ValueError,OSError,json.JSONDecodeError):return {'metadata_unavailable':True}
