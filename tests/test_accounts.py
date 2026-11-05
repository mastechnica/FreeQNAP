import base64,hashlib,http.client,importlib.util,json,tempfile,threading,time,unittest,urllib.parse
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from freeqnap import auth,accounts,library_shares
from freeqnap.state import State
from freeqnap.identity import Identity
from freeqnap.personal_access import Gateway
from freeqnap.nas.personal import Personal
from freeqnap.nas.common import Context
from freeqnap.nas.myradio import MyRadio
from freeqnap.nas.personal_photos import PersonalPhotos
from freeqnap.server import handler

PASSWORD='fixture private password'
class Fixture(Context):
 def volume(self,key):
  value=self.config()['pools'][key];return value,Path(value['mountpoint'])
class Device:
 def __init__(self,root):
  self.ctx=Fixture(root/'broker');volume=root/'data';volume.mkdir();cfg=self.ctx.config();cfg['pools']['data']={'name':'data','mountpoint':str(volume),'filesystem_uuid':'fixture-volume','read_only':False};self.ctx.save(cfg);self.my_radio=MyRadio(self.ctx);self.personal_photos=PersonalPhotos(self.ctx);self.personal=Personal(self);self.calls=[]
 def request(self,action,payload=None):
  if action=='access.invoke':
   from freeqnap.access_scope import using
   with using(payload['actor']):return self.request(payload['action'],payload['payload'])
  self.calls.append(action);payload=payload or {}
  if action=='personal.invoke':return self.personal.invoke(payload)
  if action=='personal.control':return self.personal.control(payload)
  if action=='personal.shared':return self.personal.shared(payload)
  if action=='myradio.status':return self.my_radio.status()
  if action=='photos.status':return self.personal_photos.status()
  if action=='personal.options':return {'shares':list(self.ctx.config()['shares'].values()),'pools':self.ctx.config()['pools']}
  if action=='nas.status':return {'fixture':True,'shares':[],'pools':[]}
  raise ValueError('Unavailable fixture operation')

class AccountsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.state=State(self.root/'console');self.state.set('administrator',auth.password_hash(PASSWORD));self.token,self.csrf=auth.login(self.state,PASSWORD);self.admin=auth.session(self.state,self.token)['user'];self.device=Device(self.root)
 def user(self,name='alice',permissions=None):
  result=accounts.change(self.state,self.admin,{'action':'create','username':name,'label':name.title(),'password':PASSWORD,'permissions':permissions if permissions is not None else accounts.DEFAULT})
  with self.state.connect() as db:row=db.execute('SELECT * FROM local_accounts WHERE id=?',(result['id'],)).fetchone()
  accounts.change_password(self.state,accounts.public(row),{'current_password':PASSWORD,'password':PASSWORD+' updated'})
  token,csrf=auth.login(self.state,PASSWORD+' updated',name);return auth.session(self.state,token)['user'],token,csrf
 def gateway(self,token,share=None,managed=None):return Gateway(self.device,self.state,lambda:auth.session(self.state,token),share,managed)
 def configure(self,user,token,kind='radio'):
  gateway=self.gateway(token);plan=gateway.request('library.storage-plan',{'library':kind,'pool':'data','folder':'My Radio' if kind=='radio' else 'Memories'});job=gateway.request('library.storage-apply',{'plan_id':plan['id'],'digest':plan['digest'],'confirmation':plan['confirmation']});self.device.personal.one();scope=self.device.personal.get(user['id']);result=scope['ctx'].state.jobs()[0];self.assertEqual(result['status'],'succeeded');return scope
 def test_legacy_admin_login_and_cookie_migrate_without_default_password(self):
  self.assertEqual(self.admin['username'],'admin');self.assertEqual(self.admin['role'],'administrator');self.assertFalse(self.admin['must_change']);self.assertIsNone(auth.login(self.state,'wrong password'))
  with self.assertRaises(ValueError):accounts.change(self.state,self.admin,{'action':'update','id':self.admin['id'],'enabled':False})
 def test_temporary_password_and_role_changes_revoke_sessions_and_retain_identity(self):
  a,token,_=self.user();self.assertEqual(a['role'],'member');ident=a['id'];accounts.change(self.state,self.admin,{'action':'update','id':ident,'label':'New name','enabled':False});self.assertIsNone(auth.session(self.state,token));self.assertIsNone(auth.login(self.state,PASSWORD+' updated','alice'));self.assertEqual(next(v for v in accounts.listing(self.state)['users'] if v['id']==ident)['label'],'New name')
  self.assertNotIn(PASSWORD,self.state.database.read_bytes().decode('latin1'))
 def test_personal_namespaces_and_icloud_settings_are_isolated(self):
  a,at,_=self.user();b,bt,_=self.user('bob');sa=self.configure(a,at);sb=self.configure(b,bt)
  self.assertTrue(sa['radio'].config()['folder'].startswith('Users/'+a['id']+'/'));self.assertNotEqual(sa['ctx'].directory,sb['ctx'].directory)
  self.gateway(at).request('photos.icloud-save',{'account':'alice@example.invalid','enabled':False});self.gateway(bt).request('photos.icloud-save',{'account':'bob@example.invalid','enabled':False});self.assertEqual(self.gateway(at).request('photos.icloud-status')['settings']['account'],'alice@example.invalid');self.assertNotIn('bob@example.invalid',json.dumps(self.gateway(at).request('photos.icloud-status')))
  self.assertNotEqual(sa['ctx'].directory/'personal-icloud-sessions',sb['ctx'].directory/'personal-icloud-sessions')
 def test_member_cannot_select_other_user_pool_files_or_internal_envelope(self):
  a,at,_=self.user();b,bt,_=self.user('bob');self.configure(a,at);self.configure(b,bt)
  for operation,payload in [('personal.invoke',{'owner':b['id']}),('network.plan',{}),('files.list',{'share':'pool:data'}),('myradio.import-folder',{'category':'music','share':'pool:data','path':''})]:
   with self.assertRaises((PermissionError,ValueError)):self.gateway(at).request(operation,payload)
  with self.assertRaises(PermissionError):self.gateway(at,managed=b['id']).request('myradio.status')
 def test_family_file_manager_can_upload_only_into_own_visible_container(self):
  a,at,_=self.user();scope=self.configure(a,at)
  with patch('os.fchown'):self.gateway(at).request('files.mkdir',{'share':'my-radio','path':'','name':'USB import'})
  self.assertTrue((self.root/'data'/scope['radio'].config()['location_folder']/'USB import').is_dir())
  with self.assertRaises(ValueError):self.gateway(at).request('files.list',{'share':'my-radio','path':'.freeqnap-myradio'})
 def test_shared_content_is_separate_readonly_and_revocation_takes_effect(self):
  a,at,_=self.user();b,bt,_=self.user('bob');sa=self.configure(a,at);sb=self.configure(b,bt)
  from test_myradio import rename
  with patch('freeqnap.nas.myradio.rename_exclusive',rename):
   v=sa['radio'].upload_begin({'category':'books','name':'book.txt','bytes':5});sa['radio'].upload_chunk({'upload_id':v['upload_id'],'offset':0,'data_base64':'aGVsbG8='});item=sa['radio'].upload_finish({'upload_id':v['upload_id']})['item']
  library_shares.change(self.state,a,{'action':'share','recipient':b['id'],'kind':'books'});share=library_shares.listing(self.state,b)['shared_with_me'][0]['id'];g=self.gateway(bt,share)
  self.assertEqual(g.request('myradio.book-text',{'id':item['id']})['text'],'hello');self.assertEqual(sb['radio'].catalog({'category':'books'})['total'],0)
  with self.assertRaises(PermissionError):g.request('myradio.metadata',{'id':item['id'],'metadata':{'title':'changed'}})
  library_shares.change(self.state,a,{'action':'revoke','id':share})
  with self.assertRaises(PermissionError):g.request('myradio.read',{'id':item['id']})
 def test_photo_item_album_map_and_original_scope_never_include_unshared_files(self):
  a,at,_=self.user();b,bt,_=self.user('bob');sa=self.configure(a,at,'photos');p=sa['photos'];p.extract=lambda fd,t:{'latitude':45.,'longitude':-73.,'taken':'2025-01-01'};p.preview=lambda fd,large:b'jpeg'
  one=p.ingest('one','1','one.jpg',lambda offset:iter([b'one'[offset:]]),3)['id'];two=p.ingest('two','1','two.jpg',lambda offset:iter([b'two'[offset:]]),3)['id'];album=p.album({'title':'Selected family album'})['id'];p.album_add({'id':one,'album':album})
  for scope in [{'mode':'items','ids':[one]},{'mode':'albums','ids':[album]}]:
   library_shares.change(self.state,a,{'action':'share','recipient':b['id'],'kind':'photos','scope':scope});share=library_shares.listing(self.state,b)['shared_with_me'][0]['id'];g=self.gateway(bt,share);catalog=g.request('photos.catalog',{})
   self.assertEqual([v['id'] for v in catalog['items']],[one]);self.assertEqual(catalog['years'][0]['count'],1);self.assertEqual(g.request('photos.places',{})['total'],1);self.assertEqual(base64.b64decode(g.request('photos.read',{'id':one})['data_base64']),b'one')
   with self.assertRaises(ValueError):g.request('photos.read',{'id':two})
   self.assertNotIn('account',json.dumps(g.request('photos.icloud-status')))
 def test_own_grants_and_disabled_accounts_override_share_access(self):
  a,at,_=self.user(permissions=['myradio.read']);g=self.gateway(at)
  with self.assertRaises(PermissionError):g.request('myradio.upload-begin',{})
  accounts.change(self.state,self.admin,{'action':'update','id':a['id'],'enabled':False})
  with self.assertRaises(PermissionError):g.request('myradio.status')
 def test_http_member_cannot_read_admin_data_or_forge_internal_owner(self):
  user,token,csrf=self.user();server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.state,self.root/'backups',snapshot=self.root/'inventory.json',broker=self.device));server.auth_lock=threading.Lock();server.login_attempts=[];threading.Thread(target=server.serve_forever,daemon=True).start();self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
  def request(path,body=None):
   c=http.client.HTTPConnection('127.0.0.1',server.server_port);headers={'Host':'127.0.0.1:'+str(server.server_port),'Origin':'http://127.0.0.1:'+str(server.server_port),'Content-Type':'application/json','Cookie':'freeqnap_session='+token,'X-CSRF-Token':csrf};c.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,headers);r=c.getresponse();v=r.status,json.loads(r.read());c.close();return v
  self.assertEqual(request('/api/users')[0],403);self.assertEqual(request('/api/identity')[0],403);self.assertEqual(request('/api/nas/personal.invoke',{'owner':self.admin['id']})[0],403);self.assertEqual(request('/api/nas/network.plan',{})[0],403);self.assertEqual(request('/api/account')[1]['user']['id'],user['id']);self.assertTrue(request('/api/nas/status')[1]['personal_only'])
  with patch('freeqnap.system_summary.inventory.snapshot',return_value={'sampled_at':time.time(),'stale':False,'errors':[],'disks':[{'name':'sda','path':'/dev/sda','type':'disk','size':100,'model':'Test SATA','serial':'private-device-serial'}]}):
   code,summary=request('/api/status');self.assertEqual(code,200);self.assertEqual(summary['inventory']['disks'][0]['model'],'Test SATA');self.assertNotIn('private-device-serial',json.dumps(summary));self.assertTrue(summary['inventory']['health']['monitor_stale'])
  self.assertEqual(request('/api/nas/health.alerts',{})[0],403);self.assertEqual(request('/api/nas/system.frontpanel',{})[0],403)
  accounts.save_preferences(self.state,user,{'landing_page':'photos-shared'});self.assertEqual(request('/api/login',{'username':'alice','password':PASSWORD+' updated'})[1]['landing_page'],'/#photos?view=shared');self.assertEqual(request('/api/login',{'username':'admin','password':PASSWORD})[1]['landing_page'],'/#overview')

 def test_dedicated_files_and_admin_shared_folder_rights_remain_separate(self):
  a,at,_=self.user();b,bt,_=self.user('bob');g=self.gateway(at);plan=g.request('library.files-plan',{'pool':'data','folder':'My files'});g.request('library.files-apply',{'plan_id':plan['id'],'digest':plan['digest'],'confirmation':plan['confirmation']});scope=self.device.personal.get(a['id']);self.assertTrue(scope['ctx'].state.setting('personal-files')['folder'].startswith('Users/'+a['id']+'/'))
  directory=self.root/'data'/'Family';directory.mkdir();(directory/'read.txt').write_text('family');cfg=self.device.ctx.config();cfg['shares']['family']={'name':'family','pool':'data','path':str(directory),'gid':0};self.device.ctx.save(cfg);pin={'share':'family','pool':'data','path':str(directory),'filesystem_uuid':'fixture-volume','access':'read'};accounts.set_storage(self.state,self.admin,a['id'],[pin]);self.assertEqual(g.request('files.list',{'share':'family'})['total_entries'],1)
  with self.assertRaises(ValueError):g.request('files.mkdir',{'share':'family','name':'blocked'})
  with self.assertRaises(ValueError):self.gateway(bt).request('files.list',{'share':'family'})
  accounts.set_storage(self.state,self.admin,a['id'],[{**pin,'access':'write'}])
  with patch('os.fchown'):g.request('files.mkdir',{'share':'family','name':'allowed'})
  accounts.set_storage(self.state,self.admin,a['id'],[])
  with self.assertRaises(ValueError):g.request('files.list',{'share':'family'})
  self.assertTrue((directory/'read.txt').exists())


 def test_photo_map_preference_is_private_boolean_and_does_not_change_landing(self):
  a,at,_=self.user(permissions=['photos.read']);b,bt,_=self.user('bob',permissions=['photos.read'])
  self.assertFalse(accounts.photo_maps(self.state,a)['online']);accounts.save_preferences(self.state,a,{'photo_online_maps':True});self.assertTrue(accounts.photo_maps(self.state,a)['online']);self.assertFalse(accounts.photo_maps(self.state,b)['online']);self.assertEqual(accounts.landing(self.state,a)['href'],'/#overview')
  accounts.save_preferences(self.state,a,{'photo_online_maps':False});self.assertFalse(accounts.photo_maps(self.state,a)['online'])
  for payload in ({'photo_online_maps':'yes'},{'photo_online_maps':True,'user_id':b['id']}):
   with self.assertRaises(ValueError):accounts.save_preferences(self.state,a,payload)

 def test_administrator_landing_is_locked_to_overview(self):
  value=accounts.landing(self.state,self.admin);self.assertTrue(value['locked']);self.assertEqual(value['href'],'/#overview')
  with self.assertRaises(ValueError):accounts.save_preferences(self.state,self.admin,{'landing_page':'photos'})
 def test_family_landing_is_private_persistent_and_permission_aware(self):
  a,at,_=self.user(permissions=['photos.read']);b,bt,_=self.user('bob',permissions=['files.read']);self.assertEqual(accounts.landing(self.state,a)['href'],'/#overview');accounts.save_preferences(self.state,a,{'landing_page':'photos-shared'});self.assertEqual(accounts.landing(self.state,a)['href'],'/#photos?view=shared');self.assertEqual(accounts.landing(self.state,b)['href'],'/#overview')
  with self.assertRaises(ValueError):accounts.save_preferences(self.state,b,{'landing_page':'photos'})
  accounts.change(self.state,self.admin,{'action':'update','id':a['id'],'permissions':['files.read']});a=next(u for u in accounts.listing(self.state)['users'] if u['id']==a['id']);self.assertEqual(accounts.landing(self.state,a)['href'],'/#overview')
 def test_landing_rejects_external_urls_other_users_and_admin_routes(self):
  user,_,_=self.user()
  for value in ['https://example.invalid','//example.invalid','settings/users','storage','vpn']:
   with self.assertRaises(ValueError):accounts.save_preferences(self.state,user,{'landing_page':value})
  with self.assertRaises(ValueError):accounts.save_preferences(self.state,user,{'landing_page':'photos','user_id':self.admin['id']})

 def test_shared_plain_usb_is_browsable_but_private_user_roots_are_not(self):
  a,token,_=self.user();cfg=self.device.ctx.config();cfg['pools']['data']['kind']='usb';cfg['pools']['data']['encrypted']=False;self.device.ctx.save(cfg);root=Path(cfg['pools']['data']['mountpoint']);(root/'public.txt').write_text('shared');(root/'Users/bob').mkdir(parents=True);(root/'Users/bob/private.txt').write_text('private');gateway=self.gateway(token)
  listed=gateway.request('files.list',{'share':'pool:data'});self.assertIn('public.txt',[v['name'] for v in listed['entries']]);self.assertNotIn('Users',[v['name'] for v in listed['entries']])
  self.assertEqual(base64.b64decode(gateway.request('files.read',{'share':'pool:data','path':'public.txt','offset':0,'count':100})['data_base64']),b'shared')
  with self.assertRaises(ValueError):gateway.request('files.read',{'share':'pool:data','path':'Users/bob/private.txt','offset':0,'count':100})
  with self.assertRaises(ValueError):gateway.request('photos.import-folder',{'share':'pool:data','folder':'Users/bob'})
  with self.assertRaises(ValueError):gateway.request('myradio.import-folder',{'share':'pool:data','path':'Users/bob','category':'music'})
 def test_library_folder_picker_is_scoped_to_the_family_user(self):
  a,token,_=self.user();b,other,_=self.user('bob');self.configure(a,token);self.configure(b,other);data=self.gateway(token).request('library.folders',{'pool':'data','path':''});self.assertIn('My Radio',[v['name'] for v in data['entries']]);self.assertNotIn(b['id'],str(data))
  with self.assertRaises(ValueError):self.gateway(token).request('library.folders',{'pool':'data','path':'../'+b['id']})

