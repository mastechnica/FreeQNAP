"""Short-lived, authenticated-console selections for streaming ZIP downloads.

Tickets never bypass the HTTP administrator session. No archive is staged on
an OS/data disk for browser downloads; contents remain descriptor-guarded reads.
"""
import hashlib,json,os,re,secrets,stat,time
from pathlib import Path
from .files import relative
from .fileops import fingerprint
from .common import canonical

class Bundles:
    def __init__(self,ctx,files):self.ctx=ctx;self.files=files
    def selection(self,request):
        paths=request.get('paths');share=request.get('share');filename=request.get('filename','download.zip')
        if not isinstance(paths,list) or not 1<=len(paths)<=200 or any(not isinstance(p,str) for p in paths) or len(set(paths))!=len(paths):raise ValueError('Choose 1–200 distinct items or one folder')
        if len(relative(filename))!=1 or not filename.lower().endswith('.zip') or any(ord(c)<32 for c in filename):raise ValueError('Choose one ZIP filename')
        roots=[]
        for path in paths:
            parts=relative(path)
            if any(other!=path and (not other or Path(other) in Path(path).parents) for other in paths):raise ValueError('Choose a folder or its children, not both')
            with self.files.directory(share,str(Path(*parts[:-1])) if parts else '') as (fd,mapping,pool):
                info=os.stat(parts[-1],dir_fd=fd,follow_symlinks=False) if parts else os.fstat(fd)
                if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)) or info.st_dev!=os.fstat(fd).st_dev:raise ValueError('Choose regular files/folders; symlinks and nested filesystems are excluded')
                roots.append({'path':path,'name':parts[-1] if parts else mapping['name'],'identity':fingerprint(info),'directory':stat.S_ISDIR(info.st_mode)})
        if len({r['name'] for r in roots})!=len(roots):raise ValueError('Archive root names collide')
        return {'share':share,'share_path':mapping['path'],'pool':pool['name'],'filesystem_uuid':pool['filesystem_uuid'],'roots':roots,'filename':filename}
    def start(self,request):
        record=self.selection(request);now=time.time();ident=secrets.token_hex(16)
        with self.ctx.state.connect() as db:
            rows=db.execute("SELECT key,value FROM settings WHERE key LIKE 'bundle:%'").fetchall();active=0
            for row in rows:
                value=json.loads(row['value'])
                if value['expires_at']<now:db.execute('DELETE FROM settings WHERE key=?',(row['key'],))
                else:active+=1
            if active>=64:raise ValueError('Too many active ZIP downloads; wait for existing selections to expire')
        record.update(id=ident,created_at=now,expires_at=now+3600,last_renewed=now,maximum_end=now+7*86400);self.ctx.state.set('bundle:'+ident,record)
        return {'ticket':ident,'filename':record['filename'],'expires_at':record['expires_at']}
    def get(self,request,path=None):
        ident=request.get('ticket')
        if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{32}',ident):raise ValueError('Unknown ZIP selection')
        record=self.ctx.state.setting('bundle:'+ident);now=time.time()
        if not record or record['expires_at']<now or record['maximum_end']<now:raise ValueError('ZIP selection expired; select files again')
        pool,_=(self.files.validate_volume(record['pool']) if hasattr(self.files,'validate_volume') else self.ctx.volume(record['pool']));share=self.files.mapping(record['share'])
        if pool['filesystem_uuid']!=record['filesystem_uuid'] or not share or share['path']!=record['share_path'] or share['pool']!=record['pool']:raise ValueError('ZIP selection mapping changed')
        if now-record['last_renewed']>=60:record.update(last_renewed=now,expires_at=min(now+3600,record['maximum_end']));self.ctx.state.set('bundle:'+ident,record)
        if path is not None:
            relative(path);roots=[r for r in record['roots'] if not r['path'] or path==r['path'] or (r['directory'] and path.startswith(r['path']+'/'))]
            if len(roots)!=1:raise ValueError('Path is outside the selected ZIP items')
            root=roots[0];parts=relative(root['path'])
            with self.files.directory(record['share'],str(Path(*parts[:-1])) if parts else '') as (fd,_,_):
                info=os.stat(parts[-1],dir_fd=fd,follow_symlinks=False) if parts else os.fstat(fd)
                if fingerprint(info)!=root['identity']:raise ValueError('Selected item changed during download')
        return record
    def info(self,request):
        record=self.get(request)
        return {'ticket':record['id'],'filename':record['filename'],'roots':[{'path':r['path'],'name':r['name']} for r in record['roots']]}
    def node(self,request):
        path=request.get('path','');record=self.get(request,path);parts=relative(path)
        with self.files.directory(record['share'],str(Path(*parts[:-1])) if parts else '') as (fd,_,_):
            info=os.stat(parts[-1],dir_fd=fd,follow_symlinks=False) if parts else os.fstat(fd)
            if info.st_dev!=os.fstat(fd).st_dev or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):raise ValueError('ZIP refuses symlinks, special files and nested filesystems')
            etag=hashlib.sha256(canonical(fingerprint(info))).hexdigest();directory=stat.S_ISDIR(info.st_mode)
        if request.get('expected_etag') and request['expected_etag']!=etag:raise ValueError('Folder changed between ZIP index pages')
        result={'directory':directory,'bytes':info.st_size,'modified_at':info.st_mtime,'etag':etag}
        if directory:result.update(self.files.list({'share':record['share'],'path':path,'offset':request.get('offset',0),'limit':500}))
        return result
    def read(self,request):
        path=request.get('path','');record=self.get(request,path)
        return self.files.read({'share':record['share'],'path':path,'offset':request.get('offset',0),'count':request.get('count',512*1024)})
