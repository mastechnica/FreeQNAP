import base64,http.client,json,tempfile,threading,time,unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from freeqnap import auth,radio_catalog
from freeqnap.state import State
from freeqnap.server import handler
from test_radio_catalog import Gateway,item
class HubHTTPTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.state=State(self.root/'state');self.state.set('administrator',auth.password_hash('private fixture password'));self.token,self.csrf=auth.login(self.state,'private fixture password');self.model=Gateway(self.state);self.model.owner=auth.session(self.state,self.token)['user']['id'];self.model.rows=[item(1,track='2'),item(2,track='1'),item(3,'books',author='Writer',book_type='audiobook',playable='audio')];radio_catalog._CACHE.clear();test=self
  class Broker:
   def request(self,op,payload):
    if op=='access.invoke':return self.request(payload['action'],payload['payload'])
    return test.model._request(op,payload)
  self.server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.state,self.root/'backups',broker=Broker()));threading.Thread(target=self.server.serve_forever,daemon=True).start();self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
 def request(self,path,payload=None,token=True,csrf=True,**headers):
  c=http.client.HTTPConnection('127.0.0.1',self.server.server_port);host='127.0.0.1:'+str(self.server.server_port);h={'Host':host,'Origin':'http://'+host}
  if token:h['Cookie']='freeqnap_session='+self.token
  if payload is not None:h.update({'Content-Type':'application/json','X-CSRF-Token':self.csrf if csrf else 'bad'})
  h.update(headers);c.request('POST' if payload is not None else 'GET',path,json.dumps(payload) if payload is not None else None,h);r=c.getresponse();value=(r.status,dict(r.getheaders()),r.read());c.close();return value
 def post(self,op,data):
  code,h,raw=self.request('/api/nas/'+op,data);self.assertEqual(code,200,raw);return json.loads(raw)
 def test_album_overview_and_book_organization_routes(self):
  r=self.post('myradio.music-browser',{});self.assertEqual(r['total'],1);a=r['items'][0];detail=self.post('myradio.music-browser',{'album':a['id']});self.assertEqual(detail['album']['tracks'][0]['id'],'2'.zfill(32));self.assertEqual(self.post('myradio.overview',{})['stats']['total_seconds'],0)
  self.post('myradio.metadata',{'id':'3'.zfill(32),'metadata':{'series':'Series','series_number':'1','collections':['Family favorites']}});self.assertEqual(self.post('myradio.books-browser',{'collection':'Family favorites'})['total'],1)
  self.assertEqual(self.request('/api/nas/myradio.music-browser',{},token=False)[0],403);self.assertEqual(self.request('/api/nas/myradio.album-save',{'album':a['id'],'metadata':{'album':'Changed'}},csrf=False)[0],403)
 def test_listening_ticks_are_not_audit_spam_and_owner_cannot_be_forged(self):
  sid=self.post('myradio.listen',{'event':'start','id':'1'.zfill(32),'kind':'music'})['session'];self.post('myradio.listen',{'event':'tick','session':sid,'playing':True});self.post('myradio.listen',{'event':'stop','session':sid})
  deadline=time.monotonic()+2
  while True:
   with self.state.connect() as db:count=db.execute("SELECT count(*) FROM activity_events WHERE operation='nas.myradio.listen'").fetchone()[0]
   if count==2 or time.monotonic()>deadline:break
   time.sleep(.01)
  self.assertEqual(count,2)
  self.assertEqual(self.request('/api/nas/myradio.listen',{'event':'start','id':'1'.zfill(32),'kind':'music','owner':'forged'})[0],400)
 def test_provider_artwork_cache_reauthorizes_before_304(self):
  album=self.post('myradio.music-browser',{})['items'][0]
  with patch('freeqnap.radio_providers._mb',return_value={'releases':[{'id':'12345678-1234-1234-1234-123456789abc','title':'Album'}]}):r=self.post('myradio.metadata-search',{'kind':'album','id':album['id'],'title':'Album'})
  path='/api/metadata-match-art?ticket='+r['results'][0]['ticket']
  with patch('freeqnap.radio_providers.public_http.fetch',return_value=b'\xff\xd8\xfffixture') as fetch:
   code,h,body=self.request(path);self.assertEqual(code,200);self.assertIn('private',h['Cache-Control']);self.assertEqual(self.request(path,**{'If-None-Match':h['ETag']})[0],304);self.assertEqual(fetch.call_count,1)
  self.model.allowed=False;self.assertEqual(self.request(path,**{'If-None-Match':h['ETag']})[0],404)
 def test_album_cover_supports_documented_upload_size(self):
  album=self.post('myradio.music-browser',{})['items'][0];r=self.post('myradio.album-save',{'album':album['id'],'metadata':{},'artwork':base64.b64encode(b'\xff\xd8\xff'+b'x'*100000).decode()});self.assertTrue(r['cover_saved']);self.assertEqual(self.request('/api/album-art?id='+album['id'])[0],200)
