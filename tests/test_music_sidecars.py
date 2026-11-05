import json,os,tempfile,unittest
from pathlib import Path
from freeqnap.nas.music_sidecars import name,document,read
class SidecarTests(unittest.TestCase):
 def test_exact_original_identity_required_and_active_fields_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);p=root/'track.mp3';p.write_bytes(b'audio');st=p.stat();fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
   try:
    side=root/name(p.name);side.write_text(json.dumps(document(p.name,st,{'title':'Title','artist':'Artist','source_url':'javascript:bad'})));self.assertEqual(read(fd,p.name,st),{'title':'Title','artist':'Artist'})
    value=json.loads(side.read_text());value['file']['inode']+=1;side.write_text(json.dumps(value));self.assertEqual(read(fd,p.name,st),{})
    value=document(p.name,st,{'title':'Title'});value['metadata']['source_url']='https://example.com';side.write_text(json.dumps(value));self.assertEqual(read(fd,p.name,st),{})
    side.unlink();side.symlink_to(p);self.assertEqual(read(fd,p.name,st),{})
   finally:os.close(fd)
 def test_long_utf8_source_names_have_bounded_sidecar_filenames(self):
  self.assertLessEqual(len(name('é'*120+'.flac').encode()),255)
