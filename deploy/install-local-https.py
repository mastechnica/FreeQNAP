#!/usr/bin/env python3
"""Install one verified local TLS bundle; stock nginx/HTTP stays disabled."""
import argparse,hashlib,json,os,pathlib,shutil,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from freeqnap.nas.management_tls import validate,nginx,origins,ManagementTLS
from freeqnap.state import atomic

def run(*args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=45)
    if p.returncode:raise ValueError(Path(args[0]).name+' verification failed; no automatic activation retry')
    return p.stdout

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--verify-only',action='store_true');a=p.parse_args()
if os.geteuid()!=0 or Path('/proc/device-tree/compatible').read_bytes().split(b'\0')[0]!=b'qnap,ts-431xeu':raise SystemExit('Root on the selected supported NAS required')
bundle=a.bundle.resolve();config=validate(json.loads((bundle/'public.json').read_text()))
for name in ('ca.crt','server.crt','server.key','public.json'):
    source=bundle/name
    if source.is_symlink() or not source.is_file() or source.stat().st_size>32768:raise ValueError('Invalid bounded TLS bundle')
if (bundle/'server.key').stat().st_mode&0o077:raise ValueError('Server key must be private')
if (bundle/'ca.key').exists():raise ValueError('Never put the CA private key on the NAS')
run('openssl','verify','-x509_strict','-purpose','sslserver','-verify_ip',config['address'],'-CAfile',str(bundle/'ca.crt'),str(bundle/'server.crt'))
run('openssl','x509','-in',str(bundle/'server.crt'),'-noout','-checkip',config['address'])
cert=run('openssl','x509','-in',str(bundle/'server.crt'),'-pubkey','-noout')
key=run('openssl','pkey','-in',str(bundle/'server.key'),'-pubout')
if cert!=key:raise ValueError('TLS key does not match server certificate')
addresses=json.loads(run('ip','-j','-4','addr','show'))
if not any(addr.get('local')==config['address'] for interface in addresses if interface.get('ifname') in ('enp0s1','enp0s3') for addr in interface.get('addr_info',[])):raise ValueError('TLS address is not currently assigned to this NAS')
if not shutil.which('nginx'):raise ValueError('Install signed Debian nginx first with its stock service disabled')
print(json.dumps({'bundle_verified':True,'address':config['address'],'allowed_networks':config['networks'],'origin_allowlist':origins(config),'ca_private_key_present':False}))
if a.verify_only:raise SystemExit(0)
target=Path('/etc/freeqnap-https')
if target.exists():raise ValueError('TLS is already installed; stage and review certificate rotation separately')
# Preserve the existing loopback administration and all service isolation.
run('systemctl','mask','--now','nginx.service')
if subprocess.run(['getent','passwd','freeqnap-https'],capture_output=True).returncode:run('useradd','--system','--user-group','--home-dir','/nonexistent','--no-create-home','--shell','/usr/sbin/nologin','freeqnap-https')
target.mkdir(mode=0o750)
for name in ('ca.crt','server.crt','server.key','public.json'):
    shutil.copyfile(bundle/name,target/name);(target/name).chmod(0o600 if name=='server.key' else 0o644)
(target/'nginx.conf').write_text(nginx(config));(target/'nginx.conf').chmod(0o644)
verification_runtime=bundle/'syntax-runtime';verification_runtime.mkdir(mode=0o700)
verification=bundle/'nginx-verify.conf';verification.write_text(nginx(config).replace('/run/credentials/freeqnap-https.service',str(target)).replace('/run/freeqnap-https/',str(verification_runtime)+'/'));verification.chmod(0o600)
run('nginx','-t','-c',str(verification))
service=Path(__file__).resolve().parent/'freeqnap-https.service';shutil.copyfile(service,'/etc/systemd/system/freeqnap-https.service')
drop=Path('/etc/systemd/system/freeqnap-console.service.d');drop.mkdir(mode=0o755,exist_ok=True)
args=' '.join('--origin '+v for v in origins(config))
(drop/'https-origin.conf').write_text('[Service]\nExecStart=\nExecStart=/usr/bin/python3 -B -m freeqnap.server --snapshot /run/freeqnap/inventory.json '+args+'\n')
run('systemctl','daemon-reload');run('systemd-analyze','verify','/etc/systemd/system/freeqnap-https.service')
run('systemctl','restart','freeqnap-console.service');run('systemctl','enable','--now','freeqnap-https.service')
probe=ManagementTLS(None)
for attempt in range(20):
    if probe.probe(config['address']):break
    time.sleep(.5)
else:raise ValueError('Activation did not pass a certificate-verified response check. Keep the SSH tunnel and inspect the retained service configuration.')
print(json.dumps({'activated':origins(config),'browser_ca_trust_requires_owner_install':True,'ssh_tunnel_preserved':True}))
