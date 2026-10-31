import copy
import base64
import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from freeqnap.nas.common import Context,canonical
from freeqnap.nas.external import External,usb_probe,attached

class USBTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.commands=[]
  self.disk={'name':'sdz','path':'/dev/sdz','type':'disk','size':4*1024**3,'model':'Fixture logical USB volume','serial':'TEST-ONLY-LUN','wwn':None,'tran':'usb','fstype':None,'uuid':None,'mountpoints':[],'ro':False}
  self.usb={'identity':{'vendor_id':'ffff','product_id':'0001','serial':'FIXTURE-ONLY','interface':'00','channel':'0','target':'0','lun':'0'},'enclosure_id':'e'*32,'stable':True,'port':'1-1','product':'TR-004 fixture','speed_mbps':'5000','driver':'usb-storage','bytes':self.disk['size'],'member_health':'unavailable'}
  self.usb['id']=hashlib.sha256(canonical(self.usb['identity'])).hexdigest()[:32]
  self.data={'root':{'uuid':'ROOT-PROTECTED'},'disks':[self.disk],'sampled_at':time.time(),'errors':[]}
  self.ctx=Context(self.root/'state',runner=self.fake_run)
  self.service=External(self.ctx,collector=lambda:copy.deepcopy(self.data),probe=self.probe)
 def probe(self,path):
  if path!=self.disk['path']:raise ValueError('not USB')
  return copy.deepcopy(self.usb)
 def fake_run(self,*args,**kw):
  self.commands.append(args)
  if args[0]=='swapon':return ''
  if args[0]=='wipefs':return '{"signatures":[]}'
  if args[0]=='blockdev':return str(512 if args[1]=='--getss' else self.disk['size'])
  if args[0]=='findmnt':return '{"filesystems":[]}'
  if args[0] in ('sg_sync','systemctl'):return ''
  raise ValueError('Unexpected fixture command: '+args[0])
 def review(self,plan):return {'plan_id':plan['id'],'digest':plan['digest'],'confirmation':plan['confirmation']}
 def fs(self):
  self.disk['children']=[{'name':'sdz1','path':'/dev/sdz1','type':'part','size':self.disk['size']-1024**2,'fstype':'ext4','uuid':'fixture-filesystem','partuuid':'fixture-partition','mountpoints':[]}]
 def test_usb_descriptor_identity_uses_enclosure_serial_interface_and_lun(self):
  sys=self.root/'sys';block=sys/'class/block/sdz';block.mkdir(parents=True)
  usb=sys/'devices/usb1/1-1';interface=usb/'1-1:1.0';device=interface/'host1/target1:0:0/1:0:0:0';device.mkdir(parents=True)
  for field,value in [('idVendor','ffff'),('idProduct','0001'),('serial','FIXTURE-ONLY'),('product','TR-004 fixture'),('speed','5000')]: (usb/field).write_text(value)
  (interface/'bInterfaceNumber').write_text('00');(block/'device').symlink_to(device);(block/'size').write_text(str(self.disk['size']//512))
  value=usb_probe('/dev/sdz',sysroot=sys)
  self.assertTrue(value['stable']);self.assertEqual(value['identity']['lun'],'0');self.assertEqual(value['bytes'],self.disk['size'])
  self.assertEqual(value['id'],self.usb['id']);(usb/'serial').write_text('OTHER-ENCLOSURE')
  self.assertNotEqual(usb_probe('/dev/sdz',sysroot=sys)['id'],value['id'])
 def test_discovery_is_read_only_and_never_offers_usb_for_boot(self):
  result=self.service.discover();self.assertEqual(len(result['devices']),1);self.assertFalse(result['devices'][0]['install_target'])
  self.assertFalse(result['writes_performed']);self.assertFalse(result['vendor_commands_issued']);self.assertFalse(self.commands)
 def test_os_and_missing_serial_external_devices_are_protected(self):
  self.disk['children']=[{'uuid':'ROOT-PROTECTED','type':'part','path':'/dev/sdz1','mountpoints':[] }]
  with self.assertRaises(ValueError):self.service.create_plan({'id':self.usb['id'],'name':'external'})
  self.disk['children']=[];self.usb['stable']=False
  with self.assertRaises(ValueError):self.service.create_plan({'id':self.usb['id'],'name':'external'})
  self.assertFalse(self.commands)
 def test_active_mount_holders_and_swap_are_not_format_candidates(self):
  for field,value in [('mountpoints',['/other']),('children',[{'type':'crypt','path':'/dev/mapper/fixture','mountpoints':[]}])]:
   old=self.disk.get(field);self.disk[field]=value
   with self.assertRaises(ValueError):self.service.create_plan({'id':self.usb['id'],'name':'external'})
   if old is None:self.disk.pop(field)
   else:self.disk[field]=old
  original=self.ctx.run
  self.ctx.run=lambda *a,**k:'/dev/sdz\n' if a[0]=='swapon' else original(*a,**k)
  with self.assertRaises(ValueError):self.service.create_plan({'id':self.usb['id'],'name':'external'})
 def test_swapped_or_disconnected_enclosure_refused_before_any_write(self):
  plan=self.service.create_plan({'id':self.usb['id'],'name':'external','encrypted':True})
  self.data['disks']=[]
  with self.assertRaisesRegex(ValueError,'missing'):self.service.create({**self.review(plan),'secret':{'password':'fixture private password'}})
  self.assertFalse(any(c[0] in ('mkfs.ext4','sgdisk','cryptsetup') or '--all' in c for c in self.commands));self.assertFalse(self.ctx.state.jobs())
 def test_existing_ext4_import_defaults_read_only_and_does_not_format(self):
  self.fs();plan=self.service.import_plan({'id':self.usb['id'],'name':'external','uuid':'fixture-filesystem'})
  self.assertTrue(plan['body']['read_only']);self.assertFalse(plan['body']['auto_mount'])
  with patch('freeqnap.nas.storage.Storage.mount') as mount:result=self.service.import_volume(self.review(plan))
  self.assertFalse(result['data_formatted']);self.assertTrue(result['read_only']);self.assertEqual(mount.call_count,1)
  self.assertEqual(self.ctx.config()['pools']['external']['kind'],'usb')
  self.assertFalse(any(c[0] in ('mkfs.ext4','sgdisk','wipefs','cryptsetup') for c in self.commands))
 def test_duplicate_filesystem_uuid_refuses_import(self):
  self.fs();other=copy.deepcopy(self.disk);other['path']='/dev/sdy';self.data['disks'].append(other)
  with self.assertRaises(ValueError):self.service.import_plan({'id':self.usb['id'],'name':'external','uuid':'fixture-filesystem'})
 def test_usb_import_no_silent_filesystem_conversion(self):
  self.fs();self.disk['children'][0]['fstype']='ntfs'
  with self.assertRaises(ValueError):self.service.import_plan({'id':self.usb['id'],'name':'external','uuid':'fixture-filesystem'})
 def test_attached_check_refuses_replacement_or_removed_device(self):
  pool={'external':{**copy.deepcopy(self.usb),'disk_path':'/dev/sdz'}}
  with patch('freeqnap.nas.external.usb_probe',return_value={**self.usb,'bytes':1}):
   with self.assertRaises(ValueError):attached(pool)
  with patch('freeqnap.nas.external.usb_probe',return_value={**self.usb,'disk_sequence':'replugged'}):
   with self.assertRaises(ValueError):attached(pool)
  with patch('freeqnap.nas.external.usb_probe',side_effect=FileNotFoundError):
   with self.assertRaises(OSError):attached(pool)
 def test_eject_flushes_only_identified_idle_enclosure_without_vendor_commands(self):
  plan=self.service.eject_plan({'id':self.usb['id']});stopped=[]
  result=self.service.eject(self.review(plan),lambda pools:stopped.append(pools))
  self.assertTrue(result['safe_to_unplug']);self.assertFalse(result['device_powered_off']);self.assertEqual(stopped,[[]])
  self.assertIn(('blockdev','--flushbufs','/dev/sdz'),self.commands);self.assertIn(('sg_sync','/dev/sdz'),self.commands)
  self.assertFalse(any(c[0] in ('smartctl','sgdisk','wipefs','mkfs.ext4','cryptsetup') for c in self.commands))
 def test_eject_refuses_unknown_mount_and_active_operation(self):
  self.disk['mountpoints']=['/unmanaged'];plan=self.service.eject_plan({'id':self.usb['id']})
  with self.assertRaises(ValueError):self.service.eject(self.review(plan),lambda p:self.fail('must not stop services'))
  self.disk['mountpoints']=[];plan=self.service.eject_plan({'id':self.usb['id']});self.ctx.state.enqueue('backup.run',{})
  with self.assertRaises(ValueError):self.service.eject(self.review(plan),lambda p:self.fail('must not stop services'))
 def registered(self):
  self.fs();plan=self.service.import_plan({'id':self.usb['id'],'name':'external','uuid':'fixture-filesystem'})
  with patch('freeqnap.nas.storage.Storage.mount'):self.service.import_volume(self.review(plan))
  return self.ctx.config()['pools']['external']
 def test_browser_reads_existing_files_but_refuses_symlink_and_parent_escape(self):
  pool=self.registered();mount=self.root/'volume';mount.mkdir();(mount/'file.txt').write_text('preserved data');outside=self.root/'outside';outside.write_text('private');(mount/'link').symlink_to(outside)
  with patch.object(self.ctx,'volume',return_value=(pool,mount)):
   read=self.service.read_file({'pool':'external','path':'file.txt'})
   self.assertEqual(base64.b64decode(read['data_base64']),b'preserved data')
   with self.assertRaises(OSError):self.service.read_file({'pool':'external','path':'link'})
   with self.assertRaises(ValueError):self.service.read_file({'pool':'external','path':'../outside'})
   with self.assertRaises(ValueError):self.service.list_files({'pool':'external','path':'.freeqnap'})
 def test_forget_keeps_data_and_requires_unused_exact_registration(self):
  pool=self.registered();marker=self.root/'untouched';marker.write_text('data remains')
  plan=self.service.forget_plan({'pool':'external'});result=self.service.forget(self.review(plan))
  self.assertFalse(result['data_deleted']);self.assertEqual(marker.read_text(),'data remains');self.assertNotIn('external',self.ctx.config()['pools'])
 def test_forget_refuses_dependents_and_changed_plan(self):
  self.registered();cfg=self.ctx.config();cfg['shares']['used']={'pool':'external'};self.ctx.save(cfg)
  with self.assertRaises(ValueError):self.service.forget_plan({'pool':'external'})
  cfg['shares']={};self.ctx.save(cfg);plan=self.service.forget_plan({'pool':'external'})
  cfg['pools']['external']['read_only']=False;self.ctx.save(cfg)
  with self.assertRaises(ValueError):self.service.forget(self.review(plan))

 def test_initialization_clears_old_partition_signature_before_mkfs(self):
  self.fs();plan=self.service.create_plan({'id':self.usb['id'],'name':'external','encrypted':False})
  original=self.ctx.run
  def runner(*args,**kw):
   if args[0]=='sgdisk':
    self.commands.append(args)
    if '--new=1:0:0' in args:self.disk['children'][0]['partuuid']='fresh-partition'
    return ''
   if args[0] in ('partx','udevadm','mkfs.ext4'):self.commands.append(args);return ''
   if args[0]=='blkid':return 'fresh-filesystem'
   return original(*args,**kw)
  self.ctx.run=runner
  with patch('freeqnap.nas.storage.Storage.mount'):self.service.create(self.review(plan))
  index=next(n for n,c in enumerate(self.commands) if c[0]=='mkfs.ext4')
  self.assertIn(('wipefs','--all','/dev/sdz1'),self.commands[:index])

 def test_arm32_ext4_addressability_refuses_oversize_without_writes(self):
  from freeqnap.nas.limits import require_ext4_size
  limit=16*1024**4
  self.assertEqual(require_ext4_size(limit,pointer_bytes=4,page_bytes=4096),limit)
  with self.assertRaises(ValueError):require_ext4_size(limit+4096,pointer_bytes=4,page_bytes=4096)
  self.assertIsNone(require_ext4_size(30*10**12,pointer_bytes=8,page_bytes=4096))

 def test_large_external_plan_splits_full_capacity_and_rejects_single_on_arm32(self):
  self.disk['size']=30002393382912;self.usb['bytes']=self.disk['size']
  with patch('freeqnap.nas.limits.ext4_limit',return_value=16*1024**4):
   with self.assertRaises(ValueError):self.service.create_plan({'id':self.usb['id'],'name':'external','encrypted':False})
   plan=self.service.create_plan({'id':self.usb['id'],'name':'external','encrypted':False,'volume_count':2})
  self.assertEqual([v['name'] for v in plan['body']['layout']['volumes']],['external-1','external-2'])
  self.assertTrue(all(v['bytes']<16*1024**4 for v in plan['body']['layout']['volumes']))
  self.assertFalse(any('--all' in c for c in self.commands))
 def test_split_initialization_failure_is_durable_and_never_auto_retried(self):
  plan=self.service.create_plan({'id':self.usb['id'],'name':'external','encrypted':False,'volume_count':2})
  with patch('freeqnap.nas.external.gpt.write',side_effect=OSError('injected metadata failure')):
   with self.assertRaises(OSError):self.service.create(self.review(plan))
  jobs=self.ctx.state.jobs();self.assertEqual(len(jobs),1);self.assertEqual(jobs[0]['status'],'retryable')
  self.assertFalse(self.ctx.config()['pools']);self.assertFalse(any(c[0]=='mkfs.ext4' for c in self.commands))
  with self.assertRaises(ValueError):self.service.create(self.review(plan))
 def test_split_names_and_count_revalidated_before_plan(self):
  for count in [True,0,9,'2']:
   with self.assertRaises(ValueError):self.service.create_plan({'id':self.usb['id'],'name':'external','volume_count':count})
  cfg=self.ctx.config();cfg['pools']['external-2']={'name':'external-2'};self.ctx.save(cfg)
  with self.assertRaises(ValueError):self.service.create_plan({'id':self.usb['id'],'name':'external','volume_count':2})

 def test_import_sibling_partition_preserves_existing_registered_mount(self):
  self.fs();plan=self.service.import_plan({'id':self.usb['id'],'name':'first','uuid':'fixture-filesystem'})
  with patch('freeqnap.nas.storage.Storage.mount'):self.service.import_volume(self.review(plan))
  self.disk['children'][0]['mountpoints']=['/srv/freeqnap/volumes/first']
  self.disk['children'].append({'name':'sdz2','path':'/dev/sdz2','type':'part','size':1024**3,'fstype':'ext4','uuid':'second-filesystem','partuuid':'second-partition','mountpoints':[]})
  plan=self.service.import_plan({'id':self.usb['id'],'name':'second','uuid':'second-filesystem'})
  with patch('freeqnap.nas.storage.Storage.mount'):self.service.import_volume(self.review(plan))
  self.assertEqual(set(self.ctx.config()['pools']),{'first','second'});self.assertFalse(any(c[0] in ('mkfs.ext4','sgdisk','cryptsetup') for c in self.commands))
  with self.assertRaises(ValueError):self.service.import_plan({'id':self.usb['id'],'name':'duplicate','uuid':'fixture-filesystem'})

if __name__=='__main__':unittest.main()
