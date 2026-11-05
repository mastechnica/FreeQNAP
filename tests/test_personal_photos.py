import base64,hashlib,json,os,tempfile,unittest
from pathlib import Path
from freeqnap.nas.common import Context
from freeqnap.nas.personal_photos import PersonalPhotos,digest
from freeqnap.nas.personal_metadata import metadata

class Fixture(Context):
 def volume(self,pool):
  p=self.config()['pools'][pool]
  if p['filesystem_uuid']!='fixture-uuid':raise ValueError('Wrong mounted identity')
  return p,Path(p['mountpoint'])
class PhotosTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.data=self.root/'data';self.data.mkdir();self.ctx=Fixture(self.root/'state');cfg=self.ctx.config();cfg['pools']['data']={'name':'data','filesystem_uuid':'fixture-uuid','mountpoint':str(self.data),'read_only':False};self.ctx.save(cfg)
  self.photos=PersonalPhotos(self.ctx,extract=lambda fd,t:{'taken':'2024-06-10T12:00:00','latitude':45.,'longitude':-73.,'camera':'Test camera'},preview=lambda fd,large:b'\xff\xd8fixture-jpeg');self.photos.configure({'pool':'data','folder':'Photos'});self.archive=self.data/self.photos.config()['folder']
 def test_download_file_progress_preserves_inventory_and_clears_stale_bytes(self):
  self.photos.progress(state='downloading',seen=2,completed=3,failed=0,expected_items=100)
  self.photos.progress(state='downloading',file='sample.jpg',bytes=4,total_bytes=10)
  p=self.ctx.state.setting('personal-photo-progress',{});self.assertEqual(p['expected_items'],100);self.assertEqual(p['completed'],3);self.assertEqual(p['bytes'],4)
  self.photos.progress(state='downloading',seen=3,completed=4,failed=0,expected_items=100)
  self.assertNotIn('bytes',self.ctx.state.setting('personal-photo-progress',{}))
  self.photos.progress(state='scanning');self.assertNotIn('expected_items',self.ctx.state.setting('personal-photo-progress',{}))
 def put(self,data=b'fixture-photo',source='icloud:id',revision='one',filename='IMG_0001.JPG'):
  return self.photos.ingest(source,revision,filename,lambda start:iter([data[start:]]) if start<len(data) else iter([]),len(data),group='fixture-live')
 def test_corrected_previews_ignore_legacy_partial_tile_cache(self):
  a=self.put();previews=self.archive/'previews';previews.mkdir();(previews/(a['id']+'-thumbnail.jpg')).write_bytes(b'legacy partial tile')
  result=self.photos.read({'id':a['id'],'variant':'thumbnail'});self.assertEqual(base64.b64decode(result['data_base64']),b'\xff\xd8fixture-jpeg');self.assertTrue(result['etag'].endswith('-v2'));self.assertEqual((previews/(a['id']+'-thumbnail.jpg')).read_bytes(),b'legacy partial tile')

 def test_existing_photo_reads_do_not_wait_for_network_ingestion(self):
  import concurrent.futures,threading
  a=self.put();started=threading.Event();release=threading.Event()
  def slow(start):
   started.set();release.wait(5);yield b'new-photo'[start:]
  with concurrent.futures.ThreadPoolExecutor(2) as pool:
   ingest=pool.submit(self.photos.ingest,'slow','one','new.jpg',slow,9)
   try:
    self.assertTrue(started.wait(2));read=pool.submit(self.photos.read,{'id':a['id'],'variant':'thumbnail'});self.assertTrue(base64.b64decode(read.result(timeout=2)['data_base64']).startswith(b'\xff\xd8'))
   finally:release.set()
   ingest.result(timeout=3)
 def test_concurrent_preview_requests_decode_once_and_publish_complete_cache(self):
  import concurrent.futures,threading
  a=self.put();entered=threading.Event();release=threading.Event();calls=[]
  def preview(fd,large):calls.append(large);entered.set();release.wait(5);return b'\xff\xd8complete-jpeg'
  self.photos.preview=preview
  with concurrent.futures.ThreadPoolExecutor(2) as pool:
   first=pool.submit(self.photos.read,{'id':a['id'],'variant':'preview'})
   try:
    self.assertTrue(entered.wait(2));second=pool.submit(self.photos.read,{'id':a['id'],'variant':'preview'})
   finally:release.set()
   self.assertEqual(first.result(timeout=3),second.result(timeout=3));self.assertEqual(calls,[True])

 def test_retains_original_after_remote_deletion_and_duplicate_runs(self):
  first=self.put();self.assertFalse(first['already_present']);self.assertTrue(self.put()['already_present'])
  # A later empty remote inventory has no deletion operation to invoke.
  self.assertEqual(self.photos.catalog({})['total'],1)
  self.assertEqual(base64.b64decode(self.photos.read({'id':first['id']})['data_base64']),b'fixture-photo')
 def test_new_remote_version_keeps_both_originals(self):
  a=self.put();b=self.put(b'edited-photo',revision='two');self.assertNotEqual(a['id'],b['id']);self.assertEqual(self.photos.catalog({'include_versions':True})['total'],2)
  self.assertEqual(base64.b64decode(self.photos.read({'id':a['id']})['data_base64']),b'fixture-photo')
 def test_failed_download_resumes_from_durable_partial(self):
  def broken(start):yield b'first';raise OSError('network failed')
  with self.assertRaises(OSError):self.photos.ingest('cloud','rev','x.jpg',broken,10)
  offsets=[]
  def resumed(start):offsets.append(start);yield b'last!'
  item=self.photos.ingest('cloud','rev','x.jpg',resumed,10);self.assertEqual(offsets,[5]);self.assertEqual(base64.b64decode(self.photos.read({'id':item['id']})['data_base64']),b'firstlast!')
 def test_same_name_different_files_do_not_overwrite(self):
  a=self.put(source='one');b=self.put(b'other-photo',source='two');self.assertNotEqual(a['id'],b['id']);self.assertEqual(self.photos.status()['files'],2)
 def test_identical_content_is_deduplicated(self):
  a=self.put(source='one');b=self.put(source='two');self.assertEqual(a['id'],b['id']);self.assertTrue(b['already_present'])
 def test_annotations_and_album_do_not_change_original(self):
  a=self.put();self.photos.annotate({'id':a['id'],'favorite':True,'caption':'My memory'});album=self.photos.album({'title':'Family'});self.photos.album_add({'id':a['id'],'album':album['id']});self.assertEqual(self.photos.catalog({'favorite':True,'album':album['id']})['total'],1);self.assertEqual(hashlib.sha256(base64.b64decode(self.photos.read({'id':a['id']})['data_base64'])).hexdigest(),a['id'])
 def test_original_change_is_refused(self):
  a=self.put();item=self.photos.asset(a['id']);p=self.archive/item['path'];p.chmod(0o600);p.write_bytes(b'different')
  with self.assertRaises(ValueError):self.photos.read({'id':a['id']})
 def test_cache_and_path_validation(self):
  a=self.put();r=self.photos.read({'id':a['id'],'variant':'thumbnail'});self.assertTrue(base64.b64decode(r['data_base64']).startswith(b'\xff\xd8'))
  for bad in ('../../secret','a'*63):
   with self.assertRaises(ValueError):self.photos.read({'id':bad})
 def test_wrong_volume_and_marker_refused(self):
  marker=self.archive/'.freeqnap-photo-library.json';marker.write_text('{}')
  with self.assertRaises(ValueError):self.put()
 def test_existing_nonempty_archive_folder_refused(self):
  other=PersonalPhotos(Fixture(self.root/'other-state'));cfg=other.ctx.config();cfg['pools']=self.ctx.config()['pools'];other.ctx.save(cfg)
  with self.assertRaises(ValueError):other.configure({'pool':'data','folder':'Photos'})
 def test_gps_and_date_validation(self):
  self.assertNotIn('latitude',metadata({'GPSLatitude':float('nan'),'GPSLongitude':1}))
  self.assertNotIn('latitude',metadata({'GPSLatitude':100,'GPSLongitude':1}))
  self.assertEqual(metadata({'DateTimeOriginal':'2024:06:10 10:11:12'})['taken'],'2024-06-10T10:11:12')
 def test_no_raw_commands_or_deletion_interface(self):
  self.assertFalse(hasattr(self.photos,'delete'));self.assertFalse(hasattr(self.photos,'prune'))
  with self.assertRaises(ValueError):self.put(filename='x.exe')

 def test_metadata_gps_and_capture_date_update_map_without_changing_original(self):
  from unittest.mock import patch
  item=self.put();before=base64.b64decode(self.photos.read({'id':item['id']})['data_base64'])
  with patch('freeqnap.nas.file_metadata.inspect',return_value={}):
   value=self.photos.metadata_read({'id':item['id']});plan=self.photos.metadata_plan({'id':item['id'],'etag':value['etag'],'metadata':{**value['metadata'],'latitude':40.5,'longitude':-75.5,'taken':'1990-06-01T10:00:00','description':'Added location'}});self.photos.metadata_apply({'plan_id':plan['id'],'digest':plan['digest'],'confirmation':plan['confirmation']})
  row=self.photos.catalog({'id':item['id']})['items'][0];self.assertEqual(row['latitude'],40.5);self.assertTrue(row['taken'].startswith('1990-06-01'));self.assertEqual(row['caption'],'Added location');self.assertEqual(self.photos.places({})['total'],1);self.assertEqual(base64.b64decode(self.photos.read({'id':item['id']})['data_base64']),before)

