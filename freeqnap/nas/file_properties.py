"""Bounded, descriptor-relative file/folder information within the caller's view."""
import os
from pathlib import Path
import stat
import time
from .files import relative


def inspect(files, request):
    if set(request)-{'share','path'} or 'share' not in request:
        raise ValueError('Choose a file or folder')
    share=request['share'];path=request.get('path','');parts=relative(path)
    result={'path':path,'name':parts[-1] if parts else share,'bytes':0,'allocated_bytes':0,'files':0,'folders':0,'skipped_links':0,'complete':True,'warnings':[]}
    deadline=time.monotonic()+8;entries=0
    def warning(text):
        result['complete']=False
        if text not in result['warnings']:result['warnings'].append(text)
    def visit(parent,leaf,device,logical,depth=0):
        nonlocal entries
        if time.monotonic()>deadline or entries>=100000 or depth>64:
            warning('Folder calculation reached its safety limit; displayed totals are partial.');return
        entries+=1
        if leaf.startswith('.freeqnap'):return
        if share.startswith('pool:') and hasattr(files.ctx,'shared_usb_path') and not files.ctx.shared_usb_path(share[5:],logical):return
        try:
            info=os.stat(leaf,dir_fd=parent,follow_symlinks=False)
            if info.st_dev!=device:warning('Nested mounted volumes were excluded.');return
            if stat.S_ISLNK(info.st_mode):result['skipped_links']+=1;return
            if stat.S_ISREG(info.st_mode):
                result['files']+=1;result['bytes']+=info.st_size;result['allocated_bytes']+=getattr(info,'st_blocks',0)*512;return
            if not stat.S_ISDIR(info.st_mode):warning('Special files were excluded.');return
            result['folders']+=1
            fd=os.open(leaf,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
            try:
                opened=os.fstat(fd)
                if (opened.st_dev,opened.st_ino)!=(info.st_dev,info.st_ino):raise ValueError('Folder changed during calculation')
                for child in os.listdir(fd):
                    visit(fd,child,device,str(Path(logical)/child),depth+1)
                    if time.monotonic()>deadline or entries>=100000:warning('Folder calculation reached its safety limit; displayed totals are partial.');break
                after=os.fstat(fd)
                if (after.st_mtime_ns,after.st_ctime_ns)!=(opened.st_mtime_ns,opened.st_ctime_ns):warning('Folder contents changed during calculation; refresh for current totals.')
            finally:os.close(fd)
        except (OSError,ValueError):warning('Some entries changed or could not be read; totals are partial.')
    parent_path=str(Path(*parts[:-1])) if parts else ''
    with files.directory(share,parent_path) as (parent,mapping,pool):
        before=os.stat(parts[-1],dir_fd=parent,follow_symlinks=False) if parts else os.fstat(parent)
        if stat.S_ISLNK(before.st_mode):raise ValueError('Link targets are not inspected')
        if not (stat.S_ISDIR(before.st_mode) or stat.S_ISREG(before.st_mode)):raise ValueError('Choose a regular file or folder')
        result.update(type='Folder' if stat.S_ISDIR(before.st_mode) else 'File',modified_at=before.st_mtime,accessed_at=before.st_atime,changed_at=before.st_ctime,mode=oct(stat.S_IMODE(before.st_mode)),read_only=bool(mapping.get('read_only') or pool.get('read_only')),volume=pool['name'])
        birth=getattr(before,'st_birthtime',None)
        if birth is not None:result['created_at']=birth
        if parts:visit(parent,parts[-1],os.fstat(parent).st_dev,path)
        else:
            result['folders']=1
            for child in os.listdir(parent):
                visit(parent,child,before.st_dev,child)
                if time.monotonic()>deadline or entries>=100000:warning('Folder calculation reached its safety limit; displayed totals are partial.');break
        files.ctx.volume(pool['name']) if not share.startswith('foreign:') else None
    result['folders']=max(0,result['folders']-(1 if result['type']=='Folder' else 0))
    result['calculated_at']=time.time()
    return result
