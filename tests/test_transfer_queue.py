import json,time
from unittest.mock import patch
from test_fileops import FileManagerTests
from freeqnap.access_scope import using

class TransferQueueTests(FileManagerTests):
 def test_accepted_job_survives_long_queue_and_preserves_identity_checks(self):
  (self.a/'song').write_bytes(b'music');actor='user:'+'a'*32
  with using(actor):
   p=self.fm.transfer_plan({'share':'a','paths':['song'],'target_share':'b'});payload=self.review(p);j=self.fm.enqueue_transfer(payload)['job_id'];self.assertEqual(self.ctx.state.claim()['id'],j)
   with patch('time.time',return_value=time.time()+7200):self.fm.transfer(payload,j)
   self.assertEqual((self.b/'song').read_bytes(),b'music')
   with self.assertRaises(ValueError):self.fm.transfer(payload,j)
 def test_expired_plan_is_rejected_before_enqueue(self):
  (self.a/'song').write_bytes(b'music');p=self.fm.transfer_plan({'share':'a','paths':['song'],'target_share':'b'})
  with patch('time.time',return_value=time.time()+7200):
   with self.assertRaisesRegex(ValueError,'expired'):self.fm.enqueue_transfer(self.review(p))
  self.assertFalse(self.ctx.state.jobs())
 def test_changed_source_and_wrong_principal_still_fail_after_wait(self):
  (self.a/'song').write_bytes(b'music');actor='user:'+'a'*32
  with using(actor):
   p=self.fm.transfer_plan({'share':'a','paths':['song'],'target_share':'b'});payload=self.review(p);j=self.fm.enqueue_transfer(payload)['job_id'];self.ctx.state.claim()
  with using('user:'+'b'*32):
   with self.assertRaisesRegex(ValueError,'account'):self.fm.transfer(payload,j)
  (self.a/'song').write_bytes(b'changed')
  with using(actor),patch('time.time',return_value=time.time()+7200):
   with self.assertRaisesRegex(ValueError,'source changed'):self.fm.transfer(payload,j)
  self.assertFalse((self.b/'song').exists())
