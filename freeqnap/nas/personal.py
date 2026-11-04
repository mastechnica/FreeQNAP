"""Trusted-console personal namespaces. Never reachable as a raw HTTP operation."""
import json,os,re,threading,time
from pathlib import Path
from .common import Context
from .myradio import MyRadio
from .personal_photos import PersonalPhotos
from .personal_cloud import PersonalCloud
from .library_storage import LibraryStorage,FileLocation
from .fileops import FileManager
from .recovery import Recovery
from .bundle import Bundles
from .archives import Archives
from .file_metadata import FileMetadata

READ_RADIO={'myradio.status','myradio.catalog','myradio.item','myradio.read','myradio.book-text','myradio.stations','myradio.station-source','myradio.podcasts'}
READ_PHOTOS={'photos.status','photos.catalog','photos.places','photos.related','photos.read','photos.metadata-read'}
RADIO_METHODS={'status':'status','configure':'configure','catalog':'catalog','item':'item','read':'read','book-text':'book_text','upload-begin':'upload_begin','upload-chunk':'upload_chunk','upload-finish':'upload_finish','metadata':'metadata','artwork':'artwork','artwork-url':'artwork_url','progress':'progress','lookup':'lookup','stations':'stations','station-save':'station_save','station-check':'station_check','station-source':'station_source','podcasts':'feeds','podcast-add':'feed_add','podcast-refresh':'feed_refresh'}
PHOTO_METHODS={'metadata-read':'metadata_read','metadata-plan':'metadata_plan','metadata-apply':'metadata_apply','status':'status','catalog':'catalog','places':'places','related':'related','read':'read','annotate':'annotate','album-create':'album','album-add':'album_add','import-folder':'import_folder'}
CLOUD_METHODS={'photos.icloud-status':'status','photos.icloud-save':'save','photos.icloud-login':'login','photos.icloud-code':'code','photos.icloud-run':'run','photos.pause':'pause'}
QUEUED={'library.storage-apply','myradio.scan','myradio.import-folder','myradio.station-refresh','myradio.download','files.transfer','files.delete','files.recycle','files.archive'}
FILE_METHODS={'media-neighbors':'media_neighbors','list':'list','read':'read','mkdir':'mkdir','upload-begin':'upload_begin','upload-chunk':'upload_chunk','upload-finish':'upload_finish','move-plan':'move_plan','move':'move','transfer-plan':'transfer_plan','recycle-plan':'recycle_plan','delete-plan':'delete_plan','trash':'trash_items','restore-plan':'restore_plan','restore':'restore','purge-plan':'purge_plan','purge':'purge','policy':'policy','policy-plan':'policy_plan','policy-save':'policy_apply','stages':'stages','stage-plan':'stage_plan','stage-remove':'stage_remove'}

class PersonalContext(Context):
 def __init__(self,base,owner):self.base=base;self.owner=owner;super().__init__(base.directory/'personal'/owner,runner=base.run)
 def volume(self,key):return self.base.volume(key)
 def lock(self):return self.base.lock()
 def config(self):
  cfg=self.base.config();shares={}
  for key,label in [('myradio','my-radio'),('personal-photos','my-photos'),('personal-files','my-files')]:
   v=self.state.setting(key,{})
   if v.get('location_selected'):
    root=Path(cfg['pools'][v['pool']]['mountpoint']);shares[label]={'name':label,'pool':v['pool'],'path':str(root/v['location_folder']),'gid':os.getegid(),'label':{'my-radio':'My Radio import folder','my-photos':'Personal Photos import folder','my-files':'My personal files'}[label],'personal_root':True,'enabled':True}
  for assignment in self.state.setting('assigned-shares',[]):
   source=cfg['shares'].get(assignment.get('share'))
   if not source:continue
   if source['name'] in shares or source['name'] in ('my-radio','my-photos','my-files'):continue
   pool=cfg['pools'].get(source['pool'],{})
   if any(assignment.get(k)!=source.get(k) for k in ('pool','path')) or assignment.get('filesystem_uuid')!=pool.get('filesystem_uuid'):continue
   shares[source['name']]={**source,'personal_root':True,'read_only':bool(source.get('read_only')) or assignment['access']=='read','admin_assigned':True}
  return {**cfg,'shares':shares,'users':{},'repositories':{},'libraries':{}}
 def save_locations(self):
  rows=self.base.state.setting('personal-library-locations',{});rows[self.owner]=[]
  for key in ('myradio','personal-photos','personal-files'):
   cfg=self.state.setting(key,{})
   if cfg:rows[self.owner]+=[{k:cfg[k] for k in ('pool','folder','filesystem_uuid')}]+cfg.get('previous_locations',[])
  self.base.state.set('personal-library-locations',rows)

