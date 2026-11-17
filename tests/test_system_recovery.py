import hashlib,json,os,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from test_nas import Fixture
from freeqnap.state import State
from freeqnap.nas.system_recovery import SystemRecovery
from freeqnap.nas.recovery import Recovery
from freeqnap.nas.fileops import FileManager

class SystemRecoveryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.ctx=Fixture(self.root);self.host=self.root/'host';(self.host/'etc').mkdir(parents=True);(self.host/'etc/freeqnap-install-id').write_text('test-install');(self.host/'etc/shadow').write_text('private-password-hash');(self.ctx.directory/'secrets').mkdir();(self.ctx.directory/'secrets/repo.password').write_text('private-repo-password');self.console=State(self.host/'var/lib/freeqnap');self.console.set('administrator',{'fixture':True});self.console.set('enrollment','private-one-use-token')
  with self.console.connect() as db:db.execute('INSERT INTO sessions VALUES(?,?,?)',('session','csrf',99999999999))
  self.r=SystemRecovery(self.ctx,self.host);self.ident='a'*32
 def review(self,p):return {'plan_id':p['id'],'digest':p['digest'],'confirmation':p['confirmation']}
 def test_consistent_private_capture_includes_broker_credentials_and_excludes_sessions(self):
  stage=self.r.capture(self.ident);manifest=self.r.verify(stage);self.assertTrue(manifest['contains_credentials_and_private_keys']);self.assertFalse(manifest['automatic_restore_supported']);self.assertEqual((stage/'state/nas/secrets/repo.password').read_text(),'private-repo-password')
  self.assertTrue((stage/'state/console').exists());self.assertTrue(manifest['console_login_database_included']);
  with sqlite3.connect(stage/'state/console/state.sqlite3') as db:self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0);self.assertEqual(db.execute("SELECT count(*) FROM settings WHERE key='enrollment'").fetchone()[0],0)
  self.assertTrue(manifest['fresh_console_administrator_required'])
  with sqlite3.connect(stage/'state/nas/state.sqlite3') as db:self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
  self.assertEqual((stage/'system/etc/shadow').stat().st_mode&511,384);self.assertEqual(stage.stat().st_mode&511,448);self.assertEqual(self.r.capture(self.ident),stage)
 def test_modified_or_incomplete_capture_refuses_retry(self):
  stage=self.r.capture(self.ident);(stage/'system/etc/shadow').write_text('changed')
  with self.assertRaises(ValueError):self.r.capture(self.ident)
 def test_symlink_does_not_export_outside_configuration(self):
  private=self.root/'outside';private.write_text('outside-data');(self.host/'etc/ssh').mkdir();(self.host/'etc/ssh/ssh_host_key').symlink_to(private)
  with self.assertRaises(ValueError):self.r.capture(self.ident)
  self.assertEqual(private.read_text(),'outside-data')
 def test_bounded_capture_retains_failure_and_originals(self):
  with patch('freeqnap.nas.system_recovery.LIMIT',1):
   with self.assertRaises(ValueError):self.r.capture(self.ident)
  self.assertTrue((self.ctx.directory/'system-recovery'/self.ident).exists());self.assertEqual((self.host/'etc/shadow').read_text(),'private-password-hash')
 def test_encrypted_repository_success_removes_private_stage_and_failure_retains(self):
  class Backups:
   def get(self,name):return {'name':name}
   def command(self,entry,*args,**kwargs):return json.dumps({'message_type':'summary','snapshot_id':'b'*64}) if args[0]=='backup' else ''
  value=self.r.backup({'repository':'repo'},self.ident,Backups());self.assertTrue(value['encrypted_in_repository']);self.assertTrue(value['private_stage_removed']);self.assertFalse((self.ctx.directory/'system-recovery'/self.ident).exists())
  b=Backups()
  with patch.object(b,'command',side_effect=ValueError('offline')):
   with self.assertRaises(ValueError):self.r.backup({'repository':'repo'},'c'*32,b)
  self.assertTrue((self.ctx.directory/'system-recovery'/('c'*32)/'manifest.json').exists())
 def test_system_restore_stage_cannot_be_published_to_a_share(self):
  ident=self.ctx.state.enqueue('backup.restore',{});self.ctx.state.finish(ident,result={'pool':'data','staging_directory':str(self.ctx.mount/'.freeqnap/restores'/ident),'restored_content_verified':True,'system_recovery_only':True});recovery=Recovery(self.ctx,FileManager(self.ctx))
  with self.assertRaisesRegex(ValueError,'credentials'):recovery.source('restore',ident)
 def test_failed_private_stage_cleanup_is_reviewed_and_cannot_resurrect(self):
  ident=self.ctx.state.enqueue('backup.system-run',{'repository':'repo'});self.r.capture(ident);self.ctx.state.finish(ident,error='offline');plan=self.r.stage_plan({'id':ident});self.r.stage_remove(self.review(plan));self.assertFalse(self.r.stages()['items'])
  with self.assertRaisesRegex(ValueError,'explicitly removed'):self.r.capture(ident)
 def test_samba_database_requires_consistent_snapshot_tool(self):
  p=self.host/'var/lib/samba/private';p.mkdir(parents=True);(p/'passdb.tdb').write_bytes(b'fixture')
  with patch('freeqnap.nas.system_recovery.shutil.which',return_value=None):
   with self.assertRaisesRegex(ValueError,'tdb-tools'):self.r.capture(self.ident)

 def test_pending_network_change_refuses_capture_before_copying_credentials(self):
  self.ctx.state.set('network_pending',{'id':'test'})
  with self.assertRaisesRegex(ValueError,'network/VPN'):self.r.capture(self.ident)
  self.assertFalse((self.ctx.directory/'system-recovery'/self.ident).exists())
 def test_verified_backup_with_cleanup_failure_can_be_reviewed_and_cleaned(self):
  ident=self.ctx.state.enqueue('backup.system-run',{'repository':'repo'})
  class Backups:
   def get(self,name):return {'name':name}
   def command(self,entry,*args,**kwargs):return json.dumps({'message_type':'summary','snapshot_id':'b'*64}) if args[0]=='backup' else ''
  with patch('freeqnap.nas.system_recovery.shutil.rmtree',side_effect=OSError('fixture cleanup failure')):value=self.r.backup({'repository':'repo'},ident,Backups())
  self.assertFalse(value['private_stage_removed']);self.ctx.state.finish(ident,result=value);plan=self.r.stage_plan({'id':ident});self.r.stage_remove(self.review(plan));self.assertFalse(self.r.stages()['items']);self.assertTrue(self.ctx.state.setting('system_backup:'+ident)['encrypted_in_repository'])

 def test_named_watchdog_policy_is_captured_but_other_manager_settings_are_not(self):
  directory=self.host/'etc/systemd/system.conf.d';directory.mkdir(parents=True)
  (directory/'80-freeqnap-watchdog.conf').write_text('[Manager]\nRuntimeWatchdogSec=10s\n')
  (directory/'unrelated.conf').write_text('unrelated')
  stage=self.r.capture(self.ident)
  self.assertTrue((stage/'system/etc/systemd/system.conf.d/80-freeqnap-watchdog.conf').exists())
  self.assertFalse((stage/'system/etc/systemd/system.conf.d/unrelated.conf').exists())

 def test_only_named_hardening_policy_is_captured(self):
  directory=self.host/'etc/sysctl.d';directory.mkdir(parents=True)
  (directory/'90-freeqnap-hardening.conf').write_text('kernel.unprivileged_bpf_disabled = 2\n')
  (directory/'unrelated.conf').write_text('unrelated settings')
  stage=self.r.capture(self.ident)
  target=stage/'system/etc/sysctl.d/90-freeqnap-hardening.conf'
  self.assertEqual(target.read_text(),'kernel.unprivileged_bpf_disabled = 2\n');self.assertEqual(target.stat().st_mode&511,384)
  self.assertFalse((stage/'system/etc/sysctl.d/unrelated.conf').exists());self.r.verify(stage)

 def test_personal_database_above_ordinary_file_limit_is_streamed_and_kept(self):
  owner='b'*32;database=State(self.ctx.directory/'personal'/owner)
  database.set('large-fixture','x'*40000)
  original=Path.read_bytes
  def bounded_read(path):
   if path.suffix=='.sqlite3':raise AssertionError('SQLite recovery hashes must stream')
   return original(path)
  with patch('freeqnap.nas.system_recovery.FILE_LIMIT',1024),patch('freeqnap.nas.system_recovery.DATABASE_LIMIT',1024*1024),patch.object(Path,'read_bytes',bounded_read):
   stage=self.r.capture(self.ident);manifest=self.r.verify(stage)
  relative='state/nas/personal/'+owner+'/state.sqlite3'
  self.assertTrue(manifest['files'][relative]['sqlite_consistent'])
  with sqlite3.connect(stage/relative) as db:
   self.assertEqual(db.execute("SELECT value FROM settings WHERE key='large-fixture'").fetchone()[0],json.dumps('x'*40000))

 def test_database_cap_failure_keeps_previous_stage_and_incomplete_evidence(self):
  accepted=self.r.capture(self.ident)
  with patch('freeqnap.nas.system_recovery.DATABASE_LIMIT',1):
   with self.assertRaisesRegex(ValueError,'size limit'):self.r.capture('b'*32)
  self.r.verify(accepted);self.assertTrue((self.ctx.directory/'system-recovery'/('b'*32)).is_dir())

 def test_database_open_error_is_structured_and_preserves_incomplete_stage(self):
  original=sqlite3.connect
  def fail_snapshot(path,*args,**kwargs):
   if str(path).startswith('file:'):raise sqlite3.OperationalError('fixture private diagnostic')
   return original(path,*args,**kwargs)
  with patch('freeqnap.nas.system_recovery.sqlite3.connect',side_effect=fail_snapshot):
   with self.assertRaisesRegex(ValueError,'Consistent database snapshot unavailable') as caught:self.r.capture(self.ident)
  self.assertNotIn('fixture private diagnostic',str(caught.exception))
  self.assertTrue((self.ctx.directory/'system-recovery'/self.ident).is_dir())

 def test_runtime_locks_are_excluded_but_network_and_vpn_configuration_are_kept(self):
  for directory,lockfile in (('network','lock'),('vpn','operations.lock')):
   root=self.ctx.directory/directory;root.mkdir()
   (root/lockfile).write_text('runtime lock')
   (root/'active.json').write_text('fixture configuration')
  stage=self.r.capture(self.ident);manifest=self.r.verify(stage)
  for directory,lockfile in (('network','lock'),('vpn','operations.lock')):
   excluded='state/nas/'+directory+'/'+lockfile
   self.assertNotIn(excluded,manifest['files']);self.assertIn(excluded,manifest['excluded_runtime_files'])
   self.assertIn('state/nas/'+directory+'/active.json',manifest['files'])
