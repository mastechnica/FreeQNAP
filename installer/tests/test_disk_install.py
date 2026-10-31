import copy
import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).resolve().parents[1]/'target/install-disks.py'
spec=importlib.util.spec_from_file_location('disk_install',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class DiskInstallTests(unittest.TestCase):
 def fixture(self):
  disks=[{'serial':'SERIAL-'+str(i),'wwn':'0x5000cca21122334'+str(i),'size':100*1024**3,
     'path':'/dev/sd'+chr(97+i),'internal_sata':True,'readonly':False,'busy':False} for i in range(4)]
  plan={'schema':1,'unit_fingerprint':'unit-A','install_id':'a'*32,'os_mirror_serials':['SERIAL-0','SERIAL-1'],
   'erase_disks':[{k:d[k] for k in ('serial','wwn','size')} for d in disks],
   'root_password_method':'first-login','artifacts':{name:{'bytes':100,'sha256':'b'*64} for name in ('uImage','debian-armhf-base.tar.gz')}}
  return plan,disks
 def test_explicit_four_disk_erase_keeps_two_disk_os_mirror(self):
  plan,observed=self.fixture();self.assertEqual(len(module.validate_plan(plan,observed,'unit-A')),4)
  # Resolve from immutable identities, even after kernel sdX enumeration changes.
  observed[0]['path']='/dev/sdz';self.assertEqual(module.validate_plan(plan,observed,'unit-A')[0]['path'],'/dev/sdz')
 def test_wrong_unit_changed_disk_duplicate_identity_and_busy_disk_rejected(self):
  plan,observed=self.fixture()
  with self.assertRaises(ValueError):module.validate_plan(plan,observed,'unit-B')
  for key,value in (('size',120*1024**3),('wwn','0x5000cca211223399'),('internal_sata',False),('readonly',True),('busy',True)):
   changed=copy.deepcopy(observed);changed[3][key]=value
   with self.assertRaises(ValueError):module.validate_plan(plan,changed,'unit-A')
  with self.assertRaises(ValueError):module.validate_plan(plan,observed+[observed[0]],'unit-A')
 def test_invalid_mirror_or_unpinned_artifact_rejected(self):
  plan,observed=self.fixture()
  for change in ('duplicate','unknown','artifact','password'):
   bad=copy.deepcopy(plan)
   if change=='duplicate':bad['os_mirror_serials']=['SERIAL-0','SERIAL-0']
   if change=='unknown':bad['os_mirror_serials']=['SERIAL-0','UNKNOWN']
   if change=='artifact':bad['artifacts']['uImage']['sha256']='unverified'
   if change=='password':bad['root_password_method']='default-password'
   with self.assertRaises(ValueError):module.validate_plan(bad,observed,'unit-A')

if __name__=='__main__':unittest.main()
