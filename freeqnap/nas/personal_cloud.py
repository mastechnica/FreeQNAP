"""Explicit iCloud sign-in and download-only scheduling. No deletion API calls."""
import contextlib,importlib.util,logging,os,re,threading,time
from pathlib import Path
from .personal_photos import digest,text

class PersonalCloud:
    def __init__(self,photos,factory=None):
        self.photos=photos;self.ctx=photos.ctx;self.factory=factory;self.client=None;self.auth_lock=threading.Lock();self.auth_state='signed-out';self.restored=False;self.last_auth=0
    def settings(self):return self.ctx.state.setting('personal-icloud',{'enabled':False,'interval_minutes':30,'hidden':False,'shared':False,'preserve_edits':True,'adp':False,'account':''})
    def installed(self):
        try:return self.factory is not None or importlib.util.find_spec('pyicloud_ipd') is not None
        except (ImportError,ValueError):return False
    def status(self,r=None):
        cfg=self.settings();return {'settings':cfg,'installed':self.installed(),'authentication':self.auth_state,'last_run':self.ctx.state.setting('personal-icloud-last-run',{}),'retention_locked':True,'deletion_available':False,'password_saved':False,'paused':self.ctx.state.setting('personal-icloud-paused',False)}
    def save(self,r):
        old=self.settings();account=text(r.get('account',old['account']),254).strip();interval=r.get('interval_minutes',30)
        if account and ('@' not in account or len(account)<3):raise ValueError('Enter your Apple Account email address')
        if type(interval)!=int or not 15<=interval<=1440:raise ValueError('Choose an interval from 15 minutes to one day')
        cfg={'account':account,'interval_minutes':interval}
        for k in ('enabled','hidden','shared','preserve_edits','adp'):
            v=r.get(k,old.get(k,False))
            if not isinstance(v,bool):raise ValueError('Choose iCloud options on or off')
            cfg[k]=v
        if cfg['enabled']:
            if not account:raise ValueError('Enter an Apple Account first')
            with self.photos.root():pass
            if not self.installed():raise ValueError('Install the optional iCloud connector first')
        if account!=old['account']:
            if self.photos.busy.locked() or self.auth_lock.locked():raise ValueError('Pause and wait before changing the account')
            self.client=None;self.auth_state='signed-out';self.restored=False
        self.ctx.state.set('personal-icloud',cfg)
        if cfg['enabled']:self.ctx.state.set('personal-icloud-paused',False)
        return self.status()
    def _factory(self,password):
        cfg=self.settings();cookies=self.ctx.directory/'personal-icloud-sessions'/digest(cfg['account']);cookies.mkdir(mode=0o700,parents=True,exist_ok=True);cookies.chmod(0o700)
        # Upstream logs can include account or signed URLs; never forward them.
        for logger in ('pyicloud_ipd','icloudpd'):
            log=logging.getLogger(logger);log.setLevel(logging.CRITICAL+1);log.propagate=False
        if self.factory:return self.factory(cfg['account'],password,str(cookies))
        from pyicloud_ipd.base import PyiCloudService
        box=[password]
        try:return PyiCloudService('com',cfg['account'],lambda:box[0] or None,None,cookie_directory=str(cookies))
        finally:
            box[0]=''
            for p in cookies.rglob('*'):
                if p.is_file() and not p.is_symlink():p.chmod(0o600)
    def login(self,r):
        if not self.installed():raise ValueError('The optional iCloud connector is not installed')
        if not self.settings()['account']:raise ValueError('Save your Apple Account email address first')
        password=text(r.get('password'),1024)
        if not password:raise ValueError('Enter your Apple Account password privately')
        if time.monotonic()-self.last_auth<15:raise ValueError('Please wait before another sign-in attempt')
        if self.photos.busy.locked() or not self.auth_lock.acquire(False):raise ValueError('A photo download or authentication is already running')
        self.last_auth=time.monotonic();self.auth_state='signing-in';threading.Thread(target=self._login,args=(password,),daemon=True).start();return {'started':True}
    def _login(self,password):
        try:
            self.client=self._factory(password);password='';self.restored=True
            if self.client.requires_2fa:
                self.auth_state='verification-code-needed'
                try:self.client.trigger_push_notification()
                except Exception:pass
            elif getattr(self.client,'requires_2sa',False):self.auth_state='older-two-step-not-supported';self.client=None
            else:self._consent()
        except Exception:self.client=None;self.auth_state='sign-in-needed'
        finally:password='';self.auth_lock.release()
    def _consent(self):
        if self.settings()['adp']:
            self.auth_state='approve-web-access-on-iphone'
            self.client.request_pcs_consent('photos')
        self.auth_state='connected'
    def code(self,r):
        code=r.get('code')
        if not isinstance(code,str) or not re.fullmatch('[0-9]{6}',code):raise ValueError('Enter the six-digit Apple verification code')
        if self.auth_state!='verification-code-needed' or self.client is None:raise ValueError('Start Apple sign-in first')
        if not self.auth_lock.acquire(False):raise ValueError('Authentication is already running')
        threading.Thread(target=self._code,args=(code,),daemon=True).start();return {'started':True}
    def _code(self,code):
        try:
            if not self.client.validate_2fa_code(code):self.auth_state='verification-code-needed';return
            self.client.trust_session();self._consent()
        except Exception:self.auth_state='sign-in-needed';self.client=None
        finally:code='';self.auth_lock.release()
    def restore(self):
        if self.restored or not self.settings()['account'] or not self.installed():return
        self.restored=True
        try:
            self.client=self._factory('')
            if self.client.requires_2fa or getattr(self.client,'requires_2sa',False):self.auth_state='sign-in-needed';self.client=None
            else:self._consent()
        except Exception:self.client=None;self.auth_state='sign-in-needed'
    def run(self,r=None):
        if not self.settings()['account']:raise ValueError('Configure iCloud first')
        if self.auth_state!='connected' or self.client is None:raise ValueError('Connect your Apple Account before downloading')
        if self.auth_lock.locked() or not self.photos.busy.acquire(False):raise ValueError('A photo operation is already running')
        self.ctx.state.set('personal-icloud-paused',False);self.photos.stop.clear();threading.Thread(target=self._download,daemon=True).start();return {'started':True}
    def _download(self):
        cfg=self.settings();complete=failed=seen=0;began=time.time();inventory_complete=False;inventory_problem=False
        self.photos.progress(state='checking-icloud',completed=0,failed=0)
        try:
            api=self.client;service=api.photos
            libraries=[('personal',service)]
            if cfg['shared']:
                # Fail visibly if shared-library enumeration is unavailable.
                from pyicloud_ipd.services.photos import PhotoLibrary
                endpoint=service.get_service_endpoint('shared');response=api.session.post(endpoint+'/zones/list',data='{}',headers={'Content-Type':'text/plain'});response.raise_for_status();zones=response.json()
                if not isinstance(zones.get('zones'),list):raise ValueError('Shared-library inventory unavailable')
                for zone in zones['zones']:
                    if not zone.get('deleted'):libraries.append(('shared:'+zone['zoneID']['zoneName'],PhotoLibrary(endpoint,api.session,service.params,zone['zoneID'],'shared')))
            for library_name,library in libraries:
                collections=[library.all]
                if cfg['hidden']:collections.append(library.hidden)
                for collection in collections:
                    before_count=len(collection);collection_seen=0;collection_ids=set()
                    for asset in collection:
                        if self.photos.stop.is_set():raise InterruptedError('Paused')
                        with self.photos.root():pass
                        seen+=1;collection_seen+=1
                        remote_id=str(getattr(asset,'id','unidentified-'+str(collection_seen)))
                        if remote_id in collection_ids:inventory_problem=True;continue
                        collection_ids.add(remote_id)
                        try:
                            versions=asset.versions
                            chosen=[(k,v) for k,v in versions.items() if getattr(k,'value',str(k)).lower() in (('original','alternative','adjusted') if cfg['preserve_edits'] else ('original','alternative'))]
                            if not chosen:raise ValueError('No downloadable original was returned')
                            for key,version in chosen:
                                variant=type(key).__name__+':'+str(getattr(key,'value',key));revision=str(version.checksum)+':'+str(version.size)+':'+str(version.type)
                                extensions={'public.heic':'HEIC','public.heif':'HEIF','public.jpeg':'JPG','public.png':'PNG','com.apple.quicktime-movie':'MOV','public.mpeg-4':'MP4','com.adobe.raw-image':'DNG'}
                                extension=extensions.get(version.type,Path(asset.filename).suffix[1:]);filename=Path(asset.filename).stem+'.'+extension
                                def open_range(offset):
                                    response=asset.download(api.session,version.url,offset)
                                    try:
                                        if offset:
                                            match=re.fullmatch(r'bytes ([0-9]+)-([0-9]+)/([0-9]+)',response.headers.get('Content-Range',''))
                                            if response.status_code!=206 or not match or int(match[1])!=offset or int(match[3])!=version.size:raise ValueError('Server did not honor the saved download range')
                                        elif response.status_code not in (200,206):raise ValueError('Apple did not provide this asset')
                                        for data in response.iter_content(1024**2):
                                            if data:yield data
                                    finally:response.close()
                                created=asset.created.isoformat() if getattr(asset,'created',None) else None
                                self.photos.ingest('icloud:'+cfg['account']+':'+library_name+':'+asset.id+':'+variant,revision,filename,open_range,int(version.size),group='icloud:'+cfg['account']+':'+library_name+':'+asset.id,taken=created);complete+=1
                        except InterruptedError:raise
                        except Exception:failed+=1
                        self.photos.progress(state='downloading',seen=seen,completed=complete,failed=failed)
                    if before_count!=collection_seen or len(collection)!=before_count:inventory_problem=True
            inventory_complete=not inventory_problem
            self.photos.progress(state='complete-with-errors' if failed or inventory_problem else 'complete',seen=seen,completed=complete,failed=failed)
        except InterruptedError:self.photos.progress(state='paused',seen=seen,completed=complete,failed=failed)
        except Exception:
            self.photos.progress(state='needs-attention',seen=seen,completed=complete,failed=failed,message='iCloud listing stopped; previous originals and partial downloads retained. Check Apple authentication and connectivity.')
        finally:
            self.ctx.state.set('personal-icloud-last-run',{'started':began,'finished':time.time(),'inventory_complete':inventory_complete,'seen':seen,'processed_files':complete,'failed':failed,'originals_retained':True,'scope':{'personal':True,'hidden':cfg['hidden'],'shared':cfg['shared']}});self.photos.busy.release()
    def tick(self):
        cfg=self.settings()
        if not cfg['enabled'] or self.ctx.state.setting('personal-icloud-paused',False) or self.auth_lock.locked() or self.photos.busy.locked():return
        self.restore()
        previous=self.ctx.state.setting('personal-icloud-last-run',{})
        if self.auth_state=='connected' and time.time()-previous.get('finished',0)>=cfg['interval_minutes']*60:self.run()
    def health(self):
        if not self.settings()['enabled']:return []
        state=self.photos.status();out=[]
        if self.auth_state not in ('connected','signing-in','approve-web-access-on-iphone'):
            out.append({'source':'personal-photos:icloud','severity':'warning','summary':'iCloud photo archive needs sign-in','details':{'authentication':self.auth_state}})
        if not state['online']:out.append({'source':'personal-photos:storage','severity':'critical','summary':'Personal photo archive volume unavailable','details':{}})
        last=self.ctx.state.setting('personal-icloud-last-run',{})
        if last and not last.get('inventory_complete') and state['operation'].get('state')!='paused':out.append({'source':'personal-photos:inventory','severity':'warning','summary':'iCloud photo inventory did not finish','details':{}})
        if (state['pending'] and not self.photos.busy.locked()) or last.get('failed'):
            out.append({'source':'personal-photos:pending','severity':'warning','summary':'Photo downloads need attention; previous originals retained','details':{'pending':state['pending']}})
        return out

    def pause(self,r):
        self.ctx.state.set('personal-icloud-paused',True)
        return self.photos.pause(r)