class Personal:
 def __init__(self,backend):self.backend=backend;self.ctx=backend.ctx;self.lock=threading.RLock();self.scopes={};self.last_tick=0
 def get(self,owner,label='Personal library'):
  if not isinstance(owner,str) or not re.fullmatch('[a-f0-9]{32}',owner):raise ValueError('Invalid personal account identity')
  with self.lock:
   if owner not in self.scopes:
    if len(self.scopes)>=32:raise ValueError('Personal account capacity reached')
    ctx=PersonalContext(self.ctx,owner);radio=MyRadio(ctx);photos=PersonalPhotos(ctx);cloud=PersonalCloud(photos);storage=LibraryStorage(ctx,radio,photos);storage.owner={'id':owner,'label':label};ctx.state.set('personal-library-owner',storage.owner)
    ctx.state.reconcile_interrupted();radio.reconcile_downloads();files=FileManager(ctx);bundles=Bundles(ctx,files);self.scopes[owner]={'ctx':ctx,'radio':radio,'photos':photos,'cloud':cloud,'storage':storage,'metadata':FileMetadata(ctx,files),'file_location':FileLocation(ctx,storage.owner),'files':files,'bundles':bundles,'archives':Archives(ctx,files,bundles),'recovery':Recovery(ctx,files)}
   return self.scopes[owner]
 def shared(self,r):
  if set(r)!={'owner','label','primary','action','payload','scope'}:raise ValueError('Invalid shared envelope')
  photos=self.backend.personal_photos if r['primary'] else self.get(r['owner'],r['label'])['photos']
  return photos.shared_view(r['action'],r['payload'],r['scope'])
 def control(self,r):
  owner=r.get('owner');s=self.get(owner,r.get('label','Personal library'));enabled=r.get('enabled')
  if type(enabled)is not bool:raise ValueError('Invalid account state')
  policies=self.ctx.state.setting('personal-account-status',{});policies[owner]={'enabled':enabled,'permissions':r.get('permissions',[])};self.ctx.state.set('personal-account-status',policies)
  if 'assignments' in r:s['ctx'].state.set('assigned-shares',r['assignments'])
  if not enabled:s['photos'].stop.set();s['ctx'].state.set('personal-icloud-paused',True)
  return {'enabled':enabled,'personal_jobs_retained':True}
 def invoke(self,r):
  if set(r)-{'owner','label','action','payload','assignments'} or not {'owner','label','action','payload'}<=set(r):raise ValueError('Invalid personal envelope')
  s=self.get(r['owner'],r['label'])
  if 'assignments' in r:s['ctx'].state.set('assigned-shares',r['assignments'])
  return self.dispatch(s,r['action'],r['payload'])
 def dispatch(self,s,action,payload,queued=False):
  if not isinstance(payload,dict):raise ValueError('JSON object required')
  if action=='myradio.configure' and not s['radio'].config().get('location_selected'):raise ValueError('Choose your personal library location first')
  if action=='personal.status':
   pools=[]
   for key,value in self.ctx.config()['pools'].items():
    try:
     p,mount=self.ctx.volume(key);v=os.statvfs(mount);pools.append({'name':key,'mounted':True,'read_only':bool(p.get('read_only')),'available_bytes':v.f_bavail*v.f_frsize})
    except (ValueError,OSError):pass
   return {'pools':pools,'shares':list(s['ctx'].config()['shares'].values()),'users':[],'repositories':[],'libraries':[],'jobs':s['ctx'].state.jobs(),'services':{},'packages':{},'worker':{},'health':{'active_total':0},'personal_only':True}
  if action=='library.files-status':return s['file_location'].status()
  if action=='library.files-plan':
   folder=payload.get('folder','');prefix='Users/'+s['ctx'].owner+'/'
   if not isinstance(folder,str):raise ValueError('Choose a personal folder')
   return s['file_location'].plan({**payload,'folder':folder if folder.startswith(prefix) else prefix+folder})
  if action=='library.files-apply':return s['file_location'].apply(payload)
  if action=='personal.jobs':return {'jobs':s['ctx'].state.jobs()}
  if action=='library.storage-plan':
   kind=payload.get('library');folder=payload.get('folder','');prefix='Users/'+s['ctx'].owner+'/'
   if not isinstance(folder,str):raise ValueError('Choose a personal folder')
   if not folder.startswith(prefix):folder=prefix+folder
   return s['storage'].plan({**payload,'folder':folder})
  if action in ('myradio.import-folder','photos.import-folder'):
   source=payload.get('share')
   if source not in s['ctx'].config()['shares']:raise ValueError('Import from your own File Manager folders; an administrator can transfer USB files into them')
  if action.startswith(('files.','recovery.')):
   for field in ('share','target_share'):
    if field in payload and payload[field] not in s['ctx'].config()['shares']:raise ValueError('Choose one of your own library folders')
  if action in QUEUED and not queued:
   if any(k in payload for k in ('password','secret','key_base64')):raise ValueError('Secrets cannot enter jobs')
   schemas={'library.storage-apply':{'plan_id','digest','confirmation'},'myradio.scan':set(),'myradio.import-folder':{'category','share','path'},'myradio.station-refresh':{'group','query','country'},'myradio.download':{'source'},'files.transfer':{'plan_id','digest','confirmation'},'files.delete':{'plan_id','digest','confirmation'},'files.recycle':{'plan_id','digest','confirmation'},'files.archive':{'plan_id','digest','confirmation'}}
   if set(payload)-schemas[action]:raise ValueError('Unknown queued setting')
   return {'job_id':s['ctx'].state.enqueue(action,payload)}
  if action=='library.storage-apply':
   return s['storage'].apply(payload)
  if action.startswith('myradio.'):
   key=action.split('.',1)[1]
   if key in RADIO_METHODS:return getattr(s['radio'],RADIO_METHODS[key])(payload)
   if key in ('scan','import-folder','station-refresh','download'):return getattr(s['radio'],key.replace('-','_'))(payload)
   if key=='import-url':return s['radio'].queue_url(payload,s['ctx'].state.enqueue)
   if key=='resume-download':return s['radio'].retry_download(payload,s['ctx'].state.enqueue)
   if key=='episode-download':return s['radio'].episode_download(payload,s['ctx'].state.enqueue)
  if action in CLOUD_METHODS:return getattr(s['cloud'],CLOUD_METHODS[action])(payload)
  if action.startswith('photos.') and action.split('.',1)[1] in PHOTO_METHODS:return getattr(s['photos'],PHOTO_METHODS[action.split('.',1)[1]])(payload)
  if action in ('recovery.list','recovery.plan','recovery.apply'):return getattr(s['recovery'],action.split('.')[1])(payload)
  if action.startswith('files.'):
   key=action.split('.',1)[1]
   if key in ('metadata-read','metadata-plan','metadata-apply'):return getattr(s['metadata'],{'metadata-read':'read','metadata-plan':'plan','metadata-apply':'apply'}[key])(payload)
   if key=='recycle-policy':return s['files'].policy_apply(payload)
   if key=='recycle-policy-plan':return s['files'].policy_plan(payload)
   if key=='archive-plan':return s['archives'].plan(payload)
   if key=='archive':return s['archives'].apply(payload,payload['plan_id'])
   if key in ('bundle','bundle-info','bundle-node','bundle-read'):return getattr(s['bundles'],{'bundle':'start','bundle-info':'info','bundle-node':'node','bundle-read':'read'}[key])(payload)
   if key=='transfer':return s['files'].transfer(payload)
   if key=='delete':return s['files'].move(payload)
   if key=='recycle':return s['files'].recycle(payload,payload['plan_id'])
   if key in FILE_METHODS:return getattr(s['files'],FILE_METHODS[key])(payload)
  raise ValueError('Unavailable personal operation')
 def one(self):
  root=self.ctx.directory/'personal'
  ids=[p.name for p in root.iterdir() if p.is_dir() and re.fullmatch('[a-f0-9]{32}',p.name)] if root.exists() else []
  for owner in ids[:32]:
   if not self.ctx.state.setting('personal-account-status',{}).get(owner,{}).get('enabled',True):continue
   s=self.get(owner);job=s['ctx'].state.claim()
   if job:
    from ..personal_access import permission
    rights=self.ctx.state.setting('personal-account-status',{}).get(owner,{}).get('permissions')
    if rights is not None and permission(job['kind']) not in rights:
     s['ctx'].state.finish(job['id'],error='Account permissions changed; queued operation not executed and files retained');return
    try:s['ctx'].state.finish(job['id'],result=self.dispatch(s,job['kind'],json.loads(job['payload']),True))
    except Exception as e:s['ctx'].state.finish(job['id'],error=str(e))
    return
 def tick(self):
  if time.monotonic()-self.last_tick<60:return
  self.last_tick=time.monotonic()
  for owner,s in list(self.scopes.items()):
   if not self.ctx.state.setting('personal-account-status',{}).get(owner,{}).get('enabled',True):continue
   try:
    rights=self.ctx.state.setting('personal-account-status',{}).get(owner,{}).get('permissions')
    if rights is None or 'photos.icloud' in rights:s['cloud'].tick()
    if rights is None or 'myradio.write' in rights:s['radio'].refresh_due_feeds()
    s['files'].expire()
   except Exception:pass
