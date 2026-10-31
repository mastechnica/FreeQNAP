#!/usr/bin/env python3
"""Isolated network-namespace TLS, login and access-denial fixture; no real accounts."""
import argparse,http.client,json,os,pathlib,secrets,shutil,socket,ssl,subprocess,sys,tempfile,threading,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--confirm-isolated-fixture',action='store_true',required=True);p.add_argument('--inside',action='store_true');a=p.parse_args()
if os.geteuid()!=0 or sys.platform!='linux':raise SystemExit('Explicit Linux root fixture required')
if not a.inside:
    result=subprocess.run(['unshare','--net','--',sys.executable,'-B',__file__,'--confirm-isolated-fixture','--inside']);raise SystemExit(result.returncode)
from freeqnap.nas.management_tls import nginx
from freeqnap import auth
from freeqnap.state import State
from freeqnap.server import handler,NASHTTPServer

def run(*args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=45)
    if p.returncode:raise ValueError(Path(args[0]).name+' failed in isolated HTTPS test')
    return p.stdout

account=__import__('pwd').getpwnam('freeqnap-https');www=account.pw_gid;base=Path('/run/freeqnap-https-validation');base.mkdir(mode=0o750,exist_ok=True);os.chown(base,0,www);root=base/('https-'+secrets.token_hex(8));root.mkdir(mode=0o750);os.chown(root,0,www)
child=None;server=None;report={}
try:
 run('ip','link','set','lo','up');run('ip','addr','add','192.168.77.2/32','dev','lo')
 tool=Path(__file__).resolve().parent/'local-https.py'
 run(sys.executable,str(tool),'create-ca','--directory',str(root/'ca'))
 run(sys.executable,str(tool),'issue','--ca',str(root/'ca'),'--directory',str(root/'tls'),'--address','192.168.77.2','--network','192.168.77.0/24')
 runtime=root/'runtime';runtime.mkdir(mode=0o750);os.chown(runtime,account.pw_uid,www)
 for folder in ('body','proxy'):
  path=runtime/folder;path.mkdir(mode=0o700);os.chown(path,account.pw_uid,www)
 os.chown(root/'tls',0,www);(root/'tls').chmod(0o750);os.chown(root/'tls/server.key',0,www);(root/'tls/server.key').chmod(0o640);(root/'tls/server.crt').chmod(0o644)
 config=nginx({'address':'192.168.77.2','networks':['192.168.77.0/24'],'names':[]}).replace('/run/credentials/freeqnap-https.service',str(root/'tls')).replace('192.168.77.2:443','192.168.77.2:18443').replace('proxy_set_header Host $host','proxy_set_header Host $http_host').replace('/run/freeqnap-https/',str(runtime)+'/').replace('127.0.0.1:8080','127.0.0.1:8181')
 (root/'nginx.conf').write_text(config);run('runuser','-u','freeqnap-https','--','nginx','-t','-c',str(root/'nginx.conf'))
 state=State(root/'state');password=secrets.token_urlsafe(32);state.set('administrator',auth.password_hash(password))
 class FakeNAS:
  def request(self,action,payload=None):
   if action=='nas.status':return {'fixture':True}
   raise ValueError('No hardware operations in TLS fixture')
 server=NASHTTPServer(('127.0.0.1',8181),handler(state,root/'backups',broker=FakeNAS(),origins=['https://192.168.77.2:18443']));server.auth_lock=threading.Lock();server.login_attempts=[];threading.Thread(target=server.serve_forever,daemon=True).start()
 log=(root/'nginx.log').open('wb');child=subprocess.Popen(['runuser','-u','freeqnap-https','--','nginx','-c',str(root/'nginx.conf'),'-g','daemon off;'],stdout=log,stderr=log);log.close()
 ctx=ssl.create_default_context(cafile=str(root/'ca/ca.crt'))
 for _ in range(40):
  try:
   with socket.create_connection(('192.168.77.2',18443),.2):break
  except OSError:time.sleep(.1)
 else:raise ValueError('Isolated HTTPS listener unavailable')
 def request(path,body=None,headers=None,source=None,context=ctx):
  connection=http.client.HTTPSConnection('192.168.77.2',18443,context=context,timeout=10,source_address=source);h={'Origin':'https://192.168.77.2:18443','Content-Type':'application/json'};h.update(headers or {});connection.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,h);response=connection.getresponse();result=(response.status,dict(response.getheaders()),response.read());connection.close();return result
 assert request('/api/session')[0]==200
 for version in (ssl.TLSVersion.TLSv1_2,ssl.TLSVersion.TLSv1_3):
  c=ssl.create_default_context(cafile=str(root/'ca/ca.crt'));c.minimum_version=c.maximum_version=version;assert request('/api/session',context=c)[0]==200
 try:request('/api/session',context=ssl.create_default_context())
 except ssl.SSLCertVerificationError:pass
 else:raise AssertionError('Untrusted certificate was accepted')
 try:request('/api/session',headers={'Host':'attacker.local'})
 except http.client.RemoteDisconnected:pass
 else:raise AssertionError('Unexpected Host reached upstream')
 assert request('/api/session',source=('127.0.0.1',0))[0]==403
 assert request('/api/nas/status',headers={'X-User':'admin','X-Forwarded-User':'admin'})[0]==401
 assert request('/api/login',{'password':password},headers={'Origin':'https://attacker.local'})[0]==403
 code,headers,body=request('/api/login',{'password':password});assert code==200;cookie=headers['Set-Cookie'];assert all(v in cookie for v in ('Secure','HttpOnly','SameSite=Strict'));cookie=cookie.split(';')[0];csrf=json.loads(body)['csrf']
 assert request('/api/nas/status',headers={'Cookie':cookie})[0]==200
 assert request('/api/nas/anything',{},headers={'Cookie':cookie})[0]==403
 assert request('/api/logout',{},headers={'Cookie':cookie,'X-CSRF-Token':csrf})[0]==200
 assert request('/api/nas/status',headers={'Cookie':cookie})[0]==401
 report={'isolated_namespace':True,'tls12_and_tls13':True,'untrusted_ca_rejected':True,'unknown_host_rejected':True,'unapproved_client_network_denied':True,'forwarded_identity_not_trusted':True,'wrong_origin_and_missing_csrf_denied':True,'secure_cookie_login_and_logout':True,'real_nas_accounts_used':False,'actual_browser_trust_accepted':False}
finally:
 if child:child.terminate();child.wait(timeout=15)
 if server:server.shutdown();server.server_close()
 if report:shutil.rmtree(root)
if report:print(json.dumps(report,indent=2))
