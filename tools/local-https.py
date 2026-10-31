#!/usr/bin/env python3
"""Create an offline local CA and issue a LAN HTTPS bundle; never upload the CA key."""
import argparse,hashlib,ipaddress,json,os,secrets,ssl,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from freeqnap.nas.management_tls import validate
from freeqnap.state import atomic

def command(*args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=45)
    if result.returncode:raise ValueError('OpenSSL certificate operation failed; private output retained for review')
    return result.stdout

def private_directory(value):
    path=Path(value).absolute()
    if path.exists() or path.is_symlink():raise ValueError('Choose a new private output directory; never overwrite a CA or certificate')
    path.mkdir(mode=0o700,parents=True);return path

def ca_create(directory):
    root=private_directory(directory);os.umask(0o077)
    (root/'ca.cnf').write_text('[req]\ndistinguished_name=dn\nx509_extensions=ca\nprompt=no\n[dn]\nCN=FreeQNAP Local Root '+secrets.token_hex(4)+'\n[ca]\nbasicConstraints=critical,CA:TRUE,pathlen:0\nkeyUsage=critical,keyCertSign,cRLSign\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid:always\n')
    command('openssl','req','-new','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256','-pkeyopt','ec_param_enc:named_curve','-nodes','-sha256','-days','3650','-keyout',str(root/'ca.key'),'-out',str(root/'ca.crt'),'-config',str(root/'ca.cnf'))
    (root/'ca.key').chmod(0o600);certificate=(root/'ca.crt').read_text();fingerprint=hashlib.sha256(ssl.PEM_cert_to_DER_cert(certificate)).hexdigest()
    atomic(root/'public.json',{'sha256':fingerprint,'purpose':'Private FreeQNAP administration only. Retain the CA key here; install only ca.crt on client devices.'})
    print(json.dumps({'ca_created':True,'public_certificate':str(root/'ca.crt'),'sha256':fingerprint,'private_key_uploaded':False},indent=2))

def issue(ca,directory,address,networks,names):
    config=validate({'address':address,'networks':networks,'names':names});ca=Path(ca).absolute()
    for name in ('ca.key','ca.crt'):
        file=ca/name
        if file.is_symlink() or not file.is_file():raise ValueError('Original local CA files are required')
    if (ca/'ca.key').stat().st_mode&0o077:raise ValueError('CA private key permissions must be 0600')
    command('openssl','verify','-CAfile',str(ca/'ca.crt'),str(ca/'ca.crt'))
    root=private_directory(directory);os.umask(0o077)
    names='\n'.join('DNS.'+str(i+1)+'='+v for i,v in enumerate(config['names']))
    extensions='basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth\nsubjectKeyIdentifier=hash\nsubjectAltName=@alt\n'
    # A CSR has no issuer; add AKI only when signing the issued certificate.
    (root/'server.cnf').write_text('[req]\ndistinguished_name=dn\nreq_extensions=request\nprompt=no\n[dn]\nCN=FreeQNAP Local NAS\n[request]\n'+extensions+'[server]\n'+extensions+'authorityKeyIdentifier=keyid:always\n[alt]\nIP.1='+config['address']+'\n'+names+'\n')
    command('openssl','req','-new','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256','-pkeyopt','ec_param_enc:named_curve','-nodes','-sha256','-keyout',str(root/'server.key'),'-out',str(root/'server.csr'),'-config',str(root/'server.cnf'))
    command('openssl','x509','-req','-in',str(root/'server.csr'),'-CA',str(ca/'ca.crt'),'-CAkey',str(ca/'ca.key'),'-set_serial','0x'+secrets.token_hex(16),'-days','365','-sha256','-extfile',str(root/'server.cnf'),'-extensions','server','-out',str(root/'server.crt'))
    command('openssl','verify','-x509_strict','-purpose','sslserver','-CAfile',str(ca/'ca.crt'),str(root/'server.crt'))
    (root/'ca.crt').write_bytes((ca/'ca.crt').read_bytes());(root/'server.key').chmod(0o600);atomic(root/'public.json',config)
    print(json.dumps({'issued':True,'bundle':str(root),'address':config['address'],'private_ca_key_included':False},indent=2))

p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
a=s.add_parser('create-ca');a.add_argument('--directory',required=True)
a=s.add_parser('issue');a.add_argument('--ca',required=True);a.add_argument('--directory',required=True);a.add_argument('--address',required=True);a.add_argument('--network',action='append',required=True);a.add_argument('--name',action='append',default=[])
a=p.parse_args()
if a.action=='create-ca':ca_create(a.directory)
else:issue(a.ca,a.directory,a.address,a.network,a.name)
