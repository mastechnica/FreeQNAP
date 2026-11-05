import os,tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from freeqnap.state import State
from freeqnap import activity
from freeqnap.access_scope import using,metadata,claim,check,current
from freeqnap.nas.common import Context
from freeqnap.nas.files import Files
from freeqnap.nas.foreign import Foreign
from freeqnap.nas.user_usage import measure
A='user:'+'a'*32;B='user:'+'b'*32
class PrivacyTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.ctx=Context(self.root/'state');self.pool={'name':'private','encrypted':True,'luks_uuid':'test-luks','filesystem_uuid':'test-fs','mountpoint':str(self.root/'volume')};cfg=self.ctx.config();cfg['pools']['private']=self.pool;self.ctx.save(cfg)
 def test_personal_worker_passes_the_real_job_id_to_transfer(self):
  from freeqnap.nas.personal import Personal
  from types import SimpleNamespace
  from unittest.mock import Mock
  personal=Personal(SimpleNamespace(ctx=self.ctx));scope=personal.get('a'*32);scope['files']=SimpleNamespace(transfer=Mock(return_value={'published':[]}))
  payload={'plan_id':'test-plan','digest':'test-digest','confirmation':'COPY 1 ITEM(S)'}
  with using(A):job=scope['ctx'].state.enqueue('files.transfer',payload)
  personal.one();scope['files'].transfer.assert_called_once_with(payload,job)
  rows=scope['ctx'].state.jobs();self.assertEqual(len(rows),1);self.assertEqual(rows[0]['status'],'succeeded')

 def test_owner_persists_and_no_administrator_or_agent_bypass(self):
  with using(A):claim(self.ctx,self.pool);check(self.ctx,self.pool)
  reloaded=Context(self.ctx.directory)
  for actor in (B,'agent:'+'c'*24,None):
   with using(actor),self.assertRaises(ValueError):check(reloaded,self.pool)
  with using(A):check(reloaded,self.pool)
 def test_identity_change_and_unknown_old_unlock_fail_closed(self):
  with using(A):
   with self.assertRaises(ValueError):check(self.ctx,self.pool)
   claim(self.ctx,self.pool)
   with self.assertRaises(ValueError):check(self.ctx,{**self.pool,'luks_uuid':'replacement'})
 def test_status_metadata_never_becomes_file_access(self):
  with using(A):claim(self.ctx,self.pool)
  with using(B),metadata():
   check(self.ctx,self.pool)
   with self.assertRaises(ValueError):Files(self.ctx).mapping('pool:private')
 def test_foreign_owner_and_legacy_unknown_are_not_implicitly_adopted(self):
  foreign=Foreign(self.ctx,None)
  for record in ({'format':'luks','owner':A},{'format':'apfs'},{'format':'bitlk','owner':B}):
   with using('agent:'+'c'*24),self.assertRaises(ValueError):foreign.assert_owner(record)
  with using(A):foreign.assert_owner({'format':'luks','owner':A})
 def test_plans_cannot_be_applied_by_other_users(self):
  with using(A):plan=self.ctx.plan('fixture',{},'CONFIRM')
  request={'plan_id':plan['id'],'digest':plan['digest'],'confirmation':'CONFIRM'}
  with using(B),self.assertRaisesRegex(ValueError,'another account'):self.ctx.reviewed(request,'fixture')
  with using(A):self.ctx.reviewed(request,'fixture')
 def test_jobs_keep_actor_without_changing_payload(self):
  with using(A):ident=self.ctx.state.enqueue('files.transfer',{'plan_id':'fixture'})
  with self.ctx.state.connect() as db:
   self.assertEqual(db.execute('SELECT actor FROM job_principals WHERE id=?',(ident,)).fetchone()[0],A)
   self.assertEqual(json.loads(db.execute('SELECT payload FROM jobs WHERE id=?',(ident,)).fetchone()[0]),{'plan_id':'fixture'})
  self.ctx.state.finish(ident,result={})
  result=activity.listing(self.ctx.state,{'id':'a'*32,'role':'member'},{});self.assertEqual(result['events'][0]['operation'],'job.files.transfer')
 def test_audit_only_self_plus_sanitized_system_notices(self):
  activity.record(self.ctx.state,A,'files.mkdir');activity.record(self.ctx.state,B,'photos.annotate');activity.record(self.ctx.state,'system','system.restart',scope='system',severity='warning')
  member=activity.listing(self.ctx.state,{'id':'a'*32,'role':'member'},{});self.assertEqual({v['actor'] for v in member['events']},{A,'system'})
  admin=activity.listing(self.ctx.state,{'id':'a'*32,'role':'administrator'},{});self.assertEqual(len(admin['events']),3)
 def test_audit_pagination_does_not_cross_user_boundary(self):
  for _ in range(4):activity.record(self.ctx.state,A,'files.list');activity.record(self.ctx.state,B,'files.read')
  user={'id':'a'*32,'role':'member'};first=activity.listing(self.ctx.state,user,{'limit':2});second=activity.listing(self.ctx.state,user,{'limit':2,'before':first['next_before']})
  self.assertEqual(len(first['events'])+len(second['events']),4);self.assertFalse(set(v['id'] for v in first['events'])&set(v['id'] for v in second['events']))
 def test_no_arbitrary_audit_body_or_secret_fields(self):
  with self.assertRaises(TypeError):activity.record(self.ctx.state,A,'files.upload',password='not stored')
  with self.assertRaises(ValueError):activity.record(self.ctx.state,A,'https://user@example.org/path?key=secret')
 def test_accounting_deduplicates_hardlinks_and_skips_links(self):
  folder=self.root/'files';folder.mkdir();(folder/'image.jpg').write_bytes(b'abc');os.link(folder/'image.jpg',folder/'copy.jpg');outside=self.root/'secret.mp4';outside.write_bytes(b'not counted');(folder/'linked.mp4').symlink_to(outside)
  result=measure(folder);self.assertTrue(result['complete']);self.assertEqual(result['bytes'],3);self.assertEqual(result['files'],1);self.assertEqual(result['types'],{'images':3})
 def test_accounting_limits_are_reported_as_partial(self):
  folder=self.root/'files';folder.mkdir();(folder/'a').write_bytes(b'a');(folder/'b').write_bytes(b'b');self.assertFalse(measure(folder,limit=1)['complete'])
 def test_context_does_not_leak_between_requests(self):
  with using(A):self.assertEqual(current(),A)
  self.assertIsNone(current())

 def test_job_retry_does_not_change_requesting_identity(self):
  with using(A):ident=self.ctx.state.enqueue('files.transfer',{})
  self.ctx.state.finish(ident,error='fixture')
  with using(B),self.assertRaises(ValueError):self.ctx.state.retry(ident)
  with using(A):self.ctx.state.retry(ident)
 def test_root_job_audit_does_not_expose_other_users(self):
  from types import SimpleNamespace
  from freeqnap.nas.backend import Backend
  activity.record(self.ctx.state,A,'job.files.transfer');activity.record(self.ctx.state,B,'job.files.recycle');activity.record(self.ctx.state,'system','system.boot-observed',scope='system')
  backend=SimpleNamespace(ctx=self.ctx)
  with using(A):self.assertEqual(len(Backend.job_activity(backend,{})),1);self.assertEqual(len(Backend.job_activity(backend,{'administrator':True})),2)
 def test_http_activity_is_private_and_internal_envelope_is_forbidden(self):
  import http.client,threading
  from http.server import ThreadingHTTPServer
  from freeqnap import auth,accounts
  from freeqnap.server import handler
  state=State(self.root/'console');state.set('administrator',auth.password_hash('fixture private password'));token,_=auth.login(state,'fixture private password');admin=auth.session(state,token)['user'];member_id=accounts.change(state,admin,{'action':'create','username':'member','label':'Member','password':'fixture second password','permissions':[]})['id']
  with state.connect() as db:db.execute('UPDATE local_accounts SET must_change=0 WHERE id=?',(member_id,))
  member,member_csrf=accounts.login(state,'member','fixture second password');activity.record(state,'user:'+admin['id'],'files.mkdir');activity.record(state,'user:'+member_id,'photos.catalog')
  class Broker:
   def request(self,action,payload):
    if action=='access.invoke':return self.request(payload['action'],payload['payload'])
    if action in ('activity.system','activity.jobs'):return []
    raise ValueError('Unexpected fixture operation')
  server=ThreadingHTTPServer(('127.0.0.1',0),handler(state,self.root/'backups',broker=Broker()));threading.Thread(target=server.serve_forever,daemon=True).start();self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
  def get(path,cookie):
   connection=http.client.HTTPConnection('127.0.0.1',server.server_port);connection.request('GET',path,headers={'Cookie':'freeqnap_session='+cookie});response=connection.getresponse();data=json.loads(response.read());connection.close();return response.status,data
  code,data=get('/api/activity',member);self.assertEqual(code,200);self.assertNotIn('user:'+admin['id'],{v['actor'] for v in data['events']});self.assertTrue(any(v['operation']=='account.local-login' for v in data['events']));self.assertEqual(get('/api/users/usage',member)[0],403)
  connection=http.client.HTTPConnection('127.0.0.1',server.server_port);body=json.dumps({'actor':'user:'+admin['id'],'action':'files.read','payload':{}});connection.request('POST','/api/nas/access.invoke',body,headers={'Cookie':'freeqnap_session='+member,'Content-Type':'application/json','X-CSRF-Token':member_csrf,'Origin':'http://127.0.0.1:'+str(server.server_port)});response=connection.getresponse();self.assertEqual(response.status,403);response.read();connection.close()

 def test_shared_health_names_component_without_leaking_private_title(self):
  import time
  from types import SimpleNamespace
  from freeqnap.nas.health import Health,fault
  from freeqnap.nas.backend import Backend
  health=Health(self.ctx);health.reconcile('schedules',[fault('private-user-library','critical','Private owner and folder details')],time.time())
  result=Backend.system_activity(SimpleNamespace(ctx=self.ctx));text=json.dumps(result)
  self.assertIn('Scheduled backups',text);self.assertIn('critical',text);self.assertNotIn('Private owner',text);self.assertNotIn('private-user-library',text)

 def test_status_polling_is_retained_but_optional_in_human_view(self):
  activity.record(self.ctx.state,A,'nas.photos.status');activity.record(self.ctx.state,A,'files.mkdir');user={'id':'a'*32,'role':'member'}
  self.assertEqual(len(activity.listing(self.ctx.state,user,{})['events']),1);self.assertEqual(len(activity.listing(self.ctx.state,user,{'include_polls':1})['events']),2)
