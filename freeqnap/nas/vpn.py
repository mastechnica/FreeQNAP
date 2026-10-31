"""Declarative VPN configuration and narrowly scoped, default-deny firewall.

No imported hooks, shell fragments, wg-quick files or arbitrary OpenVPN options.
A client tunnel is always an untrusted WAN. Gateway forwarding is explicit.
"""
import base64
import contextlib
import fcntl
import os
import hashlib
import ipaddress
import json
import re
import secrets
import time
from pathlib import Path
from .common import canonical, name
from ..state import atomic

CLIENT='fqvpn0'
SERVER='fqsv0'
TABLE='freeqnap_vpn'
MARK=0x4651
ROUTE_TABLE=51820
INTERFACES={'enp0s1','enp0s3'}

def key(value):
    try:raw=base64.b64decode(value,validate=True)
    except (ValueError,TypeError):raise ValueError('WireGuard keys must be base64 encoded') from None
    if len(raw)!=32 or raw==bytes(32):raise ValueError('WireGuard keys must contain 32 nonzero bytes')
    return base64.b64encode(raw).decode()

def address(value):
    ip=ipaddress.ip_address(value)
    if ip.is_loopback or ip.is_multicast or ip.is_unspecified or ip.is_link_local:raise ValueError('Use a unicast endpoint address, not a hostname or link-local address')
    return str(ip)

def network(value, version=4):
    n=ipaddress.ip_network(value,strict=True)
    if n.version!=version or n.prefixlen==0 or n.is_multicast or n.is_loopback:raise ValueError('Use an explicit network of the correct address family')
    return str(n)

def port(value):
    if isinstance(value,bool) or not str(value).isdigit() or not 1<=int(value)<=65535:raise ValueError('Invalid network port')
    return int(value)

def certificate(value,kind):
    if not isinstance(value,str) or not 32<=len(value)<=32768:raise ValueError('Missing inline certificate/key material')
    allowed={'ca':('CERTIFICATE',),'cert':('CERTIFICATE',),'key':('PRIVATE KEY','RSA PRIVATE KEY','EC PRIVATE KEY'),'tls-crypt':('OpenVPN Static key V1',)}[kind]
    if not any(value.strip().startswith('-----BEGIN '+label+'-----') and value.strip().endswith('-----END '+label+'-----') for label in allowed):raise ValueError('Only inline PEM certificates and unencrypted private keys are supported')
    if any(line.lstrip().startswith(('<','>')) for line in value.splitlines()):raise ValueError('Invalid inline material')
    return value.strip()+'\n'

