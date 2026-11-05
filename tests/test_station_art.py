import base64,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from freeqnap.nas.common import Context
from freeqnap.nas.station_art import artwork,fallback
from freeqnap.nas.myradio import MyRadio
class StationArtTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.ctx=Context(Path(self.tmp.name));MyRadio(self.ctx);self.ident='a'*32
  with self.ctx.state.connect() as db:db.execute('INSERT INTO radio_stations(id,name,url,metadata,checked,working) VALUES(?,?,?,?,0,1)',(self.ident,'Example FM','https://example.invalid/audio',json.dumps({'favicon':'https://example.invalid/icon.png','countrycode':'US','tags':'Jazz'})))
 def test_generated_fallback_is_unique_deterministic_and_escaped(self):
  one=fallback('<script> & FM','Jazz <news>',self.ident);self.assertEqual(one,fallback('<script> & FM','Jazz <news>',self.ident));self.assertNotIn(b'<script>',one);self.assertIn(b'LIVE RADIO',one);self.assertNotEqual(one,fallback('Other','Rock','b'*32))
 def test_failed_icon_uses_local_art_without_exposing_url(self):
  with patch('freeqnap.nas.station_art.public_http.fetch',side_effect=ValueError('blocked')):result=artwork(self.ctx,{'id':self.ident})
  self.assertEqual(result['mime'],'image/svg+xml');self.assertNotIn(b'https://example.invalid',base64.b64decode(result['data_base64']))
 def test_remote_svg_is_never_passed_to_browser(self):
  with patch('freeqnap.nas.station_art.public_http.fetch',return_value=b'<svg><script>evil()</script></svg>'):result=artwork(self.ctx,{'id':self.ident})
  self.assertNotIn(b'evil()',base64.b64decode(result['data_base64']))
 def test_decoded_raster_is_cached(self):
  with patch('freeqnap.nas.station_art.public_http.fetch',return_value=b'\x89PNG\r\n\x1a\nfixture') as fetch,patch('freeqnap.nas.station_art.jpeg',return_value=b'\xff\xd8fixture'):
   first=artwork(self.ctx,{'id':self.ident});second=artwork(self.ctx,{'id':self.ident});self.assertEqual(fetch.call_count,1);self.assertTrue(first['station_icon']);self.assertEqual(first,second)
