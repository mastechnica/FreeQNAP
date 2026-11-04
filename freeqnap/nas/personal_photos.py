"""Private, append-only photo archive. No remote/local deletion or public exports."""
import base64,contextlib,hashlib,json,math,os,re,secrets,sqlite3,stat,threading,time
from pathlib import Path
from .common import name
from .library_lock import serialized
from .library_storage_source import source_directory
from .files import Files,relative
from .personal_metadata import inspect,jpeg

PHOTO={'.jpg','.jpeg','.heic','.heif','.png','.gif','.webp','.tif','.tiff','.dng','.avif','.bmp','.cr2','.cr3','.crw','.arw','.raf','.rw2','.nrw','.nef','.orf','.pef','.raw'}
VIDEO={'.mov','.mp4','.m4v','.mkv','.webm','.avi','.mts','.3gp'}
IDENT=re.compile(r'[a-f0-9]{64}\Z')

def text(v,maximum=500):
    if not isinstance(v,str) or len(v)>maximum or any(ord(c)<32 for c in v):raise ValueError('Invalid photo text')
    return v

def digest(v):return hashlib.sha256(v.encode()).hexdigest()

@contextlib.contextmanager
def directory(fd,parts,create=False):
    current=os.dup(fd)
    try:
        device=os.fstat(fd).st_dev
        for part in parts:
            if part in ('','.','..') or '/' in part:raise ValueError('Invalid archive path')
            if create:
                try:os.mkdir(part,0o700,dir_fd=current)
                except FileExistsError:pass
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=current)
            if os.fstat(child).st_dev!=device:os.close(child);raise ValueError('Nested mounts are not allowed in the private library')
            os.close(current);current=child
        yield current
    finally:os.close(current)