@unittest.skipUnless(importlib.util.find_spec('jwt'),'Optional PyJWT dependency')
class IdentityTests(unittest.TestCase):
 def setUp(self):
  AccountsTests.setUp(self);from cryptography.hazmat.primitives.asymmetric import rsa
  self.key=rsa.generate_private_key(public_exponent=65537,key_size=2048);import jwt
  self.jwk=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()));self.jwk.update(kid='fixture',use='sig',alg='RS256');self.issuer='https://auth.example.invalid/application/o/freeqnap/';self.config={'enabled':True,'issuer':self.issuer,'client_id':'fixture-client','client_secret':'private-client-secret','redirect_uri':'https://nas.example.invalid/auth/oidc/callback','session_minutes':60};self.identity=Identity(self.state,['https://nas.example.invalid']);self.state.set('oidc-provider',self.config)
  self.discovery={'issuer':self.issuer,'authorization_endpoint':'https://auth.example.invalid/authorize','token_endpoint':'https://auth.example.invalid/token','jwks_uri':'https://auth.example.invalid/keys','id_token_signing_alg_values_supported':['RS256']};self.claims=None
 def fetch(self,url,data=None,headers=None):
  if url.endswith('openid-configuration'):return self.discovery
  if url.endswith('/keys'):return {'keys':[self.jwk]}
  if url.endswith('/token'):
   import jwt
   return {'id_token':jwt.encode(self.claims,self.key,algorithm='RS256',headers={'kid':'fixture'})}
  raise AssertionError('Unexpected fixture request')
 def begin(self,user=None):
  with patch('freeqnap.identity.fetch',side_effect=self.fetch):url,binding=self.identity.begin(user)
  query=urllib.parse.parse_qs(urllib.parse.urlsplit(url).query);self.claims={'iss':self.issuer,'aud':'fixture-client','sub':'cloud-subject','iat':int(time.time()),'exp':int(time.time())+300,'nonce':query['nonce'][0]};return query['state'][0],binding
 def test_signed_link_login_replay_and_optional_local_fallback(self):
  state,binding=self.begin(self.admin)
  with patch('freeqnap.identity.fetch',side_effect=self.fetch):self.assertTrue(self.identity.finish(state,'code',binding)['linked'])
  state,binding=self.begin()
  with patch('freeqnap.identity.fetch',side_effect=self.fetch):result=self.identity.finish(state,'code',binding)
  self.assertEqual(auth.session(self.state,result['token'])['user']['id'],self.admin['id']);self.assertEqual(result['landing_page'],'/#overview')
  with self.assertRaises(ValueError):self.identity.finish(state,'code',binding)
  self.identity.save(self.admin,{'enabled':False});self.assertIsNone(auth.session(self.state,result['token']));self.assertIsNotNone(auth.login(self.state,PASSWORD));self.assertNotIn('private-client-secret',json.dumps(self.identity.status()))
 def test_binding_nonce_audience_and_unlinked_identity_fail_closed(self):
  state,binding=self.begin()
  with self.assertRaises(ValueError):self.identity.finish(state,'code','wrong-browser')
  for key,bad in [('nonce','wrong'),('aud','wrong'),('exp',int(time.time())-1000),('iss','https://other.example/')]:
   state,binding=self.begin(self.admin);self.claims[key]=bad
   with patch('freeqnap.identity.fetch',side_effect=self.fetch):
    with self.assertRaises(ValueError):self.identity.finish(state,'code',binding)
  state,binding=self.begin()
  with patch('freeqnap.identity.fetch',side_effect=self.fetch):
   with self.assertRaisesRegex(ValueError,'No local account'):self.identity.finish(state,'code',binding)
 def test_issuer_endpoint_origin_and_callback_are_pinned(self):
  with patch('freeqnap.identity.fetch',side_effect=self.fetch):self.identity.save(self.admin,self.config)
  self.discovery['token_endpoint']='https://evil.example/token'
  with patch('freeqnap.identity.fetch',side_effect=self.fetch):
   with self.assertRaises(ValueError):self.identity.discovery(self.config)
  with self.assertRaises(ValueError):self.identity.save(self.admin,{**self.config,'redirect_uri':'https://evil.example/auth/oidc/callback'})


