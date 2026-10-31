#!/usr/bin/env python3
"""Isolated private-LAN firewall and DHCP acceptance; no live-port changes."""
import argparse,json,os,pathlib,pwd,signal,subprocess,sys,tempfile,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from freeqnap.nas.network import DEFAULT,validate,firewall,dnsmasq
from freeqnap.nas.vpn import firewall as vpn_firewall,validate as vpn_validate
from importlib.machinery import SourceFileLoader
old=SourceFileLoader('owned_packet_fixture',str(pathlib.Path(__file__).with_name('network-smoke.py'))).load_module()
DHCP=r'''import socket,struct,sys,random,json
mac=bytes.fromhex(sys.argv[1].replace(':',''));xid=random.randrange(1,2**32);s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1);s.setsockopt(socket.SOL_SOCKET,socket.SO_BINDTODEVICE,sys.argv[2].encode()+b'\0');s.bind(('0.0.0.0',68));s.settimeout(2)
head=struct.pack('!BBBBIHH4s4s4s4s16s64s128s',1,1,6,0,xid,0,0x8000,b'\0'*4,b'\0'*4,b'\0'*4,b'\0'*4,mac+b'\0'*10,b'\0'*64,b'\0'*128)
def exchange(options):
 s.sendto(head+b'\x63\x82\x53\x63'+options+b'\xff',('255.255.255.255',67))
 while True:
  b,_=s.recvfrom(4096)
  if len(b)<240 or struct.unpack_from('!I',b,4)[0]!=xid:continue
  pos=240;opts={}
  while pos<len(b):
   t=b[pos];pos+=1
   if t==255:break
   if not t:continue
   n=b[pos];pos+=1;opts[t]=b[pos:pos+n];pos+=n
  return b,opts
try:
 offer,opts=exchange(b'\x35\x01\x01');ip=offer[16:20];server=opts[54];ack,opts=exchange(b'\x35\x01\x03'+b'\x32\x04'+ip+b'\x36\x04'+server);assert opts[53]==b'\x05';print(json.dumps({'ip':socket.inet_ntoa(ack[16:20]),'router':socket.inet_ntoa(opts[3][:4]) if opts.get(3) else None,'dns':socket.inet_ntoa(opts[6][:4])}));sys.exit(0)
except (OSError,KeyError):sys.exit(1)
'''
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--confirm-isolated-test',action='store_true');p.add_argument('--inner',action='store_true');a=p.parse_args()
 if not a.confirm_isolated_test or os.geteuid()!=0:raise SystemExit('Explicit local-root isolated-test confirmation required')
 if not a.inner:os.execvp('unshare',['unshare','--mount','--net','--fork','--propagation','private',sys.executable,str(pathlib.Path(__file__).resolve()),'--inner','--confirm-isolated-test'])
 subprocess.run(['mount','--make-rprivate','/'],check=True);pathlib.Path('/run/netns').mkdir(exist_ok=True);subprocess.run(['mount','-t','tmpfs','-o','mode=700','tmpfs','/run/netns'],check=True)
 names=['fq-private-test-nas','fq-private-test-client','fq-private-test-wan'];processes=[];results={}
 def run(*args,data=None,check=True):
  r=subprocess.run(args,input=data,text=True,capture_output=True,timeout=20)
  if check and r.returncode:raise RuntimeError(str(args[:5])+': '+r.stderr[:1500])
  return r
 def ns(i,*args,**kw):return run('ip','netns','exec',names[i],*args,**kw)
 def expect(key,result):
  if not result:raise AssertionError(key)
  results[key]=True;print('PASS '+key,flush=True)
 def start(i,args,output=None):
  p=subprocess.Popen(['ip','netns','exec',names[i],*args],stdout=output or subprocess.DEVNULL,stderr=output or subprocess.DEVNULL);processes.append(p);return p
 def http(i,host,port):return ns(i,'python3','-c',old.REQUEST,host,str(port),check=False)
 def policy(c,ips=()):ns(0,'nft','-f','-',data=firewall(c,ips))
 try:
  for name in names:run('ip','netns','add',name)
  for left,right,iface,peer in [(0,1,'enp0s3','eth0'),(0,2,'enp0s1','eth0'),(0,2,'fqvpn0','eth1')]:
   run('ip','link','add','fq-a','type','veth','peer','name','fq-b');run('ip','link','set','fq-a','netns',names[left]);run('ip','link','set','fq-b','netns',names[right]);ns(left,'ip','link','set','fq-a','name',iface);ns(right,'ip','link','set','fq-b','name',peer)
  for i,iface,addr in [(0,'enp0s3','192.168.88.1/24'),(1,'eth0','192.168.88.10/24'),(0,'enp0s1','198.51.100.2/24'),(2,'eth0','198.51.100.1/24'),(0,'fqvpn0','192.0.2.2/24'),(2,'eth1','192.0.2.1/24')]:
   ns(i,'ip','link','set','lo','up');ns(i,'ip','addr','add',addr,'dev',iface);ns(i,'ip','link','set',iface,'up')
  client_mac='02:11:22:33:44:55';ns(1,'ip','link','set','eth0','address',client_mac)
  ns(1,'ip','route','add','default','via','192.168.88.1');ns(0,'sysctl','-w','net.ipv4.ip_forward=1');ns(2,'ip','addr','add','203.0.113.99/32','dev','lo');ns(0,'ip','route','add','203.0.113.99/32','via','198.51.100.1','dev','enp0s1')
  start(0,['python3','-c',old.HTTP,'0.0.0.0','443']);start(0,['python3','-c',old.HTTP,'0.0.0.0','8081']);start(2,['python3','-c',old.HTTP,'0.0.0.0','8080']);time.sleep(.5)
  private={'interface':'enp0s3','mac':'02:11:22:33:44:66','address':'192.168.88.1/24','start':'192.168.88.100','end':'192.168.88.199','dns':['1.1.1.1'],'nas_ports':[443],'clients':[{'mac':client_mac,'name':'fixture-client','reservation':'192.168.88.10'}]}
  c=validate({'private_lan':private});policy(c)
  expect('private_allowed_nas_service',http(1,'192.168.88.1',443).returncode==0);expect('private_unlisted_nas_service_denied',http(1,'192.168.88.1',8081).returncode!=0);expect('no_internet_by_default',http(1,'203.0.113.99',8080).returncode!=0)
  c['private_lan'].update(route_via='uplink',uplink='enp0s1');policy(c);response=http(1,'203.0.113.99',8080);expect('explicit_uplink_nat_works',response.returncode==0 and 'fixture 198.51.100.2' in response.stdout)
  c['private_lan']['clients'][0]['blocked']=True;policy(c,['192.168.88.10']);expect('blocked_client_nas_denied',http(1,'192.168.88.1',443).returncode!=0);expect('blocked_client_routing_denied',http(1,'203.0.113.99',8080).returncode!=0)
  c['private_lan']['clients'][0]['blocked']=False;policy(c);expect('unblocked_client_access_restored',http(1,'192.168.88.1',443).returncode==0)
  c['private_lan'].update(route_via='vpn',uplink=None);policy(c)
  vpn=vpn_validate({'client':{'type':'wireguard','endpoint':'203.0.113.10','private_key':'AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE=','public_key':'AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI=','addresses':['10.0.0.2/32'],'dns':['10.0.0.1'],'lan_networks':['192.168.97.0/24'],'gateway_clients':[]}})
  ns(0,'nft','-f','-',data=vpn_firewall(vpn,c['private_lan']));ns(0,'ip','route','replace','203.0.113.99/32','via','192.0.2.1','dev','fqvpn0')
  response=http(1,'203.0.113.99',8080);expect('private_vpn_gateway_combined_firewalls',response.returncode==0 and 'fixture 192.0.2.2' in response.stdout);expect('vpn_kill_switch_keeps_private_nas_access',http(1,'192.168.88.1',443).returncode==0)
  ns(0,'ip','link','set','fqvpn0','down');ns(0,'ip','route','replace','203.0.113.99/32','via','198.51.100.1','dev','enp0s1');expect('private_vpn_loss_no_wan_fallback',http(1,'203.0.113.99',8080).returncode!=0)
  ns(0,'nft','-f','-',data=vpn_firewall({'client':None,'server':None}));policy(DEFAULT);expect('disable_private_lan_does_not_leave_router_open',http(1,'203.0.113.99',8080).returncode!=0)
  ns(0,'ip','link','set','fqvpn0','up');ns(0,'ip','route','replace','203.0.113.99/32','via','192.0.2.1','dev','fqvpn0')
  ordinary=json.loads(json.dumps(vpn));ordinary['client'].update(lan_interface='enp0s3',lan_networks=['192.168.88.0/24'],gateway_clients=['192.168.88.10/32'])
  ns(0,'nft','-f','-',data=vpn_firewall(ordinary));expect('ordinary_vpn_gateway_survives_default_network_policy',http(1,'203.0.113.99',8080).returncode==0)
  ns(0,'nft','-f','-',data=vpn_firewall({'client':None,'server':None}))
  # Real DHCP DORA using production rendering, in isolated namespaces only.
  c['private_lan'].update(route_via='none',uplink=None);policy(c)
  with tempfile.TemporaryDirectory(prefix='freeqnap-dhcp-fixture-',dir='/run') as directory:
   root=pathlib.Path(directory);root.chmod(0o755);account=pwd.getpwnam('dnsmasq');leases=root/'state';leases.mkdir();os.chown(leases,account.pw_uid,account.pw_gid)
   config=root/'dnsmasq.conf';config.write_text(dnsmasq(c).replace('/var/lib/freeqnap-dhcp/leases',str(leases/'leases')));config.chmod(0o644);log=(root/'engine.log').open('w+')
   daemon=start(0,['setpriv','--reuid='+str(account.pw_uid),'--regid='+str(account.pw_gid),'--clear-groups','--inh-caps=+net_bind_service,+net_raw,+net_admin','--ambient-caps=+net_bind_service,+net_raw,+net_admin','dnsmasq','--keep-in-foreground','--conf-file='+str(config),'--pid-file='],log);time.sleep(.5)
   if daemon.poll() is not None:log.seek(0);raise RuntimeError(log.read())
   response=ns(1,'python3','-c',DHCP,client_mac,'eth0',check=False)
   expect('unprivileged_dhcp_reserved_address_dora',response.returncode==0 and json.loads(response.stdout)['ip']=='192.168.88.10');expect('dhcp_no_gateway_when_routing_disabled',json.loads(response.stdout)['router'] is None);expect('dhcp_dns_is_private_nas',json.loads(response.stdout)['dns']=='192.168.88.1')
   expect('dhcp_never_serves_uplink_port',ns(2,'python3','-c',DHCP,'02:11:22:33:44:77','eth0',check=False).returncode!=0)
   c['private_lan']['clients'][0]['blocked']=True;policy(c,['192.168.88.10']);expect('blocked_client_cannot_renew_dhcp',ns(1,'python3','-c',DHCP,client_mac,'eth0',check=False).returncode!=0)
   daemon.terminate();daemon.wait(timeout=10);log.close()
  print(json.dumps({'tests':results,'live_ports_changed':False,'live_lan_dhcp_enabled':False}),flush=True)
 finally:
  for p in processes:
   if p.poll() is None:p.terminate()
  for p in processes:
   try:p.wait(timeout=5)
   except subprocess.TimeoutExpired:p.kill();p.wait()
  for name in reversed(names):run('ip','netns','delete',name,check=False)
if __name__=='__main__':main()
