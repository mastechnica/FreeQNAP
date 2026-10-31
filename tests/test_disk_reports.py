import tempfile,unittest,time
from pathlib import Path
from unittest.mock import Mock
from test_nas import Fixture
from freeqnap.nas.disk_reports import DiskReports
class DiskReportTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.ctx=Fixture(Path(self.tmp.name));self.service=DiskReports(self.ctx);self.ctx.run=Mock()
  self.data={'disks':[{'type':'disk','serial':'fixture','path':'/dev/sda','tran':'sata'},{'type':'disk','serial':'usb','path':'/dev/sdb','tran':'usb'}],'smart':[{'device':'/dev/sda','passed':True}],'arrays':[{'sync_action':'recover','degraded':1}]};self.service.inventory=lambda:self.data
 def test_reports_are_saved_and_raid_busy_defers_test(self):
  self.service.save({'serial':'fixture','enabled':True,'short_days':7,'long_days':30});cfg=self.ctx.state.setting('smart_schedules');cfg['fixture']['next_short']=0;self.ctx.state.set('smart_schedules',cfg);self.service.tick();self.ctx.run.assert_not_called();self.assertEqual(len(self.service.history({'serial':'fixture'})['reports']),1);self.assertIn('Deferred',self.service.status()['test_state']['fixture']['status'])
 def test_usb_and_invalid_intervals_rejected(self):
  for body in ({'serial':'usb','enabled':True,'short_days':7,'long_days':30},{'serial':'fixture','enabled':True,'short_days':0,'long_days':30}):
   with self.assertRaises(ValueError):self.service.save(body)
