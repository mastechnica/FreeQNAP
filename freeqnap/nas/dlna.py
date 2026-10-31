"""Default-deny DLNA device approval, enforced for catalog and stream packets.

Only this application's named nftables table is changed. No global ruleset flush.
Device approvals bind interface, IP and observed Ethernet MAC; this is not a
cryptographic client login and does not protect against a hostile LAN spoofer.
"""
import hashlib
import functools
import threading
import ipaddress
import json
import os
import pwd
import re
import time
from pathlib import Path

TABLE='freeqnap_dlna'
INTERFACES={'enp0s1','enp0s3'}

PROFILES={
 'generic':{'name':'Generic DLNA player','suggestions':['Start with direct play.','MP4 with H.264 video and AAC audio is a useful compatibility test.','Test subtitles and seeking on the actual player.']},
 'appletv':{'name':'Apple TV','suggestions':['Use a DLNA-capable app, or an SMB-capable player for per-user folder permissions.','Test MP4/H.264/AAC first. Codec support depends on the app and device generation.']},
 'roku':{'name':'Roku','suggestions':['Use Roku Media Player or another compatible app.','Test MP4/H.264/AAC; codec and subtitle support vary by model.']},
 'firetv':{'name':'Fire TV','suggestions':['Use a DLNA/SMB-capable player app.','Try direct playback before converting files.']},
 'smarttv':{'name':'Smart TV','suggestions':['Test a short MP4/H.264/AAC sample.','If audio or subtitles fail, try a compatible player app or convert a copy.','The television model matters more than the brand alone.']},
 'audio':{'name':'Network music player','suggestions':['Test MP3 first, then FLAC if the device supports it.','Lossless audio compatibility and gapless playback depend on the player.']}}

def endpoint(ip, mac, interface):
    address=ipaddress.ip_address(ip)
    if address.is_unspecified or address.is_multicast or address.is_loopback:
        raise ValueError('A unicast network client address is required')
    mac=str(mac).lower()
    if not re.fullmatch(r'[0-9a-f]{2}(:[0-9a-f]{2}){5}',mac) or int(mac[:2],16)&1 or mac=='00:00:00:00:00:00':
        raise ValueError('A valid observed unicast client MAC is required')
    if interface not in INTERFACES:raise ValueError('Invalid media interface')
    ident=hashlib.sha256((interface+'|'+str(address)+'|'+mac).encode()).hexdigest()[:32]
    return {'id':ident,'ip':str(address),'version':address.version,'mac':mac,'interface':interface}

def render(clients, interface, media_uid):
    if interface not in INTERFACES or not isinstance(media_uid,int) or media_uid<0:
        raise ValueError('Invalid interface or service UID')
    approved=[]
    for item in clients:
        verified=endpoint(item['ip'],item['mac'],item['interface'])
        if verified['interface']==interface and item.get('approved') is True:approved.append(verified)
    four=[item for item in approved if item['version']==4];six=[item for item in approved if item['version']==6]
    def elements(items,mac=False):
        values=sorted({item['ip']+(' . '+item['mac'] if mac else '') for item in items})
        return (' elements = { '+', '.join(values)+' };') if values else ''
    lines=['destroy table inet '+TABLE,'table inet '+TABLE+' {']
    for version,kind,items in ((4,'ipv4_addr',four),(6,'ipv6_addr',six)):
        lines += [f' set approved{version} {{ type {kind} . ether_addr; {elements(items,True)} }}',
                  f' set destinations{version} {{ type {kind}; {elements(items)} }}',
                  f' set seen{version} {{ type {kind} . ether_addr; flags dynamic,timeout; timeout 24h; size 1024; }}']
    lines += [' chain incoming { type filter hook input priority -20; policy accept;',
              '  iifname "lo" accept']
    for version,network in ((4,'ip'),(6,'ip6')):
        # Record requests before allow/drop; no packet payload is written to disk.
        base=f'  iifname "{interface}" meta nfproto ipv{version} '
        lines += [base+f'tcp dport 49152 tcp flags & syn == syn update @seen{version} {{ {network} saddr . ether saddr timeout 24h }}',
                  base+f'udp dport 1900 @th,64,64 0x4d2d534541524348 update @seen{version} {{ {network} saddr . ether saddr timeout 24h }}',
                  base+f'tcp dport 49152 {network} saddr . ether saddr @approved{version} accept',
                  base+f'udp dport 1900 {network} saddr . ether saddr @approved{version} accept']
    lines += ['  tcp dport 49152 counter drop','  udp dport 1900 counter drop',' }',
              ' chain outgoing { type filter hook output priority -20; policy accept;',
              '  oifname "lo" accept',
              f'  meta skuid {media_uid} ip daddr 224.0.0.0/4 udp dport 1900 counter drop',
              f'  meta skuid {media_uid} ip6 daddr ff00::/8 udp dport 1900 counter drop']
    for version,network in ((4,'ip'),(6,'ip6')):
        # All TCP/SSDP from the media UID is gated, including a fallback server port.
        base=f'  meta skuid {media_uid} oifname "{interface}" '
        lines += [base+f'{network} daddr @destinations{version} meta l4proto tcp accept',
                  base+f'{network} daddr @destinations{version} udp sport 1900 accept']
    lines += [f'  meta skuid {media_uid} meta l4proto tcp counter drop',f'  meta skuid {media_uid} udp sport 1900 counter drop',' }','}']
    return '\n'.join(lines)+'\n'

