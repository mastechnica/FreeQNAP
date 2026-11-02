"""Explicitly approved LAN UPnP renderers and short-lived original-media streams.

No AirPlay/Cast emulation, transcoding, arbitrary URLs, redirects or API-token
sharing. The optional HTTP listener serves only IP-bound expiring item tickets.
"""
import base64
import hashlib
import http.client
import ipaddress
import json
import secrets
import socket
import threading
import time
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,urljoin
from .agents import Denied
from .media_http import byte_range,content_type

OPERATIONS=frozenset(['media.players','media.players-discover','media.play','media.playback-control','media.playback-status'])
AV='urn:schemas-upnp-org:service:AVTransport:1'

def lan_ip(value):
    ip=ipaddress.ip_address(value)
    if ip.version!=4 or not ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified or str(ip)=='255.255.255.255':raise ValueError('Choose an IPv4 LAN device')
    # Restrict to RFC1918, not documentation/special-use ranges.
    if not any(ip in ipaddress.ip_network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):raise ValueError('Choose an RFC1918 LAN device')
    return str(ip)

def endpoint(url,ip):
    value=urlsplit(url)
    if value.scheme!='http' or value.username or value.password or value.fragment or value.hostname!=lan_ip(ip) or not 1<=(value.port or 80)<=65535:raise ValueError('Renderer URLs must use HTTP on the same observed LAN IP')
    if len(url)>2048 or any(ord(c)<32 for c in url):raise ValueError('Invalid renderer URL')
    return value

def xml(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():raise ValueError('Unsafe device XML')
    return ET.fromstring(data)

def exchange(url,ip,method='GET',body=None,headers=None):
    target=endpoint(url,ip);c=http.client.HTTPConnection(ip,target.port or 80,timeout=4)
    try:
        c.request(method,target.path+('?' + target.query if target.query else ''),body,headers or {})
        r=c.getresponse();data=r.read(256*1024+1)
        if r.status!=200 or len(data)>256*1024:raise ValueError('Renderer did not accept the request')
        return data
    finally:c.close()

def describe(location,ip):
    root=xml(exchange(location,ip));ns={'d':'urn:schemas-upnp-org:device-1-0'}
    for device in root.findall('.//d:device',ns):
        if device.findtext('d:deviceType','',ns)!='urn:schemas-upnp-org:device:MediaRenderer:1':continue
        for service in device.findall('d:serviceList/d:service',ns):
            if service.findtext('d:serviceType','',ns)!=AV:continue
            control=urljoin(location,service.findtext('d:controlURL','',ns));endpoint(control,ip)
            udn=device.findtext('d:UDN','',ns)
            if not udn or len(udn)>256:raise ValueError('Renderer identity unavailable')
            return {'id':hashlib.sha256((ip+'|'+udn).encode()).hexdigest()[:32],'ip':ip,'udn':udn,
                    'name':device.findtext('d:friendlyName','Unnamed player',ns)[:120],
                    'location':location,'control':control,'approved':False,'seen':time.time()}
    raise ValueError('No supported UPnP AVTransport renderer found')

def soap(player,action,values):
    envelope=ET.Element('{http://schemas.xmlsoap.org/soap/envelope/}Envelope');body=ET.SubElement(envelope,'{http://schemas.xmlsoap.org/soap/envelope/}Body');call=ET.SubElement(body,'{'+AV+'}'+action)
    for key,value in {'InstanceID':'0',**values}.items():ET.SubElement(call,key).text=str(value)
    return xml(exchange(player['control'],player['ip'],'POST',ET.tostring(envelope,encoding='utf-8',xml_declaration=True),{'Content-Type':'text/xml; charset="utf-8"','SOAPAction':'"'+AV+'#'+action+'"'}))

class MediaServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,*args):self.capacity=threading.BoundedSemaphore(4);super().__init__(*args)
    def process_request(self,request,address):
        if not self.capacity.acquire(False):request.close();return
        request.settimeout(30)
        try:super().process_request(request,address)
        except Exception:self.capacity.release();raise
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.capacity.release()

