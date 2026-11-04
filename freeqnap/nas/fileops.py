"""Staged, no-overwrite file transfers and an explicitly managed recycle bin."""
import contextlib
import hashlib
import json
import os
import secrets
import stat
import time
from pathlib import Path
from .files import Files,relative,rename_exclusive
from ..state import atomic


def fingerprint(info):
    return [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns,info.st_mode]


def remove_tree(parent,leaf,device,depth=0):
    if depth>64:raise ValueError('Deletion depth limit; remaining data retained')
    before=os.stat(leaf,dir_fd=parent,follow_symlinks=False)
    if before.st_dev!=device:raise ValueError('Nested mounted filesystems are never deleted')
    if stat.S_ISDIR(before.st_mode):
        fd=os.open(leaf,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
        try:
            if os.fstat(fd).st_ino!=before.st_ino:raise ValueError('Deletion source changed')
            for child in os.listdir(fd):remove_tree(fd,child,device,depth+1)
            if os.stat(leaf,dir_fd=parent,follow_symlinks=False).st_ino!=before.st_ino:raise ValueError('Deletion directory changed')
            os.rmdir(leaf,dir_fd=parent)
        finally:os.close(fd)
    else:
        if fingerprint(os.stat(leaf,dir_fd=parent,follow_symlinks=False))!=fingerprint(before):raise ValueError('Deletion source changed')
        os.unlink(leaf,dir_fd=parent)
    os.fsync(parent)


class FileManager(Files):
    def foreign_view(self,share_id):
        from .external import External
        from .foreign import Foreign
        return Foreign(self.ctx,External(self.ctx)).file_view(share_id[8:])
    def mapping(self,share_id):
        if isinstance(share_id,str) and share_id.startswith('foreign:'):
            with self.foreign_view(share_id).directory(share_id) as (_,share,_):return share
        return super().mapping(share_id)
    @contextlib.contextmanager
    def directory(self,share_id,path=''):
        if isinstance(share_id,str) and share_id.startswith('foreign:'):
            with self.foreign_view(share_id).directory(share_id,path) as value:yield value
        else:
            with super().directory(share_id,path) as value:yield value
    def validate_volume(self,ident):
        if ident.startswith('foreign:'):
            with self.foreign_view(ident).directory(ident) as (_,_,pool):return pool,Path(pool['mountpoint'])
        return self.ctx.volume(ident)

    def policy(self,request=None):
        return self.ctx.state.setting('recycle_policy',{'retention_days':30})

    def policy_plan(self,request):
        days=request.get('retention_days')
        if isinstance(days,bool) or not isinstance(days,int) or not 0<=days<=3650:raise ValueError('Choose 0 (keep indefinitely) to 3650 days')
        return self.ctx.plan('recycle-policy',{'before':self.policy(),'retention_days':days,'review':'Shortening retention applies to existing dated recycle items. Expired items will be permanently removed; 0 disables expiration. Old undated or incomplete items are retained.'},'SET RECYCLE RETENTION '+str(days))

    def policy_apply(self,request):
        with self.ctx.lock():
            path,plan=self.ctx.reviewed(request,'recycle-policy');body=plan['body']
            if body['before']!=self.policy():raise ValueError('Recycle policy changed; review again')
            self.ctx.consume(path,plan);self.ctx.state.set('recycle_policy',{'retention_days':body['retention_days'],'updated_at':time.time()})
        return self.policy()

    def trash_items(self,request=None):
        with self.ctx.state.connect() as db:records=[json.loads(r[0]) for r in db.execute("SELECT value FROM settings WHERE key LIKE 'trash:%'")]
        days=self.policy()['retention_days'];items=[]
        for record in records:
            if record.get('recovered') or record.get('purged'):continue
            deleted=record.get('deleted_at');expires=deleted+days*86400 if days and deleted else None
            items.append({k:record.get(k) for k in ['trash_id','share','path','pool','size','deleted_at','purge_error']}|{'expires_at':expires,'deleting':bool(record.get('deleting'))})
        return {'policy':self.policy(),'items':sorted(items,key=lambda r:r.get('deleted_at') or 0,reverse=True)}

    def transfer_plan(self,request):
        source=request.get('share');paths=request.get('paths');target_share=request.get('target_share');target_path=request.get('target_path','');mode=request.get('mode','copy')
        if mode not in ('copy','move') or not isinstance(paths,list) or not 1<=len(paths)<=200 or len(set(paths))!=len(paths):raise ValueError('Select 1–200 distinct paths and copy or move')
        new_name=request.get('new_name')
        if new_name is not None and (len(paths)!=1 or len(relative(new_name))!=1):raise ValueError('A custom name is only available for one selected item')
        self.writable(target_share)
        if mode=='move':self.writable(source)
        items=[]
        with self.directory(target_share,target_path) as (target,destination,pool):
            parent=os.fstat(target)
            for path in paths:
                if mode=='move':self.protect_library_parent(source,path)
                parts=relative(path)
                if not parts:raise ValueError('Share roots cannot be transferred')
                leaf=new_name or parts[-1]
                with self.directory(source,str(Path(*parts[:-1]))) as (fd,share,source_pool):
                    info=os.stat(parts[-1],dir_fd=fd,follow_symlinks=False)
                    if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):raise ValueError('Copy/move regular files or folders; symlinks and special files are excluded')
                    src=Path(share['path']).joinpath(*parts);dst=Path(destination['path']).joinpath(*relative(target_path),leaf)
                    if src==dst or src in dst.parents:raise ValueError('Cannot place an item inside itself')
                    try:os.stat(leaf,dir_fd=target,follow_symlinks=False)
                    except FileNotFoundError:pass
                    else:raise ValueError('Destination already exists; existing data will never be overwritten')
                    items.append({'path':path,'name':leaf,'identity':fingerprint(info),'filesystem_uuid':source_pool['filesystem_uuid']})
            if len({v['name'] for v in items})!=len(items):raise ValueError('Selected destination names collide')
            body={'share':source,'items':items,'target_share':target_share,'target_path':target_path,'target_identity':[parent.st_dev,parent.st_ino], 'target_uuid':pool['filesystem_uuid'],'mode':mode,'review':'Copy is staged and hash-verified before publication; live files are not a consistent filesystem snapshot. Existing targets are never overwritten. Interrupted staging is retained. Cross-volume moves verify the copy, then retain the original in its source recycle bin; completed items remain recorded after partial failures.'}
        return self.ctx.plan('file-transfer',body,mode.upper()+' '+str(len(items))+' ITEM(S)')

    def transfer(self,request,job_id=None):
        with self.ctx.lock():
            plan_path,plan=self.ctx.reviewed(request,'file-transfer');body=plan['body']
            self.writable(body['target_share'])
            if body['mode']=='move':self.writable(body['share'])
            with self.directory(body['target_share'],body['target_path']) as (target,share,pool):
                if [os.fstat(target).st_dev,os.fstat(target).st_ino]!=body['target_identity'] or pool['filesystem_uuid']!=body['target_uuid']:raise ValueError('Transfer destination changed')
                for item in body['items']:
                    if body['mode']=='move':self.protect_library_parent(body['share'],item['path'])
                    parts=relative(item['path'])
                    with self.directory(body['share'],str(Path(*parts[:-1]))) as (source,_,source_pool):
                        if fingerprint(os.stat(parts[-1],dir_fd=source,follow_symlinks=False))!=item['identity'] or source_pool['filesystem_uuid']!=item['filesystem_uuid']:raise ValueError('Transfer source changed since review')
                self.ctx.consume(plan_path,plan)
                ident=job_id or self.ctx.operation('file-transfer',{'plan_id':plan['id']})
                checkpoint={'id':ident,'plan_id':plan['id'],'stage_pool':pool['name'],'stage_uuid':pool['filesystem_uuid'],'published':[],'staging_retained_on_failure':True}
                record=self.ctx.directory/'operations'/(ident+'.json');atomic(record,checkpoint)
                # Hold the storage-operation lock: eject/reformat cannot race a transfer.
                for item in body['items']:
                    if body['mode']=='move':self.protect_library_parent(body['share'],item['path'])
                    parts=relative(item['path'])
                    with self.directory(body['share'],str(Path(*parts[:-1]))) as (source,_,source_pool):
                        if fingerprint(os.stat(parts[-1],dir_fd=source,follow_symlinks=False))!=item['identity']:raise ValueError('Source changed during queued transfer')
                        if body['mode']=='move' and source_pool['filesystem_uuid']==pool['filesystem_uuid']:rename_exclusive(source,parts[-1],target,item['name']);os.fsync(source)
                        else:
                            staging=Path(pool['mountpoint'])/'.freeqnap'/'transfers';staging.mkdir(mode=0o700,parents=True,exist_ok=True)
                            stage=os.open(staging,os.O_DIRECTORY|os.O_RDONLY|os.O_NOFOLLOW)
                            try:
                                token=secrets.token_hex(16);checkpoint['partial_stage']=token;atomic(record,checkpoint)
                                budget={'entries':0,'bytes':0};self.copy_node(source,parts[-1],stage,token,os.fstat(source).st_dev,share['gid'],budget,0,source_pool['name'],pool['name'])
                                self.writable(body['target_share']);self.ctx.volume(pool['name']);self.validate_volume(source_pool['name']);rename_exclusive(stage,token,target,item['name']);os.fsync(stage)
                            finally:os.close(stage)
                            os.fsync(target);checkpoint['published'].append(item['name']);checkpoint.pop('partial_stage',None);atomic(record,checkpoint)
                            if body['mode']=='move':
                                self.writable(body['share'])
                                if fingerprint(os.stat(parts[-1],dir_fd=source,follow_symlinks=False))!=item['identity']:raise ValueError('Source changed after verified copy; both source and destination are retained')
                                trash=Path(source_pool['mountpoint'])/'.freeqnap'/'trash';trash.mkdir(mode=0o700,parents=True,exist_ok=True);trash_id=secrets.token_hex(16);info=os.stat(parts[-1],dir_fd=source,follow_symlinks=False)
                                entry={'share':body['share'],'path':item['path'],'new_name':None,'pool':source_pool['name'],'filesystem_uuid':source_pool['filesystem_uuid'],'inode':info.st_ino,'device':info.st_dev,'size':info.st_size,'mtime_ns':info.st_mtime_ns,'trash_id':trash_id,'deleted_at':time.time(),'pending':True,'verified_move_destination':{'share':body['target_share'],'path':str(Path(body['target_path'])/item['name'])}}
                                self.ctx.state.set('trash:'+trash_id,entry);trash_fd=os.open(trash,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                                try:rename_exclusive(source,parts[-1],trash_fd,trash_id);os.fsync(source);os.fsync(trash_fd)
                                finally:os.close(trash_fd)
                                entry['pending']=False;self.ctx.state.set('trash:'+trash_id,entry);checkpoint.setdefault('recycled_sources',[]).append(trash_id)
                        os.fsync(target)
                        if item['name'] not in checkpoint['published']:checkpoint['published'].append(item['name'])
                        checkpoint.pop('partial_stage',None);atomic(record,checkpoint)
                result={'mode':body['mode'],'published':checkpoint['published'],'recycled_sources':checkpoint.get('recycled_sources',[]),'existing_files_overwritten':False}
                if job_id is None:self.ctx.state.finish(ident,result=result)
                return result

    def copy_node(self,source,leaf,target,new_name,device,gid,budget,depth,source_pool,target_pool):
        budget['entries']+=1
        if depth>64 or budget['entries']>200000:raise ValueError('Transfer tree limit reached; partial stage retained')
        if leaf.startswith('.freeqnap'):raise ValueError('Reserved private folders are not copied')
        before=os.stat(leaf,dir_fd=source,follow_symlinks=False)
        if before.st_dev!=device:raise ValueError('Nested mounted filesystems are not copied')
        if stat.S_ISDIR(before.st_mode):
            fd=os.open(leaf,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=source)
            try:
                if fingerprint(os.fstat(fd))!=fingerprint(before):raise ValueError('Source directory changed')
                os.mkdir(new_name,0o2770,dir_fd=target);out=os.open(new_name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=target)
                try:
                    os.fchown(out,0,gid)
                    for child in os.listdir(fd):self.copy_node(fd,child,out,child,device,gid,budget,depth+1,source_pool,target_pool)
                    if fingerprint(os.fstat(fd))!=fingerprint(before):raise ValueError('Source directory changed while copying')
                    os.fsync(out)
                finally:os.close(out)
            finally:os.close(fd)
        elif stat.S_ISREG(before.st_mode):
            fd=os.open(leaf,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=source)
            try:
                if fingerprint(os.fstat(fd))!=fingerprint(before):raise ValueError('Source file changed')
                out=os.open(new_name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o660,dir_fd=target)
                try:
                    digest=hashlib.sha256();written=0
                    while chunk:=os.read(fd,4*1024**2):
                        self.validate_volume(source_pool);self.ctx.volume(target_pool)
                        digest.update(chunk);view=memoryview(chunk)
                        while view:
                            n=os.write(out,view)
                            if n<=0:raise OSError('Short copy write')
                            view=view[n:]
                        written+=len(chunk)
                    if fingerprint(os.fstat(fd))!=fingerprint(before) or written!=before.st_size:raise ValueError('Source file changed during copy')
                    os.fchown(out,0,gid);os.fchmod(out,0o660);os.fsync(out);os.lseek(out,0,os.SEEK_SET);check=hashlib.sha256()
                    while chunk:=os.read(out,4*1024**2):check.update(chunk)
                    if check.digest()!=digest.digest():raise ValueError('Copy readback hash differs; stage retained')
                    os.utime(out,ns=(before.st_atime_ns,before.st_mtime_ns));budget['bytes']+=written
                finally:os.close(out)
            finally:os.close(fd)
        else:raise ValueError('Symlink/special-file copy refused; stage retained')
        os.fsync(target)

    def stages(self,request=None):
        items=[]
        for p in sorted((self.ctx.directory/'operations').glob('*.json')):
            record=json.loads(p.read_text())
            if not record.get('partial_stage') or not record.get('stage_pool'):continue
            with self.ctx.state.connect() as db:job=db.execute('SELECT status FROM jobs WHERE id=?',(p.stem,)).fetchone()
            items.append({'id':p.stem,'pool':record['stage_pool'],'status':job['status'] if job else 'unknown','published':record.get('published',[])})
        return {'items':items[:200],'truncated':len(items)>200}

    def stage_info(self,ident):
        import re
        if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{32}',ident):raise ValueError('Choose a retained transfer stage')
        path=self.ctx.directory/'operations'/(ident+'.json');record=json.loads(path.read_text());token=record.get('partial_stage','')
        if not re.fullmatch('[a-f0-9]{32}',token):raise ValueError('No retained partial copy')
        with self.ctx.state.connect() as db:job=db.execute('SELECT status FROM jobs WHERE id=?',(ident,)).fetchone()
        if not job or job['status']!='retryable':raise ValueError('Only failed, inactive copy stages can be removed')
        pool,mount=self.ctx.volume(record['stage_pool'])
        if pool['filesystem_uuid']!=record['stage_uuid']:raise ValueError('Partial-copy filesystem changed')
        return path,record,pool,mount/'.freeqnap'/'transfers',token

    def stage_plan(self,request):
        _,record,pool,parent,token=self.stage_info(request.get('id'));fd=os.open(parent,os.O_DIRECTORY|os.O_RDONLY|os.O_NOFOLLOW)
        try:identity=fingerprint(os.stat(token,dir_fd=fd,follow_symlinks=False))
        finally:os.close(fd)
        return self.ctx.plan('copy-stage-purge',{'id':request['id'],'record':record,'identity':identity,'uuid':pool['filesystem_uuid'],'review':'Permanently remove only this unpublished partial copy. Published destination files and original sources are kept.'},'DELETE PARTIAL COPY '+request['id'])

    def stage_remove(self,request):
        with self.ctx.lock():
            plan_path,plan=self.ctx.reviewed(request,'copy-stage-purge');body=plan['body'];path,record,pool,parent,token=self.stage_info(body['id'])
            if record!=body['record'] or pool['filesystem_uuid']!=body['uuid']:raise ValueError('Partial-copy record changed')
            fd=os.open(parent,os.O_DIRECTORY|os.O_RDONLY|os.O_NOFOLLOW)
            try:
                if fingerprint(os.stat(token,dir_fd=fd,follow_symlinks=False))!=body['identity']:raise ValueError('Partial copy changed')
                self.ctx.consume(plan_path,plan);remove_tree(fd,token,os.fstat(fd).st_dev)
                record.pop('partial_stage');record['partial_removed_at']=time.time();atomic(path,record)
            finally:os.close(fd)
        return {'partial_copy_removed':body['id'],'published_files_kept':True}

    def recycle_plan(self,request):
        paths=request.get('paths');permanent=request.get('permanent',False)
        if not isinstance(paths,list) or not 1<=len(paths)<=200 or len(set(paths))!=len(paths) or not isinstance(permanent,bool):raise ValueError('Choose 1–200 distinct items')
        children=[]
        for item in paths:
            parts=relative(item)
            if any(Path(other) in Path(item).parents for other in paths if other!=item):raise ValueError('Do not select both a folder and its descendants')
            child=(self.delete_plan if permanent else super().move_plan)({'share':request['share'],'path':item})
            children.append({'plan_id':child['id'],'digest':child['digest'],'confirmation':child['confirmation']})
        return self.ctx.plan('file-recycle-batch',{'children':children,'share':request['share'],'paths':paths,'permanent':permanent},('PERMANENTLY DELETE ' if permanent else 'RECYCLE ')+str(len(paths))+' ITEM(S)')

    def recycle(self,request,job_id):
        with self.ctx.lock():
            path,plan=self.ctx.reviewed(request,'file-recycle-batch');self.ctx.consume(path,plan)
        progress={'plan_id':plan['id'],'completed':[],'errors':[]};record=self.ctx.directory/'operations'/(job_id+'.json');atomic(record,progress)
        for filename,child in zip(plan['body']['paths'],plan['body']['children']):
            try:self.move(child);progress['completed'].append(filename)
            except Exception as error:progress['errors'].append({'path':filename,'error':str(error)})
            atomic(record,progress)
        if progress['errors']:raise ValueError(str(len(progress['errors']))+' item(s) failed; completed items and per-item errors retained in operation history')
        return progress

    def delete_plan(self,request):
        old=super().move_plan({**request,'new_name':None})
        return self.ctx.plan('file-move',{**old['body'],'permanent_delete':True},'PERMANENTLY DELETE '+request['path'])

    def move(self,request):
        _,plan=self.ctx.reviewed(request,'file-move');permanent=plan['body'].get('permanent_delete',False)
        result=super().move(request)
        if permanent:
            with self.ctx.lock():
                ident=result['plan_id'];record=self.ctx.state.setting('trash:'+ident);pool,mount=self.ctx.volume(record['pool'])
                fd=os.open(mount/'.freeqnap'/'trash',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                try:self.purge_item(ident,fd,pool)
                finally:os.close(fd)
            result.update(moved_to_recoverable_trash=False,permanently_deleted=True)
        return result

    def purge_plan(self,request):
        ident=request.get('id');record=self.ctx.state.setting('trash:'+str(ident))
        if not record or record.get('recovered') or record.get('purged'):raise ValueError('Choose an unrecovered recycle-bin item')
        pool,mount=self.ctx.volume(record['pool']);root=mount/'.freeqnap'/'trash';fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:info=os.stat(ident,dir_fd=fd,follow_symlinks=False)
        finally:os.close(fd)
        return self.ctx.plan('file-purge',{'id':ident,'pool':pool['name'],'uuid':pool['filesystem_uuid'],'identity':fingerprint(info),'description':record['share']+'/'+record['path'],'review':'Permanently remove this recycle-bin item and descendants. This cannot be undone.'},'PERMANENTLY DELETE '+record['path'])

    def purge(self,request):
        with self.ctx.lock():
            path,plan=self.ctx.reviewed(request,'file-purge');body=plan['body'];pool,mount=self.ctx.volume(body['pool'])
            record=self.ctx.state.setting('trash:'+body['id'])
            if record:self.writable(record['share'])
            if pool['filesystem_uuid']!=body['uuid']:raise ValueError('Recycle-bin volume changed')
            fd=os.open(mount/'.freeqnap'/'trash',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:
                if fingerprint(os.stat(body['id'],dir_fd=fd,follow_symlinks=False))!=body['identity']:raise ValueError('Recycle-bin item changed since review')
                self.ctx.consume(path,plan);self.purge_item(body['id'],fd,pool)
            finally:os.close(fd)
        return {'permanently_deleted':body['id']}

    def purge_item(self,ident,parent,pool):
        record=self.ctx.state.setting('trash:'+ident)
        if not record or record.get('pending') or record.get('recovered') or record.get('purged') or record['pool']!=pool['name'] or record.get('filesystem_uuid')!=pool['filesystem_uuid']:raise ValueError('Recycle-bin record changed')
        if os.stat(ident,dir_fd=parent,follow_symlinks=False).st_ino!=record['inode']:raise ValueError('Recycle-bin inode changed')
        record['deleting']=True;self.ctx.state.set('trash:'+ident,record)
        try:
            remove_tree(parent,ident,os.fstat(parent).st_dev);record.update(purged=True,purged_at=time.time(),deleting=False,purge_error=None)
        except Exception as error:
            record['purge_error']=str(error);raise
        finally:self.ctx.state.set('trash:'+ident,record)

    def expire(self):
        days=self.policy()['retention_days']
        if not days:return
        due=[r for r in self.trash_items()['items'] if r['expires_at'] and r['expires_at']<=time.time()][:16]
        for row in due:
            try:
                with self.ctx.lock():
                    record=self.ctx.state.setting('trash:'+row['trash_id'])
                    days=self.policy()['retention_days']
                    if not days or not record or record.get('pending') or record.get('recovered') or record.get('purged') or not record.get('deleted_at') or record['deleted_at']+days*86400>time.time():continue
                    pool,mount=self.ctx.volume(record['pool']);fd=os.open(mount/'.freeqnap'/'trash',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                    try:self.purge_item(row['trash_id'],fd,pool)
                    finally:os.close(fd)
            except (ValueError,OSError):continue  # Missing/locked pools retain records and data.
