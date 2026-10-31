import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import unittest
import zlib
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

path=Path(__file__).resolve().parents[1]/'flash-backup.py'
spec=importlib.util.spec_from_file_location('flash_backup',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class FlashBackupTests(unittest.TestCase):
 def test_fresh_crc_must_be_single_unambiguous_result(self):
  line='CRC32 for 10000000 ... 11ffffff ==> aabbccdd'
  self.assertEqual(module.crc_result(line),'aabbccdd')
  for value in ('no result',line+'\n'+line):
   with self.assertRaises(ValueError):module.crc_result(value)
 def test_host_backup_and_receiver_receipt_must_both_match_uart_crc(self):
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory)/'spi-original.bin';data=b'test original bytes';p.write_bytes(data)
   sha=hashlib.sha256(data).hexdigest();crc=f'{zlib.crc32(data):08x}'
   receipt=p.with_name(p.name+'.json');receipt.write_text(json.dumps({'bytes':len(data),'sha256':sha,'crc32':crc}))
   with patch.dict(module.SIZES,{p.name:len(data)}):
    self.assertEqual(module.verified_local_backup(p,crc),sha)
    with self.assertRaises(ValueError):module.verified_local_backup(p,'00000000')
    receipt.write_text(json.dumps({'bytes':len(data),'sha256':'0'*64,'crc32':crc}))
    with self.assertRaises(ValueError):module.verified_local_backup(p,crc)

if __name__=='__main__':unittest.main()
