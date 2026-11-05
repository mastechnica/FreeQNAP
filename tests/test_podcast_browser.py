import json,tempfile,time,unittest
from unittest.mock import patch
from freeqnap.state import State
from freeqnap.podcast_browser import Browser,epoch,image_type,_CACHE
class Gateway:
 def __init__(self,state,modern=False):
  self.state=state;self.managed=None;self.share=None;self.allowed=True;self.modern=modern;self.calls=[];self.owner='a'*32;self.session=lambda:{'user':{'id':self.owner,'role':'member','must_change':False}}
  self.feeds=[{'id':'1'*32,'title':'Alpha Tech','metadata':{'author':'Publisher A','description':'Engineering','genres':['Technology']},'checked_at':1},{'id':'2'*32,'title':'Security Show','metadata':{'author':'Publisher B','description':'Defense','genres':['Cybersecurity']},'checked_at':1}]
  self.rows={self.feeds[0]['id']:[{'id':f'{i:032x}','feed':'1'*32,'title':'Episode '+str(i),'metadata':{'published':'Sun, 01 Nov 2026 10:00:00 +0000','description':'Engineering details','duration':'01:02:03'},'asset':'saved' if i==0 else None} for i in range(61)],'2'*32:[{'id':'f'*32,'feed':'2'*32,'title':'Threat research','metadata':{'published':'Tue, 03 Nov 2026 10:00:00 +0000','description':'Ransomware investigation'},'asset':None}]}
 def _request(self,operation,payload):
  if not self.allowed:raise PermissionError('Revoked')
  self.calls.append(payload);rows=json.loads(json.dumps(self.rows.get(payload.get('feed'),[])))
  if self.modern:
   offset=payload.get('offset',0);page=rows[offset:offset+30];return {'feeds':self.feeds,'episodes':page,'pagination':True,'next_offset':offset+30 if offset+30<len(rows) else None,'unclassified_feeds':[]}
  return {'feeds':self.feeds,'episodes':rows[:300],'unclassified_feeds':[]}
class PodcastBrowserTests(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.g=Gateway(State(tmp.name));_CACHE.clear()
 def test_show_first_results_do_not_include_episode_rows_or_private_urls(self):
  r=Browser(self.g).listing({'limit':25});self.assertEqual(r['total'],2);self.assertEqual(r['items'][0]['title'],'Security Show');self.assertNotIn('rows',r['items'][0]);self.assertNotIn('feed_url',json.dumps(r))
 def test_episode_page_sizes_offset_all_and_real_date_order(self):
  b=Browser(self.g)
  for n in (25,50,100,500):
   r=b.listing({'view':'episodes','feed':'1'*32,'limit':n});self.assertEqual(len(r['items']),min(n,61));self.assertEqual(r['total'],61)
  self.assertEqual(len(b.listing({'view':'episodes','feed':'1'*32,'limit':'all'})['items']),61)
  self.assertEqual(len(b.listing({'view':'episodes','feed':'1'*32,'limit':25,'offset':50})['items']),11)
 def test_genre_search_publisher_and_download_filters(self):
  b=Browser(self.g);self.assertEqual(b.listing({'genre':'Cybersecurity'})['total'],1);self.assertEqual(b.listing({'query':'ransomware'})['items'][0]['title'],'Security Show');self.assertEqual(b.listing({'publisher':'Publisher A'})['total'],1)
  self.assertEqual(b.listing({'view':'episodes','feed':'1'*32,'saved':'yes'})['total'],1)
  self.assertEqual(b.listing({'view':'episodes','feed':'1'*32,'query':'missing'})['show']['title'],'Alpha Tech')
 def test_date_parser_handles_rfc_iso_and_unknown_without_string_sorting(self):
  self.assertEqual(epoch('2026-11-01T10:00:00Z'),epoch('Sun, 01 Nov 2026 10:00:00 +0000'));self.assertIsNone(epoch('bad date'))
 def test_cached_catalog_still_checks_access_and_manual_refresh_reloads_assets(self):
  b=Browser(self.g);b.listing({});self.g.rows['1'*32][0]['asset']=None;self.assertEqual(b.listing({'view':'episodes','feed':'1'*32,'saved':'yes','refresh':True})['total'],0);self.g.allowed=False
  with self.assertRaises(PermissionError):b.listing({})
 def test_modern_pagination_follows_actual_cursors_but_legacy_windows_are_honest(self):
  self.g.modern=True;r=Browser(self.g).listing({'view':'episodes','feed':'1'*32,'limit':'all'});self.assertEqual(r['total'],61);self.assertTrue(any(c.get('offset')==60 for c in self.g.calls));self.assertFalse(r['recent_window'])
  _CACHE.clear();self.g.modern=False;self.g.rows['1'*32]*=6;r=Browser(self.g).listing({'view':'episodes','feed':'1'*32,'limit':'all'});self.assertEqual(r['total'],300);self.assertTrue(r['recent_window'])
 def test_artwork_requires_show_ownership_and_rejects_active_content(self):
  with self.assertRaises(PermissionError):Browser(self.g).artwork('3'*32)
  for raw in (b'<svg onload="bad"/>',b'<!doctype html>'):
   with self.assertRaises(ValueError):image_type(raw)
 def test_other_account_cache_is_not_reused(self):
  Browser(self.g).listing({});self.g.owner='b'*32;self.g.feeds=[];r=Browser(self.g).listing({});self.assertEqual(r['items'],[])
 def test_artwork_cached_bytes_are_reauthorized_before_return(self):
  ident='1'*32;self.g.state.set('podcast-profile:'+self.g.owner+':'+ident,{'checked':time.time(),'artwork':'https://public.example/art.jpg'});b=Browser(self.g)
  with patch('freeqnap.podcast_browser.public_http.fetch',return_value=b'\xff\xd8\xfffixture'):
   self.assertEqual(b.artwork(ident)[1],'image/jpeg')
  self.g.allowed=False
  with self.assertRaises(PermissionError):b.artwork(ident)