class Players:
    def __init__(self,state,broker,agents):self.state=state;self.broker=broker;self.agents=agents;self.listener=None;self.lock=threading.RLock();self.start_error=None
    def resume(self):
        try:self.start()
        except (OSError,ValueError):self.start_error='Media listener unavailable; check its NAS address and port. Playback remains blocked.'
    def settings(self):return self.state.setting('player-settings',{'enabled':False,'address':None,'port':8091})
    def listing(self,request=None):
        return {'settings':self.settings(),'listener_running':self.listener is not None,'listener_error':self.start_error,'players':[{k:v for k,v in p.items() if k not in ('control','location')} for p in self.state.setting('players',{}).values()],
                'protocol':'UPnP AVTransport; original media only','approval':'Explicit owner approval required. Network identity is not cryptographic authentication.'}
    def configure(self,request):
        enabled=request.get('enabled') is True
        if enabled:
            address=lan_ip(request.get('address'));port=request.get('port',8091)
            if type(port)!=int or not 1024<=port<=65535:raise ValueError('Choose an unprivileged media port')
            # Verify an address actually assigned to this NAS, never an arbitrary advertised origin.
            with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:probe.bind((address,0))
            settings={'enabled':True,'address':address,'port':port}
        else:settings={'enabled':False,'address':None,'port':8091}
        with self.lock:
            if self.listener:self.listener.shutdown();self.listener.server_close();self.listener=None
            if enabled:
                try:self.start(settings)
                except OSError:
                    self.start_error='Media listener unavailable; check its NAS address and port. Playback remains blocked.'
                    raise ValueError(self.start_error) from None
            self.state.set('player-settings',settings)
        return self.listing()
    def start(self,settings=None):
        settings=settings or self.settings()
        if not settings['enabled'] or self.listener:return
        owner=self
        class Stream(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_HEAD(self):self.do_GET()
            def do_GET(self):
                try:
                    ticket=urlsplit(self.path).path.removeprefix('/stream/')
                    if self.path!='/stream/'+ticket or len(ticket)!=43:raise Denied('Unknown stream')
                    record=owner.stream(ticket,self.client_address[0])
                    first=owner.broker.request('files.read',{**record['source'],'offset':0,'count':1})
                    if first['etag']!=record['etag']:raise Denied('Media changed')
                    total=first['total_bytes'];start,end,partial=byte_range(self.headers.get('Range'),total)
                    self.send_response(206 if partial else 200);self.send_header('Content-Type',content_type(record['path']));self.send_header('Content-Length',str(max(0,end-start+1)));self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
                    if partial:self.send_header('Content-Range',f'bytes {start}-{end}/{total}')
                    self.end_headers();self.stream_started=True
                    if self.command=='HEAD':return
                    while start<=end:
                        owner.stream(ticket,self.client_address[0])
                        chunk=owner.broker.request('files.read',{**record['source'],'offset':start,'count':min(512*1024,end-start+1)})
                        if chunk['etag']!=record['etag']:raise Denied('Media changed')
                        data=base64.b64decode(chunk['data_base64'],validate=True)
                        if not data:raise ValueError('Short media read')
                        self.wfile.write(data);start+=len(data)
                except Exception:
                    # Never expose stream records or tokens in errors/logs.
                    self.close_connection=True
                    if not getattr(self,'stream_started',False):
                        try:self.send_error(404)
                        except OSError:pass
        server=MediaServer((settings['address'],settings['port']),Stream);self.listener=server;self.start_error=None
        threading.Thread(target=server.serve_forever,daemon=True).start()
    def discover(self,request):
        with self.lock:return self._discover(request)
    def _discover(self,request):
        settings=self.settings()
        if not settings['enabled']:raise ValueError('Enable network playback in AI agent access first')
        locations={}
        # Optional manual description URL still receives identical SSRF/identity checks.
        if request.get('location'):
            url=request['location'];ip=lan_ip(urlsplit(url).hostname);endpoint(url,ip);locations[(ip,url)]=True
        else:
            message=b'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\nMX: 2\r\nST: urn:schemas-upnp-org:device:MediaRenderer:1\r\n\r\n'
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM,socket.IPPROTO_UDP) as sock:
                sock.bind((settings['address'],0));sock.setsockopt(socket.IPPROTO_IP,socket.IP_MULTICAST_IF,socket.inet_aton(settings['address']));sock.settimeout(.25);sock.sendto(message,('239.255.255.250',1900));deadline=time.monotonic()+3
                while time.monotonic()<deadline and len(locations)<16:
                    try:data,peer=sock.recvfrom(8192)
                    except socket.timeout:continue
                    try:
                        ip=lan_ip(peer[0]);lines=data.decode('iso-8859-1').split('\r\n');headers=dict(line.split(':',1) for line in lines[1:] if ':' in line);headers={k.lower().strip():v.strip() for k,v in headers.items()};url=headers.get('location','');endpoint(url,ip);locations[(ip,url)]=True
                    except ValueError:continue
        players=self.state.setting('players',{});errors=0
        for ip,url in list(locations)[:16]:
            try:
                candidate=describe(url,ip);old=players.get(candidate['id'])
                # Endpoint changes invalidate approval even if a UDN is reused.
                candidate['approved']=bool(old and old.get('approved') and old.get('location')==candidate['location'] and old.get('control')==candidate['control']);players[candidate['id']]=candidate
            except (ValueError,OSError,ET.ParseError,http.client.HTTPException):errors+=1
        if len(players)>128:raise ValueError('Player registry full; remove old devices before discovery')
        self.state.set('players',players)
        return {**self.listing(),'unavailable_descriptions':errors}
    def approve(self,request):
        with self.lock:return self._approve(request)
    def _approve(self,request):
        players=self.state.setting('players',{});player=players.get(request.get('id'))
        if not player:raise ValueError('Discover a player first')
        player['approved']=request.get('approved') is True;self.state.set('players',players);return self.listing()
    def player(self,ident):
        player=self.state.setting('players',{}).get(ident)
        if self.start_error or not self.settings()['enabled'] or not player or not player['approved']:raise Denied('Player is not approved for playback')
        current=describe(player['location'],player['ip'])
        if any(current[k]!=player[k] for k in ('id','udn','control')):raise Denied('Player identity changed; rediscover and approve it')
        return player
    def stream(self,ticket,ip):
        record=self.state.setting('player-ticket:'+hashlib.sha256(ticket.encode()).hexdigest())
        if not self.settings()['enabled'] or not record or record['expires']<=time.time() or record['ip']!=ip:raise Denied('Stream not authorized')
        player=self.state.setting('players',{}).get(record['player'])
        if not player or not player.get('approved'):raise Denied('Player access revoked')
        with self.state.connect() as db:row=db.execute('SELECT revoked,expires FROM agent_tokens WHERE id=?',(record['principal'],)).fetchone()
        if not row or row['revoked'] or row['expires']<=time.time():raise Denied('Agent access revoked')
        return record
    def invoke(self,operation,request,principal):
        if operation=='media.players':return self.listing()
        if operation=='media.players-discover':return self.discover(request)
        player=self.player(request.get('player'))
        if operation=='media.play':
            library=request.get('library');offset=request.get('offset',0)
            if type(offset)!=int or not 0<=offset<=100000:raise ValueError('Choose a catalog page')
            catalog=self.broker.request('media.catalog',{'library':library,'offset':offset})
            item=next((e for e in catalog['entries'] if e['id']==request.get('id')),None)
            if not item:raise ValueError('Choose an indexed item on the specified catalog page')
            config=self.broker.request('nas.status',{});lib=next((l for l in config['libraries'] if l['name']==library),None)
            if not lib:raise ValueError('Library unavailable')
            source={'share':lib['share'],'path':item['path']};info=self.broker.request('files.read',{**source,'offset':0,'count':1});ticket=secrets.token_urlsafe(32);settings=self.settings();now=time.time()
            record={'source':source,'path':item['path'],'etag':info['etag'],'expires':now+6*3600,'principal':principal['id'],'ip':player['ip'],'player':player['id']}
            # Bound persistent tickets and retain only their hashes.
            with self.state.connect() as db:
                rows=db.execute("SELECT key,value FROM settings WHERE key LIKE 'player-ticket:%'").fetchall();active=0
                for row in rows:
                    if json.loads(row['value'])['expires']<=now:db.execute('DELETE FROM settings WHERE key=?',(row['key'],))
                    else:active+=1
                if active>=64:raise ValueError('Too many active streams; wait for expiry')
            key='player-ticket:'+hashlib.sha256(ticket.encode()).hexdigest();self.state.set(key,record)
            url=f"http://{settings['address']}:{settings['port']}/stream/{ticket}"
            try:soap(player,'SetAVTransportURI',{'CurrentURI':url,'CurrentURIMetaData':''});soap(player,'Play',{'Speed':'1'})
            except Exception:
                with self.state.connect() as db:db.execute('DELETE FROM settings WHERE key=?',(key,))
                raise
            return {'sent':True,'player':player['id'],'media':item['id'],'stream_expires':record['expires'],'playback_verified':False}
        if operation=='media.playback-status':
            result=soap(player,'GetTransportInfo',{});allowed={'CurrentTransportState','CurrentTransportStatus','CurrentSpeed'}
            return {node.tag.split('}')[-1]:node.text for node in result.iter() if node.tag.split('}')[-1] in allowed}
        if operation=='media.playback-control':
            command=request.get('command')
            if command not in ('play','pause','stop','seek','forward','rewind'):raise ValueError('Choose play, pause, stop or seek')
            values={'Speed':'1'} if command=='play' else {}
            if command in ('forward','rewind'):
                seconds=request.get('seconds',30)
                if type(seconds)!=int or not 1<=seconds<=3600:raise ValueError('Choose a skip of 1–3600 seconds')
                info=soap(player,'GetPositionInfo',{});value=next((n.text for n in info.iter() if n.tag.split('}')[-1]=='RelTime'),'')
                import re
                if not re.fullmatch(r'\d{1,3}:[0-5]\d:[0-5]\d',value or ''):raise ValueError('This player does not report its playhead; use an absolute seek')
                h,m,s=map(int,value.split(':'));target=max(0,h*3600+m*60+s+(seconds if command=='forward' else -seconds))
                request={**request,'position':f'{target//3600:02d}:{target//60%60:02d}:{target%60:02d}'};command='seek'
            if command=='seek':
                position=request.get('position')
                import re
                if not isinstance(position,str) or not re.fullmatch(r'\d{1,3}:[0-5]\d:[0-5]\d',position):raise ValueError('Use HHH:MM:SS')
                values={'Unit':'REL_TIME','Target':position}
            soap(player,command.title(),values)
            return {'sent':True,'playback_verified':False}
        raise ValueError('Unsupported player operation')
