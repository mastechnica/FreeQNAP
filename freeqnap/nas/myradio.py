"""Private personal audio/book collections, opt-in metadata and public radio.

Originals are isolated from general shares, DLNA folders and personal photos.
Network imports retain partial files on failure and never overwrite originals.
"""
import base64
import contextlib
import hashlib
import fcntl
import json
import os
import re
import secrets
import shutil
import stat
import threading
import time
import urllib.parse
from pathlib import Path
from xml.etree import ElementTree as ET
from .common import name
from .library_lock import serialized
from .library_storage_source import source_directory,source_allowed
from .files import Files, relative, rename_exclusive
from .personal_photos import directory
from .personal_metadata import jpeg
from .radio_metadata import AUDIO, BOOKS, audio_metadata, extract_book
from . import public_http

CATEGORIES = {'music':'Music','books':'Books','podcasts':'Podcasts'}
IDENT = re.compile('[a-f0-9]{32}\\Z')
FIELDS = {'title':500,'artist':500,'album':500,'album_artist':500,'genre':200,'year':20,'track':40,'disc':40,'composer':500,'author':500,'narrator':500,'publisher':500,'description':10000,'isbn':30,'source_url':2000,'book_type':40}

REGIONS={'US':'United States','CA':'Canada'}
def region(value):
    aliases={'united states':'US','united states of america':'US','the united states of america':'US','canada':'CA'}
    result=aliases.get(str(value).lower(),str(value).upper())
    if result not in REGIONS:raise ValueError('Choose United States or Canada')
    return result

def origin(meta):
    try:return region(meta.get('countrycode') or meta.get('country'))
    except ValueError:return None

def clean(value, limit=500):
    if not isinstance(value,str) or len(value)>limit or any(ord(c)<32 and c not in '\n\t' for c in value):raise ValueError('Invalid library text')
    return value.strip()

def category(value):
    if value not in CATEGORIES:raise ValueError('Choose Music, Books or Podcasts')
    return value

def filename(value):
    value=clean(value,180)
    if len(value.encode('utf-8'))>220 or not value or value.startswith('.') or '/' in value or '\\' in value:raise ValueError('Choose a plain filename')
    return value

def catalog_indexes(db):
    db.execute("CREATE INDEX IF NOT EXISTS radio_title_page ON radio_assets(category,hidden,lower(coalesce(json_extract(metadata,'$.title'),name)))")
    for field in ('artist','author','album','genre'):
        db.execute("CREATE INDEX IF NOT EXISTS radio_facet_"+field+" ON radio_assets(category,hidden,json_extract(metadata,'$."+field+"'))")

