import os,subprocess,unittest
from pathlib import Path
SCRIPT=Path(__file__).resolve().parents[1]/'tools/build-native-kernel.sh'
class KernelBuildProfileTests(unittest.TestCase):
 def run_profile(self,suffix,security,version='6.12.115'):
  env={k:v for k,v in os.environ.items() if not k.startswith('FREEQNAP_')}
  env.update(FREEQNAP_LOCALVERSION='-eyeq-ts431xeu-freeqnap'+str(suffix),FREEQNAP_SECURITY_PROFILE=security,FREEQNAP_EXPECTED_KERNEL_VERSION=version,FREEQNAP_BOOT_PROFILE='complete-mirror-v1',FREEQNAP_DEPMOD='/usr/bin/true')
  r=subprocess.run(['sh',str(SCRIPT)],env=env,capture_output=True,text=True,timeout=5)
  return r,r.stdout+r.stderr
 def test_experiment_cannot_use_baseline(self):self.assertIn('separate reviewed candidate',self.run_profile(8,'baseline')[1])
 def test_experiment_cannot_use_memory_only_profile(self):self.assertIn('separate reviewed candidate',self.run_profile(8,'arm-hardening-v1')[1])
 def test_memory_candidate_cannot_adopt_cpu_experiment(self):self.assertIn('separate reviewed candidate',self.run_profile(7,'arm-hardening-ibe-v1')[1])
 def test_memory_candidate_requires_its_profile(self):self.assertIn('separate reviewed candidate',self.run_profile(7,'baseline')[1])
 def test_reviewed_experiment_stops_without_source(self):
  r,out=self.run_profile(8,'arm-hardening-ibe-v1');self.assertNotEqual(r.returncode,0);self.assertIn('Reviewed prepared kernel tree required',out)
 def test_unreviewed_version_denied(self):self.assertIn('Unreviewed kernel/version/bootstrap',self.run_profile(8,'arm-hardening-ibe-v1','6.12.116')[1])
