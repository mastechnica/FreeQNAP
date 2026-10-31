"""Local physical-port profiles and opt-in private-LAN configuration.

Only the independent network agent applies profiles; pending changes must be
confirmed after successful application, otherwise it restores the old profiles.
"""
import contextlib
import fcntl
import hashlib
import ipaddress
import json
import os
import re
import secrets
import time
from pathlib import Path
from .common import canonical
from ..state import atomic

TABLE='freeqnap_lan'
PREFIX='00-freeqnap-'
DEFAULT={'version':1,'interfaces':[],'private_lan':None}

def interface(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,14}',value) or value=='lo':raise ValueError('Select a physical Ethernet port')
    return value

def mac(value):
    if not isinstance(value,str) or not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}',value):raise ValueError('Invalid client or port MAC address')
    value=value.lower()
    if int(value[:2],16)&1 or value=='00:00:00:00:00:00':raise ValueError('Use a unicast MAC address')
    return value

def integer(value,low,high,label):
    if isinstance(value,bool) or not isinstance(value,int) or not low<=value<=high:raise ValueError('Invalid '+label)
    return value

def address(value):
    ip=ipaddress.ip_address(value)
    if ip.is_multicast or ip.is_unspecified or ip.is_loopback:raise ValueError('Use a unicast address')
    return str(ip)