class CloudLocalPasswordTests(IdentityTests):
 def assign(self,**extra):
  with patch('freeqnap.identity.fetch',side_effect=self.fetch):return self.identity.assign(self.admin,{'current_password':PASSWORD,'subject':'cloud-subject','username':'matt','label':'Matt','permissions':['photos.read','files.read'],**extra})
 def cloud_login(self):
  state,binding=self.begin()
  with patch('freeqnap.identity.fetch',side_effect=self.fetch):result=self.identity.finish(state,'code',binding)
  return auth.session(self.state,result['token']),result['token']
 def test_explicit_cloud_family_profile_enables_offline_password_without_new_identity(self):
  assigned=self.assign();ident=assigned['user']['id'];self.assertFalse(assigned['user']['local_password_enabled']);self.assertEqual(assigned['user']['role'],'member');self.assertIsNone(auth.login(self.state,PASSWORD,'matt'))
  session,token=self.cloud_login();self.assertTrue(session['recent_oidc']);self.assertEqual(session['user']['id'],ident)
  request={'password':'separate local fixture password','confirm_password':'separate local fixture password','different_password_ack':True}
  for bad in [{**request,'different_password_ack':False},{**request,'confirm_password':'wrong'}]:
   with self.assertRaises(ValueError):accounts.configure_local_password(self.state,session,bad)
  result,new_token=accounts.configure_local_password(self.state,session,request);self.assertEqual(result['user']['id'],ident);self.assertEqual(result['user']['permissions'],['files.read','photos.read']);self.assertIsNone(auth.session(self.state,token));self.assertIsNotNone(auth.session(self.state,new_token))
  with patch('freeqnap.identity.fetch',side_effect=ValueError('Provider offline')):local,csrf=auth.login(self.state,request['password'],'matt')
  self.assertEqual(auth.session(self.state,local)['user']['id'],ident)
 def test_local_session_and_stale_cloud_session_cannot_reset_without_recent_cloud_proof(self):
  self.assign();session,token=self.cloud_login();r={'password':'new separate local fixture','confirm_password':'new separate local fixture','different_password_ack':True}
  with self.state.connect() as db:db.execute('UPDATE recent_cloud_auth SET authenticated_at=?',(time.time()-301,))
  with self.assertRaises(PermissionError):accounts.configure_local_password(self.state,auth.session(self.state,token),r)
  with self.assertRaises(PermissionError):accounts.configure_local_password(self.state,auth.session(self.state,self.token),r)
  fresh,_=self.cloud_login();accounts.configure_local_password(self.state,fresh,r)
 def test_existing_administrator_link_preserves_password_role_and_profile(self):
  before=self.state.setting('administrator');assigned=self.assign(user_id=self.admin['id']);self.assertEqual(assigned['user']['id'],self.admin['id']);self.assertEqual(assigned['user']['role'],'administrator');self.assertEqual(self.state.setting('administrator'),before);session,_=self.cloud_login();self.assertEqual(session['user']['id'],self.admin['id']);self.assertIsNotNone(auth.login(self.state,PASSWORD))
  with self.assertRaises(ValueError):self.assign(user_id=self.admin['id'])
 def test_assignment_requires_admin_password_and_rolls_back_bad_subject_or_existing_username(self):
  with self.assertRaises(PermissionError):self.assign(current_password='wrong')
  with self.assertRaises(ValueError):self.assign(subject='bad\nsubject')
  with self.assertRaises(ValueError):self.assign(username='admin')
  with self.state.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM external_identities').fetchone()[0],0)
 def test_admin_local_password_reset_does_not_break_verified_cloud_login(self):
  assigned=self.assign();accounts.change(self.state,self.admin,{'action':'set-password','id':assigned['user']['id'],'password':'admin temporary fixture password'});cloud,_=self.cloud_login();self.assertFalse(cloud['user']['must_change']);self.assertTrue(cloud['user']['local_password_change_required']);request={'password':'user independent new password','confirm_password':'user independent new password','different_password_ack':True};result,_=accounts.configure_local_password(self.state,cloud,request);self.assertFalse(result['user']['must_change']);self.assertIsNotNone(auth.login(self.state,request['password'],'matt'))

 def test_revocation_between_request_and_password_write_is_rechecked(self):
  assigned=self.assign();session,_=self.cloud_login();accounts.change(self.state,self.admin,{'action':'revoke-sessions','id':assigned['user']['id']})
  with self.assertRaises(PermissionError):accounts.configure_local_password(self.state,session,{'password':'separate new fixture password','confirm_password':'separate new fixture password','different_password_ack':True})
