"""Session-scoped requests for the album-only iCloud companion."""
import secrets,time
from . import accounts

def handle(g,operation,r):
 if g.share:raise PermissionError('Shared albums are read-only')
 status=g._request('photos.status',{})
 owner=g.managed or g.session()['user']['id'];key='photos-albums-config:'+owner
 cfg=g.state.setting(key,{'enabled':False,'interval_hours':6})
 if operation!='photos.icloud-albums-status':
  user=g.session()['user']
  if not accounts.permitted(user,'photos.write') or not accounts.permitted(user,'photos.icloud'):raise PermissionError('Photo and iCloud management are required')
 if operation!='photos.icloud-albums-status' and not (operation=='photos.icloud-albums-configure' and r.get('enabled') is False):
  if not status.get('config',{}).get('location_selected'):raise ValueError('Choose your photo archive folder in Settings first')
  if not g._request('photos.icloud-status',{}).get('settings',{}).get('account'):raise ValueError('Save your iCloud account in Import & iCloud first')
 if operation=='photos.icloud-albums-configure':
  if set(r)-{'enabled','interval_hours'} or type(r.get('enabled'))is not bool or type(r.get('interval_hours',6))is not int or not 1<=r.get('interval_hours',6)<=24:raise ValueError('Choose album import settings')
  cfg={'enabled':r['enabled'],'interval_hours':r.get('interval_hours',6)};g.state.set(key,cfg)
 elif operation=='photos.icloud-albums-sync':
  if r:raise ValueError('No album-sync fields are required')
  if not cfg['enabled']:raise ValueError('Enable iCloud album import first')
  run=g.state.setting('photos-albums-status:'+owner,{})
  if run.get('state') in ('queued','running'):raise ValueError('Album import is already queued or running')
  g.state.set('photos-albums-request:'+owner,{'id':secrets.token_hex(16),'requested':time.time()});g.state.set('photos-albums-status:'+owner,{**run,'state':'queued','message':'Album import queued. Existing photos and albums are retained.'})
 elif operation!='photos.icloud-albums-status':raise ValueError('Unknown album operation')
 return {'config':cfg,'run':g.state.setting('photos-albums-status:'+owner,{}),'retention':'add-only','download_required_for_membership':True}
