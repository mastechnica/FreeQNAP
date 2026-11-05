"""Bounded local media indexing, NFO import and explicitly requested TV metadata."""
import base64
import contextlib
import secrets
import hashlib
import json
import os
import re
import sqlite3
import pwd
import stat
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from xml.etree import ElementTree as ET
from .common import name

EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v', '.mp3', '.flac', '.m4a', '.ogg', '.wav', '.jpg', '.jpeg', '.png'}

def nfo(data):
    if len(data) > 2 * 1024**2 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('NFO is too large or contains a document/entity declaration')
    root = ET.fromstring(data)
    result = {}
    for key in ('title', 'originaltitle', 'plot', 'year', 'premiered', 'season', 'episode', 'studio', 'director', 'producer', 'rating', 'runtime', 'mpaa', 'tagline', 'mediatype', 'provider', 'source_url', 'trailer'):
        item = root.find(key)
        if item is not None and item.text:result[key] = item.text[:10000]
    result['genres'] = [item.text[:200] for item in root.findall('genre') if item.text][:20]
    result['actors'] = [{'name':a.findtext('name','')[:200],'role':a.findtext('role','')[:200]} for a in root.findall('actor')][:100]
    return result

class Media:
    def __init__(self, context):
        self.ctx = context
        if not context.state.setting('dlna_udn'):
            import uuid
            context.state.set('dlna_udn','uuid:'+str(uuid.uuid4()))
        with context.state.connect() as database:
            database.execute('CREATE TABLE IF NOT EXISTS media(id TEXT PRIMARY KEY,library TEXT NOT NULL,path TEXT NOT NULL,signature TEXT NOT NULL,metadata TEXT NOT NULL,last_seen REAL NOT NULL)')

    def library(self, request):
        ident = name(request.get('name'))
        share = self.ctx.config()['shares'].get(name(request.get('share')))
        if not share:raise ValueError('Choose a designated shared media folder')
        pool, mount = self.ctx.volume(share['pool'])
        interface = request.get('interface', 'enp0s1')
        if interface not in ('enp0s1', 'enp0s3'):raise ValueError('Choose an RJ45 interface')
        value = {'name': ident, 'share': share['name'], 'pool': pool['name'], 'path': share['path'],
                 'filesystem_uuid': pool['filesystem_uuid'], 'dlna': request.get('dlna') is True,
                 'interface': interface, 'online_metadata': request.get('online_metadata') is True,
                 'scan_enabled':request.get('scan_enabled',True) is True, 'exclude_folders':self.exclusions(request.get('exclude_folders',[])), 'scan_limit': 100000, 'transcoding_enabled': False}
        if value['dlna'] and request.get('public_lan_confirmation') != 'ENABLE APPROVALS ' + ident:
            raise ValueError('DLNA requires explicit device approval; confirm enabling the selected folder behind that policy')
        config = self.ctx.config();config['libraries'][ident] = value;self.ctx.save(config)
        return value

    def exclusions(self, values):
        from .files import relative
        if not isinstance(values,list) or len(values)>100:raise ValueError('Choose up to 100 excluded relative folders')
        for v in values:
            if not relative(v):raise ValueError('Exclude a subfolder, not the entire library')
        return values

    def scanner_settings(self, request):
        enabled=request.get('enabled')
        if not isinstance(enabled,bool):raise ValueError('Choose whether scanning is enabled')
        self.ctx.state.set('media-scanning-enabled',enabled)
        return {'enabled':enabled}

    def scanner_status(self, request=None):
        return {'enabled':self.ctx.state.setting('media-scanning-enabled',True), 'libraries':[{'name':l['name'],'enabled':l.get('scan_enabled',True),'progress':self.ctx.state.setting('scan-progress:'+l['name']), 'last_scan':self.ctx.state.setting('scan:'+l['name'])} for l in self.ctx.config()['libraries'].values()]}

    def scan(self, request):
        library = self.ctx.config()['libraries'].get(name(request.get('library')))
        if not library:raise ValueError('Unknown media library')
        if not self.ctx.state.setting('media-scanning-enabled',True) or not library.get('scan_enabled',True):raise ValueError('Scanning is disabled')
        pool, _ = self.ctx.volume(library['pool'])
        if pool['filesystem_uuid'] != library['filesystem_uuid']:raise ValueError('Media volume identity changed')
        start = time.time();count = 0;errors = [];complete = True
        self.ctx.state.set('scan-progress:'+library['name'],{'running':True,'phase':'Starting','indexed':0,'updated_at':start})
        root = os.open(library['path'], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            device = os.fstat(root).st_dev
            for folder, directories, files, directory in os.fwalk('.', dir_fd=root, follow_symlinks=False):
                directories[:] = [d for d in directories if not d.startswith('.') and str(Path(folder)/d) not in library.get('exclude_folders',[])]
                if not self.ctx.state.setting('media-scanning-enabled',True) or not self.ctx.config()['libraries'].get(library['name'],{}).get('scan_enabled',True):
                    complete=False;break
                self.ctx.state.set('scan-progress:'+library['name'],{'running':True,'phase':'Scanning','folder':folder,'indexed':count,'updated_at':time.time()})
                if os.fstat(directory).st_dev != device:
                    directories[:] = [];continue
                for filename in files:
                    if count >= library['scan_limit'] or time.time() - start > 300:
                        complete = False;break
                    if Path(filename).suffix.lower() not in EXTENSIONS:continue
                    descriptor = -1
                    try:
                        descriptor = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                        info = os.fstat(descriptor)
                        if not stat.S_ISREG(info.st_mode) or info.st_dev != device:continue
                        relative = str(Path(folder) / filename)
                        ident = hashlib.sha256((library['name'] + '\0' + relative).encode()).hexdigest()
                        signature = f'{info.st_ino}:{info.st_size}:{info.st_mtime_ns}'
                        for companion in (Path(filename).stem+'.nfo','movie.nfo','tvshow.nfo',Path(filename).stem+'.jpg','poster.jpg','folder.jpg','cover.jpg'):
                            try:
                                cinfo=os.stat(companion,dir_fd=directory,follow_symlinks=False)
                                if stat.S_ISREG(cinfo.st_mode):signature+=f':{companion}:{cinfo.st_ino}:{cinfo.st_size}:{cinfo.st_mtime_ns}'
                            except FileNotFoundError:pass
                        with self.ctx.state.connect() as db:
                            old = db.execute('SELECT signature FROM media WHERE id=?', (ident,)).fetchone()
                        if old and old[0] == signature:
                            with self.ctx.state.connect() as db:db.execute('UPDATE media SET last_seen=? WHERE id=?', (start, ident))
                            count += 1;continue
                        metadata = {'title': Path(filename).stem, 'bytes': info.st_size, 'modified_at': info.st_mtime,
                                    'source': 'filename', 'artwork': []}
                        # An already-open FD prevents a concurrent symlink replacement from redirecting ffprobe.
                        privileges = {}
                        if os.geteuid() == 0:
                            account=pwd.getpwnam('gerbera');privileges={'user':account.pw_uid,'group':account.pw_gid,'extra_groups':[]}
                        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json',
                                                '/proc/self/fd/' + str(descriptor)], pass_fds=(descriptor,), capture_output=True, timeout=10, **privileges)
                        if probe.returncode == 0 and len(probe.stdout) <= 1024**2:
                            metadata['probe'] = json.loads(probe.stdout)
                            tags = metadata['probe'].get('format', {}).get('tags', {})
                            metadata['title'] = tags.get('title', metadata['title'])
                        for sidecar in (Path(filename).stem + '.nfo', 'movie.nfo', 'tvshow.nfo'):
                            try:
                                side = os.open(sidecar, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                                try:
                                    if not stat.S_ISREG(os.fstat(side).st_mode):continue
                                    data = os.read(side, 2 * 1024**2 + 1)
                                finally:os.close(side)
                                metadata.update(nfo(data));metadata['source'] = 'local-nfo';break
                            except FileNotFoundError:pass
                        for image in ('poster.jpg', 'folder.jpg', 'cover.jpg', Path(filename).stem + '.jpg'):
                            try:
                                image_info = os.stat(image, dir_fd=directory, follow_symlinks=False)
                                if stat.S_ISREG(image_info.st_mode):metadata['artwork'].append(str(Path(folder) / image))
                            except FileNotFoundError:pass
                        with self.ctx.state.connect() as db:
                            db.execute('INSERT OR REPLACE INTO media VALUES(?,?,?,?,?,?)', (ident, library['name'], relative, signature, json.dumps(metadata), start))
                        count += 1
                    except (OSError, ValueError, ET.ParseError, subprocess.TimeoutExpired) as error:
                        if len(errors) < 100:errors.append({'path': str(Path(folder) / filename), 'error': type(error).__name__})
                    finally:
                        if descriptor >= 0:os.close(descriptor)
                if not complete:break
        finally:
            os.close(root)
            self.ctx.state.set('scan-progress:'+library['name'],{'running':False,'phase':('Finished with errors' if errors else 'Finished') if complete else 'Stopped / incomplete','indexed':count,'updated_at':time.time()})
        # Partial scans never delete or mark unseen entries missing.
        if complete and not errors:
            with self.ctx.state.connect() as db:db.execute('DELETE FROM media WHERE library=? AND last_seen<?', (library['name'], start))
        self.ctx.volume(library['pool'])
        result = {'library': library['name'], 'indexed': count, 'complete': complete and not errors,
                  'errors': errors, 'finished_at': time.time(), 'online_lookup_performed': False}
        self.ctx.state.set('scan:' + library['name'], result)
        return result

    def catalog(self, request):
        from ..access_scope import check
        lib=self.ctx.config()['libraries'].get(request.get('library'),{})
        pool=self.ctx.config()['pools'].get(lib.get('pool'),{})
        if pool:check(self.ctx,pool,content=True)
        ident = name(request.get('library'))
        offset = max(0, int(request.get('offset', 0)))
        with self.ctx.state.connect() as db:
            rows = db.execute('SELECT id,path,metadata FROM media WHERE library=? ORDER BY path LIMIT 200 OFFSET ?', (ident, offset)).fetchall()
            count = db.execute('SELECT count(*) FROM media WHERE library=?', (ident,)).fetchone()[0]
        return {'entries': [{'id': row['id'], 'path': row['path'], **json.loads(row['metadata'])} for row in rows], 'total': count, 'offset': offset}

    def provider_status(self, request=None):
        return {'tvmaze':True,'omdb_configured':bool(self.ctx.state.setting('media-provider-omdb'))}

    def provider_save(self, request):
        if request.get('provider')!='omdb':raise ValueError('Choose OMDb')
        key=request.get('api_key','')
        if not isinstance(key,str) or not re.fullmatch('[A-Za-z0-9]{1,128}',key):raise ValueError('Enter your OMDb API key')
        self.ctx.state.set('media-provider-omdb',key)
        return {'saved':True}

    def omdb_lookup(self, request):
        key=self.ctx.state.setting('media-provider-omdb')
        if not key:raise ValueError('Add your OMDb API key in website settings first')
        query=request.get('query','')
        if not isinstance(query,str) or not 1<=len(query)<=200:raise ValueError('Enter a title')
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        url='https://www.omdbapi.com/?'+urllib.parse.urlencode({'apikey':key,'t':query,'plot':'full'})
        try:
            with urllib.request.build_opener(NoRedirect).open(url,timeout=15) as response:data=response.read(2*1024**2+1)
            if len(data)>2*1024**2:raise ValueError('Response too large')
            item=json.loads(data)
        except Exception:raise ValueError('OMDb request failed; check provider settings and connectivity') from None
        results=[]
        if item.get('Response')=='True':
            imdb=item.get('imdbID','')
            results=[{'title':item.get('Title',''),'year':item.get('Year',''),'plot':item.get('Plot',''),'genres':item.get('Genre','').split(', '),'director':item.get('Director',''),'actors':[{'name':v,'role':''} for v in item.get('Actors','').split(', ')],'runtime':item.get('Runtime',''),'rating':item.get('imdbRating',''),'mediatype':item.get('Type',''),'source_url':'https://www.imdb.com/title/'+imdb+'/' if re.fullmatch('tt[0-9]+',imdb) else ''}]
        return {'provider':'OMDb','results':results,'attribution':'Metadata from OMDb; provider terms apply.'}

    def lookup(self, request):
        library = self.ctx.config()['libraries'].get(name(request.get('library')))
        if not library or not library.get('online_metadata',False):raise ValueError('Enable optional external metadata lookup for this library first')
        if request.get('provider','tvmaze')=='omdb':return self.omdb_lookup(request)
        if request.get('provider','tvmaze')!='tvmaze':raise ValueError('Unknown provider')
        query = request.get('query', '')
        if not isinstance(query, str) or not 1 <= len(query) <= 200:raise ValueError('Enter a title to search')
        # Explicit request, fixed HTTPS endpoint; no arbitrary URL or embedded HTML rendering.
        url = 'https://api.tvmaze.com/search/shows?' + urllib.parse.urlencode({'q': query})
        with urllib.request.urlopen(url, timeout=15) as response:
            if urllib.parse.urlsplit(response.url).hostname != 'api.tvmaze.com':raise ValueError('Unexpected metadata redirect')
            data = response.read(2 * 1024**2 + 1)
        if len(data) > 2 * 1024**2:raise ValueError('Metadata response too large')
        results = json.loads(data)
        return {'provider': 'TVmaze', 'results': [{'id': row['show']['id'], 'title': row['show']['name'],
                'year': str(row['show'].get('premiered') or '')[:4], 'genres': row['show'].get('genres', []),
                'plot': re.sub('<[^>]+>', '', row['show'].get('summary') or ''),
                'source_url': row['show']['url']} for row in results[:20]],
                'attribution': 'TV information from TVmaze, CC BY-SA; preserve provider/source attribution.'}

    def apply_metadata(self, request):
        ident = request.get('id', '')
        if not re.fullmatch('[a-f0-9]{64}', ident):raise ValueError('Select an indexed media item')
        value = request.get('metadata', {})
        if not isinstance(value, dict) or set(value) - {'title', 'plot', 'year', 'genres', 'provider', 'source_url', 'actors', 'director', 'producer', 'studio', 'premiered', 'season', 'episode', 'originaltitle', 'rating', 'runtime', 'mpaa', 'tagline', 'mediatype', 'trailer'} or len(json.dumps(value)) > 20000:
            raise ValueError('Invalid metadata fields')
        for k,v in value.items():
            if k=='genres':
                if not isinstance(v,list) or len(v)>30 or any(not isinstance(x,str) or len(x)>200 for x in v):raise ValueError('Invalid genres')
            elif k=='actors':
                if not isinstance(v,list) or len(v)>100 or any(not isinstance(x,dict) or set(x)-{'name','role'} or any(not isinstance(t,str) or len(t)>200 for t in x.values()) for x in v):raise ValueError('Invalid cast')
            elif not isinstance(v,str) or len(v)>10000:raise ValueError('Invalid metadata text')
        with self.ctx.state.connect() as db:
            row = db.execute('SELECT metadata FROM media WHERE id=?', (ident,)).fetchone()
            if not row:raise ValueError('Unknown media item')
            metadata = json.loads(row[0]);metadata.update(value);metadata['source'] = 'owner-selected-metadata'
            db.execute('UPDATE media SET metadata=? WHERE id=?', (json.dumps(metadata), ident))
        saved=False
        if request.get('save_sidecar'):
            self.save_sidecar(ident,metadata);saved=True
        return {'updated': ident, 'source_file_modified': saved}

    def item(self, ident):
        if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{64}',ident):raise ValueError('Choose a media title')
        with self.ctx.state.connect() as db:row=db.execute('SELECT library,path,metadata FROM media WHERE id=?',(ident,)).fetchone()
        if not row:raise ValueError('Title is no longer indexed')
        library=self.ctx.config()['libraries'].get(row['library'])
        if not library:raise ValueError('Library is no longer configured')
        pool,_=self.ctx.volume(library['pool'])
        if pool['filesystem_uuid']!=library['filesystem_uuid']:raise ValueError('Media filesystem changed')
        return library,row['path'],json.loads(row['metadata']),pool

    def write_companion(self, ident, suffix, data):
        from .files import Files,relative
        library,path,_,pool=self.item(ident)
        if pool.get('read_only'):raise ValueError('This media volume is read-only')
        parts=relative(path);leaf=Path(parts[-1]).stem+suffix
        with Files(self.ctx).directory(library['share'],str(Path(*parts[:-1]))) as (directory,share,_):
            if share.get('read_only'):raise ValueError('This media folder is read-only')
            token='.freeqnap-companion-'+secrets.token_hex(12)
            fd=os.open(token,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
            try:
                with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
                # Preserve previous sidecar/artwork for manual rollback, never follow links.
                try:
                    info=os.stat(leaf,dir_fd=directory,follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode):raise ValueError('Companion path is not a regular file')
                    backup=leaf+'.backup-'+secrets.token_hex(6)
                    os.link(leaf,backup,src_dir_fd=directory,dst_dir_fd=directory,follow_symlinks=False)
                except FileNotFoundError:pass
                os.rename(token,leaf,src_dir_fd=directory,dst_dir_fd=directory);os.fsync(directory)
            finally:
                try:os.unlink(token,dir_fd=directory)
                except FileNotFoundError:pass
        return str(Path(path).with_suffix(suffix))

    def save_sidecar(self, ident, metadata):
        root=ET.Element('movie')
        for key,value in metadata.items():
            if key in ('title','originaltitle','plot','year','director','producer','studio','premiered','season','episode','rating','runtime','mpaa','tagline','mediatype','provider','source_url','trailer'):
                ET.SubElement(root,key).text=str(value)
        for genre in metadata.get('genres',[]):ET.SubElement(root,'genre').text=str(genre)
        for actor in metadata.get('actors',[]):
            a=ET.SubElement(root,'actor')
            for k in ('name','role'):ET.SubElement(a,k).text=str(actor.get(k,''))
        return self.write_companion(ident,'.nfo',ET.tostring(root,encoding='utf-8',xml_declaration=True))

    def artwork(self, request):
        from .files import Files,relative
        ident=request.get('id');library,path,metadata,pool=self.item(ident)
        if 'data_base64' in request:
            try:data=base64.b64decode(request['data_base64'],validate=True)
            except (ValueError,TypeError):raise ValueError('Invalid image upload')
            if not 1<=len(data)<=1024*1024:raise ValueError('Cover image must be at most 1 MiB')
            # Decode/re-encode through a bounded, unprivileged ffmpeg process below.
            if data.startswith(b'\x89PNG\r\n\x1a\n'):codec='png'
            elif data.startswith(b'\xff\xd8\xff'):codec='mjpeg'
            else:raise ValueError('Choose a PNG or JPEG cover image')
            input_data=data;args=['-f','image2pipe','-c:v',codec,'-i','pipe:0']
            descriptor=None
        else:
            seconds=request.get('seconds',180)
            if isinstance(seconds,bool) or not isinstance(seconds,(int,float)) or not 0<=seconds<=86400:raise ValueError('Choose a video time from 0 to 86400 seconds')
            parts=relative(path)
            with Files(self.ctx).directory(library['share'],str(Path(*parts[:-1]))) as (directory,_,_):
                descriptor=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
            info=os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):os.close(descriptor);raise ValueError('Choose a regular video')
            args=['-ss',str(seconds),'-i','/proc/self/fd/'+str(descriptor)];input_data=None
        privileges={}
        if os.geteuid()==0:
            account=pwd.getpwnam('gerbera');privileges={'user':account.pw_uid,'group':account.pw_gid,'extra_groups':[]}
        try:
            result=subprocess.run(['ffmpeg','-v','error','-max_alloc','67108864','-protocol_whitelist','file,pipe','-threads','1',*args,'-frames:v','1','-vf','scale=640:-2','-f','image2pipe','-vcodec','mjpeg','pipe:1'],input=input_data,pass_fds=(() if descriptor is None else (descriptor,)),capture_output=True,timeout=30,**privileges)
            if result.returncode or not result.stdout or len(result.stdout)>1024*1024:raise ValueError('Could not generate a cover at that time; try an earlier time or another image')
            artwork=self.write_companion(ident,'.jpg',result.stdout)
        finally:
            if descriptor is not None:os.close(descriptor)
        metadata['artwork']=[artwork]
        with self.ctx.state.connect() as db:db.execute('UPDATE media SET metadata=? WHERE id=?',(json.dumps(metadata),ident))
        return {'saved':artwork}

    def dlna_config(self):
        libraries = []
        for library in self.ctx.config()['libraries'].values():
            if not library['dlna'] or self.ctx.config()['pools'].get(library['pool'],{}).get('encrypted'):continue
            try:
                pool, _ = self.ctx.volume(library['pool'])
                if pool['filesystem_uuid'] == library['filesystem_uuid']:libraries.append(library)
            except (ValueError, OSError):continue
        interfaces = {item['interface'] for item in libraries}
        if len(interfaces) > 1:raise ValueError('Use one explicit LAN interface for this DLNA server')
        root = ET.Element('config', {'version': '2', 'xmlns': 'http://mediatomb.cc/config/2'})
        server = ET.SubElement(root, 'server')
        ET.SubElement(server, 'name').text = 'FreeQNAP Media'
        ET.SubElement(server, 'udn').text = self.ctx.state.setting('dlna_udn', '')
        ET.SubElement(server, 'home').text = '/var/lib/freeqnap-media'
        ET.SubElement(server, 'webroot').text = '/usr/share/gerbera/web'
        ET.SubElement(server, 'port').text = '49152'
        if interfaces:ET.SubElement(server, 'interface').text = next(iter(interfaces))
        ET.SubElement(server, 'ui', {'enabled': 'no'})
        storage = ET.SubElement(server, 'storage')
        sql = ET.SubElement(storage, 'sqlite3', {'enabled': 'yes'})
        ET.SubElement(sql, 'database-file').text = '/var/lib/freeqnap-media/gerbera.db'
        imports = ET.SubElement(root, 'import', {'hidden-files': 'no'})
        autoscan = ET.SubElement(imports, 'autoscan', {'use-inotify': 'yes'})
        for item in libraries:
            ET.SubElement(autoscan, 'directory', {'location': item['path'], 'mode': 'inotify', 'recursive': 'yes', 'hidden-files': 'no'})
        ET.SubElement(root, 'transcoding', {'enabled': 'no'})
        return ET.tostring(root, encoding='unicode'), libraries
