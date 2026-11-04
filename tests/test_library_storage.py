import base64,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from freeqnap.nas.common import Context
from freeqnap.nas.myradio import MyRadio
from freeqnap.nas.personal_photos import PersonalPhotos
from freeqnap.nas.library_storage import LibraryStorage

class Fixture(Context):
 def volume(self,key):
  value=self.config()['pools'][key];return value,Path(value['mountpoint'])

class LibraryStorageTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.ctx=Fixture(self.root/'state');cfg=self.ctx.config()
  for key in ('first','second'):
   path=self.root/key;path.mkdir();cfg['pools'][key]={'name':key,'mountpoint':str(path),'filesystem_uuid':'uuid-'+key,'read_only':False}
  self.ctx.save(cfg);self.radio=MyRadio(self.ctx);self.photos=PersonalPhotos(self.ctx,extract=lambda fd,t:{},preview=lambda fd,large:b'jpeg');self.storage=LibraryStorage(self.ctx,self.radio,self.photos)
 def apply(self,plan):return self.storage.apply({'plan_id':plan['id'],'digest':plan['digest'],'confirmation':plan['confirmation']})
 def choose(self,kind='radio',pool='first',folder='Media/My Radio'):return self.apply(self.storage.plan({'library':kind,'pool':pool,'folder':folder}))
 def upload(self):
  from test_myradio import rename
  v=self.radio.upload_begin({'category':'books','name':'book.txt','bytes':5});self.radio.upload_chunk({'upload_id':v['upload_id'],'offset':0,'data_base64':'aGVsbG8='})
  with patch('freeqnap.nas.myradio.rename_exclusive',rename):return self.radio.upload_finish({'upload_id':v['upload_id']})['item']
 def test_first_setup_and_cross_volume_relocation_keep_data_and_old_archive(self):
  self.choose();item=self.upload();old=self.radio.config();oldfile=self.root/'first'/old['folder']/self.radio.asset(item['id'])['path'];self.choose(pool='second',folder='Music')
  self.assertEqual(self.radio.book_text({'id':item['id']})['text'],'hello');self.assertEqual(oldfile.read_bytes(),b'hello');self.assertTrue(self.radio.config()['location_selected']);self.assertEqual(len(self.radio.config()['previous_locations']),1)
  self.radio.configure({'pool':'second','scan_enabled':False});self.assertEqual(self.radio.config()['location_folder'],'Music');self.assertEqual(self.radio.book_text({'id':item['id']})['text'],'hello')
 def test_photo_relocation_refreshes_exact_original_identity_and_keeps_old_copy(self):
  self.choose('photos',folder='Memories');v=self.photos.ingest('test','one','pic.jpg',lambda offset:iter([b'photo'[offset:]]),5);old=self.photos.config();self.choose('photos','second','Family/Photos')
  self.assertEqual(base64.b64decode(self.photos.read({'id':v['id']})['data_base64']),b'photo');self.assertTrue((self.root/'first'/old['folder']/self.photos.asset(v['id'])['path']).exists())
 def test_invalid_paths_existing_archive_symlink_and_changed_volume_refused(self):
  for folder in ('','/root','../escape','.freeqnap-hidden'):
   with self.assertRaises(ValueError):self.storage.plan({'library':'radio','pool':'first','folder':folder})
  (self.root/'first'/'linked').symlink_to(self.root/'second')
  with self.assertRaises(OSError):self.choose(folder='linked')
  self.choose(folder='Music');plan=self.storage.plan({'library':'radio','pool':'second','folder':'New'});cfg=self.ctx.config();cfg['pools']['second']['filesystem_uuid']='changed';self.ctx.save(cfg)
  with self.assertRaises(ValueError):self.apply(plan)
  with self.assertRaises(ValueError):self.choose(folder='Music/.freeqnap-myradio')
 def test_failed_copy_and_consumed_plan_keep_old_binding(self):
  self.choose();self.upload();old=self.radio.config();plan=self.storage.plan({'library':'radio','pool':'second','folder':'Music'})
  with patch.object(self.storage,'copy',side_effect=OSError('test interrupted copy')):
   with self.assertRaises(OSError):self.apply(plan)
  self.assertEqual(self.radio.config(),old)
  with self.assertRaises(ValueError):self.apply(plan)
  with self.assertRaises(ValueError):self.choose(pool='second',folder='Music')
 def test_changed_original_is_not_silently_trusted_on_move(self):
  self.choose();v=self.upload();item=self.radio.asset(v['id']);(self.root/'first'/self.radio.config()['folder']/item['path']).write_bytes(b'other')
  with self.assertRaises(ValueError):self.choose(pool='second',folder='Music')
  self.assertEqual(self.radio.config()['pool'],'first')
 def test_copy_import_from_readonly_registered_usb_leaves_source_unchanged(self):
  from test_myradio import rename
  self.choose();cfg=self.ctx.config();cfg['pools']['second']['read_only']=True;cfg['pools']['second']['kind']='usb';self.ctx.save(cfg);(self.root/'second'/'book.txt').write_text('USB book')
  with patch('freeqnap.nas.myradio.rename_exclusive',rename):v=self.radio.import_folder({'category':'books','share':'pool:second','path':''})
  self.assertEqual(v['imported'],1);self.assertEqual((self.root/'second'/'book.txt').read_text(),'USB book');self.assertEqual(self.radio.catalog({'category':'books'})['total'],1)
 def test_photo_import_from_readonly_usb_and_unconfigured_fail_before_job(self):
  with self.assertRaises(ValueError):self.photos.import_folder({'pool':'second','folder':''})
  self.choose('photos',folder='Memories');cfg=self.ctx.config();cfg['pools']['second']['read_only']=True;self.ctx.save(cfg);(self.root/'second'/'photo.jpg').write_bytes(b'photo');self.photos.busy.acquire();self.photos._import('second','')
  self.assertEqual(self.photos.catalog({})['total'],1);self.assertEqual((self.root/'second'/'photo.jpg').read_bytes(),b'photo')

 def test_library_owner_survives_relocation_and_parent_file_moves_are_blocked(self):
  from freeqnap.nas.files import Files
  from freeqnap.nas.fileops import FileManager
  self.choose();owner=self.radio.config()['owner_id'];self.assertEqual(owner,self.storage.owner['id'])
  for folder in ('Media','Media/My Radio'):
   with self.assertRaises(ValueError):Files(self.ctx).move_plan({'share':'pool:first','path':folder,'new_name':'Other'})
  self.choose(pool='second',folder='Music');self.assertEqual(self.radio.config()['owner_id'],owner)
  with self.assertRaises(ValueError):Files(self.ctx).move_plan({'share':'pool:first','path':'Media','new_name':'Other'})
  (self.root/'second'/'Other').mkdir()
  with self.assertRaises(ValueError):FileManager(self.ctx).transfer_plan({'share':'pool:second','paths':['Music'],'target_share':'pool:second','target_path':'Other','mode':'move'})