class CloudTests(PhotosTests):
 def setUp(self):
  super().setUp()
  from freeqnap.nas.personal_cloud import PersonalCloud
  self.cloud=PersonalCloud(self.photos,factory=lambda account,password,cookies:None)
  self.cloud.save({'account':'fixture@example.invalid','enabled':False})
 def test_password_never_enters_saved_settings(self):
  self.assertFalse(self.cloud.status()['password_saved']);self.assertNotIn('password',self.cloud.settings());self.assertFalse(self.cloud.status()['deletion_available'])
 def test_malformed_asset_does_not_block_later_assets(self):
  from types import SimpleNamespace as NS
  class Response:
   status_code=200;headers={}
   def iter_content(self,n):yield b'cloud-fixture'
   def close(self):pass
  version=NS(checksum='fixture-revision',size=13,type='public.jpeg',url='https://example.invalid/not-requested')
  class Good:
   id='good';filename='good.jpg';created=None
   @property
   def versions(self):return {NSKey():version}
   def download(self,*args):return Response()
  class Broken:
   @property
   def versions(self):raise RuntimeError('Malformed item')
  class NSKey:
   value='original'
  self.cloud.client=NS(photos=NS(all=[Broken(),Good()]),session=object());self.cloud.auth_state='connected';self.photos.busy.acquire();self.cloud._download()
  self.assertEqual(self.photos.status()['files'],1);self.assertEqual(self.cloud.status()['last_run']['failed'],1)
  # A later empty cloud library must retain the archived original.
  self.cloud.client.photos.all=[];self.photos.busy.acquire();self.cloud._download();self.assertEqual(self.photos.status()['files'],1)
 def test_incomplete_inventory_is_not_healthy(self):
  from types import SimpleNamespace as NS
  class BrokenCollection:
   def __iter__(self):raise RuntimeError('Network unavailable')
  self.cloud.client=NS(photos=NS(all=BrokenCollection()));self.cloud.auth_state='connected';self.cloud.save({'enabled':True});self.photos.busy.acquire();self.cloud._download()
  self.assertFalse(self.cloud.status()['last_run']['inventory_complete']);self.assertTrue(any(i['source']=='personal-photos:inventory' for i in self.cloud.health()))

 def test_failure_diagnostic_uses_fixed_vocabulary_without_exception_contents(self):
  self.cloud.auth_state='checking-photo-access';self.cloud.fail(KeyError('private-token-do-not-save'),'photo-access')
  problem=self.cloud.status()['connection_problem'];self.assertEqual(problem['error_kind'],'KeyError');self.assertEqual(problem['step'],'checking-photo-access');self.assertNotIn('private-token-do-not-save',str(problem))

 def test_apple_terms_and_account_repair_stop_before_web_approval(self):
  for flag,code in [('termsUpdateNeeded','apple-terms-required'),('isRepairNeeded','apple-account-action-required')]:
   client=self.verified_client(data={flag:True});client.request_pcs_consent=lambda app:(_ for _ in ()).throw(AssertionError('No consent request before owner action'))
   self.cloud.client=client;self.cloud.save({'adp':True});self.cloud.auth_lock.acquire();self.cloud._code('123456')
   self.assertEqual(self.cloud.status()['authentication'],'account-action-required');self.assertEqual(self.cloud.status()['connection_problem']['code'],code);self.assertFalse(self.cloud.status()['can_download']);self.assertFalse(self.cloud.auth_lock.locked())

 def verified_client(self,**extra):
  from types import SimpleNamespace as NS
  return NS(photos=NS(all=[]),requires_2fa=False,requires_2sa=False,validate_2fa_code=lambda code:True,trust_session=lambda:(_ for _ in ()).throw(AssertionError('duplicate trust call')),request_pcs_consent=lambda app:None,**extra)
 def test_verified_code_checks_photo_access_without_double_trust(self):
  self.cloud.client=self.verified_client();self.cloud.auth_state='verification-code-needed';self.cloud.auth_lock.acquire();self.cloud._code('123456');self.assertEqual(self.cloud.auth_state,'connected');self.assertTrue(self.cloud.status()['can_download'])
 def test_adp_approval_timeout_preserves_session_and_explains_next_step(self):
  self.cloud.save({'adp':True});client=self.verified_client();client.request_pcs_consent=lambda app:(_ for _ in ()).throw(ValueError('Timed out waiting for the iCloud web access approval'));self.cloud.client=client;self.cloud.auth_lock.acquire();self.cloud._code('123456')
  self.assertEqual(self.cloud.auth_state,'photo-access-needed');self.assertIs(self.cloud.client,client);self.assertEqual(self.cloud.status()['connection_problem']['code'],'approval-timed-out');self.assertFalse(self.cloud.status()['can_download'])
  client.request_pcs_consent=lambda app:None;self.cloud.restore(force=True);self.assertEqual(self.cloud.auth_state,'connected')
 def test_photo_permission_failure_does_not_claim_connected(self):
  from types import SimpleNamespace as NS
  class NoAccess:
   @property
   def all(self):raise ValueError('CloudKit ACCESS_DENIED private-token-do-not-save')
  self.cloud.client=self.verified_client();self.cloud.client.photos=NoAccess();self.cloud.auth_lock.acquire();self.cloud._code('123456');self.assertEqual(self.cloud.auth_state,'photo-access-needed');self.assertNotIn('private-token-do-not-save',str(self.cloud.status()))
 def test_bad_code_can_be_retried_and_is_not_reported_connected(self):
  self.cloud.client=self.verified_client();self.cloud.client.validate_2fa_code=lambda code:False;self.cloud.auth_lock.acquire();self.cloud._code('123456');self.assertEqual(self.cloud.auth_state,'verification-code-needed');self.assertEqual(self.cloud.status()['connection_problem']['code'],'invalid-code')
 def test_start_download_has_immediate_persistent_progress(self):
  from unittest.mock import patch
  self.cloud.client=self.verified_client();self.cloud.auth_state='connected'
  with patch('freeqnap.nas.personal_cloud.threading.Thread'):
   self.assertTrue(self.cloud.run()['started']);self.assertEqual(self.photos.status()['operation']['state'],'starting-icloud');self.assertTrue(self.cloud.status()['download_running'])
  self.photos.busy.release()
 def test_failed_connection_does_not_queue_a_download(self):
  with self.assertRaises(ValueError):self.cloud.run()
  self.assertFalse(self.photos.busy.locked());self.assertEqual(self.photos.status()['operation']['state'],'idle')
 def test_restore_does_not_overwrite_an_authentication_in_progress(self):
  self.cloud.auth_lock.acquire();self.cloud.auth_state='verifying-code';self.cloud.restore();self.assertEqual(self.cloud.auth_state,'verifying-code');self.cloud.auth_lock.release()

 def test_start_failure_releases_photo_busy_and_remains_retryable(self):
  from unittest.mock import patch
  self.cloud.client=self.verified_client();self.cloud.auth_state='connected'
  with patch.object(self.photos,'root',side_effect=ValueError('volume offline')):
   with self.assertRaises(ValueError):self.cloud.run()
  self.assertFalse(self.photos.busy.locked());self.assertEqual(self.photos.status()['operation']['state'],'needs-attention')
 def test_failed_authentication_worker_start_does_not_strand_lock(self):
  from unittest.mock import patch
  with patch('freeqnap.nas.personal_cloud.threading.Thread',side_effect=RuntimeError('worker unavailable')):
   with self.assertRaises(RuntimeError):self.cloud.check()
  self.assertFalse(self.cloud.auth_lock.locked())

