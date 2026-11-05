import copy,tempfile,unittest
from freeqnap.state import State
from freeqnap import radio_catalog as catalog
class Gateway:
 def __init__(self,state):
  self.state=state;self.owner='a'*32;self.share=None;self.managed=None;self.allowed=True;self.rows=[];self.writes=[];self.cfg={'musicbrainz':True,'openlibrary':True,'location_selected':True};self.session=lambda:{'user':{'id':self.owner,'role':'member','must_change':False,'permissions':['myradio.read','myradio.write']}}
 def _request(self,op,payload):
  if not self.allowed:raise PermissionError('Revoked')
  if op=='myradio.status':return {'config':self.cfg,'online':True,'counts':{'music':len([v for v in self.rows if v['category']=='music'])}}
  if op=='myradio.catalog':
   rows=[v for v in self.rows if v['category']==payload['category'] and bool(v['hidden'])==bool(payload.get('archived'))];offset=payload.get('offset',0);limit=payload.get('limit',60)
   return {'total':len(rows),'items':copy.deepcopy(rows[offset:offset+limit]),'offset':offset,'limit':limit,'facets':{}}
  if op in ('myradio.item','myradio.metadata'):
   row=next((v for v in self.rows if v['id']==payload['id']),None)
   if not row:raise ValueError('Unavailable')
   if op=='myradio.metadata':self.writes.append(payload);row['metadata'].update(payload.get('metadata',{}))
   return {'item':copy.deepcopy(row)}
  if op=='myradio.stations':return {'items':[{'id':'f'*32,'name':'Local station','metadata':{'country':'United States','countrycode':'US','tags':'Jazz'},'favorite':False}]}
  if op=='myradio.podcasts':return {'feeds':[],'episodes':[]}
  raise ValueError(op)
 def request(self,op,payload=None):return self._request(op,payload or {})
