#!/usr/bin/env python3
"""Native isolated packet acceptance. Never changes live LAN routes/firewalls.

Requires local root, iproute2, nftables, Python and veth/network namespaces.
Creates a private mount+network namespace before any virtual network operation.
"""
import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from freeqnap.nas.dlna import render,endpoint
from freeqnap.nas.vpn import firewall,validate

HTTP='''import http.server,socket,sys
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):
  data=('fixture '+self.client_address[0]).encode();self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
class Server(http.server.ThreadingHTTPServer):
 address_family=socket.AF_INET6 if ':' in sys.argv[1] else socket.AF_INET
 def server_bind(self):
  if self.address_family==socket.AF_INET6:self.socket.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1)
  super().server_bind()
Server((sys.argv[1],int(sys.argv[2])),Handler).serve_forever()
'''
REQUEST='''import socket,sys
try:
 s=socket.create_connection((sys.argv[1],int(sys.argv[2])),1.2,source_address=(sys.argv[3],0) if len(sys.argv)>3 else None);s.sendall(b'GET / HTTP/1.0\\r\\nHost: fixture\\r\\n\\r\\n');data=b''
 while chunk:=s.recv(4096):data+=chunk
 print(data.decode());sys.exit(0 if b'200 OK' in data else 2)
except OSError:sys.exit(1)
'''

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--confirm-isolated-test',action='store_true');p.add_argument('--inner',action='store_true');a=p.parse_args()
 if os.geteuid()!=0 or not a.confirm_isolated_test:raise SystemExit('Explicit local-root isolated-test confirmation required')
 if not a.inner:
  os.execvp('unshare',['unshare','--mount','--net','--fork','--propagation','private',sys.executable,str(Path(__file__).resolve()),'--inner','--confirm-isolated-test'])
 subprocess.run(['mount','--make-rprivate','/'],check=True)
 Path('/run/netns').mkdir(exist_ok=True);subprocess.run(['mount','-t','tmpfs','-o','mode=700','tmpfs','/run/netns'],check=True)
 processes=[];results={};names=['fq-test-nas','fq-test-lan','fq-test-wan']
 def run(*args,data=None,check=True):
  r=subprocess.run(args,input=data,text=True,capture_output=True,timeout=30)
  if check and r.returncode:raise RuntimeError(str(args[:5])+': '+r.stderr[:1600])
  return r
 def ns(which,*args,**kw):return run('ip','netns','exec',names[which],*args,**kw)
 def process(which,args,uid=None):
  def demote():os.setgroups([]);os.setgid(uid);os.setuid(uid)
  p=subprocess.Popen(['ip','netns','exec',names[which],*args],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  processes.append(p);return p
 def http(which,host,port,source=None):
  return ns(which,'python3','-c',REQUEST,host,str(port),*([source] if source else []),check=False)
 def expect(key,value):
  if not value:raise AssertionError(key)
  results[key]=True;print('PASS '+key,flush=True)
 try:
  for name in names:run('ip','netns','add',name)
  for pair,aif,bif,left,right in [('lan','enp0s1','eth0',0,1),('wan','fqvpn0','eth0',0,2),('fallback','enp0s3','eth1',0,2)]:
   run('ip','link','add','fq-a', 'type','veth','peer','name','fq-b');run('ip','link','set','fq-a','netns',names[left]);run('ip','link','set','fq-b','netns',names[right]);ns(left,'ip','link','set','fq-a','name',aif);ns(right,'ip','link','set','fq-b','name',bif)
  for which,iface,ipv4,ipv6 in [(0,'enp0s1','192.168.97.1/24','2001:db8:97::1/64'),(1,'eth0','192.168.97.2/24','2001:db8:97::2/64'),(0,'fqvpn0','192.0.2.2/24','2001:db8:98::2/64'),(2,'eth0','192.0.2.1/24','2001:db8:98::1/64'),(0,'enp0s3','198.51.100.2/24','2001:db8:99::2/64'),(2,'eth1','198.51.100.1/24','2001:db8:99::1/64')]:
   ns(which,'ip','link','set','lo','up');ns(which,'ip','addr','add',ipv4,'dev',iface);ns(which,'ip','-6','addr','add',ipv6,'dev',iface,'nodad');ns(which,'ip','link','set',iface,'up')
  ns(1,'ip','addr','add','192.168.97.3/24','dev','eth0');ns(1,'ip','route','add','default','via','192.168.97.1');ns(0,'sysctl','-w','net.ipv4.ip_forward=1')
  import tempfile
  # Start media HTTP under a dedicated unprivileged UID, including fallback port.
  for ip,port in [('0.0.0.0',49152),('::',49152),('0.0.0.0',49153)]:process(0,['setpriv','--reuid=65534','--regid=65534','--clear-groups','python3','-c',HTTP,ip,str(port)])
  process(1,['python3','-c',HTTP,'::','49152']);process(2,['python3','-c',HTTP,'0.0.0.0','8080']);process(0,['python3','-c',HTTP,'0.0.0.0','8081']);time.sleep(.7)
  def policy(script):ns(0,'nft','-f','-',data=script)
  policy(render([],'enp0s1',65534))
  expect('unapproved_catalog_and_direct_stream_denied',http(1,'192.168.97.1',49152).returncode!=0)
  expect('fallback_media_port_denied',http(1,'192.168.97.1',49153).returncode!=0)
  expect('unapproved_ipv6_media_denied',http(1,'2001:db8:97::1',49152).returncode!=0)
  seen=json.loads(ns(0,'nft','-j','list','set','inet','freeqnap_dlna','seen4').stdout)
  expect('pending_client_recorded_in_kernel',any('set' in item and item['set'].get('elem') for item in seen['nftables']))
  from freeqnap.nas.common import Context
  from freeqnap.nas.dlna import Access
  with tempfile.TemporaryDirectory(prefix='freeqnap-dlna-policy-') as private:
   context=Context(Path(private)/'state',runner=lambda *args,**kw:ns(0,*args).stdout)
   access=Access(context,media_uid=65534,policy=Path(private)/'dlna.nft')
   pending=access.list()['clients']
   expect('dashboard_pending_identity_parsed_from_kernel',any(row['ip']=='192.168.97.2' and not row['approved'] for row in pending))
  mac=json.loads(ns(1,'ip','-j','link','show','eth0').stdout)[0]['address'];client={**endpoint('192.168.97.2',mac,'enp0s1'),'approved':True}
  policy(render([client],'enp0s1',65534));expect('approved_media_catalog_works',http(1,'192.168.97.1',49152).returncode==0)
  expect('different_client_address_stays_denied',http(1,'192.168.97.1',49152,'192.168.97.3').returncode!=0)
  six={**endpoint('2001:db8:97::2',mac,'enp0s1'),'approved':True};policy(render([client,six],'enp0s1',65534));expect('explicit_ipv6_approval_works',http(1,'2001:db8:97::1',49152).returncode==0)
  policy(render([],'enp0s1',65534));expect('revoked_player_denied',http(1,'192.168.97.1',49152).returncode!=0)
  ns(0,'nft','delete','table','inet','freeqnap_dlna')
  config=validate({'client':{'type':'wireguard','endpoint':'203.0.113.10','private_key':'AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE=','public_key':'AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI=','addresses':['10.0.0.2/32'],'dns':['10.0.0.1'],'lan_networks':['192.168.97.0/24'],'gateway_clients':['192.168.97.2/32']}})
  policy(firewall(config));expect('unsolicited_vpn_wan_input_denied',http(2,'192.0.2.2',8081).returncode!=0)
  expect('nas_initiated_vpn_request_reply_works',http(0,'192.0.2.1',8080).returncode==0)
  expect('local_management_survives_kill_switch',http(1,'192.168.97.1',8081).returncode==0)
  gateway=http(1,'192.0.2.1',8080);expect('approved_gateway_forwarding_and_nat',gateway.returncode==0 and 'fixture 192.0.2.2' in gateway.stdout)
  expect('unapproved_gateway_client_denied',http(1,'192.0.2.1',8080,'192.168.97.3').returncode!=0)
  # A second physical-side veth is a functioning fallback WAN, still isolated.
  ns(2,'ip','addr','add','203.0.113.99/32','dev','lo')
  ns(0,'ip','route','add','203.0.113.99/32','via','192.0.2.1','dev','fqvpn0')
  expect('gateway_reaches_fixture_public_server_over_vpn',http(1,'203.0.113.99',8080).returncode==0)
  ns(0,'ip','link','set','fqvpn0','down')
  ns(0,'ip','route','replace','203.0.113.99/32','via','198.51.100.1','dev','enp0s3')
  expect('vpn_loss_has_no_ipv4_wan_fallback',http(0,'203.0.113.99',8080).returncode!=0)
  expect('gateway_has_no_non_vpn_fallback',http(1,'203.0.113.99',8080).returncode!=0)
  expect('non_vpn_ipv6_egress_denied',http(0,'2001:db8:97::2',49152).returncode!=0)
  ns(0,'nft','delete','table','inet','freeqnap_vpn')
  expect('fallback_wan_fixture_is_reachable_without_policy',http(0,'203.0.113.99',8080).returncode==0)
  expect('ipv6_fixture_is_reachable_without_policy',http(0,'2001:db8:97::2',49152).returncode==0)
  # Real encrypted WireGuard and mutual-TLS OpenVPN peers on the isolated LAN.
  import tempfile
  with tempfile.TemporaryDirectory(prefix='freeqnap-vpn-fixture-') as directory:
   root=Path(directory)
   wgkeys=[run('wg','genkey').stdout.strip() for _ in (0,1)]
   wgpub=[run('wg','pubkey',data=k+'\n').stdout.strip() for k in wgkeys]
   for which in (0,1):
    ns(which,'wireguard-go','fqwg'+str(which))
    text='[Interface]\nPrivateKey = '+wgkeys[which]+'\nListenPort = '+str(51830+which)+'\n[Peer]\nPublicKey = '+wgpub[1-which]+'\nAllowedIPs = 10.77.0.'+str(2-which)+'/32\n'
    if which==1:text+='Endpoint = 192.168.97.1:51830\nPersistentKeepalive = 5\n'
    path=root/('peer'+str(which)+'.conf');path.write_text(text);path.chmod(0o600)
    ns(which,'wg','setconf','fqwg'+str(which),str(path));ns(which,'ip','addr','add','10.77.0.'+str(which+1)+'/24','dev','fqwg'+str(which));ns(which,'ip','link','set','fqwg'+str(which),'up')
   process(0,['python3','-c',HTTP,'10.77.0.1','8082'])
   okay=False
   for _ in range(20):
    if http(1,'10.77.0.1',8082).returncode==0:okay=True;break
    time.sleep(.2)
   expect('wireguard_userspace_encrypted_http',okay)
   expect('wireguard_handshake_reported',int(ns(0,'wg','show','fqwg0','latest-handshakes').stdout.split()[1])>0)
   for which in (0,1):ns(which,'ip','link','delete','fqwg'+str(which))
   from freeqnap.nas.vpn_pki import ensure,issue,server_config,revoke
   from freeqnap.nas.vpn import openvpn_client
   from freeqnap.nas.vpn_runtime import write
   pki=root/'pki';ensure(pki);issue(pki,'fixture-client')
   server={'subnet':'10.78.0.0/24','port':1195,'lan_networks':[],'gateway':False}
   serverpath=root/'server.ovpn';write(serverpath,server_config(server,pki))
   client={'protocol':'udp','endpoint':'192.168.97.1','port':1195,'server_name':'server',**{k:(pki/f).read_text() for k,f in [('ca','ca.crt'),('cert','fixture-client.crt'),('key','fixture-client.key'),('tls_crypt','tls-crypt.key')]}}
   clientpath=root/'client.ovpn';write(clientpath,openvpn_client(client,root))
   ovpnserver=process(0,['openvpn','--config',str(serverpath)]);ovpnclient=process(1,['openvpn','--config',str(clientpath)])
   ready=False
   for _ in range(50):
    if ovpnserver.poll() is not None or ovpnclient.poll() is not None:break
    info=ns(1,'ip','-j','address','show','dev','fqvpn0',check=False)
    if info.returncode==0 and any(a.get('family')=='inet' for row in json.loads(info.stdout) for a in row.get('addr_info',[])):ready=True;break
    time.sleep(.4)
   expect('openvpn_mutual_tls_tunnel_address',ready)
   process(0,['python3','-c',HTTP,'10.78.0.1','8083']);time.sleep(.3)
   expect('openvpn_mutual_tls_encrypted_http',http(1,'10.78.0.1',8083).returncode==0)
   revoke(pki,'fixture-client')
   ovpnclient.terminate();ovpnserver.terminate();ovpnclient.wait(timeout=10);ovpnserver.wait(timeout=10)
   # Remove persist-tun interfaces before proving revoked credentials cannot reconnect.
   for which,iface in ((0,'fqsv0'),(1,'fqvpn0')):ns(which,'ip','link','delete',iface,check=False)
   ovpnserver=process(0,['openvpn','--config',str(serverpath)]);ovpnclient=process(1,['openvpn','--config',str(clientpath)])
   time.sleep(4)
   info=ns(1,'ip','-j','address','show','dev','fqvpn0',check=False)
   ready=info.returncode==0 and any(a.get('family')=='inet' for row in json.loads(info.stdout) for a in row.get('addr_info',[]))
   expect('revoked_openvpn_certificate_cannot_reconnect',not ready)
  print(json.dumps({'isolated_packet_results':results,'physical_vpn_peer_and_client_acceptance':False},indent=2),flush=True)
 finally:
  for p in processes:
   if p.poll() is None:p.terminate()
  for p in processes:
   try:p.wait(timeout=4)
   except subprocess.TimeoutExpired:p.kill();p.wait()
  for which in (0,1):ns(which,'ip','link','delete','fqwg'+str(which),check=False)
  for name in reversed(names):run('ip','netns','delete',name,check=False)
if __name__=='__main__':main()
