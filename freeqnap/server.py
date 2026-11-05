"""Loopback NAS console. Access remotely through authenticated SSH forwarding."""
import argparse, hashlib, json, os, secrets, threading, time, sqlite3
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, unquote
from . import auth, backups, demo, inventory, accounts, library_shares, activity
from .identity import Identity
from .personal_access import Gateway as PersonalGateway
from .state import State
from .agents import Agents, Denied, Limited, PLAYER_OPERATIONS
from .players import Players
from .media_http import byte_range,content_type,kind as media_kind
from .jobs import Worker
WEB = Path(__file__).resolve().parents[1] / 'web'
CONSOLE_OPERATIONS=frozenset(('photos.icloud-albums-status','photos.icloud-albums-configure','photos.icloud-albums-sync','library.sources-status','library.sources-save','library.sources-scan','myradio.podcast-browser','myradio.card-save','myradio.music-browser','myradio.books-browser','myradio.album-save','myradio.overview','myradio.listen','myradio.providers','myradio.providers-save','myradio.metadata-search','myradio.metadata-apply'))
AUDIT_ROUTES=frozenset('/api/'+p for p in ('session','login','logout','file','photo-file','radio-file','radio-stream','podcast-art','library-card-art','album-art','metadata-match-art','zip','pool-file','foreign-file','volume-file','download-file','library-shares/change','library-shares','users','users/change','users/storage','identity','identity/save','identity/link','identity/assign','identity/unlink','account/password','account/local-password','account/preferences','social/prepare','social/read','social/discard','agents/create','agents/revoke','agents/catalog','agents/players/discover','agents/players/approve','agents/players/configure','raid-backup','system-backup','artifact'))

