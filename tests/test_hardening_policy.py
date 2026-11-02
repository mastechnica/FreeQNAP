import importlib.util,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
SPEC=importlib.util.spec_from_file_location('hardening_tool',Path(__file__).resolve().parents[1]/'deploy/configure-hardening.py')
H=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(H)
class HardeningPolicyTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.board=self.root/'board';self.board.write_bytes(b'qnap,ts-431xeu\0alpine\0')
  self.runtime=self.root/'runtime';self.runtime.write_text('0\n');self.target=self.root/'sysctl.d/policy.conf'
  self.extra=self.root/'other.conf';self.extra.write_text('net.ipv4.ip_forward=0\n')
  for name,value in [('BOARD',self.board),('RUNTIME',self.runtime),('TARGET',self.target)]:
   p=patch.object(H,name,value);p.start();self.addCleanup(p.stop)
  p=patch.object(H,'policy_paths',return_value=[self.extra,self.target]);p.start();self.addCleanup(p.stop)
  p=patch.object(H.os,'geteuid',return_value=0);p.start();self.addCleanup(p.stop)
 def test_default_read_only(self):
  x=H.apply();self.assertTrue(x['read_only']);self.assertEqual(self.runtime.read_text(),'0\n');self.assertFalse(self.target.exists())
 def test_exact_board(self):
  self.board.write_bytes(b'other\0')
  with self.assertRaises(ValueError):H.apply(True)
  self.assertFalse(self.target.exists())
 def test_apply_and_idempotent(self):
  x=H.apply(True);self.assertEqual(x['after'],2);self.assertEqual(self.runtime.read_text(),'2\n');first=self.target.stat().st_ino
  H.apply(True);self.assertEqual(first,self.target.stat().st_ino);self.assertIn('= 2',self.target.read_text())
 def test_preserve_stricter_policy(self):
  self.runtime.write_text('1\n');self.assertEqual(H.apply(True)['after'],1);self.assertIn('= 1',self.target.read_text())
 def test_conflicting_policy_denied(self):
  self.extra.write_text('kernel.unprivileged_bpf_disabled = 0\n')
  with self.assertRaises(ValueError):H.apply(True)
  self.assertFalse(self.target.exists());self.assertEqual(self.runtime.read_text(),'0\n')
 def test_symlink_policy_denied(self):
  self.target.parent.mkdir();self.target.symlink_to(self.extra)
  with self.assertRaises(ValueError):H.apply(True)
  self.assertEqual(self.runtime.read_text(),'0\n')
 def test_unknown_policy_preserved(self):
  self.target.parent.mkdir();self.target.write_text('custom policy')
  with self.assertRaises(ValueError):H.apply(True)
  self.assertEqual(self.target.read_text(),'custom policy')
 def test_unknown_runtime_denied(self):
  self.runtime.write_text('9\n')
  with self.assertRaises(ValueError):H.apply(True)
  self.assertFalse(self.target.exists())

 def test_stricter_future_policy_requires_review(self):
  self.extra.write_text('kernel.unprivileged_bpf_disabled = 1\n')
  with self.assertRaises(ValueError):H.apply(True)
  self.assertFalse(self.target.exists());self.assertEqual(self.runtime.read_text(),'0\n')
