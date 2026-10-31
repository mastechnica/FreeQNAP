"""Local OpenVPN CA with explicit client issuance/revocation. Never exported CA key."""
import ipaddress
from pathlib import Path
from .common import name, run
from .vpn_runtime import write

def ensure(root):
    root=Path(root);root.mkdir(mode=0o700,parents=True,exist_ok=True)
    if not (root/'openssl.cnf').exists():
        (root/'newcerts').mkdir(mode=0o700,exist_ok=True);write(root/'index.txt','');write(root/'serial','1000\n');write(root/'crlnumber','1000\n')
        write(root/'openssl.cnf',f'''[ca]
default_ca=local
[local]
dir={root}
database=$dir/index.txt
new_certs_dir=$dir/newcerts
certificate=$dir/ca.crt
private_key=$dir/ca.key
serial=$dir/serial
crlnumber=$dir/crlnumber
default_md=sha256
default_days=365
default_crl_days=365
policy=names
unique_subject=no
[names]
commonName=supplied
[server]
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyAgreement
extendedKeyUsage=serverAuth
[client]
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyAgreement
extendedKeyUsage=clientAuth
''')
    if not (root/'ca.crt').exists():
        run('openssl','ecparam','-name','prime256v1','-genkey','-noout','-out',str(root/'ca.key'))
        run('openssl','req','-new','-x509','-sha256','-days','3650','-key',str(root/'ca.key'),'-out',str(root/'ca.crt'),'-subj','/CN=FreeQNAP local VPN CA','-addext','basicConstraints=critical,CA:TRUE','-addext','keyUsage=critical,keyCertSign,cRLSign')
    if not (root/'server.crt').exists():issue(root,'server',True)
    if not (root/'tls-crypt.key').exists():run('openvpn','--genkey','secret',str(root/'tls-crypt.key'))
    if not (root/'crl.pem').exists():crl(root)
    for path in root.iterdir():
        if path.is_file():path.chmod(0o600)

def issue(root,ident,server=False):
    root=Path(root);ident=name(ident)
    if ident=='server' and not server:raise ValueError('Reserved peer name')
    if (root/(ident+'.crt')).exists():raise ValueError('Peer certificate already exists; revoke it or choose a new name')
    run('openssl','ecparam','-name','prime256v1','-genkey','-noout','-out',str(root/(ident+'.key')))
    run('openssl','req','-new','-key',str(root/(ident+'.key')),'-out',str(root/(ident+'.csr')),'-subj','/CN='+ident)
    run('openssl','ca','-batch','-notext','-config',str(root/'openssl.cnf'),'-extensions','server' if server else 'client','-in',str(root/(ident+'.csr')),'-out',str(root/(ident+'.crt')))
    for ext in ('key','csr','crt'):(root/(ident+'.'+ext)).chmod(0o600)

def crl(root):run('openssl','ca','-batch','-config',str(root/'openssl.cnf'),'-gencrl','-out',str(root/'crl.pem'))
def revoke(root,ident):
    root=Path(root);ident=name(ident)
    if ident=='server' or not (root/(ident+'.crt')).exists():raise ValueError('Unknown client certificate')
    run('openssl','ca','-batch','-config',str(root/'openssl.cnf'),'-revoke',str(root/(ident+'.crt')));crl(root)

def server_config(s,root):
    net=ipaddress.ip_network(s['subnet']);root=Path(root)
    lines=['port '+str(s['port']),'proto udp','dev fqsv0','dev-type tun','topology subnet','server '+str(net.network_address)+' '+str(net.netmask),'verify-client-cert require','remote-cert-tls client','tls-version-min 1.2','data-ciphers AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305','allow-compression no','dh none','keepalive 10 60','persist-key','persist-tun','script-security 1','mark 51820','verb 2','status /run/freeqnap/openvpn-server.status 5','status-version 3']
    for option,filename in (('ca','ca.crt'),('cert','server.crt'),('key','server.key'),('crl-verify','crl.pem'),('tls-crypt','tls-crypt.key')):lines+=[option+' '+str(root/filename)]
    for lan in s['lan_networks']:
        n=ipaddress.ip_network(lan);lines+=['push "route '+str(n.network_address)+' '+str(n.netmask)+'"']
    if s['gateway']:lines+=['push "redirect-gateway def1"','push "block-ipv6"']
    return '\n'.join(lines)+'\n'

def export(s,root,ident):
    root=Path(root);ident=name(ident)
    lines=['client','dev tun','proto udp','remote '+s['public_endpoint']+' '+str(s['port']),'nobind','remote-cert-tls server','verify-x509-name server name','tls-version-min 1.2','data-ciphers AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305','allow-compression no','auth-nocache','verb 2']
    for option,filename in (('ca','ca.crt'),('cert',ident+'.crt'),('key',ident+'.key'),('tls-crypt','tls-crypt.key')):lines+=['<'+option+'>',(root/filename).read_text().strip(),'</'+option+'>']
    return '\n'.join(lines)+'\n'
