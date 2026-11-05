import base64,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from freeqnap.nas.external import External
class PoolBrowser(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);(self.root/'a.txt').write_bytes(b'proof');(self.root/'b.txt').write_bytes(b'second');(self.root/'folder').mkdir();(self.root/'escape').symlink_to('/etc',target_is_directory=True)
  self.pool={'name':'data','kind':'internal'};self.context=SimpleNamespace(config=lambda:{'pools':{'data':self.pool}},volume=lambda ident:(self.pool,self.root));self.service=External(self.context)
 def test_internal_pool_browsing_is_explicit_read_only_and_paginated(self):
  with self.assertRaises(ValueError):self.service.list_files({'pool':'data'})
  first=self.service.list_files({'pool':'data','query':'.txt','limit':1},registered_pool=True);self.assertEqual([x['name'] for x in first['entries']],['a.txt']);self.assertEqual(first['next_offset'],1)
  second=self.service.list_files({'pool':'data','query':'.txt','offset':1,'limit':1},registered_pool=True);self.assertEqual([x['name'] for x in second['entries']],['b.txt']);self.assertIsNone(second['next_offset'])
  value=self.service.read_file({'pool':'data','path':'a.txt'},registered_pool=True);self.assertEqual(base64.b64decode(value['data_base64']),b'proof')
 def test_unknown_pool_traversal_and_symlink_do_not_escape(self):
  for request in ({'pool':'missing'},{'pool':'data','path':'../'},{'pool':'data','path':'escape'}):
   with self.assertRaises((ValueError,OSError)):self.service.list_files(request,registered_pool=True)

 def test_writable_volume_folder_creation_and_readonly_guard(self):
  from freeqnap.nas.files import Files
  fs=Files(self.context)
  from unittest.mock import patch
  with patch('os.fchown'):
   self.assertEqual(fs.mkdir({'share':'pool:data','name':'created'})['created'],'created')
  self.assertTrue((self.root/'created').is_dir())
  self.pool['read_only']=True
  with self.assertRaises(ValueError):fs.mkdir({'share':'pool:data','name':'blocked'})
  self.assertFalse((self.root/'blocked').exists())
  self.pool['read_only']=False
  for path in ('../','escape'):
   with self.assertRaises((ValueError,OSError)):fs.mkdir({'share':'pool:data','path':path,'name':'blocked'})
