import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from freeqnap.nas.common import Context
from freeqnap.nas.downloads import Downloads,config_text
from freeqnap.nas.download_limits import selected,save,plan,enforce
from freeqnap.nas.member_services import downloads
from freeqnap.access_scope import using
A='a'*32;B='b'*32
class DownloadLimitsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.ctx=Context(Path(self.tmp.name));self.m=Downloads(self.ctx);self.m.target=Mock();self.m.rpc=Mock(return_value='OK');self.m.destinations=SimpleNamespace(authorize=Mock(return_value=({'role':'member'},{})))
  self.options={'concurrent':3,'download_kib':0,'upload_kib':256,'seed_ratio':1.,'seed_minutes':0};self.ctx.state.set('downloads_settings',{'pool':'fixture','options':self.options});self.m.root=Path(self.tmp.name)/'engine';self.m.root.mkdir();self.m.limits_drop=self.m.root/'limits.conf';self.ctx.run=Mock();(self.m.root/'aria2.conf').write_text('original\n');(self.ctx.directory/'downloads-rpc-token').write_text('test-token')
 def set_limits(self,owner=A,**extra):
  with using('user:'+owner):return save(self.m,{'scope':'account','concurrent':0,'download_kib':0,**extra})
 def row(self,i,owner=A,**extra):return {'id':str(i),'gid':'gid'+str(i),'actor':'user:'+owner,'desired':'running','state':'active','created':i,**extra}
 def test_default_and_account_isolation(self):
  with using('user:'+A):self.assertEqual(selected(self.m),{'concurrent':0,'download_kib':0})
  self.set_limits(concurrent=2,download_kib=1024)
  with using('user:'+B):self.assertEqual(selected(self.m),{'concurrent':0,'download_kib':0})
  self.assertEqual(self.m.settings()['options'],self.options);self.m.rpc.assert_not_called()
 def test_validate_no_identity_or_global_forgery(self):
  for extra in ({'concurrent':True},{'concurrent':-1},{'download_kib':1.1},{'concurrent':513},{'actor':'user:'+B},{'scope':'global'}):
   with self.assertRaises(ValueError):self.set_limits(**extra)
  with self.assertRaises(ValueError):save(self.m,{'scope':'account','concurrent':0,'download_kib':0})
  with using('user:'+A),self.assertRaises(ValueError):downloads(self.m,A,'downloads.limits',{'scope':'global','concurrent':2,'download_kib':100})
  with using('user:'+B),self.assertRaises(ValueError):downloads(self.m,A,'downloads.limits',{'scope':'account','concurrent':2,'download_kib':100})
 def test_slots_aggregate_bandwidth_and_other_account_untouched(self):
  rows={str(i):self.row(i,B if i==4 else A) for i in range(1,5)};self.ctx.state.set('downloads_jobs',rows);self.set_limits(concurrent=2,download_kib=1001)
  decisions=plan(self.m);self.assertEqual(set(decisions),{'1','2','3'});self.assertFalse(decisions['3']['run']);self.assertLessEqual(sum(v['rate'] for v in decisions.values() if v['run']),1001*1024)
  self.m.rpc.side_effect=lambda method,args:([{'gid':r['gid'],'status':'active'} for r in rows.values()] if method=='tellActive' else [] if method=='tellWaiting' else 'OK')
  enforce(self.m,decisions);calls=self.m.rpc.call_args_list;mutations=[c.args for c in calls if c.args[0] not in ('tellActive','tellWaiting')]
  self.assertEqual(mutations[0],('forcePause',['gid3']));self.assertNotIn('gid4',str(mutations));self.assertEqual(len(mutations),3)
 def test_completed_paused_and_backoff_jobs_release_slots(self):
  rows={'1':self.row(1,state='complete'),'2':self.row(2,desired='paused'),'3':self.row(3,state='error',next_retry=10**12),'4':self.row(4)};self.ctx.state.set('downloads_jobs',rows);self.set_limits(concurrent=1)
  decisions=plan(self.m);self.assertEqual([k for k,v in decisions.items() if v['run']],['4'])
 def test_live_global_persists_without_restart_or_job_mutation(self):
  self.m.destinations.authorize.return_value=({'role':'administrator'},{});before=self.m.jobs()
  with using('user:'+A):result=save(self.m,{'scope':'global','concurrent':0,'download_kib':2048})
  self.assertFalse(result['engine_restarted']);self.assertEqual(self.m.settings()['options']['concurrent'],0);self.assertEqual(self.m.jobs(),before)
  text=self.m.limits_drop.read_text();self.assertIn('--max-concurrent-downloads=512 ',text);self.assertIn('--max-overall-download-limit=2048K\n',text);self.assertEqual((self.m.root/'aria2.conf').read_text(),'original\n');self.ctx.run.assert_called_once_with('systemctl','daemon-reload')
  self.m.rpc.assert_called_once_with('changeGlobalOption',[{'max-concurrent-downloads':'512','max-overall-download-limit':'2048K'}])
 def test_engine_rejection_preserves_global_config_and_settings(self):
  self.m.destinations.authorize.return_value=({'role':'administrator'},{});self.m.rpc.side_effect=ValueError('unavailable')
  with using('user:'+A),self.assertRaises(ValueError):save(self.m,{'scope':'global','concurrent':1,'download_kib':10})
  self.assertEqual(self.m.settings()['options'],self.options);self.assertEqual((self.m.root/'aria2.conf').read_text(),'original\n')
 def test_scheduler_queues_excess_paused_with_limits_before_submit(self):
  rows={str(i):{**self.row(i,state='queued'),'sha256':'','kind':'url','label':'fixture','url':'https://example.org/fixture','attempts':0} for i in range(1,4)};self.ctx.state.set('downloads_jobs',rows);self.set_limits(concurrent=1,download_kib=100)
  def rpc(method,args):
   if method in ('tellActive','tellWaiting'):return []
   if method=='tellStatus':return None
   return 'OK'
  self.m.rpc.side_effect=rpc;self.m.reconcile();submitted=[c.args[1][-1] for c in self.m.rpc.call_args_list if c.args[0]=='addUri']
  self.assertEqual([v['pause'] for v in submitted],['false','true','true']);self.assertTrue(all(v['max-download-limit']=='102400' for v in submitted))
 def test_unlimited_reset_clears_old_per_job_bandwidth(self):
  self.ctx.state.set('downloads_jobs',{'1':self.row(1)});self.set_limits();self.m.rpc.side_effect=lambda method,args:([{'gid':'gid1','status':'active'}] if method=='tellActive' else [] if method=='tellWaiting' else 'OK');enforce(self.m,plan(self.m));self.m.rpc.assert_any_call('changeOption',['gid1',{'max-download-limit':'0'}])
 def test_persistence_failure_rolls_back_runtime_and_service_override(self):
  self.m.destinations.authorize.return_value=({'role':'administrator'},{});self.ctx.run.side_effect=[OSError('reload failed'),None]
  with using('user:'+A),self.assertRaises(OSError):save(self.m,{'scope':'global','concurrent':1,'download_kib':10})
  self.assertFalse(self.m.limits_drop.exists());self.assertEqual(self.m.settings()['options'],self.options)
  self.m.rpc.assert_any_call('changeGlobalOption',[{'max-concurrent-downloads':'3','max-overall-download-limit':'0K'}])
 def test_only_permitted_paused_jobs_resume_and_receive_cap_first(self):
  rows={str(i):self.row(i,state='paused') for i in range(1,3)};self.ctx.state.set('downloads_jobs',rows);self.set_limits(concurrent=1,download_kib=20)
  self.m.rpc.side_effect=lambda method,args:([] if method in ('tellActive','tellWaiting') else {'status':'paused'} if method=='tellStatus' else 'OK');self.m.reconcile()
  calls=[c.args for c in self.m.rpc.call_args_list];self.assertIn(('unpause',['gid1']),calls);self.assertNotIn(('unpause',['gid2']),calls);self.assertLess(calls.index(('changeOption',['gid1',{'max-download-limit':'20480'}])),calls.index(('unpause',['gid1'])))

 def test_paused_entries_in_tell_waiting_do_not_block_status_or_queue_progress(self):
  rows={'1':self.row(1,state='queued'),'2':self.row(2,state='queued')};self.ctx.state.set('downloads_jobs',rows);self.set_limits(concurrent=1,download_kib=10000)
  def rpc(method,args):
   if method=='tellActive':return []
   if method=='tellWaiting':return [{'gid':'gid2','status':'paused'}]
   if method=='tellStatus':return {'status':'complete','totalLength':'393901','completedLength':'393901'} if args[0]=='gid1' else {'status':'paused'}
   if method=='forcePause':raise ValueError('already paused')
   return 'OK'
  self.m.rpc.side_effect=rpc;self.m.reconcile();self.assertEqual(self.m.jobs()['1']['state'],'complete');self.assertTrue(self.m.jobs()['2']['limited']);self.assertFalse(any(c.args[0]=='forcePause' for c in self.m.rpc.call_args_list))
  self.m.reconcile();self.m.rpc.assert_any_call('unpause',['gid2'])
 def test_completion_race_during_pause_does_not_block_other_jobs(self):
  rows={str(i):self.row(i) for i in range(1,3)};self.ctx.state.set('downloads_jobs',rows);self.set_limits(concurrent=1)
  def rpc(method,args):
   if method=='tellActive':return [{'gid':'gid1','status':'active'},{'gid':'gid2','status':'waiting'}]
   if method=='tellWaiting':return []
   if method=='forcePause':raise ValueError('already completed')
   if method=='tellStatus':return {'status':'complete'}
   return 'OK'
  self.m.rpc.side_effect=rpc;enforce(self.m,plan(self.m));self.m.rpc.assert_any_call('changeOption',['gid1',{'max-download-limit':'0'}])
 def test_completion_race_during_bandwidth_change_is_harmless(self):
  self.ctx.state.set('downloads_jobs',{'1':self.row(1)});self.set_limits(download_kib=100)
  def rpc(method,args):
   if method=='tellActive':return [{'gid':'gid1','status':'active'}]
   if method=='tellWaiting':return []
   if method=='changeOption':raise ValueError('already complete')
   if method=='tellStatus':return {'status':'complete'}
  self.m.rpc.side_effect=rpc;enforce(self.m,plan(self.m))
 def test_real_engine_error_is_not_hidden_by_race_handling(self):
  self.ctx.state.set('downloads_jobs',{'1':self.row(1)});self.set_limits(download_kib=100)
  def rpc(method,args):
   if method=='tellActive':return [{'gid':'gid1','status':'active'}]
   if method=='tellWaiting':return []
   if method=='changeOption':raise ValueError('real engine failure')
   if method=='tellStatus':return {'status':'active'}
  self.m.rpc.side_effect=rpc
  with self.assertRaisesRegex(ValueError,'real engine failure'):enforce(self.m,plan(self.m))
