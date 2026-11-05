"""Add-only iCloud album membership; originals and existing membership never deleted."""
import base64,hashlib,json,re,time,urllib.parse
from .personal_photos import digest,text

def album_id(account,library,remote):return digest('icloud-album\0'+account+'\0'+library+'\0'+remote)[:32]

def schema(state):
 with state.connect() as db:db.executescript('''CREATE TABLE IF NOT EXISTS icloud_album_sources(source TEXT PRIMARY KEY,album TEXT UNIQUE NOT NULL,account TEXT NOT NULL,library TEXT NOT NULL,remote TEXT NOT NULL,last_seen REAL NOT NULL);CREATE TABLE IF NOT EXISTS icloud_album_members(source TEXT NOT NULL,remote_asset TEXT NOT NULL,group_id TEXT NOT NULL,PRIMARY KEY(source,remote_asset));CREATE INDEX IF NOT EXISTS icloud_album_groups ON icloud_album_members(group_id);''')

def attach_available(state):
 schema(state)
 with state.connect() as db:
  db.execute('INSERT OR IGNORE INTO personal_album_items(album,asset) SELECT s.album,a.id FROM icloud_album_members m JOIN icloud_album_sources s ON s.source=m.source JOIN personal_assets a ON a.group_id=m.group_id')
  return {'albums':db.execute('SELECT count(*) FROM icloud_album_sources').fetchone()[0],'matched':db.execute('SELECT count(*) FROM (SELECT DISTINCT m.source,m.group_id FROM icloud_album_members m JOIN personal_assets a ON a.group_id=m.group_id)').fetchone()[0],'pending':db.execute('SELECT count(*) FROM icloud_album_members m WHERE NOT EXISTS (SELECT 1 FROM personal_assets a WHERE a.group_id=m.group_id)').fetchone()[0]}

def folders(library):
 # Preserve stable remote IDs and duplicate names instead of the connector's
 # name-keyed dictionary. Follow CloudKit continuation markers if returned.
 if hasattr(library,'_fetch_folders'):
  url=library.service_endpoint+'/records/query?'+urllib.parse.urlencode(library.params);marker=None;seen=set()
  for _ in range(100):
   body={'query':{'recordType':'CPLAlbumByPositionLive'},'zoneID':library.zone_id}
   if marker:body['continuationMarker']=marker
   response=library.session.post(url,data=json.dumps(body),headers={'Content-type':'text/plain'});response.raise_for_status();value=response.json();records=value.get('records')
   if not isinstance(records,list):raise ValueError('Album listing was not returned')
   for record in records:
    remote=record.get('recordName','');fields=record.get('fields',{})
    if remote in ('----Root-Folder----','----Project-Root-Folder----') or fields.get('isDeleted',{}).get('value'):continue
    encoded=fields.get('albumNameEnc',{}).get('value')
    if not isinstance(remote,str) or not remote or not isinstance(encoded,str):continue
    title=base64.b64decode(encoded,validate=True).decode('utf-8');yield remote,text(title,500)
   next_marker=value.get('continuationMarker')
   if not next_marker:return
   if not isinstance(next_marker,str) or len(next_marker)>10000 or next_marker in seen:raise ValueError('Album continuation changed unexpectedly')
   seen.add(next_marker);marker=next_marker
  raise ValueError('Album listing exceeded the page limit')
 raise ValueError('The installed connector cannot expose stable album identities')

def collection(library,remote,title):
 from pyicloud_ipd.services.photos import PhotoAlbum
 return PhotoAlbum(library.params,library.session,library.service_endpoint,title,'CPLContainerRelationLiveByAssetDate','CPLContainerRelationNotDeletedByAssetDate:'+remote,[{'fieldName':'parentId','comparator':'EQUALS','fieldValue':{'type':'STRING','value':remote}}],zone_id=library.zone_id)

def sync(photos,account,library,lister=folders,make_collection=collection,progress=lambda x:None):
 schema(photos.ctx.state);stats={'listed':0,'members':0,'references':0,'failed_albums':0,'errors':[]};seen=set();account_key=digest(account)
 for remote,title in lister(library):
  if remote in seen:continue
  seen.add(remote);stats['listed']+=1
  if stats['listed']>2000:raise ValueError('Album limit reached')
  ident=album_id(account,'personal',remote);source=digest(account+'\0personal\0'+remote)
  expected=None;remote_seen=set();reference_seen=set()
  try:
   rows=make_collection(library,remote,title);expected=len(rows);remote_seen=set()
   if expected>300000:raise ValueError('Album member limit reached')
   with photos.ctx.state.connect() as db:
    prior=db.execute('SELECT album FROM icloud_album_sources WHERE source=?',(source,)).fetchone()
    if not prior and db.execute('SELECT 1 FROM personal_albums WHERE id=?',(ident,)).fetchone():raise ValueError('Album identity collision')
    db.execute('INSERT INTO personal_albums(id,title) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title',(ident,title))
    db.execute('INSERT INTO icloud_album_sources VALUES(?,?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET last_seen=excluded.last_seen',(source,ident,account_key,'personal',remote,time.time()))
   batch=[]
   for asset in rows:
    remote_asset=getattr(asset,'id',None)
    if not isinstance(remote_asset,str) or not remote_asset or len(remote_asset)>500:raise ValueError('Invalid remote photo identity')
    asset_record=getattr(asset,'_asset_record',{});reference=asset_record.get('recordName') if isinstance(asset_record,dict) else None
    if reference is None:reference=remote_asset
    if not isinstance(reference,str) or not reference or len(reference)>500:raise ValueError('Invalid remote photo identity')
    if reference in reference_seen:raise ValueError('Album membership repeated during listing')
    reference_seen.add(reference);stats['references']+=1
    if len(reference_seen)>300000:raise ValueError('Album member limit reached')
    if remote_asset in remote_seen:continue
    remote_seen.add(remote_asset);batch.append((source,remote_asset,digest('icloud:'+account+':personal:'+remote_asset)))
    if len(remote_seen)>300000:raise ValueError('Album member limit reached')
    if len(batch)>=500:
     with photos.ctx.state.connect() as db:db.executemany('INSERT OR IGNORE INTO icloud_album_members VALUES(?,?,?)',batch)
     stats['members']+=len(batch);batch=[];progress(stats)
   if batch:
    with photos.ctx.state.connect() as db:db.executemany('INSERT OR IGNORE INTO icloud_album_members VALUES(?,?,?)',batch)
    stats['members']+=len(batch)
   if len(reference_seen)!=expected or len(rows)!=expected:raise ValueError('Album changed during listing; retained partial membership')
  except Exception as error:
   stats['failed_albums']+=1
   known={'Album changed during listing; retained partial membership':'changed-during-listing','Album membership repeated during listing':'repeated-member','Invalid remote photo identity':'invalid-member','Album identity collision':'identity-collision','Album member limit reached':'member-limit'}
   stats['errors'].append({'album_id':ident,'kind':known.get(str(error),'connector-read-failed'),'error_type':type(error).__name__,'expected':expected,'read':len(remote_seen)})
  progress(stats)
 return {**stats,**attach_available(photos.ctx.state),'originals_retained':True,'remote_deletion_propagated':False}
