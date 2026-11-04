import hashlib,json,os,unittest
from pathlib import Path
from unittest.mock import patch
import test_fileops
from freeqnap.nas.file_metadata import FileMetadata,clean,read_xmp,write

class MetadataTests(unittest.TestCase):
 def setUp(self):
  test_fileops.FileManagerTests.setUp(self);self.metadata=FileMetadata(self.ctx,self.fm);self.source=self.a/'photo.jpg';self.source.write_bytes(b'fixture original image');self.patch=patch('freeqnap.nas.file_metadata.inspect',return_value={'camera':'Fixture camera','taken':'2020-01-01T12:00:00'});self.patch.start();self.addCleanup(self.patch.stop)
 def review(self,plan):return {'plan_id':plan['id'],'digest':plan['digest'],'confirmation':plan['confirmation']}
 def test_reviewed_gps_sidecar_roundtrip_preserves_original_and_previous_xmp(self):
  before=hashlib.sha256(self.source.read_bytes()).hexdigest();value=self.metadata.read({'share':'a','path':'photo.jpg'});fields={**value['metadata'],'latitude':-45.5,'longitude':73.25,'altitude':-12.5,'description':'A family memory','tags':['family','trip']};plan=self.metadata.plan({'share':'a','path':'photo.jpg','etag':value['etag'],'metadata':fields});self.metadata.apply(self.review(plan));fresh=self.metadata.read({'share':'a','path':'photo.jpg'});self.assertEqual(fresh['metadata']['latitude'],-45.5);self.assertEqual(fresh['metadata']['longitude'],73.25);self.assertEqual(fresh['metadata']['altitude'],-12.5);self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(),before)
  plan=self.metadata.plan({'share':'a','path':'photo.jpg','etag':fresh['etag'],'metadata':{**fresh['metadata'],'title':'Changed title'}});self.metadata.apply(self.review(plan));self.assertTrue(any(v.name.startswith('.freeqnap-xmp-backup-') for v in self.a.iterdir()))
 def test_stale_file_sidecar_readonly_and_invalid_values_refuse(self):
  value=self.metadata.read({'share':'a','path':'photo.jpg'});self.source.write_bytes(b'changed')
  with self.assertRaises(ValueError):self.metadata.plan({'share':'a','path':'photo.jpg','etag':value['etag'],'metadata':value['metadata']})
  for v in [{'latitude':100,'longitude':0},{'latitude':1},{'latitude':float('nan'),'longitude':0},{'taken':'yesterday'},{'title':'nul\x00'}]:
   with self.assertRaises(ValueError):clean(v)
  cfg=self.ctx.config();cfg['shares']['a']['read_only']=True;self.ctx.save(cfg)
  with self.assertRaises(ValueError):self.metadata.plan({'share':'a','path':'photo.jpg','etag':value['etag'],'metadata':value['metadata']})
 def test_xmp_unknown_tags_are_preserved_entities_and_symlinks_refused(self):
  raw=b'<x:xmpmeta xmlns:x="adobe:ns:meta/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:custom="https://example.invalid/custom"><rdf:RDF><rdf:Description><custom:note>keep me</custom:note></rdf:Description></rdf:RDF></x:xmpmeta>';(self.a/'photo.jpg.xmp').write_bytes(raw);value=self.metadata.read({'share':'a','path':'photo.jpg'});plan=self.metadata.plan({'share':'a','path':'photo.jpg','etag':value['etag'],'metadata':{**value['metadata'],'latitude':45.,'longitude':-73.}});self.metadata.apply(self.review(plan));self.assertIn(b'keep me',(self.a/'photo.jpg.xmp').read_bytes());(self.a/'photo.jpg.xmp').unlink();(self.a/'photo.jpg.xmp').symlink_to(self.source)
  with self.assertRaises(OSError):self.metadata.read({'share':'a','path':'photo.jpg'})