class PersonalPhotos:
    def __init__(self,ctx,extract=inspect,preview=jpeg):
        self.storage_lock=threading.RLock();self.ctx=ctx;self.extract=extract;self.preview=preview;self.busy=threading.Lock();self.stop=threading.Event();self.preview_slot=threading.BoundedSemaphore(1)
        with ctx.state.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS personal_assets(id TEXT PRIMARY KEY,name TEXT NOT NULL,kind TEXT NOT NULL,taken TEXT,latitude REAL,longitude REAL,camera TEXT,bytes INTEGER NOT NULL,path TEXT NOT NULL,inode INTEGER NOT NULL,mtime_ns INTEGER NOT NULL,metadata TEXT NOT NULL,group_id TEXT NOT NULL,favorite INTEGER NOT NULL DEFAULT 0,caption TEXT NOT NULL DEFAULT '',created REAL NOT NULL); CREATE INDEX IF NOT EXISTS personal_taken ON personal_assets(taken); CREATE INDEX IF NOT EXISTS personal_groups ON personal_assets(group_id); CREATE TABLE IF NOT EXISTS personal_sources(id TEXT PRIMARY KEY,revision TEXT NOT NULL,asset TEXT,status TEXT NOT NULL,partial TEXT,attempts INTEGER NOT NULL DEFAULT 0,error TEXT,updated REAL NOT NULL); CREATE TABLE IF NOT EXISTS personal_albums(id TEXT PRIMARY KEY,title TEXT NOT NULL); CREATE TABLE IF NOT EXISTS personal_album_items(album TEXT NOT NULL,asset TEXT NOT NULL,PRIMARY KEY(album,asset));''')
        with ctx.state.connect() as db:
            columns={r[1] for r in db.execute('PRAGMA table_info(personal_sources)')}
            for field,declaration in [('verified_bytes','INTEGER NOT NULL DEFAULT 0'),('prefix_sha256',"TEXT NOT NULL DEFAULT ''"),('filename',"TEXT NOT NULL DEFAULT ''"),('total_bytes','INTEGER NOT NULL DEFAULT 0')]:
                if field not in columns:db.execute('ALTER TABLE personal_sources ADD COLUMN '+field+' '+declaration)
    def config(self):return self.ctx.state.setting('personal-photos',{})
    @serialized
    def configure(self,r):
        if self.busy.locked():raise ValueError('Pause and wait for the current photo operation first')
        pool_id=name(r.get('pool'));label=text(r.get('folder','PersonalPhotos'),120).strip()
        if not label:raise ValueError('Give your private library a name')
        folder='.freeqnap-photos-'+digest(label)[:16];parts=(folder,)
        if not parts:raise ValueError('Choose a dedicated folder, not the whole volume')
        pool,mount=self.ctx.volume(pool_id)
        if pool.get('read_only'):raise ValueError('Choose a writable data volume')
        old=self.config()
        if old and (old['pool']!=pool_id or old['folder']!=folder):raise ValueError('The existing archive is retained; moving an archive requires a separate migration')
        archive_id=old.get('archive_id') or secrets.token_hex(16)
        with Files(self.ctx).directory('pool:'+pool_id) as (root,_,_):
            with directory(root,parts,True) as fd:
                marker='.freeqnap-photo-library.json';expected={'archive_id':archive_id,'filesystem_uuid':pool['filesystem_uuid']}
                if not old:
                    if os.listdir(fd):raise ValueError('Choose a new empty folder for the private archive')
                    stream=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
                    try:os.write(stream,json.dumps(expected).encode());os.fsync(stream)
                    finally:os.close(stream)
                else:
                    stream=os.open(marker,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
                    try:
                        if json.loads(os.read(stream,4096))!=expected:raise ValueError('Archive identity changed')
                    finally:os.close(stream)
                os.fchmod(fd,0o700);os.fsync(fd)
        cfg={'pool':pool_id,'folder':folder,'label':label,'archive_id':archive_id,'filesystem_uuid':pool['filesystem_uuid'],'retention':'keep-forever','remote_deletions':False,'public_sharing':False}
        self.ctx.state.set('personal-photos',cfg);return cfg
    @contextlib.contextmanager
    def root(self):
        cfg=self.config()
        if not cfg:raise ValueError('Choose the private photo archive location first')
        pool,mount=self.ctx.volume(cfg['pool'])
        if pool['filesystem_uuid']!=cfg['filesystem_uuid']:raise ValueError('Photo archive volume identity changed')
        with Files(self.ctx).directory('pool:'+cfg['pool']) as (volume_fd,_,_):
          with directory(volume_fd,Path(cfg['folder']).parts) as fd:
            marker=os.open('.freeqnap-photo-library.json',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
            try:
                if json.loads(os.read(marker,4096))!={'archive_id':cfg['archive_id'],'filesystem_uuid':cfg['filesystem_uuid']}:raise ValueError('Photo archive marker changed')
            finally:os.close(marker)
            yield fd
    def status(self,r=None):
        with self.ctx.state.connect() as db:
            counts=dict(db.execute('SELECT kind,count(*) FROM personal_assets GROUP BY kind').fetchall());total=db.execute('SELECT count(*),COALESCE(sum(bytes),0),count(latitude) FROM personal_assets').fetchone();pending=db.execute("SELECT count(*) FROM personal_sources WHERE status!='complete'").fetchone()[0];pending_items=[dict(v) for v in db.execute("SELECT filename,verified_bytes,total_bytes,error,attempts FROM personal_sources WHERE status!='complete' ORDER BY updated DESC LIMIT 30")]
        online=False
        if self.config():
            try:
                with self.root():online=True
            except (ValueError,OSError):pass
        return {'config':self.config(),'online':online,'photos':counts.get('photo',0),'videos':counts.get('video',0),'files':total[0],'bytes':total[1],'located':total[2],'pending':pending,'pending_items':pending_items,'operation':self.ctx.state.setting('personal-photo-progress',{'state':'idle'}),'retention':'Keep downloaded originals indefinitely, including after iCloud deletion','sharing':'Private administrator access only','decoders':{k:bool(__import__('shutil').which(k)) for k in ('exiftool','ffmpeg')}}
    def asset(self,ident):
        if not isinstance(ident,str) or not IDENT.fullmatch(ident):raise ValueError('Choose a photo or video')
        with self.ctx.state.connect() as db:row=db.execute('SELECT * FROM personal_assets WHERE id=?',(ident,)).fetchone()
        if row is None:raise ValueError('Photo not found')
        return dict(row)
    @contextlib.contextmanager
    def opened(self,item):
        with self.root() as root:
            p=Path(item['path'])
            with directory(root,p.parts[:-1]) as parent:
                fd=os.open(p.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent)
                try:
                    st=os.fstat(fd)
                    if not stat.S_ISREG(st.st_mode) or st.st_dev!=os.fstat(root).st_dev or (st.st_ino,st.st_size,st.st_mtime_ns)!=(item['inode'],item['bytes'],item['mtime_ns']):raise ValueError('Original file identity changed; re-verification is required')
                    yield fd
                finally:os.close(fd)
    def progress(self,**v):self.ctx.state.set('personal-photo-progress',{'at':time.time(),**v})
    @serialized
    def ingest(self,source_id,revision,filename,opener,total,group=None,taken=None,metadata_override=None):
        """opener(offset) yields bytes from a validated range; partials survive failure."""
        filename=Path(text(filename)).name;ext=Path(filename).suffix.lower()
        if ext not in PHOTO|VIDEO:raise ValueError('Unsupported photo or video file type')
        if isinstance(total,bool) or not isinstance(total,int) or total<1:raise ValueError('An exact positive asset size is required')
        sid=digest(source_id+'\0'+revision);partial='part-'+sid
        with self.ctx.state.connect() as db:
            found=db.execute('SELECT * FROM personal_sources WHERE id=?',(sid,)).fetchone()
            if found and found['status']=='complete':
                existing=self.asset(found['asset'])
                with self.opened(existing):pass
                return {'id':existing['id'],'already_present':True}
            db.execute("INSERT INTO personal_sources(id,revision,status,partial,updated,filename,total_bytes,attempts) VALUES(?,?,'pending',?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET attempts=attempts+1,error=NULL,updated=excluded.updated",(sid,revision,partial,time.time(),filename,total))
        with self.root() as root:
            with directory(root,('incoming',),True) as incoming:
                fd=os.open(partial,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=incoming)
                try:
                    st=os.fstat(fd)
                    if not stat.S_ISREG(st.st_mode) or st.st_nlink not in (1,2) or st.st_dev!=os.fstat(root).st_dev or st.st_size>total:raise ValueError('Partial download identity is invalid')
                    verified=int(found['verified_bytes']) if found else 0
                    expected_prefix=found['prefix_sha256'] if found else ''
                    if not 0<=verified<=st.st_size:raise ValueError('Saved download checkpoint is inconsistent')
                    verified_hash=hashlib.sha256()
                    for off in range(0,verified,1024**2):verified_hash.update(os.pread(fd,min(1024**2,verified-off),off))
                    if verified and verified_hash.hexdigest()!=expected_prefix:raise ValueError('Partial download failed its saved prefix verification; retained for inspection')
                    if st.st_size>verified:
                        # An uncommitted tail after a process/power interruption is
                        # retained separately; it is never trusted as cloud bytes.
                        tail=partial+'-unverified-'+secrets.token_hex(4)
                        out=os.open(tail,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600,dir_fd=incoming)
                        try:
                            for off in range(verified,st.st_size,1024**2):os.write(out,os.pread(fd,min(1024**2,st.st_size-off),off))
                            os.fsync(out)
                        finally:os.close(out)
                        os.ftruncate(fd,verified);os.fsync(fd);os.fsync(incoming)
                    position=verified;stream_hash=verified_hash.copy();space=os.fstatvfs(root)
                    def checkpoint():
                        nonlocal verified,verified_hash
                        os.fsync(fd);readback=verified_hash.copy()
                        for off in range(verified,position,1024**2):readback.update(os.pread(fd,min(1024**2,position-off),off))
                        if readback.digest()!=stream_hash.digest():raise ValueError('Photo write/readback checksum mismatch; original not accepted')
                        with self.ctx.state.connect() as db:db.execute('UPDATE personal_sources SET verified_bytes=?,prefix_sha256=? WHERE id=?',(position,stream_hash.hexdigest(),sid))
                        verified=position;verified_hash=readback

                    if space.f_bavail*space.f_frsize<total-position+1024**3:raise ValueError('Not enough photo storage; keep at least 1 GiB free')
                    os.lseek(fd,position,os.SEEK_SET)
                    for chunk in (opener(position) if position<total else ()):
                        if self.stop.is_set():raise InterruptedError('Photo import paused; partial file retained')
                        if not isinstance(chunk,bytes) or len(chunk)>4*1024**2 or position+len(chunk)>total:raise ValueError('Invalid photo download length')
                        stream_hash.update(chunk);view=memoryview(chunk)
                        while view:
                            n=os.write(fd,view);position+=n;view=view[n:]
                        if position//(32*1024**2)!=(position-len(chunk))//(32*1024**2):
                            checkpoint();self.progress(state='downloading',file=filename,bytes=position,total_bytes=total)
                    if position!=total:raise ValueError('Incomplete photo download; partial file retained')
                    checkpoint();h=hashlib.sha256()
                    for off in range(0,total,1024**2):h.update(os.pread(fd,min(1024**2,total-off),off))
                    if h.digest()!=stream_hash.digest():raise ValueError('Final photo readback differs from downloaded bytes')
                    ident=h.hexdigest()
                    if st.st_nlink==2:
                        with directory(root,('originals',ident[:2])) as linked:
                            if os.stat(ident+ext,dir_fd=linked,follow_symlinks=False).st_ino!=st.st_ino:raise ValueError('Unexpected link to partial download')
                    meta=self.extract(fd,taken);meta.update(metadata_override or {});group_id=digest(group or meta.get('live_id') or ident)
                    with self.ctx.state.connect() as db:existing=db.execute('SELECT * FROM personal_assets WHERE id=?',(ident,)).fetchone()
                    if existing:
                        with self.opened(dict(existing)) as old:
                            verify=hashlib.sha256()
                            for off in range(0,total,1024**2):verify.update(os.pread(old,min(1024**2,total-off),off))
                            if verify.hexdigest()!=ident:raise ValueError('An existing original failed verification; it was not overwritten')
                        os.unlink(partial,dir_fd=incoming)
                    else:
                        target=ident+ext;path='originals/'+ident[:2]+'/'+target
                        with directory(root,('originals',ident[:2]),True) as out:
                            os.fchmod(fd,0o400)
                            try:os.link(partial,target,src_dir_fd=incoming,dst_dir_fd=out,follow_symlinks=False)
                            except FileExistsError:
                                # A crash may leave the durable original before its index row.
                                old=os.open(target,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=out)
                                try:
                                    check=hashlib.sha256();info=os.fstat(old)
                                    if info.st_size!=total or not stat.S_ISREG(info.st_mode):raise ValueError('Unindexed original differs; do not overwrite')
                                    for off in range(0,total,1024**2):check.update(os.pread(old,min(1024**2,total-off),off))
                                    if check.hexdigest()!=ident:raise ValueError('Unindexed original hash differs')
                                finally:os.close(old)
                            os.fsync(out);info=os.stat(target,dir_fd=out,follow_symlinks=False);os.unlink(partial,dir_fd=incoming);os.fsync(incoming)
                        with self.ctx.state.connect() as db:db.execute('INSERT INTO personal_assets(id,name,kind,taken,latitude,longitude,camera,bytes,path,inode,mtime_ns,metadata,group_id,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(ident,filename,'video' if ext in VIDEO else 'photo',meta.get('taken'),meta.get('latitude'),meta.get('longitude'),meta.get('camera'),total,path,info.st_ino,info.st_mtime_ns,json.dumps(meta),group_id,time.time()))
                    self.sidecar(ident)
                    with self.ctx.state.connect() as db:db.execute("UPDATE personal_sources SET asset=?,status='complete',error=NULL,updated=? WHERE id=?",(ident,time.time(),sid))
                    return {'id':ident,'already_present':bool(existing)}
                except Exception as error:
                    if 'checkpoint' in locals() and 'position' in locals():
                        try:checkpoint()
                        except Exception:pass
                    os.fsync(fd)
                    with self.ctx.state.connect() as db:db.execute("UPDATE personal_sources SET status='pending',error=?,updated=? WHERE id=?",('paused' if isinstance(error,InterruptedError) else 'Download or verification incomplete; original retained',time.time(),sid))
                    raise
                finally:os.close(fd)
    @serialized
    def sidecar(self,ident):
        item=self.asset(ident);item['metadata']=json.loads(item['metadata'])
        with self.root() as root:
            with directory(root,('metadata',),True) as fd:
                tmp=ident+'-'+secrets.token_hex(4)+'.next';out=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600,dir_fd=fd)
                try:os.write(out,(json.dumps(item,indent=2)+'\n').encode());os.fsync(out)
                finally:os.close(out)
                os.rename(tmp,ident+'.json',src_dir_fd=fd,dst_dir_fd=fd);os.fsync(fd)
    def scope(self,r):
        scope=r.get('_share_scope',{'mode':'library'})
        if scope.get('mode')=='library':return '1',[]
        ids=scope.get('ids')
        if not isinstance(ids,list) or not 1<=len(ids)<=1000 or any(not isinstance(v,str) for v in ids):raise ValueError('Invalid shared selection')
        if scope.get('mode')=='items' and all(IDENT.fullmatch(v) for v in ids):return 'id IN (SELECT value FROM json_each(?))',[json.dumps(ids)]
        if scope.get('mode')=='albums' and all(re.fullmatch('[a-f0-9]{32}',v) for v in ids):return 'id IN (SELECT asset FROM personal_album_items WHERE album IN (SELECT value FROM json_each(?)))',[json.dumps(ids)]
        raise ValueError('Invalid shared selection')
    def shared_view(self,operation,payload,scope):
        clause,params=self.scope({'_share_scope':scope})
        if operation=='photos.status':
            with self.ctx.state.connect() as db:rows=db.execute('SELECT kind,count(*) count,COALESCE(sum(bytes),0) bytes,count(latitude) located FROM personal_assets WHERE '+clause+' GROUP BY kind',params).fetchall()
            online=False
            try:
                with self.root():online=True
            except (ValueError,OSError):pass
            return {'photos':sum(v['count'] for v in rows if v['kind']=='photo'),'videos':sum(v['count'] for v in rows if v['kind']=='video'),'bytes':sum(v['bytes'] for v in rows),'located':sum(v['located'] for v in rows),'config':{'pool':'Shared library','location_selected':True},'online':online,'operation':{'state':'idle'}}
        if operation in ('photos.catalog','photos.places'):return getattr(self,operation.split('.')[1])({**payload,**({'include_versions':True} if scope.get('mode')!='library' else {}),'_share_scope':scope})
        ident=payload.get('id')
        with self.ctx.state.connect() as db:
            if not db.execute('SELECT 1 FROM personal_assets WHERE ('+clause+') AND id=?',(*params,ident)).fetchone():raise ValueError('This photo or video is not shared')
        if operation=='photos.read':return self.read(payload)
        if operation=='photos.metadata-read':return {**self.metadata_read(payload),'read_only':True}
        if operation=='photos.related':
            result=self.related(payload)
            with self.ctx.state.connect() as db:result['items']=[v for v in result['items'] if db.execute('SELECT 1 FROM personal_assets WHERE ('+clause+') AND id=?',(*params,v['id'])).fetchone()]
            return result
        raise ValueError('Shared library is read-only')
    def catalog(self,r):
        limit=r.get('limit',120);offset=r.get('offset',0)
        if type(limit)!=int or not 1<=limit<=200 or type(offset)!=int or not 0<=offset<=1000000:raise ValueError('Invalid photo page')
        scope_clause,scope_params=self.scope(r);clauses=[scope_clause];params=list(scope_params)
        if r.get('id'):
            if not isinstance(r['id'],str) or not IDENT.fullmatch(r['id']):raise ValueError('Invalid photo identifier')
            clauses.append('id=?');params.append(r['id'])
        elif not r.get('include_versions'):
            clauses.append("id=(SELECT b.id FROM personal_assets b WHERE b.group_id=personal_assets.group_id ORDER BY CASE WHEN b.kind='photo' THEN 0 ELSE 1 END,b.created DESC,b.id LIMIT 1)")
        if all(k in r for k in ('west','east','south','north')):
            west,east,south,north=self.bounds(r);clauses.extend(['longitude BETWEEN ? AND ?','latitude BETWEEN ? AND ?']);params.extend([west,east,south,north])
        for k,col in [('kind','kind'),('year','substr(taken,1,4)'),('month','substr(taken,1,7)')]:
            if r.get(k):clauses.append(col+'=?');params.append(text(r[k],20))
        if r.get('favorite') is True:clauses.append('favorite=1')
        if r.get('located') is True:clauses.append('latitude IS NOT NULL')
        if r.get('q'):
            q=text(r['q'],200);clauses.append("(name LIKE ? ESCAPE '\\' OR caption LIKE ? ESCAPE '\\' OR camera LIKE ? ESCAPE '\\')");pattern='%'+q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%';params.extend([pattern]*3)
        if r.get('album'):
            album=text(r['album'],64);clauses.append('id IN (SELECT asset FROM personal_album_items WHERE album=?)');params.append(album)
        where=' WHERE '+' AND '.join(clauses) if clauses else ''
        with self.ctx.state.connect() as db:
            total=db.execute('SELECT count(*) FROM personal_assets'+where,params).fetchone()[0]
            rows=db.execute('SELECT * FROM personal_assets'+where+' ORDER BY taken IS NULL,taken DESC,created DESC LIMIT ? OFFSET ?',(*params,limit,offset)).fetchall()
            years=[dict(v) for v in db.execute("SELECT substr(taken,1,4) year,count(*) count,max(id) cover FROM personal_assets WHERE taken IS NOT NULL AND ("+scope_clause+") GROUP BY year ORDER BY year DESC",scope_params)]
            months=[dict(v) for v in db.execute("SELECT substr(taken,1,7) month,count(*) count,max(id) cover FROM personal_assets WHERE taken IS NOT NULL AND ("+scope_clause+") GROUP BY month ORDER BY month DESC",scope_params)]
            if r.get('_share_scope',{}).get('mode')=='items':albums=[]
            else:
                album_filter=" WHERE a.id IN (SELECT value FROM json_each(?))" if r.get('_share_scope',{}).get('mode')=='albums' else ''
                albums=[dict(v) for v in db.execute('SELECT a.*,count(i.asset) count,max(i.asset) cover FROM personal_albums a LEFT JOIN personal_album_items i ON i.album=a.id AND i.asset IN (SELECT id FROM personal_assets WHERE '+scope_clause+')'+album_filter+' GROUP BY a.id ORDER BY a.title',(*scope_params,*([json.dumps(r['_share_scope']['ids'])] if album_filter else [])))]
        items=[]
        for row in rows:
            v=dict(row);v.pop('path');v.pop('inode');v.pop('mtime_ns');v['metadata']=json.loads(v['metadata']);v['favorite']=bool(v['favorite']);items.append(v)
        return {'items':items,'total':total,'offset':offset,'limit':limit,'years':years,'months':months,'albums':albums,'has_more':offset+len(items)<total}
    def bounds(self,r):
        values=[]
        for k,low,high in [('west',-180,180),('east',-180,180),('south',-90,90),('north',-90,90)]:
            v=r.get(k,low if k in ('west','south') else high)
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not low<=v<=high:raise ValueError('Invalid map bounds')
            values.append(v)
        if values[0]>values[1] or values[2]>values[3]:raise ValueError('Invalid map extent')
        return values
    def places(self,r):
        west,east,south,north=self.bounds(r);cell=r.get('cell',15)
        if isinstance(cell,bool) or not isinstance(cell,(int,float)) or not math.isfinite(cell) or not 0.000001<=cell<=30:raise ValueError('Invalid map scale')
        # Aggregate on the NAS: all located assets contribute without sending
        # millions of individual coordinates to a phone or external map service.
        clause,scope_params=self.scope(r)
        with self.ctx.state.connect() as db:
            rows=db.execute("SELECT CAST((longitude+180)/? AS INTEGER) gx,CAST((latitude+90)/? AS INTEGER) gy,count(*) count,avg(latitude) latitude,avg(longitude) longitude,max(id) id,max(taken) taken FROM personal_assets WHERE longitude BETWEEN ? AND ? AND latitude BETWEEN ? AND ? AND ("+clause+") GROUP BY gx,gy LIMIT 1801",(cell,cell,west,east,south,north,*scope_params)).fetchall()
        items=[]
        for row in rows[:1800]:
            v=dict(row);v.update(west=max(-180,v['gx']*cell-180),east=min(180,(v['gx']+1)*cell-180),south=max(-90,v['gy']*cell-90),north=min(90,(v['gy']+1)*cell-90));items.append(v)
        return {'items':items,'total':sum(v['count'] for v in items),'truncated':len(rows)>1800,'offline_map':True}
    @serialized
    def annotate(self,r):
        item=self.asset(r.get('id'));favorite=r.get('favorite',bool(item['favorite']));caption=text(r.get('caption',item['caption']),4000)
        if not isinstance(favorite,bool):raise ValueError('Choose favorite on or off')
        with self.ctx.state.connect() as db:db.execute('UPDATE personal_assets SET favorite=?,caption=? WHERE id=?',(int(favorite),caption,item['id']))
        self.sidecar(item['id']);return {'saved':True,'original_unchanged':True}
    @serialized
    def album(self,r):
        title=text(r.get('title'),120).strip()
        if not title:raise ValueError('Give the album a name')
        ident=secrets.token_hex(16)
        with self.ctx.state.connect() as db:db.execute('INSERT INTO personal_albums VALUES(?,?)',(ident,title))
        return {'id':ident,'title':title}
    @serialized
    def album_add(self,r):
        item=self.asset(r.get('id'));album=text(r.get('album'),32)
        with self.ctx.state.connect() as db:
            if not db.execute('SELECT 1 FROM personal_albums WHERE id=?',(album,)).fetchone():raise ValueError('Choose an existing album')
            db.execute('INSERT OR IGNORE INTO personal_album_items VALUES(?,?)',(album,item['id']))
        return {'saved':True}
    @serialized
    def read(self,r):
        item=self.asset(r.get('id'));variant=r.get('variant','original');offset=r.get('offset',0);count=r.get('count',512*1024)
        if variant not in ('original','thumbnail','preview') or type(offset)!=int or not 0<=offset<=max(item['bytes'],8*1024**2) or type(count)!=int or not 1<=count<=512*1024:raise ValueError('Invalid photo read')
        if variant=='original':
            with self.opened(item) as fd:data=os.pread(fd,count,offset)
            return {'filename':item['name'],'total_bytes':item['bytes'],'etag':item['id'],'data_base64':base64.b64encode(data).decode()}
        cache=item['id']+'-'+variant+'.jpg'
        with self.root() as root:
            with directory(root,('previews',),True) as folder:
                try:fd=os.open(cache,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=folder)
                except FileNotFoundError:
                    if not self.preview_slot.acquire(timeout=1):raise ValueError('Photo preview is busy; try again shortly')
                    try:
                        with self.opened(item) as original:data=self.preview(original,variant=='preview')
                    finally:self.preview_slot.release()
                    if not data.startswith(b'\xff\xd8') or len(data)>8*1024**2:raise ValueError('JPEG preview unavailable')
                    tmp=cache+'-'+secrets.token_hex(4)+'.next';out=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=folder)
                    try:os.write(out,data);os.fsync(out)
                    finally:os.close(out)
                    os.rename(tmp,cache,src_dir_fd=folder,dst_dir_fd=folder);fd=os.open(cache,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=folder)
                try:
                    info=os.fstat(fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_size>8*1024**2:raise ValueError('Preview cache invalid')
                    data=os.pread(fd,count,offset)
                    return {'filename':item['id']+'.jpg','total_bytes':info.st_size,'etag':item['id']+'-'+variant,'data_base64':base64.b64encode(data).decode()}
                finally:os.close(fd)
    def import_folder(self,r):
        if not self.busy.acquire(False):raise ValueError('A photo operation is already running')
        try:
            pool=name(r.get('pool')) if 'pool' in r else None;share=r.get('share') if pool is None else 'pool:'+pool;folder=text(r.get('folder',''),2048);relative(folder)
            if pool is not None and 'share' in r:raise ValueError('Choose one source volume or folder')
            with self.root():pass
            with source_directory(self.ctx,share,folder):pass
            if pool==self.config().get('pool') and (folder==self.config()['folder'] or folder.startswith(self.config()['folder']+'/')):raise ValueError('Do not import the archive into itself')
            self.stop.clear();self.progress(state='scanning',source='local folder')
            t=threading.Thread(target=self._import,args=(pool,folder,share),daemon=True);t.start();return {'started':True}
        except Exception:self.busy.release();raise
    @serialized
    def _import(self,pool,folder,share=None):
        done=failed=0
        try:
            with source_directory(self.ctx,share or 'pool:'+pool,folder) as (root,_,volume):
                stack=[(os.dup(root),'')];seen=0
                try:
                    while stack and not self.stop.is_set():
                        fd,prefix=stack.pop()
                        try:
                            for n in os.listdir(fd):
                                if n.startswith('.') or self.stop.is_set():continue
                                info=os.stat(n,dir_fd=fd,follow_symlinks=False)
                                if info.st_dev!=os.fstat(root).st_dev:continue
                                if stat.S_ISDIR(info.st_mode) and pool==self.config().get('pool') and str(Path(folder)/prefix/n)==self.config()['folder']:continue
                                if stat.S_ISDIR(info.st_mode):stack.append((os.open(n,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd),prefix+n+'/'));continue
                                if not stat.S_ISREG(info.st_mode) or Path(n).suffix.lower() not in PHOTO|VIDEO:continue
                                seen+=1
                                if seen>1000000:raise ValueError('Folder import limit reached; previous originals retained')
                                source=os.open(n,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
                                try:
                                    before=os.fstat(source)
                                    def chunks(offset):
                                        while offset<before.st_size:
                                            data=os.pread(source,min(1024**2,before.st_size-offset),offset)
                                            if not data:break
                                            offset+=len(data);yield data
                                        after=os.fstat(source)
                                        if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):raise ValueError('Source changed during import')
                                    from .file_metadata import read_xmp
                                    self.ingest('local:'+volume['filesystem_uuid']+':'+folder+'/'+prefix+n,str(before.st_size)+':'+str(before.st_mtime_ns),n,chunks,before.st_size,group='local:'+volume['filesystem_uuid']+':'+folder+'/'+prefix+Path(n).stem,metadata_override=read_xmp(fd,n))
                                    done+=1
                                except (ValueError,OSError):failed+=1
                                finally:os.close(source)
                                self.progress(state='importing',completed=done,failed=failed,file=n)
                        finally:os.close(fd)
                finally:
                    for fd,_ in stack:os.close(fd)
            self.progress(state='paused' if self.stop.is_set() else 'complete-with-errors' if failed else 'complete',completed=done,failed=failed)
        except Exception:self.progress(state='needs-attention',completed=done,failed=failed,message='Import stopped; previous originals and partial files retained')
        finally:self.busy.release()
    def pause(self,r):self.stop.set();return {'pause_requested':True,'originals_retained':True}

    def related(self,r):
        item=self.asset(r.get('id'))
        with self.ctx.state.connect() as db:rows=db.execute('SELECT id,name,kind,bytes FROM personal_assets WHERE group_id=? ORDER BY kind,created',(item['group_id'],)).fetchall()
        return {'items':[dict(v) for v in rows]}

    @serialized
    def metadata_read(self,r):
        from .file_metadata import current
        item=self.asset(r.get('id'));parts=Path(item['path']).parts;extra=json.loads(item['metadata']);extra['description']=item['caption'] or extra.get('description','')
        with self.opened(item) as source,self.root() as root,directory(root,parts[:-1]) as parent:return current(source,parent,parts[-1],extra)
    @serialized
    def metadata_plan(self,r):
        from .file_metadata import clean
        if set(r)!={'id','etag','metadata'}:raise ValueError('Choose an item and metadata')
        fresh=self.metadata_read(r)
        if fresh['etag']!=r['etag']:raise ValueError('Metadata changed; reopen the editor')
        return self.ctx.plan('photo-metadata',{'id':r['id'],'etag':r['etag'],'metadata':clean(r['metadata']),'review':'Update the private catalog and XMP sidecar. Original bytes and embedded EXIF remain unchanged. GPS/date edits update the gallery/map; previous sidecar is retained.'},'SAVE PHOTO METADATA')
    def metadata_apply(self,r):
        from .file_metadata import write
        with self.ctx.lock(),self.storage_lock:
            path,plan=self.ctx.reviewed(r,'photo-metadata');b=plan['body'];fresh=self.metadata_read(b)
            if fresh['etag']!=b['etag']:raise ValueError('Metadata changed after review')
            item=self.asset(b['id']);parts=Path(item['path']).parts;meta=json.loads(item['metadata']);meta.update(b['metadata'])
            with self.root() as root,directory(root,parts[:-1]) as parent:
                self.ctx.consume(path,plan);result=write(parent,parts[-1],b['metadata'])
            with self.ctx.state.connect() as db:db.execute('UPDATE personal_assets SET taken=?,latitude=?,longitude=?,camera=?,metadata=?,caption=? WHERE id=?',(meta['taken'],meta['latitude'],meta['longitude'],meta.get('camera'),json.dumps(meta),meta['description'],item['id']))
            self.sidecar(item['id']);return result