def validate(raw):
    if not isinstance(raw,dict):raise ValueError('VPN configuration must be an object')
    if set(raw)-{'client','server'}:raise ValueError('Unknown VPN configuration field')
    out={'version':1,'client':None,'server':None}
    c=raw.get('client')
    if c:
        allowed={'type','endpoint','port','protocol','addresses','private_key','public_key','preshared_key','ca','cert','key','tls_crypt','username','password','server_name','dns','full_tunnel','lan_interface','lan_networks','gateway_clients'}
        if not isinstance(c,dict) or set(c)-allowed:raise ValueError('Unsupported VPN client field; imported scripts/options are forbidden')
        kind=c.get('type')
        if kind not in ('wireguard','openvpn'):raise ValueError('Choose WireGuard or OpenVPN')
        interface=c.get('lan_interface','enp0s1')
        if interface not in INTERFACES:raise ValueError('Choose a known LAN interface')
        lans=[network(v) for v in c.get('lan_networks',[])]
        if not 1<=len(lans)<=8 or any(not ipaddress.ip_network(v).is_private for v in lans):raise ValueError('Declare the private, directly connected management LAN networks')
        clients=[network(v) for v in c.get('gateway_clients',[])]
        if len(clients)>32 or any(not any(ipaddress.ip_network(v).subnet_of(ipaddress.ip_network(lan)) for lan in lans) for v in clients):raise ValueError('Gateway clients must be explicit subsets of the management LAN')
        full=c.get('full_tunnel',True)
        if not isinstance(full,bool):raise ValueError('Full tunnel must be true or false')
        dns=[address(v) for v in c.get('dns',[])]
        if not 1<=len(dns)<=3:raise ValueError('Specify one to three DNS servers reachable through the VPN')
        out['client']={'type':kind,'endpoint':address(c['endpoint']),'port':port(c.get('port',51820 if kind=='wireguard' else 1194)),
                       'protocol':c.get('protocol','udp'),'full_tunnel':full,'dns':dns,'lan_interface':interface,'lan_networks':lans,'gateway_clients':clients}
        v=out['client']
        if kind=='wireguard':
            if v['protocol']!='udp':raise ValueError('WireGuard uses UDP')
            v.update(private_key=key(c['private_key']),public_key=key(c['public_key']))
            if c.get('preshared_key'):v['preshared_key']=key(c['preshared_key'])
            addrs=[str(ipaddress.ip_interface(a)) for a in c.get('addresses',[])]
            if not 1<=len(addrs)<=2 or len({ipaddress.ip_interface(a).version for a in addrs})!=len(addrs):raise ValueError('Provide one tunnel address per address family')
            for assigned in addrs:
                ip=ipaddress.ip_interface(assigned)
                if ip.ip.is_loopback or ip.ip.is_unspecified or ip.ip.is_multicast or ip.ip.is_link_local:raise ValueError('Invalid WireGuard tunnel address')
                if ip.version==4 and any(ip.network.overlaps(ipaddress.ip_network(lan)) for lan in lans):raise ValueError('Tunnel address overlaps the management LAN')
                if ipaddress.ip_address(v['endpoint']).version==ip.version and ipaddress.ip_address(v['endpoint']) in ip.network:raise ValueError('Transport endpoint must not be inside the tunnel subnet')
            v['addresses']=addrs
        else:
            if v['protocol'] not in ('udp','tcp'):raise ValueError('OpenVPN supports UDP or TCP')
            v.update({k:certificate(c[k],k) for k in ('ca','cert','key')})
            if c.get('tls_crypt'):v['tls_crypt']=certificate(c['tls_crypt'],'tls-crypt')
            peer=c.get('server_name','')
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',peer):raise ValueError('Enter the exact certificate name of the VPN server')
            v['server_name']=peer
            if c.get('username') or c.get('password'):
                for k in ('username','password'):
                    if not isinstance(c.get(k),str) or not 1<=len(c[k])<=1024 or any(ord(t)<32 for t in c[k]):raise ValueError('Invalid provider login')
                    v[k]=c[k]
    s=raw.get('server')
    if s:
        allowed={'type','port','subnet','public_endpoint','lan_networks','nas_ports','gateway','peers'}
        if not isinstance(s,dict) or set(s)-allowed:raise ValueError('Unsupported VPN server field')
        kind=s.get('type')
        if kind not in ('wireguard','openvpn'):raise ValueError('Choose WireGuard or OpenVPN server')
        subnet=ipaddress.ip_network(network(s.get('subnet','10.77.0.0/24')))
        if not subnet.is_private or not 24<=subnet.prefixlen<=28:raise ValueError('Choose a private IPv4 /24 through /28 server subnet')
        lans=[network(v) for v in s.get('lan_networks',[])]
        if len(lans)>8 or any(not ipaddress.ip_network(v).is_private or subnet.overlaps(ipaddress.ip_network(v)) for v in lans):raise ValueError('Invalid server LAN routes')
        if out['client'] and any(subnet.overlaps(ipaddress.ip_network(v)) for v in out['client']['lan_networks']):raise ValueError('Server subnet overlaps the management LAN')
        gateway=s.get('gateway',False)
        if not isinstance(gateway,bool) or gateway and not out['client']:raise ValueError('Server internet forwarding requires a configured client VPN')
        endpoint=s.get('public_endpoint','')
        if not isinstance(endpoint,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}',endpoint):raise ValueError('Enter the public hostname or IPv4 address clients will use')
        peers=s.get('peers',[])
        if not isinstance(peers,list) or len(peers)>32:raise ValueError('At most 32 peers are supported')
        validated=[]
        for p in peers:
            if set(p)!={'name','public_key','ip'}:raise ValueError('WireGuard peers need a name, public key and fixed IPv4 address')
            ip=ipaddress.ip_address(p['ip'])
            if ip not in subnet or ip in (subnet.network_address,subnet.broadcast_address,subnet.network_address+1):raise ValueError('Peer IP must be an unused host inside the server subnet')
            validated.append({'name':name(p['name']),'public_key':key(p['public_key']),'ip':str(ip)})
        if len({p['ip'] for p in validated})!=len(validated) or len({p['public_key'] for p in validated})!=len(validated) or len({p['name'] for p in validated})!=len(validated):raise ValueError('Duplicate peer name, key or IP')
        if kind=='openvpn' and peers:raise ValueError('OpenVPN peers are issued through the local certificate interface')
        out['server']={'type':kind,'port':port(s.get('port',51821 if kind=='wireguard' else 1195)), 'subnet':str(subnet),'public_endpoint':endpoint,'lan_networks':lans,'nas_ports':sorted({port(p) for p in s.get('nas_ports',[443,445])}),'gateway':gateway,'peers':validated}
    return out

