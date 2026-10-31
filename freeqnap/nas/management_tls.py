"""Fixed local HTTPS configuration and public certificate status; no key export."""
import hashlib,http.client,ipaddress,json,re,ssl,time
from pathlib import Path

PRIVATE=[ipaddress.ip_network(v) for v in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')]

def validate(value):
    if not isinstance(value,dict) or set(value)!={'address','networks','names'}:raise ValueError('Choose an exact private IPv4, client networks and optional local names')
    if not isinstance(value['address'],str):raise ValueError('Use one private IPv4 address')
    address=ipaddress.IPv4Address(value['address'])
    if not any(address in n for n in PRIVATE):raise ValueError('HTTPS must bind one RFC1918 LAN address')
    networks=value['networks'];names=value['names']
    if not isinstance(networks,list) or not 1<=len(networks)<=8 or not isinstance(names,list) or len(names)>4:raise ValueError('Choose 1–8 local client networks and at most four .local names')
    if any(not isinstance(v,str) for v in networks):raise ValueError('Use explicit local network CIDRs')
    networks=[ipaddress.IPv4Network(v,strict=True) for v in networks]
    if any(not any(n.subnet_of(p) for p in PRIVATE) for n in networks) or not any(address in n for n in networks):raise ValueError('Only explicit RFC1918 client networks including the bound address are allowed')
    if any(not isinstance(v,str) or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.local',v) for v in names):raise ValueError('Use a single DNS label followed by .local')
    if len(set(names))!=len(names):raise ValueError('Duplicate local name')
    return {'address':str(address),'networks':sorted({str(n) for n in networks}),'names':names}

def origins(value):
    c=validate(value);return ['https://'+v for v in [c['address'],*c['names']]]

def nginx(value):
    c=validate(value);hosts=[c['address'],*c['names']]
    host_map='\n'.join('        '+json.dumps(h)+' 1;' for h in hosts)
    allow='\n'.join('        allow '+n+';' for n in c['networks'])
    return f'''worker_processes 2;
pid /run/freeqnap-https/nginx.pid;
error_log stderr warn;
events {{ worker_connections 128; }}
http {{
    access_log off;
    server_tokens off;
    client_max_body_size 2m;
    client_body_timeout 30s;
    keepalive_timeout 15s;
    client_body_temp_path /run/freeqnap-https/body;
    proxy_temp_path /run/freeqnap-https/proxy;
    map $host $freeqnap_allowed_host {{
        default 0;
{host_map}
    }}
    server {{
        listen {c['address']}:443 ssl;
        server_name {' '.join(hosts)};
        if ($freeqnap_allowed_host = 0) {{ return 444; }}
{allow}
        deny all;
        ssl_certificate /run/credentials/freeqnap-https.service/server.crt;
        ssl_certificate_key /run/credentials/freeqnap-https.service/server.key;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305;
        ssl_session_cache shared:FreeQNAP:2m;
        ssl_session_tickets off;
        location / {{
            proxy_pass http://127.0.0.1:8080;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header Connection close;
            proxy_set_header X-Forwarded-Proto https;
            proxy_set_header X-Forwarded-User "";
            proxy_set_header X-User "";
            proxy_set_header Forwarded "";
            proxy_buffering off;
            proxy_request_buffering off;
            proxy_read_timeout 610s;
            proxy_send_timeout 60s;
            proxy_max_temp_file_size 0;
        }}
    }}
}}
'''

class ManagementTLS:
    def __init__(self,context,directory='/etc/freeqnap-https'):self.ctx=context;self.directory=Path(directory)
    def certificate(self,file):
        path=self.directory/file
        if path.is_symlink() or not path.is_file() or path.stat().st_size>16384:raise ValueError('Managed public certificate missing or changed')
        pem=path.read_text();der=ssl.PEM_cert_to_DER_cert(pem)
        end=self.ctx.run('openssl','x509','-in',str(path),'-noout','-enddate').strip()
        if not end.startswith('notAfter='):raise ValueError('Certificate expiration unavailable')
        expires=ssl.cert_time_to_seconds(end.split('=',1)[1])
        return {'sha256':hashlib.sha256(der).hexdigest(),'expires_at':expires,'days_remaining':int((expires-time.time())/86400),'pem':pem}
    def probe(self,address):
        connection=None
        try:
            context=ssl.create_default_context(cafile=str(self.directory/'ca.crt'))
            connection=http.client.HTTPSConnection(address,443,context=context,timeout=2)
            connection.request('GET','/api/session');response=connection.getresponse();data=response.read(4096)
            return response.status==200 and json.loads(data).get('demo') is False
        except (OSError,ValueError,http.client.HTTPException):return False
        finally:
            if connection:connection.close()
    def status(self,request=None):
        path=self.directory/'public.json'
        if not path.exists():return {'configured':False,'browser_trust_verified':False}
        try:
            if path.is_symlink() or path.stat().st_size>8192:raise ValueError('Invalid HTTPS configuration')
            config=validate(json.loads(path.read_text()));cert=self.certificate('server.crt');ca=self.certificate('ca.crt')
            active=self.ctx.run('systemctl','show','freeqnap-https.service','--property=ActiveState','--value').strip()
            verified=self.probe(config['address']) if active=='active' else False
            return {'configured':True,'available':verified,'endpoint_verified':verified,'configuration':config,'urls':origins(config),'service':active,'certificate':{k:v for k,v in cert.items() if k!='pem'},'ca':{k:v for k,v in ca.items() if k!='pem'},'browser_trust_verified':False,'ssh_tunnel_fallback':True}
        except (ValueError,OSError) as error:return {'configured':True,'available':False,'error':str(error),'browser_trust_verified':False}
    def public_ca(self,request=None):
        certificate=self.certificate('ca.crt')
        return {'filename':'FreeQNAP-Local-Root-CA.crt','certificate_pem':certificate['pem'],'sha256':certificate['sha256'],'private_key_included':False}
