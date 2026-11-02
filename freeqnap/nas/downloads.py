"""Private, resumable HTTP(S)/BitTorrent queue through unprivileged aria2.

A job is durable before submission. Deterministic GIDs reconcile ambiguous RPC
responses and restarts. Removing a job never deletes its downloaded files.
"""
import base64
import contextlib
import stat
import hashlib
import json
import os
import pwd
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from .common import name
from ..state import atomic

UID_NAME='freeqnap-downloads'
SERVICE='freeqnap-downloads.service'
LIMIT=512

def url(value):
    if not isinstance(value,str) or not 1<=len(value)<=8192 or any(ord(c)<33 or ord(c)==127 for c in value):raise ValueError('Enter a URL without whitespace/control characters')
    parts=urllib.parse.urlsplit(value)
    if parts.scheme in ('http','https'):
        if not parts.hostname or parts.username or parts.password or parts.fragment:raise ValueError('Use an HTTP(S) URL without embedded login or fragment')
        try:parts.port
        except ValueError:raise ValueError('Invalid URL port') from None
        return value,'url'
    if parts.scheme=='magnet':
        query=urllib.parse.parse_qs(parts.query)
        if not any(re.fullmatch(r'urn:btih:([a-fA-F0-9]{40}|[a-zA-Z2-7]{32})',v) for v in query.get('xt',[])):raise ValueError('A BitTorrent v1/hybrid info hash is required')
        return value,'torrent'
    raise ValueError('Only HTTP, HTTPS and BitTorrent magnet links are accepted')

def clean_name(value):
    if not isinstance(value,str) or not 1<=len(value)<=180 or value in ('.','..') or value.startswith('.') or any(c in '/\\' or ord(c)<32 for c in value):raise ValueError('Use a plain visible filename, not a path')
    return value

def config_text(root,target,token,options):
    if any('\n' in str(p) or '\r' in str(p) for p in (root,target,token)):raise ValueError('Invalid configuration path')
    lines=['enable-rpc=true','rpc-listen-all=false','rpc-listen-port=6800','rpc-allow-origin-all=false','rpc-max-request-size=2M','rpc-secret='+token,
           'dir='+str(target),'input-file='+str(root/'aria2.session'),'save-session='+str(root/'aria2.session'),'save-session-interval=5','auto-save-interval=5',
           'pause=true','continue=true','always-resume=true','max-tries=0','retry-wait=30','timeout=30','connect-timeout=15','max-concurrent-downloads='+str(options['concurrent']),
           'split=4','max-connection-per-server=4','file-allocation=none','allow-overwrite=false','auto-file-renaming=true','check-certificate=true','check-integrity=true',
           'force-save=true','rpc-save-upload-metadata=true','save-not-found=false','max-download-result=1024','keep-unfinished-download-result=true','follow-metalink=false','follow-torrent=false',
           'enable-dht=true','enable-dht6=false','dht-file-path='+str(root/'dht.dat'),'dht-listen-port=6881','listen-port=6881','enable-peer-exchange=true','bt-enable-lpd=false',
           'seed-ratio='+str(options['seed_ratio']),'seed-time='+str(options['seed_minutes']),'max-overall-download-limit='+str(options['download_kib'])+'K','max-overall-upload-limit='+str(options['upload_kib'])+'K',
           'console-log-level=error','summary-interval=0','log-level=error','log='+str(root/'aria2.log')]
    return '\n'.join(lines)+'\n'