def public(config):
    value=json.loads(json.dumps(config))
    if value.get('client'):
        for field in ('private_key','preshared_key','ca','cert','key','tls_crypt','username','password'):value['client'].pop(field,None)
        value['client']['credentials_stored_privately']=True
    return value

def firewall(config,private=None):
    """Own table only: WAN input guard, no-fallback output, opt-in IPv4 NAT."""
    c=config.get('client');s=config.get('server')
    lines=['destroy table inet '+TABLE,'table inet '+TABLE+' {',' chain input { type filter hook input priority -25; policy accept;', '  iifname "lo" accept']
    if c:lines+=['  iifname "'+CLIENT+'" ct direction reply ct state established,related accept','  iifname "'+CLIENT+'" counter drop']
    if s:
        ports=', '.join(str(p) for p in s['nas_ports'])
        if ports:lines += [f'  iifname "{SERVER}" ip saddr {s["subnet"]} tcp dport {{ {ports} }} ct state new,established accept']
        lines += [f'  iifname "{SERVER}" ct state established,related accept',f'  iifname "{SERVER}" counter drop']
    lines += [' }',' chain output { type filter hook output priority -25; policy accept;']
    if c and c['full_tunnel']:
        lines += ['  oifname "lo" accept',f'  oifname "{CLIENT}" accept']
        if s:lines += [f'  meta mark {ROUTE_TABLE} udp sport {s["port"]} ct direction reply ct state established accept']
        if s:lines += [f'  oifname "{SERVER}" ip daddr {s["subnet"]} accept']
        family='ip6' if ':' in c['endpoint'] else 'ip'
        lines += [f'  meta mark {ROUTE_TABLE} {family} daddr {c["endpoint"]} {c["protocol"]} dport {c["port"]} accept',
                  '  udp dport { 53, 853 } counter drop','  tcp dport { 53, 853 } counter drop',
                  f'  oifname "{c["lan_interface"]}" udp sport 68 udp dport 67 accept']
        if private:
            subnet=str(ipaddress.ip_interface(private['address']).network)
            lines += [f'  oifname "{private["interface"]}" ip daddr {subnet} accept',f'  oifname "{private["interface"]}" udp sport 67 udp dport 68 accept']
        for lan in c['lan_networks']:lines += [f'  oifname "{c["lan_interface"]}" ip daddr {lan} accept']
        # NDP is essential for local IPv6; do not permit IPv6 internet fallback.
        lines += ['  meta l4proto ipv6-icmp icmpv6 type { nd-neighbor-solicit, nd-neighbor-advert, nd-router-solicit } accept','  counter drop']
    lines += [' }',' chain forward { type filter hook forward priority -25; policy '+('drop' if c or s else 'accept')+';']
    if c:
        for client in c['gateway_clients']:
            lines += [f'  iifname "{c["lan_interface"]}" ip saddr {client} oifname "{CLIENT}" ct state new,established,related accept',
                      f'  iifname "{CLIENT}" oifname "{c["lan_interface"]}" ip daddr {client} ct direction reply ct state established,related accept']
    if c and private and private['route_via']=='vpn':
        subnet=str(ipaddress.ip_interface(private['address']).network);iface=private['interface']
        lines += [f'  iifname "{iface}" ip saddr {subnet} oifname "{CLIENT}" ct state new,established,related accept',f'  iifname "{CLIENT}" oifname "{iface}" ip daddr {subnet} ct direction reply ct state established,related accept']
    if s:
        for lan in s['lan_networks']:
            lines += [f'  iifname "{SERVER}" ip saddr {s["subnet"]} ip daddr {lan} ct state new,established,related accept',
                      f'  oifname "{SERVER}" ip daddr {s["subnet"]} ip saddr {lan} ct direction reply ct state established,related accept']
        if s['gateway']:
            lines += [f'  iifname "{SERVER}" ip saddr {s["subnet"]} oifname "{CLIENT}" ct state new,established,related accept',
                      f'  iifname "{CLIENT}" oifname "{SERVER}" ip daddr {s["subnet"]} ct direction reply ct state established,related accept']
    lines += [' }',' chain nat { type nat hook postrouting priority srcnat; policy accept;']
    if c:
        if private and private['route_via']=='vpn':lines += [f'  ip saddr {str(ipaddress.ip_interface(private["address"]).network)} oifname "{CLIENT}" masquerade']
        for client in c['gateway_clients']:lines += [f'  ip saddr {client} oifname "{CLIENT}" masquerade']
    if s:
        for lan in s['lan_networks']:lines += [f'  ip saddr {s["subnet"]} ip daddr {lan} masquerade']
        if s['gateway']:lines += [f'  ip saddr {s["subnet"]} oifname "{CLIENT}" masquerade']
    lines += [' }','}']
    return '\n'.join(lines)+'\n'