class PrivacyAndMapTests(PhotosTests):
 def test_general_file_api_cannot_enter_private_library(self):
  from freeqnap.nas.files import Files
  with self.assertRaises(ValueError):
   with Files(self.ctx).directory('pool:data',self.photos.config()['folder']):pass
 def test_map_aggregates_every_located_file_and_drills_into_bounds(self):
  a=self.put();self.put(b'other-photo',source='two');places=self.photos.places({});self.assertEqual(places['total'],2);self.assertEqual(sum(p['count'] for p in places['items']),2)
  p=places['items'][0];self.assertTrue(self.photos.catalog({k:p[k] for k in ('west','east','south','north')})['total'])
  with self.assertRaises(ValueError):self.photos.places({'cell':0})
  with self.assertRaises(ValueError):self.photos.places({'west':float('nan')})
 def test_exact_lookup_and_read_offset_bounds(self):
  a=self.put();self.assertEqual(self.photos.catalog({'id':a['id']})['items'][0]['id'],a['id'])
  with self.assertRaises(ValueError):self.photos.read({'id':a['id'],'offset':2**100})

class CrashCheckpointTests(PhotosTests):
 def test_unclean_tail_is_not_trusted_as_downloaded_data(self):
  def killed(offset):yield b'wrong';raise SystemExit('simulated process exit')
  with self.assertRaises(SystemExit):self.photos.ingest('crash','rev','x.jpg',killed,10)
  offsets=[]
  def retry(offset):offsets.append(offset);yield b'correct!!!'
  result=self.photos.ingest('crash','rev','x.jpg',retry,10)
  self.assertEqual(offsets,[0]);self.assertEqual(base64.b64decode(self.photos.read({'id':result['id']})['data_base64']),b'correct!!!')
  self.assertTrue(list((self.archive/'incoming').glob('*unverified*')))
 def test_changed_verified_prefix_is_retained_and_refused(self):
  def broken(offset):yield b'first';raise OSError('network failure')
  with self.assertRaises(OSError):self.photos.ingest('crash','rev','x.jpg',broken,10)
  part=next((self.archive/'incoming').glob('part-*'));part.write_bytes(b'wrong')
  with self.assertRaisesRegex(ValueError,'prefix verification'):self.photos.ingest('crash','rev','x.jpg',lambda o:iter([b'last!']),10)
  self.assertEqual(self.photos.status()['files'],0)
