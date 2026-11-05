import base64,json,sqlite3,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from freeqnap.nas.common import Context
from freeqnap.nas.personal_photos import PersonalPhotos,digest
from freeqnap.nas.icloud_albums import sync,attach_available,folders,album_id
from freeqnap.photo_album_access import handle
class Fixture(Context):
 def volume(self,pool):return self.config()['pools'][pool],self.data
class Albums(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.ctx=Fixture(Path(self.tmp.name)/'state');self.ctx.data=Path(self.tmp.name)/'data';self.ctx.data.mkdir();c=self.ctx.config();c['pools']['data']={'name':'data','filesystem_uuid':'fixture','mountpoint':str(self.ctx.data),'read_only':False};self.ctx.save(c);self.photos=PersonalPhotos(self.ctx,extract=lambda fd,t:{},preview=lambda fd,large:b'jpeg');self.photos.configure({'pool':'data','folder':'Photos'})
 def run_sync(self,albums,fail=None):
  def collection(lib,remote,title):
   if remote==fail:raise ValueError('failed album')
   return [SimpleNamespace(id=x) for x in albums[remote][1]]
  return sync(self.photos,'fixture@example.invalid',None,lister=lambda _:((k,v[0])for k,v in albums.items()),make_collection=collection)
 def ingest(self,remote):return self.photos.ingest('fixture:'+remote,'one',remote+'.jpg',lambda start:iter([(remote.encode()+b'photo')[start:]]),len(remote.encode())+5,group='icloud:fixture@example.invalid:personal:'+remote)
 def test_additive_membership_pending_renames_and_duplicate_titles(self):
  a=self.ingest('a');r=self.run_sync({'one':('Holiday',['a','b']),'two':('Holiday',['a'])});self.assertEqual((r['albums'],r['matched'],r['pending']),(2,2,1));self.ingest('b');self.assertEqual(attach_available(self.ctx.state)['pending'],0)
  self.run_sync({'one':('Renamed',[])});
  with self.ctx.state.connect() as db:
   self.assertEqual(db.execute('SELECT count(*) FROM personal_albums').fetchone()[0],2);self.assertEqual(db.execute('SELECT count(*) FROM personal_album_items').fetchone()[0],3);self.assertEqual(db.execute('SELECT title FROM personal_albums WHERE id=?',(album_id('fixture@example.invalid','personal','one'),)).fetchone()[0],'Renamed')
 def test_isolates_failure_and_keeps_archived_photos(self):
  self.ingest('a');r=self.run_sync({'bad':('Broken',['a']),'ok':('Good',['a'])},fail='bad');self.assertEqual(r['failed_albums'],1);self.assertEqual(r['matched'],1)
  with self.ctx.state.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM personal_assets').fetchone()[0],1)
 def test_collision_does_not_relabel_local_album(self):
  ident=album_id('fixture@example.invalid','personal','one')
  with self.ctx.state.connect() as db:db.execute('INSERT INTO personal_albums VALUES(?,?)',(ident,'Manual'))
  self.assertEqual(self.run_sync({'one':('Cloud',[])})['failed_albums'],1)
  with self.ctx.state.connect() as db:self.assertEqual(db.execute('SELECT title FROM personal_albums').fetchone()[0],'Manual')
 def test_distinct_asset_variants_can_share_one_master(self):
  self.ingest('a');records=[SimpleNamespace(id='a',_asset_record={'recordName':'asset-one'}),SimpleNamespace(id='a',_asset_record={'recordName':'asset-two'})]
  r=sync(self.photos,'fixture@example.invalid',None,lister=lambda _:[('one','Album')],make_collection=lambda *args:records)
  self.assertEqual((r['failed_albums'],r['members'],r['references'],r['matched']),(0,1,2,1))
 def test_repeated_asset_record_is_not_accepted_as_a_complete_album(self):
  self.ingest('a');record=SimpleNamespace(id='a',_asset_record={'recordName':'asset-one'})
  r=sync(self.photos,'fixture@example.invalid',None,lister=lambda _:[('one','Album')],make_collection=lambda *args:[record,record])
  self.assertEqual(r['failed_albums'],1);self.assertEqual(r['errors'][0]['kind'],'repeated-member')
 def test_pagination_and_duplicate_album_names(self):
  responses=[{'records':[{'recordName':'one','fields':{'albumNameEnc':{'value':base64.b64encode(b'Holiday').decode()}}}],'continuationMarker':'next'},{'records':[{'recordName':'two','fields':{'albumNameEnc':{'value':base64.b64encode(b'Holiday').decode()}}}]}];sent=[]
  def post(url,**kw):
   sent.append(json.loads(kw['data']));v=responses.pop(0);return SimpleNamespace(raise_for_status=lambda:None,json=lambda:v)
  lib=SimpleNamespace(_fetch_folders=True,service_endpoint='https://fixture.invalid',params={},zone_id={},session=SimpleNamespace(post=post));self.assertEqual(list(folders(lib)),[('one','Holiday'),('two','Holiday')]);self.assertEqual(sent[1]['continuationMarker'],'next')
class FakeState:
 def __init__(self):self.values={}
 def setting(self,key,default):return self.values.get(key,default)
 def set(self,key,value):self.values[key]=value
class Access(unittest.TestCase):
 def setUp(self):
  self.g=SimpleNamespace(share=None,managed=None,state=FakeState(),session=lambda:{'user':{'id':'a'*32,'role':'administrator'}},_request=lambda op,p:{'config':{'location_selected':True}} if op=='photos.status' else {'settings':{'account':'fixture@example.invalid'}})
 def test_default_off_and_scope_from_session(self):
  self.assertFalse(handle(self.g,'photos.icloud-albums-status',{})['config']['enabled'])
  with self.assertRaises(ValueError):handle(self.g,'photos.icloud-albums-sync',{})
  handle(self.g,'photos.icloud-albums-configure',{'enabled':True});self.assertIn('photos-albums-config:'+'a'*32,self.g.state.values);handle(self.g,'photos.icloud-albums-sync',{});self.assertEqual(handle(self.g,'photos.icloud-albums-status',{})['run']['state'],'queued')
  with self.assertRaises(ValueError):handle(self.g,'photos.icloud-albums-sync',{})
 def test_rejects_owner_injection_shared_and_missing_rights(self):
  with self.assertRaises(ValueError):handle(self.g,'photos.icloud-albums-configure',{'enabled':True,'owner':'b'*32})
  self.g.share='x'
  with self.assertRaises(PermissionError):handle(self.g,'photos.icloud-albums-status',{})
  self.g.share=None;self.g.session=lambda:{'user':{'id':'a'*32,'role':'family','permissions':['photos.read']}}
  with self.assertRaises(PermissionError):handle(self.g,'photos.icloud-albums-configure',{'enabled':True})
 def test_requires_selected_archive_and_account(self):
  self.g._request=lambda op,p:{}
  with self.assertRaises(ValueError):handle(self.g,'photos.icloud-albums-configure',{'enabled':True})
