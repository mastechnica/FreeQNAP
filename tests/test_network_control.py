import copy
import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from freeqnap.nas.common import Context,canonical
from freeqnap.nas.network import DEFAULT,Network,validate,profiles,dnsmasq,firewall
from freeqnap.nas.network_runtime import Agent
from freeqnap.state import atomic

MAC='02:11:22:33:44:55'
def private():return {'interface':'enp0s3','mac':MAC,'address':'192.168.88.1/24','start':'192.168.88.100','end':'192.168.88.199','lease_hours':24,'dns':['1.1.1.1'],'route_via':'none','nas_ports':[443,445],'clients':[]}
def config():return {'version':1,'interfaces':[],'private_lan':private()}

class NetworkTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.commands=[]
  def run(*a,**k):self.commands.append(a);return 'active' if a[:2]==('systemctl','is-active') else '{}'
  self.ctx=Context(self.root/'state',runner=run);self.net=Network(self.ctx)
  self.port={'interface':'enp0s3','mac':MAC,'device':'/sys/devices/fixture-only','mtu':1500,'state':'DOWN','addresses':[]}
  p=patch.object(self.net,'ports',return_value=[self.port]);p.start();self.addCleanup(p.stop)
 def test_default_is_no_profiles_or_private_dhcp(self):
  c=validate(DEFAULT);self.assertFalse(c['interfaces']);self.assertIsNone(c['private_lan']);self.assertFalse(profiles(c));self.assertIsNone(dnsmasq(c))
  self.assertIn('policy drop',firewall(c));self.assertNotIn('hook input',firewall(c));self.assertNotIn('masquerade',firewall(c))
 def test_static_and_dhcp_render_never_use_user_shell_or_broad_match(self):
  c=validate({'interfaces':[{'interface':'enp0s3','mac':MAC,'mode':'static','address':'192.168.90.5/24','gateway':'192.168.90.1','dns':['9.9.9.9'],'routes':[{'destination':'10.2.0.0/16','gateway':'192.168.90.1','metric':50}]}]})
  value=next(iter(profiles(c).values()));self.assertIn('Name=enp0s3',value);self.assertIn('MACAddress='+MAC,value);self.assertIn('Destination=10.2.0.0/16',value);self.assertIn('UseDNS=no',value)
  c['interfaces'][0]['mode']='dhcp';value=next(iter(profiles(c).values()));self.assertIn('DHCP=yes',value)
 def test_overlap_gateway_range_injection_and_reservation_rejected(self):
  invalid=[{'start':'192.168.88.0'},{'start':'192.168.88.1'},{'end':'192.168.89.1'},{'interface':'eth0\nName=*'},{'dns':['1.1.1.1\nserver=bad']},{'nas_ports':['445']},{'clients':[{'mac':MAC,'reservation':'192.168.88.1'}]},{'clients':[{'mac':MAC,'hostname':'bad,ignore'}]}]
  for fields in invalid:
   c=config();c['private_lan'].update(fields)
   with self.assertRaises((ValueError,TypeError)):validate(c)
  c=config();c['interfaces']=[{'interface':'enp0s1','mac':'02:11:22:33:44:66','mode':'static','address':'192.168.88.2/24'}]
  with self.assertRaises(ValueError):validate(c)
 def test_dhcp_reserved_names_and_blocked_clients_scoped_to_private_port(self):
  c=config();c['private_lan']['clients']=[{'mac':MAC,'name':'test-client','notes':'Private note\nnot a config line','reservation':'192.168.88.10','blocked':False}];c=validate(c);value=dnsmasq(c)
  self.assertIn('interface=enp0s3',value);self.assertIn('dhcp-option=option:router\n',value);self.assertIn('dhcp-host='+MAC+',192.168.88.10,test-client',value);self.assertNotIn('Private note',value)
  c['private_lan']['clients'][0]['blocked']=True;value=dnsmasq(c);self.assertIn('dhcp-host='+MAC+',ignore',value)
  fw=firewall(c,['192.168.88.10']);self.assertLess(fw.index('ether saddr @blocked_mac drop'),fw.index('ct state established,related accept'));self.assertIn('oifname "enp0s3" ip daddr @blocked_ip drop',fw)
 def test_vpn_only_private_route_cannot_fall_back_to_uplink(self):
  c=config();c['private_lan']['route_via']='vpn';c=validate(c);fw=firewall(c)
  self.assertIn('oifname "fqvpn0"',fw);self.assertIn('iifname "enp0s3" counter drop',fw);self.assertNotIn('oifname "enp0s1"',fw)
 def test_live_overlapping_network_or_changed_port_refuses_plan(self):
  other={**self.port,'interface':'enp0s1','addresses':[{'family':'inet','local':'192.168.88.20','prefixlen':24}]}
  with patch.object(self.net,'ports',return_value=[self.port,other]):
   with self.assertRaises(ValueError):self.net.plan(config())
  c=config();c['private_lan']['mac']='02:11:22:33:44:66'
  with self.assertRaises(ValueError):self.net.plan(c)
 def agent(self):
  a=Agent(self.ctx,self.root/'profiles',self.root/'config',runner=self.ctx.run,boot_id='FIXTURE');a.network_dir.mkdir(exist_ok=True);return a
 def pending(self,a,cfg,phase='requested'):
  p={'id':'f'*32,'phase':phase,'previous':copy.deepcopy(DEFAULT),'boot_id':'FIXTURE','configuration_sha256':hashlib.sha256(canonical(cfg)).hexdigest(),'requested_at':time.time()}
  atomic(a.root/'active.json',cfg);a.set_pending(p);return p
 def test_independent_expiration_rolls_back_and_does_not_depend_on_broker(self):
  a=self.agent();cfg=validate(config());p=self.pending(a,cfg,'active');p.update(deadline_monotonic=time.monotonic()-1,profile_backups={});a.set_pending(p)
  def configured(cfg,restoring=None):a.applied=hashlib.sha256(canonical(cfg)).hexdigest()
  with patch.object(a,'configure',side_effect=configured):a.tick()
  self.assertEqual(self.net.current(),DEFAULT);self.assertIsNone(self.ctx.state.setting('network_pending'));self.assertEqual(self.ctx.state.setting('network_runtime')['state'],'rolled-back')
 def test_requested_applies_then_confirm_only_after_runtime_success(self):
  a=self.agent();cfg=validate(config());self.pending(a,cfg)
  def configured(cfg,restoring=None):a.applied=hashlib.sha256(canonical(cfg)).hexdigest()
  with patch.object(a,'configure',side_effect=configured),patch.object(a,'enforce'),patch.object(a,'ready',return_value=True):a.tick()
  pending=self.ctx.state.setting('network_pending');self.assertEqual(pending['phase'],'active');self.assertEqual(self.net.confirm({'id':pending['id']}),{'confirmed':True})
  with patch.object(a,'enforce'),patch.object(a,'ready',return_value=True):a.tick()
  self.assertFalse((a.root/'pending.json').exists())
 def test_partial_apply_or_daemon_restart_restores_previous_profiles(self):
  a=self.agent();cfg=validate(config());p=self.pending(a,cfg,'applying');p.update(profile_backups={'00-freeqnap-enp0s1.network':'PRIOR'},deadline_monotonic=time.monotonic()+120);a.set_pending(p)
  with patch.object(a,'configure') as restore:a.tick(startup=True)
  self.assertEqual(restore.call_args.kwargs['restoring'],{'00-freeqnap-enp0s1.network':'PRIOR'});self.assertEqual(self.net.current(),DEFAULT)
 def test_failed_apply_returns_to_previous_configuration(self):
  a=self.agent();cfg=validate(config());self.pending(a,cfg)
  calls=[]
  def configured(c,restoring=None):
   calls.append(c)
   if len(calls)==1:raise ValueError('injected reconfigure failure')
   a.applied=hashlib.sha256(canonical(c)).hexdigest()
  with patch.object(a,'configure',side_effect=configured):a.tick()
  self.assertEqual(self.net.current(),DEFAULT);self.assertIsNone(self.ctx.state.setting('network_pending'));self.assertEqual(len(calls),2)

 def test_friendly_name_is_separate_from_injection_safe_dns_hostname(self):
  c=config();c['private_lan']['clients']=[{'mac':MAC,'name':'Front Camera 1','notes':'Private note','reservation':'192.168.88.10'}];c=validate(c)
  self.assertEqual(c['private_lan']['clients'][0]['name'],'Front Camera 1');self.assertIn('192.168.88.10,front-camera-1',dnsmasq(c))

 def test_cross_boot_requested_change_restores_old_policy_before_firewall(self):
  a=self.agent();p=self.pending(a,copy.deepcopy(DEFAULT),'requested');p.update(previous=validate(config()),boot_id='OLD-BOOT');a.set_pending(p)
  with patch.object(a,'enforce') as enforced:a.prepare()
  self.assertEqual(enforced.call_args.args[0],validate(config()));self.assertEqual(self.net.current(),validate(config()));self.assertIsNone(self.ctx.state.setting('network_pending'))
 def test_confirmed_change_survives_agent_restart_before_pending_cleanup(self):
  a=self.agent();self.pending(a,copy.deepcopy(DEFAULT),'active');atomic(a.root/'confirmed.json',{'id':'f'*32})
  with patch.object(a,'enforce'):a.prepare()
  self.assertEqual(self.net.current(),DEFAULT);self.assertIsNone(self.ctx.state.setting('network_pending'));self.assertEqual(self.ctx.state.setting('network_last_change')['result'],'confirmed')
