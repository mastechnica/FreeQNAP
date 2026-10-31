import base64,hashlib,json,os,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from test_nas import Fixture
from freeqnap.nas.system_recovery import SystemRecovery
from freeqnap.nas.local_recovery import LocalRecovery

@unittest.skipUnless(shutil.which('gpg'),'GnuPG required for real encrypted archive checks')
class LocalRecoveryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.ctx=Fixture(self.root);host=self.root/'host';(host/'etc').mkdir(parents=True);(host/'etc/freeqnap-install-id').write_text('fixture-only');(host/'etc/shadow').write_text('private-fixture-password-hash');self.recovery=SystemRecovery(self.ctx,host);self.local=LocalRecovery(self.ctx,self.recovery);self.password='fixture export password never persisted'
 def create(self):return self.local.create({'secret':{'password':self.password}})
 def test_real_encrypt_decrypt_download_and_password_never_persisted(self):
  r=self.create();path,_=self.local.info(r['id']);self.assertEqual(path.stat().st_mode&511,384);raw=path.read_bytes();self.assertNotIn(b'private-fixture-password-hash',raw);self.assertTrue(r['encrypted']);self.assertFalse(r['password_saved']);self.assertFalse(self.recovery.stages()['items']);self.assertNotIn(self.password.encode(),self.ctx.state.database.read_bytes());self.assertEqual(hashlib.sha256(raw).hexdigest(),r['sha256']);self.assertTrue(self.local.list()['items'][0]['available']);self.assertEqual(base64.b64decode(self.local.read({'id':r['id'],'count':512})['data_base64']),raw[:512])
  with path.open('rb') as source,tempfile.TemporaryFile() as output:
   self.local.crypt(source,output,self.password.encode(),True);output.seek(0);manifest=self.local.verify_tar(output);self.assertIn('system/etc/shadow',manifest['files'])
  with path.open('rb') as source,tempfile.TemporaryFile() as output:
   with self.assertRaises(ValueError):self.local.crypt(source,output,b'wrong fixture password',True)
 def test_encryption_failure_does_not_delete_last_good_or_save_password(self):
  good=self.create();path,_=self.local.info(good['id'])
  with patch.object(self.local,'crypt',side_effect=ValueError('fixture encryption failure')):
   with self.assertRaises(ValueError):self.create()
  self.assertTrue(path.exists());self.assertEqual(len(self.local.list()['items']),1);self.assertEqual(len(self.recovery.stages()['items']),1);self.assertNotIn(self.password.encode(),self.ctx.state.database.read_bytes());self.assertEqual(self.ctx.state.jobs()[0]['status'],'retryable')
 def test_archive_replacement_and_unsafe_range_are_refused(self):
  r=self.create();p,_=self.local.info(r['id'])
  for request in ({'id':'../shadow'},{'id':r['id'],'offset':-1},{'id':r['id'],'count':2**30}):
   with self.assertRaises(ValueError):self.local.read(request)
  p.write_bytes(p.read_bytes()+b'changed')
  with self.assertRaisesRegex(ValueError,'changed'):self.local.read({'id':r['id']})
  self.assertFalse(self.local.list()['items'][0]['available'])
 def test_no_saved_password_or_server_key_path_is_accepted(self):
  for request in ({},{'secret':{'path':'/root/key'}},{'secret':{'password':'short'}},{'secret':{'password':self.password},'keep':7}):
   with self.assertRaises(ValueError):self.local.create(request)
  self.assertFalse(self.ctx.state.jobs())
