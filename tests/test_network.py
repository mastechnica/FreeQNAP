import base64
import copy
import hashlib
import json
import tempfile
import time
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from freeqnap.nas.common import Context
from freeqnap.nas.vpn import validate,public,firewall,VPN,openvpn_client
from freeqnap.nas.dlna import render,endpoint,Access
from freeqnap.nas.downloads import Downloads,url,config_text

PRIVATE=base64.b64encode(bytes([17])*32).decode()
PUBLIC=base64.b64encode(bytes([29])*32).decode()
def client():return {'client':{'type':'wireguard','endpoint':'203.0.113.20','port':51820,'private_key':PRIVATE,'public_key':PUBLIC,'addresses':['10.10.0.2/32'],'dns':['10.10.0.1'],'lan_networks':['192.168.97.0/24'],'gateway_clients':['192.168.97.2/32']}}
class Network(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.ctx=Context(self.root,runner=lambda *a,**k:'')
 def test_import_cannot_execute_hooks_or_add_arbitrary_routes(self):
  for field in ('PostUp','up','script_security','plugin','config_path','route','shell'):
   raw=client();raw['client'][field]='forbidden'
   with self.assertRaises(ValueError):validate(raw)
  raw=client();raw['client']['endpoint']='provider.example'
  with self.assertRaises(ValueError):validate(raw)
 def test_explicit_gateway_scope_and_family_fail_closed(self):
  for cidr in ('0.0.0.0/0','192.168.98.0/24','::/0'):
   raw=client();raw['client']['gateway_clients']=[cidr]
   with self.assertRaises(ValueError):validate(raw)
  config=validate(client());rules=firewall(config)
  self.assertNotIn('flush ruleset',rules);self.assertIn('policy drop',rules);self.assertIn('ct direction reply',rules)
  self.assertIn('udp dport { 53, 853 } counter drop',rules);self.assertIn('oifname "fqvpn0" accept',rules)
 def test_private_keys_not_in_review_or_status(self):
  manager=VPN(self.ctx);plan=manager.plan(client())
  self.assertNotIn(PRIVATE,json.dumps(plan));self.assertNotIn(PRIVATE,json.dumps(public(validate(client()))))
  candidate=manager.root/'candidates'/(plan['body']['candidate']+'.json')
  self.assertEqual(candidate.stat().st_mode&0o777,0o600);self.assertIn(PRIVATE,candidate.read_text())
  self.assertNotIn(PRIVATE,self.ctx.state.database.read_bytes().decode('latin1'))
 def test_confirmation_cannot_use_previous_runtime_success(self):
  manager=VPN(self.ctx);manager.root.mkdir();config=validate(client())
  from freeqnap.state import atomic
  atomic(manager.root/'active.json',config);pending={'id':'fixture','deadline':time.time()+60}
  self.ctx.state.set('vpn_pending',pending);self.ctx.state.set('vpn_runtime',{'state':'running','config_sha256':'old'})
  with self.assertRaisesRegex(ValueError,'configuration'):manager.confirm({'id':'fixture'})
 def test_dlna_empty_sets_and_validation(self):
  rules=render([],'enp0s1',65534);self.assertNotIn('elements = {  }',rules);self.assertIn('meta l4proto tcp counter drop',rules)
  with self.assertRaises(ValueError):endpoint('192.0.2.2','ff:ff:ff:ff:ff:ff','enp0s1')
  manager=Access(self.ctx,media_uid=65534,policy=self.root/'dlna.nft')
  with self.assertRaises(ValueError):manager.approve({'id':'a'*32,'approved':True})
 def test_download_url_schemes_paths_and_secrets(self):
  for v in ('file:///etc/shadow','ftp://host/file','https://name:password@example.test/file','https://example.test/file\nheader:x','magnet:?xt=bad'):
   with self.assertRaises(ValueError):url(v)
  self.assertEqual(url('https://example.test/media.mp4')[1],'url')
  self.assertEqual(url('magnet:?xt=urn:btih:'+'a'*40)[1],'torrent')
  options={'concurrent':3,'download_kib':0,'upload_kib':256,'seed_ratio':1,'seed_minutes':0}
  text=config_text(self.root,self.root/'downloads','fixture-token',options)
  self.assertIn('rpc-listen-all=false',text);self.assertIn('check-certificate=true',text);self.assertIn('always-resume=true',text)
 def test_ambiguous_submission_reconciles_gid_without_duplicate(self):
  manager=Downloads(self.ctx);self.ctx.state.set('downloads_settings',{'pool':'fixture'})
  with patch.object(manager,'target',return_value=self.root):job=manager.add({'url':'https://example.test/movie.mp4'})['job']
  calls=[];accepted={}
  def rpc(method,params=()):
   calls.append(method)
   if method=='tellStatus':return accepted.get(params[0])
   if method=='addUri':
    gid=params[1]['gid'];accepted[gid]={'gid':gid,'status':'active','totalLength':'10','completedLength':'2'}
    raise ValueError('reply lost after durable engine admission')
  with patch.object(manager,'settings',return_value={'pool':'fixture'}),patch.object(manager,'target',return_value=self.root),patch.object(manager,'rpc',side_effect=rpc):
   manager.reconcile();manager.reconcile()
  self.assertEqual(calls.count('addUri'),1);self.assertEqual(manager.jobs()[job['id']]['state'],'active')
 def test_one_failed_download_does_not_block_next_and_pause_survives_restart(self):
  manager=Downloads(self.ctx);self.ctx.state.set('downloads_settings',{'pool':'fixture'})
  with patch.object(manager,'target',return_value=self.root):
   bad=manager.add({'url':'https://example.test/bad.mp4'})['job'];good=manager.add({'url':'https://example.test/good.mp4'})['job']
  admitted=[]
  def rpc(method,params=()):
   if method=='tellStatus':
    if params[0]==bad['gid']:raise ValueError('one malformed engine item')
    return None
   if method=='addUri':admitted.append(params[1]['gid']);return params[1]['gid']
  with patch.object(manager,'target',return_value=self.root),patch.object(manager,'rpc',side_effect=rpc):manager.reconcile()
  self.assertEqual(admitted,[good['gid']]);manager.control({'id':good['id'],'action':'pause'})
  restarted=Downloads(Context(self.root));self.assertEqual(restarted.jobs()[good['id']]['desired'],'paused');self.assertEqual(len(restarted.jobs()),2)
 def test_vpn_timeout_rollback_does_not_wait_for_storage_lock(self):
  from freeqnap.nas import vpn_runtime
  from freeqnap.state import atomic
  root=self.root/'vpn';root.mkdir();previous={'version':1,'client':None,'server':None}
  atomic(root/'previous.json',previous);atomic(root/'active.json',validate(client()));atomic(root/'pending.json',{'id':'expired','deadline':time.time()-1})
  with self.ctx.lock(),patch.object(vpn_runtime,'ROOT',root):self.assertTrue(vpn_runtime.check_pending(self.ctx))
  self.assertEqual(json.loads((root/'active.json').read_text()),previous);self.assertIsNone(self.ctx.state.setting('vpn_pending'))
 def test_discovery_cannot_race_and_restore_a_revoked_approval(self):
  record={**endpoint('192.0.2.2','02:00:00:00:00:02','enp0s1'),'approved':True,'last_seen':0,'first_seen':0,'label':'fixture'}
  self.ctx.state.set('dlna_clients',{record['id']:record})
  entered=threading.Event();release=threading.Event();calls=[]
  def runner(*args,**kwargs):
   if args[:3]==('nft','-j','list'):
    if threading.current_thread().name=='observer' and not entered.is_set():entered.set();release.wait(2)
    return json.dumps({'nftables':[{'set':{'elem':[{'concat':['192.0.2.2','02:00:00:00:00:02']}]}}]})
   return ''
  self.ctx.run=runner;manager=Access(self.ctx,media_uid=65534,policy=self.root/'dlna.nft')
  def invoke(callback):
   try:callback()
   except Exception as e:calls.append(e)
  observer=threading.Thread(name='observer',target=lambda:invoke(manager.observe));observer.start();self.assertTrue(entered.wait(1))
  revoker=threading.Thread(target=lambda:invoke(lambda:manager.approve({'id':record['id'],'approved':False})));revoker.start();release.set();observer.join(3);revoker.join(3)
  self.assertFalse(observer.is_alive());self.assertFalse(revoker.is_alive());self.assertFalse(calls)
  self.assertFalse(manager.data()[record['id']]['approved'])
 def test_many_bad_downloads_rotate_fairly_to_later_work(self):
  manager=Downloads(self.ctx);self.ctx.state.set('downloads_settings',{'pool':'fixture'})
  with patch.object(manager,'target',return_value=self.root):
   jobs=[manager.add({'url':'https://example.test/file'+str(n)+'.bin'})['job'] for n in range(33)]
  good=jobs[-1]['gid'];admitted=[]
  def rpc(method,params=()):
   if method=='tellStatus':
    if params[0]!=good:raise ValueError('permanent isolated failure')
    return None
   if method=='addUri':admitted.append(params[1]['gid'])
  with patch.object(manager,'target',return_value=self.root),patch.object(manager,'rpc',side_effect=rpc):
   for _ in range(3):manager.reconcile()
  self.assertEqual(admitted,[good]);self.assertEqual(len(manager.jobs()),33)
if __name__=='__main__':unittest.main()
