import copy,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from test_nas import Fixture
from freeqnap.nas.health import Health
from freeqnap.nas.notifications import Notifications,DEFAULT,KEY,config

class NotificationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.ctx=Fixture(Path(self.tmp.name));Health(self.ctx);self.sent=[];self.n=Notifications(self.ctx,smtp_sender=self.sender);self.now=time.time()+10
 def sender(self,current,destination,message):self.sent.append((destination,message));return 'smtp-accepted'
 def configure(self,enabled=True,**overrides):
  c=copy.deepcopy(DEFAULT);c['smtp'].update(host='smtp.example.invalid',sender='nas@example.invalid',recipients=['one@example.invalid','two@example.invalid'],enabled=enabled,**overrides);self.n.save({'config':c});return c
 def event(self,title='A NAS fault',when=None):
  with self.ctx.state.connect() as db:return db.execute('INSERT INTO health_events(alert_id,kind,severity,title,created) VALUES(?,?,?,?,?)',('fixture','opened','critical',title,self.now if when is None else when)).lastrowid
 def rows(self):
  with self.ctx.state.connect() as db:return [dict(r) for r in db.execute('SELECT * FROM notification_outbox ORDER BY created,id')]
 def test_defaults_never_contact_any_transport(self):
  self.event();self.n.tick(self.now);self.assertEqual(self.rows(),[]);self.assertEqual(self.sent,[]);self.assertFalse(self.n.status()['config']['smtp']['enabled'])
 def test_enable_never_replays_old_incidents_and_cursor_does_not_starve_new_events(self):
  self.event(when=1);self.configure();self.event('new');self.n.tick(self.now);self.n.tick(self.now);self.assertEqual(len(self.sent),2)
  self.event('later');self.n.tick(self.now);self.assertEqual(len(self.sent),3);self.assertEqual(len(self.rows()),4)
 def test_failure_isolated_later_recipient_sent_and_failure_survives_restart(self):
  self.configure();self.event()
  def send(c,d,m):
   if d=='one@example.invalid':raise OSError('private SMTP credential must not escape')
   return self.sender(c,d,m)
  self.n.smtp_sender=send
  for _ in range(2):self.n.tick(self.now)
  rows=self.rows();self.assertEqual({r['status'] for r in rows},{'retrying','smtp-accepted'});self.assertEqual(len(self.sent),1);self.assertNotIn('private SMTP credential',json.dumps(self.n.status()))
  reloaded=Notifications(self.ctx,smtp_sender=self.sender);reloaded.tick(self.now+31);self.assertEqual({r['status'] for r in self.rows()},{'smtp-accepted'})
 def test_settings_change_holds_pending_items_and_requires_review_to_replay(self):
  self.configure();self.event();self.n.tick(self.now);self.configure();self.assertIn('needs-review',{r['status'] for r in self.rows()})
  row=next(r for r in self.rows() if r['status']=='needs-review');plan=self.n.retry_plan({'id':row['id']});self.assertIn('original_created_at',plan['body']);self.n.retry({'plan_id':plan['id'],'digest':plan['digest'],'confirmation':plan['confirmation']});self.n.tick(self.now+1);self.assertEqual(len(self.sent),2)
 def test_changed_destination_cannot_silently_receive_old_notification(self):
  self.configure();self.event();self.n.tick(self.now);c=copy.deepcopy(DEFAULT);c['smtp'].update(host='smtp.example.invalid',sender='nas@example.invalid',recipients=['other@example.invalid'],enabled=True);self.n.save({'config':c});row=next(r for r in self.rows() if r['status']=='needs-review')
  with self.assertRaises(ValueError):self.n.retry_plan({'id':row['id']})
 def test_discard_is_explicit_and_deduplication_never_requeues_it(self):
  self.configure();self.event();self.n.tick(self.now);row=next(r for r in self.rows() if r['status']=='pending')
  with self.assertRaises(ValueError):self.n.discard({'id':row['id']})
  self.n.discard({'id':row['id'],'confirmation':'DISCARD NOTIFICATION '+row['id']});self.n.tick(self.now+1);self.assertEqual(len(self.sent),1);self.assertIn('operator-discarded',{r['status'] for r in self.rows()})
 def test_interrupted_send_retained_as_ambiguous(self):
  self.configure();self.event();self.n.tick(self.now)
  with self.ctx.state.connect() as db:db.execute("UPDATE notification_outbox SET status='sending' WHERE status='pending'")
  self.n.reconcile_sending();row=next(r for r in self.rows() if r['status']=='retrying');self.assertIn('ambiguous',row['last_error'])
 def test_secrets_are_private_and_absent_from_status_and_jobs(self):
  c=self.configure(enabled=False,username='nas-account');self.n.save({'config':c,'smtp_password':'test-password-only'});self.assertNotIn('test-password-only',json.dumps(self.n.status()));self.assertEqual(self.ctx.state.jobs(),[])
  file=self.ctx.directory/'secrets'/self.n.current()['credential_file'];self.assertEqual(file.stat().st_mode&0o777,0o600)
 def test_test_delivery_requires_explicit_instruction_even_with_email_disabled(self):
  self.configure(enabled=False)
  with self.assertRaises(ValueError):self.n.test({'channel':'smtp'})
  self.n.test({'channel':'smtp','confirmation':'SEND TEST NOTIFICATION'});self.assertEqual(self.sent,[]);self.n.tick(self.now);self.assertEqual(len(self.sent),1)
 def test_tls_before_authentication_and_positive_recipient_acceptance(self):
  c=self.configure(enabled=False,username='nas-account');self.n.save({'config':c,'smtp_password':'test-password-only'});client=MagicMock();client.send_message.return_value={}
  with patch('freeqnap.nas.notifications.smtplib.SMTP',return_value=client):
   result=self.n.send_smtp(self.n.current(),'one@example.invalid',{'title':'Fixture','body':'Only fixture','event_id':1,'notification_id':'a'*32})
  names=[x[0] for x in client.method_calls];self.assertLess(names.index('starttls'),names.index('login'));self.assertEqual(result,'smtp-accepted');self.assertEqual(client.send_message.call_args.kwargs['to_addrs'],['one@example.invalid'])
  client.send_message.return_value={'one@example.invalid':(550,b'refused')}
  with patch('freeqnap.nas.notifications.smtplib.SMTP',return_value=client),self.assertRaises(ValueError):self.n.send_smtp(self.n.current(),'one@example.invalid',{'title':'Fixture','body':'Only fixture','event_id':1,'notification_id':'a'*32})
 def test_bad_server_headers_plaintext_and_invalid_credentials_rejected(self):
  for key,value in [('protocol','plain'),('host','smtp.invalid\r\nBCC:x'),('sender','nas@example.invalid\r\nBCC:x'),('recipients',['bad\n@example.invalid']),('ca_certificate','PRIVATE KEY')]:
   c=copy.deepcopy(DEFAULT);c['smtp'][key]=value
   with self.assertRaises((ValueError,TypeError)):config(c)
