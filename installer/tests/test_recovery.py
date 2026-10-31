import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import verified_image
from recovery import SUFFIX,overlay_plan


def tree(args,hardware=b'qnap,ts-431xeu\0'):
 def pad(b):return b+b'\0'*((-len(b))%4)
 def node(name):return struct.pack('>I',1)+pad(name+b'\0')
 def prop(nameoff,value):return struct.pack('>III',3,len(value),nameoff)+pad(value)
 strings=b'compatible\0bootargs\0'
 body=node(b'')+prop(0,hardware)+node(b'chosen')+prop(11,args)+struct.pack('>III',2,2,9)
 off=56;header=struct.pack('>10I',0xd00dfeed,off+len(body)+len(strings),off,off+len(body),40,17,16,0,len(strings),len(body))
 return header+b'\0'*16+body+strings


def release(path,dtb,maintenance=False,kernel=b'K'*64):
 path.mkdir();payload=kernel+dtb
 header=bytearray(struct.pack('>7I4B32s',0x27051956,0,0,len(payload),0x8000,0x8000,zlib.crc32(payload),5,2,2,0,b'Test'))
 header[4:8]=struct.pack('>I',zlib.crc32(header));raw=bytes(header)+payload
 (path/'uImage').write_bytes(raw);(path/'zImage').write_bytes(kernel)
 (path/'manifest.json').write_text(json.dumps({'schema':1,'model':'TS-431XeU','architecture':'armhf','one_boot_maintenance_only':maintenance,'artifacts':{'uImage':{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'crc32':f'{zlib.crc32(raw):08x}'}}}))
 return raw


class RecoveryTests(unittest.TestCase):
 def test_ram_edits_reconstruct_exact_checked_image_and_never_touch_kernel(self):
  with tempfile.TemporaryDirectory() as directory:
   base=Path(directory)/'base';recovery=Path(directory)/'recovery';args=b'console=ttyS0\0'
   old=release(base,tree(args));new=release(recovery,tree(args[:-1]+SUFFIX+b'\0'),True)
   self.assertEqual(len(new)%4,0)
   plan=overlay_plan(base,recovery);ram=bytearray(old+b'\0'*(len(new)-len(old)))
   for address,value in plan['words']:
    offset=address-0x08000000;self.assertTrue(offset<64 or offset>=128);ram[offset:offset+4]=value.to_bytes(4,'little')
   self.assertEqual(bytes(ram[:len(new)]),new)
   with self.assertRaises(ValueError):verified_image(recovery)
 def test_changed_hardware_or_kernel_is_rejected_even_with_valid_image_checksums(self):
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory);args=b'console=ttyS0\0';release(p/'base',tree(args))
   release(p/'bad-hardware',tree(args[:-1]+SUFFIX+b'\0',b'wrong,board\0'),True)
   release(p/'bad-kernel',tree(args[:-1]+SUFFIX+b'\0'),True,kernel=b'X'*64)
   for name in ('bad-hardware','bad-kernel'):
    with self.assertRaises(ValueError):overlay_plan(p/'base',p/name)

if __name__=='__main__':unittest.main()
