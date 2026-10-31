import base64,copy,importlib.util,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from test_nas import Fixture
from freeqnap.nas import push
from freeqnap.nas.health import Health
from freeqnap.nas.notifications import Notifications,DEFAULT
CRYPTO=all(importlib.util.find_spec(m) is not None for m in ('cryptography','py_vapid','http_ece'))
def b64(data):return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

class EndpointTests(unittest.TestCase):
 def test_only_reviewed_https_provider_endpoints_are_accepted(self):
  for value in ('https://fcm.googleapis.com/fcm/send/token','https://updates.push.services.mozilla.com/wpush/v2/token','https://web.push.apple.com/token','https://wns-fixture.notify.windows.com/w/?token=abc'):self.assertTrue(push.endpoint(value).hostname)
  for value in ('http://fcm.googleapis.com/token','https://fcm.googleapis.com.evil.invalid/token','https://127.0.0.1/token','https://user:pass@fcm.googleapis.com/token','https://fcm.googleapis.com:444/token','https://fcm.googleapis.com/token#fragment','https://fcm.googleapis.com/','https://evil.invalid/token','https://fcm.googleapis.com/token\n'):
   with self.assertRaises(ValueError):push.endpoint(value)
 def test_private_or_mixed_dns_results_are_rejected_before_connection(self):
  connection=push.PublicHTTPS('fcm.googleapis.com',443)
  with patch('freeqnap.nas.push.socket.getaddrinfo',return_value=[(2,1,6,'',('8.8.8.8',443)),(2,1,6,'',('127.0.0.1',443))]),patch('freeqnap.nas.push.socket.create_connection') as create:
   with self.assertRaises(ValueError):connection.connect()
   create.assert_not_called()

@unittest.skipUnless(CRYPTO,'Optional Web Push crypto dependencies required; native ARMhf campaign covers these')
class PushCryptoTests(unittest.TestCase):
 def setUp(self):
  from cryptography.hazmat.primitives.asymmetric import ec
  from cryptography.hazmat.primitives import serialization
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.browser=ec.generate_private_key(ec.SECP256R1());self.auth=b'0123456789abcdef';public=self.browser.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint);self.sub={'endpoint':'https://fcm.googleapis.com/fcm/send/fixture-private-token','keys':{'p256dh':b64(public),'auth':b64(self.auth)}}
 def test_actual_ecdh_payload_decryption_and_vapid_signature(self):
  import http_ece
  from py_vapid import Vapid02
  file,key=push.vapid_key(self.root/'keys');same,again=push.vapid_key(self.root/'keys');self.assertEqual(key,again);self.assertEqual(file.stat().st_mode&0o777,0o600);message={'title':'Fixture','body':'Encrypted local alert','event_id':1};body,headers=push.payload(file,self.sub,'mailto:nas@example.invalid',message)
  self.assertEqual(json.loads(http_ece.decrypt(body,private_key=self.browser,auth_secret=self.auth,version='aes128gcm')),message);self.assertTrue(Vapid02.verify(headers['Authorization']));self.assertNotIn(b'Encrypted local alert',body)
 def test_registry_keeps_endpoint_and_keys_private_and_does_not_replay_before_enrollment(self):
  ctx=Fixture(self.root/'state');Health(ctx);sent=[];service=Notifications(ctx,push_sender=lambda c,d,m:sent.append(d) or 'relay-accepted');c=copy.deepcopy(DEFAULT);c['push']={'enabled':True,'contact':'nas@example.invalid'};service.save({'config':c})
  with ctx.state.connect() as db:db.execute('INSERT INTO health_events(alert_id,kind,severity,title,created) VALUES(?,?,?,?,?)',('old','opened','critical','Earlier fault',time.time()))
  service.subscribe({'id':'a'*32,'label':'Fixture browser','subscription':self.sub});service.tick();self.assertEqual(sent,[]);self.assertNotIn('fixture-private-token',json.dumps(service.status()));self.assertNotIn(self.sub['keys']['auth'],json.dumps(service.status()))
  service.test({'channel':'push','subscription_id':'a'*32,'confirmation':'SEND TEST NOTIFICATION'});service.tick();self.assertEqual(sent,['a'*32])
 def test_expired_subscription_retains_send_and_stops_automatic_attempts(self):
  ctx=Fixture(self.root/'state');Health(ctx);service=Notifications(ctx,push_sender=lambda *a:'expired');c=copy.deepcopy(DEFAULT);c['push']['contact']='nas@example.invalid';service.save({'config':c});service.subscribe({'id':'a'*32,'label':'Fixture browser','subscription':self.sub});service.test({'channel':'push','subscription_id':'a'*32,'confirmation':'SEND TEST NOTIFICATION'});service.tick();status=service.status();self.assertTrue(status['subscriptions'][0]['expired']);self.assertEqual(status['outbox'][0]['status'],'needs-review');service.tick();self.assertEqual(service.status()['outbox'][0]['attempts'],1)
 def test_bad_points_and_auth_lengths_never_enroll(self):
  for key,value in [('p256dh',b64(b'\x04'+b'\x00'*64)),('auth',b64(b'short'))]:
   sub=copy.deepcopy(self.sub);sub['keys'][key]=value
   with self.assertRaises(ValueError):push.subscription(sub)
