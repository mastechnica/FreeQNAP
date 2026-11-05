import tempfile,unittest,time
from freeqnap.state import State
from freeqnap.library_sources import Sources,handle
class Gateway:
 def __init__(self,state):
  self.state=state;self.share=None;self.managed=None;self.user={'id':'a'*32,'label':'Family','role':'member','must_change':False,'permissions':['myradio.read','myradio.write','photos.read','photos.write','files.read','files.write']};self.calls=[];self.transfers=[];self.job_rows=[];self.entries={'':[{'name':'Music','directory':True},{'name':'Books','directory':True},{'name':'Podcasts','directory':True},{'name':'Imports','directory':True}],'Music':[{'name':'Artist A','directory':True},{'name':'Artist B','directory':True}]};self.session=lambda:{'user':self.user};self.fail_enqueue=False
 def _request(self,action,payload):
  self.calls.append((action,payload))
  if action in ('myradio.status','photos.status','library.files-status'):return {'online':True,'config':{'location_selected':True,'pool':'data','location_folder':'personal','scan_enabled':True}}
  if action=='files.list':
   if payload.get('share')=='other-private':raise PermissionError('Private folder')
   return {'entries':self.entries.get(payload.get('path',''),[]),'next_offset':None}
  if action=='files.mkdir':return {'created':payload['name']}
  if action=='files.transfers':return {'transfers':self.transfers}
  if action=='photos.icloud-status':return {'download_running':False}
  if action=='myradio.import-folder':
   if self.fail_enqueue:raise OSError('Ambiguous connection failure')
   return {'job_id':'job-'+str(len(self.calls))}
  if action=='photos.import-folder':return {'started':True}
  raise ValueError(action)
 def jobs(self):return {'jobs':self.job_rows}
class SourcesTests(unittest.TestCase):
 def setUp(self):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.g=Gateway(State(t.name));self.sources=Sources(self.g,'radio')
 def save(self):return self.sources.save({'kind':'radio','enabled':True,'interval_minutes':15,'sources':[{'share':'my-radio','path':'Music','category':'music','enabled':True,'label':'My Radio / Music'}]})
 def test_multiple_folders_suggestions_and_missing_defaults(self):
  self.g.entries['']=[];r=self.save();self.assertEqual(len(r['config']['sources']),1);self.assertEqual([p['name'] for a,p in self.g.calls if a=='files.mkdir'],['Music','Books','Podcasts']);self.assertIn('my-files',[s['share'] for s in r['suggestions']]);self.assertNotIn('tasks',r['run'])
 def test_waits_for_copy_then_splits_artist_directories_and_keeps_receipts(self):
  self.save();self.g.transfers=[{'status':'running'}];self.sources.tick();self.assertEqual(self.sources.run()['state'],'waiting-transfers');self.assertFalse(any(a=='myradio.import-folder' for a,p in self.g.calls));self.g.transfers=[];self.sources.tick();r=self.sources.run();self.assertEqual(r['state'],'waiting-job');self.assertEqual(len(r['tasks']),2);self.assertEqual(next(p for a,p in self.g.calls if a=='myradio.import-folder')['path'],'Music/Artist A');self.sources.tick();self.assertEqual(self.sources.run()['state'],'uncertain')
 def test_job_failure_is_retained_and_not_requeued(self):
  self.save();self.sources.tick();r=self.sources.run();self.g.job_rows=[{'id':r['job_id'],'status':'retryable'}];self.sources.tick();self.assertEqual(self.sources.run()['state'],'failed');n=len(self.g.calls);self.sources.tick();self.assertEqual(n,len(self.g.calls))
 def test_ambiguous_enqueue_is_not_repeated_even_after_restart_or_save(self):
  self.save();self.g.fail_enqueue=True
  with self.assertRaises(OSError):self.sources.tick()
  self.assertEqual(self.sources.run()['state'],'uncertain');n=len([a for a,p in self.g.calls if a=='myradio.import-folder']);Sources(self.g,'radio').tick();self.assertEqual(n,len([a for a,p in self.g.calls if a=='myradio.import-folder']))
  with self.assertRaises(ValueError):self.save()
 def test_success_advances_only_after_positive_receipt_and_completes(self):
  self.save();self.sources.tick();one=self.sources.run()['job_id'];self.g.job_rows=[{'id':one,'status':'succeeded'}];self.sources.tick();two=self.sources.run()['job_id'];self.g.job_rows.append({'id':two,'status':'succeeded'});self.sources.tick();self.assertEqual(self.sources.run()['state'],'complete');self.assertEqual(len([a for a,p in self.g.calls if a=='myradio.import-folder']),2)
 def test_permissions_sharing_private_sources_and_path_checks(self):
  self.g.share='grant'
  with self.assertRaises(PermissionError):Sources(self.g,'radio')
  self.g.share=None;self.g.user['permissions']=['myradio.read']
  with self.assertRaises(PermissionError):self.save()
  self.g.user['permissions']+=['myradio.write']
  with self.assertRaises(ValueError):self.sources.save({'kind':'radio','sources':[{'share':'my-radio','path':'../escape'}]})
  with self.assertRaises(PermissionError):self.sources.save({'kind':'radio','sources':[{'share':'other-private','path':'Music'}]})
 def test_loose_tracks_keep_the_parent_source_and_no_files_are_deleted(self):
  self.save();self.g.entries['Music']=[{'name':'track.mp3','directory':False},{'name':'Album','directory':True}];self.sources.tick();self.assertEqual(self.sources.run()['tasks'][0]['path'],'Music');self.assertTrue(all(a not in ('files.delete','files.move') for a,p in self.g.calls))
 def test_photo_scan_waits_for_busy_import(self):
  s=Sources(self.g,'photos');s.save({'kind':'photos','enabled':True,'sources':[{'share':'my-photos','path':'Imports'}]});original=self.g._request
  self.g._request=lambda a,p:{'download_running':True} if a=='photos.icloud-status' else original(a,p);s.tick();self.assertEqual(s.run()['state'],'waiting-photos')

 def test_existing_lowercase_music_folder_is_reused_without_creating_a_duplicate(self):
  self.g.entries['']=[{'name':'music','directory':True},{'name':'Books','directory':True},{'name':'Podcasts','directory':True}];self.save();self.assertFalse(any(a=='files.mkdir' for a,p in self.g.calls));self.assertEqual(next(r['path'] for r in self.sources.suggestions() if r['category']=='music'),'music')

 def test_existing_category_disable_switch_prevents_import(self):
  self.save();self.sources.library['config']['folders']={'music':False,'books':True,'podcasts':True};self.sources.tick();self.assertEqual(self.sources.run()['state'],'complete');self.assertFalse(any(a=='myradio.import-folder' for a,p in self.g.calls))
 def test_recorded_submission_without_receipt_is_never_replayed(self):
  self.save();self.sources.put_run({'state':'submitting','next':0});self.sources.tick();self.assertEqual(self.sources.run()['state'],'uncertain');self.assertFalse(any(a=='myradio.import-folder' for a,p in self.g.calls))

 def test_planned_maintenance_blocks_scans_without_replaying_submissions(self):
  self.save();self.sources.put_run({'state':'maintenance','message':'Reviewing local tags'})
  n=len(self.g.calls);self.sources.tick();self.assertEqual(len(self.g.calls),n)
  with self.assertRaises(ValueError):self.sources.request_scan()
  with self.assertRaises(ValueError):self.save()