def client(value,network,gateway):
    if not isinstance(value,dict) or set(value)-{'mac','name','hostname','notes','reservation','blocked'}:raise ValueError('Invalid client fields')
    label=value.get('name','');notes=value.get('notes','');blocked=value.get('blocked',False);reserved=value.get('reservation') or None
    if not isinstance(label,str) or len(label)>128 or any(ord(c)<32 for c in label):raise ValueError('Use a client display name of at most 128 characters')
    hostname=value.get('hostname',re.sub('[^a-z0-9-]+','-',label.lower()).strip('-')[:63].rstrip('-'))
    if not isinstance(hostname,str) or (hostname and not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?',hostname)):raise ValueError('Use a simple DNS hostname, at most 63 characters')
    if not isinstance(notes,str) or len(notes)>2000 or not isinstance(blocked,bool):raise ValueError('Invalid client notes or block setting')
    if reserved:
        ip=ipaddress.ip_address(reserved)
        if ip not in network or ip in (network.network_address,network.broadcast_address,ipaddress.ip_address(gateway)):raise ValueError('Reservation must be an available host on the private subnet')
        reserved=str(ip)
    return {'mac':mac(value.get('mac')),'name':label,'hostname':hostname,'notes':notes,'reservation':reserved,'blocked':blocked}

def validate(value):
    if not isinstance(value,dict) or set(value)-{'version','interfaces','private_lan'}:raise ValueError('Invalid network configuration fields')
    profiles=value.get('interfaces',[])
    if not isinstance(profiles,list) or len(profiles)>8:raise ValueError('At most eight physical-port profiles')
    result={'version':1,'interfaces':[],'private_lan':None};seen=set();subnets=[]
    for p in profiles:
        if not isinstance(p,dict) or set(p)-{'interface','mac','mode','address','gateway','dns','mtu','metric','ipv6','routes'}:raise ValueError('Invalid interface fields')
        iface=interface(p.get('interface'));hw=mac(p.get('mac'));mode=p.get('mode','dhcp');dns=p.get('dns',[]);ipv6=p.get('ipv6','auto')
        if iface in seen or mode not in ('dhcp','static','disabled') or ipv6 not in ('auto','disabled'):raise ValueError('Duplicate port or invalid addressing mode')
        if not isinstance(dns,list) or len(dns)>4:raise ValueError('Choose up to four DNS servers')
        row={'interface':iface,'mac':hw,'mode':mode,'dns':[address(v) for v in dns],'mtu':integer(p.get('mtu',1500),576,9000,'MTU'),'metric':integer(p.get('metric',100),1,32000,'route metric'),'ipv6':ipv6,'address':None,'gateway':None,'routes':[]}
        seen.add(iface)
        if mode=='static':
            ip=ipaddress.ip_interface(p.get('address'))
            if ip.version!=4 or ip.ip in (ip.network.network_address,ip.network.broadcast_address) or ip.ip.is_loopback or ip.ip.is_multicast:raise ValueError('Use a valid static IPv4 address with prefix')
            row['address']=str(ip);subnets.append(ip.network)
            if p.get('gateway'):
                gateway=ipaddress.ip_address(p['gateway'])
                if gateway not in ip.network or gateway in (ip.ip,ip.network.network_address,ip.network.broadcast_address):raise ValueError('Gateway must be another host on this port subnet')
                row['gateway']=str(gateway)
        routes=p.get('routes',[])
        if not isinstance(routes,list) or len(routes)>32:raise ValueError('At most 32 static routes per port')
        for route in routes:
            if not isinstance(route,dict) or set(route)-{'destination','gateway','metric'}:raise ValueError('Invalid static route')
            dest=ipaddress.ip_network(route.get('destination'),strict=True);gw=ipaddress.ip_address(address(route.get('gateway')))
            if dest.version!=4 or gw.version!=4 or row['mode']!='static' or gw not in ipaddress.ip_interface(row['address']).network:raise ValueError('Static routes require a reachable IPv4 gateway on this static port')
            row['routes'].append({'destination':str(dest),'gateway':str(gw),'metric':integer(route.get('metric',100),1,32000,'route metric')})
        result['interfaces'].append(row)
    p=value.get('private_lan')
    if p is not None:
        if not isinstance(p,dict) or set(p)-{'interface','mac','address','start','end','lease_hours','dns','route_via','uplink','nas_ports','clients'}:raise ValueError('Invalid private LAN fields')
        iface=interface(p.get('interface'));ip=ipaddress.ip_interface(p.get('address'))
        if iface in seen or ip.version!=4 or not any(ip.network.subnet_of(ipaddress.ip_network(n)) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')) or not 16<=ip.network.prefixlen<=29 or ip.ip in (ip.network.network_address,ip.network.broadcast_address):raise ValueError('Choose a separate physical port and private IPv4 subnet (/16–/29)')
        if any(ip.network.overlaps(n) for n in subnets):raise ValueError('Private LAN overlaps another configured port')
        first=ipaddress.ip_address(p.get('start'));last=ipaddress.ip_address(p.get('end'))
        if first not in ip.network or last not in ip.network or int(first)>int(last) or first==ip.network.network_address or last==ip.network.broadcast_address or int(first)<=int(ip.ip)<=int(last):raise ValueError('DHCP range must contain usable subnet hosts and exclude the NAS')
        dns=p.get('dns',[]);via=p.get('route_via','none');ports=p.get('nas_ports',[443,445]);clients=p.get('clients',[])
        if not isinstance(dns,list) or not 1<=len(dns)<=4 or via not in ('none','uplink','vpn') or not isinstance(clients,list) or len(clients)>1024:raise ValueError('Invalid private DNS, routing or client settings')
        if not isinstance(ports,list) or len(ports)>32:raise ValueError('Choose explicit NAS TCP service ports')
        rows=[client(c,ip.network,str(ip.ip)) for c in clients]
        reservations=[c['reservation'] for c in rows if c['reservation']]
        if len({c['mac'] for c in rows})!=len(rows) or len(set(reservations))!=len(reservations):raise ValueError('Duplicate client MAC or reserved address')
        uplink=interface(p.get('uplink')) if via=='uplink' else None
        if uplink==iface:raise ValueError('Private port cannot also be its uplink')
        result['private_lan']={'interface':iface,'mac':mac(p.get('mac')),'address':str(ip),'start':str(first),'end':str(last),'lease_hours':integer(p.get('lease_hours',24),1,168,'lease duration'),'dns':[address(v) for v in dns],'route_via':via,'uplink':uplink,'nas_ports':sorted({integer(v,1,65535,'NAS port') for v in ports}),'clients':rows}
    return result

def profiles(config):
    values=list(config['interfaces']);p=config.get('private_lan')
    if p:values.append({'interface':p['interface'],'mac':p['mac'],'mode':'static','address':p['address'],'gateway':None,'dns':[],'mtu':1500,'metric':32000,'ipv6':'disabled','routes':[]})
    result={}
    for row in values:
        mode=row['mode'];v6=row['ipv6']=='auto';dhcp=('yes' if v6 else 'ipv4') if mode=='dhcp' else 'no'
        lines=['[Match]','Name='+row['interface'],'MACAddress='+row['mac'],'','[Link]','MTUBytes='+str(row['mtu']),'ActivationPolicy='+('always-down' if mode=='disabled' else 'up'),'RequiredForOnline=no','','[Network]','DHCP='+dhcp,'IPv6AcceptRA='+('yes' if v6 and mode!='disabled' else 'no'),'ConfigureWithoutCarrier='+('yes' if mode=='static' else 'no'),'LinkLocalAddressing='+('ipv6' if v6 and mode!='disabled' else 'no'),'LLMNR=no','MulticastDNS=no']
        if row['address']:lines.append('Address='+row['address'])
        for dns in row['dns']:lines.append('DNS='+dns)
        lines+=['','[DHCPv4]','RouteMetric='+str(row['metric']),'UseDNS='+('no' if row['dns'] else 'yes')]
        routes=list(row['routes'])
        if row.get('gateway'):routes.append({'destination':'0.0.0.0/0','gateway':row['gateway'],'metric':row['metric']})
        for r in routes:lines+=['','[Route]','Destination='+r['destination'],'Gateway='+r['gateway'],'Metric='+str(r['metric'])]
        result[PREFIX+row['interface']+'.network']='\n'.join(lines)+'\n'
    return result

def dnsmasq(config):
    p=config.get('private_lan')
    if not p:return None
    ip=ipaddress.ip_interface(p['address']);lines=['interface='+p['interface'],'bind-dynamic','except-interface=lo','listen-address='+str(ip.ip),'no-resolv','no-hosts','domain-needed','bogus-priv','dhcp-authoritative','dhcp-leasefile=/var/lib/freeqnap-dhcp/leases','dhcp-range='+','.join([p['start'],p['end'],str(ip.netmask),str(p['lease_hours'])+'h']),'dhcp-option=option:router'+(','+str(ip.ip) if p['route_via']!='none' else ''),'dhcp-option=option:dns-server,'+str(ip.ip),'local=/freeqnap.home.arpa/','domain=freeqnap.home.arpa','log-dhcp','log-facility=-','stop-dns-rebind']
    lines+=['server='+v for v in p['dns']]
    for c in p['clients']:
        if c['blocked']:lines.append('dhcp-host='+c['mac']+',ignore')
        elif c['reservation']:lines.append('dhcp-host='+','.join([c['mac'],c['reservation'],*([c['hostname']] if c.get('hostname') else [])]))
    return '\n'.join(lines)+'\n'

def firewall(config,blocked_ips=()):
    p=config.get('private_lan');lines=['destroy table inet '+TABLE,'table inet '+TABLE+' {']
    if not p:return '\n'.join(lines+[' chain forward { type filter hook forward priority -20; policy drop;', '  iifname { "fqvpn0", "fqsv0" } accept', '  oifname { "fqvpn0", "fqsv0" } accept',' }','}'])+'\n'
    subnet=str(ipaddress.ip_interface(p['address']).network);iface=p['interface'];blocked=[c['mac'] for c in p['clients'] if c['blocked']];ips=sorted({str(ipaddress.ip_address(v)) for v in blocked_ips if ipaddress.ip_address(v).version==4 and ipaddress.ip_address(v) in ipaddress.ip_network(subnet)})
    def elements(values):return (' elements = { '+', '.join(values)+' };') if values else ''
    lines+=[' set blocked_mac { type ether_addr;'+elements(blocked)+' }',' set blocked_ip { type ipv4_addr;'+elements(ips)+' }',' chain input { type filter hook input priority -20; policy accept;',f'  iifname "{iface}" jump private_input',' }',' chain private_input {','  ether saddr @blocked_mac drop','  ip saddr @blocked_ip drop','  meta nfproto ipv6 drop','  udp sport 68 udp dport 67 accept',f'  ip saddr != {subnet} drop','  ct state invalid drop','  ct state established,related accept','  udp dport 53 accept','  tcp dport 53 accept']
    if p['nas_ports']:lines+=['  tcp dport { '+', '.join(map(str,p['nas_ports']))+' } accept']
    lines+=['  ip protocol icmp icmp type echo-request limit rate 10/second accept','  counter drop',' }',' chain output { type filter hook output priority -20; policy accept;',f'  oifname "{iface}" ip daddr @blocked_ip drop',' }',' chain forward { type filter hook forward priority -20; policy drop;',f'  iifname "{iface}" ether saddr @blocked_mac drop',f'  iifname "{iface}" ip saddr @blocked_ip drop',f'  oifname "{iface}" ip daddr @blocked_ip drop']
    out=p['uplink'] if p['route_via']=='uplink' else 'fqvpn0' if p['route_via']=='vpn' else None
    if out:lines += [f'  iifname "{iface}" ip saddr {subnet} oifname "{out}" ct state new,established,related accept',f'  iifname "{out}" oifname "{iface}" ip daddr {subnet} ct direction reply ct state established,related accept']
    lines += [f'  iifname "{iface}" counter drop',f'  oifname "{iface}" counter drop','  iifname { "fqvpn0", "fqsv0" } accept','  oifname { "fqvpn0", "fqsv0" } accept',' }']
    if out:lines+=[' chain nat { type nat hook postrouting priority srcnat; policy accept;',f'  ip saddr {subnet} oifname "{out}" masquerade',' }']
    return '\n'.join(lines+['}'])+'\n'

@contextlib.contextmanager
def lock(root):
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    with (root/'lock').open('a') as f:os.fchmod(f.fileno(),0o600);fcntl.flock(f,fcntl.LOCK_EX);yield

class Network:
    def __init__(self,ctx):self.ctx=ctx;self.root=ctx.directory/'network'
    def current(self):
        p=self.root/'active.json';return json.loads(p.read_text()) if p.exists() else dict(DEFAULT)
    def ports(self):
        rows=json.loads(self.ctx.run('ip','-j','address','show'));result=[]
        for r in rows:
            if r.get('link_type')!='ether' or not (Path('/sys/class/net')/r['ifname']/'device').exists():continue
            result.append({'interface':r['ifname'],'mac':r['address'].lower(),'device':str((Path('/sys/class/net')/r['ifname']/'device').resolve()),'mtu':r['mtu'],'state':r.get('operstate'),'addresses':r.get('addr_info',[])})
        return result
    def status(self,request=None):
        cfg=self.current();p=cfg.get('private_lan');observed={}
        if p:
            for r in json.loads(self.ctx.run('ip','-j','neigh','show','dev',p['interface'])):
                if r.get('lladdr') and ':' not in r.get('dst',''):
                    try:key=mac(r['lladdr'])
                    except ValueError:continue
                    observed.setdefault(key,{'mac':key,'addresses':[]})['addresses'].append(r['dst'])
            lease=Path('/var/lib/freeqnap-dhcp/leases')
            if lease.exists():
                for line in lease.read_text().splitlines():
                    fields=line.split()
                    if len(fields)!=5:continue
                    try:key=mac(fields[1]);expires=int(fields[0]);ip=address(fields[2])
                    except ValueError:continue
                    row=observed.setdefault(key,{'mac':key,'addresses':[]});row.update(lease_expires=expires,reported_hostname=fields[3]);row['addresses']=sorted(set(row['addresses']+[ip]))
            for c in p['clients']:observed.setdefault(c['mac'],{'mac':c['mac'],'addresses':[]}).update(c)
        pending=self.ctx.state.setting('network_pending');return {'configuration':cfg,'ports':self.ports(),'clients':list(observed.values()),'pending':pending,'runtime':self.ctx.state.setting('network_runtime',{'state':'disabled'}),'last_change':self.ctx.state.setting('network_last_change'),'private_lan_default':'disabled','client_identity_limit':'MAC/IP controls do not authenticate devices or isolate peers on an external switch.'}
    def plan(self,request):
        cfg=validate(request);ports=self.ports();by_name={p['interface']:p for p in ports};selected=[*cfg['interfaces'],*([cfg['private_lan']] if cfg['private_lan'] else [])]
        for p in selected:
            if p['interface'] not in by_name or p['mac']!=by_name[p['interface']]['mac']:raise ValueError('Physical port/MAC changed; refresh port discovery')
        p=cfg.get('private_lan')
        if p:
            network=ipaddress.ip_interface(p['address']).network
            for port in ports:
                if port['interface']==p['interface']:continue
                for a in port['addresses']:
                    if a.get('family')=='inet' and network.overlaps(ipaddress.ip_network(a['local']+'/'+str(a['prefixlen']),strict=False)):raise ValueError('Private LAN overlaps a live network on another port')
            if p['route_via']=='uplink' and p['uplink'] not in by_name:raise ValueError('Uplink is not a physical port')
            vpn=self.ctx.state.setting('vpn_runtime',{})
            active=self.ctx.directory/'vpn'/'active.json';vpn_cfg=json.loads(active.read_text()) if active.exists() else {}
            tunnel_networks=([ipaddress.ip_network(vpn_cfg['server']['subnet'])] if vpn_cfg.get('server') else [])+[ipaddress.ip_interface(v).network for v in (vpn_cfg.get('client') or {}).get('addresses',[])]
            if any(n.version==4 and network.overlaps(n) for n in tunnel_networks):raise ValueError('Private LAN overlaps a VPN tunnel/server subnet')
            if p['route_via']=='uplink' and vpn_cfg.get('client'):raise ValueError('Direct uplink routing is blocked while a VPN client is configured; use VPN routing or no internet')
            if p['route_via']=='vpn' and not vpn_cfg.get('client'):raise ValueError('Configure a VPN client before selecting private-LAN VPN routing')
        identities=[{k:p[k] for k in ['interface','mac','device']} for p in ports if p['interface'] in {s['interface'] for s in selected}]
        return self.ctx.plan('network-change',{'configuration':cfg,'previous':self.current(),'identities':identities,'review':['Only selected physical ports are managed; unselected factory profiles remain.','A private LAN must be a physically isolated cable/switch segment. Do not connect its DHCP server to an existing LAN.','Confirm successful access within 120 seconds of application or the previous configuration is restored.']},'APPLY NETWORK')
    def apply(self,request):
        with lock(self.root):
            if self.ctx.state.setting('network_pending'):raise ValueError('Confirm or roll back the pending network change first')
            path,plan=self.ctx.reviewed(request,'network-change');body=plan['body']
            live={p['interface']:p for p in self.ports()}
            if body['previous']!=self.current() or any(any(live.get(p['interface'],{}).get(k)!=p[k] for k in ['mac','device']) for p in body['identities']):raise ValueError('Network configuration or physical identity changed since review')
            if self.ctx.state.setting('vpn_pending'):raise ValueError('Confirm or roll back the pending VPN change first')
            self.ctx.run('systemctl','is-active','freeqnap-network.service')
            self.ctx.consume(path,plan)
            job=self.ctx.operation('network-change',{'plan_id':plan['id']})
            pending={'job_id':job,'id':secrets.token_hex(16),'phase':'requested','previous':self.current(),'requested_at':time.time(),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'configuration_sha256':hashlib.sha256(canonical(body['configuration'])).hexdigest()}
            atomic(self.root/'pending.json',pending);self.ctx.state.set('network_pending',pending);atomic(self.root/'active.json',body['configuration'])
            return {'pending':pending,'confirm_required':True}
    def confirm(self,request):
        with lock(self.root):
            p=self.ctx.state.setting('network_pending');runtime=self.ctx.state.setting('network_runtime',{})
            if not p or request.get('id')!=p['id'] or p.get('phase')!='active' or time.monotonic()>=p.get('deadline_monotonic',0) or runtime.get('configuration_sha256')!=p['configuration_sha256'] or runtime.get('state')!='running':raise ValueError('No successfully applied, unexpired network change to confirm')
            atomic(self.root/'confirmed.json',{'id':p['id']});self.ctx.state.set('network_pending',None)
            self.ctx.state.set('network_last_change',{'id':p['id'],'result':'confirmed','at':time.time()})
            if p.get('job_id'):self.ctx.state.finish(p['job_id'],result={'network_change':'confirmed'})
            return {'confirmed':True}
    def client_plan(self,request):
        cfg=self.current();p=cfg.get('private_lan')
        if not p:raise ValueError('Enable the isolated private LAN before managing its clients')
        value=client(request,ipaddress.ip_interface(p['address']).network,p['address'].split('/')[0])
        p['clients']=[c for c in p['clients'] if c['mac']!=value['mac']]+[value]
        return self.plan(cfg)

    def rollback(self,request=None):
        with lock(self.root):
            if not self.ctx.state.setting('network_pending'):raise ValueError('No pending network change')
            atomic(self.root/'rollback-request.json',{'requested_at':time.time()});return {'rollback_requested':True}
