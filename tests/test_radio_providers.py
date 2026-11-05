import base64,hashlib,tempfile,unittest
from unittest.mock import patch
from freeqnap.state import State
from freeqnap import radio_providers as providers,radio_catalog
from test_radio_catalog import Gateway,item
class ProviderTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.g=Gateway(State(self.t.name));self.g.rows=[item(1),item(2,'books')];radio_catalog._CACHE.clear()
 def test_disabled_provider_performs_no_network_search(self):
  self.g.cfg['musicbrainz']=False;a=radio_catalog.music(self.g,{})['items'][0]
  with patch('freeqnap.radio_providers.public_http.json_fetch') as fetch:
   self.assertTrue(providers.search(self.g,{'kind':'album','id':a['id'],'title':'Album'})['disabled']);fetch.assert_not_called()
  with patch('freeqnap.radio_providers.public_http.json_fetch') as fetch:
   self.assertTrue(providers.search(self.g,{'kind':'station','id':'f'*32,'title':'Station'})['disabled']);fetch.assert_not_called()
 def test_result_tickets_are_scoped_expire_and_disable_with_provider(self):
  a=radio_catalog.music(self.g,{})['items'][0]
  with patch('freeqnap.radio_providers._mb',return_value={'releases':[{'id':'12345678-1234-1234-1234-123456789abc','title':'Album','artist-credit':[{'name':'Artist'}]}]}):r=providers.search(self.g,{'kind':'album','id':a['id'],'title':'Album'})
  ticket=r['results'][0]['ticket'];self.assertNotIn('cover_url',r['results'][0]);self.assertEqual(providers.match(self.g,ticket)['id'],a['id']);self.g.owner='b'*32
  with self.assertRaises(PermissionError):providers.match(self.g,ticket)
  self.g.owner='a'*32;self.g.cfg['musicbrainz']=False
  with self.assertRaises(PermissionError):providers.match(self.g,ticket)
 def test_radio_country_filter_and_metadata_never_change_stream_url(self):
  providers.configure(self.g,{'radio':True})
  with patch('freeqnap.radio_providers.public_http.json_fetch',return_value=[{'countrycode':'GB','name':'Wrong'},{'countrycode':'US','name':'Right','tags':'Jazz'}]):r=providers.search(self.g,{'kind':'station','id':'f'*32,'title':'Station','country':'US'})
  self.assertEqual([v['title'] for v in r['results']],['Right']);self.assertNotIn('url',r['results'][0]);providers.apply(self.g,{'ticket':r['results'][0]['ticket'],'cover':False});self.assertEqual(self.g.state.setting('library-card:'+self.g.owner+':station:'+('f'*32))['metadata']['title'],'Right')
 def test_unconfirmed_podcast_origins_are_not_inferred_from_storefront(self):
  providers.configure(self.g,{'podcasts':True});self.g._request_original=self.g._request
  feed='https://example.com/feed';ident=hashlib.sha256(feed.encode()).hexdigest()[:32]
  def request(op,payload):
   if op=='myradio.podcasts':return {'feeds':[{'id':ident,'metadata':{'countrycode':'US'}}],'episodes':[]}
   return self.g._request_original(op,payload)
  self.g._request=request
  with patch('freeqnap.radio_providers.public_http.json_fetch',return_value={'results':[{'feedUrl':'https://other.example/feed','collectionViewUrl':'https://example.com/show','collectionName':'Unknown origin'},{'feedUrl':feed,'collectionViewUrl':'https://example.com/show','collectionName':'Enrolled'}]}),patch('freeqnap.radio_providers.public_http.target'):
   r=providers.search(self.g,{'kind':'podcast','id':ident,'title':'Podcast','country':'US'})
  self.assertEqual([v['title'] for v in r['results']],['Enrolled'])
 def test_shared_and_malformed_configuration_are_denied(self):
  with self.assertRaises(ValueError):providers.configure(self.g,{'radio':'yes'})
  self.g.share='missing'
  with self.assertRaises(PermissionError):providers.configure(self.g,{'radio':True})