class MyRadio:
    def __init__(self,ctx):
        self.storage_lock=threading.RLock();self.ctx=ctx;self.decode_slot=threading.BoundedSemaphore(1);self.scan_lock=threading.Lock();self.provider_lock=threading.Lock();self.last_provider=0
        with ctx.state.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS radio_assets(id TEXT PRIMARY KEY,category TEXT NOT NULL,path TEXT NOT NULL,name TEXT NOT NULL,bytes INTEGER NOT NULL,inode INTEGER NOT NULL,mtime_ns INTEGER NOT NULL,metadata TEXT NOT NULL,created REAL NOT NULL,favorite INTEGER NOT NULL DEFAULT 0,hidden INTEGER NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS radio_category ON radio_assets(category,hidden);
            CREATE TABLE IF NOT EXISTS radio_stations(id TEXT PRIMARY KEY,name TEXT NOT NULL,url TEXT NOT NULL,metadata TEXT NOT NULL,checked REAL,working INTEGER NOT NULL DEFAULT 0,favorite INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS radio_feeds(id TEXT PRIMARY KEY,url TEXT NOT NULL,title TEXT NOT NULL,metadata TEXT NOT NULL,checked REAL);
            CREATE TABLE IF NOT EXISTS radio_episodes(id TEXT PRIMARY KEY,feed TEXT NOT NULL,title TEXT NOT NULL,url TEXT NOT NULL,metadata TEXT NOT NULL,asset TEXT);
            CREATE TABLE IF NOT EXISTS radio_sources(id TEXT PRIMARY KEY,kind TEXT NOT NULL,url TEXT,name TEXT NOT NULL,category TEXT NOT NULL,status TEXT NOT NULL,bytes INTEGER NOT NULL DEFAULT 0,total INTEGER,etag TEXT,sha256 TEXT,asset TEXT,error TEXT,updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS radio_uploads(id TEXT PRIMARY KEY,name TEXT NOT NULL,category TEXT NOT NULL,total INTEGER NOT NULL,offset INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL,status TEXT NOT NULL);''')
        # Index the actual expressions used by paging and tag facets. Otherwise each
        # album-browser page repeatedly parses every track's metadata on small CPUs.
        with ctx.state.connect() as db:
            catalog_indexes(db)
        self.seed_stations()

    def config(self):return self.ctx.state.setting('myradio',{})

    @serialized
    def configure(self,r):
        if set(r)-{'pool','scan_enabled','folders','musicbrainz','openlibrary','save_sidecars','podcast_auto_refresh'}:raise ValueError('Unknown My Radio settings')
        old=self.config();pool_id=name(r.get('pool',old.get('pool')));pool,mount=self.ctx.volume(pool_id)
        if pool.get('read_only'):raise ValueError('Choose a writable data volume')
        if old and (old['pool']!=pool_id or old['filesystem_uuid']!=pool['filesystem_uuid']):raise ValueError('An existing collection is retained; moving it requires a separate migration')
        folders=r.get('folders',old.get('folders',{k:True for k in CATEGORIES}))
        if not isinstance(folders,dict) or set(folders)!=set(CATEGORIES) or any(type(v) is not bool for v in folders.values()):raise ValueError('Choose scanning for each collection folder')
        value={**old,'pool':pool_id,'folder':old.get('folder','.freeqnap-myradio'),'filesystem_uuid':pool['filesystem_uuid'],'library_id':old.get('library_id') or secrets.token_hex(16),'scan_enabled':r.get('scan_enabled',old.get('scan_enabled',True)) is True,'folders':folders,
               'musicbrainz':r.get('musicbrainz',old.get('musicbrainz',False)) is True,'openlibrary':r.get('openlibrary',old.get('openlibrary',False)) is True,'save_sidecars':r.get('save_sidecars',old.get('save_sidecars',True)) is True,'podcast_auto_refresh':r.get('podcast_auto_refresh',old.get('podcast_auto_refresh',False)) is True}
        with Files(self.ctx).directory('pool:'+pool_id) as (root,_,_):
            with directory(root,Path(value['folder']).parts,True) as fd:
                marker='.library.json';expected={'library_id':value['library_id'],'filesystem_uuid':value['filesystem_uuid']}
                if not old:
                    if os.listdir(fd):raise ValueError('The private collection folder is not empty; inspect it before setup')
                    out=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
                    try:os.write(out,json.dumps(expected).encode());os.fsync(out)
                    finally:os.close(out)
                else:self.marker(fd,expected)
                for part in (*CATEGORIES,'incoming'):
                    with directory(fd,(part,),True):pass
                os.fsync(fd)
        self.ctx.state.set('myradio',value)
        return {'configured':True,'config':value,'private':True,'shared_with_dlna':False}

    def marker(self,fd,expected):
        f=os.open('.library.json',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
        try:
            if json.loads(os.read(f,4096))!=expected:raise ValueError('Private library identity changed')
        finally:os.close(f)

    @contextlib.contextmanager
    def root(self):
        cfg=self.config()
        if not cfg:raise ValueError('Choose My Radio storage first')
        pool,mount=self.ctx.volume(cfg['pool'])
        if pool['filesystem_uuid']!=cfg['filesystem_uuid']:raise ValueError('My Radio volume identity changed')
        with Files(self.ctx).directory('pool:'+cfg['pool']) as (volume,_,_):
            with directory(volume,Path(cfg['folder']).parts) as fd:
                self.marker(fd,{'library_id':cfg['library_id'],'filesystem_uuid':cfg['filesystem_uuid']});yield fd

    def status(self,r=None):
        cfg=self.config();online=False
        if cfg:
            try:
                with self.root():online=True
            except (ValueError,OSError):pass
        with self.ctx.state.connect() as db:
            counts={v[0]:v[1] for v in db.execute('SELECT category,count(*) FROM radio_assets WHERE hidden=0 GROUP BY category')}
            stations=sum(origin(json.loads(v[0])) is not None for v in db.execute('SELECT metadata FROM radio_stations'))
            pending=[dict(v) for v in db.execute("SELECT id,name,category,status,bytes,total,error FROM radio_sources WHERE status!='complete' ORDER BY updated DESC LIMIT 50")]
            uploads=[dict(v) for v in db.execute("SELECT id,name,category,total,offset,status FROM radio_uploads WHERE status!='complete' ORDER BY created LIMIT 16")]
        return {'prepared_scanning':True,'uploads':uploads,'config':cfg,'online':online,'counts':counts,'stations':stations,'pending':pending,'scanner':self.ctx.state.setting('myradio-scanner',{'state':'idle'}),'private_storage':True,
                'formats':{'audio':sorted(AUDIO),'book_text':['.epub','.txt','.docx']+(['.pdf'] if shutil.which('pdftotext') else []),'kindle_originals':['.azw','.azw3','.mobi','.kpf'],'kindle_reading':'DRM-free MOBI/AZW/AZW3 up to 64 MB use libmobi-tools; KPF requires a readable companion','pdf_ocr':'Scanned PDFs need OCR','read_aloud':'Device speech voices; availability and background playback depend on your browser'},
                'privacy':'My Radio and Personal Photos use separate private folders, not general shares or DLNA exports'}

    def asset(self,ident):
        if not isinstance(ident,str) or not IDENT.fullmatch(ident):raise ValueError('Choose a library item')
        with self.ctx.state.connect() as db:row=db.execute('SELECT * FROM radio_assets WHERE id=?',(ident,)).fetchone()
        if not row:raise ValueError('Library item not found')
        result=dict(row);result['metadata']=json.loads(result['metadata']);return result

    @contextlib.contextmanager
    def opened(self,item,variant='original'):
        with self.root() as root:
            parts=Path(item['path']).parts
            with directory(root,parts[:-1]) as parent:
                leaf=parts[-1] if variant=='original' else 'cover.jpg' if variant=='cover' else 'book.json'
                fd=os.open(leaf,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent)
                try:
                    st=os.fstat(fd)
                    if not stat.S_ISREG(st.st_mode) or st.st_dev!=os.fstat(root).st_dev:raise ValueError('Library file identity changed')
                    if variant=='original' and (st.st_ino,st.st_size,st.st_mtime_ns)!=(item['inode'],item['bytes'],item['mtime_ns']):raise ValueError('Original changed; scan and verify it again')
                    yield fd
                finally:os.close(fd)

    def public(self,row):
        return {**{k:row[k] for k in ('id','category','name','bytes','created','favorite','hidden')},'metadata':{k:v for k,v in row['metadata'].items() if not k.startswith('_')}}

    @serialized
    def catalog(self,r):
        kind=category(r.get('category','music'));query=clean(r.get('query',''),200);limit=r.get('limit',60);offset=r.get('offset',0)
        if type(limit) is not int or not 1<=limit<=120 or type(offset) is not int or not 0<=offset<=1000000:raise ValueError('Invalid library page')
        sorts={'title':"lower(coalesce(json_extract(metadata,'$.title'),name))",'artist':"lower(coalesce(nullif(json_extract(metadata,'$.author'),''),json_extract(metadata,'$.artist'))),lower(json_extract(metadata,'$.album')),lower(name)",'album':"lower(json_extract(metadata,'$.album')),lower(json_extract(metadata,'$.track')),lower(name)",'newest':'created DESC','year':"json_extract(metadata,'$.year') DESC,lower(name)"}
        sort=sorts.get(r.get('sort','title'))
        if not sort:raise ValueError('Choose a library sort order')
        clauses=['category=?','hidden=?'];args=[kind,1 if r.get('archived') is True else 0]
        if query:clauses.append('(name LIKE ? OR metadata LIKE ?)');args += ['%'+query+'%']*2
        for key in ('artist','album','genre'):
            if r.get(key):
                source='author' if kind=='books' and key=='artist' else key
                clauses.append("json_extract(metadata,'$."+source+"')=?");args.append(clean(r[key],500))
        if r.get('favorite') is True:clauses.append('favorite=1')
        where=' AND '.join(clauses)
        with self.ctx.state.connect() as db:
            total=db.execute('SELECT count(*) FROM radio_assets WHERE '+where,args).fetchone()[0]
            rows=[dict(v) for v in db.execute('SELECT * FROM radio_assets WHERE '+where+' ORDER BY '+sort+' LIMIT ? OFFSET ?',(*args,limit,offset))]
            facets={key:[v[0] for v in db.execute("SELECT DISTINCT json_extract(metadata,'$."+('author' if kind=='books' and key=='artist' else key)+"') AS value FROM radio_assets WHERE category=? AND hidden=0 AND value IS NOT NULL AND value!='' ORDER BY value LIMIT 300",(kind,))] for key in ('artist','album','genre')}
        for row in rows:row['metadata']=json.loads(row['metadata'])
        return {'items':[self.public(row) for row in rows],'total':total,'offset':offset,'limit':limit,'facets':facets}

    @serialized
    def read(self,r):
        item=self.asset(r.get('id'));variant=r.get('variant','original')
        if variant not in ('original','cover'):raise ValueError('Choose original media or cover art')
        offset=r.get('offset',0);count=r.get('count',512*1024)
        if type(offset) is not int or offset<0 or type(count) is not int or not 1<=count<=512*1024:raise ValueError('Invalid media range')
        with self.opened(item,variant) as fd:
            st=os.fstat(fd);data=os.pread(fd,count,offset)
            return {'filename':item['name'] if variant=='original' else 'cover.jpg','total_bytes':st.st_size,'etag':f'{st.st_ino}:{st.st_size}:{st.st_mtime_ns}', 'data_base64':base64.b64encode(data).decode()}

    @serialized
    def book_text(self,r):
        item=self.asset(r.get('id'));offset=r.get('offset',0);count=r.get('count',64000)
        if item['category']!='books' or type(offset) is not int or offset<0 or type(count) is not int or not 1<=count<=64000:raise ValueError('Choose a book text page')
        companion=item['metadata'].get('companion_id')
        if companion:item=self.asset(companion)
        with self.opened(item):pass
        try:
            with self.opened(item,'text') as fd:
                raw=os.read(fd,32*1024**2+1)
                if len(raw)>32*1024**2:raise ValueError('Book text cache exceeds limits')
                value=json.loads(raw)
        except FileNotFoundError:raise ValueError(item['metadata'].get('reading_note','Upload a readable EPUB/TXT edition or audiobook companion')) from None
        text=value['text'];return {'id':item['id'],'text':text[offset:offset+count],'offset':offset,'total_characters':len(text),'next_offset':offset+count if offset+count<len(text) else None,'chapters':value.get('chapters',[])}

    def write_file(self,fd,leaf,raw):
        tmp=leaf+'.'+secrets.token_hex(8)+'.next';out=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
        try:
            with os.fdopen(out,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            os.replace(tmp,leaf,src_dir_fd=fd,dst_dir_fd=fd);os.fsync(fd)
        finally:
            try:os.unlink(tmp,dir_fd=fd)
            except FileNotFoundError:pass

    @serialized
    def register(self,kind,ident,leaf,metadata=None):
        kind=category(kind);metadata=dict(metadata or {});path=kind+'/'+ident+'/'+leaf
        with self.ctx.state.connect() as db:previous=db.execute('SELECT metadata FROM radio_assets WHERE id=?',(ident,)).fetchone()
        previous=json.loads(previous[0]) if previous else {}
        with self.root() as root,directory(root,(kind,ident)) as folder:
            fd=os.open(leaf,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=folder)
            try:
                st=os.fstat(fd);ext=Path(leaf).suffix.lower()
                if not stat.S_ISREG(st.st_mode) or st.st_dev!=os.fstat(root).st_dev:raise ValueError('Original identity changed')
                if not metadata and previous.get('_prepared')=={'inode':st.st_ino,'bytes':st.st_size,'mtime_ns':st.st_mtime_ns}:return self.public(self.asset(ident))
                with self.decode_slot:
                    if ext in AUDIO:
                        metadata={**audio_metadata(fd),**metadata};metadata['playable']='audio'
                        if kind=='books':metadata.update(book_type='audiobook',author=metadata.get('author') or metadata.get('artist',''))
                        try:
                            if not previous.get('custom_cover'):self.write_file(folder,'cover.jpg',jpeg(fd,memory_limit=384*1024**2))
                            metadata['has_cover']=True
                        except (ValueError,OSError):pass
                    elif ext=='.aax':
                        metadata={**audio_metadata(fd),**metadata,'book_type':'audiobook','playable':'original-only','reading_note':'Audible AAX original retained. Browser playback requires a compatible authorized player or a DRM-free companion edition.'}
                        metadata['author']=metadata.get('author') or metadata.get('artist','')
                        try:
                            if not previous.get('custom_cover'):self.write_file(folder,'cover.jpg',jpeg(fd,memory_limit=384*1024**2))
                            metadata['has_cover']=True
                        except (ValueError,OSError):pass
                    elif ext in BOOKS:
                        try:
                            book=extract_book(fd,ext);self.write_file(folder,'book.json',json.dumps(book,ensure_ascii=False).encode());metadata['playable']='text';metadata['book_type']='ebook';metadata['chapters']=len(book.get('chapters',[]))
                        except (ValueError,OSError,KeyError,ET.ParseError,UnicodeError) as error:metadata.update(playable='original-only',reading_note=str(error)[:400])
                    else:raise ValueError('This file format is not supported in My Radio')
                metadata['title']=metadata.get('title') or Path(leaf).stem
                with self.ctx.state.connect() as db:
                    old=db.execute('SELECT metadata FROM radio_assets WHERE id=?',(ident,)).fetchone()
                    if old:
                        saved=json.loads(old[0])
                        if saved.get('user_edited'):metadata={**metadata,**saved}
                    db.execute('INSERT INTO radio_assets(id,category,path,name,bytes,inode,mtime_ns,metadata,created) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET bytes=excluded.bytes,inode=excluded.inode,mtime_ns=excluded.mtime_ns,metadata=excluded.metadata',(ident,kind,path,leaf,st.st_size,st.st_ino,st.st_mtime_ns,json.dumps(metadata),time.time()))
                if self.config().get('save_sidecars'):self.write_file(folder,'metadata.json',json.dumps(metadata,ensure_ascii=False,indent=2).encode())
            finally:os.close(fd)
        return self.public(self.asset(ident))

    @serialized
    def upload_begin(self,r):
        kind=category(r.get('category'));leaf=filename(r.get('name'));total=r.get('bytes')
        if Path(leaf).suffix.lower() not in AUDIO|BOOKS or type(total) is not int or not 1<=total<=128*1024**3:raise ValueError('Choose a supported media/book file up to 128 GB')
        ident=secrets.token_hex(16)
        with self.root() as root,directory(root,('incoming',)) as folder:
            with self.ctx.state.connect() as db:
                if db.execute("SELECT count(*) FROM radio_uploads WHERE status='uploading'").fetchone()[0]>=16:raise ValueError('Finish or resume existing uploads first')
                fd=os.open(ident,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=folder);os.close(fd)
                db.execute("INSERT INTO radio_uploads VALUES(?,?,?,?,0,?,'uploading')",(ident,leaf,kind,total,time.time()))
        return {'upload_id':ident,'offset':0,'total_bytes':total}

    def upload_row(self,ident):
        if not isinstance(ident,str) or not IDENT.fullmatch(ident):raise ValueError('Choose an upload')
        with self.ctx.state.connect() as db:row=db.execute('SELECT * FROM radio_uploads WHERE id=?',(ident,)).fetchone()
        if not row:raise ValueError('Upload not found')
        return dict(row)

    @serialized
    def upload_chunk(self,r):
        row=self.upload_row(r.get('upload_id'));offset=r.get('offset')
        try:data=base64.b64decode(r.get('data_base64',''),validate=True)
        except (ValueError,TypeError):raise ValueError('Invalid upload chunk') from None
        if type(offset) is not int or row['status']!='uploading' or offset>row['offset'] or not 1<=len(data)<=512*1024 or offset+len(data)>row['total']:raise ValueError('Upload offset or size changed; resume from the recorded offset')
        with self.root() as root,directory(root,('incoming',)) as folder:
            fd=os.open(row['id'],os.O_RDWR|os.O_NOFOLLOW,dir_fd=folder)
            try:
                fcntl.flock(fd,fcntl.LOCK_EX)
                if offset<row['offset']:
                    if offset+len(data)>row['offset'] or os.pread(fd,len(data),offset)!=data:raise ValueError('This is not the same original file; retained upload was not overwritten')
                    return {'upload_id':row['id'],'offset':offset+len(data),'total_bytes':row['total'],'verified_existing':True}
                if os.fstat(fd).st_size!=offset:raise ValueError('Partial upload identity changed')
                if os.pwrite(fd,data,offset)!=len(data):raise OSError('Short upload write')
                os.fsync(fd)
                with self.ctx.state.connect() as db:
                    changed=db.execute('UPDATE radio_uploads SET offset=? WHERE id=? AND offset=?',(offset+len(data),row['id'],offset)).rowcount
                    if changed!=1:raise ValueError('Upload state changed; inspect the retained partial')
            finally:os.close(fd)
        return {'upload_id':row['id'],'offset':offset+len(data),'total_bytes':row['total']}

    @serialized
    def upload_finish(self,r):
        row=self.upload_row(r.get('upload_id'))
        if row['status']=='complete':return {'item':self.public(self.asset(row['id'])),'already_complete':True}
        if row['offset']!=row['total']:raise ValueError('Upload is not complete')
        with self.root() as root,directory(root,('incoming',)) as incoming,directory(root,(row['category'],row['id']),True) as target:
            try:rename_exclusive(incoming,row['id'],target,row['name'])
            except FileNotFoundError:
                # Reconcile only the exact post-rename stage; never overwrite it.
                fd=os.open(row['name'],os.O_RDONLY|os.O_NOFOLLOW,dir_fd=target)
                try:
                    if os.fstat(fd).st_size!=row['total']:raise ValueError('Upload stage changed')
                finally:os.close(fd)
            os.fsync(target);os.fsync(incoming)
        item=self.register(row['category'],row['id'],row['name'])
        with self.ctx.state.connect() as db:db.execute("UPDATE radio_uploads SET status='complete' WHERE id=?",(row['id'],))
        return {'item':item}

    @serialized
    def metadata(self,r):
        item=self.asset(r.get('id'));changes=r.get('metadata',{})
        if not isinstance(changes,dict) or set(changes)-set(FIELDS)-{'companion_id'}:raise ValueError('Unknown metadata fields')
        value=dict(item['metadata'])
        for k,v in changes.items():
            if k=='companion_id':
                if v:
                    other=self.asset(v)
                    if other['category']!='books' or other['id']==item['id']:raise ValueError('Choose another readable book edition')
                    if other['metadata'].get('companion_id'):raise ValueError('Nested companion links are not allowed')
                value[k]=v or None
            else:
                value[k]=clean(v,FIELDS[k])
                if k=='book_type' and value[k] not in ('audiobook','ebook','other'):raise ValueError('Choose Audiobook, eBook or Other')
                if k=='source_url' and value[k]:
                    u=urllib.parse.urlsplit(value[k])
                    if u.scheme not in ('http','https') or not u.hostname or u.username is not None or u.password is not None:raise ValueError('Use an HTTP(S) source link without credentials')
        value['user_edited']=True
        with self.root() as root,directory(root,Path(item['path']).parts[:-1]) as folder:
            if self.config().get('save_sidecars'):self.write_file(folder,'metadata.json',json.dumps(value,ensure_ascii=False,indent=2).encode())
        with self.ctx.state.connect() as db:db.execute('UPDATE radio_assets SET metadata=?,favorite=?,hidden=? WHERE id=?',(json.dumps(value),int(r.get('favorite',bool(item['favorite'])) is True),int(r.get('archived',bool(item['hidden'])) is True),item['id']))
        return {'item':self.public(self.asset(item['id']))}

    @serialized
    def artwork(self,r):
        item=self.asset(r.get('id'))
        try:raw=base64.b64decode(r.get('data_base64',''),validate=True)
        except (ValueError,TypeError):raise ValueError('Invalid cover image') from None
        if not 1<=len(raw)<=1024**2:raise ValueError('Choose cover art below 1 MB')
        import tempfile
        with tempfile.TemporaryFile() as stream:
            stream.write(raw);stream.flush()
            with self.decode_slot:cover=jpeg(stream.fileno(),memory_limit=384*1024**2)
        with self.root() as root,directory(root,Path(item['path']).parts[:-1]) as folder:self.write_file(folder,'cover.jpg',cover)
        value=item['metadata'];value.update(has_cover=True,custom_cover=True,user_edited=True)
        with self.root() as root,directory(root,Path(item['path']).parts[:-1]) as folder:
            if self.config().get('save_sidecars'):self.write_file(folder,'metadata.json',json.dumps(value,ensure_ascii=False,indent=2).encode())
        with self.ctx.state.connect() as db:db.execute('UPDATE radio_assets SET metadata=? WHERE id=?',(json.dumps(value),item['id']))
        return {'saved':True}

    def progress(self,r):
        item=self.asset(r.get('id'));position=r.get('position',0)
        if r.get('kind','audio') not in ('audio','text') or type(position) not in (int,float) or not 0<=position<=10**9:raise ValueError('Invalid playback position')
        self.ctx.state.set('myradio-position:'+item['id'],{'position':position,'updated':time.time(),'kind':r.get('kind','audio')})
        return {'saved':True}

    def item(self,r):
        item=self.asset(r.get('id'));return {'item':self.public(item),'progress':self.ctx.state.setting('myradio-position:'+item['id'])}

    @serialized
    def scan(self,r):
        cfg=self.config()
        if not cfg or not cfg['scan_enabled']:raise ValueError('Folder scanning is disabled')
        if not self.scan_lock.acquire(blocking=False):raise ValueError('A My Radio scan is already running')
        count=0;errors=[]
        def progress(state,**fields):self.ctx.state.set('myradio-scanner',{'state':state,'at':time.time(),'indexed':count,**fields})
        progress('running',phase='Reading designated collection folders')
        try:
            with self.root() as root:
                for kind,enabled in cfg['folders'].items():
                    if not enabled:continue
                    with directory(root,(kind,)) as folder:
                        with os.scandir(folder) as entries:
                            for entry in entries:
                                if count>=100000:raise ValueError('Scanner limit reached; earlier results are retained')
                                if not IDENT.fullmatch(entry.name) or not entry.is_dir(follow_symlinks=False):continue
                                prepared=False
                                with directory(folder,(entry.name,)) as item_fd:
                                    candidates=[e.name for e in os.scandir(item_fd) if e.is_file(follow_symlinks=False) and Path(e.name).suffix.lower() in AUDIO|BOOKS]
                                    if len(candidates)==1:
                                        try:
                                            saved=self.asset(entry.name);st=os.stat(candidates[0],dir_fd=item_fd,follow_symlinks=False)
                                            expected={'inode':st.st_ino,'bytes':st.st_size,'mtime_ns':st.st_mtime_ns}
                                            prepared=stat.S_ISREG(st.st_mode) and st.st_dev==os.fstat(root).st_dev and saved['path']==kind+'/'+entry.name+'/'+candidates[0] and saved['metadata'].get('_prepared')==expected and all(saved[k]==v for k,v in expected.items())
                                        except ValueError:pass
                                if len(candidates)!=1:continue
                                if prepared:
                                    count+=1
                                    if count%50==0:progress('running',folder=CATEGORIES[kind],filename=candidates[0],phase='Verifying prepared local metadata')
                                    continue
                                progress('running',folder=CATEGORIES[kind],filename=candidates[0],phase='Reading local metadata')
                                try:self.register(kind,entry.name,candidates[0]);count+=1
                                except (ValueError,OSError) as error:errors.append({'name':candidates[0],'error':str(error)[:200]})
                                if len(errors)>=50:raise ValueError('Scanner stopped after repeated file errors; earlier results are retained')
            progress('idle',phase='Finished',errors=errors)
            return {'indexed':count,'errors':errors,'complete':not errors}
        except Exception as error:progress('failed',phase='Stopped; partial results retained',error=str(error)[:300]);raise
        finally:self.scan_lock.release()

    @serialized
    def import_folder(self,r):
        kind=category(r.get('category'));share=r.get('share');source_path=r.get('path','');relative(source_path)
        imported=0;skipped=0
        with source_directory(self.ctx,share,source_path) as (start,_,pool):
            source_device=os.fstat(start).st_dev
            def walk(fd,parts=()):
                nonlocal imported,skipped
                if len(parts)>30:raise ValueError('Source folder nesting exceeds limits')
                with os.scandir(fd) as entries:
                    for entry in entries:
                        if entry.name.startswith('.freeqnap') or entry.name=='@eaDir' or entry.is_symlink():continue
                        if not source_allowed(self.ctx,share,str(Path(source_path).joinpath(*parts,entry.name))):continue
                        if imported+skipped>=10000:raise ValueError('Import limit reached; earlier imports are retained')
                        if entry.is_dir(follow_symlinks=False):
                            with directory(fd,(entry.name,)) as child:
                                if os.fstat(child).st_dev!=source_device:continue
                                walk(child,parts+(entry.name,))
                        elif entry.is_file(follow_symlinks=False) and Path(entry.name).suffix.lower() in AUDIO|BOOKS:
                            source=os.open(entry.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
                            try:
                                st=os.fstat(source)
                                if not stat.S_ISREG(st.st_mode) or st.st_dev!=source_device:raise ValueError('Source identity changed')
                                ident=hashlib.sha256((self.config()['library_id']+'\0'+pool['filesystem_uuid']+'\0'+str(st.st_ino)+'\0'+str(st.st_mtime_ns)+'\0'+kind).encode()).hexdigest()[:32]
                                try:self.asset(ident);skipped+=1;continue
                                except ValueError:pass
                                leaf=filename(entry.name)
                                from .music_sidecars import read as read_sidecar
                                sidecar=read_sidecar(fd,entry.name,st) if kind=='music' else {}
                                with self.root() as root,directory(root,(kind,ident),True) as folder:
                                    try:existing=os.open(leaf,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=folder)
                                    except FileNotFoundError:existing=None
                                    if existing is not None:
                                        try:
                                            if os.fstat(existing).st_size!=st.st_size:raise ValueError('Retained import differs; inspect it before retry')
                                            a=hashlib.sha256();b=hashlib.sha256()
                                            while True:
                                                chunk=os.read(existing,1024**2)
                                                if not chunk:break
                                                a.update(chunk)
                                            while True:
                                                chunk=os.read(source,1024**2)
                                                if not chunk:break
                                                b.update(chunk)
                                            if a.digest()!=b.digest():raise ValueError('Retained import differs; inspect it before retry')
                                        finally:os.close(existing)
                                        self.register(kind,ident,leaf,sidecar);imported+=1;continue
                                    stage=leaf+'.'+secrets.token_hex(8)+'.partial'
                                    out=os.open(stage,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=folder)
                                    try:
                                        with os.fdopen(out,'wb') as target:
                                            while True:
                                                data=os.read(source,1024**2)
                                                if not data:break
                                                target.write(data)
                                            target.flush();os.fsync(target.fileno())
                                        after=os.fstat(source)
                                        if (st.st_ino,st.st_size,st.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):raise ValueError('Source changed during import; partial copy retained for inspection')
                                        rename_exclusive(folder,stage,folder,leaf);os.fsync(folder)
                                    except Exception:raise
                                self.register(kind,ident,leaf,sidecar);imported+=1
                                self.ctx.state.set('myradio-scanner',{'state':'running','phase':'Importing files','filename':leaf,'indexed':imported,'at':time.time()})
                            finally:os.close(source)
            walk(start)
        self.ctx.state.set('myradio-scanner',{'state':'idle','phase':'Import finished','indexed':imported,'at':time.time()})
        return {'imported':imported,'already_present':skipped,'source_files_unchanged':True}

    @serialized
    def lookup(self,r):
        item=self.asset(r.get('id'));cfg=self.config();meta=item['metadata'];title=clean(r.get('title',meta.get('title',item['name'])),500)
        author=clean(r.get('artist',meta.get('artist') or meta.get('author') or ''),500)
        if item['category']=='books':
            if not cfg.get('openlibrary'):raise ValueError('Enable Open Library title searches in My Radio settings first')
            value=public_http.json_fetch('https://openlibrary.org/search.json?'+urllib.parse.urlencode({'title':title,'author':author,'limit':8,'fields':'key,title,author_name,first_publish_year,isbn,cover_i'}))
            results=[]
            for row in value.get('docs',[])[:8]:
                key=row.get('key','')
                if not re.fullmatch('/works/OL[0-9]+W',key):continue
                cover=row.get('cover_i');results.append({'title':str(row.get('title',''))[:500],'author':', '.join(row.get('author_name',[]))[:500],'year':str(row.get('first_publish_year','')),'isbn':str((row.get('isbn') or [''])[0])[:30],'source_url':'https://openlibrary.org'+key,'cover_url':'https://covers.openlibrary.org/b/id/'+str(cover)+'-M.jpg' if type(cover) is int and cover>0 else None})
            return {'provider':'Open Library','results':results}
        if not cfg.get('musicbrainz'):raise ValueError('Enable MusicBrainz title searches in My Radio settings first')
        def escaped(s):return s.replace('\\','\\\\').replace('"','\\"')
        query='recording:"'+escaped(title)+'"'+(' AND artist:"'+escaped(author)+'"' if author else '')
        with self.provider_lock:
            time.sleep(max(0,1.1-(time.monotonic()-self.last_provider)))
            try:value=public_http.json_fetch('https://musicbrainz.org/ws/2/recording/?'+urllib.parse.urlencode({'query':query,'fmt':'json','limit':8}))
            finally:self.last_provider=time.monotonic()
        results=[]
        for row in value.get('recordings',[])[:8]:
            ident=row.get('id','')
            if not re.fullmatch('[a-f0-9-]{36}',ident):continue
            release=(row.get('releases') or [{}])[0];release_id=release.get('id','')
            results.append({'title':str(row.get('title',''))[:500],'artist':''.join(v.get('name','')+v.get('joinphrase','') for v in row.get('artist-credit',[]) if isinstance(v,dict))[:500],'album':str(release.get('title',''))[:500],'year':str(release.get('date',''))[:4],'source_url':'https://musicbrainz.org/recording/'+ident,'cover_url':'https://coverartarchive.org/release/'+release_id+'/front-250' if re.fullmatch('[a-f0-9-]{36}',release_id) else None})
        return {'provider':'MusicBrainz / Cover Art Archive','results':results}

    @serialized
    def artwork_url(self,r):
        url=r.get('url','');host=urllib.parse.urlsplit(url).hostname
        if host not in ('covers.openlibrary.org','coverartarchive.org') or not url.startswith('https://'):raise ValueError('Choose cover art returned by the enabled metadata provider')
        raw=public_http.fetch(url,4*1024**2)
        return self.artwork({'id':r.get('id'),'data_base64':base64.b64encode(raw).decode()})

    def queue_url(self,r,job_enqueue,episode_id=None):
        kind=category(r.get('category'));leaf=filename(r.get('name'));url=r.get('url','')
        if Path(leaf).suffix.lower() not in AUDIO|BOOKS:raise ValueError('Choose a supported destination filename')
        public_http.target(url)
        ident=secrets.token_hex(16)
        with self.root():pass
        with self.ctx.state.connect() as db:db.execute("INSERT INTO radio_sources(id,kind,url,name,category,status,updated) VALUES(?,'url',?,?,?,'queued',?)",(ident,url,leaf,kind,time.time()))
        if episode_id:self.ctx.state.set('myradio-episode-source:'+ident,episode_id)
        try:job=job_enqueue('myradio.download',{'source':ident})
        except Exception:
            with self.ctx.state.connect() as db:db.execute("UPDATE radio_sources SET status='retryable',error='Queue unavailable; source retained for explicit resume' WHERE id=?",(ident,))
            raise
        return {'job_id':job,'source_id':ident}

    def reconcile_downloads(self):
        with self.ctx.state.connect() as db:
            db.execute("UPDATE radio_sources SET status='retryable',error='Interrupted; verified partial retained for explicit resume',updated=? WHERE status IN ('running','finalizing')",(time.time(),))

    @serialized
    def download(self,r):
        ident=r.get('source','')
        if not isinstance(ident,str) or not IDENT.fullmatch(ident):raise ValueError('Choose a retained download source')
        with self.root() as root,directory(root,('incoming',)) as incoming:
            lock=os.open(ident+'.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=incoming)
            try:
                try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:raise ValueError('This download is already running') from None
                return self._download(r)
            finally:os.close(lock)

    def _download(self,r):
        ident=r.get('source','')
        if not isinstance(ident,str) or not IDENT.fullmatch(ident):raise ValueError('Choose a retained download source')
        with self.ctx.state.connect() as db:row=db.execute('SELECT * FROM radio_sources WHERE id=?',(ident,)).fetchone()
        if not row:raise ValueError('Download source not found')
        row=dict(row)
        if row['status']=='complete':return {'item':self.public(self.asset(row['asset'])),'already_present':True}
        try:
            with self.root() as root,directory(root,(row['category'],ident),True) as target:
                try:completed=os.open(row['name'],os.O_RDONLY|os.O_NOFOLLOW,dir_fd=target)
                except FileNotFoundError:completed=None
                if completed is not None:
                    try:
                        h=hashlib.sha256();count=0
                        while True:
                            b=os.read(completed,1024**2)
                            if not b:break
                            h.update(b);count+=len(b)
                        if count!=row['bytes'] or not row['sha256'] or h.hexdigest()!=row['sha256']:raise ValueError('Finalized original identity changed; inspect before retry')
                    finally:os.close(completed)
                    return self.finish_download(row)
            with self.root() as root,directory(root,('incoming',)) as incoming:
                fd=os.open(ident+'.part',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=incoming)
                try:
                    offset=os.fstat(fd).st_size;digest=hashlib.sha256();position=0
                    while position<offset:
                        data=os.pread(fd,min(1024**2,offset-position),position)
                        if not data:raise ValueError('Short retained partial read')
                        digest.update(data);position+=len(data)
                    if offset and (offset!=row['bytes'] or digest.hexdigest()!=row['sha256']):raise ValueError('Retained partial changed; inspect before starting a new download')
                    headers={'Range':'bytes='+str(offset)+'-'} if offset else {}
                    if offset and row['etag']:headers['If-Range']=row['etag']
                    with public_http.open_url(row['url'],headers=headers,timeout=15) as (response,_):
                        if offset and (response.status!=206 or not (response.getheader('Content-Range') or '').startswith('bytes '+str(offset)+'-')):raise ValueError('Server cannot resume this retained partial; it was not overwritten')
                        total=int(response.getheader('Content-Length') or 0)+offset
                        if not offset and response.status==206:raise ValueError('Unexpected partial response')
                        if total>128*1024**3:raise ValueError('Download exceeds the collection size limit')
                        etag=(response.getheader('ETag') or '')[:500]
                        with self.ctx.state.connect() as db:db.execute("UPDATE radio_sources SET status='running',total=?,etag=?,error=NULL,updated=? WHERE id=?",(total or None,etag,time.time(),ident))
                        while True:
                            data=response.read(512*1024)
                            if not data:break
                            if offset+len(data)>128*1024**3:raise ValueError('Download exceeds the collection size limit')
                            if os.pwrite(fd,data,offset)!=len(data):raise OSError('Short download write')
                            offset+=len(data);digest.update(data);os.fsync(fd)
                            with self.ctx.state.connect() as db:db.execute('UPDATE radio_sources SET bytes=?,sha256=?,updated=? WHERE id=?',(offset,digest.hexdigest(),time.time(),ident))
                        if not offset or (total and offset!=total):raise ValueError('Incomplete response; verified partial is retained')
                    os.fsync(fd)
                    with self.ctx.state.connect() as db:db.execute("UPDATE radio_sources SET status='finalizing',updated=? WHERE id=?",(time.time(),ident))
                finally:os.close(fd)
                with directory(root,(row['category'],ident),True) as target:rename_exclusive(incoming,ident+'.part',target,row['name']);os.fsync(target);os.fsync(incoming)
            return self.finish_download(row)
        except Exception as error:
            with self.ctx.state.connect() as db:db.execute("UPDATE radio_sources SET status='retryable',error=?,updated=? WHERE id=?",(str(error)[:300],time.time(),ident))
            raise

    @serialized
    def finish_download(self,row):
        ident=row['id'];metadata={}
        episode_id=self.ctx.state.setting('myradio-episode-source:'+ident,'')
        if episode_id:
            with self.ctx.state.connect() as db:episode=db.execute('SELECT * FROM radio_episodes WHERE id=?',(episode_id,)).fetchone()
            if episode:
                m=json.loads(episode['metadata']);metadata={'title':episode['title'],'artist':m.get('author',''),'album':m.get('series',''),'description':m.get('description','')}
        item=self.register(row['category'],ident,row['name'],metadata)
        with self.ctx.state.connect() as db:
            db.execute("UPDATE radio_sources SET status='complete',asset=?,error=NULL,updated=? WHERE id=?",(ident,time.time(),ident))
            db.execute('UPDATE radio_episodes SET asset=? WHERE id=?',(ident,episode_id))
        return {'item':item}

    def retry_download(self,r,enqueue):
        ident=r.get('source')
        with self.ctx.state.connect() as db:row=db.execute('SELECT status FROM radio_sources WHERE id=?',(ident,)).fetchone()
        if not row or row[0]!='retryable':raise ValueError('Choose a retained failed download')
        return {'job_id':enqueue('myradio.download',{'source':ident})}

    def seed_stations(self):
        with self.ctx.state.connect() as db:
            # Add newly reviewed regional seeds without overwriting saved stations.
            source=Path(__file__).parents[1]/'radio_stations.json'
            if not source.exists():return
            value=json.loads(source.read_text())
            for row in value.get('stations',[])[:150]:
                if origin(row['metadata']) not in REGIONS:continue
                ident=hashlib.sha256(row['id'].encode()).hexdigest()[:32]
                metadata={**row['metadata'],'directory_uuid':row['id'],'content_type':row['content_type'],'source':'Radio Browser'}
                db.execute('INSERT OR IGNORE INTO radio_stations(id,name,url,metadata,checked,working) VALUES(?,?,?,?,?,1)',(ident,row['name'],row['url'],json.dumps(metadata),row['checked_at']))

    def station_artwork(self,r):
        from .station_art import artwork
        return artwork(self.ctx,r)

    def stations(self,r):
        query=clean(r.get('query',''),200);tag=clean(r.get('group',''),100);country=clean(r.get('country',''),100)
        if country:country=region(country)
        with self.ctx.state.connect() as db:rows=[dict(v) for v in db.execute('SELECT * FROM radio_stations ORDER BY favorite DESC,name LIMIT 1000')]
        items=[];groups=set();countries=set()
        for row in rows:
            meta=json.loads(row['metadata'])
            code=origin(meta)
            if not code:continue
            meta.update(countrycode=code,country=REGIONS[code]);tags=[v.strip() for v in str(meta.get('tags') or '').split(',') if v.strip()]
            groups.update(tags[:12]);countries.add(meta.get('country') or '')
            if query.casefold() not in (row['name']+' '+str(meta.get('tags') or '')+' '+str(meta.get('country') or '')).casefold():continue
            if tag and tag.casefold() not in [v.casefold() for v in tags]:continue
            if country and region(country)!=code:continue
            if r.get('favorite') is True and not row['favorite']:continue
            items.append({'id':row['id'],'name':row['name'],'metadata':meta,'checked_at':row['checked'],'working':bool(row['working']),'favorite':bool(row['favorite']),'verification_stale':not row['checked'] or time.time()-row['checked']>7*86400})
        return {'items':items,'groups':sorted(groups)[:300],'countries':sorted(v for v in countries if v),'source':'Radio Browser and your custom stations','verification':'Small direct audio samples, not a guarantee of future availability'}

    def station_save(self,r):
        if r.get('id'):
            ident=r['id']
            with self.ctx.state.connect() as db:
                if not db.execute('SELECT id FROM radio_stations WHERE id=?',(ident,)).fetchone():raise ValueError('Station not found')
                db.execute('UPDATE radio_stations SET favorite=? WHERE id=?',(int(r.get('favorite') is True),ident))
            return {'saved':True}
        code=region(r.get('country'));label=clean(r.get('name'),160);url=r.get('url');probe=public_http.probe_stream(url)
        ident=hashlib.sha256(probe['url'].encode()).hexdigest()[:32]
        meta={'tags':clean(r.get('group','Custom'),100),'country':REGIONS[code],'countrycode':code,'content_type':probe['content_type'],'source':'Your station'}
        with self.ctx.state.connect() as db:db.execute('INSERT INTO radio_stations(id,name,url,metadata,checked,working) VALUES(?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET name=excluded.name,url=excluded.url,metadata=excluded.metadata,checked=excluded.checked,working=1',(ident,label,probe['url'],json.dumps(meta),time.time()))
        return {'id':ident,'working':True,'checked_at':time.time()}

    def station_check(self,r):
        with self.ctx.state.connect() as db:row=db.execute('SELECT * FROM radio_stations WHERE id=?',(r.get('id'),)).fetchone()
        if not row:raise ValueError('Station not found')
        if not origin(json.loads(row['metadata'])):raise ValueError('Only United States and Canada stations are enabled')
        try:probe=public_http.probe_stream(row['url'])
        except (ValueError,OSError):
            with self.ctx.state.connect() as db:db.execute('UPDATE radio_stations SET working=0,checked=? WHERE id=?',(time.time(),row['id']))
            raise ValueError('The station did not return a direct playable audio stream; your station entry is retained') from None
        with self.ctx.state.connect() as db:db.execute('UPDATE radio_stations SET working=1,checked=?,url=? WHERE id=?',(time.time(),probe['url'],row['id']))
        return {'id':row['id'],'working':True,'checked_at':time.time()}

    def station_source(self,r):
        with self.ctx.state.connect() as db:row=db.execute('SELECT * FROM radio_stations WHERE id=?',(r.get('id'),)).fetchone()
        if not row:raise ValueError('Station not found')
        if not origin(json.loads(row['metadata'])):raise ValueError('Only United States and Canada stations are enabled')
        return {'id':row['id'],'url':row['url'],'name':row['name'],'public_only':True}

    def station_refresh(self,r):
        tag=clean(r.get('group',''),80);query=clean(r.get('query',''),200);selected=[region(r['country'])] if r.get('country') else list(REGIONS)
        params={'limit':50,'hidebroken':'true','is_https':'true','order':'votes','reverse':'true','codec':'MP3'}
        if tag:params['tag']=tag
        if query:params['name']=query
        rows=[]
        for code in selected:
            batch=public_http.json_fetch('https://de1.api.radio-browser.info/json/stations/search?'+urllib.parse.urlencode({**params,'countrycode':code}))
            if not isinstance(batch,list):raise ValueError('Invalid station directory response')
            rows.extend(v for v in batch[:25] if isinstance(v,dict) and origin(v)==code)
        added=0;failed=0
        for row in rows[:50]:
            try:
                probe=public_http.probe_stream(row.get('url_resolved') or row['url'])
                ident=hashlib.sha256(row['stationuuid'].encode()).hexdigest()[:32]
                meta={key:row.get(key) for key in ('country','countrycode','language','tags','codec','bitrate','homepage','favicon')}
                meta.update(directory_uuid=row['stationuuid'],source='Radio Browser',content_type=probe['content_type'])
                with self.ctx.state.connect() as db:db.execute('INSERT INTO radio_stations(id,name,url,metadata,checked,working) VALUES(?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET name=excluded.name,url=excluded.url,metadata=excluded.metadata,checked=excluded.checked,working=1',(ident,clean(row['name'],160),probe['url'],json.dumps(meta),time.time()))
                added+=1
            except (ValueError,OSError,KeyError):failed+=1
            self.ctx.state.set('myradio-radio-refresh',{'at':time.time(),'checked':added+failed,'working':added,'state':'running'})
        self.ctx.state.set('myradio-radio-refresh',{'at':time.time(),'checked':added+failed,'working':added,'state':'idle'})
        return {'verified_working':added,'unavailable_skipped':failed,'old_stations_retained':True}

    def feeds(self,r):
        from email.utils import parsedate_to_datetime
        from datetime import datetime,timezone
        def stamp(row):
            value=row['metadata'].get('published')
            try:
                try:d=parsedate_to_datetime(value)
                except (ValueError,TypeError):d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
                return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()
            except (ValueError,TypeError,OverflowError):return None
        limit=r.get('limit',300);offset=r.get('offset',0)
        if limit!='all' and (type(limit)is not int or not 1<=limit<=1000) or type(offset)is not int or offset<0:raise ValueError('Choose a valid podcast page')
        with self.ctx.state.connect() as db:
            feeds=[{'id':v['id'],'title':v['title'],'metadata':json.loads(v['metadata']),'checked_at':v['checked']} for v in db.execute('SELECT * FROM radio_feeds ORDER BY title')]
            unclassified=[v for v in feeds if not origin(v['metadata'])];feeds=[v for v in feeds if origin(v['metadata'])];allowed={v['id'] for v in feeds}
            if r.get('feed'):allowed &= {r['feed']}
            episodes=[]
            if allowed:
                records=db.execute('SELECT * FROM radio_episodes WHERE feed IN ('+','.join('?' for _ in allowed)+') LIMIT 20001',tuple(allowed)).fetchall()
                if len(records)>20000:raise ValueError('This podcast catalog exceeds the 20,000 episode browser limit; choose one show')
                episodes=[{'id':v['id'],'feed':v['feed'],'title':v['title'],'metadata':json.loads(v['metadata']),'asset':v['asset']} for v in records]
        query=clean(r.get('query',''),200).casefold()
        if query:episodes=[v for v in episodes if query in (v['title']+' '+str(v['metadata'].get('series',''))+' '+str(v['metadata'].get('description',''))).casefold()]
        episodes.sort(key=lambda v:(stamp(v) is None,-stamp(v) if stamp(v) is not None else 0,v['id']))
        total=len(episodes);page=episodes[offset:offset+(1000 if limit=='all' else limit)]
        # Leave headroom for the broker's two-MiB envelope, including non-ASCII text.
        budget=1500*1024-len(json.dumps(feeds).encode())
        admitted=[];used=0
        for item in page:
            amount=len(json.dumps(item).encode())+2
            if used+amount>budget:break
            admitted.append(item);used+=amount
        if page and not admitted:raise ValueError('Podcast metadata exceeds the broker response budget')
        page=admitted
        return {'unclassified_feeds':unclassified,'regions':REGIONS,'feeds':feeds,'episodes':page,'total':total,'offset':offset,'limit':limit,'next_offset':None if offset+len(page)>=total else offset+len(page),'pagination':True,'feed_urls_private':True,'auto_refresh':self.config().get('podcast_auto_refresh',False)}

    def feed_add(self,r):
        code=region(r.get('country'))
        if r.get('id'):
            with self.ctx.state.connect() as db:
                old=db.execute('SELECT metadata FROM radio_feeds WHERE id=?',(r['id'],)).fetchone()
                if not old:raise ValueError('Subscription not found')
                meta=json.loads(old[0]);meta.update(countrycode=code,country=REGIONS[code],region_source='owner')
                db.execute('UPDATE radio_feeds SET metadata=? WHERE id=?',(json.dumps(meta),r['id']))
            return {'id':r['id'],'countrycode':code}
        url=r.get('url','');public_http.target(url);ident=hashlib.sha256(url.encode()).hexdigest()[:32]
        with self.ctx.state.connect() as db:
            if db.execute('SELECT count(*) FROM radio_feeds').fetchone()[0]>=50 and not db.execute('SELECT id FROM radio_feeds WHERE id=?',(ident,)).fetchone():raise ValueError('50 podcast feeds maximum')
            db.execute('INSERT OR IGNORE INTO radio_feeds VALUES(?,?,?,?,NULL)',(ident,url,'Podcast subscription',json.dumps({'countrycode':code,'country':REGIONS[code],'region_source':'owner'})))
            db.execute("UPDATE radio_feeds SET metadata=json_set(metadata,'$.countrycode',?,'$.country',?,'$.region_source','owner') WHERE id=?",(code,REGIONS[code],ident))
        return self.feed_refresh({'id':ident})

    def feed_refresh(self,r):
        with self.ctx.state.connect() as db:row=db.execute('SELECT * FROM radio_feeds WHERE id=?',(r.get('id'),)).fetchone()
        if not row:raise ValueError('Podcast subscription not found')
        savedmeta=json.loads(row['metadata']);code=origin(savedmeta)
        if not code:raise ValueError('Confirm this podcast service is in the United States or Canada first')
        try:raw=public_http.fetch(row['url'],2*1024**2)
        except ValueError as error:
            if str(error)!='Internet response exceeded the size limit':raise
            from .podcast_feed import fetch
            raw=fetch(row['url'])
        normalized=raw.replace(b'\x00',b'').upper()
        if b'<!DOCTYPE' in normalized or b'<!ENTITY' in normalized:raise ValueError('Podcast feed contains an unsafe XML declaration')
        try:root=ET.fromstring(raw)
        except ET.ParseError:raise ValueError('Invalid podcast XML') from None
        channel=root.find('channel')
        if channel is None:channel=root
        def find(node,key,default=''):
            return next((''.join(n.itertext()).strip()[:10000] for n in node if n.tag.split('}')[-1]==key),default)
        title=find(channel,'title','Podcast')[:500];description=(find(channel,'description') or find(channel,'subtitle'))[:4000]
        feedmeta={'countrycode':code,'country':REGIONS[code],'region_source':'owner','description':description,'author':find(channel,'author') or find(channel,'managingEditor'),'source_host':urllib.parse.urlsplit(row['url']).hostname}
        items=[n for n in channel if n.tag.split('}')[-1] in ('item','entry')]
        count=0
        for item in items[:300]:
            enclosures=[n for n in item if n.tag.split('}')[-1]=='enclosure' or (n.tag.split('}')[-1]=='link' and n.get('rel')=='enclosure')]
            if not enclosures:continue
            enclosure=enclosures[0];url=enclosure.get('url') or enclosure.get('href')
            if not url:continue
            try:
                parsed=urllib.parse.urlsplit(url)
                if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:continue
            except ValueError:continue
            guid=find(item,'guid') or find(item,'id') or url;ident=hashlib.sha256((row['id']+'\0'+guid).encode()).hexdigest()[:32]
            meta={'description':(find(item,'description') or find(item,'summary'))[:2000],'published':find(item,'pubDate') or find(item,'published'),'author':find(item,'author',feedmeta['author']),'series':title,'content_type':enclosure.get('type','audio/mpeg'),'duration':find(item,'duration')}
            with self.ctx.state.connect() as db:db.execute('INSERT INTO radio_episodes(id,feed,title,url,metadata) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,url=excluded.url,metadata=excluded.metadata',(ident,row['id'],find(item,'title','Episode')[:500],url,json.dumps(meta)))
            count+=1
        with self.ctx.state.connect() as db:db.execute('UPDATE radio_feeds SET title=?,metadata=?,checked=? WHERE id=?',(title,json.dumps(feedmeta),time.time(),row['id']))
        return {'id':row['id'],'title':title,'episodes':count,'downloaded_originals_retained':True}

    def episode_download(self,r,enqueue):
        with self.ctx.state.connect() as db:row=db.execute('SELECT * FROM radio_episodes WHERE id=?',(r.get('id'),)).fetchone()
        if not row:raise ValueError('Choose a podcast episode')
        with self.ctx.state.connect() as db:feed=db.execute('SELECT metadata FROM radio_feeds WHERE id=?',(row['feed'],)).fetchone()
        if not feed or not origin(json.loads(feed[0])):raise ValueError('Confirm the podcast service region before downloading')
        if row['asset']:return {'item':self.public(self.asset(row['asset'])),'already_downloaded':True}
        ext=Path(urllib.parse.urlsplit(row['url']).path).suffix.lower()
        if ext not in AUDIO:ext='.mp3'
        label=re.sub(r'[/\\\x00-\x1f]','_',row['title'])[:140]+ext
        result=self.queue_url({'category':'podcasts','name':label,'url':row['url']},enqueue,episode_id=row['id'])
        return result

    def refresh_due_feeds(self):
        if not self.config().get('podcast_auto_refresh'):return
        with self.ctx.state.connect() as db:rows=db.execute("SELECT id FROM radio_feeds WHERE (checked IS NULL OR checked<?) AND json_extract(metadata,'$.countrycode') IN ('US','CA') ORDER BY checked LIMIT 10",(time.time()-6*3600,)).fetchall()
        for row in rows:
            try:self.feed_refresh({'id':row[0]})
            except (ValueError,OSError):self.ctx.state.set('myradio-feed-refresh-error',{'at':time.time(),'message':'A podcast feed could not be refreshed; earlier episodes and downloads were retained'})
