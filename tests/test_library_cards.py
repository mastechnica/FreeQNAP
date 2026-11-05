import base64,tempfile,unittest
from freeqnap.state import State
from freeqnap.library_cards import save,overlay,artwork
from freeqnap.podcast_browser import Browser,_CACHE
from test_podcast_browser import Gateway
class CardTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.g=Gateway(State(self.t.name));self.user={'id':self.g.owner,'role':'member','permissions':['myradio.read','myradio.write'],'must_change':False};self.g.session=lambda:{'user':self.user};_CACHE.clear()
 def test_show_edits_filter_and_preserve_source_and_original(self):
  save(self.g,{'kind':'podcast','id':'1'*32,'metadata':{'title':'My title','genre':'Favorites','author':'My publisher','description':'My notes'}})
  r=Browser(self.g).listing({'query':'My title','genre':'Favorites'});self.assertEqual(r['items'][0]['title'],'My title');self.assertEqual(r['items'][0]['publisher'],'My publisher');self.assertEqual(self.g.feeds[0]['title'],'Alpha Tech')
 def test_account_isolation_and_write_permission(self):
  save(self.g,{'kind':'podcast','id':'1'*32,'metadata':{'title':'Mine'}})
  self.g.owner='b'*32;self.user['id']=self.g.owner;self.assertEqual(overlay(self.g,'podcast',self.g.feeds[0])['title'],'Alpha Tech')
  self.user['permissions']=['myradio.read']
  with self.assertRaises(PermissionError):save(self.g,{'kind':'podcast','id':'1'*32,'metadata':{'title':'No'}})
 def test_shared_read_only_and_foreign_id(self):
  self.g.share='grant'
  with self.assertRaises(Exception):save(self.g,{'kind':'podcast','id':'1'*32,'metadata':{}})
  self.g.share=None
  with self.assertRaises(PermissionError):save(self.g,{'kind':'podcast','id':'3'*32,'metadata':{}})
 def test_cover_authorized_before_cache_and_active_image_denied(self):
  r={'kind':'podcast','id':'1'*32,'artwork':base64.b64encode(b'\xff\xd8\xfffixture').decode()};save(self.g,r);self.assertEqual(artwork(self.g,'podcast','1'*32)[1],'image/jpeg');self.g.allowed=False
  with self.assertRaises(PermissionError):artwork(self.g,'podcast','1'*32)
  self.g.allowed=True;r['artwork']=base64.b64encode(b'<svg/>').decode()
  with self.assertRaises(ValueError):save(self.g,r)
 def test_no_source_destinations_or_owner_override(self):
  for r in ({'owner':'b'*32},{'metadata':{'url':'https://example.com'}},{'metadata':{'title':''}},{'metadata':{'genre':'x'*201}}):
   with self.assertRaises(ValueError):save(self.g,{'kind':'podcast','id':'1'*32,**r})

 def test_station_edits_search_and_filter_with_validated_inputs(self):
  from freeqnap.library_cards import stations
  row={'id':'1'*32,'name':'Original station','favorite':False,'metadata':{'countrycode':'US','country':'United States','tags':'old'}}
  self.g._request=lambda op,r:{'items':[row]}
  save(self.g,{'kind':'station','id':row['id'],'metadata':{'title':'My station','genre':'Jazz','description':'Evening favorites'}})
  self.assertEqual(stations(self.g,{'items':[row]},{'query':'evening','group':'Jazz','country':'United States'})['items'][0]['name'],'My station')
  self.assertEqual(stations(self.g,{'items':[row]},{'group':'old'})['items'],[])
  for bad in ({'query':3},{'group':[]},{'country':'elsewhere'}):
   with self.assertRaises(ValueError):stations(self.g,{'items':[row]},bad)

 def test_prepared_collection_cannot_start_old_expensive_scanner(self):
  from freeqnap.personal_access import Gateway as PersonalGateway
  g=object.__new__(PersonalGateway);g.state=self.g.state;g.session=self.g.session;g.managed=None;g.share=None;calls=[]
  ready=False
  def request(op,payload):
   calls.append(op)
   return {'prepared_scanning':ready} if op=='myradio.status' else {'job_id':'job'}
  g._request=request;g.state.set('library-prepared:'+self.g.owner,{'needs_native_reload':True})
  with self.assertRaises(ValueError):g.request('myradio.scan',{})
  self.assertNotIn('myradio.scan',calls);self.assertTrue(g.request('myradio.status',{})['optimized_scan_pending'])
  ready=True;self.assertEqual(g.request('myradio.scan',{})['job_id'],'job');self.assertFalse(g.request('myradio.status',{})['optimized_scan_pending'])
