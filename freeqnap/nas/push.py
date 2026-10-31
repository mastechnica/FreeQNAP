"""Web Push encryption/signing with fixed provider hosts and public-address pinning."""
import base64,http.client,ipaddress,json,os,re,socket,ssl,time
from pathlib import Path
from urllib.parse import urlsplit

def decode(value,size):
    if not isinstance(value,str) or not re.fullmatch('[A-Za-z0-9_-]+={0,2}',value):raise ValueError('Invalid browser push key')
    data=base64.urlsafe_b64decode(value+'='*((-len(value))%4))
    if len(data)!=size:raise ValueError('Invalid browser push key size')
    return data

def endpoint(value):
    if not isinstance(value,str) or len(value)>8192 or any(ord(c)<33 for c in value):raise ValueError('Invalid browser push endpoint')
    u=urlsplit(value)
    if u.scheme!='https' or u.username or u.password or u.fragment or u.port not in (None,443) or not u.path or u.path=='/':raise ValueError('Use the browser-generated HTTPS push endpoint')
    host=u.hostname or ''
    if host not in ('fcm.googleapis.com','updates.push.services.mozilla.com','web.push.apple.com') and not re.fullmatch(r'[a-z0-9-]+\.notify\.windows\.com',host):raise ValueError('Push service is not in the reviewed provider allowlist')
    return u

def subscription(value):
    if not isinstance(value,dict) or set(value)-{'endpoint','keys','expirationTime'} or not isinstance(value.get('keys'),dict) or set(value.get('keys',{}))!={'p256dh','auth'}:raise ValueError('A browser-generated push subscription is required')
    endpoint(value.get('endpoint'));public=decode(value['keys']['p256dh'],65);decode(value['keys']['auth'],16)
    if public[0]!=4:raise ValueError('Push key must be an uncompressed P-256 point')
    from cryptography.hazmat.primitives.asymmetric import ec
    ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),public)
    return {'endpoint':value['endpoint'],'keys':dict(value['keys'])}

def vapid_key(directory):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    directory=Path(directory);directory.mkdir(mode=0o700,exist_ok=True);file=directory/'notifications-vapid.pem'
    if not file.exists():
        key=ec.generate_private_key(ec.SECP256R1());data=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
        fd=os.open(file,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as out:out.write(data);out.flush();os.fsync(out.fileno())
        fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
    if file.is_symlink() or not file.is_file() or file.stat().st_mode&0o077 or file.stat().st_size>4096:raise ValueError('Invalid private VAPID key')
    key=serialization.load_pem_private_key(file.read_bytes(),None)
    if not isinstance(key,ec.EllipticCurvePrivateKey) or not isinstance(key.curve,ec.SECP256R1):raise ValueError('VAPID requires P-256')
    public=key.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
    return file,base64.urlsafe_b64encode(public).rstrip(b'=').decode()

def payload(key,sub,subject,message,now=None):
    import http_ece
    from py_vapid import Vapid02
    from cryptography.hazmat.primitives.asymmetric import ec
    s=subscription(sub);u=endpoint(s['endpoint']);now=time.time() if now is None else now
    raw=json.dumps(message,separators=(',',':')).encode()
    if len(raw)>2048:raise ValueError('Push message is too large')
    encrypted=http_ece.encrypt(raw,private_key=ec.generate_private_key(ec.SECP256R1()),dh=decode(s['keys']['p256dh'],65),auth_secret=decode(s['keys']['auth'],16),version='aes128gcm')
    headers=Vapid02.from_file(str(key)).sign({'sub':subject,'aud':u.scheme+'://'+u.hostname,'exp':int(now)+12*3600});headers.update({'Content-Encoding':'aes128gcm','Content-Type':'application/octet-stream','TTL':'3600','Urgency':'normal'})
    return encrypted,headers

class PublicHTTPS(http.client.HTTPSConnection):
    def connect(self):
        # Resolve once, reject every non-public result, and connect to the checked IP.
        rows=socket.getaddrinfo(self.host,self.port,type=socket.SOCK_STREAM);addresses=[]
        for row in rows:
            ip=ipaddress.ip_address(row[4][0])
            if not ip.is_global or ip.is_multicast or ip.is_loopback:raise ValueError('Push provider resolved to a non-public address')
            if str(ip) not in addresses:addresses.append(str(ip))
        error=None
        for address in addresses[:3]:
            raw=None
            try:
                raw=socket.create_connection((address,self.port),self.timeout);self.sock=self._context.wrap_socket(raw,server_hostname=self.host);return
            except OSError as caught:
                if raw:raw.close()
                error=caught
        raise OSError('Push provider connection unavailable') from error

def send(key,sub,subject,message):
    u=endpoint(sub['endpoint']);body,headers=payload(key,sub,subject,message);context=ssl.create_default_context();context.verify_flags|=ssl.VERIFY_X509_STRICT
    c=PublicHTTPS(u.hostname,443,timeout=5,context=context)
    try:
        c.request('POST',u.path+('?' +u.query if u.query else ''),body,headers);r=c.getresponse();r.read(4096)
        if r.status in (404,410):return 'expired'
        if not 200<=r.status<300:raise ValueError('Push relay did not accept the request')
        return 'relay-accepted'
    finally:c.close()
