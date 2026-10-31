import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from test_nas import Fixture
from freeqnap.nas.storage_boundary import tokens,shared
from freeqnap.nas.filebackup import FileBackups
from freeqnap.nas.backup_schedules import BackupSchedules

class BoundaryTests(unittest.TestCase):
 def test_separate_filesystems_on_same_array_are_not_independent(self):
  first={'filesystem_uuid':'one','md_uuid':'11111111:22222222:33333333:44444444'};second={'filesystem_uuid':'two','md_uuid':'11111111-22222222-33333333-44444444'};self.assertTrue(shared(first,second))
 def test_different_arrays_on_same_disk_and_usb_luns_share_a_boundary(self):
  self.assertTrue(shared({'md_uuid':'one','regions':[{'disk':{'wwn':'fixture-disk'}}]},{'md_uuid':'two','members':[{'wwn':'fixture-disk'}]}))
  self.assertTrue(shared({'kind':'usb','external':{'enclosure_id':'fixture-enclosure'}},{'kind':'usb','external':{'enclosure_id':'fixture-enclosure'}}))
 def test_unknown_identity_is_not_invented_and_distinct_known_arrays_do_not_match(self):
  self.assertFalse(shared({},{}));self.assertFalse(shared({'md_uuid':'one','regions':[{'disk':{'serial':'disk-a'}}]},{'md_uuid':'two','regions':[{'disk':{'serial':'disk-b'}}]}));self.assertNotIn(('group',''),tokens({}))
 def setup_context(self):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);ctx=Fixture(Path(temp.name));cfg=ctx.config();cfg['pools']['data']['md_uuid']='fixture-array';cfg['pools']['destination']={'name':'destination','filesystem_uuid':'other-filesystem','md_uuid':'fixture-array','mountpoint':str(ctx.mount)};cfg['shares']['files']={'name':'files','pool':'data','path':str(ctx.mount/'files')};(ctx.mount/'files').mkdir();cfg['repositories']['repo']={'name':'repo','kind':'local','pool':'destination','filesystem_uuid':'other-filesystem','path':str(ctx.mount/'repo'),'initialized':True};ctx.save(cfg);return ctx
 def test_manual_backup_requires_ack_even_when_pool_names_and_filesystems_differ(self):
  ctx=self.setup_context();backups=FileBackups(ctx)
  with patch.object(backups,'command',return_value='') as command:
   with self.assertRaisesRegex(ValueError,'RAID'):backups.backup({'repository':'repo','shares':['files']})
   command.assert_not_called()
  def run(entry,*args,**kwargs):return json.dumps({'message_type':'summary','snapshot_id':'a'*64}) if args[0]=='backup' else '[]'
  with patch.object(backups,'command',side_effect=run):result=backups.backup({'repository':'repo','shares':['files'],'same_pool_confirmation':'SAME POOL repo'})
  self.assertFalse(result['independent_disaster_backup'])
 def test_schedule_requires_shared_storage_ack_and_pins_domain_mapping(self):
  ctx=self.setup_context();schedules=BackupSchedules(ctx);request={'name':'daily','repository':'repo','shares':['files'],'enabled':True,'interval_hours':24,'full_check_days':7}
  with self.assertRaisesRegex(ValueError,'RAID'):schedules.plan(request)
  request['same_pool_acknowledged']=True;plan=schedules.plan(request);schedules.apply({'plan_id':plan['id'],'digest':plan['digest'],'confirmation':plan['confirmation']});cfg=ctx.config();cfg['pools']['destination']['md_uuid']='changed-array';ctx.save(cfg)
  with self.assertRaisesRegex(ValueError,'mapping'):schedules.run_now({'name':'daily'})
