import fcntl,json,os,tempfile,time,unittest
from pathlib import Path
from freeqnap.storage_status import observe,read,guard

class StorageStatusTests(unittest.TestCase):
 def test_lock_is_observed_without_waiting_or_changing_its_bytes(self):
  with tempfile.TemporaryDirectory() as tmp:
   lock=Path(tmp)/'operations.lock';lock.write_bytes(b'identity');fd=os.open(lock,os.O_RDONLY)
   try:
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);self.assertTrue(observe(lock)['busy'])
   finally:os.close(fd)
   self.assertFalse(observe(lock)['busy']);self.assertEqual(lock.read_bytes(),b'identity')
 def test_busy_and_unavailable_are_not_submitted_and_unrelated_reads_continue(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'status.json';p.write_text(json.dumps({'busy':True,'sampled_at':time.time()}))
   with self.assertRaisesRegex(ValueError,'Nothing was submitted'):guard('external.import',p)
   guard('external.discover',p)
   p.write_text(json.dumps({'busy':False,'sampled_at':time.time()-121}))
   with self.assertRaisesRegex(ValueError,'could not be checked'):guard('external.mount',p)
   p.write_text(json.dumps({'busy':False,'sampled_at':time.time()}));guard('external.mount',p)