def handler(state, destination, snapshot=None, preview=False, broker=None, origins=()):
    from .nas.broker import Client
    nas = broker or Client()
    from .system_summary import Summary
    family_system = Summary(nas, snapshot)
    identity = Identity(state,origins)
    agents = Agents(state)
    players = Players(state,nas,agents)
    radio_slots=threading.BoundedSemaphore(4)
    if not preview:players.resume()

    class Handler(BaseHTTPRequestHandler):

        def handle_one_request(self):
            self.audit_actor=None;self.audit_code=0;self.audit_size=0;self.audit_suppress=False
            try:return super().handle_one_request()
            finally:
                path=urlsplit(getattr(self,'path','')).path
                if self.audit_actor and path.startswith('/api/') and path not in ('/api/activity','/api/status','/api/nas/status','/api/jobs','/api/account','/api/users/usage'):
                    operation=path.removeprefix('/api/').replace('/','.')
                    if path.startswith('/api/agent/v1/operations/'):operation=path.removeprefix('/api/agent/v1/operations/')
                    from .agents import BACKEND_OPERATIONS,OPERATIONS
                    known=path in AUDIT_ROUTES or path.startswith('/api/nas/') and path.removeprefix('/api/nas/') in BACKEND_OPERATIONS|CONSOLE_OPERATIONS or path.startswith('/api/agent/v1/operations/') and operation in OPERATIONS
                    if known and activity.SAFE.fullmatch(operation) and (not self.audit_suppress or self.audit_code>=400):
                        try:activity.record(state,self.audit_actor,operation,'denied' if self.audit_code in (401,403) else 'failed' if self.audit_code>=400 else 'accepted' if self.command=='POST' else 'succeeded',size=self.audit_size)
                        except (OSError,ValueError,sqlite3.Error):self.server.audit_error='Activity logging could not save an event. Check NAS storage and service health.'

        def send_response(self,code,message=None):
            self.audit_code=code
            return super().send_response(code,message)

        def send_header(self,keyword,value):
            if keyword.lower()=='content-length':
                try:self.audit_size=int(value)
                except ValueError:pass
            return super().send_header(keyword,value)

        def log_message(self, *args):
            pass

        def send(self, code, value, cookie=None):
            raw = json.dumps(value).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            if isinstance(value,dict) and value.get('signed_out'):
                self.send_header('Clear-Site-Data', '"cache"')
            if cookie:
                self.send_header('Set-Cookie', cookie)
            self.end_headers()
            if self.command!='HEAD':self.wfile.write(raw)

        def safe_host(self):
            allowed = {'localhost:' + str(self.server.server_port), '127.0.0.1:' + str(self.server.server_port)}
            allowed.update(urlsplit(origin).netloc for origin in origins)
            return self.headers.get('Host') in allowed

        def safe_origin(self):
            return self.headers.get('Origin') in {'http://localhost:'+str(self.server.server_port),'http://127.0.0.1:'+str(self.server.server_port),*origins}

        def authenticated(self):
            try:
                c = SimpleCookie(self.headers.get('Cookie', ''))
                token = c['freeqnap_session'].value
            except (KeyError, ValueError, CookieError):
                return None
            result=auth.session(state, token)
            if result:self.audit_actor='user:'+result['user']['id']
            return result

        def gateway(self):
            query=parse_qs(urlsplit(self.path).query);share=self.headers.get('X-Library-Share') or query.get('shared',[None])[0]
            return PersonalGateway(nas,state,self.authenticated,share,self.headers.get('X-Personal-User'))

        def redirect(self,url,cookie=None):
            self.send_response(303);self.send_header('Location',url);self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer')
            if cookie:self.send_header('Set-Cookie',cookie)
            self.send_header('Content-Length','0');self.end_headers()

        def session_cookie(self,token):return 'freeqnap_session='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200'+('; Secure' if self.headers.get('X-Forwarded-Proto')=='https' else '')

        def identity_get(self,path):
            if path not in ('/auth/oidc/start','/auth/oidc/callback'):return False
            if self.client_address[0] not in ('127.0.0.1','::1') or self.headers.get('X-Forwarded-Proto')!='https':self.send(403,{'error':'Use trusted HTTPS for cloud sign-in'});return True
            try:
                if path.endswith('/start'):
                    url,binding=identity.begin();self.redirect(url,'freeqnap_oidc='+binding+'; HttpOnly; SameSite=Lax; Secure; Path=/auth/oidc/; Max-Age=300')
                else:
                    query=parse_qs(urlsplit(self.path).query);cookies=SimpleCookie(self.headers.get('Cookie',''));session=self.authenticated()
                    result=identity.finish(query.get('state',[''])[0],query.get('code',[''])[0],cookies['freeqnap_oidc'].value,session['user'] if session else None)
                    self.redirect('/#account' if result.get('linked') else result.get('landing_page','/#overview'),self.session_cookie(result['token']) if result.get('token') else 'freeqnap_oidc=; HttpOnly; SameSite=Lax; Secure; Path=/auth/oidc/; Max-Age=0')
            except (ValueError,OSError,KeyError,CookieError):self.send(400,{'error':'Cloud sign-in could not be completed. Use local sign-in and check the provider/link settings.'})
            return True

        def do_GET(self):
            if not self.safe_host():
                self.send(403, {'error': 'Unrecognized host'})
                return
            path = urlsplit(self.path).path
            if self.identity_get(path):return
            if path.startswith('/api/agent/v1'):
                self.agent_request(path)
                return
            tutorial={'/tutorial/':('index.html','text/html; charset=utf-8'),'/tutorial':('index.html','text/html; charset=utf-8'),'/tutorial/tutorial.css':('tutorial.css','text/css'),'/tutorial/assets/motherboard-redacted.png':('assets/motherboard-redacted.png','image/png'),'/tutorial/assets/uart0-debug-redacted.png':('assets/uart0-debug-redacted.png','image/png'),'/tutorial/assets/uart-pinout.svg':('assets/uart-pinout.svg','image/svg+xml')}
            if path in tutorial:
                filename,kind=tutorial[path];source=WEB.parent/'docs'/'tutorial'/filename
                if not source.is_file():self.send(404,{'error':'Tutorial asset is not installed'});return
                raw=source.read_bytes();self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; frame-ancestors 'self'");self.end_headers();
                if self.command!='HEAD':self.wfile.write(raw)
                return
            assets={'/radio-hub.js':('radio-hub.js','text/javascript'),'/radio-metadata.js':('radio-metadata.js','text/javascript'),'/podcasts.js':('podcasts.js','text/javascript'),'/library-sources.js':('library-sources.js','text/javascript'),'/photos-map.js':('photos-map.js','text/javascript'),'/folder-picker.js':('folder-picker.js','text/javascript'),'/ts431xeu-front.svg':('ts431xeu-front.svg','image/svg+xml'),'/':('index.html','text/html; charset=utf-8'),'/style.css':('style.css','text/css'),'/app.js':('app.js','text/javascript'),'/accounts.js':('accounts.js','text/javascript'),'/metadata-editor.js':('metadata-editor.js','text/javascript'),'/social-share.js':('social-share.js','text/javascript'),'/photos.js':('photos.js','text/javascript'),'/photo-land.json':('photo-land.json','application/json'),'/navigation.js':('navigation.js','text/javascript'),'/myradio.js':('myradio.js','text/javascript'),'/array-recovery.js':('array-recovery.js','text/javascript'),'/agents.js':('agents.js','text/javascript'),'/file-desktop.js':('file-desktop.js','text/javascript'),'/file-actions.js':('file-actions.js','text/javascript'),'/file-locations.js':('file-locations.js','text/javascript'),'/health.js':('health.js','text/javascript'),'/notifications.js':('notifications.js','text/javascript'),'/ddns.js':('ddns.js','text/javascript'),'/sw.js':('sw.js','text/javascript'),'/manifest.webmanifest':('manifest.webmanifest','application/manifest+json'),'/icon.svg':('icon.svg','image/svg+xml'),'/icon-192.png':('icon-192.png','image/png'),'/icon-512.png':('icon-512.png','image/png')}
            if path in assets:
                name,kind=assets[path];raw=(WEB/name).read_bytes();self.send_response(200)
                self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)))
                self.send_header('Cache-Control','public, max-age=604800' if path=='/photo-land.json' else 'no-store');self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; worker-src 'self'; img-src 'self' data: blob: https://tile.openstreetmap.org; frame-src 'self' https://www.openstreetmap.org; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
                if path=='/sw.js':self.send_header('Service-Worker-Allowed','/')
                self.end_headers()
                if self.command!='HEAD':self.wfile.write(raw)
                return
            if preview and path.startswith('/demo-media/'):
                names={'/demo-media/video.mp4':('video.mp4','video/mp4'),'/demo-media/audio.wav':('audio.wav','audio/wav'),'/demo-media/picture.png':('picture.png','image/png')}
                if path not in names:self.send(404,{'error':'Unknown sample'});return
                name,kind=names[path];data=(WEB/'demo-media'/name).read_bytes()
                class Sample:
                    def request(self,action,payload):
                        import base64
                        offset=payload['offset'];count=payload['count'];return {'total_bytes':len(data),'etag':hashlib.sha256(data).hexdigest(),'data_base64':base64.b64encode(data[offset:offset+count]).decode()}
                self.download(Sample(),{'share':['synthetic'],'path':[name],'inline':['1']});return
            if path == '/api/session':
                s = self.authenticated()
                self.send(200, {'authenticated': bool(s), 'csrf': s['csrf'] if s else None, 'setup_required': not bool(state.setting('administrator')), 'demo': preview,'user':s['user'] if s else None,'cloud_login':bool(identity.config().get('enabled')),'landing_page':accounts.landing(state,s['user'])['href'] if s else '/#overview'})
                return
            if not preview and (not self.authenticated()):
                self.send(401, {'error': 'Administrator login required'})
                return
            session=self.authenticated() if not preview else None
            if not preview:
                user=session['user']
                if path in ('/api/activity','/api/users/usage'):
                    if user['must_change']:self.send(403,{'error':'Change your temporary password first'});return
                    if path=='/api/users/usage' and user['role']!='administrator':self.send(403,{'error':'Administrator access required'});return
                    try:
                        if path=='/api/activity':
                            q={k:v[0] for k,v in parse_qs(urlsplit(self.path).query).items()};result=activity.listing(state,user,q);result['security']=activity.security_events(state,user);result['system']=self.gateway().request('activity.system',{})
                            from .access_scope import Broker
                            result['jobs']=Broker(nas,'user:'+user['id']).request('activity.jobs',{'administrator':user['role']=='administrator'});result['logging_warning']=getattr(self.server,'audit_error',None)
                        else:
                            roster=accounts.listing(state)['users'];result=self.gateway().request('users.usage',{'users':[{'id':v['id'],'primary_admin':bool(v['primary_admin'])} for v in roster],'refresh':parse_qs(urlsplit(self.path).query).get('refresh')==['1']})
                        self.send(200,result)
                    except (ValueError,OSError,KeyError,TypeError,sqlite3.Error):self.send(400,{'error':'Report unavailable. Check the request and NAS service health.'})
                    return
                if path=='/api/account':
                    with state.connect() as db:links=[dict(v) for v in db.execute('SELECT issuer,subject FROM external_identities WHERE user_id=?',(user['id'],))]
                    self.send(200,{'user':user,'identities':links,'cloud_enabled':bool(identity.config().get('enabled')),'authentication':session['source'],'recent_oidc':session.get('recent_oidc',False),'landing':accounts.landing(state,user),'photo_maps':accounts.photo_maps(state,user)});return
                if user['must_change']:self.send(403,{'error':'Change your temporary password first'});return
                if path=='/api/library-shares':self.send(200,library_shares.listing(state,user));return
                if path in ('/api/users','/api/identity'):
                    if user['role']!='administrator':self.send(403,{'error':'Administrator access required'});return
                    if path=='/api/users':
                        result=accounts.listing(state);options=nas.request('personal.options',{});result['storage_options']=options['shares'];self.send(200,result)
                    else:self.send(200,identity.status())
                    return
                member_allowed={'/api/nas/status','/api/status','/api/backups','/api/jobs','/api/radio-file','/api/radio-stream','/api/photo-file','/api/file','/api/radio-station-art','/api/podcast-art','/api/library-card-art','/api/album-art','/api/metadata-match-art','/api/zip','/api/pool-file','/api/foreign-file','/api/volume-file'}
                if user['role']!='administrator' and path not in member_allowed:self.send(403,{'error':'Administrator access required'});return
            if path == '/api/agents/players':
                self.send(200,players.listing());return
            if path == '/api/agents/catalog':
                self.send(200, agents.catalog());return
            if path == '/api/agents':
                self.send(200, agents.listing());return
            if path == '/api/nas/status':
                try:self.send(200, demo.nas() if preview else self.gateway().status())
                except (ValueError, OSError) as error:self.send(503, {'error': str(error), 'available': False})
                return
            if path == '/api/zip':
                if preview:self.send(403,{'error':'Synthetic preview cannot download NAS files'});return
                query=parse_qs(urlsplit(self.path).query)
                try:
                    from .zipstream import write_zip
                    from urllib.parse import quote
                    info=self.gateway().request('files.bundle-info',{'ticket':query['ticket'][0]})
                    self.send_response(200);self.send_header('Content-Type','application/zip');self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(info['filename']));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cross-Origin-Resource-Policy','same-origin');self.send_header('Connection','close');self.end_headers();self.download_started=True;self.close_connection=True
                    if self.command!='HEAD':write_zip(self.wfile,self.gateway().request,info)
                except (ValueError,OSError,KeyError,PermissionError) as error:
                    if getattr(self,'download_started',False):self.close_connection=True
                    else:self.send(403 if isinstance(error,PermissionError) else 400,{'error':str(error)})
                return
            if path in ('/api/artifact','/api/system-backup'):
                if preview:self.send(403,{'error':'Preview cannot read private artifacts'});return
                try:self.download(self.gateway(),parse_qs(urlsplit(self.path).query),artifact=path=='/api/artifact',system_backup=path=='/api/system-backup')
                except (ValueError,OSError,KeyError,PermissionError) as error:
                    if getattr(self,'download_started',False):self.close_connection=True
                    else:self.send(403 if isinstance(error,PermissionError) else 400,{'error':str(error)})
                return
            if path in ('/api/podcast-art','/api/library-card-art','/api/album-art','/api/metadata-match-art'):
                if preview:self.send(403,{'error':'Podcast artwork is unavailable in preview'});return
                try:
                    from .podcast_browser import Browser
                    from . import media_cache
                    query=parse_qs(urlsplit(self.path).query)
                    if path=='/api/album-art':
                        from .radio_catalog import album_art
                        raw,mime=album_art(self.gateway(),query.get('id',[''])[0])
                    elif path=='/api/metadata-match-art':
                        from .radio_providers import cover
                        raw,mime=cover(self.gateway(),query.get('ticket',[''])[0])
                    elif path=='/api/library-card-art':
                        from .library_cards import artwork
                        raw,mime=artwork(self.gateway(),query.get('kind',[''])[0],query.get('id',[''])[0])
                    else:raw,mime=Browser(self.gateway()).artwork(query.get('id',[''])[0])
                    etag=media_cache.tag(hashlib.sha256(raw).hexdigest(),session['user']['id'],parse_qs(urlsplit(self.path).query).get('shared',[''])[0])
                    unchanged=media_cache.matches(self.headers.get('If-None-Match'),etag)
                    self.send_response(304 if unchanged else 200);self.send_header('Cache-Control',media_cache.POLICY);self.send_header('ETag',etag);self.send_header('Vary','Cookie');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cross-Origin-Resource-Policy','same-origin');self.send_header('Content-Security-Policy',"default-src 'none'; sandbox")
                    if not unchanged:self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)))
                    self.end_headers()
                    if not unchanged and self.command!='HEAD':self.wfile.write(raw)
                except (ValueError,OSError,KeyError,PermissionError,StopIteration):self.send(404,{'error':'Podcast artwork unavailable'})
                return
            if path == '/api/radio-station-art':
                if preview:self.send(403,{'error':'Station artwork is unavailable in preview'});return
                try:
                    import base64
                    value=self.gateway().request('myradio.station-artwork',{'id':parse_qs(urlsplit(self.path).query).get('id',[''])[0]});raw=base64.b64decode(value['data_base64'],validate=True)
                    if value['mime'] not in ('image/jpeg','image/svg+xml') or len(raw)>256*1024:raise ValueError('Invalid station artwork')
                    from . import media_cache
                    etag=media_cache.tag(hashlib.sha256(raw).hexdigest(),session['user']['id'])
                    if media_cache.matches(self.headers.get('If-None-Match'),etag):
                        self.send_response(304);self.send_header('Cache-Control',media_cache.POLICY);self.send_header('ETag',etag);self.send_header('Vary','Cookie');self.end_headers();return
                    self.send_response(200);self.send_header('Content-Type',value['mime']);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control',media_cache.POLICY);self.send_header('ETag',etag);self.send_header('Vary','Cookie');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cross-Origin-Resource-Policy','same-origin');self.send_header('Content-Security-Policy',"default-src 'none'; sandbox");self.end_headers()
                    if self.command!='HEAD':self.wfile.write(raw)
                except (ValueError,OSError,KeyError,PermissionError):self.send(404,{'error':'Station artwork unavailable'})
                return
            if path == '/api/radio-stream':
                if preview:self.send(403,{'error':'Live radio is unavailable in preview'});return
                if not radio_slots.acquire(blocking=False):self.send(503,{'error':'Four radio streams are already active'});return
                try:
                    from .nas.public_http import open_url
                    query=parse_qs(urlsplit(self.path).query);station=self.gateway().request('myradio.station-source',{'id':query['id'][0]})
                    with open_url(station['url'],timeout=15) as (response,_):
                        kind=(response.getheader('Content-Type') or '').split(';')[0].lower()
                        if not (kind.startswith('audio/') or kind in ('application/ogg','application/octet-stream')):raise ValueError('Station did not return direct audio')
                        self.download_started=True;self.close_connection=True;self.send_response(200)
                        self.send_header('Content-Type',kind if kind!='application/octet-stream' else 'audio/mpeg');self.send_header('Cache-Control','no-store');self.send_header('Connection','close');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cross-Origin-Resource-Policy','same-origin');self.end_headers()
                        if self.command!='HEAD':
                            until=time.monotonic()+6*3600
                            while time.monotonic()<until:
                                raw=response.read(32768)
                                if not raw:break
                                self.wfile.write(raw)
                except (ValueError,OSError,KeyError,PermissionError) as error:
                    if getattr(self,'download_started',False):self.close_connection=True
                    else:self.send(403 if isinstance(error,PermissionError) else 400,{'error':str(error)})
                finally:radio_slots.release()
                return
            if path == '/api/radio-file':
                if preview:self.send(403,{'error':'Private library media is unavailable in preview'});return
                try:self.download(self.gateway(),parse_qs(urlsplit(self.path).query),radio_file=True)
                except (ValueError,OSError,KeyError,PermissionError) as error:
                    if getattr(self,'download_started',False):self.close_connection=True
                    else:self.send(403 if isinstance(error,PermissionError) else 400,{'error':str(error)})
                return
            if path == '/api/raid-backup':
                if preview:self.send(403,{'error':'Recovery backup unavailable in preview'});return
                try:self.download(self.gateway(),parse_qs(urlsplit(self.path).query),raid_backup=True)
                except (ValueError,OSError,KeyError,PermissionError) as error:
                    if getattr(self,'download_started',False):self.close_connection=True
                    else:self.send(403 if isinstance(error,PermissionError) else 400,{'error':str(error)})
                return
            if path in ('/api/file','/api/download-file','/api/volume-file','/api/foreign-file','/api/pool-file','/api/photo-file'):
                if preview:self.send(403, {'error':'Synthetic preview cannot read files'});return
                try:self.download(self.gateway(), parse_qs(urlsplit(self.path).query),download_job=path=='/api/download-file',volume_file=path=='/api/volume-file',foreign_file=path=='/api/foreign-file',pool_file=path=='/api/pool-file',photo_file=path=='/api/photo-file')
                except (ValueError, OSError, KeyError,PermissionError) as error:
                    if getattr(self,'download_started',False):self.close_connection=True
                    else:self.send(403 if isinstance(error,PermissionError) else 400, {'error': str(error)})
                return
            if path == '/api/status':
                try:
                    value = demo.inventory() if preview else family_system.read() if session['user']['role']!='administrator' else inventory.snapshot(snapshot)
                    self.send(200, {'inventory': value, 'demo': preview, 'capabilities': {'storage_status': True, 'pool_planning': True, 'pool_execution': False, 'configuration_backup': not preview, 'data_backup': False, 'restore_preview': True, 'restore_execution': False, 'smb_nfs_commissioned': False}})
                except (OSError, ValueError, RuntimeError) as error:
                    self.send(503, {'error': str(error), 'stale': True})
            elif path == '/api/backups':
                self.send(200, {'backups': [] if preview or session['user']['role']!='administrator' else backups.list_backups(destination), 'scope': 'FreeQNAP configuration and consistent SQLite snapshots; no shared files, OS or flash'})
            elif path == '/api/jobs':
                self.send(200, {'jobs': [] if preview else self.gateway().jobs().get('jobs',[]) if session['user']['role']!='administrator' else state.jobs(), 'worker': getattr(self.server, 'worker_health', {'mode': 'read-only preview'})})
            else:
                self.send(404, {'error': 'Unknown endpoint'})

        def download(self, nas, query, artifact=False, download_job=False, volume_file=False,foreign_file=False,system_backup=False,pool_file=False,photo_file=False,raid_backup=False,radio_file=False):
            import base64
            if radio_file:
                payload={'id':query['id'][0],'variant':query.get('variant',['original'])[0]};read_action='myradio.read';path='original.bin'
            elif raid_backup:
                payload={'id':query['id'][0]};read_action='raid.backup-read';path='raid-metadata.tar'
            elif photo_file:
                payload={'id':query['id'][0],'variant':query.get('variant',['original'])[0]};read_action='photos.read';path='photo.jpg'
            elif system_backup:
                payload={'id':query['id'][0]};read_action='backup.local-read';path='freeqnap-recovery.tar.gz.gpg'
            elif artifact:
                payload={'id':query['id'][0]};read_action='artifacts.read';path='luks-header.bin'
            elif foreign_file:
                payload={'session':query['session'][0],'path':query['path'][0]};read_action='external.session-read';path=payload['path']
            elif pool_file:
                payload={'pool':query['pool'][0],'path':query['path'][0]};read_action='files.pool-read';path=payload['path']
            elif volume_file:
                payload={'pool':query['pool'][0],'path':query['path'][0]};read_action='external.read';path=payload['path']
            elif download_job:
                payload={'id':query['id'][0],'path':query['path'][0]};read_action='downloads.read';path=payload['path']
            else:
                payload={'share':query['share'][0],'path':query['path'][0]};read_action='files.read';path=payload['path']
            first=nas.request(read_action,{**payload,'offset':0,'count':1})
            if artifact or system_backup or photo_file or raid_backup or radio_file:path=first['filename']
            total=first['total_bytes'];etag='"'+hashlib.sha256(first['etag'].encode()).hexdigest()+'"'
            from . import media_cache
            cacheable=media_cache.preview_resource(photo_file,radio_file,payload.get('variant'),path,query.get('inline')==['1'] and query.get('download')!=['1'])
            if cacheable:
                etag=media_cache.tag(first['etag'],self.authenticated()['user']['id'],query.get('shared',[''])[0])
                if media_cache.matches(self.headers.get('If-None-Match'),etag):
                    self.download_started=True;self.send_response(304);self.send_header('Cache-Control',media_cache.POLICY);self.send_header('ETag',etag);self.send_header('Vary','Cookie');self.end_headers();return
            try:start,end,partial=byte_range(self.headers.get('Range'),total,etag,self.headers.get('If-Range'))
            except ValueError:
                self.download_started=True;self.send_response(416);self.send_header('Content-Range','bytes */'+str(total));self.send_header('Content-Length','0');self.end_headers();return
            self.download_started=True;self.send_response(206 if partial else 200)
            self.send_header('Content-Type',content_type(path));self.send_header('Content-Length',str(max(0,end-start+1)))
            from urllib.parse import quote
            disposition='inline' if query.get('inline')==['1'] and query.get('download')!=['1'] and media_kind(path) else 'attachment'
            self.send_header('Content-Disposition',disposition+"; filename*=UTF-8''"+quote(Path(path).name))
            self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control',media_cache.POLICY if cacheable else 'no-store');self.send_header('ETag',etag)
            if cacheable:self.send_header('Vary','Cookie')
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cross-Origin-Resource-Policy','same-origin')
            if first.get('modified_at'):
                from email.utils import formatdate
                self.send_header('Last-Modified',formatdate(first['modified_at'],usegmt=True))
            if partial:self.send_header('Content-Range',f'bytes {start}-{end}/{total}')
            self.end_headers();offset=start
            if self.command=='HEAD':return
            while offset<=end:
                value=nas.request(read_action,{**payload,'offset':offset,'count':min(512*1024,end-offset+1)})
                if value['etag']!=first['etag']:raise ConnectionAbortedError('File changed during download')
                chunk=base64.b64decode(value['data_base64'],validate=True)
                if not chunk:raise ConnectionAbortedError('Short file read')
                self.wfile.write(chunk);offset+=len(chunk)

        def agent_request(self, path):
            if preview or not self.safe_host():self.send(403, {'error':'Agent access unavailable'});return
            # The TLS proxy overwrites this header; only loopback proxy peers count.
            if self.client_address[0] not in ('127.0.0.1','::1') or self.headers.get('X-Forwarded-Proto')!='https':
                self.send(403, {'error':'Use the trusted HTTPS endpoint for agent credentials'});return
            if self.headers.get('Origin') is not None:
                self.send(403, {'error':'Agent API does not accept browser-origin requests'});return
            try:
                principal=agents.authenticate(self.headers.get('Authorization'));self.audit_actor='agent:'+principal['id']
                if self.command in ('GET','HEAD') and path=='/api/agent/v1':
                    catalog=agents.catalog()
                    catalog['operations']=[row for row in catalog['operations'] if row['id'] in principal['grants']]
                    catalog['presets']={};catalog['principal_id']=principal['id']
                    self.send(200,catalog);return
                prefix='/api/agent/v1/operations/'
                if self.command!='POST' or not path.startswith(prefix):self.send(404,{'error':'Unknown agent endpoint'});return
                if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('Content-Length JSON required')
                size=int(self.headers.get('Content-Length','0'))
                operation=path[len(prefix):]
                limit=2*1024**2 if operation in ('myradio.artwork','myradio.card-save','myradio.album-save') else 2*1024**2 if operation=='media.artwork' else 1024**2 if operation in ('myradio.upload-chunk','files.upload-chunk','downloads.add','vpn.plan') else 32768
                if not 0<size<=limit:raise ValueError('Request size invalid')
                payload=json.loads(self.rfile.read(size))
                class Gateway:
                    def request(self,action,value):
                        if action in PLAYER_OPERATIONS:return players.invoke(action,value,principal)
                        from .access_scope import Broker
                        return Broker(nas,'agent:'+principal['id']).request(action,value)
                self.send(200,agents.invoke(principal,operation,payload,Gateway()))
            except Denied as error:self.send(403,{'error':str(error)})
            except Limited as error:self.send(429,{'error':str(error)})
            except (ValueError,KeyError,TypeError,OSError):self.send(400,{'error':'Operation failed; check its request and the NAS activity. No automatic retry was performed.'})

        def do_HEAD(self):self.do_GET()

        def do_POST(self):
            if urlsplit(self.path).path.startswith('/api/agent/v1'):
                self.agent_request(urlsplit(self.path).path);return
            if preview:
                self.send(403, {'error': 'Preview is read-only and uses synthetic data'})
                return
            if not self.safe_host() or not self.safe_origin() or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                self.send(403, {'error': 'Same-origin JSON required'})
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                limit = 256*1024 if urlsplit(self.path).path in ('/api/nas/files.metadata-plan','/api/nas/photos.metadata-plan') else 128*1024 if urlsplit(self.path).path=='/api/library-shares/change' else 2*1024**2 if urlsplit(self.path).path in ('/api/nas/myradio.artwork','/api/nas/myradio.card-save','/api/nas/myradio.album-save') else 2*1024**2 if urlsplit(self.path).path == '/api/nas/media.artwork' else 1024**2 if urlsplit(self.path).path in ('/api/nas/myradio.upload-chunk','/api/nas/files.upload-chunk','/api/nas/downloads.add','/api/nas/vpn.plan') else 32768
                if not 0 < size <= limit:
                    raise ValueError('Request size invalid')
                value = json.loads(self.rfile.read(size))
                path = urlsplit(self.path).path
                if path in ('/api/nas/photos.icloud-login','/api/nas/photos.icloud-code') and not (self.client_address[0] in ('127.0.0.1','::1') and self.headers.get('X-Forwarded-Proto')=='https'):
                    self.send(403,{'error':'Use trusted local HTTPS for Apple sign-in'});return
                if not isinstance(value, dict):
                    raise ValueError('JSON object required')
                if path == '/api/enroll':
                    self.send(200, auth.enroll(state, value.get('token'), value.get('password')))
                    return
                if path == '/api/login':
                    with self.server.auth_lock:
                        now = time.monotonic()
                        self.server.login_attempts = [t for t in self.server.login_attempts if now - t < 60]
                        if len(self.server.login_attempts) >= 10:
                            self.send(429, {'error': 'Wait before trying again'})
                            return
                        self.server.login_attempts.append(now)
                    s = auth.login(state, value.get('password'),value.get('username','admin'))
                    if not s:
                        self.send(401, {'error': 'Login failed'})
                        return
                    token, csrf = s
                    self.send(200, {'authenticated': True, 'csrf': csrf,'landing_page':accounts.landing(state,auth.session(state,token)['user'])['href']}, 'freeqnap_session=' + token + '; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200' + ('; Secure' if self.headers.get('Origin','').startswith('https://') else ''))
                    return
                s = self.authenticated()
                if not s or not secrets.compare_digest(self.headers.get('X-CSRF-Token', ''), s['csrf']):
                    self.send(403, {'error': 'Authenticated session and CSRF token required'})
                    return
                user=s['user']
                if path.startswith('/api/social/'):
                    self.send(200,PersonalGateway(nas,state,self.authenticated,value.get('shared')).social(path.removeprefix('/api/social/'),value));return
                if path=='/api/account/preferences':self.send(200,accounts.save_preferences(state,user,value));return
                if path=='/api/account/local-password':
                    result,token=accounts.configure_local_password(state,s,value);self.send(200,result,self.session_cookie(token));return
                if path=='/api/identity/assign':self.send(200,identity.assign(user,value));return
                if path=='/api/account/password':self.send(200,accounts.change_password(state,user,value));return
                if user['must_change'] and path!='/api/logout':self.send(403,{'error':'Change your temporary password first'});return
                if path=='/api/library-shares/change':
                    if value.get('action')=='share' and value.get('kind')=='photos':
                        scope=value.get('scope',{'mode':'library'})
                        if isinstance(scope,dict) and scope.get('mode')=='items':
                            for ident in scope.get('ids',[]):
                                result=PersonalGateway(nas,state,self.authenticated).request('photos.catalog',{'id':ident,'limit':1})
                                if not any(v['id']==ident for v in result['items']):raise ValueError('Select items from your own library')
                        elif isinstance(scope,dict) and scope.get('mode')=='albums':
                            albums=PersonalGateway(nas,state,self.authenticated).request('photos.catalog',{'limit':1})['albums']
                            if any(ident not in {v['id'] for v in albums} for ident in scope.get('ids',[])):raise ValueError('Select albums from your own library')
                    self.send(200,library_shares.change(state,user,value));return
                if path=='/api/identity/link':
                    with state.connect() as db:row=db.execute('SELECT * FROM local_accounts WHERE id=?',(user['id'],)).fetchone()
                    if not row or not accounts.verify(row,value.get('current_password')):raise ValueError('Confirm your local password')
                    url,binding=identity.begin(user);self.send(200,{'url':url},'freeqnap_oidc='+binding+'; HttpOnly; SameSite=Lax; Secure; Path=/auth/oidc/; Max-Age=300');return
                if path=='/api/identity/unlink':self.send(200,identity.unlink(user,value));return
                if path=='/api/users/storage':
                    if user['role']!='administrator':raise PermissionError('Administrator access required')
                    target=value.get('id');rows=value.get('assignments')
                    if not isinstance(rows,list) or len(rows)>32:raise ValueError('Choose up to 32 shared folders')
                    options=nas.request('personal.options',{});valid={v['name']:v for v in options['shares']};pinned=[]
                    for row in rows:
                        if not isinstance(row,dict) or set(row)!={'share','access'} or row['access'] not in ('read','write') or row['share'] not in valid:raise ValueError('Choose valid shared folders and read/write access')
                        if row['share'] in ('my-radio','my-photos','my-files'):raise ValueError('This shared-folder name is reserved for personal storage')
                        source=valid[row['share']];pinned.append({**row,'pool':source['pool'],'path':source['path'],'filesystem_uuid':options['pools'][source['pool']]['filesystem_uuid']})
                    if len({v['share'] for v in pinned})!=len(pinned):raise ValueError('Choose each shared folder once')
                    self.send(200,accounts.set_storage(state,user,target,pinned));return
                if path in ('/api/users/change','/api/identity/save'):
                    if user['role']!='administrator':self.send(403,{'error':'Administrator access required'});return
                    result=accounts.change(state,user,value) if path=='/api/users/change' else identity.save(user,value)
                    if path=='/api/users/change':
                        with state.connect() as db:target=db.execute('SELECT * FROM local_accounts WHERE id=?',(result['id'],)).fetchone()
                        if not target['primary_admin']:
                            try:nas.request('personal.control',{'owner':target['id'],'label':target['label'],'enabled':bool(target['enabled']),'permissions':accounts.DEFAULT if target['role']=='administrator' else json.loads(target['permissions']),'assignments':accounts.assignments(state,target['id'])})
                            except (ValueError,OSError):result['warning']='Account access changed, but background library control could not be verified. Check Activity.'
                    self.send(200,result);return
                if path.startswith('/api/nas/'):
                    operation=path.removeprefix('/api/nas/')
                    if operation.startswith(('personal.','access.')) or operation=='photos.share-view':self.send(403,{'error':'Internal operation unavailable'});return
                    if operation=='myradio.listen' and value.get('event')=='tick':self.audit_suppress=True
                    from .storage_status import guard
                    guard(operation)
                    self.send(200,self.gateway().request(operation,value));return
                if user['role']!='administrator' and path!='/api/logout':self.send(403,{'error':'Administrator access required'});return
                if path == '/api/agents/players/configure':
                    self.send(200,players.configure(value));return
                if path == '/api/agents/players/discover':
                    self.send(200,players.discover(value));return
                if path == '/api/agents/players/approve':
                    self.send(200,players.approve(value));return
                if path == '/api/agents/create':
                    self.send(200,agents.issue(value));return
                if path == '/api/agents/revoke':
                    self.send(200,agents.revoke(value));return
                if path.startswith('/api/nas/'):
                    self.send(200, nas.request(path.removeprefix('/api/nas/'), value))
                    return
                if path == '/api/logout':
                    cookie = SimpleCookie(self.headers.get('Cookie', ''))
                    token = cookie['freeqnap_session'].value
                    with state.connect() as database:database.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))
                    self.send(200, {'signed_out':True}, 'freeqnap_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
                    return
                if path == '/api/backups/create':
                    ident = state.enqueue('config-backup', {'keep': int(value.get('keep', 7))})
                elif path == '/api/backups/verify':
                    ident = state.enqueue('verify-backup', {'name': value['name']})
                elif path == '/api/jobs/retry':
                    state.retry(value['id'])
                    self.send(200, {'queued': True})
                    return
                else:
                    self.send(404, {'error': 'Unknown or unavailable operation'})
                    return
                self.send(202, {'job_id': ident})
            except PermissionError as error:
                self.send(403,{'error':str(error)})
            except (ValueError, KeyError, TypeError, OSError) as error:
                self.send(403 if isinstance(error,PermissionError) else 400, {'error': str(error)})
    return Handler

class NASHTTPServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,*args,**kwargs):
        self.capacity=threading.BoundedSemaphore(16)
        super().__init__(*args,**kwargs)
    def process_request(self,request,address):
        if not self.capacity.acquire(blocking=False):
            try:request.sendall(b'HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            finally:request.close()
            return
        request.settimeout(30)
        try:super().process_request(request,address)
        except Exception:self.capacity.release();raise
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.capacity.release()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state', type=Path, default=Path('/var/lib/freeqnap'))
    p.add_argument('--backups', type=Path, default=Path('/var/backups/freeqnap'))
    p.add_argument('--snapshot', type=Path)
    p.add_argument('--port', type=int, default=8080)
    p.add_argument('--demo', action='store_true')
    p.add_argument('--origin', action='append', default=[])
    p.add_argument('--broker', type=Path, default=Path('/run/freeqnap/broker.sock'))
    a = p.parse_args()
    if a.demo and a.snapshot:
        p.error('Synthetic preview cannot read a device snapshot')
    a.state.mkdir(mode=0o700, parents=True, exist_ok=True)
    import fcntl
    lock = (a.state / '.server.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = State(a.state)
    health = {'ok': True, 'last_checked': None, 'error': None}
    if not a.demo:
        state.reconcile_interrupted()
        worker = Worker(state, a.backups)

        def work():
            while True:
                try:
                    worker.schedule()
                    worker.one()
                    health.update(ok=True, last_checked=time.time(), error=None)
                except Exception as error:
                    health.update(ok=False, last_checked=time.time(), error=str(error))
                time.sleep(0.5)
        threading.Thread(target=work, daemon=True).start()
        def source_work():
            from .library_sources import tick_all
            source_nas=__import__('freeqnap.nas.broker',fromlist=['Client']).Client(a.broker,timeout=15)
            while True:
                try:
                    tick_all(state,source_nas);health.update(source_scanner_ok=True)
                except Exception:health.update(source_scanner_ok=False,source_scanner_error='Folder scanner coordinator needs attention')
                time.sleep(3)
        threading.Thread(target=source_work,daemon=True).start()
    with NASHTTPServer(('127.0.0.1', a.port), handler(state, a.backups, a.snapshot, a.demo, __import__('freeqnap.nas.broker',fromlist=['Client']).Client(a.broker), a.origin)) as server:
        server.worker_health = health
        server.login_attempts = []
        server.auth_lock = threading.Lock()
        print('FreeQNAP ' + ('synthetic read-only preview' if a.demo else 'local console') + ' at http://127.0.0.1:' + str(a.port), flush=True)
        server.serve_forever()
if __name__ == '__main__':
    main()
