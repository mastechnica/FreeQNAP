import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from test_nas import Fixture
from freeqnap.nas.backup_schedules import BackupSchedules,KEY

class ScheduleTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.ctx=Fixture(Path(self.tmp.name));cfg=self.ctx.config();cfg['shares']={'files':{'name':'files','pool':'data','path':str(self.ctx.mount/'files')}}
  cfg['repositories']={n:{'name':n,'kind':'sftp','host':n+'.invalid','user':'backup','port':22,'remote_path':'/backup','initialized':True,'password_file':'private-not-exposed'} for n in ['one','two']};self.ctx.save(cfg);self.s=BackupSchedules(self.ctx)
 def request(self,name='daily',repository='one',**kw):return {'name':name,'repository':repository,'shares':['files'],'enabled':True,'interval_hours':24,'full_check_days':7,**kw}
 def review(self,p):return {'plan_id':p['id'],'digest':p['digest'],'confirmation':p['confirmation']}
 def save(self,now=1000,**kw):
  with patch('freeqnap.nas.backup_schedules.time.time',return_value=now):self.s.apply(self.review(self.s.plan(self.request(**kw))))
 def row(self):return self.s.list()['items'][0]
 def finish(self,jid,error=None):self.ctx.state.finish(jid,result=None if error else {'snapshot_id':'a'*64},error=error)
 def test_default_disabled_and_no_secrets_or_automatic_prune(self):
  self.assertEqual(self.s.tick(),[]);self.save(enabled=False);self.assertEqual(self.s.tick(100000),[]);self.assertFalse(self.s.list()['automatic_pruning']);self.assertNotIn('password_file',json.dumps(self.s.list()))
  out=self.s.run_now({'name':'daily'});self.assertTrue(out['job_id']);self.assertEqual(len(self.ctx.state.jobs()),1)
 def test_due_coalesces_restart_no_duplicate_and_full_check_after_success(self):
  self.save();due=1000+86400;first=self.s.tick(due);self.assertEqual(len(first),1);self.assertEqual(self.s.tick(due+1),[]);self.assertEqual(BackupSchedules(self.ctx).tick(due+2),[])
  self.finish(first[0]);checks=self.s.tick(due+3);self.assertEqual(len(checks),1)
  with self.ctx.state.connect() as db:r=db.execute('SELECT kind,payload FROM jobs WHERE id=?',(checks[0],)).fetchone()
  self.assertEqual(r['kind'],'backup.check');self.assertTrue(json.loads(r['payload'])['read_data']);self.assertTrue(self.row()['last_backup_success']);self.assertEqual(self.s.tick(due+4),[])
 def test_failure_stays_durable_later_repository_and_later_due_backup_continue(self):
  self.save(name='a',repository='one');self.save(name='b',repository='two');jobs=self.s.tick(1000+86400);self.assertEqual(len(jobs),2);self.finish(jobs[0],'offline');self.finish(jobs[1]);later=self.s.tick(1000+2*86400);self.assertEqual(len(later),2)
  with self.ctx.state.connect() as db:self.assertEqual(db.execute('SELECT status FROM jobs WHERE id=?',(jobs[0],)).fetchone()[0],'retryable')
  self.assertEqual(self.s.list()['items'][0]['backup_consecutive_failures'],1)
 def test_explicit_failed_job_retry_success_refreshes_last_good(self):
  self.save();jid=self.s.tick(87400)[0];self.finish(jid,'offline');self.s.tick(87401);self.assertFalse(self.row().get('last_backup_success'));self.ctx.state.retry(jid);self.ctx.state.claim();self.finish(jid);self.s.tick(87402);self.assertTrue(self.row()['last_backup_success']);self.assertEqual(self.row()['backup_consecutive_failures'],0)
 def test_mapping_change_blocks_automatic_work_until_review(self):
  self.save();cfg=self.ctx.config();cfg['shares']['files']['path']='/changed';self.ctx.save(cfg);self.assertEqual(self.s.tick(100000),[]);self.assertIn('identity changed',self.row()['message'])
  with self.assertRaises(ValueError):self.s.run_now({'name':'daily'})
  self.save(now=100000);self.assertEqual(len(self.s.tick(200000)),1)
 def test_repository_busy_suppresses_overlap_without_blocking_other_repository(self):
  self.save(name='a');self.save(name='b',repository='two');self.ctx.state.enqueue('backup.restore',{'repository':'one'});jobs=self.s.tick(100000);self.assertEqual(len(jobs),1);self.assertEqual(self.s.list()['items'][0]['message'],'Waiting for active repository work')
 def test_clock_jumps_bound_wait_and_coalesce_missed_intervals(self):
  self.save(now=1000000);self.s.tick(1000000);self.assertEqual(self.s.tick(1000),[]);self.assertLessEqual(self.row()['next_backup_at'],87400);self.assertEqual(len(self.s.tick(10000000)),1);self.assertEqual(self.s.tick(10000001),[])
 def test_capacity_defers_without_dropping_due_work_or_failed_history(self):
  self.save()
  for i in range(128):self.ctx.state.enqueue('fixture',{'index':i})
  self.assertEqual(self.s.tick(100000),[]);self.assertIn('Queue full',self.row()['message']);self.assertEqual(self.row()['next_backup_at'],87400)
  job=self.ctx.state.claim();self.finish(job['id'],'retained');self.assertEqual(len(self.s.tick(100001)),1)
 def test_delete_keeps_snapshots_job_history_and_active_job(self):
  self.save();jid=self.s.tick(100000)[0];p=self.s.delete_plan({'name':'daily'});self.s.delete(self.review(p));self.assertEqual(self.s.list()['items'],[])
  with self.ctx.state.connect() as db:self.assertEqual(db.execute('SELECT status FROM jobs WHERE id=?',(jid,)).fetchone()[0],'queued')
 def test_review_revision_survives_scheduler_runtime_and_rejects_conflicting_edit(self):
  self.save();p=self.s.plan(self.request(interval_hours=12));self.s.tick(1001);self.s.apply(self.review(p));self.assertEqual(self.row()['interval_hours'],12)
  p=self.s.plan(self.request());self.save(interval_hours=6)
  with self.assertRaises(ValueError):self.s.apply(self.review(p))
 def test_disabled_policy_can_be_disabled_with_missing_resources_and_never_enables(self):
  self.save();cfg=self.ctx.config();cfg['repositories']={};self.ctx.save(cfg);self.save(enabled=False);self.assertEqual(self.s.tick(999999),[])
 def test_same_pool_requires_explicit_policy_acknowledgement(self):
  cfg=self.ctx.config();cfg['repositories']['one']={'name':'one','kind':'local','pool':'data','filesystem_uuid':'fixture-uuid','path':str(self.ctx.mount/'backup'),'initialized':True};self.ctx.save(cfg)
  with self.assertRaises(ValueError):self.save()
  self.save(same_pool_acknowledged=True);jid=self.s.tick(100000)[0]
  with self.ctx.state.connect() as db:payload=json.loads(db.execute('SELECT payload FROM jobs WHERE id=?',(jid,)).fetchone()[0])
  self.assertEqual(payload['same_pool_confirmation'],'SAME POOL one')

 def test_system_scope_needs_no_share_and_queues_credential_recovery_kind(self):
  self.save(scope='system',shares=[]);jid=self.s.tick(100000)[0]
  with self.ctx.state.connect() as db:r=db.execute('SELECT kind,payload FROM jobs WHERE id=?',(jid,)).fetchone()
  self.assertEqual(r['kind'],'backup.system-run');self.assertEqual(json.loads(r['payload']),{'repository':'one'})
 def test_system_backup_blocks_other_work_on_same_repository_only(self):
  self.save();self.ctx.state.enqueue('backup.system-run',{'repository':'one'});self.assertEqual(self.s.tick(100000),[])
