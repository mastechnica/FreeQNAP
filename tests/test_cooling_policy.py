import copy,unittest
from freeqnap.cooling_policy import decide
class CoolingPolicyTests(unittest.TestCase):
 def sample(self):return {'cpu_c':49,'cpu_age':0,'disk_age':10,'disks_c':[37,39,40,41],'fans':[{'rpm':8500,'state':48} for _ in range(3)]}
 def test_disabled_default_never_reduces_and_no_stop_level(self):
  self.assertEqual(decide(self.sample())['level'],7)
  for cpu in range(0,100):
   s=self.sample();s['cpu_c']=cpu;self.assertIn(decide(s,enabled=True)['level'],(6,7))
 def test_hysteresis_and_heat_override(self):
  s=self.sample();self.assertEqual(decide(s,enabled=True)['level'],6);s['cpu_c']=56
  self.assertEqual(decide(s,previous=6,enabled=True)['level'],6);self.assertEqual(decide(s,previous=7,enabled=True)['level'],7)
  s['cpu_c']=60;self.assertEqual(decide(s,previous=6,enabled=True)['level'],7)
  s=self.sample();s['disks_c'][2]=48;self.assertEqual(decide(s,previous=6,enabled=True)['level'],7)
 def test_missing_stale_malformed_and_tach_fault_force_full(self):
  bad=[]
  for field in ('cpu_c','cpu_age','disk_age','disks_c','fans'):
   s=self.sample();s.pop(field);bad.append(s)
  for field,value in [('cpu_c',float('nan')),('cpu_c',True),('cpu_age',4),('cpu_age',-1),('disk_age',91),('disks_c',[30,31,32]),('disks_c',[30,31,32,'35'])]:
   s=self.sample();s[field]=value;bad.append(s)
  for field,value in [('rpm',0),('rpm',5000),('rpm',float('inf')),('state',49)]:
   s=self.sample();s['fans'][1][field]=value;bad.append(s)
  for s in bad:
   result=decide(s,previous=6,enabled=True);self.assertEqual(result['level'],7);self.assertTrue(result['fault'])
