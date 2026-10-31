import copy
import hashlib
import importlib.util
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

path=Path(__file__).resolve().parents[1]/'flash-install.py'
spec=importlib.util.spec_from_file_location('flash_install',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class FlashInstallTests(unittest.TestCase):
 def fixture(self):
  plan={'install_id':'a'*32,'unit_fingerprint':'unit-A'};image=b'accepted kernel';manifest={'kernel':'test-kernel'}
  proof={**plan,'verified_at':1000,'normal_boot_accepted':True,'image_sha256':hashlib.sha256(image).hexdigest(),'kernel':'test-kernel',
   'cmdline':'console=ttyS0','debug_shell_inactive':True,'raid_degraded':0,'raid_sync_action':'idle','failed_units':'',
   'services':{s:'active' for s in ('eyeq-cooling','eyeq-drive-green','eyeq-buttons','eyeq-disk-leds','ssh','systemd-networkd','mdmonitor')},
   'network_restarts':{'passed':True,'results':[{'interface':p,'cycle':i,'upload_download_sha256_match':True} for p in ('enp0s1','enp0s3') for i in (1,2)]},
   'temperatures':[55000],'root_password_status':'L','hardware':{'global_fan_mode':'7','fans':[{'counter':280}]*3}}
  backup={**plan,'complete':True,'backups':{n:{'independent_reread_match':True} for n in ('boot1-original.bin','boot2-original.bin','spi-original.bin')}}
  return plan,proof,backup,manifest,image
 def test_only_complete_normal_acceptance_can_authorize_first_slot(self):
  args=self.fixture();module.validate_acceptance(*args,now=1100)
  for key,value in (('unit_fingerprint','another-unit'),('verified_at',0),('cmdline','systemd.debug_shell=ttyS0'),('debug_shell_inactive',False),('raid_degraded',1),('raid_sync_action','resync'),('failed_units','ssh.service failed'),('image_sha256','0'*64),('temperatures',[75000]),('root_password_status','NP')):
   plan,proof,backup,manifest,image=self.fixture();proof[key]=value
   with self.assertRaises(ValueError):module.validate_acceptance(plan,proof,backup,manifest,image,now=4000 if key=='verified_at' else 1100)
 def test_sparse_network_service_or_backup_claims_are_rejected(self):
  for kind in ('network','service','reread','missing-bank','fan'):
   plan,proof,backup,manifest,image=self.fixture()
   if kind=='network':proof['network_restarts']['results'].pop()
   if kind=='service':proof['services'].pop('mdmonitor')
   if kind=='reread':backup['backups']['spi-original.bin']['independent_reread_match']=False
   if kind=='missing-bank':backup['backups'].pop('boot2-original.bin')
   if kind=='fan':proof['hardware']['fans']=[{'counter':0}]*3
   with self.assertRaises(ValueError):module.validate_acceptance(plan,proof,backup,manifest,image,now=1100)

 def test_ram_only_manifest_cannot_be_promoted_by_normal_acceptance(self):
  for fields in ({'ram_only':True,'flash_allowed':False},{'flash_allowed':False}):
   plan,proof,backup,manifest,image=self.fixture();manifest.update(fields)
   with self.assertRaisesRegex(ValueError,'RAM-only'):module.validate_acceptance(plan,proof,backup,manifest,image,now=1100)

if __name__=='__main__':unittest.main()
