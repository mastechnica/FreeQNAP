import tempfile,unittest
from unittest.mock import patch
from freeqnap.state import State
from freeqnap import radio_listening as listening
from test_radio_catalog import Gateway,item
class ListeningTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.g=Gateway(State(self.t.name));self.g.rows=[item(1,genre='Jazz')];self.clock=100;self.addCleanup(patch.stopall);patch('freeqnap.radio_listening.time.time',lambda:self.clock).start()
 def event(self,event,**kw):return listening.listen(self.g,{'event':event,**kw})
 def test_server_time_counts_play_not_pause_or_seeking(self):
  sid=self.event('start',id='1'.zfill(32),kind='music')['session'];self.event('tick',session=sid,playing=True);self.clock=115;self.event('tick',session=sid,playing=True);self.clock=130;self.event('tick',session=sid,playing=False);self.clock=200;self.event('tick',session=sid,playing=False);self.clock=300;self.event('tick',session=sid,playing=True);self.clock=315;self.event('stop',session=sid)
  r=listening.overview(self.g);self.assertEqual(r['stats']['total_seconds'],45);self.assertEqual(r['stats']['genres'][0]['percent'],100);self.assertEqual(r['recent']['music'][0]['title'],'Track 1')
  self.assertEqual(self.event('stop',session=sid)['seconds'],45)
 def test_missing_heartbeats_are_bounded_and_client_seconds_rejected(self):
  sid=self.event('start',id='1'.zfill(32),kind='music')['session'];self.event('tick',session=sid,playing=True);self.clock=10000;self.assertEqual(self.event('tick',session=sid,playing=True)['seconds'],60)
  with self.assertRaises(ValueError):self.event('tick',session=sid,playing=True,seconds=9999)
 def test_other_listener_cannot_read_or_update_sessions(self):
  sid=self.event('start',id='1'.zfill(32),kind='music')['session'];self.g.owner='b'*32
  with self.assertRaises(PermissionError):self.event('tick',session=sid,playing=True)
  self.assertEqual(listening.overview(self.g)['stats']['sessions'],0)
 def test_revocation_hides_recent_item_and_denies_tracking(self):
  sid=self.event('start',id='1'.zfill(32),kind='music')['session'];self.g.allowed=False
  with self.assertRaises(PermissionError):self.event('tick',session=sid,playing=True)
  with self.assertRaises(PermissionError):listening.overview(self.g)
 def test_new_accounts_have_no_invented_history(self):
  r=listening.overview(self.g);self.assertEqual(r['stats']['total_seconds'],0);self.assertIsNone(r['stats']['tracking_since']);self.assertEqual(r['recent']['music'],[])
