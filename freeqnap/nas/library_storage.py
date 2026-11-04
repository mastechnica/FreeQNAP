"""Reviewed private-library placement; verified copies retain the previous archive."""
import hashlib,json,os,secrets,stat
from pathlib import Path
from .files import Files,relative
from .personal_photos import directory
from .common import name

class LibraryStorage:
    def __init__(self,ctx,radio,photos):
        self.ctx=ctx;self.engines={'radio':radio,'photos':photos}
        with ctx.lock():
            self.owner=ctx.state.setting('personal-library-owner',{})
            if not self.owner:
                self.owner={'id':secrets.token_hex(16),'label':'Administrator'};ctx.state.set('personal-library-owner',self.owner)
    def engine(self,kind):
        if kind not in self.engines:raise ValueError('Choose Music or Personal Photos & Videos')
        return self.engines[kind]
    def plan(self,r):
        if set(r)!={'library','pool','folder'}:raise ValueError('Choose library, volume and dedicated folder')
        engine=self.engine(r['library']);pool,mount=self.ctx.volume(name(r['pool']))
        if pool.get('read_only'):raise ValueError('Choose a writable volume')
        if not isinstance(r['folder'],str) or any(ord(c)<32 for c in r['folder']):raise ValueError('Choose a plain folder path')
        parts=relative(r['folder'])
        if not parts or len(parts)>12:raise ValueError('Choose a dedicated folder inside the volume')
        folder=str(Path(*parts));old=engine.config()
        return self.ctx.plan('library-storage',{'library':r['library'],'pool':pool['name'],'filesystem_uuid':pool['filesystem_uuid'],'folder':folder,'before':old,'review':'Copy and verify the private library at this location; retain the previous archive. Files placed in the visible folder can be imported from File Manager. No disks are formatted.'},'SET LIBRARY LOCATION')
    def apply(self,r):
        with self.ctx.lock():
            path,plan=self.ctx.reviewed(r,'library-storage');body=plan['body'];engine=self.engine(body['library'])
            with engine.storage_lock:
                old=engine.config()
                if old!=body['before']:raise ValueError('Library settings changed; choose the location again')
                if body['library']=='photos' and engine.busy.locked():raise ValueError('Pause and wait for photo imports before changing storage')
                pool,mount=self.ctx.volume(body['pool'])
                if pool['filesystem_uuid']!=body['filesystem_uuid'] or pool.get('read_only'):raise ValueError('Destination volume identity or access changed')
                leaf='.freeqnap-myradio' if body['library']=='radio' else '.freeqnap-photo-archive'
                destination=str(Path(body['folder'])/leaf)
                if old and old['pool']==body['pool'] and old['folder']==destination:
                    self.ctx.consume(path,plan);return {'configured':True,'unchanged':True}
                with Files(self.ctx).directory('pool:'+body['pool']) as (root,_,_):
                    with directory(root,Path(body['folder']).parts,True) as container:
                        if leaf in os.listdir(container):raise ValueError('This destination already contains a private library; choose another folder')
                        # Consume before the first archive write. Interrupted destinations
                        # remain retained and cannot be merged or overwritten on retry.
                        self.ctx.consume(path,plan)
                        os.mkdir(leaf,0o700,dir_fd=container);os.fsync(container)
                        with directory(container,(leaf,)) as target:
                            if old:
                                table='radio_assets' if body['library']=='radio' else 'personal_assets'
                                with self.ctx.state.connect() as db:identifiers=[v[0] for v in db.execute('SELECT id FROM '+table)]
                                for ident in identifiers:
                                    with engine.opened(engine.asset(ident)):pass
                                with engine.root() as source:
                                    count,total=self.measure(source)
                                    space=os.fstatvfs(target)
                                    if total+1024**3>space.f_bavail*space.f_frsize:raise ValueError('Not enough space; keep at least 1 GiB free')
                                    self.copy(source,target)
                                cfg={**old,'pool':body['pool'],'folder':destination,'filesystem_uuid':pool['filesystem_uuid']}
                            elif body['library']=='radio':
                                cfg={'pool':body['pool'],'folder':destination,'filesystem_uuid':pool['filesystem_uuid'],'library_id':secrets.token_hex(16),'scan_enabled':True,'folders':{'music':True,'books':True,'podcasts':True},'musicbrainz':False,'openlibrary':False,'save_sidecars':True,'podcast_auto_refresh':False}
                                for part in ('music','books','podcasts','incoming'):
                                    with directory(target,(part,),True):pass
                            else:
                                cfg={'pool':body['pool'],'folder':destination,'filesystem_uuid':pool['filesystem_uuid'],'archive_id':secrets.token_hex(16),'retention':'keep-forever','remote_deletions':False,'public_sharing':False}
                            history=list(old.get('previous_locations',[]))
                            if old:history.append({k:old[k] for k in ('pool','folder','filesystem_uuid')})
                            cfg.update(location_selected=True,location_folder=body['folder'],previous_locations=history,owner_id=old.get('owner_id',self.owner['id']),owner_label=old.get('owner_label',self.owner['label']))
                            if body['library']=='photos':cfg['label']=body['folder']
                            marker='.library.json' if body['library']=='radio' else '.freeqnap-photo-library.json'
                            identity={'library_id':cfg['library_id'],'filesystem_uuid':cfg['filesystem_uuid']} if body['library']=='radio' else {'archive_id':cfg['archive_id'],'filesystem_uuid':cfg['filesystem_uuid']}
                            self.marker(target,marker,identity)
                            table='radio_assets' if body['library']=='radio' else 'personal_assets'
                            updates=[]
                            with self.ctx.state.connect() as db:
                                for item in db.execute('SELECT id,path,bytes FROM '+table):
                                    with directory(target,Path(item['path']).parts[:-1]) as parent:
                                        info=os.stat(Path(item['path']).name,dir_fd=parent,follow_symlinks=False)
                                        if not stat.S_ISREG(info.st_mode) or info.st_size!=item['bytes']:raise ValueError('Copied original identity does not match the library')
                                        updates.append((info.st_ino,info.st_mtime_ns,item['id']))
                                # One transaction switches both lookup identities and config.
                                db.executemany('UPDATE '+table+' SET inode=?,mtime_ns=? WHERE id=?',updates)
                                key='myradio' if body['library']=='radio' else 'personal-photos'
                                db.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(cfg)))
                            os.fsync(target)
                if hasattr(self.ctx,'save_locations'):self.ctx.save_locations()
                return {'configured':True,'config':cfg,'previous_archive_retained':bool(old)}
    def measure(self,fd,depth=0):
        if depth>40:raise ValueError('Library nesting limit exceeded')
        total=count=0;device=os.fstat(fd).st_dev
        for leaf in os.listdir(fd):
            info=os.stat(leaf,dir_fd=fd,follow_symlinks=False)
            if info.st_dev!=device:raise ValueError('Nested library mount refused')
            if stat.S_ISDIR(info.st_mode):
                with directory(fd,(leaf,)) as child:n,b=self.measure(child,depth+1)
                count+=n;total+=b
            elif stat.S_ISREG(info.st_mode):count+=1;total+=info.st_size
            else:raise ValueError('Library contains a link or unsupported file; previous archive retained')
            if count>1000000:raise ValueError('Library file limit exceeded')
        return count,total
    def copy(self,source,target,depth=0):
        if depth>40:raise ValueError('Library nesting limit exceeded')
        device=os.fstat(source).st_dev
        for leaf in os.listdir(source):
            info=os.stat(leaf,dir_fd=source,follow_symlinks=False)
            if info.st_dev!=device:raise ValueError('Nested library mount refused')
            if stat.S_ISDIR(info.st_mode):
                with directory(source,(leaf,)) as src,directory(target,(leaf,),True) as dst:self.copy(src,dst,depth+1)
            elif stat.S_ISREG(info.st_mode):
                src=os.open(leaf,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=source);dst=os.open(leaf,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=target)
                try:
                    before=os.fstat(src)
                    if (before.st_ino,before.st_size,before.st_mtime_ns)!=(info.st_ino,info.st_size,info.st_mtime_ns):raise ValueError('Source changed before copying')
                    a=hashlib.sha256();b=hashlib.sha256()
                    while True:
                        data=os.read(src,1024**2)
                        if not data:break
                        a.update(data);view=memoryview(data)
                        while view:
                            written=os.write(dst,view)
                            if written<=0:raise OSError('Short library copy write')
                            view=view[written:]
                    os.fsync(dst);os.lseek(dst,0,0)
                    while True:
                        data=os.read(dst,1024**2)
                        if not data:break
                        b.update(data)
                    after=os.fstat(src)
                    if a.digest()!=b.digest() or (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):raise ValueError('Library copy verification failed; old location retained')
                    os.fchmod(dst,stat.S_IMODE(info.st_mode)&0o600)
                finally:os.close(src);os.close(dst)
            else:raise ValueError('Library contains a symbolic link or unsupported file')
        os.fsync(target)
    def marker(self,fd,leaf,value):
        # Copied marker is replaced inside the uncommitted new archive only.
        if leaf in os.listdir(fd):os.unlink(leaf,dir_fd=fd)
        stream=os.open(leaf,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600,dir_fd=fd)
        try:os.write(stream,json.dumps(value).encode());os.fsync(stream)
        finally:os.close(stream)
        os.fsync(fd)