def wireguard(config,private_key=None):
    if private_key is None:
        c=config['client'];endpoint=('['+c['endpoint']+']') if ':' in c['endpoint'] else c['endpoint']
        lines=['[Interface]','PrivateKey = '+c['private_key'],'FwMark = '+str(ROUTE_TABLE),'[Peer]','PublicKey = '+c['public_key'],'Endpoint = '+endpoint+':'+str(c['port']),'AllowedIPs = 0.0.0.0/0, ::/0','PersistentKeepalive = 25']
        if c.get('preshared_key'):lines+=['PresharedKey = '+c['preshared_key']]
    else:
        s=config['server'];lines=['[Interface]','PrivateKey = '+key(private_key),'ListenPort = '+str(s['port']),'FwMark = '+str(ROUTE_TABLE)]
        for p in s['peers']:lines+=['[Peer]','PublicKey = '+p['public_key'],'AllowedIPs = '+p['ip']+'/32']
    return '\n'.join(lines)+'\n'

def openvpn_client(c,root):
    root=Path(root)
    lines=['client','dev '+CLIENT,'dev-type tun','proto '+('tcp-client' if c['protocol']=='tcp' else 'udp'),'remote '+c['endpoint']+' '+str(c['port']),'nobind','persist-key','persist-tun','remote-cert-tls server','verify-x509-name '+c['server_name']+' name','tls-version-min 1.2','data-ciphers AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305','allow-compression no','disable-dco','script-security 1','route-noexec','route-nopull','pull-filter ignore "redirect-gateway"','pull-filter ignore "dhcp-option"','auth-nocache','auth-retry nointeract','verb 2','mark '+str(ROUTE_TABLE)]
    for k in ('ca','cert','key'):
        lines += ['<'+k+'>',c[k].strip(),'</'+k+'>']
    if c.get('tls_crypt'):lines+=['<tls-crypt>',c['tls_crypt'].strip(),'</tls-crypt>']
    if c.get('username'):lines+=['auth-user-pass '+str(root/'provider-login')]
    return '\n'.join(lines)+'\n'