def serialized(method):
    @functools.wraps(method)
    def locked(self,*args,**kwargs):
        with self._mutex:return method(self,*args,**kwargs)
    return locked

class Access:
    def __init__(self, context, interface='enp0s1', media_uid=None, policy='/etc/freeqnap/dlna.nft'):
        self.ctx=context;self.interface=interface;self._mutex=threading.RLock()
        self.uid=pwd.getpwnam('gerbera').pw_uid if media_uid is None else media_uid
        self.policy=Path(policy)

    def options(self, request=None):
        return {'profiles':PROFILES,'settings':self.ctx.state.setting('dlna_options',{'default_profile':'generic'}),
                'transcoding':{'mode':'direct-play','live_available':False,'reason':'Live transcoding is not configured or benchmarked on this ARM32 NAS. Convert a copy on a more capable machine for now.'},
                'folder_access':{'per_user_dlna':False,'per_device_dlna':False,'scope':'All approved DLNA players can access every published DLNA library. Use authenticated SMB shared folders for per-user restrictions.'}}

    def save_options(self, request):
        profile=request.get('default_profile')
        if profile not in PROFILES:raise ValueError('Choose a supported display profile')
        if request.get('transcoding','direct-play')!='direct-play':raise ValueError('Live transcoding is unavailable; no settings changed')
        value={'default_profile':profile,'transcoding':'direct-play'}
        self.ctx.state.set('dlna_options',value)
        return value

    def client_profile(self, request):
        profile=request.get('profile');ident=request.get('id')
        if profile not in PROFILES:raise ValueError('Choose a supported display profile')
        with self.ctx.lock(),self._mutex:
            clients=self.data()
            if ident not in clients:raise ValueError('Choose an observed player')
            clients[ident]['profile']=profile;self.ctx.state.set('dlna_clients',clients)
        return {'saved':True,'access_changed':False,'profile_is_guidance_only':True}

    def data(self):
        return self.ctx.state.setting('dlna_clients',{})

    @serialized
    def observe(self):
        clients=self.data();changed=False;now=time.time()
        for version in (4,6):
            try:
                document=json.loads(self.ctx.run('nft','-j','list','set','inet',TABLE,'seen'+str(version)))
                entries=next(item['set'].get('elem',[]) for item in document['nftables'] if 'set' in item)
            except (ValueError,KeyError,StopIteration,OSError):continue
            for item in entries:
                value=item.get('elem',item)
                concat=value.get('val',value).get('concat')
                if not isinstance(concat,list) or len(concat)!=2:continue
                try:record=endpoint(concat[0],concat[1],self.interface)
                except ValueError:continue
                old=clients.get(record['id'])
                if not old:
                    if len(clients)>=1024:continue
                    clients[record['id']]={**record,'label':'','approved':False,'first_seen':now,'last_seen':now}
                    changed=True
                elif now-old.get('last_seen',0)>60:
                    old['last_seen']=now;changed=True
        if changed:self.ctx.state.set('dlna_clients',clients)
        return clients

    def list(self, request=None):
        clients=self.observe()
        applied=self.ctx.state.setting('dlna_policy',{})
        return {'clients':sorted(clients.values(),key=lambda row:row.get('last_seen',0),reverse=True),
                'default_deny':True,'interface':self.interface,'enforcement':applied,
                'discovery':'Multicast announcements suppressed; approved players must rescan to discover the server.',
                'identity_limit':'IP/MAC device approval is not cryptographic authentication. Use a trusted LAN/VLAN or authenticated SMB/HTTPS for stronger access control.'}

    @serialized
    def apply(self):
        self.observe()
        script=render(self.data().values(),self.interface,self.uid)
        self.policy.parent.mkdir(mode=0o750,parents=True,exist_ok=True)
        temporary=self.policy.with_name(self.policy.name+'.next')
        temporary.write_text(script);temporary.chmod(0o600)
        try:
            self.ctx.run('nft','--check','-f',str(temporary))
            self.ctx.run('nft','-f',str(temporary))
            os.replace(temporary,self.policy)
            result={'applied':True,'applied_at':time.time(),'sha256':hashlib.sha256(script.encode()).hexdigest()}
            self.ctx.state.set('dlna_policy',result)
            return result
        except Exception:
            self.ctx.state.set('dlna_policy',{'applied':False,'error':'Media policy could not be enforced; server must stay stopped'})
            try:self.ctx.run('systemctl','stop','freeqnap-dlna',timeout=20)
            except Exception:pass
            raise
        finally:temporary.unlink(missing_ok=True)

    def approve(self, request):
        ident=request.get('id','')
        if not re.fullmatch('[a-f0-9]{32}',ident):raise ValueError('Select an observed client')
        if not isinstance(request.get('approved'),bool):raise ValueError('Choose approve or revoke')
        with self.ctx.lock(), self._mutex:
            clients=self.observe();record=clients.get(ident)
            if not record:raise ValueError('Client has not been observed; arbitrary address approval is not available')
            label=request.get('label',record.get('label',''))
            if not isinstance(label,str) or len(label)>80 or any(ord(c)<32 for c in label):raise ValueError('Invalid client label')
            record.update(approved=request['approved'],label=label,changed_at=time.time())
            self.ctx.state.set('dlna_clients',clients)
            applied=self.apply()
            return {'client':record,'enforcement':applied,'cached_client_media_cannot_be_retracted':True}
