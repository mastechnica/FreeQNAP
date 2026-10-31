import unittest,tempfile,json,hashlib
from pathlib import Path
from test_nas import Fixture
from freeqnap.nas.media import Media,nfo
class MediaLibraryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.ctx=Fixture(Path(self.tmp.name));self.media=Media(self.ctx)
  folder=self.ctx.mount/'films';folder.mkdir();(folder/'sample.mp4').write_bytes(b'fixture')
  cfg=self.ctx.config();cfg['shares']['films']={'name':'films','pool':'data','path':str(folder),'gid':0};cfg['libraries']['films']={'name':'films','share':'films','pool':'data','path':str(folder),'filesystem_uuid':cfg['pools']['data']['filesystem_uuid'],'scan_enabled':True};self.ctx.save(cfg)
  self.ident='a'*64
  with self.ctx.state.connect() as db:db.execute('INSERT INTO media VALUES(?,?,?,?,?,?)',(self.ident,'films','sample.mp4','fixture','{}',0))
 def test_sidecar_roundtrip_and_backup(self):
  value={'title':'Example','trailer':'https://example.org/trailer','director':'Director','producer':'Producer','actors':[{'name':'Actor','role':'Role'}],'genres':['Drama']}
  self.media.apply_metadata({'id':self.ident,'metadata':value,'save_sidecar':True})
  path=self.ctx.mount/'films/sample.nfo';self.assertEqual(nfo(path.read_bytes())['actors'],value['actors']);self.assertEqual(nfo(path.read_bytes())['producer'],'Producer');self.assertEqual(nfo(path.read_bytes())['trailer'],'https://example.org/trailer')
  self.media.apply_metadata({'id':self.ident,'metadata':{'title':'Updated'},'save_sidecar':True});self.assertEqual(len(list(path.parent.glob('*.backup-*'))),1)
 def test_controls_and_validation(self):
  self.media.scanner_settings({'enabled':False})
  with self.assertRaisesRegex(ValueError,'disabled'):self.media.scan({'library':'films'})
  self.assertFalse(self.media.scanner_status()['enabled'])
  for v in (['../outside'],['/etc'],['']):
   with self.assertRaises(ValueError):self.media.exclusions(v)
  with self.assertRaises(ValueError):self.media.apply_metadata({'id':self.ident,'metadata':{'actors':['wrong']}})
  with self.assertRaises(ValueError):self.media.artwork({'id':self.ident,'seconds':-1})
 def test_provider_key_is_not_returned(self):
  result=self.media.provider_save({'provider':'omdb','api_key':'fixture123'})
  self.assertNotIn('fixture123',json.dumps(result));self.assertTrue(self.media.provider_status()['omdb_configured'])
  with self.assertRaises(ValueError):self.media.provider_save({'provider':'arbitrary','api_key':'fixture123'})
 def test_omdb_requires_library_permission(self):
  with self.assertRaises(ValueError):self.media.lookup({'library':'films','provider':'omdb','query':'Example'})
 def test_omdb_maps_credits_without_network(self):
  from unittest.mock import patch,MagicMock
  self.media.provider_save({'provider':'omdb','api_key':'fixture123'})
  response=MagicMock();response.__enter__.return_value.read.return_value=json.dumps({'Response':'True','Title':'Example','Actors':'Actor One, Actor Two','Director':'Director','imdbID':'tt123'}).encode()
  with patch('urllib.request.build_opener') as opener:
   opener.return_value.open.return_value=response
   result=self.media.omdb_lookup({'query':'Example'})
  self.assertEqual(result['results'][0]['actors'][0]['name'],'Actor One')
  self.assertNotIn('fixture123',json.dumps(result))
