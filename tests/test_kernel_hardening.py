import importlib.util,unittest
from pathlib import Path
S=importlib.util.spec_from_file_location('check_hardening',Path(__file__).resolve().parents[1]/'tools/check-hardening.py');H=importlib.util.module_from_spec(S);S.loader.exec_module(H)
class KernelHardeningTests(unittest.TestCase):
 def report(self,**changes):
  args=dict(kernel='test',expected='test',config='\n'.join('CONFIG_'+x+'=y' for x in H.REQUIRED),cmdline='',log='arm/mm: Checked W+X mappings: passed, no W+X pages found.',bpf=2,vulnerabilities={'spectre_v2':'Mitigation: History overwrite'});args.update(changes);return H.assess(**args)
 def test_full_software_evidence(self):self.assertTrue(self.report()['memory_and_bpf_hardening_passed'])
 def test_sysfs_does_not_override_firmware_warning(self):
  x=self.report(log='arm/mm: Checked W+X mappings: passed, no W+X pages found.\nCPU3: Spectre v2: firmware did not set auxiliary control register IBE bit, system vulnerable')
  self.assertTrue(x['memory_and_bpf_hardening_passed']);self.assertFalse(x['firmware_mitigation_complete']);self.assertEqual(x['firmware_ibe_warning_cpus'],[3])
 def test_absent_boot_check_fails(self):self.assertFalse(self.report(log='')['memory_and_bpf_hardening_passed'])
 def test_failed_boot_check_wins(self):self.assertFalse(self.report(log='Checked W+X mappings: passed, no W+X pages found.\nChecked W+X mappings: FAILED')['memory_and_bpf_hardening_passed'])
 def test_wrong_kernel_fails(self):self.assertFalse(self.report(kernel='other')['memory_and_bpf_hardening_passed'])
 def test_missing_option_fails(self):self.assertFalse(self.report(config='')['memory_and_bpf_hardening_passed'])
 def test_unprivileged_bpf_fails(self):self.assertFalse(self.report(bpf=0)['memory_and_bpf_hardening_passed'])
 def test_disabled_boot_protection_fails(self):self.assertFalse(self.report(cmdline='quiet rodata=off')['memory_and_bpf_hardening_passed'])

 def test_native_success_without_punctuation(self):self.assertTrue(self.report(log='[    2.06] Checked W+X mappings: passed, no W+X pages found')['memory_and_bpf_hardening_passed'])
 def test_partial_success_message_denied(self):self.assertFalse(self.report(log='Checked W+X mappings: passed, no W+X pages found but not checked')['memory_and_bpf_hardening_passed'])

 def test_all_core_positive_readback_path(self):
  log='\n'.join('CPU'+str(i)+': Spectre v2: using ICIALLU workaround' for i in range(4))
  x=self.report(log=log,online_cpus=[0,1,2,3]);self.assertTrue(x['cpu_ibe_workaround_confirmed']);self.assertIsNone(x['firmware_mitigation_complete'])
 def test_partial_core_workaround_denied(self):
  log='\n'.join('CPU'+str(i)+': Spectre v2: using ICIALLU workaround' for i in range(3))
  self.assertFalse(self.report(log=log,online_cpus=[0,1,2,3])['cpu_ibe_workaround_confirmed'])
 def test_online_core_missing_denied(self):
  log='\n'.join('CPU'+str(i)+': Spectre v2: using ICIALLU workaround' for i in range(4))
  self.assertFalse(self.report(log=log,online_cpus=[0,1,2])['cpu_ibe_workaround_confirmed'])
 def test_contradictory_firmware_warning_denied(self):
  log='\n'.join('CPU'+str(i)+': Spectre v2: using ICIALLU workaround' for i in range(4))+'\nCPU2: Spectre v2: firmware did not set auxiliary control register IBE bit'
  self.assertFalse(self.report(log=log,online_cpus=[0,1,2,3])['cpu_ibe_workaround_confirmed'])
 def test_sysfs_mitigation_alone_not_cpu_proof(self):self.assertFalse(self.report(online_cpus=[0,1,2,3])['cpu_ibe_workaround_confirmed'])
