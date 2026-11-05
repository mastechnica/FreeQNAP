import json
from pathlib import Path
import tempfile
import time
import unittest
from freeqnap.system_summary import Summary, project_inventory, project_health, project_history, project_frontpanel

class SystemSummaryTests(unittest.TestCase):
 def test_allowlist_omits_private_paths_credentials_and_accounts(self):
  secret='private-sentinel'
  raw={'sampled_at':time.time(),'stale':False,'errors':[secret],'disks':[{'name':'sda','path':'/dev/sda','type':'disk','size':100,'model':'SATA','serial':secret,'children':[{'mountpoints':[secret]}]}],'smart':[{'device':'/dev/sda','passed':False,'temperature':55,'raw':{'secret':secret}}],'arrays':[{'device':'/dev/md0','uuid':secret,'members':['sda1','sdb1'],'degraded':0,'sync_action':'check','state':'active'}],'volumes':[{'target':secret,'uuid':secret,'total_bytes':100,'available_bytes':50}],'temperatures':[{'celsius':60,'name':secret}]}
  value=project_inventory(raw);self.assertNotIn(secret,json.dumps(value));self.assertEqual(value['arrays'][0]['members'],2);self.assertFalse(value['smart'][0]['passed'])
  health=project_health({'items':[{'severity':'critical','scope':'raid','title':secret,'details':{'path':secret},'resolved_at':None}],'monitor':{'secret':secret},'monitor_stale':False,'active_total':1,'active_counts':{'critical':1}});self.assertNotIn(secret,json.dumps(health));self.assertEqual(health['items'][0]['title'],'RAID protection')
  history=project_history({'points':[{'time':1,'cpu':4,'interfaces':secret,'secret':secret}],'stale':False});self.assertNotIn(secret,json.dumps(history));self.assertEqual(history['points'][0]['cpu'],4)
  front=project_frontpanel({'ports':[{'bay':1,'green':True,'disk':secret}],'network':{'lan1':{'up':True,'address':secret},secret:{'up':True}}});self.assertNotIn(secret,json.dumps(front))
 def test_capacity_deduplicates_bind_mounts_and_labels_present_bays(self):
  value=project_inventory({'volumes':[{'uuid':'root','system':False,'total_bytes':100,'available_bytes':50},{'uuid':'root','system':True,'total_bytes':100,'available_bytes':50},{'uuid':'data','total_bytes':1000,'available_bytes':900}]})
  self.assertEqual([v['label'] for v in value['volumes']],['System','Data volume 1'])
  front=project_frontpanel({'ports':[{'bay':1,'present':True,'green':True,'disk':'private-identity'}]});self.assertEqual(front['ports'][0]['disk'],'Drive installed');self.assertTrue(front['ports'][0]['present'])
 def test_bounded_cache_unavailable_is_not_healthy(self):
  class Device:
   def __init__(self):self.calls=[]
   def request(self,op,payload):self.calls.append(op);raise ValueError('private-sentinel')
  device=Device();summary=Summary(device,None);value=summary.read();self.assertTrue(value['stale']);self.assertTrue(value['health']['monitor_stale']);self.assertNotIn('private-sentinel',json.dumps(value));self.assertEqual(value,summary.read());self.assertEqual(len(device.calls),3)

if __name__=='__main__':unittest.main()
