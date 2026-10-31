import tempfile,unittest
from pathlib import Path
from test_nas import Fixture
from freeqnap.nas.dlna import Access
class OptionsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.ctx=Fixture(Path(self.tmp.name));self.access=Access(self.ctx,media_uid=0)
 def test_profiles_never_claim_access_or_transcoding(self):
  self.access.save_options({'default_profile':'roku','transcoding':'direct-play'})
  options=self.access.options();self.assertEqual(options['settings']['default_profile'],'roku');self.assertFalse(options['transcoding']['live_available']);self.assertFalse(options['folder_access']['per_device_dlna'])
  with self.assertRaises(ValueError):self.access.save_options({'default_profile':'roku','transcoding':'video'})
 def test_observed_client_required_and_approval_unchanged(self):
  self.ctx.state.set('dlna_clients',{'fixture':{'approved':False}})
  self.access.client_profile({'id':'fixture','profile':'appletv'})
  self.assertFalse(self.access.data()['fixture']['approved'])
  with self.assertRaises(ValueError):self.access.client_profile({'id':'missing','profile':'generic'})
