"""Session-derived NAS routing. Untrusted requests never choose the owner ID."""
from . import accounts,library_shares
from .access_scope import Broker
from .nas.personal import READ_RADIO,READ_PHOTOS

def is_personal(operation):return operation.startswith(('myradio.','photos.','library.','files.','recovery.'))
def permission(operation):
 if operation=='library.files-status':return 'files.read'
 if operation in READ_RADIO:return 'myradio.read'
 if operation=='photos.icloud-status':return 'photos.read'
 if operation in READ_PHOTOS:return 'photos.read'
 if operation.startswith('photos.icloud') or operation=='photos.pause':return 'photos.icloud'
 if operation.startswith('photos.'):return 'photos.write'
 if operation.startswith('myradio.'):return 'myradio.write'
 if operation.startswith('library.'):return 'storage.choose'
 if operation in ('files.transfers','files.metadata-read','files.media-neighbors','files.list','files.read','files.trash','files.policy','files.stages','files.bundle','files.bundle-info','files.bundle-node','files.bundle-read','recovery.list'):return 'files.read'
 if operation.startswith(('files.','recovery.')):return 'files.write'
 return None

class Gateway:
 def __init__(self,nas,state,session,share=None,managed=None):self.nas=Broker(nas,"user:"+session()["user"]["id"]);self.state=state;self.session=session;self.share=share;self.managed=managed
 def request(self,operation,payload=None):
  if operation in ('myradio.scan','myradio.import-folder','myradio.import-url','myradio.upload-begin','myradio.upload-chunk','myradio.upload-finish','myradio.metadata','myradio.artwork','myradio.artwork-url','myradio.album-save','myradio.metadata-apply'):
   session=self.session();owner=self.managed or (session or {}).get('user',{}).get('id','')
   if self.state.setting('library-sources:'+owner+':radio:run',{}).get('state')=='maintenance':raise ValueError('Your music library is being verified. Existing playback and other transfers remain available; edits and scans will resume when verification finishes.')
  if operation.startswith('photos.icloud-albums-'):
   from .photo_album_access import handle
   return handle(self,operation,payload or {})
  if operation=='myradio.scan':
   session=self.session();owner=self.managed or (session or {}).get('user',{}).get('id','')
   if self.state.setting('library-prepared:'+owner,{}).get('needs_native_reload') and not self._request('myradio.status',{}).get('prepared_scanning'):raise ValueError('Your collection is indexed. Full-library rescans are temporarily paused while the current file transfer finishes and the optimized scanner is activated.')
  if operation in ('myradio.music-browser','myradio.books-browser','myradio.album-save'):
   from . import radio_catalog
   return {'myradio.music-browser':radio_catalog.music,'myradio.books-browser':radio_catalog.books,'myradio.album-save':radio_catalog.album_save}[operation](self,payload or {})
  if operation=='myradio.overview':
   from .radio_hub import overview
   return overview(self)
  if operation=='myradio.listen':
   from .radio_listening import listen
   return listen(self,payload or {})
  if operation in ('myradio.providers','myradio.providers-save','myradio.metadata-search','myradio.metadata-apply'):
   from . import radio_providers
   fn={'myradio.providers':radio_providers.providers,'myradio.providers-save':radio_providers.configure,'myradio.metadata-search':radio_providers.search,'myradio.metadata-apply':radio_providers.apply}[operation]
   return fn(self,payload or {})
  if operation=='myradio.metadata' and isinstance((payload or {}).get('metadata'),dict) and any(k in (payload or {}).get('metadata',{}) for k in ('series','series_number','collections')):
   from .radio_catalog import save_book
   return save_book(self,payload)
  if operation=='myradio.card-save':
   from .library_cards import save
   return save(self,payload or {})
  if operation=='myradio.podcast-browser':
   from .podcast_browser import Browser
   return Browser(self).listing(payload or {})
  if operation.startswith('library.sources-'):
   from .library_sources import handle
   return handle(self,operation,payload or {})
  result=self._request(operation,{} if operation=='myradio.stations' else payload)
  if operation=='myradio.status':
   session=self.session();owner=self.managed or (session or {}).get('user',{}).get('id','')
   result={**result,'optimized_scan_pending':bool(self.state.setting('library-prepared:'+owner,{}).get('needs_native_reload') and not result.get('prepared_scanning'))}
  if operation=='myradio.stations':
   from .library_cards import stations
   result=stations(self,result,payload or {})
  if operation in ('myradio.catalog','myradio.item'):
   from .radio_catalog import extra
   if 'items' in result:result={**result,'items':[extra(self,v) for v in result['items']]}
   elif 'item' in result:result={**result,'item':extra(self,result['item'])}
  if operation in ('myradio.metadata','myradio.artwork','myradio.artwork-url'):
   from .radio_catalog import invalidate
   from .podcast_browser import scope
   invalidate(scope(self)[0],self.state)
  if operation=='myradio.podcast-add' and (payload or {}).get('url') and result.get('id'):
   from .podcast_browser import Browser
   Browser(self).remember(result['id'],payload['url'])
  if operation=='library.storage-apply' and result.get('job_id'):
   owner=self.managed or self.session()['user']['id']
   self.state.set('library-folders-followup:'+owner,{'state':'waiting-job','job_id':result['job_id']})
  if operation=='files.transfers':
   from .transfer_context import enrich
   result=enrich(result)
  return result
 def _request(self,operation,payload=None):
  payload=payload or {};s=self.session()
  if not s:raise PermissionError('Sign in again')
  user=s['user']
  if user['must_change']:raise PermissionError('Change your temporary password first')
  if operation.startswith(('personal.','access.')):raise PermissionError('Internal operation unavailable')
  if operation.startswith('activity.') and operation!='activity.system':raise PermissionError('Internal activity operation unavailable')
  if operation=='activity.system':return self.nas.request(operation,{})
  if operation=='users.usage' and user['role']!='administrator':raise PermissionError('Administrator access required')
  if user['role']!='administrator' and operation in ('external.discover','external.unlock-capabilities','external.session-files','external.session-read'):
   if not accounts.permitted(user,'files.read'):raise PermissionError('File browsing is not enabled for this account')
   return self.nas.request(operation,payload)
  if user['role']!='administrator' and operation in ('external.files','external.read'):
   if not accounts.permitted(user,'files.read'):raise PermissionError('File browsing is not enabled for this account')
   return self.nas.request('personal.invoke',{'owner':user['id'],'label':user['label'],'action':'files.list' if operation=='external.files' else 'files.read','payload':{**payload,'share':'pool:'+str(payload.get('pool',''))}})
  if user['role']!='administrator' and operation=='external.mount':
   if not accounts.permitted(user,'storage.unlock'):raise PermissionError('External-drive mounting is not enabled for this account')
   return self.nas.request(operation,payload)
  if user['role']!='administrator' and operation in ('external.import-plan','external.import','external.unlock-plan','external.unlock','external.lock-session','storage.unlock','storage.lock'):
   if not accounts.permitted(user,'storage.unlock'):raise PermissionError('The administrator has not enabled external-volume unlocking for this account')
   return self.nas.request(operation,payload)
  if user['role']!='administrator' and operation in ('files.pool-list','files.pool-read'):
   from .nas.common import name
   if not accounts.permitted(user,'files.read'):raise PermissionError('Permission not granted')
   pool=name(payload.get('pool'));return self.nas.request('personal.invoke',{'owner':user['id'],'label':user['label'],'action':'files.list' if operation.endswith('list') else 'files.read','payload':{**payload,'share':'pool:'+pool}})
  needed=permission(operation)
  if operation in ('files.metadata-plan','files.metadata-apply','photos.metadata-plan','photos.metadata-apply') and not accounts.permitted(user,'metadata.edit'):raise PermissionError('Metadata editing is not enabled for this account')
  if self.managed and is_personal(operation):
   if user['role']!='administrator':raise PermissionError('Only an administrator can manage another account')
   with self.state.connect() as db:target=db.execute('SELECT * FROM local_accounts WHERE id=?',(self.managed,)).fetchone()
   if not target:raise ValueError('Local account not found')
   if target['primary_admin']:return self.nas.request(operation,payload)
   return self.nas.request('personal.invoke',{'owner':target['id'],'label':target['label'],'action':operation,'payload':payload,'assignments':accounts.assignments(self.state,target['id'])})
  if self.share:
   grant=library_shares.resolve(self.state,user,self.share);kind=grant['kind'];allowed=READ_PHOTOS if kind=='photos' else READ_RADIO
   if operation=='myradio.progress':return {'saved':False,'shared_read_only':True}
   if operation=='photos.icloud-status':return {'installed':False,'settings':{},'authentication':'shared-read-only','last_run':{}}
   if operation not in allowed:raise PermissionError('Shared libraries are read-only')
   if not accounts.permitted(user,'photos.read' if kind=='photos' else 'myradio.read'):raise PermissionError('Permission not granted')
   if kind=='photos' and not operation.startswith('photos.') or kind!='photos' and not operation.startswith('myradio.'):raise PermissionError('Wrong shared library')
   if kind!='photos':
    if operation in ('myradio.stations','myradio.station-source','myradio.station-artwork') or operation=='myradio.podcasts' and kind!='podcasts':raise PermissionError('This is outside the shared collection')
    if operation=='myradio.catalog':payload={**payload,'category':kind,'archived':False}
    if operation in ('myradio.item','myradio.read','myradio.book-text'):
     item=self.owner_request(grant, 'myradio.item',{'id':payload.get('id')})['item']
     if item['category']!=kind or item.get('hidden'):raise PermissionError('Item is not in this shared library')
   result=self.nas.request('personal.shared',{'owner':grant['owner'],'label':grant['label'],'primary':bool(grant['primary_admin']),'action':operation,'payload':payload,'scope':grant['scope']}) if kind=='photos' else self.owner_request(grant,operation,payload)
   if operation.endswith('.status'):
    result={**result,'config':{'pool':'Shared library','folder':'','location_folder':grant['owner_label'],'location_selected':True},'shared_read_only':True,'shared_owner':grant['owner_label']}
    if operation=='myradio.status':result.update(counts={kind:result['counts'].get(kind,0)},pending=[],uploads=[])
   if operation=='myradio.item':result={**result,'progress':{'position':0}}
   return result
  if user['role']=='administrator':
   if user['primary_admin'] or operation.startswith(('files.','recovery.')) or not is_personal(operation):return self.nas.request(operation,payload)
  elif not needed or not accounts.permitted(user,needed):raise PermissionError('Permission not granted')
  return self.nas.request('personal.invoke',{'owner':user['id'],'label':user['label'],'action':operation,'payload':payload,'assignments':accounts.assignments(self.state,user['id'])})
 def owner_request(self,grant,operation,payload):
  if grant['primary_admin']:return self.nas.request(operation,payload)
  return self.nas.request('personal.invoke',{'owner':grant['owner'],'label':grant['label'],'action':operation,'payload':payload})
 def status(self):
  s=self.session()
  if not s:raise PermissionError('Sign in again')
  user=s['user']
  if user['role']=='administrator':
   result=self.nas.request('nas.status')
   if not user['primary_admin']:
    own=self.nas.request('personal.invoke',{'owner':user['id'],'label':user['label'],'action':'personal.jobs','payload':{}});result['jobs']+=own['jobs']
   return result
  return self.nas.request('personal.invoke',{'owner':user['id'],'label':user['label'],'action':'personal.status','payload':{},'assignments':accounts.assignments(self.state,user['id'])})
 def jobs(self):
  s=self.session();user=s['user']
  if user['role']=='administrator' and user['primary_admin']:return self.nas.request('jobs.list',{})
  return self.nas.request('personal.invoke',{'owner':user['id'],'label':user['label'],'action':'personal.jobs','payload':{}})

 def social(self,action,payload):
  session=self.session()
  if not session or session['user']['must_change']:raise PermissionError('Sign in again')
  user=session['user']
  if not accounts.permitted(user,'social.share'):raise PermissionError('External sharing is not enabled for this account')
  source=payload.get('source',{})
  if source.get('type') not in ('files','photos'):raise ValueError('Choose a photo or video')
  fields={'id':source.get('id'),'variant':'original'} if source['type']=='photos' else {'share':source.get('share'),'path':source.get('path')}
  self.request('photos.read' if source['type']=='photos' else 'files.read',{**fields,'offset':0,'count':1})
  owner=user['id'];primary=bool(user['primary_admin']) or source['type']=='files' and user['role']=='administrator'
  if self.share:
   grant=library_shares.resolve(self.state,user,self.share);owner=grant['owner'];primary=bool(grant['primary_admin'])
  if action=='prepare':return self.nas.request('personal.social-prepare',{'recipient':user['id'],'owner':owner,'primary':primary,'source':source,'assignments':accounts.assignments(self.state,owner)})
  if action not in ('read','discard'):raise ValueError('Invalid sharing operation')
  return self.nas.request('personal.social-'+action,{'recipient':user['id'],'id':payload.get('id'),'offset':payload.get('offset',0),'count':payload.get('count',512*1024),'source':source,'owner':owner,'primary':primary})
