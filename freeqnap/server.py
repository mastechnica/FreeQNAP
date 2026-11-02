"""Loopback NAS console. Access remotely through authenticated SSH forwarding."""
import argparse, hashlib, json, os, secrets, threading, time
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, unquote
from . import auth, backups, demo, inventory
from .state import State
from .agents import Agents, Denied, Limited, PLAYER_OPERATIONS
from .players import Players
from .media_http import byte_range,content_type,kind as media_kind
from .jobs import Worker
WEB = Path(__file__).resolve().parents[1] / 'web'

def handler(state, destination, snapshot=None, preview=False, broker=None, origins=()):
    from .nas.broker import Client
    nas = broker or Client()
    agents = Agents(state)
    players = Players(state,nas,agents)
    if not preview:players.resume()

    class Handler(BaseHTTPRequestHandler):

        def log_message(self, *args):
            pass

        def send(self, code, value, cookie=None):
            raw = json.dumps(value).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
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
            return auth.session(state, token)

        def do_GET(self):
            if not self.safe_host():
                self.send(403, {'error': 'Unrecognized host'})
                return
            path = urlsplit(self.path).path
            if path.startswith('/api/agent/v1'):
                self.agent_request(path)
                return
            tutorial={'/tutorial/':('index.html','text/html; charset=utf-8'),'/tutorial':('index.html','text/html; charset=utf-8'),'/tutorial/tutorial.css':('tutorial.css','text/css'),'/tutorial/assets/motherboard-redacted.png':('assets/motherboard-redacted.png','image/png'),'/tutorial/assets/uart0-debug-redacted.png':('assets/uart0-debug-redacted.png','image/png'),'/tutorial/assets/uart-pinout.svg':('assets/uart-pinout.svg','image/svg+xml')}
            if path in tutorial:
                filename,kind=tutorial[path];source=WEB.parent/'docs'/'tutorial'/filename
                if not source.is_file():self.send(404,{'error':'Tutorial asset is not installed'});return
                raw=source.read_bytes();self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; frame-ancestors 'none'");self.end_headers();
                if self.command!='HEAD':self.wfile.write(raw)
                return
            assets={'/ts431xeu-front.svg':('ts431xeu-front.svg','image/svg+xml'),'/':('index.html','text/html; charset=utf-8'),'/style.css':('style.css','text/css'),'/app.js':('app.js','text/javascript'),'/agents.js':('agents.js','text/javascript'),'/file-desktop.js':('file-desktop.js','text/javascript'),'/file-locations.js':('file-locations.js','text/javascript'),'/health.js':('health.js','text/javascript'),'/notifications.js':('notifications.js','text/javascript'),'/ddns.js':('ddns.js','text/javascript'),'/sw.js':('sw.js','text/javascript'),'/manifest.webmanifest':('manifest.webmanifest','application/manifest+json'),'/icon.svg':('icon.svg','image/svg+xml'),'/icon-192.png':('icon-192.png','image/png'),'/icon-512.png':('icon-512.png','image/png')}
            if path in assets:
                name,kind=assets[path];raw=(WEB/name).read_bytes();self.send_response(200)
                self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)))
                self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
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
                self.send(200, {'authenticated': bool(s), 'csrf': s['csrf'] if s else None, 'setup_required': not bool(state.setting('administrator')), 'demo': preview})
                return
            if not preview and (not self.authenticated()):
                self.send(401, {'error': 'Administrator login required'})
                return
            if path == '/api/agents/players':
                self.send(200,players.listing());return
            if path == '/api/agents/catalog':
                self.send(200, agents.catalog());return
            if path == '/api/agents':
                self.send(200, agents.listing());return
            if path == '/api/nas/status':
                try:self.send(200, demo.nas() if preview else nas.request('nas.status'))
                except (ValueError, OSError) as error:self.send(503, {'error': str(error), 'available': False})
                return
            if path == '/api/zip':
                if preview:self.send(403,{'error':'Synthetic preview cannot download NAS files'});return
                query=parse_qs(urlsplit(self.path).query)
                try:
                    from .zipstream import write_zip
                    from urllib.parse import quote
                    info=nas.request('files.bundle-info',{'ticket':query['ticket'][0]})
                    self.send_response(200);self.send_header('Content-Type','application/zip');self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(info['filename']));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cross-Origin-Resource-Policy','same-origin');self.send_header('Connection','close');self.end_headers();self.download_started=True;self.close_connection=True
                    if self.command!='HEAD':write_zip(self.wfile,nas.request,info)
                except (ValueError,OSError,KeyError) as error:
                    if getattr(self,'download_started',False):self.close_connection=True
                    else:self.send(400,{'error':str(error)})
                return
            if path in ('/api/artifact','/api/system-backup'):
                if preview:self.send(403,{'error':'Preview cannot read private artifacts'});return
                try:self.download(nas,parse_qs(urlsplit(self.path).query),artifact=path=='/api/artifact',system_backup=path=='/api/system-backup')
                except (ValueError,OSError,KeyError) as error:
                    if getattr(self,'download_started',False):self.close_connection=True
                    else:self.send(400,{'error':str(error)})
                return
            if path in ('/api/file','/api/download-file','/api/volume-file','/api/foreign-file','/api/pool-file'):
                if preview:self.send(403, {'error':'Synthetic preview cannot read files'});return
                try:self.download(nas, parse_qs(urlsplit(self.path).query),download_job=path=='/api/download-file',volume_file=path=='/api/volume-file',foreign_file=path=='/api/foreign-file',pool_file=path=='/api/pool-file')
                except (ValueError, OSError, KeyError) as error:
                    if getattr(self,'download_started',False):self.close_connection=True
                    else:self.send(400, {'error': str(error)})
                return
            if path == '/api/status':
                try:
                    value = demo.inventory() if preview else inventory.snapshot(snapshot)
                    self.send(200, {'inventory': value, 'demo': preview, 'capabilities': {'storage_status': True, 'pool_planning': True, 'pool_execution': False, 'configuration_backup': not preview, 'data_backup': False, 'restore_preview': True, 'restore_execution': False, 'smb_nfs_commissioned': False}})
                except (OSError, ValueError, RuntimeError) as error:
                    self.send(503, {'error': str(error), 'stale': True})
            elif path == '/api/backups':
                self.send(200, {'backups': [] if preview else backups.list_backups(destination), 'scope': 'FreeQNAP configuration and consistent SQLite snapshots; no shared files, OS or flash'})
            elif path == '/api/jobs':
                self.send(200, {'jobs': [] if preview else state.jobs(), 'worker': getattr(self.server, 'worker_health', {'mode': 'read-only preview'})})
            else:
                self.send(404, {'error': 'Unknown endpoint'})

        def download(self, nas, query, artifact=False, download_job=False, volume_file=False,foreign_file=False,system_backup=False,pool_file=False):
            import base64
            if system_backup:
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
            if artifact or system_backup:path=first['filename']
            total=first['total_bytes'];etag='"'+hashlib.sha256(first['etag'].encode()).hexdigest()+'"'
            try:start,end,partial=byte_range(self.headers.get('Range'),total,etag,self.headers.get('If-Range'))
            except ValueError:
                self.download_started=True;self.send_response(416);self.send_header('Content-Range','bytes */'+str(total));self.send_header('Content-Length','0');self.end_headers();return
            self.download_started=True;self.send_response(206 if partial else 200)
            self.send_header('Content-Type',content_type(path));self.send_header('Content-Length',str(max(0,end-start+1)))
            from urllib.parse import quote
            disposition='inline' if query.get('inline')==['1'] and media_kind(path) else 'attachment'
            self.send_header('Content-Disposition',disposition+"; filename*=UTF-8''"+quote(Path(path).name))
            self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','no-store');self.send_header('ETag',etag)
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
                principal=agents.authenticate(self.headers.get('Authorization'))
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
                limit=2*1024**2 if operation=='media.artwork' else 1024**2 if operation in ('files.upload-chunk','downloads.add','vpn.plan') else 32768
                if not 0<size<=limit:raise ValueError('Request size invalid')
                payload=json.loads(self.rfile.read(size))
                class Gateway:
                    def request(self,action,value):
                        if action in PLAYER_OPERATIONS:return players.invoke(action,value,principal)
                        return nas.request(action,value)
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
                limit = 2*1024**2 if urlsplit(self.path).path == '/api/nas/media.artwork' else 1024**2 if urlsplit(self.path).path in ('/api/nas/files.upload-chunk','/api/nas/downloads.add','/api/nas/vpn.plan') else 32768
                if not 0 < size <= limit:
                    raise ValueError('Request size invalid')
                value = json.loads(self.rfile.read(size))
                path = urlsplit(self.path).path
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
                    s = auth.login(state, value.get('password'))
                    if not s:
                        self.send(401, {'error': 'Login failed'})
                        return
                    token, csrf = s
                    self.send(200, {'authenticated': True, 'csrf': csrf}, 'freeqnap_session=' + token + '; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200' + ('; Secure' if self.headers.get('Origin','').startswith('https://') else ''))
                    return
                s = self.authenticated()
                if not s or not secrets.compare_digest(self.headers.get('X-CSRF-Token', ''), s['csrf']):
                    self.send(403, {'error': 'Authenticated session and CSRF token required'})
                    return
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
            except (ValueError, KeyError, TypeError, OSError) as error:
                self.send(400, {'error': str(error)})
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
    with NASHTTPServer(('127.0.0.1', a.port), handler(state, a.backups, a.snapshot, a.demo, __import__('freeqnap.nas.broker',fromlist=['Client']).Client(a.broker), a.origin)) as server:
        server.worker_health = health
        server.login_attempts = []
        server.auth_lock = threading.Lock()
        print('FreeQNAP ' + ('synthetic read-only preview' if a.demo else 'local console') + ' at http://127.0.0.1:' + str(a.port), flush=True)
        server.serve_forever()
if __name__ == '__main__':
    main()
