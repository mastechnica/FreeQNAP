import unittest,json
from unittest.mock import patch
from freeqnap.nas.frontpanel import snapshot
class FrontPanelTests(unittest.TestCase):
 def test_stale_snapshot_never_shows_green(self):
  with patch('pathlib.Path.read_text',return_value=json.dumps({'updated_monotonic':0})),patch('time.monotonic',return_value=10):self.assertFalse(snapshot()['available'])
 def test_green_outputs_follow_readback_and_polarity(self):
  data={'updated_monotonic':10,'ports':[{'bay':i,'disk':'sd'+str(i),'present':True,'recent_activity':False,'kernel_active_low':i!=2} for i in range(1,5)]}
  def read(p):return json.dumps(data) if str(p).endswith('.json') else '1'
  with patch('pathlib.Path.read_text',read),patch('time.monotonic',return_value=11):
   value=snapshot();self.assertTrue(value['available']);self.assertTrue(value['ports'][0]['green']);self.assertFalse(value['ports'][1]['green']);self.assertFalse(value['red_available'])
 def test_missing_network_speed_is_not_invented(self):
  from freeqnap.nas.frontpanel import network_snapshot
  def read(p):
   if str(p).endswith('/carrier'):return '1'
   raise OSError('driver speed unavailable')
  with patch('pathlib.Path.read_text',read):
   result=network_snapshot();self.assertTrue(result['lan1']['up']);self.assertIsNone(result['lan1']['speed_mbps']);self.assertEqual(result['sfp']['interface'],'enp0s0');self.assertEqual(result['lan2']['interface'],'enp0s1');self.assertEqual(result['lan1']['interface'],'enp0s3')
