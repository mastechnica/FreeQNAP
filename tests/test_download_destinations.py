import json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from freeqnap import accounts,auth
from freeqnap.state import State
from freeqnap.access_scope import using
from freeqnap.nas.fileops import FileManager
from freeqnap.nas.download_destinations import DownloadDestinations
from test_accounts import Device,PASSWORD

class DestinationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.state=State(self.root/'console');self.state.set('administrator',auth.password_hash(PASSWORD));token,_=auth.login(self.state,PASSWORD);self.admin=auth.session(self.state,token)['user'];self.device=Device(self.root);self.device.files=FileManager(self.device.ctx);self.manager=self.device.downloads;self.handler=DownloadDestinations(self.device,self.state.database);self.manager.destinations=self.handler
  self.users=[]
  for name in ('alice','bob'):
   ident=accounts.change(self.state,self.admin,{'action':'create','username':name,'label':name,'password':PASSWORD,'permissions':accounts.DEFAULT})['id'];scope=self.device.personal.get(ident,name);folder='Users/'+ident+'/files';path=self.root/'data'/folder;path.mkdir(parents=True);scope['ctx'].state.set('personal-files',{'pool':'data','folder':folder,'location_folder':folder,'location_selected':True,'filesystem_uuid':'fixture-volume'});self.users.append((ident,path))
  self.a,self.path=self.users[0];self.b,self.other=self.users[1];self.actor='user:'+self.a
  self.staging=self.root/'data/.freeqnap-downloads';self.staging.mkdir();self.manager.ctx.state.set('downloads_settings',{'pool':'data','filesystem_uuid':'fixture-volume','inode':self.staging.stat().st_ino,'options':{}})
  if sys.platform!='linux':
   def rename(sfd,s,tfd,t):
    try:os.stat(t,dir_fd=tfd,follow_symlinks=False)
    except FileNotFoundError:pass
    else:raise FileExistsError(t)
    os.rename(s,t,src_dir_fd=sfd,dst_dir_fd=tfd)
   p=patch('freeqnap.nas.fileops.rename_exclusive',side_effect=rename);p.start();self.addCleanup(p.stop)
  if os.geteuid()!=0:
   p=patch('os.fchown');p.start();self.addCleanup(p.stop)
 def choose(self,location=None):return self.handler.choose({'save_to':location or {'share':'my-files','path':''}})['destination']
 def add(self):
  choice=self.choose();job=self.manager.add({'url':'https://example.org/file.txt','save_to':choice['token']})['job'];folder=self.staging/job['id'];folder.mkdir();(folder/'file.txt').write_bytes(b'verified download bytes');rows=self.manager.jobs();rows[job['id']]['state']='complete';self.manager.ctx.state.set('downloads_jobs',rows);return job
 def test_owned_destination_is_bound_and_completed_file_is_copied_without_moving_private_data(self):
  with using(self.actor):job=self.add();self.assertEqual(job['save_to']['share'],'my-files')
  self.assertTrue(self.handler.one());self.assertEqual((self.path/'file.txt').read_bytes(),b'verified download bytes');self.assertTrue((self.staging/job['id']/'file.txt').exists());self.assertEqual(self.manager.jobs()[job['id']]['delivery']['state'],'delivered')
 def test_other_accounts_unassigned_roots_traversal_and_forged_binding_are_denied(self):
  with using(self.actor):
   choice=self.choose()
   for loc in ({'share':'pool:data','path':'Users/'+self.b+'/files'},{'share':'my-files','path':'../'+self.b},{'share':'unassigned','path':''},{'share':'my-files','path':'','identity':[1,2]}):
    with self.assertRaises((ValueError,OSError)):self.handler.choose({'save_to':loc})
   with self.assertRaises(ValueError):self.manager.add({'url':'https://example.org/x','save_to':{'share':'my-files','path':''}})
  with using('user:'+self.b),self.assertRaises(ValueError):self.manager.add({'url':'https://example.org/x','save_to':choice['token']})
 def test_permission_revocation_after_queue_prevents_publication(self):
  with using(self.actor):job=self.add()
  accounts.change(self.state,self.admin,{'action':'update','id':self.a,'permissions':['downloads.use','files.read']});self.handler.one();self.assertFalse((self.path/'file.txt').exists());self.assertEqual(self.manager.jobs()[job['id']]['delivery']['state'],'needs-attention')
 def test_read_only_and_symlink_destinations_are_rejected(self):
  (self.path/'escape').symlink_to(self.other,target_is_directory=True)
  with using(self.actor):
   with self.assertRaises(OSError):self.choose({'share':'my-files','path':'escape'})
   cfg=self.device.ctx.config();cfg['pools']['data']['read_only']=True;self.device.ctx.save(cfg)
   with self.assertRaises(ValueError):self.choose()
 def test_replaced_directory_binding_blocks_new_job_and_finished_delivery(self):
  target=self.path/'chosen';target.mkdir()
  with using(self.actor):choice=self.choose({'share':'my-files','path':'chosen'});job=self.manager.add({'url':'https://example.org/file.txt','save_to':choice['token']})['job']
  target.rename(self.path/'original');target.mkdir()
  with using(self.actor),self.assertRaises(ValueError):self.manager.add({'url':'https://example.org/next.txt','save_to':choice['token']})
  folder=self.staging/job['id'];folder.mkdir();(folder/'file.txt').write_text('private');rows=self.manager.jobs();rows[job['id']]['state']='complete';self.manager.ctx.state.set('downloads_jobs',rows);self.handler.one();self.assertEqual(list(target.iterdir()),[])
 def test_existing_files_are_not_overwritten(self):
  (self.path/'file.txt').write_bytes(b'original')
  with using(self.actor):job=self.add()
  self.handler.one();self.assertEqual((self.path/'file.txt').read_bytes(),b'original');self.assertEqual(self.manager.jobs()[job['id']]['delivery']['state'],'needs-attention')
 def test_disabled_user_and_read_only_assignment_cannot_choose_destination(self):
  with using(self.actor):choice=self.choose()
  accounts.change(self.state,self.admin,{'action':'update','id':self.a,'enabled':False})
  with using(self.actor),self.assertRaises(ValueError):self.handler.choose({'save_to':{'share':'my-files'}})
 def test_previous_jobs_keep_destinations_and_partial_data_stays_private(self):
  with using(self.actor):
   old=self.manager.add({'url':'https://example.org/old.txt','save_to':None})['job'];choice=self.choose();new=self.manager.add({'url':'https://example.org/new.txt','save_to':choice['token']})['job'];self.handler.choose({'save_to':None})
  self.assertIsNone(self.manager.jobs()[old['id']]['save_to']);self.assertEqual(self.manager.jobs()[new['id']]['save_to']['share'],'my-files');self.assertFalse(self.handler.one());self.assertEqual(list(self.path.iterdir()),[])
 def test_interruption_does_not_automatically_replay_a_copy(self):
  with using(self.actor):job=self.add()
  rows=self.manager.jobs();rows[job['id']]['delivery']={'state':'copying'};self.manager.ctx.state.set('downloads_jobs',rows);self.handler.recover();self.assertFalse(self.handler.one());self.assertEqual(self.manager.jobs()[job['id']]['delivery']['state'],'needs-attention')
 def test_changing_another_users_job_destination_is_denied(self):
  with using(self.actor):job=self.add()
  with using('user:'+self.b),self.assertRaises(ValueError):self.handler.choose({'id':job['id'],'save_to':{'share':'my-files'}})
 def test_revocation_during_copy_is_rechecked_before_publication(self):
  with using(self.actor):job=self.add()
  original=FileManager.copy_node
  def copy_then_revoke(manager,*args,**kwargs):
   value=original(manager,*args,**kwargs);accounts.change(self.state,self.admin,{'action':'update','id':self.a,'permissions':['downloads.use','files.read']});return value
  with patch.object(FileManager,'copy_node',copy_then_revoke):self.handler.one()
  self.assertFalse((self.path/'file.txt').exists());self.assertEqual(self.manager.jobs()[job['id']]['delivery']['state'],'needs-attention')
 def test_assigned_share_requires_current_write_grant_and_revocation_blocks_saving(self):
  folder=self.root/'data/project';folder.mkdir();cfg=self.device.ctx.config();cfg['shares']['project']={'name':'project','pool':'data','path':str(folder),'gid':os.getgid(),'enabled':True};self.device.ctx.save(cfg)
  assignment={'share':'project','pool':'data','path':str(folder),'filesystem_uuid':'fixture-volume','access':'read'}
  def grant(access):
   assignment['access']=access
   with self.state.connect() as db:db.execute('INSERT OR REPLACE INTO account_storage VALUES(?,?)',(self.a,json.dumps([assignment])))
  grant('read')
  with using(self.actor),self.assertRaises(ValueError):self.choose({'share':'project','path':''})
  grant('write')
  with using(self.actor):
   choice=self.choose({'share':'project','path':''});job=self.manager.add({'url':'https://example.org/file.txt','save_to':choice['token']})['job']
  root=self.staging/job['id'];root.mkdir();(root/'file.txt').write_text('owned bytes');rows=self.manager.jobs();rows[job['id']]['state']='complete';self.manager.ctx.state.set('downloads_jobs',rows)
  grant('read');self.handler.one();self.assertFalse((folder/'file.txt').exists());self.assertEqual(self.manager.jobs()[job['id']]['delivery']['state'],'needs-attention')
 def test_encrypted_volume_lease_is_not_bypassed_by_destination_choice(self):
  from freeqnap.access_scope import claim
  cfg=self.device.ctx.config();cfg['pools']['data'].update(encrypted=True,luks_uuid='fixture-encryption');self.device.ctx.save(cfg)
  with using('user:'+self.b):claim(self.device.ctx,cfg['pools']['data'])
  with using(self.actor),self.assertRaises(ValueError):self.choose()
 def test_unknown_share_or_unavailable_volume_does_not_change_selected_preference(self):
  with using(self.actor):
   original=self.choose()
   with self.assertRaises(ValueError):self.choose({'share':'absent','path':''})
   self.assertEqual(self.handler.selected()['token'],original['token'])
 def test_queue_destination_can_be_changed_only_before_copying_and_never_moves_partials(self):
  with using(self.actor):
   job=self.manager.add({'url':'https://example.org/file.txt','save_to':None})['job'];root=self.staging/job['id'];root.mkdir();(root/'partial.aria2').write_text('partial marker')
   self.handler.choose({'id':job['id'],'save_to':{'share':'my-files','path':''}});self.assertTrue((root/'partial.aria2').exists());self.assertEqual(self.manager.jobs()[job['id']]['destination']['inode'],self.staging.stat().st_ino)
   rows=self.manager.jobs();rows[job['id']]['delivery']={'state':'copying'};self.manager.ctx.state.set('downloads_jobs',rows)
   with self.assertRaises(ValueError):self.handler.choose({'id':job['id'],'save_to':None})
 def test_temporary_selection_binds_a_batch_without_changing_saved_default(self):
  (self.path/'batch').mkdir()
  with using(self.actor):
   default=self.choose();temporary=self.handler.choose({'save_to':{'share':'my-files','path':'batch'},'temporary':True})['destination']
   self.assertEqual(self.handler.selected()['token'],default['token'])
   chosen=self.manager.add({'url':'https://example.org/batch.txt','save_to':temporary['token']})['job'];normal=self.manager.add({'url':'https://example.org/default.txt'})['job']
   self.assertEqual(chosen['save_to']['path'],'batch');self.assertEqual(normal['save_to']['path'],'');self.assertEqual(self.handler.selected()['token'],default['token'])
 def test_temporary_selections_cannot_evict_the_saved_default(self):
  with using(self.actor):
   default=self.choose()
   for _ in range(35):self.handler.choose({'save_to':{'share':'my-files','path':''},'temporary':True})
   self.assertEqual(self.handler.selected()['token'],default['token']);self.assertEqual(self.handler.binding({})['share'],'my-files')
 def test_temporary_clear_and_invalid_modes_do_not_change_default(self):
  with using(self.actor):
   default=self.choose();self.handler.choose({'save_to':None,'temporary':True});self.assertEqual(self.handler.selected()['token'],default['token'])
   for request in ({'save_to':None,'temporary':'true'},{'save_to':None,'temporary':True,'id':'a'*32}):
    with self.assertRaises(ValueError):self.handler.choose(request)
   self.assertEqual(self.handler.selected()['token'],default['token'])
