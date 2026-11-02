import ast,http.client,json,tempfile,threading,time,unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from freeqnap import auth
from freeqnap.agents import Agents,Denied,Limited,OPERATIONS,BACKEND_OPERATIONS,PRESETS
from freeqnap.server import handler
from freeqnap.state import State

class AgentTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.state=State(Path(self.tmp.name));self.agents=Agents(self.state)
 def issue(self,grants):
  v=self.agents.issue({'name':'test agent','grants':grants,'days':1});return v,self.agents.authenticate('Bearer '+v['token'])
 def test_catalog_matches_exact_backend_and_presets_are_explicit(self):
  tree=ast.parse(Path('freeqnap/nas/backend.py').read_text());fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='dispatch')
  direct=next(n.value for n in fn.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='direct' for t in n.targets))
  queued=next(n for n in fn.body if isinstance(n,ast.If) and isinstance(n.test,ast.Compare) and isinstance(n.test.left,ast.Name) and n.test.left.id=='action' and isinstance(n.test.comparators[0],ast.Tuple))
  expected={k.value for k in direct.keys}|set(ast.literal_eval(queued.test.comparators[0]));self.assertEqual(BACKEND_OPERATIONS,expected)
  for ops in PRESETS.values():self.assertTrue(set(ops)<=OPERATIONS)
 def test_only_hash_persisted_revoke_expiry_unknown(self):
  token,p=self.issue(['media.catalog'])
  self.assertNotIn(token['token'],self.state.database.read_bytes().decode('latin1'))
  self.assertNotIn('token_hash',json.dumps(self.agents.listing()))
  self.agents.revoke({'id':token['id']})
  with self.assertRaises(Denied):self.agents.authenticate('Bearer '+token['token'])
  token,p=self.issue(['media.catalog'])
  with self.state.connect() as db:db.execute('UPDATE agent_tokens SET expires=0 WHERE id=?',(p['id'],))
  with self.assertRaises(Denied):self.agents.authenticate('Bearer '+token['token'])
  for v in ['Bearer wrong','',None,'Bearer fqn_'+'a'*10000]:
   with self.assertRaises(Denied):self.agents.authenticate(v)
 def test_default_deny_plan_ownership_revocation_and_audit_privacy(self):
  class Broker:
   def __init__(self):self.calls=[]
   def request(self,op,payload):self.calls.append((op,payload));return {'id':'a'*32,'digest':'hash','confirmation':'EXACT'} if op.endswith('plan') else {'accepted':True}
  b=Broker();t,a=self.issue(['system.plan','system.apply']);_,other=self.issue(['system.apply'])
  for op in ['nas.status','media.catalog','shell.run','credential.issue']:
   with self.assertRaises(Denied):self.agents.invoke(a,op,{},b)
  self.assertFalse(b.calls);plan=self.agents.invoke(a,'system.plan',{'operation':'shutdown'},b)
  payload={'plan_id':plan['id'],'digest':'hash','confirmation':'EXACT','secret':'DO NOT LOG'}
  with self.assertRaises(Denied):self.agents.invoke(other,'system.apply',payload,b)
  self.agents.invoke(a,'system.apply',payload,b)
  self.assertNotIn('DO NOT LOG',json.dumps(self.agents.listing()))
  self.agents.revoke({'id':a['id']})
  with self.assertRaises(Denied):self.agents.invoke(a,'system.apply',payload,b)
 def test_no_grant_wildcards_and_rate_limit(self):
  for grants in [[],['*'],['media.*'],['unknown'],[{}]]:
   with self.assertRaises(ValueError):self.agents.issue({'name':'bad','grants':grants})
  token,_=self.issue(['media.catalog'])
  with self.state.connect() as db:db.execute('UPDATE agent_tokens SET hits=120,window=?',(time.time(),))
  with self.assertRaises(Limited):self.agents.authenticate('Bearer '+token['token'])
 def test_http_token_boundary_csrf_and_https(self):
  test=self
  class Broker:
   def request(self,op,payload):test.assertEqual(op,'media.catalog');return {'entries':[]}
  self.state.set('administrator',auth.password_hash('fixture private password'));cookie,csrf=auth.login(self.state,'fixture private password')
  server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.state,Path(self.tmp.name)/'backups',broker=Broker()));threading.Thread(target=server.serve_forever,daemon=True).start();self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
  def request(path,method='GET',body=None,**headers):
   c=http.client.HTTPConnection('127.0.0.1',server.server_port);h={'Host':'127.0.0.1:'+str(server.server_port),'Content-Type':'application/json'};h.update(headers);c.request(method,path,body=json.dumps(body) if body is not None else None,headers=h);r=c.getresponse();v=r.status,json.loads(r.read());c.close();return v
  token,_=self.issue(['media.catalog']);h={'Authorization':'Bearer '+token['token'],'X-Forwarded-Proto':'https'}
  self.assertEqual(request('/api/agent/v1',**h)[0],200)
  self.assertEqual(request('/api/agent/v1',Authorization=h['Authorization'])[0],403)
  self.assertEqual(request('/api/agent/v1',Origin='https://attacker.invalid',**h)[0],403)
  self.assertEqual(request('/api/agent/v1/operations/media.catalog','POST',{'library':'movies'},**h)[0],200)
  self.assertEqual(request('/api/agent/v1/operations/system.apply','POST',{},**h)[0],403)
  self.assertEqual(request('/api/nas/status',**h)[0],401)
  self.assertEqual(request('/api/agents/create','POST',{'name':'bad','grants':['nas.status']},**h)[0],403)
  admin={'Cookie':'freeqnap_session='+cookie,'Origin':'http://127.0.0.1:'+str(server.server_port)}
  self.assertEqual(request('/api/agents/create','POST',{'name':'owner issued','grants':['media.catalog']},**admin)[0],403)
  admin['X-CSRF-Token']=csrf
  self.assertEqual(request('/api/agents/create','POST',{'name':'owner issued','grants':['media.catalog']},**admin)[0],200)
