import os
from unittest.mock import patch
from test_fileops import FileManagerTests
from freeqnap.personal_access import permission

class PropertiesTests(FileManagerTests):
 def test_recursive_size_and_link_exclusion(self):
  folder=self.a/'album';folder.mkdir();(folder/'song.flac').write_bytes(b'a'*13);(folder/'disc').mkdir();(folder/'disc/song.mp3').write_bytes(b'b'*17);(folder/'outside').symlink_to(self.root);(folder/'.freeqnap-private').mkdir();(folder/'.freeqnap-private/key').write_bytes(b'x'*100)
  value=self.fm.properties({'share':'a','path':'album'})
  self.assertEqual((value['bytes'],value['files'],value['folders'],value['skipped_links']),(30,2,1,1));self.assertTrue(value['complete']);self.assertEqual(value['type'],'Folder');self.assertEqual(permission('files.properties'),'files.read')
  self.assertEqual(self.fm.properties({'share':'a','path':'album/song.flac'})['bytes'],13)
 def test_root_is_scoped_and_invalid_paths_rejected(self):
  (self.a/'one').write_bytes(b'1');(self.b/'private').write_bytes(b'2'*400)
  self.assertEqual(self.fm.properties({'share':'a'})['bytes'],1)
  for p in ['../b','/etc/passwd','.freeqnap-private']:
   with self.assertRaises(ValueError):self.fm.properties({'share':'a','path':p})
 def test_budget_returns_honest_partial_totals(self):
  (self.a/'one').write_bytes(b'hello')
  with patch('freeqnap.nas.file_properties.time.monotonic',side_effect=[0,9,9]):
   value=self.fm.properties({'share':'a'})
  self.assertFalse(value['complete']);self.assertEqual(value['bytes'],0);self.assertTrue(value['warnings'])
