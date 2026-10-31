import base64
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import zlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import advance,verified_image,observed_profile,Console,disk_plan,parse_inventory

PROFILE='''U-Boot 2015.07-alpine_db-1.73.5-HAL

I2C: ready
DRAM:  2 GiB
Board config ID: alpine_db_qnap
NAND:  512 MiB
SF: total 2 MiB
Page size       2048 b
Erase size    131072 b
bootcmd=nand read $loadaddr 0 0x2000000;run sata_cmd;bootm $loadaddr - $fdtaddr;
ALPINE_DB> '''

class Invariants(unittest.TestCase):
 def test_bootloader_fault_prevents_next_command_after_unexpected_reset(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder);(p/'console.bin').write_bytes(PROFILE.encode());(p/'ready.json').write_text(json.dumps({'pid':os.getpid()}));c=Console(p)
   def fail(_):
    with (p/'console.bin').open('ab') as out:out.write(b'scsi scan\r\ndata abort\r\nResetting CPU ...\r\n'+PROFILE.encode())
   c.send=fail
   with self.assertRaisesRegex(RuntimeError,'no subsequent command'):c.command('version')
 def test_unaccepted_vendor_disk_loading_is_blocked_before_send(self):
  c=object.__new__(Console)
  for command in ('scsi scan','scsi reset','ext4load scsi 0:1 08000000 /freeqnap/uImage'):
   with self.assertRaisesRegex(ValueError,'unaccepted'):c.command(command)
 def test_disk_identity_without_udev_and_malformed_vpd_rejection(self):
  fields={'kernel':'6.12.114-eyeq-ts431xeu-freeqnap1','board':'QNAP TS-431XeU','compatible':'qnap,ts-431xeu\0al,alpine\0','cpu':'processor : 0\nprocessor : 1\nprocessor : 2\nprocessor : 3\n','memory':'MemTotal: 2067632 kB\n','mounts':'rootfs / rootfs rw 0 0','mdstat':'unused devices: <none>','swaps':'Filename Type Size Used Priority\n','cooling_ack':'1','factory_macs_verified':'1','existing_root_failed':'0','thermal.zone0':'41000','mac.eth0':'24:5e:be:11:22:30','mac.eth1':'24:5e:be:11:22:31','mac.eth2':'24:5e:be:11:22:32','disks':json.dumps({'blockdevices':[{'name':'sda','type':'disk','serial':None,'wwn':None}]}),'disk.sda.vpd80':(b'\0\x80\0\x08DISK0001').hex(),'disk.sda.wwid':'naa.5000cca211223344'}
  def text():return '\n'.join('__FREEQNAP_FIELD__|'+k+'|'+base64.b64encode(v.encode()).decode() for k,v in fields.items())
  result=parse_inventory(text())
  self.assertEqual(result['disks'][0]['serial'],'DISK0001');self.assertEqual(result['disks'][0]['wwn'],'0x5000cca211223344')
  fields['disk.sda.vpd80']=(b'\0\x80\0\x09DISK0001').hex()
  with self.assertRaises(ValueError):parse_inventory(text())
  fields['disk.sda.vpd80']=(b'\0\x80\0\x08DISK0001').hex();fields['disks']=json.dumps({'blockdevices':[{'name':'sda','type':'disk','serial':'OTHER'}]})
  with self.assertRaises(ValueError):parse_inventory(text())
 def test_wrong_board_and_geometry(self):
  self.assertTrue(observed_profile(PROFILE,'TS-431XeU')['boot_family_match'])
  for changed in (PROFILE.replace('2 GiB','1 GiB'),PROFILE.replace('2048 b','4096 b'),PROFILE.replace('0x2000000','0x1000000')):
   with self.assertRaises(ValueError):observed_profile(changed,'TS-431XeU')
  with self.assertRaises(ValueError):observed_profile(PROFILE,'TS-431P')
 def test_version_reply_does_not_hide_real_boot_epoch(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder);(p/'console.bin').write_bytes((PROFILE+'version\r\nU-Boot 2015.07-alpine_db-1.73.5-HAL\r\nALPINE_DB> ').encode());(p/'ready.json').write_text(json.dumps({'pid':os.getpid()}))
   c=Console(p);self.assertIn(b'DRAM:  2 GiB',c.current())
   (p/'console.bin').write_bytes((PROFILE+PROFILE.replace('2 GiB','1 GiB')).encode());self.assertNotIn(b'2 GiB',c.current())
 def test_stages_cannot_skip_or_overwrite(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'session.json'
   with self.assertRaises(ValueError):advance(p,'ram_loaded',{})
   advance(p,'serial_ready',{'model':'TS-431XeU'})
   with self.assertRaises(ValueError):advance(p,'serial_ready',{})
   advance(p,'inspected',{'fresh':True});d=json.loads(p.read_text());self.assertEqual(d['events'][1]['previous'],d['events'][0]['hash']);self.assertEqual(p.stat().st_mode&0o777,0o600)
 def test_corrupt_or_wrong_architecture_image_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder);data=b'fake kernel payload'*100
   h=bytearray(struct.pack('>7I4B32s',0x27051956,0,0,len(data),0x8000,0x8000,zlib.crc32(data),5,2,2,0,b'FreeQNAP test'))
   h[4:8]=struct.pack('>I',zlib.crc32(h));image=bytes(h)+data
   m={'schema':1,'model':'TS-431XeU','architecture':'armhf','artifacts':{'uImage':{'bytes':len(image),'sha256':hashlib.sha256(image).hexdigest(),'crc32':f'{zlib.crc32(image):08x}'}}}
   (p/'manifest.json').write_text(json.dumps(m));(p/'uImage').write_bytes(image);self.assertEqual(verified_image(p)[1],image)
   (p/'uImage').write_bytes(image[:-1]+b'x')
   with self.assertRaises(ValueError):verified_image(p)
   (p/'uImage').write_bytes(image);m['architecture']='arm64';(p/'manifest.json').write_text(json.dumps(m))
   with self.assertRaises(ValueError):verified_image(p)
 def test_disk_plan_refuses_wrong_mounted_duplicate_stale_and_active_swap(self):
  inv={'unit_fingerprint':'test-unit','recorded_at':time.time(),'fields':{'mdstat':'Personalities : [raid1]\nunused devices: <none>','swaps':'Filename Type Size Used Priority\n','disk.sda.sysfs':'/sys/devices/pci0000:00/0000:00:09.0/ata1/disk','disk.sdb.sysfs':'/sys/devices/pci0000:00/0000:00:09.0/ata2/disk'},'disks':[{'path':'/dev/sda','type':'disk','size':100*1024**3,'serial':'DISK-A','mountpoints':[None],'children':[{'path':'/dev/sda1','mountpoints':[None],'fstype':'swap'}]},{'path':'/dev/sdb','type':'disk','size':100*1024**3,'serial':'DISK-B','mountpoints':[None]}]}
  self.assertFalse(disk_plan(inv,['DISK-A','DISK-B'])['writes_performed'])
  for ids in (['DISK-A','DISK-A'],['DISK-A','UNKNOWN']):
   with self.assertRaises(ValueError):disk_plan(inv,ids)
  inv['disks'][0]['children'][0]['mountpoints']=['/data']
  with self.assertRaises(ValueError):disk_plan(inv,['DISK-A','DISK-B'])
  inv['disks'][0]['children'][0]['mountpoints']=[None];inv['fields']['swaps']+=' /dev/sda1 partition 1000 0 -2\n'
  with self.assertRaises(ValueError):disk_plan(inv,['DISK-A','DISK-B'])
  inv['fields']['swaps']='';inv['recorded_at']=time.time()-1000
  with self.assertRaises(ValueError):disk_plan(inv,['DISK-A','DISK-B'])
 def test_disk_record_is_never_shell_code(self):
  parser=Path(__file__).resolve().parents[1]/'target/boot-record.sh'
  valid='FORMAT=1\nMODEL=TS-431XeU\nINSTALL_ID='+'1'*32+'\nUNIT_MAC=245ebe112233\nROOT_MD_UUID=11111111:22222222:33333333:44444444\nROOT_FS_UUID=11111111-2222-3333-4444-555555555555\n'
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'record';marker=Path(folder)/'unsafe'
   def run(text):
    p.write_text(text);return subprocess.run(['sh','-c','. "$1"; parse_record "$2"','test',str(parser),str(p)],capture_output=True).returncode
   self.assertEqual(run(valid),0)
   for text in (valid+'FORMAT=1\n',valid.replace('MODEL=TS-431XeU','MODEL=$(touch '+str(marker)+')'),valid+'UNKNOWN=x\n',valid.replace('ROOT_MD_UUID=11111111','ROOT_MD_UUID=bad')):
    self.assertNotEqual(run(text),0)
   self.assertFalse(marker.exists())

if __name__=='__main__':unittest.main()
