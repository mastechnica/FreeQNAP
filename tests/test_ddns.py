import copy,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from test_nas import Fixture
from freeqnap.nas.ddns import DDNS,PROVIDERS,validate,render,accepted_cache,KEY

class DDNSTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.ctx=Fixture(self.root/'state');self.cache=self.root/'cache';self.cache.mkdir();self.ddns=DDNS(self.ctx,self.cache,runner=self.driver);self.calls=[]
  self.c={'name':'home','provider':'cloudflare','hostname':'nas.example.invalid','zone':'example.invalid','login':'token','family':4,'source':'manual','address':'8.8.8.8','server':'','interval_minutes':5,'enabled':True}
 def save(self,**kw):
  c={**self.c,**kw};plan=self.ddns.plan(c);return self.ddns.apply({'plan_id':plan['id'],'digest':plan['digest'],'confirmation':plan['confirmation'],'password':'fixture-token'})
 def driver(self,args):
  self.calls.append(args);cache=Path(next(a.split('=',1)[1] for a in args if a.startswith('-cache=')));cache.write_text('mtime='+str(int(time.time()))+',status=good,ip=8.8.8.8 nas.example.invalid\n');return 0,'SUCCESS: provider accepted'
 def test_defaults_disabled_and_no_contact(self):
  self.ddns.tick();self.assertEqual(self.calls,[]);self.assertFalse(self.ddns.status()['enabled_by_default']);self.assertGreaterEqual(len(PROVIDERS),16)
 def test_provider_configuration_is_typed_and_has_no_hooks_or_arbitrary_options(self):
  text,host=render(self.c,'fixture-token','8.8.8.8');self.assertIn('ssl=yes',text);self.assertIn('usev4=ipv4',text);self.assertNotIn('cmd=',text);self.assertEqual(host,'nas.example.invalid')
  for change in ({'hostname':'nas.invalid\npostscript=/bin/sh'},{'provider':'shell'},{'source':'cmd'},{'server':'evil.invalid'},{'address':'192.168.1.2'},{'family':True},{'hostname':'evil.invalid'},{'interval_minutes':1}):
   with self.assertRaises(ValueError):validate({**self.c,**change})
  with self.assertRaises(ValueError):render(self.c,'token\npostscript=x','8.8.8.8')
 def test_provider_specific_hostname_mapping(self):
  c={**self.c,'provider':'duckdns','hostname':'fixture.duckdns.org','zone':'','login':''};text,host=render(c,'token','8.8.8.8');self.assertEqual(host,'fixture');self.assertIn('protocol=duckdns',text)
  c={**self.c,'provider':'namecheap','hostname':'example.invalid','login':''};text,host=render(c,'token','8.8.8.8');self.assertEqual(host,'@');self.assertIn('login=example.invalid',text)
 def test_receipt_must_match_exact_hostname_address_status_and_time(self):
  f=self.cache/'receipt';valid='mtime=123,status=good,ip=8.8.8.8 nas.example.invalid\n';f.write_text(valid);self.assertEqual(accepted_cache(f,'nas.example.invalid','8.8.8.8',4),123)
  for text in (valid.replace('good','badauth'),valid.replace('8.8.8.8','1.1.1.1'),valid.replace('123','0'),valid+valid,valid.replace('nas.','other.')):
   f.write_text(text)
   with self.assertRaises(ValueError):accepted_cache(f,'nas.example.invalid','8.8.8.8',4)
 def test_zero_exit_without_receipt_is_not_success_and_later_profile_continues(self):
  self.save();self.save(name='second',hostname='other.example.invalid');now=time.time()+1
  def driver(args):
   self.calls.append(args);return 0,'No verified receipt'
  self.ddns.runner=driver
  with patch('freeqnap.nas.ddns.shutil.which',return_value='/usr/bin/ddclient'):
   self.ddns.tick(now);self.ddns.tick(now)
  rows=self.ddns.status()['items'];self.assertEqual(len(self.calls),2);self.assertTrue(all(r['state']=='retrying' for r in rows));self.assertTrue(all(r['next_attempt_at']>now for r in rows))
 def test_private_credentials_and_isolated_unprivileged_command(self):
  self.save();now=time.time()
  with patch('freeqnap.nas.ddns.shutil.which',return_value='/usr/bin/ddclient'):self.ddns.tick(now)
  self.assertEqual(self.ddns.status()['items'][0]['state'],'provider-accepted');args=self.calls[0];self.assertIn('--property=User=freeqnap-ddns',args);self.assertIn('--property=ProtectSystem=strict',args);self.assertNotIn('fixture-token',' '.join(args));self.assertNotIn('fixture-token',json.dumps(self.ddns.status()))
  secret=self.ctx.directory/'secrets'/self.ddns.records()['home']['credential_file'];self.assertEqual(secret.stat().st_mode&0o777,0o600)
 def test_rollback_changed_plan_wrong_confirmation_and_duplicate_host_are_blocked(self):
  p=self.ddns.plan(self.c);self.save()
  with self.assertRaises(ValueError):self.ddns.apply({'plan_id':p['id'],'digest':p['digest'],'confirmation':p['confirmation'],'password':'token'})
  with self.assertRaises(ValueError):self.save(name='duplicate')
 def test_remove_never_deletes_remote_record_and_retry_keeps_provider_backoff(self):
  self.save();records=self.ddns.records();records['home']['runtime']['retry_not_before']=time.time()+1000;self.ctx.state.set(KEY,records);self.ddns.request_update({'name':'home'});self.assertGreater(self.ddns.status()['items'][0]['next_attempt_at'],time.time()+900)
  with self.assertRaises(ValueError):self.ddns.remove({'name':'home'})
  self.assertFalse(self.ddns.remove({'name':'home','confirmation':'REMOVE DDNS home'})['provider_record_deleted'])

 def test_ddns_and_other_service_accounts_cannot_be_created_as_share_users(self):
  from freeqnap.nas.sharing import Sharing
  sharing=Sharing(self.ctx)
  for username in ('freeqnap-ddns','freeqnap-https','freeqnap-downloads','systemd-network'):
   with self.assertRaises(ValueError):sharing.user({'name':username,'password':'fixture-password-only'})
