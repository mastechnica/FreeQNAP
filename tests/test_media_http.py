import base64,http.client,io,json,tempfile,threading,unittest,zipfile
from pathlib import Path
from http.server import ThreadingHTTPServer
from freeqnap import auth
from freeqnap.state import State
from freeqnap.server import handler
from freeqnap.media_http import byte_range,kind

class MediaHTTPTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.state=State(self.root/'state');self.state.set('administrator',auth.password_hash('private fixture password'));self.token,self.csrf=auth.login(self.state,'private fixture password');self.data=b'0123456789';test=self
  class Broker:
   def request(self,action,payload):
    if action in ('files.read','files.pool-read','external.session-read'):return {'data_base64':base64.b64encode(test.data[payload['offset']:payload['offset']+payload['count']]).decode(),'etag':'stable','total_bytes':len(test.data),'modified_at':1700000000}
    if action in ('photos.read','myradio.read','raid.backup-read'):return {'filename':'fixture.mp4','data_base64':base64.b64encode(test.data[payload['offset']:payload['offset']+payload['count']]).decode(),'etag':'photo-fixture','total_bytes':len(test.data)}
    if action=='files.bundle-info':return {'ticket':payload['ticket'],'filename':'files.zip','roots':[{'path':'test','name':'test'}]}
    if action=='files.bundle-node':return {'directory':False,'bytes':len(test.data),'modified_at':1700000000,'etag':'stable'}
    if action=='files.bundle-read':return self.request('files.read',payload)
    raise ValueError('Unexpected action')
  self.server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.state,self.root/'backups',broker=Broker()));threading.Thread(target=self.server.serve_forever,daemon=True).start();self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
 def request(self,path,method='GET',authorized=True,**headers):
  c=http.client.HTTPConnection('127.0.0.1',self.server.server_port);h={'Host':'127.0.0.1:'+str(self.server.server_port)}
  if authorized:h['Cookie']='freeqnap_session='+self.token
  h.update(headers);c.request(method,path,headers=h);r=c.getresponse();result=r.status,dict(r.getheaders()),r.read();c.close();return result
 def test_media_ranges_suffix_head_and_if_range(self):
  path='/api/file?share=a&path=movie.mp4&inline=1';code,h,b=self.request(path,Range='bytes=2-5');self.assertEqual((code,b),(206,b'2345'));self.assertEqual(h['Content-Range'],'bytes 2-5/10');self.assertTrue(h['Content-Disposition'].startswith('inline'))
  self.assertEqual(self.request(path,Range='bytes=-3')[2],b'789');self.assertEqual(self.request(path,'HEAD')[2],b'');self.assertEqual(self.request(path,Range='bytes=99-')[0],416);self.assertEqual(self.request(path,Range='bytes=2-5',**{'If-Range':'"other"'})[2],self.data)
 def test_files_and_zip_require_session_and_active_content_is_attachment(self):
  self.assertEqual(self.request('/api/file?share=a&path=file',authorized=False)[0],401);self.assertEqual(self.request('/api/zip?ticket=abc',authorized=False)[0],401);self.assertEqual(self.request('/api/foreign-file?session=x&path=test',authorized=False)[0],401)
  h=self.request('/api/file?share=a&path=unsafe.svg&inline=1')[1];self.assertTrue(h['Content-Disposition'].startswith('attachment'));self.assertEqual(h['X-Content-Type-Options'],'nosniff')
  code,h,b=self.request('/api/zip?ticket=abc');self.assertEqual(code,200);self.assertEqual(h['Content-Type'],'application/zip')
  with zipfile.ZipFile(io.BytesIO(b)) as z:self.assertEqual(z.read('test'),self.data);self.assertIsNone(z.testzip())
 def test_range_validation_and_kinds(self):
  for value in ['bytes=0-1,4-5','bytes=-0','bytes=5-2','other']:
   with self.assertRaises(ValueError):byte_range(value,10)
  self.assertIsNone(kind('active.svg'));self.assertEqual(kind('photo.JPG'),'image');self.assertEqual(byte_range(None,0),(0,-1,False))

 def test_registered_pool_and_foreign_media_keep_auth_ranges_and_inline_rules(self):
  for path in ('/api/pool-file?pool=data&path=movie.mp4&inline=1','/api/foreign-file?session=fixture&path=movie.mp4&inline=1'):
   self.assertEqual(self.request(path,authorized=False)[0],401)
   code,h,b=self.request(path,Range='bytes=2-5');self.assertEqual((code,b),(206,b'2345'));self.assertTrue(h['Content-Disposition'].startswith('inline'));self.assertEqual(h['Cache-Control'],'no-store')

 def test_location_selector_asset_loads_before_login_without_exposing_data(self):
  code,headers,body=self.request('/file-locations.js',authorized=False);self.assertEqual(code,200);self.assertIn('javascript',headers['Content-Type']);self.assertIn(b'FreeQNAPLocations',body)

 def test_personal_photo_stream_requires_session_and_supports_ranges(self):
  path='/api/photo-file?id='+'a'*64+'&variant=original&inline=1'
  self.assertEqual(self.request(path,authorized=False)[0],401)
  code,headers,data=self.request(path,Range='bytes=2-5')
  self.assertEqual((code,data),(206,b'2345'));self.assertEqual(headers['Cache-Control'],'no-store');self.assertEqual(headers['Cross-Origin-Resource-Policy'],'same-origin')

 def test_private_radio_and_recovery_backup_routes_keep_auth_and_ranges(self):
  for path in ['/api/radio-file?id='+'a'*32+'&inline=1','/api/raid-backup?id='+'b'*32]:
   self.assertEqual(self.request(path,authorized=False)[0],401)
   code,headers,data=self.request(path,Range='bytes=1-3');self.assertEqual((code,data),(206,b'123'));self.assertEqual(headers['Cache-Control'],'no-store')
  self.assertTrue(self.request('/api/radio-file?id='+'a'*32+'&inline=1&download=1')[1]['Content-Disposition'].startswith('attachment'))
 def test_station_stream_requires_browser_session_and_new_assets_are_public_code_only(self):
  self.assertEqual(self.request('/api/radio-stream?id='+'a'*32,authorized=False)[0],401)
  for path in ['/navigation.js','/myradio.js','/array-recovery.js']:
   code,headers,body=self.request(path,authorized=False);self.assertEqual(code,200);self.assertIn('javascript',headers['Content-Type'])
