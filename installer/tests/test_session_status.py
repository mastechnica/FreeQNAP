import json,tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from session_status import session_status

class SessionStatusTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.save('session.json',{'phase':'inventoried'});self.save('connection.json',{'capture':'private-fixture'})
 def save(self,name,value):(self.root/name).write_text(json.dumps(value))
 def test_unwritten_session_does_not_claim_hardware_acceptance(self):
  before={p.name:p.read_bytes() for p in self.root.iterdir()};out=session_status(self.root)
  self.assertFalse(out['disk_writes']);self.assertFalse(out['flash_writes']);self.assertFalse(out['hardware_rechecked']);self.assertFalse(out['retry_authorized'])
  self.assertEqual(before,{p.name:p.read_bytes() for p in self.root.iterdir()})
 def test_partial_flash_is_visible_and_requires_reconciliation(self):
  self.save('flash-operation.json',{'write_started':True,'readback_verified':False})
  out=session_status(self.root);self.assertTrue(out['flash_writes']);self.assertTrue(out['requires_reconciliation']);self.assertFalse(out['retry_authorized'])
 def test_verified_flash_is_still_reported_as_written(self):
  self.save('flash-operation.json',{'write_started':True,'readback_verified':True});out=session_status(self.root)
  self.assertTrue(out['flash_writes']);self.assertFalse(out['requires_reconciliation']);self.assertTrue(out['journal_only'])
 def test_partial_disk_remains_blocked_even_after_verified_flash(self):
  self.save('flash-operation.json',{'write_started':True,'readback_verified':True});self.save('disk-operation.json',{'disk_writes_started':True,'status':'started'})
  self.assertTrue(session_status(self.root)['requires_reconciliation'])
 def test_malformed_or_incomplete_records_do_not_report_no_writes(self):
  for value in ({}, {'write_started':'false'}, []):
   self.save('flash-operation.json',value)
   with self.assertRaises(ValueError):session_status(self.root)

if __name__=='__main__':unittest.main()
