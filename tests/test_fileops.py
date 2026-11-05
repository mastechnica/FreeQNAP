import contextlib
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from test_nas import Fixture
from freeqnap.nas.fileops import FileManager
from freeqnap.nas.files import rename_exclusive
from freeqnap.nas.recovery import Recovery

class FileManagerTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.ctx=Fixture(self.root);self.fm=FileManager(self.ctx)
  self.a=self.ctx.mount/'a';self.b=self.ctx.mount/'b';self.a.mkdir();self.b.mkdir();cfg=self.ctx.config()
  for n in ['a','b']:cfg['shares'][n]={'name':n,'pool':'data','path':str(self.ctx.mount/n),'gid':os.getgid()}
  self.ctx.save(cfg)
  # macOS does not implement Linux renameat2; native Linux runs the real primitive.
  if sys.platform!='linux':
   def fixture_rename(sfd,s,tfd,t):
    try:os.stat(t,dir_fd=tfd,follow_symlinks=False)
    except FileNotFoundError:pass
    else:raise FileExistsError(t)
    os.rename(s,t,src_dir_fd=sfd,dst_dir_fd=tfd)
   for module in ['freeqnap.nas.files','freeqnap.nas.fileops','freeqnap.nas.recovery']:
    p=patch(module+'.rename_exclusive',side_effect=fixture_rename);p.start();self.addCleanup(p.stop)
  if os.geteuid()!=0:
   p=patch('os.fchown');p.start();self.addCleanup(p.stop)
 def review(self,plan):return {'plan_id':plan['id'],'digest':plan['digest'],'confirmation':plan['confirmation']}
 def trash(self,path='file.txt'):
  plan=self.fm.move_plan({'share':'a','path':path});self.fm.move(self.review(plan));return plan['id']
 def test_folder_creation_never_requests_special_permission_bits(self):
  (self.a/'folder').mkdir();(self.a/'folder/file').write_text('data');real=os.mkdir;modes=[]
  def mkdir(path,mode=0o777,*args,**kwargs):
   modes.append(mode)
   if mode&0o6000:raise PermissionError('Special directory bits blocked')
   return real(path,mode,*args,**kwargs)
  with patch('os.mkdir',side_effect=mkdir):
   self.fm.mkdir({'share':'b','name':'new'});p=self.fm.transfer_plan({'share':'a','paths':['folder'],'target_share':'b'});self.fm.transfer(self.review(p))
  self.assertTrue(modes);self.assertTrue(all(not mode&0o6000 for mode in modes));self.assertEqual((self.b/'folder/file').read_text(),'data')
 def test_transfer_progress_is_private_and_counts_copy_and_verification(self):
  from freeqnap.access_scope import using
  actor='user:'+'a'*32;other='user:'+'b'*32;(self.a/'data').write_bytes(b'x'*12345)
  with using(actor):
   p=self.fm.transfer_plan({'share':'a','paths':['data'],'target_share':'b'});job=self.ctx.state.enqueue('files.transfer',self.review(p));r=self.fm.transfer(self.review(p),job);self.ctx.state.finish(job,result=r);progress=self.fm.transfers()['transfers'][0]['progress']
   self.assertEqual(progress['copied_bytes'],12345);self.assertEqual(progress['verified_bytes'],12345);self.assertEqual(progress['files_completed'],1);self.assertEqual(progress['percent'],100)
  with using(other):self.assertFalse(self.fm.transfers()['transfers'])
 def test_failed_copy_can_only_start_again_with_a_fresh_review(self):
  from freeqnap.access_scope import using
  (self.a/'data').write_text('safe source')
  with using('user:'+'a'*32):
   p=self.fm.transfer_plan({'share':'a','paths':['data'],'target_share':'b'});job=self.ctx.state.enqueue('files.transfer',self.review(p));self.ctx.state.finish(job,error='test failure')
   new=self.fm.transfer_retry_plan({'id':job});self.assertNotEqual(new['id'],p['id']);self.assertFalse((self.b/'data').exists());self.assertEqual(new['body']['target_share'],'b')
   active=self.ctx.state.enqueue('files.transfer',self.review(new))
   with self.assertRaisesRegex(ValueError,'already queued'):self.fm.transfer_retry_plan({'id':job})
   self.ctx.state.finish(active,error='Fixture cleanup')
  with using('user:'+'b'*32):
   with self.assertRaises(ValueError):self.fm.transfer_retry_plan({'id':job})
 def test_transfer_eta_includes_readback_and_stale_state_has_no_eta(self):
  from freeqnap.nas.transfer_progress import summarize
  p={'total_bytes':2000,'copied_bytes':1000,'verified_bytes':500,'copy_seconds':1.,'verify_seconds':.2,'totals_ready':True,'updated_at':time.time()}
  r=summarize(p,'running');self.assertAlmostEqual(r['percent'],37.5);self.assertAlmostEqual(r['eta_seconds'],1.6)
  p['updated_at']=time.time()-60;self.assertTrue(summarize(p,'running')['stale']);self.assertIsNone(summarize(p,'running')['eta_seconds'])

 def test_recursive_copy_hash_readback_and_no_overwrite(self):
  source=self.a/'folder';source.mkdir();(source/'hello.txt').write_bytes(b'payload'*10000);(source/'nested').mkdir();(source/'nested'/'empty').touch()
  p=self.fm.transfer_plan({'share':'a','paths':['folder'],'target_share':'b','mode':'copy'});result=self.fm.transfer(self.review(p))
  self.assertEqual(result['published'],['folder']);self.assertEqual((self.b/'folder/hello.txt').read_bytes(),(source/'hello.txt').read_bytes());self.assertTrue(source.exists())
  with self.assertRaises(ValueError):self.fm.transfer_plan({'share':'a','paths':['folder'],'target_share':'b'})
 def test_duplicate_custom_name_move_and_stale_source(self):
  (self.a/'file.txt').write_text('original');p=self.fm.transfer_plan({'share':'a','paths':['file.txt'],'target_share':'a','new_name':'file copy.txt'})
  self.fm.transfer(self.review(p));self.assertEqual((self.a/'file copy.txt').read_text(),'original')
  p=self.fm.transfer_plan({'share':'a','paths':['file.txt'],'target_share':'b','mode':'move'});self.fm.transfer(self.review(p));self.assertFalse((self.a/'file.txt').exists());self.assertTrue((self.b/'file.txt').exists())
  p=self.fm.transfer_plan({'share':'b','paths':['file.txt'],'target_share':'a'});(self.b/'file.txt').write_text('changed after review')
  with self.assertRaises(ValueError):self.fm.transfer(self.review(p))
  self.assertFalse((self.a/'file.txt').exists())
 def test_self_descendant_symlink_and_cross_volume_move_refused(self):
  (self.a/'folder').mkdir()
  with self.assertRaises(ValueError):self.fm.transfer_plan({'share':'a','paths':['folder'],'target_share':'a','target_path':'folder'})
  secret=self.root/'outside';secret.write_text('private');(self.a/'folder'/'escape').symlink_to(secret)
  p=self.fm.transfer_plan({'share':'a','paths':['folder'],'target_share':'b'})
  with self.assertRaises(ValueError):self.fm.transfer(self.review(p))
  self.assertFalse((self.b/'folder').exists());self.assertEqual(secret.read_text(),'private')
  self.assertFalse((self.ctx.mount/'.freeqnap/transfers').exists())
 def test_recycle_default_expiry_and_undated_or_locked_data_retained(self):
  (self.a/'file.txt').write_text('recoverable');ident=self.trash();record=self.ctx.state.setting('trash:'+ident)
  self.assertEqual(self.fm.trash_items()['policy']['retention_days'],30);self.assertTrue(record['deleted_at'])
  record['deleted_at']=time.time()-31*86400;self.ctx.state.set('trash:'+ident,record)
  with patch.object(self.ctx,'volume',side_effect=ValueError('locked')):self.fm.expire()
  self.assertFalse(self.ctx.state.setting('trash:'+ident).get('purged',False))
  record.pop('deleted_at');self.ctx.state.set('trash:'+ident,record);self.fm.expire();self.assertTrue((self.ctx.mount/'.freeqnap/trash'/ident).exists())
  record['deleted_at']=time.time()-31*86400;self.ctx.state.set('trash:'+ident,record);self.fm.expire();self.assertFalse((self.ctx.mount/'.freeqnap/trash'/ident).exists());self.assertTrue(self.ctx.state.setting('trash:'+ident)['purged'])
 def test_policy_review_disable_and_purge_symlink_does_not_follow(self):
  p=self.fm.policy_plan({'retention_days':0});self.fm.policy_apply(self.review(p));self.assertEqual(self.fm.policy()['retention_days'],0)
  for days in [-1,True,'30',3651]:
   with self.assertRaises(ValueError):self.fm.policy_plan({'retention_days':days})
  outside=self.root/'outside';outside.write_text('preserved');(self.a/'folder').mkdir();(self.a/'folder/escape').symlink_to(outside);ident=self.trash('folder')
  p=self.fm.purge_plan({'id':ident});self.fm.purge(self.review(p));self.assertEqual(outside.read_text(),'preserved');self.assertFalse(self.fm.trash_items()['items'])
  with self.assertRaises(ValueError):Recovery(self.ctx,self.fm).source('trash',ident)
 def test_reviewed_permanent_delete_and_multi_item_recycle(self):
  for n in ['one','two']:(self.a/n).write_text(n)
  p=self.fm.recycle_plan({'share':'a','paths':['one','two'],'permanent':False});job=self.ctx.operation('files.recycle',{'plan_id':p['id']});result=self.fm.recycle(self.review(p),job)
  self.assertEqual(result['completed'],['one','two']);self.assertEqual(len(self.fm.trash_items()['items']),2)
  (self.a/'permanent').write_text('gone');p=self.fm.delete_plan({'share':'a','path':'permanent'});r=self.fm.move(self.review(p));self.assertTrue(r['permanently_deleted']);self.assertFalse((self.a/'permanent').exists())
 def test_folder_search_and_pagination(self):
  for i in range(7):(self.a/('example-'+str(i))).touch()
  page=self.fm.list({'share':'a','query':'example','limit':3});self.assertEqual(len(page['entries']),3);self.assertEqual(page['next_offset'],3)
  self.assertEqual(self.fm.list({'share':'a','offset':6,'limit':3})['entries'][0]['name'],'example-6')

 def test_failed_unpublished_copy_stage_can_be_reviewed_and_removed(self):
  (self.a/'folder').mkdir();(self.a/'folder/first').write_text('kept source');outside=self.root/'outside';outside.write_text('outside');(self.a/'folder/last').write_text('second source')
  p=self.fm.transfer_plan({'share':'a','paths':['folder'],'target_share':'b'});job=self.ctx.operation('files.transfer',{'plan_id':p['id']})
  with patch.object(self.fm,'validate_volume',side_effect=ValueError('Injected mid-copy failure')):
   with self.assertRaises(ValueError):self.fm.transfer(self.review(p),job)
  self.ctx.state.finish(job,error='Injected copy failure retained')
  self.assertEqual(self.fm.stages()['items'][0]['id'],job);plan=self.fm.stage_plan({'id':job});self.fm.stage_remove(self.review(plan))
  self.assertFalse(self.fm.stages()['items']);self.assertEqual((self.a/'folder/first').read_text(),'kept source');self.assertEqual(outside.read_text(),'outside');self.assertFalse((self.b/'folder').exists())

 def test_cross_volume_move_verifies_then_recycles_original(self):
  other=self.root/'second';other.mkdir();destination=other/'destination';destination.mkdir();cfg=self.ctx.config();cfg['pools']['second']={'name':'second','mountpoint':str(other),'filesystem_uuid':'second-uuid'};cfg['shares']['second']={'name':'second','pool':'second','path':str(destination),'gid':os.getgid()};self.ctx.save(cfg)
  original_volume=self.ctx.volume
  def volume(key):return (self.ctx.config()['pools']['second'],other) if key=='second' else original_volume(key)
  (self.a/'move.txt').write_bytes(b'verified content')
  with patch.object(self.ctx,'volume',side_effect=volume):
   plan=self.fm.transfer_plan({'share':'a','paths':['move.txt'],'target_share':'second','mode':'move'});result=self.fm.transfer(self.review(plan))
  self.assertEqual((destination/'move.txt').read_bytes(),b'verified content');self.assertFalse((self.a/'move.txt').exists());self.assertEqual(len(result['recycled_sources']),1);self.assertEqual((self.ctx.mount/'.freeqnap/trash'/result['recycled_sources'][0]).read_bytes(),b'verified content')
 def test_readonly_source_can_copy_but_cannot_move_or_be_written(self):
  cfg=self.ctx.config();cfg['shares']['a']['read_only']=True;self.ctx.save(cfg);(self.a/'copy.txt').write_text('safe source')
  plan=self.fm.transfer_plan({'share':'a','paths':['copy.txt'],'target_share':'b','mode':'copy'});self.fm.transfer(self.review(plan));self.assertTrue((self.a/'copy.txt').exists())
  for request in [{'share':'a','paths':['copy.txt'],'target_share':'b','mode':'move'},{'share':'b','paths':['copy.txt'],'target_share':'a','mode':'copy'}]:
   with self.assertRaises(ValueError):self.fm.transfer_plan(request)
 def test_media_neighbors_span_pages_and_exclude_links_private_and_nonmedia(self):
  for i in range(250):(self.a/('image-%03d.jpg'%i)).write_bytes(b'image')
  (self.a/'image-099a.txt').write_text('ignore');(self.a/'image-099b.jpg').symlink_to(self.a/'image-000.jpg');(self.a/'.freeqnap-private.jpg').write_bytes(b'private')
  result=self.fm.media_neighbors({'share':'a','path':'','name':'image-099.jpg'});self.assertEqual(result['next']['name'],'image-100.jpg');self.assertEqual(result['previous']['name'],'image-098.jpg');self.assertEqual(result['total'],250)
