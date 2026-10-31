import hashlib
import json
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backups import receive_backup,SIZES,negotiate_options

class BackupTests(unittest.TestCase):
 def test_negotiated_upload_block_size_and_exact_size_limits(self):
  size,ack,requested=negotiate_options([b'blksize',b'1468',b'tsize',b'3000',b''],3000)
  self.assertEqual(size,1468);self.assertEqual(ack,b'\0\6blksize\x001468\0tsize\x003000\0')
  for fields in ([b'blksize',b'0'],[b'tsize',b'3001'],[b'blksize',b'1468',b'blksize',b'512'],[b'blksize']):
   with self.assertRaises(ValueError):negotiate_options(fields,3000)
 def test_real_upload_after_option_acknowledgement(self):
  with tempfile.TemporaryDirectory() as directory,socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as client:
   client.bind(('127.0.0.1',0));client.settimeout(2);data=b'y'*3000;result=[]
   def receiver():
    try:result.append(receive_backup('127.0.0.1',client.getsockname(),'spi-original.bin',directory,timeout=.1,options=[b'blksize',b'1468',b'tsize',b'3000',b'']))
    except BaseException as error:result.append(error)
   with patch.dict(SIZES,{'spi-original.bin':len(data)}):
    thread=threading.Thread(target=receiver);thread.start();ack,peer=client.recvfrom(2048);self.assertEqual(ack[:2],b'\0\6')
    for number,offset in enumerate(range(0,len(data),1468),1):
     client.sendto(struct.pack('!HH',3,number)+data[offset:offset+1468],peer)
     ack,_=client.recvfrom(2048);self.assertEqual(ack,struct.pack('!HH',4,number))
    thread.join(3);self.assertFalse(thread.is_alive());self.assertIsInstance(result[0],dict);self.assertEqual((Path(directory)/'spi-original.bin').read_bytes(),data)
 def test_duplicate_block_is_not_appended_and_backups_cannot_be_overwritten(self):
  with tempfile.TemporaryDirectory() as directory,socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as client:
   client.bind(('127.0.0.1',0));client.settimeout(2);data=b'x'*1027;result=[]
   def receiver():
    try:result.append(receive_backup('127.0.0.1',client.getsockname(),'spi-original.bin',directory,timeout=.1))
    except BaseException as error:result.append(error)
   with patch.dict(SIZES,{'spi-original.bin':len(data)}):
    thread=threading.Thread(target=receiver);thread.start();ack,peer=client.recvfrom(2048);self.assertEqual(ack,struct.pack('!HH',4,0))
    for number,offset in enumerate(range(0,len(data),512),1):
     packet=struct.pack('!HH',3,number)+data[offset:offset+512]
     client.sendto(packet,peer);ack,_=client.recvfrom(2048);self.assertEqual(ack,struct.pack('!HH',4,number))
     if number==1:
      client.sendto(packet,peer);ack,_=client.recvfrom(2048);self.assertEqual(ack,struct.pack('!HH',4,1))
    thread.join(3);self.assertFalse(thread.is_alive());self.assertIsInstance(result[0],dict)
    p=Path(directory)/'spi-original.bin';self.assertEqual(p.read_bytes(),data);self.assertEqual(p.stat().st_mode&0o777,0o600)
    receipt=json.loads(p.with_name(p.name+'.json').read_text());self.assertEqual(receipt['sha256'],hashlib.sha256(data).hexdigest());self.assertFalse(receipt['uart_crc_verified'])
    with self.assertRaises(FileExistsError):receive_backup('127.0.0.1',client.getsockname(),p.name,directory)
 def test_unlisted_path_is_rejected_without_creating_a_file(self):
  with tempfile.TemporaryDirectory() as directory:
   with self.assertRaises(ValueError):receive_backup('127.0.0.1',('127.0.0.1',12345),'../unsafe',directory)
   self.assertEqual(list(Path(directory).iterdir()),[])

if __name__=='__main__':unittest.main()
