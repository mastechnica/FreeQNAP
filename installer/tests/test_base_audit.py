import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

path=Path(__file__).resolve().parents[1]/'audit-base.py'
spec=importlib.util.spec_from_file_location('base_audit',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class BaseAuditTests(unittest.TestCase):
 def make(self,path,mode=0o644,extra_key=False):
  with tarfile.open(path,'w:gz') as tar:
   for name in ('etc','etc/systemd','etc/systemd/network'):
    m=tarfile.TarInfo('./'+name);m.type=tarfile.DIRTYPE;m.mode=0o755;tar.addfile(m)
   files={'etc/systemd/network/10-freeqnap-wired.network':b'[Match]\nType=ether\n[Network]\nDHCP=yes\n','etc/machine-id':b'','etc/shadow':b'root:!:20000:0:99999:7:::\n'}
   if extra_key:files['root/.ssh/authorized_keys']=b'ssh-ed25519 test-public-key\n'
   for name,data in files.items():
    m=tarfile.TarInfo('./'+name);m.size=len(data);m.mode=mode if name.endswith('.network') else (0o644 if name=='etc/machine-id' else 0o600);tar.addfile(m,io.BytesIO(data))
 def test_service_can_read_profile_but_unreadable_or_identity_seeded_base_is_rejected(self):
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory)/'base.tar.gz';self.make(p);self.assertTrue(module.audit(p)['dhcp_profile_service_readable'])
   self.make(p,mode=0o600)
   with self.assertRaises(ValueError):module.audit(p)
   self.make(p,extra_key=True)
   with self.assertRaises(ValueError):module.audit(p)

if __name__=='__main__':unittest.main()
