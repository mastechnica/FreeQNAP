import contextlib
import fcntl
import json
import os
from pathlib import Path
import threading
from unittest.mock import patch
from test_fileops import FileManagerTests
from freeqnap.nas.fileops import FileManager
from freeqnap.nas.volume_leases import lease,idle

class ResumeTests(FileManagerTests):
 def interrupted(self):
  from freeqnap.access_scope import using
  actor='user:'+'a'*32
  folder=self.a/'folder';folder.mkdir();(folder/'complete.bin').write_bytes(b'a'*12000);(folder/'partial.bin').write_bytes(b'b'*14000);(folder/'new.bin').write_bytes(b'c'*16000)
  with using(actor):
   plan=self.fm.transfer_plan({'share':'a','paths':['folder'],'target_share':'b'});job=self.ctx.state.enqueue('files.transfer',self.review(plan));real=self.fm.copy_node
   def interrupted(source,leaf,target,new_name,*args,**kwargs):
    if leaf=='partial.bin':
     fd=os.open(new_name,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o660,dir_fd=target);os.write(fd,b'b'*7000);os.fsync(fd);os.close(fd);raise OSError('intentional interruption')
    return real(source,leaf,target,new_name,*args,**kwargs)
   listdir=os.listdir
   with patch.object(self.fm,'copy_node',side_effect=interrupted),patch('os.listdir',side_effect=lambda fd:sorted(listdir(fd))):
    with self.assertRaises(OSError):self.fm.transfer(self.review(plan),job)
   self.ctx.state.finish(job,error='intentional interruption')
  record=json.loads((self.ctx.directory/'operations'/(job+'.json')).read_text());stage=self.ctx.mount/'.freeqnap/transfers'/record['partial_stage']
  return actor,job,stage
 def test_resume_reuses_partial_bytes_verifies_and_preserves_sources(self):
  from freeqnap.access_scope import using
  actor,job,stage=self.interrupted();old_inode=(stage/'complete.bin').stat().st_ino
  with using(actor):
   plan=self.fm.transfer_resume_plan({'id':job});new=self.ctx.state.enqueue('files.transfer',self.review(plan));result=self.fm.transfer(self.review(plan),new);self.ctx.state.finish(new,result=result)
  self.assertEqual((self.b/'folder/complete.bin').stat().st_ino,old_inode)
  for name in ('complete.bin','partial.bin','new.bin'):self.assertEqual((self.a/'folder'/name).read_bytes(),(self.b/'folder'/name).read_bytes())
  rec=json.loads((self.ctx.directory/'operations'/(new+'.json')).read_text());self.assertEqual(rec['continued_from'],job);self.assertGreaterEqual(rec['progress']['reused_bytes'],19000);self.assertEqual(rec['progress']['copied_bytes'],42000);self.assertEqual(rec['progress']['verified_bytes'],42000)
  with using(actor):
   with self.assertRaisesRegex(ValueError,'continuation'):self.fm.stage_info(job)
 def test_corrupt_retained_prefix_and_other_owner_are_rejected(self):
  from freeqnap.access_scope import using
  actor,job,stage=self.interrupted();(stage/'partial.bin').write_bytes(b'z'*7000)
  with using('user:'+'b'*32):
   with self.assertRaisesRegex(ValueError,'another account'):self.fm.transfer_resume_plan({'id':job})
  with using(actor):
   plan=self.fm.transfer_resume_plan({'id':job});new=self.ctx.state.enqueue('files.transfer',self.review(plan))
   with self.assertRaisesRegex(ValueError,'differ'):self.fm.transfer(self.review(plan),new)
  self.assertEqual((stage/'partial.bin').read_bytes(),b'z'*7000);self.assertFalse((self.b/'folder').exists());self.assertEqual((self.a/'folder/partial.bin').read_bytes(),b'b'*14000)
 def test_transfer_releases_global_lock_and_protects_only_its_volumes(self):
  (self.a/'file').write_bytes(b'source');plan=self.fm.transfer_plan({'share':'a','paths':['file'],'target_share':'b'});observed=[];real=self.fm.copy_node
  key=self.ctx.config()['pools']['data']['filesystem_uuid']
  def checked(*args,**kwargs):
   fd=os.open(self.ctx.directory/'operations.lock',os.O_RDONLY)
   try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);observed.append(True)
   finally:os.close(fd)
   with self.assertRaisesRegex(ValueError,'active transfer'):idle(self.ctx,[key])
   idle(self.ctx,['unrelated-volume']);return real(*args,**kwargs)
  with patch.object(self.fm,'copy_node',side_effect=checked):self.fm.transfer(self.review(plan))
  self.assertTrue(observed);idle(self.ctx,[key])

 def test_interruption_during_rescan_keeps_a_resumable_checkpoint(self):
  from freeqnap.access_scope import using
  actor,job,stage=self.interrupted()
  with using(actor):
   plan=self.fm.transfer_resume_plan({'id':job});new=self.ctx.state.enqueue('files.transfer',self.review(plan))
   with patch('freeqnap.nas.transfer_progress.Meter',side_effect=OSError('interrupted before rescan')):
    with self.assertRaises(OSError):self.fm.transfer(self.review(plan),new)
   self.ctx.state.finish(new,error='rescan interrupted')
   retry=self.fm.transfer_resume_plan({'id':new});self.assertEqual(retry['body']['resume']['token'],stage.name)
  self.assertTrue((stage/'partial.bin').exists());self.assertTrue((self.a/'folder/partial.bin').exists())
