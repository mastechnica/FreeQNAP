import copy,json,time,unittest
from pathlib import Path
from unittest.mock import patch
import test_nas as fixtures
from freeqnap.nas.storage import Storage

class SplitStorageTests(unittest.TestCase):
 setUp=fixtures.NAS.setUp
 inventory=fixtures.NAS.inventory
 def large(self):
  data=self.inventory();data['disks'].append({**copy.deepcopy(data['disks'][1]),'path':'/dev/sdd','serial':'TEST-d','wwn':'fixture-d'})
  for d in data['disks']:d['size']=10_000_000_000_000
  return data
 def request(self,**kw):return {'name':'raid','level':'raid5','disks':['TEST-a','TEST-b','TEST-c','TEST-d'],'allocation':'free-tail','encrypted':False,'volume_count':2,**kw}
 def store(self):
  original=self.ctx.run
  def run(*a,**kw):
   text=original(*a,**kw)
   if a[0]=='sfdisk':
    d=json.loads(text);d['partitiontable']['lastlba']=10_000_000_000_000//512-34;return json.dumps(d)
   return text
  self.ctx.run=run
  return Storage(self.ctx,self.large,lambda _:True)
 def test_full_four_disk_raid5_is_split_below_arm32_limit(self):
  body=self.store().plan(self.request())['body'];self.assertEqual(len(body['layout']['volumes']),2);self.assertGreater(body['usable_bytes_before_overhead'],29_000_000_000_000)
  for v in body['layout']['volumes']:self.assertLess(v['bytes'],16*1024**4);self.assertGreater(v['bytes'],14_000_000_000_000)
  self.assertEqual(body['regions'][0]['number'],3);self.assertGreaterEqual(body['regions'][0]['start'],12288);self.assertEqual(body['usable_bytes_before_overhead'],body['component_bytes']*3)
 def test_one_oversized_filesystem_is_refused_on_arm32_and_changed_member_refuses_writes(self):
  store=self.store()
  with patch('freeqnap.nas.limits.struct.calcsize',return_value=4),patch('freeqnap.nas.limits.os.sysconf',return_value=4096):
   with self.assertRaises(ValueError):store.plan(self.request(volume_count=1))
  plan=store.plan(self.request());data=self.large();data['disks'][0]['wwn']='replacement';store.collect=lambda:data
  with self.assertRaisesRegex(ValueError,'changed'):store.create({'plan_id':plan['id'],'digest':plan['digest'],'confirmation':plan['confirmation']})
  self.assertFalse(any(c[0][0] in ('sgdisk','mdadm') for c in self.ctx.commands))
 def test_split_names_collision_and_count_validation(self):
  store=self.store();cfg=self.ctx.config();cfg['pools']['raid-2']={};self.ctx.save(cfg)
  with self.assertRaisesRegex(ValueError,'name'):store.plan(self.request())
  for count in (True,3,'2'):
   with self.assertRaises(ValueError):store.plan(self.request(volume_count=count))
 def test_wrong_partition_parent_or_extent_is_refused(self):
  store=Storage(self.ctx);pool={'array_partition':{'bytes':1024**3,'start_bytes':1024**2},'partition_uuid':'fixture'}
  self.ctx.run=lambda *a,**kw:json.dumps({'blockdevices':[{'path':'/dev/md2','children':[{'type':'part','path':'/dev/md2p1','partuuid':'fixture','size':1024**3,'start':2048}]}]})
  with patch.object(store,'array_device',return_value='/dev/md1'):
   with self.assertRaisesRegex(ValueError,'parent'):store.data_device(pool)
  with patch.object(store,'array_device',return_value='/dev/md2'):
   pool['array_partition']['bytes']+=4096
   with self.assertRaisesRegex(ValueError,'extent'):store.data_device(pool)

 def test_existing_exact_kernel_partition_avoids_duplicate_add_and_wrong_extent_refuses(self):
  store=Storage(self.ctx);region={'partition':'/dev/sdc1','number':1,'disk':{'path':'/dev/sdc'},'start':2048,'end':4095}
  with patch.object(store,'kernel_partition_matches',return_value=True):store.ensure_partition(region)
  self.assertFalse(self.ctx.commands)
  directory=self.root/'sys/sdc1';directory.mkdir(parents=True);(directory/'start').write_text('2048');(directory/'size').write_text('2048')
  self.assertTrue(store.kernel_partition_matches(region,self.root/'sys'))
  (directory/'size').write_text('4096')
  with self.assertRaisesRegex(ValueError,'extent'):store.kernel_partition_matches(region,self.root/'sys')
 def test_registration_race_accepts_only_the_verified_matching_partition(self):
  store=Storage(self.ctx);region={'partition':'/dev/sdc1','number':1,'disk':{'path':'/dev/sdc'},'start':2048,'end':4095}
  self.ctx.run=lambda *a,**kw: (_ for _ in ()).throw(ValueError('partx already registered')) if a[0]=='partx' else ''
  with patch.object(store,'kernel_partition_matches',side_effect=[False,True,True]):store.ensure_partition(region)
  with patch.object(store,'kernel_partition_matches',return_value=False):
   with self.assertRaises(ValueError):store.ensure_partition(region)

 def test_kernel_progress_is_validated_not_inferred_from_array_mount(self):
  self.assertEqual(Storage.sync_progress('50 / 200')['percent'],25)
  for value in ('none','delayed','-1 / 100','101 / 100','0 / 0','100'):
   self.assertIsNone(Storage.sync_progress(value))
