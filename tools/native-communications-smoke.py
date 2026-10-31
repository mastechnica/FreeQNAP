#!/usr/bin/env python3
"""Isolated TLS SMTP/DDNS fixtures. Never contacts an owner mailbox or DNS provider."""
import argparse,base64,grp,http.server,json,os,secrets,shutil,socketserver,ssl,subprocess,sys,threading,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--confirm-isolated-fixture',action='store_true',required=True);p.add_argument('--inside',action='store_true');a=p.parse_args()
if os.geteuid()!=0 or sys.platform!='linux':raise SystemExit('Explicit Linux root fixture required')
if not a.inside:raise SystemExit(subprocess.run(['unshare','--net','--',sys.executable,'-B',__file__,'--confirm-isolated-fixture','--inside']).returncode)
from freeqnap.nas.common import Context
from freeqnap.nas.health import Health
from freeqnap.nas.notifications import Notifications,DEFAULT
from freeqnap.nas.ddns import DDNS,render,accepted_cache

def run(*args):
 r=subprocess.run(args,capture_output=True,text=True,timeout=60)
 if r.returncode:raise ValueError(Path(args[0]).name+' failed in isolated communication fixture')
 return r.stdout

group=grp.getgrnam('freeqnap-ddns');base=Path('/run/freeqnap-communications-validation');base.mkdir(mode=0o750,exist_ok=True);os.chown(base,0,group.gr_gid);root=base/('fixture-'+secrets.token_hex(8));root.mkdir(mode=0o750);os.chown(root,0,group.gr_gid)
servers=[];caches=[];report={};mail=[];dns_requests=[];mode={'dns':'good','allow_refused_recipient':False,'expect_untrusted':False}
try:
 run('ip','link','set','lo','up');run('ip','addr','add','192.168.77.2/32','dev','lo')
 tool=Path(__file__).with_name('local-https.py');run(sys.executable,str(tool),'create-ca','--directory',str(root/'ca'));run(sys.executable,str(tool),'issue','--ca',str(root/'ca'),'--directory',str(root/'tls'),'--address','192.168.77.2','--network','192.168.77.0/24')
 public=root/'public-ca.crt';public.write_bytes((root/'ca/ca.crt').read_bytes());public.chmod(0o644);context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2;context.load_cert_chain(root/'tls/server.crt',root/'tls/server.key')
 class DNS(http.server.BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def do_GET(self):
   expected='Basic '+base64.b64encode(b'fixture-user:fixture-token').decode();assert self.headers.get('Authorization')==expected;assert 'fixture.example.invalid' in self.path;dns_requests.append(self.path);raw=(mode['dns']+' 8.8.8.8\n').encode();self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 http=http.server.ThreadingHTTPServer(('192.168.77.2',18443),DNS);http.socket=context.wrap_socket(http.socket,server_side=True);servers.append(http);threading.Thread(target=http.serve_forever,daemon=True).start()
 class SMTP(socketserver.BaseRequestHandler):
  def handle(self):
   connection=self.request;encrypted=self.server.implicit
   if encrypted:
    try:connection=context.wrap_socket(connection,server_side=True)
    except ssl.SSLError as error:
     if mode['expect_untrusted'] and error.reason=='TLSV1_ALERT_UNKNOWN_CA':return
     raise
   connection.settimeout(10);stream=connection.makefile('rb');authenticated=False;recipient=None
   def reply(value):connection.sendall(value.encode()+b'\r\n')
   reply('220 fixture ESMTP')
   while True:
    line=stream.readline(8192)
    if not line:break
    command=line.decode().strip();verb=command.split(' ',1)[0].upper()
    if verb in ('EHLO','HELO'):reply('250-fixture\r\n250-AUTH PLAIN\r\n250 STARTTLS' if not encrypted else '250-fixture\r\n250 AUTH PLAIN')
    elif verb=='STARTTLS':
     reply('220 Begin TLS');stream.close();connection=context.wrap_socket(connection,server_side=True);stream=connection.makefile('rb');encrypted=True
    elif verb=='AUTH':
     assert encrypted,'Authentication was attempted before TLS';assert command.startswith('AUTH PLAIN ');assert base64.b64decode(command[11:])==b'\0fixture-user\0fixture-password';authenticated=True;reply('235 authenticated')
    elif verb=='MAIL':assert encrypted and authenticated;reply('250 sender')
    elif verb=='RCPT':
     recipient='fail@example.invalid' if 'fail@example.invalid' in command else 'ok@example.invalid';reply('550 fixture refusal' if recipient.startswith('fail') and not mode['allow_refused_recipient'] else '250 recipient')
    elif verb=='DATA':
     reply('354 send data');body=b''
     while True:
      part=stream.readline(8192)
      if part in (b'.\r\n',b'.\n'):break
      if not part or len(body)+len(part)>131072:raise ValueError('Invalid fixture message')
      body+=part
     mail.append({'recipient':recipient,'encrypted':encrypted,'bytes':len(body)});reply('250 accepted')
    elif verb in ('RSET','NOOP'):reply('250 reset')
    elif verb=='QUIT':reply('221 closing');break
    else:reply('500 unsupported fixture command')
   stream.close();connection.close()
 class SMTPServer(socketserver.ThreadingTCPServer):allow_reuse_address=True;daemon_threads=True
 for port,implicit in ((18587,False),(18465,True)):
  server=SMTPServer(('192.168.77.2',port),SMTP);server.implicit=implicit;servers.append(server);threading.Thread(target=server.serve_forever,daemon=True).start()
 ctx=Context(root/'state');Health(ctx);n=Notifications(ctx);c=json.loads(json.dumps(DEFAULT));c['smtp'].update(enabled=True,host='192.168.77.2',port=18587,protocol='starttls',username='fixture-user',sender='fixture@example.invalid',recipients=['fail@example.invalid','ok@example.invalid'],ca_certificate=public.read_text());n.save({'config':c,'smtp_password':'fixture-password'})
 with ctx.state.connect() as db:db.execute('INSERT INTO health_events(alert_id,kind,severity,title,created) VALUES(?,?,?,?,?)',('fixture','opened','critical','Isolated fixture health event',time.time()))
 for _ in range(2):n.tick()
 statuses={r['status'] for r in n.status()['outbox']};assert statuses=={'retrying','smtp-accepted'} and len(mail)==1
 n=Notifications(ctx);mode['allow_refused_recipient']=True;n.tick(time.time()+31);assert all(r['status']=='smtp-accepted' for r in n.status()['outbox']) and len(mail)==2
 report['smtp_starttls_auth_and_failure_isolation_restart']=True
 c['smtp'].update(protocol='tls',port=18465,recipients=['ok@example.invalid']);n.save({'config':c});n.test({'channel':'smtp','confirmation':'SEND TEST NOTIFICATION'});n.tick();assert len(mail)==3;report['smtp_implicit_tls']=True
 mode['expect_untrusted']=True;c['smtp']['ca_certificate']='';n.save({'config':c});n.test({'channel':'smtp','confirmation':'SEND TEST NOTIFICATION'});n.tick();assert len(mail)==3 and n.status()['outbox'][0]['status']=='retrying';report['smtp_untrusted_ca_rejected']=True
 # Run the real ddclient in the production unprivileged transient-unit sandbox,
 # joining this isolated namespace. Override only the fixture's transport endpoint.
 driver=DDNS(ctx);profile={'name':'fixture','provider':'custom-dyndns2','hostname':'fixture.example.invalid','zone':'','login':'fixture-user','family':4,'source':'manual','address':'8.8.8.8','server':'provider.example.invalid','interval_minutes':5,'enabled':True};text,host=render(profile,'fixture-token','8.8.8.8');text=text.replace('server=provider.example.invalid','server=192.168.77.2:18443');file=root/'ddclient.conf';file.write_text(text);file.chmod(0o600)
 def call_driver(label,trusted=True):
  cache=Path('/var/lib/freeqnap-ddns')/('fixture-'+secrets.token_hex(8)+'.cache');caches.append(cache);unit='freeqnap-ddns-test-'+secrets.token_hex(8);args=driver.command(file,unit,cache);index=args.index('/usr/bin/ddclient');extra=['--property=NetworkNamespacePath=/proc/'+str(os.getpid())+'/ns/net']
  if trusted:extra+=['--setenv=CURL_CA_BUNDLE='+str(public),'--setenv=SSL_CERT_FILE='+str(public)]
  code,output=driver.execute(args[:index]+extra+args[index:]);(root/('driver-'+label+'.log')).write_text(output);return cache,code
 cache,code=call_driver('good');assert code==0;assert accepted_cache(cache,host,'8.8.8.8',4)>0;assert dns_requests;assert cache.stat().st_uid==__import__('pwd').getpwnam('freeqnap-ddns').pw_uid;report['ddns_real_driver_tls_basic_auth_cache_acceptance_and_unprivileged_unit']=True
 mode['dns']='badauth';cache,code=call_driver('badauth')
 try:accepted_cache(cache,host,'8.8.8.8',4)
 except (ValueError,OSError):pass
 else:raise AssertionError('Provider rejection accepted')
 report['ddns_provider_rejection_not_success']=True
 before=len(dns_requests);cache,code=call_driver('untrusted',False);assert len(dns_requests)==before
 try:accepted_cache(cache,host,'8.8.8.8',4)
 except (ValueError,OSError):pass
 else:raise AssertionError('Untrusted TLS accepted')
 report['ddns_untrusted_tls_rejected']=True
 report.update(isolated_namespace=True,owner_mailboxes_contacted=False,external_dns_provider_contacted=False,production_profiles_changed=False,physical_disks_formatted=False)
finally:
 for server in servers:server.shutdown();server.server_close()
 if report.get('ddns_untrusted_tls_rejected'):
  for cache in caches:
   if cache.exists():cache.unlink()
  shutil.rmtree(root)
if report:print(json.dumps(report,indent=2))
