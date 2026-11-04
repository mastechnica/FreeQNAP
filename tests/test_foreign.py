import copy,os,unittest
from pathlib import Path
from unittest.mock import patch
import test_external
from freeqnap.nas.foreign import Foreign,unlock_secret

class ForeignTests(unittest.TestCase):
 def setUp(self):
  test_external.USBTests.setUp(self);self.foreign=Foreign(self.ctx,self.service)
  self.disk['children']=[{'path':'/dev/sdz1','type':'part','size':2*1024**3,'fstype':'crypto_LUKS','uuid':'test-crypto','partuuid':'test-part','mountpoints':[]}]
 def probe(self,*a):return test_external.USBTests.probe(self,*a)
 def fake_run(self,*a,**kw):return test_external.USBTests.fake_run(self,*a,**kw)
 def request(self,**extra):return {'id':self.usb['id'],'source':'/dev/sdz1',**extra}
 def review(self,p):return {'plan_id':p['id'],'digest':p['digest'],'confirmation':p['confirmation']}
 def test_password_policy_preserves_short_existing_passwords_without_weakening_new_volume_policy(self):
  from freeqnap.nas.common import secret
  self.assertEqual(unlock_secret({'password':'old'}),b'old')
  with self.assertRaises(ValueError):secret({'password':'old'})
  for value in [{'password':''},{'password':'a\npassword'},{'path':'/root/key'},{'password':'x','key_base64':'eA=='}]:
   with self.assertRaises(ValueError):unlock_secret(value)
 def test_read_only_plan_supported_formats_and_no_secret_persisted(self):
  for kind,expected in [('crypto_LUKS','luks'),('BitLocker','bitlk'),('apfs','apfs')]:
   self.disk['children'][0]['fstype']=kind;p=self.foreign.plan(self.request());self.assertEqual(p['body']['format'],expected);self.assertIn('Read-only',p['body']['review']);self.assertNotIn('secret',str(p))
  self.assertFalse(any(c[0] in ('cryptsetup','systemd-mount','mkfs.ext4') for c in self.commands))
 def test_active_root_wrong_path_unidentified_and_registered_refused(self):
  for change in [{'mountpoints':['/other']},{'children':[{'path':'/dev/mapper/other'}]},{'uuid':None,'partuuid':None},{'path':'/dev/sda1'}]:
   old=copy.deepcopy(self.disk['children'][0]);self.disk['children'][0].update(change)
   with self.assertRaises(ValueError):self.foreign.plan(self.request())
   self.disk['children'][0]=old
  self.data['root']['uuid']='test-crypto'
  with self.assertRaises(ValueError):self.foreign.plan(self.request())
 def test_stale_identity_refuses_unlock_before_secret_or_mapping(self):
  p=self.foreign.plan(self.request());self.usb['identity']['serial']='REPLACED'
  with self.assertRaisesRegex(ValueError,'changed'):self.foreign.unlock({**self.review(p),'secret':{'password':'old'}})
  self.assertFalse(any(c[0]=='cryptsetup' for c in self.commands))
 def test_mapping_is_read_only_stdin_only_and_failure_closes(self):
  p=self.foreign.plan(self.request());calls=[]
  def run(*a,**kw):
   calls.append((a,kw))
   if a[0]=='swapon':return ''
   if a[:2]==('cryptsetup','open'):return ''
   if a[:2]==('cryptsetup','close'):return ''
   if a[:2]==('blockdev','--getro'):return '1'
   if a[0]=='blkid':return 'unsupported'
   raise ValueError('Unexpected fixture command')
  with patch.object(self.ctx,'run',side_effect=run),patch.object(self.foreign,'prepare_target'),patch('freeqnap.nas.foreign.atomic'):
   with self.assertRaisesRegex(ValueError,'Unsupported inner'):self.foreign.unlock({**self.review(p),'secret':{'password':'test-private-unlock'}})
  opened=[r for r in calls if r[0][:2]==('cryptsetup','open')][0];self.assertIn('--readonly',opened[0]);self.assertEqual(opened[1]['data'],b'test-private-unlock');self.assertNotIn('test-private-unlock',str(opened[0]));self.assertTrue(any(c[0][:2]==('cryptsetup','close') for c in calls));self.assertNotIn(b'test-private-unlock',self.ctx.state.database.read_bytes())
 def test_bitlocker_password_uses_prompt_stdin_not_binary_startup_key_mode(self):
  self.disk['children'][0]['fstype']='BitLocker';p=self.foreign.plan(self.request());calls=[]
  def run(*a,**kw):
   calls.append((a,kw))
   if a[0]=='swapon':return ''
   if a[:2] in [('cryptsetup','open'),('cryptsetup','close')]:return ''
   if a[:2]==('blockdev','--getro'):return '1'
   if a[0]=='blkid':return 'unsupported'
   raise ValueError('Unexpected command')
  with patch.object(self.ctx,'run',side_effect=run),patch.object(self.foreign,'prepare_target'),patch('freeqnap.nas.foreign.atomic'):
   with self.assertRaisesRegex(ValueError,'Unsupported inner'):self.foreign.unlock({**self.review(p),'secret':{'password':'existing-password'}})
  opened=[r for r in calls if r[0][:2]==('cryptsetup','open')][0];self.assertNotIn('--key-file',opened[0]);self.assertEqual(opened[1]['data'],b'existing-password\n');self.assertIn('--readonly',opened[0])
 def test_foreign_sessions_never_become_writable_data_pools(self):
  cap=self.foreign.capabilities();self.assertFalse(cap['automatic_unlock']);self.assertFalse(cap['universal_format_support']);self.assertFalse(self.ctx.config()['pools']);self.assertEqual(cap['sessions'],[])
  with self.assertRaises(ValueError):self.foreign.record('../escape')

 def test_apfs_browser_uses_volume_root_and_skips_collected_service_on_lock(self):
  import base64
  target=self.root/'apfs';(target/'root').mkdir(parents=True);(target/'private-dir').mkdir();(target/'root/proof.txt').write_bytes(b'proof')
  record={'id':'b'*32,'mapping':None,'format':'apfs','mountpoint':str(target),'unit':'freeqnap-foreign-'+('b'*32)+'.service'}
  with patch.object(self.foreign,'record',return_value=record),patch.object(self.foreign,'validate',return_value=record):
   listing=self.foreign.files({'session':'b'*32});self.assertEqual([e['name'] for e in listing['entries']],['proof.txt']);self.assertEqual(base64.b64decode(self.foreign.files({'session':'b'*32,'path':'proof.txt'},True)['data_base64']),b'proof')
   calls=[]
   with patch('os.path.ismount',return_value=False),patch.object(self.ctx,'run',side_effect=lambda *a,**k:calls.append(a) or ''):
    self.assertTrue(self.foreign.lock({'session':'b'*32})['locked'])
   self.assertFalse(any(c[:2]==('systemctl','stop') for c in calls))

 def test_permissive_foreign_fs_remains_behind_private_parent_and_symlink_refused(self):
  import stat
  base=self.root/'mounts';base.mkdir(mode=0o755);target=base/('c'*32);self.foreign.prepare_target(target)
  self.assertEqual(stat.S_IMODE(base.stat().st_mode),0o700);self.assertEqual(stat.S_IMODE(target.stat().st_mode),0o700)
  other=self.root/'other';other.mkdir(mode=0o755);link=self.root/'link';link.symlink_to(other,target_is_directory=True)
  with self.assertRaises(OSError):self.foreign.prepare_target(link/('d'*32))
  self.assertEqual(stat.S_IMODE(other.stat().st_mode),0o755)

 def test_mounted_but_changed_attachment_is_not_advertised_as_unlocked(self):
  import json
  record={'id':'d'*32,'source':'/dev/sdz1','format':'apfs','mountpoint':str(self.root/'mounted'),'created_at':1,'mapping':None}
  directory=self.ctx.directory/'foreign';directory.mkdir(exist_ok=True);(directory/(record['id']+'.json')).write_text(json.dumps(record))
  with patch('os.path.ismount',return_value=True),patch.object(self.foreign,'validate',side_effect=ValueError('Attachment changed')):
   rows=self.foreign.sessions();self.assertEqual(len(rows),1);self.assertFalse(rows[0]['active'])
  with patch('os.path.ismount',return_value=True),patch.object(self.foreign,'validate',return_value=record):self.assertTrue(self.foreign.sessions()[0]['active'])

 def test_plain_ntfs_plan_mounts_readonly_without_password_or_cryptsetup(self):
  self.disk['children'][0]['fstype']='ntfs';plan=self.foreign.plan(self.request());self.assertEqual(plan['confirmation'],'MOUNT USB READ ONLY');calls=[]
  def run(*args,**kwargs):calls.append(args);return ''
  with patch.object(self.foreign,'source',return_value=(self.service.select(self.request()['id']),self.disk['children'][0])),patch.object(self.ctx,'run',side_effect=run),patch.object(self.foreign,'prepare_target'),patch.object(self.foreign,'validate'),patch('freeqnap.nas.foreign.atomic'),patch('shutil.which',return_value='/usr/bin/ntfs-3g'),patch('pathlib.Path.exists',return_value=True):
   result=self.foreign.unlock(self.review(plan))
  self.assertTrue(result['read_only']);mount=next(v for v in calls if v[0]=='systemd-mount');self.assertIn('--type=ntfs-3g',mount);self.assertIn('--options=ro,nodev,nosuid,noexec,norecover',mount);self.assertFalse(any(v[0]=='cryptsetup' for v in calls))