@contextlib.contextmanager
def configuration_lock(root):
    root=Path(root);root.mkdir(mode=0o700,parents=True,exist_ok=True)
    with (root/'operations.lock').open('a') as stream:
        os.fchmod(stream.fileno(),0o600);fcntl.flock(stream,fcntl.LOCK_EX)
        try:yield
        finally:fcntl.flock(stream,fcntl.LOCK_UN)

class VPN:
    def __init__(self,ctx):self.ctx=ctx;self.root=ctx.directory/'vpn'
    def lock(self):return configuration_lock(self.root)
    def current(self):
        path=self.root/'active.json'
        return json.loads(path.read_text()) if path.exists() else {'version':1,'client':None,'server':None}
    def peer_status(self,request=None):
        config=self.current();server=config.get('server');runtime=self.ctx.state.setting('vpn_runtime',{'state':'disabled'});rows=[];available=False
        if server and server['type']=='wireguard':
            try:
                handshakes={r.split()[0]:int(r.split()[1]) for r in self.ctx.run('wg','show',SERVER,'latest-handshakes').splitlines()}
                transfers={r.split()[0]:[int(r.split()[1]),int(r.split()[2])] for r in self.ctx.run('wg','show',SERVER,'transfer').splitlines()};available=True
            except (OSError,ValueError,IndexError):handshakes={};transfers={}
            for peer in server['peers']:
                last=handshakes.get(peer['public_key'],0);traffic=transfers.get(peer['public_key'],[0,0]);rows.append({'name':peer['name'],'address':peer['ip'],'state':'Recently active' if available and last and time.time()-last<180 else 'No recent handshake' if available else 'Status unavailable','connected':bool(available and last and time.time()-last<180),'received':traffic[0],'sent':traffic[1],'last_handshake':last})
        elif server and server['type']=='openvpn':
            sessions={}
            try:
                path=Path('/run/freeqnap/openvpn-server.status');info=path.lstat()
                if path.is_symlink() or info.st_size>1024*1024 or not 0<=time.time()-info.st_mtime<30:raise ValueError('OpenVPN status is stale')
                headers=None
                for line in path.read_text().splitlines():
                    cols=line.split('\t')
                    if cols[:2]==['HEADER','CLIENT_LIST']:headers=cols[2:]
                    elif cols and cols[0]=='CLIENT_LIST' and headers:
                        row=dict(zip(headers,cols[1:]));sessions[row.get('Common Name','')]={'address':row.get('Virtual Address',''),'received':int(row.get('Bytes Received',0)),'sent':int(row.get('Bytes Sent',0))}
                available=headers is not None
            except (OSError,ValueError):pass
            for peer in self.ctx.state.setting('openvpn_peers',{}).values():
                session=sessions.get(peer['name']);rows.append({'name':peer['name'],'state':'Revoked' if peer.get('revoked') else 'Connected' if session else 'Disconnected' if available else 'Status unavailable','connected':bool(session and not peer.get('revoked')),**(session or {})})
        return {'server':server and server['type'],'client':(config.get('client') or {}).get('type'),'runtime':runtime,'available':available,'clients':rows,'wireguard_note':'Recently active means a handshake within 3 minutes, not a persistent connection.','sampled_at':time.time()}

    def status(self,request=None):
        status=self.ctx.state.setting('vpn_runtime',{'state':'disabled'})
        if not self.current().get('client') and not self.current().get('server'):status={**status,'state':'disabled'}
        server_public_key=None
        if (self.current().get('server') or {}).get('type')=='wireguard':
            try:server_public_key=self.ctx.run('wg','show',SERVER,'public-key').strip()
            except (OSError,ValueError):pass
        return {'configuration':public(self.current()),'server_public_key':server_public_key,'runtime':status,'pending':self.ctx.state.setting('vpn_pending'),
                'openvpn_peers':list(self.ctx.state.setting('openvpn_peers',{}).values()),'gateway_ipv4_only':True,'gateway_dns_note':'LAN clients must use tunnel-reachable DNS themselves; this NAS is not a DHCP or LAN DNS server.',
                'manual_recovery':'Local UART/console: systemctl stop freeqnap-vpn; python3 -m freeqnap.nas.vpn_runtime --disable'}
    def plan(self,request):
        config=validate(request)
        # Secrets never enter reviewed plans, activity records, or the web status.
        token=secrets.token_hex(16);path=self.root/'candidates'/(token+'.json');atomic(path,config)
        return self.ctx.plan('vpn-change',{'candidate':token,'configuration':public(config),'candidate_sha256':hashlib.sha256(canonical(config)).hexdigest(),
            'review':['Client VPN is an untrusted WAN: unsolicited tunnel input is blocked.','Full tunnel has a persistent IPv4/IPv6/DNS kill switch; disconnect does not restore ordinary internet.','Forwarding is denied except the listed LAN clients/server routes. No router, DHCP or LAN address changes.','Confirm local administration within 120 seconds or the prior VPN configuration is restored.']},'APPLY VPN')
    def apply(self,request):
        with self.lock():
            if self.ctx.state.setting('network_pending'):raise ValueError('Confirm or roll back the pending network change first')
            if self.ctx.state.setting('vpn_pending'):raise ValueError('Confirm or roll back the pending VPN change first')
            path,plan=self.ctx.reviewed(request,'vpn-change');candidate=self.root/'candidates'/(plan['body']['candidate']+'.json');config=json.loads(candidate.read_text())
            if hashlib.sha256(canonical(config)).hexdigest()!=plan['body']['candidate_sha256']:raise ValueError('VPN candidate changed; review again')
            # Live route preflight refuses remote/unrelated management networks.
            if config.get('client'):
                links=json.loads(self.ctx.run('ip','-j','-4','route','show','scope','link','dev',config['client']['lan_interface']))
                direct={row.get('dst') for row in links if row.get('dst')!='default'}
                if not all(any(ipaddress.ip_network(lan).subnet_of(ipaddress.ip_network(d)) for d in direct if d) for lan in config['client']['lan_networks']):raise ValueError('Declared management LAN is not directly connected on the selected interface')
            self.ctx.consume(path,plan)
            previous=self.current();atomic(self.root/'previous.json',previous)
            pending={'id':secrets.token_hex(16),'deadline':time.time()+120}
            atomic(self.root/'pending.json',pending);self.ctx.state.set('vpn_pending',pending)
            atomic(self.root/'active.json',config)
            self.ctx.run('systemctl','restart','freeqnap-vpn.service',timeout=45)
            return {'pending':pending,'confirm_required':True}
    def confirm(self,request):
        with self.lock():
            pending=self.ctx.state.setting('vpn_pending')
            if not pending or request.get('id')!=pending['id'] or time.time()>=pending['deadline']:raise ValueError('No current VPN change to confirm')
            runtime=self.ctx.state.setting('vpn_runtime',{})
            if runtime.get('state')!='running' or runtime.get('config_sha256')!=hashlib.sha256(canonical(self.current())).hexdigest():raise ValueError('VPN runtime has not applied this configuration successfully')
            # Agent also checks this file; broker restart cannot cancel the rollback timer.
            atomic(self.root/'confirmed.json',pending);self.ctx.state.set('vpn_pending',None)
            return {'confirmed':True,'tunnel_handshake_still_requires_peer_validation':True}
    def rollback(self,request=None):
        with self.lock():
            previous=self.root/'previous.json'
            if not previous.exists():raise ValueError('There is no previous VPN configuration')
            atomic(self.root/'active.json',json.loads(previous.read_text()))
            (self.root/'pending.json').unlink(missing_ok=True);self.ctx.state.set('vpn_pending',None)
            self.ctx.run('systemctl','restart','freeqnap-vpn.service',timeout=45)
            return {'rolled_back':True}

    def peer(self,request):
        from . import vpn_pki
        with self.lock():
            if self.ctx.state.setting('network_pending'):raise ValueError('Confirm or roll back the pending network change first')
            if self.ctx.state.setting('vpn_pending'):raise ValueError('Confirm or roll back the pending VPN change before issuing peers')
            config=self.current();server=config.get('server')
            if not server or server['type']!='openvpn':raise ValueError('Configure an OpenVPN server first; WireGuard accepts client-generated public keys')
            ident=name(request.get('name'))
            vpn_pki.ensure(self.root/'pki');vpn_pki.issue(self.root/'pki',ident)
            peers=self.ctx.state.setting('openvpn_peers',{});peers[ident]={'name':ident,'issued':time.time(),'revoked':False};self.ctx.state.set('openvpn_peers',peers)
            # Returned once, never saved to activity. CA private key is never included.
            return {'filename':ident+'.ovpn','configuration':vpn_pki.export(server,self.root/'pki',ident),'private':True}
    def revoke(self,request):
        from . import vpn_pki
        with self.lock():
            if self.ctx.state.setting('network_pending'):raise ValueError('Confirm or roll back the pending network change first')
            if self.ctx.state.setting('vpn_pending'):raise ValueError('Confirm or roll back the pending VPN change before revoking peers')
            ident=name(request.get('name'))
            config=self.current();server=config.get('server')
            if server and server['type']=='wireguard':
                selected=next((p for p in server['peers'] if p['name']==ident),None)
                if not selected:raise ValueError('Unknown WireGuard peer')
                self.ctx.run('wg','set',SERVER,'peer',selected['public_key'],'remove')
                server['peers']=[p for p in server['peers'] if p['name']!=ident];atomic(self.root/'active.json',config)
                return {'revoked':ident,'existing_sessions_disconnected':True}
            peers=self.ctx.state.setting('openvpn_peers',{})
            if ident not in peers or peers[ident]['revoked']:raise ValueError('Select an active issued OpenVPN peer')
            vpn_pki.revoke(self.root/'pki',ident);peers[ident].update(revoked=True,revoked_at=time.time());self.ctx.state.set('openvpn_peers',peers)
            # Restart disconnects currently authenticated clients too, including the revoked peer.
            self.ctx.run('systemctl','restart','freeqnap-vpn.service')
            return {'revoked':ident,'existing_sessions_disconnected':True}

    def wireguard_profile(self,request):
        config=self.current();server=config.get('server')
        if not server or server['type']!='wireguard':raise ValueError('Configure a WireGuard server first')
        ident=name(request.get('name'));peer=next((p for p in server['peers'] if p['name']==ident),None)
        if not peer:raise ValueError('Unknown WireGuard peer')
        pub=self.ctx.run('wg','show',SERVER,'public-key').strip()
        if not pub or pub=='(none)':raise ValueError('WireGuard server key is not ready')
        allowed=['0.0.0.0/0','::/0'] if server['gateway'] else [server['subnet'],*server['lan_networks']]
        lines=['# Insert only the private key generated on THIS client. Never share it.','[Interface]','PrivateKey = YOUR_CLIENT_PRIVATE_KEY','Address = '+peer['ip']+'/32','[Peer]','PublicKey = '+pub,'Endpoint = '+server['public_endpoint']+':'+str(server['port']),'AllowedIPs = '+', '.join(allowed),'PersistentKeepalive = 25']
        if server['gateway'] and config.get('client'):lines.insert(4,'DNS = '+', '.join(config['client']['dns']))
        return {'filename':ident+'-wireguard-template.conf','configuration':'\n'.join(lines)+'\n','contains_private_key':False,'requires_client_private_key':True}
