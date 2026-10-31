import unittest
from unittest.mock import Mock
from freeqnap.nas.status_light import StatusLight,health_mode
class StatusLightTests(unittest.TestCase):
 def test_modes(self):
  self.assertEqual(health_mode({'active_counts':{'critical':1},'active_total':1}),'red')
  self.assertEqual(health_mode({'active_total':1}),'both');self.assertEqual(health_mode({'active_total':0}),'green');self.assertEqual(health_mode({'monitor_stale':True}),'both')
 def test_only_changes_write_and_failed_writes_retry(self):
  c=Mock();s=StatusLight(c);s.update({'active_total':0});s.update({'active_total':0});self.assertEqual(c.run.call_count,1)
  c.run.side_effect=ValueError('busy')
  with self.assertRaises(ValueError):s.update({'active_counts':{'critical':1}})
  self.assertEqual(s.last,'green')
  c.run.side_effect=None;s.update({'active_counts':{'critical':1}});self.assertEqual(s.last,'red')