class Downloads:
    def __init__(self,ctx):self.ctx=ctx;self.root=Path('/var/lib/freeqnap-downloads')
    def settings(self):return self.ctx.state.setting('downloads_settings')
    def jobs(self):return self.ctx.state.setting('downloads_jobs',{})
    def rpc(self,method,params=()):
        token=(self.ctx.directory/'downloads-rpc-token').read_text().strip()
        raw=json.dumps({'jsonrpc':'2.0','id':'freeqnap','method':'aria2.'+method,'params':['token:'+token,*params]}).encode()
        request=urllib.request.Request('http://127.0.0.1:6800/jsonrpc',data=raw,headers={'Content-Type':'application/json'})
        try:
            # Never use environment proxy variables for private loopback RPC.
            try:
                with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=3) as response:data=response.read(1024**2+1)
            except urllib.error.HTTPError as error:
                if error.code!=400:raise
                data=error.read(1024**2+1)
            if len(data)>1024**2:raise ValueError('RPC response exceeds limit')
            value=json.loads(data)
        except (OSError,urllib.error.URLError,ValueError):raise ValueError('Download engine unavailable; queued jobs remain durable') from None
        if 'error' in value:
            if method=='tellStatus' and value['error'].get('code')==1: return None
            raise ValueError('Download engine rejected operation; inspect the private local engine log')
        return value.get('result')
    def target(self,settings=None):
        settings=settings or self.settings()
        if not settings:raise ValueError('Choose a download destination first')
        pool,mount=self.ctx.volume(settings['pool'])
        if pool.get('filesystem_uuid')!=settings['filesystem_uuid']:raise ValueError('Download volume identity changed')
        target=mount/'.freeqnap-downloads'
        if target.is_symlink() or not target.is_dir() or target.stat().st_dev!=mount.stat().st_dev:raise ValueError('Download folder is unavailable')
        if target.stat().st_ino!=settings['inode']:raise ValueError('Download folder changed identity')
        return target
    def setup(self,request):
        if set(request)-{'pool','concurrent','download_kib','upload_kib','seed_ratio','seed_minutes'}:raise ValueError('Unsupported download setting')
        with self.ctx.lock():
            pool,mount=self.ctx.volume(name(request['pool']))
            if pool.get('read_only'):raise ValueError('Download destination must be writable')
            old=self.settings()
            if old and old['pool']!=pool['name'] and (self.jobs() or self.ctx.state.setting('downloads_retained_files',{})):raise ValueError('Download history still references the current pool; changing pools does not move partial or retained files. Keep the existing destination.')
            options={}
            for key,default,low,high in (('concurrent',3,1,8),('download_kib',0,0,1000000),('upload_kib',256,1,1000000),('seed_minutes',0,0,10080)):
                v=request.get(key,default)
                if isinstance(v,bool) or not isinstance(v,int) or not low<=v<=high:raise ValueError('Invalid '+key)
                options[key]=v
            ratio=request.get('seed_ratio',1.0)
            if isinstance(ratio,bool) or not isinstance(ratio,(int,float)) or not 0<=ratio<=100:raise ValueError('Invalid seed ratio')
            options['seed_ratio']=float(ratio)
            account=pwd.getpwnam(UID_NAME);target=mount/'.freeqnap-downloads'
            if target.exists() and (target.is_symlink() or target.stat().st_uid!=account.pw_uid):raise ValueError('Existing download folder has unexpected ownership')
            target.mkdir(mode=0o750,exist_ok=True);os.chown(target,account.pw_uid,account.pw_gid)
            self.root.mkdir(mode=0o700,parents=True,exist_ok=True);os.chown(self.root,account.pw_uid,account.pw_gid)
            tokenpath=self.ctx.directory/'downloads-rpc-token'
            if not tokenpath.exists():
                fd=os.open(tokenpath,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'w') as f:f.write(secrets.token_hex(32)+'\n');f.flush();os.fsync(f.fileno())
            token=tokenpath.read_text().strip()
            conf=self.root/'aria2.conf';conf.write_text(config_text(self.root,Path('/srv/freeqnap/download-work'),token,options));conf.chmod(0o600);os.chown(conf,account.pw_uid,account.pw_gid)
            session=self.root/'aria2.session'
            if not session.exists():session.touch(mode=0o600);os.chown(session,account.pw_uid,account.pw_gid)
            settings={'pool':pool['name'],'filesystem_uuid':pool['filesystem_uuid'],'inode':target.stat().st_ino,'options':options}
            # Mount dependency stops the process before a pool is removed; a namespace
            # pinned RW bind prevents an underlying empty OS directory receiving data.
            drop=Path('/etc/systemd/system/freeqnap-downloads.service.d');drop.mkdir(parents=True,exist_ok=True)
            escaped=self.ctx.run('systemd-escape','--path','--suffix=mount',str(mount)).strip()
            (drop/'volume.conf').write_text('[Unit]\nBindsTo='+escaped+'\nAfter='+escaped+'\n[Service]\nBindPaths='+str(target)+':/srv/freeqnap/download-work\n')
            self.ctx.state.set('downloads_settings',settings)
            self.ctx.run('systemctl','daemon-reload');self.ctx.run('systemctl','enable',SERVICE);self.ctx.run('systemctl','restart',SERVICE)
            return {'configured':True,'destination':'Private downloads on '+pool['name'],'settings':settings,'files_not_deleted':True}
    def public_job(self,row):
        return {k:v for k,v in row.items() if k not in ('url','torrent_base64')}
    def status(self,request=None):
        return {'retained_files':list(self.ctx.state.setting('downloads_retained_files',{}).values()),'settings':self.settings(),'jobs':[self.public_job(j) for j in sorted(self.jobs().values(),key=lambda j:j['created'],reverse=True)],'upload_note':'Torrents upload while downloading. Limits and post-completion seeding apply to all torrents.','vpn_note':'Downloads follow NAS routing. Full-tunnel VPN plus its kill switch is required to prevent ordinary-WAN downloads.'}
    def add(self,request):
        if set(request)-{'url','torrent_base64','name','sha256'}:raise ValueError('Unsupported download field')
        with self.ctx.lock():
            self.target();rows=self.jobs()
            if len(rows)>=LIMIT:raise ValueError('Download history is full; remove selected finished records without deleting files')
            ident=secrets.token_hex(16);gid=secrets.token_hex(8)
            row={'id':ident,'gid':gid,'created':time.time(),'updated':time.time(),'desired':'running','state':'queued','attempts':0,'destination':self.settings()}
            if request.get('torrent_base64'):
                if request.get('url'):raise ValueError('Choose a torrent file or URL')
                try:data=base64.b64decode(request['torrent_base64'],validate=True)
                except (ValueError,TypeError):raise ValueError('Invalid torrent upload') from None
                if not 1<=len(data)<=512*1024 or not data.startswith(b'd') or not data.endswith(b'e'):raise ValueError('Upload a torrent file up to 512 KiB')
                row.update(kind='torrent',torrent_base64=base64.b64encode(data).decode(),label=clean_name(request.get('name','torrent')))
            else:
                value,kind=url(request.get('url'));row.update(url=value,kind=kind,label=clean_name(request.get('name') or ('torrent' if kind=='torrent' else urllib.parse.unquote(urllib.parse.urlsplit(value).path.split('/')[-1])[:180] or 'download')))
            digest=request.get('sha256','')
            if digest and not re.fullmatch('[a-fA-F0-9]{64}',digest):raise ValueError('Invalid expected SHA-256')
            row['sha256']=digest.lower();rows[ident]=row;self.ctx.state.set('downloads_jobs',rows)
            # The manager performs network submission after this durable commit.
            return {'job':self.public_job(row)}
    def control(self,request):
        with self.ctx.lock():
            rows=self.jobs();row=rows.get(request.get('id'))
            if not row:raise ValueError('Unknown download')
            action=request.get('action')
            if action not in ('pause','resume','remove'):raise ValueError('Choose pause, resume or remove')
            row['desired']={'pause':'paused','resume':'running','remove':'removed'}[action];row['updated']=time.time()
            if action=='resume' and row.get('recovery_required'):
                raise ValueError('Resume data is damaged. Existing files are preserved. Start a new download in a fresh job, or recover the partial files manually.')
            if action=='resume':row['next_retry']=0
            self.ctx.state.set('downloads_jobs',rows)
            return {'job':self.public_job(row),'files_deleted':False}
    def reconcile(self):
        settings=self.settings()
        if not settings:return
        try:self.target(settings)
        except (ValueError,OSError):
            self.ctx.run('systemctl','stop',SERVICE);return
        keys=list(self.jobs())
        if not keys:return
        cursor=self.ctx.state.setting('downloads_cursor',0)%len(keys)
        batch=(keys[cursor:]+keys[:cursor])[:16]
        for ident in batch:
            with self.ctx.lock():
                rows=self.jobs();row=rows.get(ident);changed=False
                if not row or row.get('state')=='complete' and row['desired']=='running':continue
                if row.get('recovery_required') and row['desired']!='removed':continue
                try:
                    status=self.rpc('tellStatus',[row['gid'],['gid','status','totalLength','completedLength','downloadSpeed','uploadSpeed','errorCode','errorMessage','followedBy']])
                    if row['desired']=='removed':
                        if status and status['status'] in ('active','waiting','paused'):self.rpc('forceRemove',[row['gid']])
                        if status:self.rpc('removeDownloadResult',[row['gid']])
                        retained=self.ctx.state.setting('downloads_retained_files',{})
                        if len(retained)>=1024:raise ValueError('Retained file history is full; preserve the queue entry')
                        retained[ident]=self.public_job(row);self.ctx.state.set('downloads_retained_files',retained)
                        del rows[ident];changed=True;continue
                    if status and status.get('status')=='error' and str(status.get('errorCode'))=='1' and 'segment file' in str(status.get('errorMessage','')).lower():
                        row.update(state='error',recovery_required=True,download_bps=0,upload_bps=0,error_code='1',engine_error='Resume data is damaged. Existing files are preserved. Start a new download, or recover the partial files manually.');changed=True;continue
                    if status and status.get('followedBy'):
                        # Magnets create the payload GID: persist it before any control.
                        if len(status['followedBy'])!=1:raise ValueError('Unexpected torrent metadata descendants; manual review required')
                        row['metadata_gid']=row['gid'];row['gid']=status['followedBy'][0];changed=True;continue
                    if status:
                        row.pop('engine_error',None)
                        row.update(state=status['status'],total_bytes=int(status.get('totalLength',0)),completed_bytes=int(status.get('completedLength',0)),download_bps=int(status.get('downloadSpeed',0)),upload_bps=int(status.get('uploadSpeed',0)),error_code=status.get('errorCode'));changed=True
                        if row['desired']=='paused' and status['status'] in ('active','waiting'):self.rpc('forcePause',[row['gid']])
                        elif row['desired']=='running' and status['status']=='paused':self.rpc('unpause',[row['gid']])
                        elif row['desired']=='running' and status['status'] in ('error','removed') and time.time()>=row.get('next_retry',0):
                            self.rpc('removeDownloadResult',[row['gid']]);status=None;row['next_retry']=time.time()+90
                    if status is None and row['desired']=='running' and row.get('state')!='complete' and time.time()>=row.get('next_retry',0):
                        # Each job has a dedicated fixed subdirectory; no arbitrary path/options.
                        options={'gid':row['gid'],'dir':'/srv/freeqnap/download-work/'+row['id'],'pause':'false'}
                        if row['sha256']:options['checksum']='sha-256='+row['sha256']
                        if row['kind']=='url':options['out']=row['label']
                        if row.get('torrent_base64'):self.rpc('addTorrent',[row['torrent_base64'],[],options])
                        else:self.rpc('addUri',[[row['url']],options])
                        row['attempts']+=1;row['next_retry']=time.time()+90;row['state']='queued';changed=True
                except (ValueError,KeyError,TypeError):
                    # One bad URL/torrent or an ambiguous reply never halts later jobs.
                    row['engine_error']='Not reconciled; retained for retry';row['next_retry']=max(row.get('next_retry',0),time.time()+30);changed=True
                finally:
                    if changed:self.ctx.state.set('downloads_jobs',rows)
        self.ctx.state.set('downloads_cursor',(cursor+len(batch))%len(keys))

    def file_view(self,request):
        from .files import Files,relative
        ident=request.get('id','')
        if not re.fullmatch('[a-f0-9]{32}',ident):raise ValueError('Select a known download')
        item=self.jobs().get(ident) or self.ctx.state.setting('downloads_retained_files',{}).get(ident)
        if not item:raise ValueError('Unknown download files')
        destination=item.get('destination') or self.settings()
        if not destination:raise ValueError('Download destination metadata unavailable')
        pool,mount=self.ctx.volume(destination['pool'])
        if pool['filesystem_uuid']!=destination['filesystem_uuid']:raise ValueError('Download volume changed identity')
        base=mount/'.freeqnap-downloads'
        if base.is_symlink() or base.stat().st_ino!=destination['inode']:raise ValueError('Download root changed identity')
        context=self.ctx
        class View(Files):
            @contextlib.contextmanager
            def directory(self,share_id,path=''):
                descriptor=os.open(base,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                try:
                    device=os.fstat(descriptor).st_dev
                    if device!=mount.stat().st_dev:raise ValueError('Download volume no longer mounted')
                    for component in (ident,*relative(path)):
                        child=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=descriptor)
                        os.close(descriptor);descriptor=child
                        if os.fstat(descriptor).st_dev!=device:raise ValueError('Nested mounts are not followed')
                    context.volume(destination['pool'])
                    yield descriptor,{},pool
                finally:os.close(descriptor)
        return View(self.ctx)
    def list_files(self,request):return self.file_view(request).list({'share':'download','path':request.get('path','')})
    def read_file(self,request):return self.file_view(request).read({'share':'download','path':request.get('path',''),'offset':request.get('offset',0),'count':request.get('count',512*1024)})
