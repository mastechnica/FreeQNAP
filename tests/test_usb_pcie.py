import importlib.util,unittest
from pathlib import Path
s=importlib.util.spec_from_file_location('usb_pcie',Path(__file__).resolve().parents[1]/'tools/usb-pcie-workaround.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class USBPCIe(unittest.TestCase):
 def test_only_read_request_bits_change_and_repeat_is_idempotent(self):
  for old in (0x2910,0x2fff,0x0910):
   new=m.desired(old);self.assertEqual(new,old&~0x7000);self.assertEqual((old^new)&~0x7000,0);self.assertEqual(m.desired(new),new)
  for old in (0x1910,0x3910,0x7910):
   with self.assertRaises(ValueError):m.desired(old)
 def test_capability_chain_rejects_loops_bounds_and_missing(self):
  good=bytearray(256);good[0x34]=0xa0;good[0xa0]=0x10;self.assertEqual(m.capability(good),0xa0)
  for pos in (0,0x20,0xff):
   bad=bytearray(256);bad[0x34]=pos
   with self.assertRaises(ValueError):m.capability(bad)
  bad=bytearray(256);bad[0x34]=0x40;bad[0x41]=0x40
  with self.assertRaises(ValueError):m.capability(bad)
