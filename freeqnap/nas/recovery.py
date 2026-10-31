"""Reviewable promotion of verified restore stages or recoverable trash."""
import json
import os
import re
import stat
from pathlib import Path
from .common import name
from .files import relative, rename_exclusive

class Recovery:
    def __init__(self, context, files):
        self.ctx=context;self.files=files

    def source(self, kind, ident):
        if not re.fullmatch('[a-f0-9]{32}',ident):raise ValueError('Invalid recovery item')
        if kind=='trash':
            item=self.ctx.state.setting('trash:'+ident)
            if not item or item.get('recovered') or item.get('pending') or item.get('deleting') or item.get('purged'):raise ValueError('Trash item is absent or already recovered')
            pool,mount=self.ctx.volume(item['pool'])
            path=mount/'.freeqnap'/'trash'/ident
            description=item['share']+'/'+item['path']
        elif kind=='restore':
            with self.ctx.state.connect() as db:job=db.execute("SELECT status,result FROM jobs WHERE id=? AND kind='backup.restore'",(ident,)).fetchone()
            if not job or job['status']!='succeeded':raise ValueError('Only a verified successful restore stage can be promoted')
            item=json.loads(job['result'])
            if item.get('system_recovery_only'):raise ValueError('System recovery snapshots contain credentials and cannot be promoted into a file share')
            pool,mount=self.ctx.volume(item['pool'])
            path=mount/'.freeqnap'/'restores'/ident
            if str(path)!=item['staging_directory'] or not item['restored_content_verified']:
                raise ValueError('Restore stage does not match the recorded verified operation')
            description='Verified snapshot '+item['snapshot'][:12]
        else:raise ValueError('Choose restore or trash')
        if not path.exists() or path.is_symlink():raise ValueError('Recovery item is missing or changed')
        return pool,path,description

    def list(self, request=None):
        rows=[]
        with self.ctx.state.connect() as db:
            trash=[r[0].removeprefix('trash:') for r in db.execute("SELECT key FROM settings WHERE key LIKE 'trash:%'")]
            restores=[r[0] for r in db.execute("SELECT id FROM jobs WHERE kind='backup.restore' AND status='succeeded' ORDER BY created DESC LIMIT 200")]
        for kind,values in (('trash',trash),('restore',restores)):
            for ident in values:
                try:
                    pool,path,description=self.source(kind,ident)
                    rows.append({'kind':kind,'id':ident,'pool':pool['name'],'description':description,'directory':path.is_dir()})
                except (ValueError,OSError):continue
        return {'items':rows}

    def plan(self, request):
        kind=request.get('kind');ident=request.get('id');pool,path,description=self.source(kind,ident)
        share_name=name(request.get('share'));new_name=request.get('name')
        if len(relative(new_name))!=1:raise ValueError('Choose one destination file or folder name')
        target_path=request.get('target_path','');relative(target_path)
        with self.files.directory(share_name,target_path) as (directory,share,target_pool):
            if target_pool['filesystem_uuid']!=pool['filesystem_uuid']:
                raise ValueError('Restore directly into the destination pool before promotion; cross-pool promotion is not atomic')
            try:os.stat(new_name,dir_fd=directory,follow_symlinks=False)
            except FileNotFoundError:pass
            else:raise ValueError('Destination already exists; it will not be overwritten')
            info=path.stat();parent=os.fstat(directory)
        body={'kind':kind,'id':ident,'source_pool':pool['name'],'filesystem_uuid':pool['filesystem_uuid'],
              'inode':info.st_ino,'device':info.st_dev,'mtime_ns':info.st_mtime_ns,'share':share_name,
              'new_name':new_name,'target_path':target_path,'destination_parent_inode':parent.st_ino,'description':description}
        return self.ctx.plan('recover-files',body,'RECOVER '+share_name+'/'+new_name)

    def apply(self, request):
        with self.ctx.lock():
            plan_path,plan=self.ctx.reviewed(request,'recover-files');body=plan['body']
            pool,path,_=self.source(body['kind'],body['id']);info=path.stat()
            if (info.st_ino,info.st_dev,info.st_mtime_ns,pool['filesystem_uuid'])!=(body['inode'],body['device'],body['mtime_ns'],body['filesystem_uuid']):
                raise ValueError('Recovery source identity changed since review')
            with self.files.directory(body['share'],body.get('target_path','')) as (target,_,target_pool):
                if os.fstat(target).st_ino!=body['destination_parent_inode'] or target_pool['filesystem_uuid']!=pool['filesystem_uuid']:
                    raise ValueError('Recovery destination changed')
                self.ctx.consume(plan_path,plan)
                source=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                try:rename_exclusive(source,path.name,target,body['new_name']);os.fsync(source);os.fsync(target)
                finally:os.close(source)
            if body['kind']=='trash':
                item=self.ctx.state.setting('trash:'+body['id']);item['recovered']=True;self.ctx.state.set('trash:'+body['id'],item)
            return {'recovered_to':body['share']+'/'+body['new_name'],'existing_data_overwritten':False,
                    'original_ownership_and_modes_preserved':True}
