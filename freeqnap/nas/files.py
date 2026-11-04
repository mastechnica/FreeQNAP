"""Descriptor-relative manual file operations; no shell, symlink following or overwrite."""
import base64
import contextlib
import ctypes
import errno
import hashlib
import json
import os
import secrets
import stat
import time
from pathlib import Path
from .common import name

MAX_CHUNK = 512 * 1024

def relative(value):
    if not isinstance(value, str) or len(value) > 2048 or '\x00' in value:
        raise ValueError('Invalid relative path')
    parts = Path(value).parts
    if Path(value).is_absolute() or '..' in parts or any(p.startswith('.freeqnap') for p in parts):
        raise ValueError('Path must remain inside a selected shared folder')
    return parts

def rename_exclusive(source_fd, source, target_fd, target):
    """Linux renameat2 guarantees an existing target is never replaced by a race."""
    library = ctypes.CDLL(None, use_errno=True)
    if not hasattr(library, 'renameat2'):
        raise ValueError('Atomic no-overwrite rename is unavailable on this host')
    result = library.renameat2(source_fd, os.fsencode(source), target_fd, os.fsencode(target), 1)
    if result:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number))

class Files:
    def __init__(self, context):
        self.ctx = context

    def mapping(self, share_id):
        if isinstance(share_id,str) and share_id.startswith('pool:'):
            pool,mount=self.ctx.volume(name(share_id[5:]))
            return {'name':share_id,'pool':pool['name'],'path':str(mount),'gid':os.getegid(),'volume_root':True,'read_only':bool(pool.get('read_only'))}
        return self.ctx.config()['shares'].get(name(share_id))

    def writable(self,share_id):
        share=self.mapping(share_id)
        if not share or share.get('read_only'):raise ValueError('This folder is read-only or access was removed')
        pool,_=self.ctx.volume(share['pool'])
        if pool.get('read_only'):raise ValueError('This volume is read-only')
        return share

    def protect_library_parent(self,share_id,path):
        share=self.mapping(share_id)
        if not share:raise ValueError('Unknown shared folder')
        candidate=Path(share['path']).joinpath(*relative(path))
        pools=self.ctx.config()['pools']
        extra=[v for values in self.ctx.state.setting('personal-library-locations',{}).values() for v in values]
        for key in ('myradio','personal-photos','personal-files'):
            cfg=self.ctx.state.setting(key,{})
            for location in ([cfg] if cfg else [])+cfg.get('previous_locations',[])+extra:
                pool=pools.get(location.get('pool'))
                if not pool:continue
                protected=Path(pool['mountpoint'])/location['folder']
                if candidate==protected or candidate in protected.parents:raise ValueError('This folder contains a personal library or retained archive. Change its location in Settings instead of moving or deleting it.')

    @contextlib.contextmanager
    def directory(self, share_id, path=''):
        share = self.mapping(share_id)
        if not share:
            raise ValueError('Unknown shared folder')
        pool, mount = self.ctx.volume(share['pool'])
        if not share.get('personal_root') and (Path(share['path']) if share.get('volume_root') else Path(share['path']).parent) != mount:
            raise ValueError('Share root mapping changed')
        if share.get('personal_root'):
            try:components=Path(share['path']).relative_to(mount).parts
            except ValueError:raise ValueError('Personal folder mapping escaped its volume') from None
            descriptor=os.open(mount,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:
                for component in relative(str(Path(*components))):
                    child=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=descriptor);os.close(descriptor);descriptor=child
                    if os.fstat(descriptor).st_dev!=mount.stat().st_dev:raise ValueError('Personal folder contains a nested mount')
            except Exception:os.close(descriptor);raise
        else:descriptor = os.open(share['path'], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            self.ctx.volume(share['pool'])
            device = os.fstat(descriptor).st_dev
            if device != mount.stat().st_dev:
                raise ValueError('Share is not on the expected volume')
            for component in relative(path):
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                os.close(descriptor);descriptor = child
                if os.fstat(descriptor).st_dev != device:
                    raise ValueError('Nested mounts are not followed')
            yield descriptor, share, pool
        finally:
            os.close(descriptor)

    def list(self, request):
        with self.directory(request['share'], request.get('path', '')) as (directory, _, _):
            entries = [];query=request.get('query','');offset=request.get('offset',0);limit=request.get('limit',500)
            if not isinstance(query,str) or len(query)>255 or isinstance(offset,bool) or not isinstance(offset,int) or not 0<=offset<=1000000 or isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=1000:raise ValueError('Invalid folder filter or page')
            names=sorted(n for n in os.listdir(directory) if not n.startswith('.freeqnap') and query.casefold() in n.casefold())
            for filename in names[offset:offset+limit]:
                if filename.startswith('.freeqnap'):continue
                info = os.stat(filename, dir_fd=directory, follow_symlinks=False)
                entries.append({'name': filename, 'directory': stat.S_ISDIR(info.st_mode),
                                'symlink': stat.S_ISLNK(info.st_mode), 'bytes': info.st_size,
                                'modified_at': info.st_mtime, 'mode': oct(stat.S_IMODE(info.st_mode))})
            return {'entries':entries,'limit':limit,'offset':offset,'total_entries':len(names),'truncated':offset+limit<len(names),'next_offset':offset+limit if offset+limit<len(names) else None}

    def media_neighbors(self,request):
        from ..media_http import kind
        leaf=request.get('name');query=request.get('query','')
        if len(relative(leaf))!=1 or not isinstance(query,str) or len(query)>255:raise ValueError('Choose a media filename in this folder')
        with self.directory(request['share'],request.get('path','')) as (fd,_,_):
            names=[];device=os.fstat(fd).st_dev
            for filename in sorted(os.listdir(fd)):
                if filename.startswith('.freeqnap') or query.casefold() not in filename.casefold() or not kind(filename):continue
                info=os.stat(filename,dir_fd=fd,follow_symlinks=False)
                if stat.S_ISREG(info.st_mode) and info.st_dev==device:names.append(filename)
            if leaf not in names:raise ValueError('The media file is no longer in this folder')
            index=names.index(leaf)
            def item(i):return {'name':names[i],'directory':False,'symlink':False} if 0<=i<len(names) else None
            return {'previous':item(index-1),'next':item(index+1),'position':index+1,'total':len(names)}

    def mkdir(self, request):
        self.writable(request['share'])
        folder = request.get('name', '')
        if len(relative(folder)) != 1:
            raise ValueError('Choose one new folder name')
        with self.directory(request['share'], request.get('path', '')) as (directory, share, _):
            os.mkdir(folder, mode=0o770 if share.get("volume_root") else 0o2770, dir_fd=directory)
            os.chown(folder, 0, share['gid'], dir_fd=directory, follow_symlinks=False)
            os.fsync(directory)
        return {'created': folder}

    def read(self, request):
        parts = relative(request.get('path', ''))
        if not parts:raise ValueError('Select a regular file')
        offset = int(request.get('offset', 0));count = int(request.get('count', MAX_CHUNK))
        if offset < 0 or not 1 <= count <= MAX_CHUNK:raise ValueError('Invalid file range')
        with self.directory(request['share'], str(Path(*parts[:-1]))) as (directory, _, _):
            descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            try:
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode) or info.st_dev!=os.fstat(directory).st_dev:raise ValueError('Select a regular file on the expected volume')
                data = os.pread(descriptor, count, offset)
            finally:os.close(descriptor)
        return {'data_base64': base64.b64encode(data).decode(), 'offset': offset,
                'total_bytes': info.st_size, 'modified_at':info.st_mtime, 'etag': f'{info.st_dev}-{info.st_ino}-{info.st_size}-{info.st_mtime_ns}'}

    def upload_begin(self, request):
        self.writable(request['share'])
        parts = relative(request.get('path', ''));total = int(request.get('bytes', -1))
        if not parts or not 0 <= total <= 64 * 1024**3:raise ValueError('Choose a file of at most 64 GiB')
        with self.directory(request['share'], str(Path(*parts[:-1]))) as (_, share, pool):
            free = os.statvfs(pool['mountpoint'])
            if total + 256 * 1024**2 > free.f_bavail * free.f_frsize:raise ValueError('Insufficient free space, including reserve')
            private = Path(pool['mountpoint']) / '.freeqnap' / 'uploads'
            private.mkdir(mode=0o700, parents=True, exist_ok=True)
            ident = secrets.token_hex(16);path = private / ident
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(descriptor)
            record = {'id': ident, 'pool': pool['name'], 'filesystem_uuid': pool['filesystem_uuid'],
                      'share': share['name'], 'path': request['path'], 'temporary': str(path),
                      'bytes': total, 'offset': 0, 'hash_chain': '0'*64, 'created_at': time.time(), 'finished': False}
            self.ctx.state.set('upload:' + ident, record)
        return {'upload_id': ident, 'chunk_bytes': MAX_CHUNK}

    def upload_chunk(self, request):
        ident = request.get('upload_id', '')
        if not isinstance(ident, str) or not len(ident) == 32 or any(c not in '0123456789abcdef' for c in ident):
            raise ValueError('Unknown upload')
        with self.ctx.lock():
            record = self.ctx.state.setting('upload:' + ident)
            if record:self.writable(record['share'])
            if not record or record['finished'] or time.time() - record['created_at'] > 86400:
                raise ValueError('Upload expired or completed; incomplete data was retained')
            self.ctx.volume(record['pool'])
            try:data = base64.b64decode(request.get('data_base64', ''), validate=True)
            except (ValueError, TypeError) as error:raise ValueError('Invalid upload chunk') from error
            if len(data) != min(MAX_CHUNK, record['bytes']-record['offset']) or int(request.get('offset', -1)) != record['offset']:
                raise ValueError('Chunk offset or length differs from the upload record')
            checksum = hashlib.sha256(data).hexdigest()
            if checksum != request.get('sha256'):raise ValueError('Upload chunk checksum mismatch')
            descriptor = os.open(record['temporary'], os.O_WRONLY | os.O_NOFOLLOW)
            try:
                if os.fstat(descriptor).st_size != record['offset']:raise ValueError('Partial upload changed; reconcile before resuming')
                written = os.pwrite(descriptor, data, record['offset'])
                if written != len(data):raise ValueError('Short upload write')
                os.fsync(descriptor)
            finally:os.close(descriptor)
            record['offset'] += len(data)
            record['hash_chain'] = hashlib.sha256((record['hash_chain']+checksum).encode()).hexdigest()
            self.ctx.state.set('upload:' + ident, record)
        return {'upload_id': ident, 'offset': record['offset']}

    def upload_finish(self, request):
        ident = request.get('upload_id', '')
        with self.ctx.lock():
            record = self.ctx.state.setting('upload:' + ident)
            if record:self.writable(record['share'])
            if not record or record['finished'] or record['offset'] != record['bytes']:
                raise ValueError('Upload is unknown, incomplete or already finished')
            pool, _ = self.ctx.volume(record['pool'])
            if pool['filesystem_uuid'] != record['filesystem_uuid']:raise ValueError('Upload volume identity changed')
            parts = relative(record['path'])
            with self.directory(record['share'], str(Path(*parts[:-1]))) as (directory, share, _):
                source = Path(record['temporary'])
                descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
                try:
                    digest=hashlib.sha256();chain='0'*64
                    with os.fdopen(os.dup(descriptor),'rb') as content:
                        while chunk:=content.read(MAX_CHUNK):
                            digest.update(chunk)
                            chain=hashlib.sha256((chain+hashlib.sha256(chunk).hexdigest()).encode()).hexdigest()
                    checksum=digest.hexdigest()
                    if chain != record['hash_chain'] or chain != request.get('hash_chain'):raise ValueError('Upload readback checksum chain mismatch')
                    os.fchown(descriptor, 0, share['gid']);os.fchmod(descriptor, 0o660);os.fsync(descriptor)
                finally:os.close(descriptor)
                parent = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:rename_exclusive(parent, source.name, directory, parts[-1])
                finally:os.close(parent)
                os.fsync(directory)
            record['finished'] = True;self.ctx.state.set('upload:' + ident, record)
        return {'uploaded': record['path'], 'sha256': checksum, 'existing_file_replaced': False}

    def move_plan(self, request):
        self.writable(request['share'])
        parts = relative(request.get('path', ''))
        self.protect_library_parent(request['share'],request.get('path',''))
        if not parts:raise ValueError('Share roots cannot be moved or deleted')
        destination = request.get('new_name')
        if destination is not None and len(relative(destination)) != 1:raise ValueError('Choose one destination name')
        with self.directory(request['share'], str(Path(*parts[:-1]))) as (directory, _, pool):
            info = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
            body = {'share': request['share'], 'path': request['path'], 'new_name': destination,
                    'filesystem_uuid': pool['filesystem_uuid'], 'inode': info.st_ino,
                    'device': info.st_dev, 'size': info.st_size, 'mtime_ns': info.st_mtime_ns}
        return self.ctx.plan('file-move', body, ('RENAME ' if destination else 'TRASH ') + parts[-1])

    def move(self, request):
        with self.ctx.lock():
            plan_path, plan = self.ctx.reviewed(request, 'file-move');body = plan['body'];parts = relative(body['path'])
            self.writable(body['share']);self.protect_library_parent(body['share'],body['path'])
            with self.directory(body['share'], str(Path(*parts[:-1]))) as (directory, _, pool):
                info = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
                if (info.st_ino, info.st_dev, info.st_size, info.st_mtime_ns, pool['filesystem_uuid']) != (body['inode'], body['device'], body['size'], body['mtime_ns'], body['filesystem_uuid']):
                    raise ValueError('File identity changed since review')
                self.ctx.consume(plan_path, plan)
                if body['new_name']:
                    rename_exclusive(directory, parts[-1], directory, body['new_name'])
                else:
                    trash = Path(pool['mountpoint']) / '.freeqnap' / 'trash';trash.mkdir(mode=0o700, parents=True, exist_ok=True)
                    target = os.open(trash, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                    record={**body,'pool':pool['name'],'trash_id':plan['id'],'deleted_at':time.time(),'pending':True}
                    self.ctx.state.set('trash:'+plan['id'],record)
                    try:
                        rename_exclusive(directory, parts[-1], target, plan['id']);os.fsync(target)
                        record['pending']=False;self.ctx.state.set('trash:'+plan['id'],record)
                    finally:os.close(target)
                os.fsync(directory)
        return {'completed': True, 'moved_to_recoverable_trash': body['new_name'] is None, 'plan_id': plan['id']}