def item(n,category='music',**meta):return {'id':f'{n:032x}','name':str(n)+'.mp3','category':category,'metadata':{'title':'Track '+str(n),'artist':'Artist','album':'Album','year':'2020',**meta},'created':float(n),'bytes':100,'favorite':False,'hidden':False}
class CatalogTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.g=Gateway(State(self.t.name));catalog._CACHE.clear()
 def test_album_grouping_disc_order_and_full_search(self):
  self.g.rows=[item(1,track='10',disc='1'),item(2,track='2',disc='1'),item(3,track='1',disc='2'),item(4,album='Other')]
  r=catalog.music(self.g,{});self.assertEqual(r['total'],2);a=next(v for v in r['items'] if v['title']=='Album');self.assertEqual(a['track_count'],3)
  full=catalog.music(self.g,{'album':a['id']})['album'];self.assertEqual([v['id'] for v in full['tracks']],['2'.zfill(32),'1'.zfill(32),'3'.zfill(32)]);self.assertEqual(catalog.music(self.g,{'query':'Track 3'})['total'],1)
 def test_compilation_group_uses_local_source_evidence_not_common_title_alone(self):
  self.g.rows=[item(1,artist='A',album='Hits'),item(2,artist='B',album='Hits'),item(3,artist='C',album='Hits')];self.g.state.set('radio-source-groups:'+self.g.owner,{f'{i:032x}':{'group':'same' if i<3 else 'other'} for i in range(1,4)})
  r=catalog.music(self.g,{});self.assertEqual(r['total'],2);self.assertTrue(any(v['artist']=='Various artists' and v['track_count']==2 for v in r['items']))
 def test_cache_and_custom_art_are_reauthorized(self):
  self.g.rows=[item(1)];a=catalog.music(self.g,{})['items'][0];import base64
  catalog.album_save(self.g,{'album':a['id'],'metadata':{},'artwork':base64.b64encode(b'\xff\xd8\xfffixture').decode()});self.assertEqual(catalog.album_art(self.g,a['id'])[1],'image/jpeg');self.g.allowed=False
  with self.assertRaises(PermissionError):catalog.album_art(self.g,a['id'])
 def test_other_account_cache_and_book_organization_are_isolated(self):
  self.g.rows=[item(1,'books',author='Writer')];catalog.save_book(self.g,{'id':'1'.zfill(32),'metadata':{'series':'A series','series_number':'2','collections':['Favorites','Favorites']}});r=catalog.books(self.g,{'series':'A series'});self.assertEqual(r['total'],1);self.assertEqual(r['items'][0]['metadata']['collections'],['Favorites'])
  self.g.owner='b'*32;self.assertEqual(catalog.books(self.g,{'series':'A series'})['total'],0)
 def test_numeric_series_sort_and_archive_filter(self):
  self.g.rows=[item(1,'books',series='Series',series_number='10'),item(2,'books',series='Series',series_number='2'),{**item(3,'books'),'hidden':True}];self.assertEqual([v['id'] for v in catalog.books(self.g,{'sort':'series'})['items']],['2'.zfill(32),'1'.zfill(32)]);self.assertEqual(catalog.books(self.g,{'archived':True})['total'],1)
 def test_invalid_organization_and_read_only_edits(self):
  for values in ({'collections':'not-list'},{'series':'bad\nname'},{'owner':'forged'}):
   with self.assertRaises(ValueError):catalog.book_changes(values)
  self.g.share='missing-grant'
  with self.assertRaises(PermissionError):catalog.save_book(self.g,{'id':'1'*32,'metadata':{'series':'Bad'}})

 def test_compilation_years_do_not_split_one_source_album(self):
  self.g.rows=[item(1,artist='A',year='1990'),item(2,artist='B',year='1998')];self.g.state.set('radio-source-groups:'+self.g.owner,{v['id']:{'group':'same'} for v in self.g.rows})
  r=catalog.music(self.g,{});self.assertEqual(r['total'],1);self.assertEqual(r['items'][0]['track_count'],2)
 def test_persistent_index_needs_fresh_authorization_and_count_and_edit_invalidation(self):
  self.g.rows=[item(1)];catalog.music(self.g,{});catalog._CACHE.clear();self.g.allowed=False
  with self.assertRaises(PermissionError):catalog.music(self.g,{})
  self.g.allowed=True;self.g.rows.append(item(2,album='Second'));catalog._CACHE.clear();self.assertEqual(catalog.music(self.g,{})['total'],2)
  catalog.invalidate(self.g.owner,self.g.state);self.assertFalse(list((self.g.state.directory/'radio-index').glob('*.json')))

 def test_same_album_merges_accent_case_and_source_folder_differences(self):
  self.g.rows=[item(1,artist='Björk',album='Post',year='1995'),item(2,artist='Bjork',album='POST',year='2001')];self.g.state.set('radio-source-groups:'+self.g.owner,{v['id']:{'group':v['id']} for v in self.g.rows})
  self.assertEqual(catalog.music(self.g,{})['total'],1)
 def test_reviewed_group_is_bound_to_current_album_metadata(self):
  self.g.rows=[item(1),item(2,album='Other')];sources={v['id']:{'album_key':'reviewed','album_signature':catalog.album_signature(v['metadata']['album'],v['metadata']['artist'])} for v in self.g.rows};self.g.state.set('radio-source-groups:'+self.g.owner,sources)
  self.assertEqual(catalog.music(self.g,{})['total'],1);self.g.rows[1]['metadata']['album']='Changed';catalog.invalidate(self.g.owner,self.g.state);self.assertEqual(catalog.music(self.g,{})['total'],2)
 def test_only_equal_verified_content_collapses_and_all_copies_get_album_edits(self):
  self.g.rows=[item(1,title='Same song',track='1'),item(2,title='Same song',track='1'),item(3,title='Different song',track='2')];sources={v['id']:{'audio_hash':('a' if n<2 else 'b')*64,'audio_bytes':100} for n,v in enumerate(self.g.rows)};self.g.state.set('radio-source-groups:'+self.g.owner,sources)
  a=catalog.music(self.g,{})['items'][0];detail=catalog.music(self.g,{'album':a['id']})['album'];self.assertEqual(detail['file_count'],3);self.assertEqual(detail['track_count'],2);self.assertEqual(detail['identical_copies'],1);self.assertEqual(len(detail['tracks'][0]['alternate_copies']),1)
  self.assertEqual(catalog.album_save(self.g,{'album':a['id'],'metadata':{'album':'New'}})['updated'],3)
 def test_unrelated_various_artist_compilations_remain_separate(self):
  self.g.rows=[item(1,artist='Various Artists',album='Hits'),item(2,artist='Various Artists',album='Hits')];self.g.state.set('radio-source-groups:'+self.g.owner,{v['id']:{'group':v['id']} for v in self.g.rows});self.assertEqual(catalog.music(self.g,{})['total'],2)

 def test_other_versions_are_not_claimed_identical_and_edits_include_them(self):
  self.g.rows=[item(1,title='Song',track='1',duration=200),item(2,title='Song',track='1',duration=201),item(3,title='Song (live)',track='1',duration=201),item(4,title='Song',track='1',duration=260)]
  a=catalog.music(self.g,{})['items'][0];detail=catalog.music(self.g,{'album':a['id']})['album'];self.assertEqual(detail['track_count'],3);self.assertEqual(detail['other_versions'],1);self.assertEqual(detail['identical_copies'],0)
  self.assertEqual(catalog.album_save(self.g,{'album':a['id'],'metadata':{'genre':'Jazz'}})['updated'],4)
 def test_unavailable_placeholder_yields_to_existing_good_file_without_deletion(self):
  self.g.rows=[item(1,title='Song',track='1',duration=200),item(2,title='Song',track='1',audio_status='unavailable')]
  a=catalog.music(self.g,{})['items'][0];detail=catalog.music(self.g,{'album':a['id']})['album'];self.assertEqual(detail['track_count'],1);self.assertEqual(detail['file_count'],2);self.assertEqual(detail['retained_unavailable_copies'],1);self.assertEqual(detail['unavailable_tracks'],0)

 def test_attention_filters_distinguish_identification_from_missing_audio(self):
  self.g.rows=[item(1,album='Unknown tags',identification_status='needs-review'),item(2,album='Missing',audio_status='unavailable'),item(3,album='Ready')]
  self.assertEqual(catalog.music(self.g,{'attention':'identification'})['total'],1);self.assertEqual(catalog.music(self.g,{'attention':'audio'})['total'],1)
  with self.assertRaises(ValueError):catalog.music(self.g,{'attention':'invented'})

 def test_empty_or_equal_bytes_do_not_merge_different_intended_tracks(self):
  self.g.rows=[item(1,title='Missing one',track='1',audio_status='unavailable'),item(2,title='Missing two',track='2',audio_status='unavailable'),item(3,title='Intro',track='3'),item(4,title='Outro',track='4')];self.g.state.set('radio-source-groups:'+self.g.owner,{v['id']:{'audio_hash':'a'*64,'audio_bytes':100} for v in self.g.rows})
  a=catalog.music(self.g,{})['items'][0];self.assertEqual(a['track_count'],4);self.assertEqual(a['identical_copies'],0);self.assertEqual(a['unavailable_tracks'],2)

 def test_padded_disc_and_track_numbers_share_the_same_intended_slot(self):
  self.g.rows=[item(1,title='Song',track='01/12',disc='01',duration=200),item(2,title='Song',track='1',disc='1/2',duration=200)]
  self.assertEqual(catalog.music(self.g,{})['items'][0]['track_count'],1)
