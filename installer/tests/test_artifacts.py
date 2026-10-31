import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from artifacts import load_artifacts

class ArtifactTests(unittest.TestCase):
 def test_changed_release_is_rejected_and_active_bytes_are_immutable(self):
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory);data=b'test-base-rootfs'
   (p/'debian-armhf-base.tar.gz').write_bytes(data)
   (p/'manifest.json').write_text(json.dumps({'artifacts':{'debian-armhf-base.tar.gz':{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}}}))
   served=load_artifacts(p)
   (p/'debian-armhf-base.tar.gz').write_bytes(b'changed')
   self.assertEqual(served,{'/debian-armhf-base.tar.gz':data})
   with self.assertRaises(ValueError):load_artifacts(p)

if __name__=='__main__':unittest.main()
