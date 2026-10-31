import tempfile,unittest,time
from pathlib import Path
from unittest.mock import Mock
from test_nas import Fixture
from freeqnap.nas.health import Health
from freeqnap.nas.alert_rules import AlertRules
class RuleTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.ctx=Fixture(Path(self.tmp.name));Health(self.ctx);self.rules=AlertRules(self.ctx);self.ctx.run=Mock()
 def test_scope_severity_and_channels(self):
  self.rules.save({'rules':[{'scope':'smart','severity':'critical','enabled':True,'smtp':True,'push':False,'buzzer':True}]})
  routes=[('smtp','mail','rev','to'),('push','push','rev','id')]
  self.assertEqual(len(self.rules.routes({'scope':'smart','severity':'critical'},routes)),1)
  self.assertEqual(self.rules.routes({'scope':'raid','severity':'critical'},routes),[])
  self.assertEqual(self.rules.routes({'scope':'smart','severity':'warning'},routes),[])
 def test_buzzer_off_and_mute_persist_without_clearing_alerts(self):
  self.rules.tick();self.ctx.run.assert_not_called()
  self.rules.sound({'action':'enable'});self.rules.sound({'action':'mute','minutes':60});self.rules.tick();self.ctx.run.assert_not_called()
  self.assertTrue(AlertRules(self.ctx).status()['buzzer']['mute_until']>time.time())
  self.rules.sound({'action':'disable'});self.assertFalse(self.rules.status()['buzzer']['enabled'])
