import os,subprocess,tempfile,unittest
from pathlib import Path
POLICY=Path(__file__).resolve().parents[1]/'target/boot-policy.sh'
class BootPolicy(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.sys=self.root/'sys';(self.sys/'class/block').mkdir(parents=True)
 def partition(self,name='sda1',number=1,usb=False):
  disk=name[:-1];parent=self.sys/('devices/0001:01:00.0/usb1/host0/target0/0/block' if usb else 'devices/0000:00:09.0/ata1/host0/target0/0/block')/disk;part=parent/name;part.mkdir(parents=True);(part/'partition').write_text(str(number));(self.sys/'class/block'/disk).symlink_to(parent);(self.sys/'class/block'/name).symlink_to(part)
 def run_policy(self,script,*args):return subprocess.run(['sh','-c','. "$1"; shift; '+script,'test',str(POLICY),*map(str,args)],capture_output=True,text=True)
 def test_internal_direct_sata_partition_is_required(self):
  self.partition();self.assertEqual(self.run_policy('internal_partition "$1" 1 "$2"','/dev/sda1',self.sys).returncode,0)
  self.assertNotEqual(self.run_policy('internal_partition "$1" 2 "$2"','/dev/sda1',self.sys).returncode,0)
  self.partition('sdb1',usb=True);self.assertNotEqual(self.run_policy('internal_partition "$1" 1 "$2"','/dev/sdb1',self.sys).returncode,0)
  for path in ('/dev/md0p1','/dev/sda1;touch bad','/dev/sda','/dev/sda12'):
   self.assertNotEqual(self.run_policy('internal_partition "$1" 1 "$2"',path,self.sys).returncode,0)
 def test_member_export_is_exact_two_disk_raid1_and_never_code(self):
  uuid='11111111:22222222:33333333:44444444';dev='aaaaaaaa:bbbbbbbb:cccccccc:dddddddd';valid='MD_LEVEL=raid1\nMD_DEVICES=2\nMD_UUID='+uuid+'\nMD_DEV_UUID='+dev+'\n';file=self.root/'metadata'
  file.write_text(valid);self.assertEqual(self.run_policy('root_member_metadata "$1" "$2"',file,uuid).returncode,0)
  for text in (valid.replace('raid1','raid5'),valid.replace('DEVICES=2','DEVICES=3'),valid.replace(uuid,'e'*32),valid+'MD_UUID='+uuid+'\n',valid.replace(dev,'$(touch '+str(self.root/'unsafe')+')'),valid.replace('MD_DEV_UUID','UNKNOWN')):
   file.write_text(text);self.assertNotEqual(self.run_policy('root_member_metadata "$1" "$2"',file,uuid).returncode,0)
  self.assertFalse((self.root/'unsafe').exists())
 def test_metadata_symlinks_and_oversized_exports_are_rejected(self):
  real=self.root/'real';real.write_text('x'*17000);file=self.root/'link';file.symlink_to(real)
  for path in (real,file):self.assertNotEqual(self.run_policy('root_member_metadata "$1" "$2"',path,'expected').returncode,0)
