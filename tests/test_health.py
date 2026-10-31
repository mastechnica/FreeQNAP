import copy,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from test_nas import Fixture
from freeqnap.nas.health import Health,DEFAULTS,policy

class HealthTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.ctx=Fixture(self.root/'state');self.ctx.run=lambda *a,**kw:'active\n';self.now=time.time();self.file=self.root/'inventory.json';self.monitor=Health(self.ctx,self.file)
  self.sample={'sampled_at':self.now,'errors':[],'arrays':[{'uuid':'fixture-array','device':'/dev/md0','degraded':0,'sync_action':'idle'}],'smart':[{'device':'/dev/sda','available':True,'passed':True}],'volumes':[{'uuid':'fixture-fs','target':'/','total_bytes':10*1024**3,'available_bytes':8*1024**3}],'temperatures':[{'name':'cpu','celsius':45}]}
 def tick(self,**changes):
  self.sample.update(changes);self.file.write_text(json.dumps(self.sample));self.monitor.tick(self.now);return self.active()
 def active(self):return [r for r in self.monitor.list()['items'] if r['resolved_at'] is None]
 def test_healthy_has_no_alerts_and_outbound_delivery_disabled(self):
  self.assertEqual(self.tick(),[]);self.assertFalse(self.monitor.list()['external_delivery_enabled'])
 def test_ack_does_not_clear_or_hide_fault_and_escalation_reopens_attention(self):
  self.sample['temperatures'][0]['celsius']=78;row=self.tick()[0];self.monitor.acknowledge({'id':row['id']});self.assertIsNotNone(self.tick()[0]['acknowledged_at'])
  self.sample['temperatures'][0]['celsius']=90;row=self.tick()[0];self.assertEqual(row['severity'],'critical');self.assertIsNone(row['acknowledged_at'])
 def test_recovery_and_recurrence_are_distinct_durable_incidents(self):
  self.sample['arrays'][0]['degraded']=1;first=self.tick()[0]['id'];self.monitor=Health(self.ctx,self.file);self.assertEqual(self.active()[0]['id'],first)
  self.sample['arrays'][0]['degraded']=0;self.assertEqual(self.tick(),[]);self.sample['arrays'][0]['degraded']=1;second=self.tick()[0]['id'];self.assertNotEqual(first,second)
  with self.ctx.state.connect() as db:self.assertEqual(db.execute("SELECT count(*) FROM health_events WHERE kind='opened'").fetchone()[0],2)
 def test_stale_or_partial_inventory_never_resolves_existing_hardware_faults(self):
  self.sample['smart'][0]['passed']=False;self.tick();self.sample['smart']=[];self.sample['sampled_at']=self.now-121;rows=self.tick();self.assertEqual({r['scope'] for r in rows},{'smart','inventory'})
  self.sample['sampled_at']=self.now;self.sample['errors']=['one collector failed'];self.assertEqual({r['scope'] for r in self.tick()},{'smart','inventory'})
 def test_one_malformed_check_cannot_hide_later_critical_temperature(self):
  self.sample['arrays'][0]['degraded']='invalid';self.sample['temperatures'][0]['celsius']=95;rows=self.tick();self.assertIn('monitor-raid',{r['scope'] for r in rows});self.assertIn('temperature',{r['scope'] for r in rows})
 def test_failed_backup_stays_visible_and_later_job_can_succeed(self):
  first=self.ctx.state.enqueue('backup.run',{});self.ctx.state.finish(first,error='private diagnostic')
  second=self.ctx.state.enqueue('backup.run',{});self.ctx.state.finish(second,result={'snapshot':'good'});rows=self.tick();self.assertEqual(len(rows),1);self.assertEqual(rows[0]['source'],first);self.assertNotIn('private diagnostic',json.dumps(rows))
  self.ctx.state.retry(first);self.assertEqual(len(self.tick()),1);self.ctx.state.claim();self.ctx.state.finish(first,result={'snapshot':'recovered'});self.assertEqual(self.tick(),[])
 def test_missing_array_cannot_be_mistaken_for_recovery(self):
  cfg=self.ctx.config();cfg['pools']['data']={'name':'data','md_uuid':'fixture-array','kind':'internal'};self.ctx.save(cfg);self.sample['arrays']=[];row=self.tick()[0];self.assertEqual(row['scope'],'raid');self.assertEqual(row['severity'],'critical')
 def test_capacity_thresholds_and_root_floor(self):
  self.sample['volumes'][0]['available_bytes']=400*1024**2;row=self.tick()[0];self.assertEqual(row['scope'],'space');self.assertEqual(row['severity'],'critical')
  self.sample['volumes'].append(copy.deepcopy(self.sample['volumes'][0]));self.assertEqual(len(self.tick()),1)
 def test_invalid_policy_and_ack_are_rejected(self):
  for value in ({},dict(DEFAULTS,space_critical_percent=80),dict(DEFAULTS,temperature_warning_c=True),dict(DEFAULTS,temperature_critical_c=150)):
   with self.assertRaises(ValueError):policy(value)
  for request in ({'id':'invalid'},{'id':'a'*32},{'id':'a'*32,'clear_all':True}):
   with self.assertRaises(ValueError):self.monitor.acknowledge(request)
 def test_required_service_failure_and_disabled_optional_services(self):
  self.ctx.run=lambda *a,**kw:'failed\n' if a[2]=='eyeq-cooling' else 'active\n';rows=self.tick();self.assertEqual(len(rows),1);self.assertEqual(rows[0]['source'],'eyeq-cooling')
 def test_missing_sensor_and_future_samples_are_unavailable(self):
  self.assertEqual(self.tick(temperatures=[])[0]['scope'],'temperature');rows=self.tick(sampled_at=self.now+60);self.assertIn('inventory',{r['scope'] for r in rows})

 def test_repeated_queueing_without_success_never_resets_staleness(self):
  class Schedules:
   def list(inner):return {'items':[{'name':'daily','enabled':True,'interval_hours':1,'last_backup_queued_at':self.now,'last_backup_success':None}]}
  self.monitor.schedules=Schedules();self.tick();self.now+=3*3600;self.sample['sampled_at']=self.now;self.assertIn('schedules',{r['scope'] for r in self.tick()})
 def test_failed_optional_delivery_check_does_not_hide_other_faults(self):
  self.monitor.optional_checks={'broken':lambda:(_ for _ in ()).throw(ValueError('failed')), 'next':lambda:[{'source':'fixture','severity':'critical','title':'Later fault','details':{}}]};rows=self.tick();self.assertIn('monitor-broken',{r['scope'] for r in rows});self.assertIn('next',{r['scope'] for r in rows})
