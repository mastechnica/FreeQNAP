import importlib.util,json,stat,tempfile,unittest
from pathlib import Path
path=Path(__file__).resolve().parents[1]/'audit-initramfs.py';spec=importlib.util.spec_from_file_location('initramfs_audit',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class InitramfsAudit(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  for name in module.REQUIRED:
   file=self.root/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(b'generic fixture')
 def audit(self):return module.audit(module.directory_entries(self.root))
 def test_generic_directory_passes_and_required_helper_or_symlink_fails(self):
  self.assertTrue(self.audit()['generic_bootstrap_audit']);file=self.root/'freeqnap/boot-policy.sh';file.unlink()
  with self.assertRaises(ValueError):self.audit()
  file.symlink_to('/etc/passwd')
  with self.assertRaises(ValueError):self.audit()
 def test_keys_identity_static_network_and_host_paths_are_rejected_without_contents(self):
  cases={'root/.ssh/authorized_keys':b'synthetic-public-key-DO-NOT-PRINT','etc/dropbear/dropbear_ed25519_host_key':b'synthetic-private-key-DO-NOT-PRINT','etc/freeqnap-install-id':b'synthetic-install-id','etc/resolv.conf':b'nameserver 192.168.77.1','etc/systemd/network/fixed.network':b'[Network]\nAddress=192.168.77.2/24\n','freeqnap/tool.sh':('echo '+module.PERSONAL_ROOT+'fixture/private\n').encode()}
  for name,data in cases.items():
   file=self.root/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(data)
   with self.assertRaises(ValueError) as error:self.audit()
   self.assertNotIn('DO-NOT-PRINT',str(error.exception));file.unlink()
 def test_locked_root_and_empty_identity_allowed_but_password_and_human_account_refused(self):
  etc=self.root/'etc';etc.mkdir();(etc/'machine-id').write_bytes(b'');(etc/'shadow').write_text('root:!:20000:0:99999:7:::\n');self.audit();(etc/'shadow').write_text('root::20000:0:99999:7:::\n')
  with self.assertRaises(ValueError):self.audit()
  (etc/'shadow').unlink();(etc/'passwd').write_text('human:x:1000:1000::/home/human:/bin/sh\n')
  with self.assertRaises(ValueError):self.audit()
 def cpio(self,entries):
  out=bytearray()
  for name,mode,data in [*entries,('TRAILER!!!',0,b'')]:
   raw=name.encode()+b'\0';fields=[1,mode,0,0,1,0,len(data),0,0,0,0,len(raw),0];out.extend(b'070701'+''.join(f'{n:08x}' for n in fields).encode());out.extend(raw);out.extend(b'\0'*((-len(out))%4));out.extend(data);out.extend(b'\0'*((-len(out))%4))
  return bytes(out)
 def test_embedded_cpio_is_checked_without_extracting_and_cannot_hide_a_second_archive(self):
  entries=[(name,stat.S_IFREG|0o755,b'generic') for name in sorted(module.REQUIRED)];file=self.root/'image.cpio';file.write_bytes(self.cpio(entries));self.assertTrue(module.audit(module.cpio_entries(file))['generic_bootstrap_audit'])
  for data in (self.cpio(entries)+self.cpio([('root/.ssh/authorized_keys',stat.S_IFREG|0o600,b'synthetic-key')]),self.cpio(entries+[('../escape',stat.S_IFREG|0o600,b'x')]),self.cpio(entries+[entries[0]]),self.cpio(entries)[:-4]):
   file.write_bytes(data)
   with self.assertRaises(ValueError):module.audit(module.cpio_entries(file))
