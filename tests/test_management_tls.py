import copy,hashlib,json,shutil,ssl,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from test_nas import Fixture
from freeqnap.nas.management_tls import validate,nginx,origins,ManagementTLS

class ManagementTLSTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.config={'address':'192.168.77.2','networks':['192.168.77.0/24'],'names':['freeqnap.local']}
 def test_exact_private_bind_and_deny_all_are_mandatory(self):
  c=nginx(self.config);self.assertIn('listen 192.168.77.2:443 ssl;',c);self.assertIn('allow 192.168.77.0/24;',c);self.assertIn('deny all;',c);self.assertNotIn('listen 80',c);self.assertNotIn('0.0.0.0',c);self.assertIn('proxy_buffering off;',c);self.assertIn('proxy_max_temp_file_size 0;',c);self.assertIn('access_log off;',c)
  for key,value in [('address','8.8.8.8'),('networks',['0.0.0.0/0']),('networks',['192.168.88.0/24']),('names',['evil.local;return 200']),('names',['public.example']),('names',['freeqnap.local','freeqnap.local'])]:
   bad=copy.deepcopy(self.config);bad[key]=value
   with self.assertRaises(ValueError):validate(bad)
 def test_origin_allowlist_and_stripped_impersonation_headers(self):
  self.assertEqual(origins(self.config),['https://192.168.77.2','https://freeqnap.local']);c=nginx(self.config);self.assertIn('proxy_set_header X-Forwarded-User "";',c);self.assertIn('proxy_set_header X-User "";',c);self.assertIn('return 444;',c);self.assertNotIn('include ',c)
 @unittest.skipUnless(shutil.which('openssl'),'OpenSSL required')
 def test_real_ca_server_key_separation_and_certificate_status(self):
  script=Path(__file__).resolve().parents[1]/'tools/local-https.py';ca=self.root/'ca';bundle=self.root/'bundle'
  for args in [('create-ca','--directory',str(ca)),('issue','--ca',str(ca),'--directory',str(bundle),'--address',self.config['address'],'--network',self.config['networks'][0],'--name','freeqnap.local')]:
   subprocess.run(['python3',str(script),*args],capture_output=True,check=True,timeout=30)
  self.assertEqual((ca/'ca.key').stat().st_mode&511,384);self.assertEqual((bundle/'server.key').stat().st_mode&511,384);self.assertFalse((bundle/'ca.key').exists())
  for cert in (ca/'ca.crt',bundle/'server.crt'):
   text=subprocess.check_output(['openssl','x509','-in',str(cert),'-noout','-text'],text=True);self.assertIn('ASN1 OID: prime256v1',text);self.assertIn('Authority Key Identifier',text)
  # Real strict TLS handshake via memory BIOs: catches LibreSSL-issued missing AKI.
  client_context=ssl.create_default_context(cafile=str(ca/'ca.crt'));client_context.verify_flags|=ssl.VERIFY_X509_STRICT
  server_context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);server_context.load_cert_chain(str(bundle/'server.crt'),str(bundle/'server.key'))
  client_in,client_out,server_in,server_out=[ssl.MemoryBIO() for _ in range(4)]
  client=client_context.wrap_bio(client_in,client_out,server_hostname=self.config['address']);server=server_context.wrap_bio(server_in,server_out,server_side=True);finished=set()
  for _ in range(20):
   for index,(connection,outgoing,incoming) in enumerate(((client,client_out,server_in),(server,server_out,client_in))):
    try:connection.do_handshake();finished.add(index)
    except ssl.SSLWantReadError:pass
    if outgoing.pending:incoming.write(outgoing.read())
   if len(finished)==2:break
  self.assertEqual(finished,{0,1})
  context=Fixture(self.root/'fixture')
  def run(*args,**kwargs):
   if args[0]=='systemctl':return 'active\n'
   return subprocess.check_output(args,text=True)
  context.run=run;tls=ManagementTLS(context,bundle)
  with patch.object(tls,'probe',return_value=True):s=tls.status()
  self.assertTrue(s['configured']);self.assertEqual(s['service'],'active');self.assertFalse(s['browser_trust_verified']);self.assertGreater(s['certificate']['days_remaining'],360);self.assertNotIn('pem',s['certificate']);public=tls.public_ca();self.assertFalse(public['private_key_included']);self.assertNotIn('PRIVATE KEY',json.dumps(public));self.assertEqual(public['sha256'],hashlib.sha256(ssl.PEM_cert_to_DER_cert(public['certificate_pem'])).hexdigest())
  (bundle/'ca.crt').unlink();(bundle/'ca.crt').symlink_to(ca/'ca.key')
  with self.assertRaises(ValueError):tls.public_ca()
 def test_not_installed_is_unconfigured_not_healthy(self):
  tls=ManagementTLS(Fixture(self.root/'fixture'),self.root/'missing');self.assertEqual(tls.status(),{'configured':False,'browser_trust_verified':False})

 def test_service_active_does_not_substitute_for_verified_endpoint(self):
  directory=self.root/'tls';directory.mkdir();(directory/'public.json').write_text(json.dumps(self.config));ctx=Fixture(self.root/'fixture');tls=ManagementTLS(ctx,directory)
  with patch.object(tls,'certificate',return_value={'sha256':'fixture','expires_at':9999999999,'pem':'fixture'}),patch.object(tls,'probe',return_value=False):
   s=tls.status();self.assertEqual(s['service'],'active');self.assertFalse(s['available']);self.assertFalse(s['endpoint_verified'])
