import tempfile,unittest,time
from pathlib import Path
from unittest.mock import Mock
from test_nas import Fixture
from freeqnap.nas.vpn import VPN
class PeerStatusTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.ctx=Fixture(Path(self.tmp.name));self.v=VPN(self.ctx)
 def test_unconfigured_is_not_a_connection_failure(self):
  self.v.current=lambda:{'client':None,'server':None};r=self.v.peer_status();self.assertIsNone(r['server']);self.assertEqual(r['clients'],[])
 def test_wireguard_recent_handshake_not_claimed_as_persistent_connection(self):
  self.v.current=lambda:{'client':None,'server':{'type':'wireguard','peers':[{'name':'phone','ip':'10.8.0.2','public_key':'fixture'}]}}
  self.ctx.run=lambda *a,**k:'fixture '+str(int(time.time())) if a[-1]=='latest-handshakes' else 'fixture 100 200'
  r=self.v.peer_status();self.assertTrue(r['clients'][0]['connected']);self.assertEqual(r['clients'][0]['state'],'Recently active');self.assertEqual(r['clients'][0]['received'],100)
