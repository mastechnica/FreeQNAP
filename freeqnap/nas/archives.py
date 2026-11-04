"""Reviewed ZIP creation/extraction, private data-volume stages, no replacement."""
import hashlib,json,os,re,secrets,stat,zipfile
from pathlib import Path
from .files import relative,rename_exclusive
from .fileops import fingerprint
from ..archive_reader import Reader,safe_member
from ..zipstream import write_zip
from ..state import atomic

RESERVE=256*1024**2

def archive_folder(filename):
    result=re.sub(r'(?i)(\.tar\.(gz|bz2|xz|zst)|\.t(gz|bz2|xz)|\.(zip|7z|rar|tar|gz|bz2|xz|zst))$','',filename)
    if result==filename:result=filename+'-extracted'
    if not result or len(relative(result))!=1:raise ValueError('Choose a valid extraction folder name')
    return result

class Archives:
    def __init__(self,ctx,files,bundles):self.ctx=ctx;self.files=files;self.bundles=bundles
    def plan(self,request):
        self.files.writable(request.get('share'))
        operation=request.get('operation');share=request.get('share');target_path=request.get('target_path','');maximum=request.get('max_output_bytes',64*1024**3)
        if isinstance(maximum,bool) or not isinstance(maximum,int) or not 1<=maximum<=16*1024**4:raise ValueError('Choose an output limit up to 16 TiB')
        with self.files.directory(share,target_path) as (fd,mapping,pool):
            body={'operation':operation,'share':share,'target_path':target_path,'target_identity':[os.fstat(fd).st_dev,os.fstat(fd).st_ino],'filesystem_uuid':pool['filesystem_uuid'],'max_output_bytes':maximum}
            if operation=='zip':
                selection=self.bundles.selection({'share':share,'paths':request.get('paths'),'filename':request.get('filename','archive.zip')})
                body.update(selection=selection,name=selection['filename'])
                for root in selection['roots']:
                    if root['directory'] and (not root['path'] or target_path==root['path'] or target_path.startswith(root['path']+'/')):raise ValueError('Save the ZIP outside the selected source folder')
            elif operation=='extract':
                path=request.get('path','');parts=relative(path)
                if not parts:raise ValueError('Choose one archive file')
                with self.files.directory(share,str(Path(*parts[:-1]))) as (source,_,_):
                    info=os.stat(parts[-1],dir_fd=source,follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode):raise ValueError('Choose a regular archive file')
                mode=request.get('destination','named')
                if mode not in ('current','named'):raise ValueError('Choose current folder or archive-named folder')
                body.update(path=path,source_identity=fingerprint(info),destination=mode,name=archive_folder(parts[-1]) if mode=='named' else None)
            else:raise ValueError('Choose zip or extract')
            if body['name']:
                try:os.stat(body['name'],dir_fd=fd,follow_symlinks=False)
                except FileNotFoundError:pass
                else:raise ValueError('Destination already exists; choose another name or folder')
            body['review']='Existing files are never overwritten. Output is staged and verified on the selected data volume, not the OS disk. Interrupted stages remain recoverable in File manager. Live input is not a filesystem snapshot. Extraction rejects links, special files, unsafe paths and encrypted archives. Limit: 100,000 extracted entries / 64 levels; maximum expansion 10,000×.'
            return self.ctx.plan('file-archive',body,operation.upper()+' ARCHIVE')
    def apply(self,request,job_id=None):
        with self.ctx.lock():
            plan_path,plan=self.ctx.reviewed(request,'file-archive');b=plan['body']
            self.files.writable(b['share'])
            with self.files.directory(b['share'],b['target_path']) as (target,share,pool):
                if [os.fstat(target).st_dev,os.fstat(target).st_ino]!=b['target_identity'] or pool['filesystem_uuid']!=b['filesystem_uuid']:raise ValueError('Archive destination changed')
                self.ctx.consume(plan_path,plan);ident=job_id or self.ctx.operation('files.archive',{'plan_id':plan['id']});token=secrets.token_hex(16)
                staging=Path(pool['mountpoint'])/'.freeqnap/transfers';staging.mkdir(parents=True,mode=0o700,exist_ok=True)
                stage=os.open(staging,os.O_DIRECTORY|os.O_RDONLY|os.O_NOFOLLOW);record=self.ctx.directory/'operations'/(ident+'.json')
                checkpoint={'id':ident,'stage_pool':pool['name'],'stage_uuid':pool['filesystem_uuid'],'partial_stage':token,'published':[],'operation':b['operation']};atomic(record,checkpoint)
                try:
                    if b['operation']=='zip':
                        fresh=self.bundles.selection({'share':b['share'],'paths':[r['path'] for r in b['selection']['roots']],'filename':b['name']})
                        if fresh!=b['selection']:raise ValueError('ZIP selection changed since review')
                        ticket=self.bundles.start({'share':b['share'],'paths':[r['path'] for r in fresh['roots']],'filename':b['name']});info=self.bundles.info(ticket)
                        def read(action,payload):return {'files.bundle-node':self.bundles.node,'files.bundle-read':self.bundles.read}[action](payload)
                        limit=min(b['max_output_bytes'],self.available(target))
                        fd=os.open(token,os.O_CREAT|os.O_EXCL|os.O_RDWR|os.O_NOFOLLOW,0o600,dir_fd=stage)
                        with os.fdopen(fd,'w+b') as out:
                            result=write_zip(out,read,info,compression='deflate',max_bytes=limit,progress=lambda _:self.available(target));out.flush();os.fsync(out.fileno());out.seek(0)
                            with zipfile.ZipFile(out) as check:
                                if check.testzip() is not None:raise ValueError('ZIP readback verification failed')
                            os.fchown(out.fileno(),0,share['gid']);os.fchmod(out.fileno(),0o660);os.fsync(out.fileno())
                        rename_exclusive(stage,token,target,b['name']);os.fsync(target);checkpoint['published']=[b['name']]
                    else:
                        os.mkdir(token,0o700,dir_fd=stage);out=os.open(token,os.O_DIRECTORY|os.O_RDONLY|os.O_NOFOLLOW,dir_fd=stage)
                        try:
                            result=self.extract(b,out,target,share['gid'])
                            names=[b['name']] if b['name'] else sorted(os.listdir(out))
                            # Check every collision before publishing the first top-level item.
                            for name in names:
                                try:os.stat(name,dir_fd=target,follow_symlinks=False)
                                except FileNotFoundError:pass
                                else:raise ValueError('Destination exists: '+name+'; extracted stage retained')
                            if b['name']:
                                os.fchown(out,0,share['gid']);os.fchmod(out,0o2770);os.fsync(out);rename_exclusive(stage,token,target,b['name']);os.fsync(target);checkpoint['published']=names
                            else:
                                for name in names:
                                    rename_exclusive(out,name,target,name);os.fsync(out);os.fsync(target);checkpoint['published'].append(name);atomic(record,checkpoint)
                                os.rmdir(token,dir_fd=stage)
                        finally:os.close(out)
                    os.fsync(stage);checkpoint.pop('partial_stage');atomic(record,checkpoint)
                    result.update(published=checkpoint['published'],existing_files_overwritten=False)
                    if job_id is None:self.ctx.state.finish(ident,result=result)
                    return result
                finally:os.close(stage)
    def available(self,fd):
        space=os.fstatvfs(fd);available=space.f_bavail*space.f_frsize-RESERVE
        if available<=0:raise ValueError('Free-space reserve reached; stage retained')
        return available
    def extract(self,b,output,target,gid):
        parts=relative(b['path']);seen=set();total=0;count=0
        def directory(parts):
            fd=os.dup(output)
            try:
                for name in parts:
                    try:os.mkdir(name,0o2770,dir_fd=fd)
                    except FileExistsError:pass
                    child=os.open(name,os.O_DIRECTORY|os.O_NOFOLLOW|os.O_RDONLY,dir_fd=fd);os.fchown(child,0,gid);os.fchmod(child,0o2770);os.fsync(fd);os.close(fd);fd=child
                return fd
            except Exception:os.close(fd);raise
        with self.files.directory(b['share'],str(Path(*parts[:-1]))) as (source,_,_):
            fd=os.open(parts[-1],os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW,dir_fd=source)
            try:
                if fingerprint(os.fstat(fd))!=b['source_identity']:raise ValueError('Archive changed since review')
                with Reader(fd) as reader:
                    for entry in reader.entries():
                        count+=1
                        if count>100000:raise ValueError('Archive entry limit reached; stage retained')
                        members=safe_member(parts[-1].rsplit('.',1)[0] if entry['raw'] else entry['name'])
                        if not members:
                            if entry['directory']:continue
                            raise ValueError('Archive member has no filename')
                        if members in seen:raise ValueError('Duplicate archive path; stage retained')
                        seen.add(members)
                        if entry['directory']:
                            d=directory(members);os.fsync(d);os.close(d);continue
                        parent=directory(members[:-1])
                        try:
                            dest=os.open(members[-1],os.O_EXCL|os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600,dir_fd=parent)
                            try:
                                digest=hashlib.sha256();length=0
                                for chunk in reader.chunks():
                                    total+=len(chunk);length+=len(chunk)
                                    if total>b['max_output_bytes'] or total>max(1024**2,os.fstat(fd).st_size*10000):raise ValueError('Archive output/expansion limit reached; stage retained')
                                    if len(chunk)>self.available(target):raise ValueError('Insufficient free space; stage retained')
                                    digest.update(chunk);view=memoryview(chunk)
                                    while view:
                                        n=os.write(dest,view)
                                        if n<=0:raise OSError('Short extraction write')
                                        view=view[n:]
                                if entry['size']>=0 and length!=entry['size']:raise ValueError('Archive entry size mismatch')
                                os.fsync(dest);os.lseek(dest,0,os.SEEK_SET);verify=hashlib.sha256()
                                while chunk:=os.read(dest,1024*1024):verify.update(chunk)
                                if verify.digest()!=digest.digest():raise ValueError('Extracted file readback mismatch')
                                os.fchown(dest,0,gid);os.fchmod(dest,0o660);os.fsync(dest);os.fsync(parent)
                            finally:os.close(dest)
                        finally:os.close(parent)
                if fingerprint(os.fstat(fd))!=b['source_identity']:raise ValueError('Archive changed during extraction; stage retained')
            finally:os.close(fd)
        os.fsync(output);return {'entries':count,'output_bytes':total}
