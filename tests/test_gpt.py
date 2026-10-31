import struct
import unittest
import uuid
import zlib
from unittest.mock import patch
from freeqnap.nas import gpt

class GPTTests(unittest.TestCase):
 def test_large_disk_split_is_bounded_contiguous_and_covers_capacity(self):
  size=30002393382912
  with patch('freeqnap.nas.limits.ext4_limit',return_value=16*1024**4):
   plan=gpt.layout(size,512,['external-1','external-2'])
   with self.assertRaises(ValueError):gpt.layout(size,512,['oversize'])
  a,b=plan['volumes'];self.assertLess(a['bytes'],16*1024**4);self.assertLess(b['bytes'],16*1024**4)
  self.assertEqual(a['start_bytes']+a['bytes'],b['start_bytes']);self.assertLess(size-b['start_bytes']-b['bytes'],2*gpt.ALIGN)
  self.assertNotEqual(a['uuid'],b['uuid'])
 def test_primary_secondary_headers_entries_and_crcs_for_512_and_4kn(self):
  for sector in [512,4096]:
   plan=gpt.layout(8*1024**3,sector,['one','two']);(offset,secondary),(_,primary)=gpt.images(plan)
   self.assertEqual(primary[510:512],b'\x55\xaa');self.assertEqual(primary[450],0xee)
   headers=[]
   for blob,local in [(primary,sector),(secondary,len(secondary)-sector)]:
    h=bytearray(blob[local:local+92]);self.assertEqual(h[:8],b'EFI PART');saved=struct.unpack_from('<I',h,16)[0];struct.pack_into('<I',h,16,0);self.assertEqual(saved,zlib.crc32(h))
    headers.append(struct.unpack_from('<QQQQ16sQIII',h,24))
   self.assertEqual(headers[0][0],1);self.assertEqual(headers[0][1],plan['bytes']//sector-1);self.assertEqual(headers[1][1],1)
   entry=primary[2*sector:2*sector+16384];start=headers[1][5]*sector-offset
   self.assertEqual(entry,secondary[start:start+16384]);self.assertEqual(zlib.crc32(entry),headers[0][-1])
   for i,v in enumerate(plan['volumes']):
    kind,ident,first,last,_,_=struct.unpack_from('<16s16sQQQ72s',entry,i*128)
    self.assertEqual(uuid.UUID(bytes_le=ident),uuid.UUID(v['uuid']));self.assertEqual(uuid.UUID(bytes_le=kind),gpt.LINUX_DATA)
    self.assertEqual(first*sector,v['start_bytes']);self.assertEqual((last-first+1)*sector,v['bytes'])
 def test_invalid_geometry_and_tiny_layout_refused(self):
  for size,sector,names in [(1024**3,512,['a','b']),(8*1024**3,1024,['a']),(8*1024**3+512,512,['a']),(8*1024**3,512,[])]:
   with self.assertRaises(ValueError):gpt.layout(size,sector,names)