class FileLocation:
    """A user's ordinary files folder; switching retains previous folders."""
    def __init__(self,ctx,owner):self.ctx=ctx;self.owner=owner
    def status(self,r=None):return {'config':self.ctx.state.setting('personal-files',{}),'previous_files_retained':True}
    def plan(self,r):
        if set(r)!={'pool','folder'}:raise ValueError('Choose a volume and personal folder')
        parts=relative(r['folder'])
        if not parts or any(ord(c)<32 for c in r['folder']):raise ValueError('Choose a dedicated folder inside the volume')
        pool,mount=self.ctx.volume(name(r['pool']))
        if pool.get('read_only'):raise ValueError('Choose a writable volume')
        return self.ctx.plan('personal-files-location',{'pool':pool['name'],'folder':str(Path(*parts)),'filesystem_uuid':pool['filesystem_uuid'],'before':self.status()['config'],'review':'Use this personal files folder. Previous folders and files stay in place; switching does not move or erase them. Copy files explicitly in File Manager.'},'SET PERSONAL FILES LOCATION')
    def apply(self,r):
        with self.ctx.lock():
            path,plan=self.ctx.reviewed(r,'personal-files-location');b=plan['body'];old=self.status()['config']
            if old!=b['before']:raise ValueError('Personal storage changed; choose again')
            pool,mount=self.ctx.volume(b['pool'])
            if pool['filesystem_uuid']!=b['filesystem_uuid'] or pool.get('read_only'):raise ValueError('Volume identity or access changed')
            with Files(self.ctx).directory('pool:'+b['pool']) as (root,_,_):
                with directory(root,Path(b['folder']).parts,True) as target:
                    marker='.freeqnap-personal-files.json';expected={'owner_id':self.owner['id'],'filesystem_uuid':pool['filesystem_uuid']}
                    if marker in os.listdir(target):
                        fd=os.open(marker,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=target)
                        try:
                            if json.loads(os.read(fd,4096))!=expected:raise ValueError('This personal folder belongs to a different identity')
                        finally:os.close(fd)
                    elif os.listdir(target):raise ValueError('Choose an empty new folder for personal files')
                    self.ctx.consume(path,plan)
                    if marker not in os.listdir(target):
                        fd=os.open(marker,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600,dir_fd=target)
                        try:os.write(fd,json.dumps(expected).encode());os.fsync(fd)
                        finally:os.close(fd)
                    os.fsync(target)
            history=list(old.get('previous_locations',[]))
            if old and (old['pool'],old['folder'])!=(b['pool'],b['folder']):history.append({k:old[k] for k in ('pool','folder','filesystem_uuid')})
            cfg={'pool':b['pool'],'folder':b['folder'],'location_folder':b['folder'],'filesystem_uuid':b['filesystem_uuid'],'location_selected':True,'owner_id':self.owner['id'],'owner_label':self.owner['label'],'previous_locations':history};self.ctx.state.set('personal-files',cfg)
            if hasattr(self.ctx,'save_locations'):self.ctx.save_locations()
            return {'configured':True,'config':cfg,'previous_files_retained':True}
