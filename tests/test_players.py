import base64,hashlib,http.client,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from freeqnap.agents import Agents,Denied
from freeqnap.players import Players,lan_ip,endpoint,describe,soap,xml
from freeqnap.state import State

DESCRIPTION=b'''<root xmlns="urn:schemas-upnp-org:device-1-0"><device><deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType><friendlyName>Fixture TV</friendlyName><UDN>uuid:fixture</UDN><serviceList><service><serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType><controlURL>/control</controlURL></service></serviceList></device></root>'''
class PlayerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.state=State(Path(self.tmp.name));self.agents=Agents(self.state);issued=self.agents.issue({'name':'test','grants':['media.play','media.playback-control'],'days':1});self.principal=self.agents.authenticate('Bearer '+issued['token']);self.calls=[];owner=self
  class Broker:
   def request(self,op,r):
    owner.calls.append((op,r))
    if op=='media.catalog':return {'entries':[{'id':'item','path':'movie.mp4'}]}
    if op=='nas.status':return {'libraries':[{'name':'movies','share':'media'}]}
    if op=='files.read':return {'etag':'fixed','total_bytes':10,'data_base64':base64.b64encode(b'0123456789'[r['offset']:r['offset']+r['count']]).decode()}
    raise AssertionError(op)
  self.players=Players(self.state,Broker(),self.agents)
 def test_reject_public_loopback_url_redirect_and_entities(self):
  for ip in ['127.0.0.1','169.254.169.254','8.8.8.8','::1','224.0.0.1','0.0.0.0','192.0.2.1']:
   with self.assertRaises(ValueError):lan_ip(ip)
  for url in ['https://192.168.1.20/a','http://127.0.0.1/a','http://user:pw@192.168.1.20/a','http://192.168.1.20/a#x','http://192.168.1.21/a']:
   with self.assertRaises(ValueError):endpoint(url,'192.168.1.20')
  with self.assertRaises(ValueError):xml(b'<!DOCTYPE a [<!ENTITY foo "bar">]><a/>')
  with patch('freeqnap.players.exchange',return_value=DESCRIPTION.replace(b'>/control<',b'>http://127.0.0.1/private<')):
   with self.assertRaises(ValueError):describe('http://192.168.1.20/device.xml','192.168.1.20')
 def approved(self):
  with patch('freeqnap.players.exchange',return_value=DESCRIPTION):p=describe('http://192.168.1.20/device.xml','192.168.1.20')
  p['approved']=True;self.state.set('players',{p['id']:p});self.state.set('player-settings',{'enabled':True,'address':'192.168.1.10','port':8091});return p
 def test_approval_identity_drift_and_ticket_revocation(self):
  p=self.approved()
  with patch('freeqnap.players.describe',return_value={**p,'control':'http://192.168.1.20/changed'}):
   with self.assertRaises(Denied):self.players.player(p['id'])
  with patch('freeqnap.players.describe',return_value=p),patch('freeqnap.players.soap') as call:
   result=self.players.invoke('media.play',{'player':p['id'],'library':'movies','id':'item'},self.principal)
   self.assertTrue(result['sent']);self.assertFalse(result['playback_verified']);self.assertEqual(call.call_count,2)
   url=call.call_args_list[0].args[2]['CurrentURI'];ticket=url.rsplit('/',1)[1]
  self.assertNotIn(ticket,self.state.database.read_bytes().decode('latin1'));self.players.stream(ticket,p['ip'])
  with self.assertRaises(Denied):self.players.stream(ticket,'192.168.1.21')
  self.players.approve({'id':p['id'],'approved':False})
  with self.assertRaises(Denied):self.players.stream(ticket,p['ip'])
  self.players.approve({'id':p['id'],'approved':True});self.agents.revoke({'id':self.principal['id']})
  with self.assertRaises(Denied):self.players.stream(ticket,p['ip'])
 def test_failed_play_removes_ticket_and_nonindexed_source_denied(self):
  p=self.approved()
  with patch('freeqnap.players.describe',return_value=p),patch('freeqnap.players.soap',side_effect=ValueError('unavailable')):
   with self.assertRaises(ValueError):self.players.invoke('media.play',{'player':p['id'],'library':'movies','id':'item'},self.principal)
  with self.state.connect() as db:self.assertEqual(db.execute("SELECT count(*) FROM settings WHERE key LIKE 'player-ticket:%'").fetchone()[0],0)
  with patch('freeqnap.players.describe',return_value=p):
   with self.assertRaises(ValueError):self.players.invoke('media.play',{'player':p['id'],'library':'movies','id':'not indexed'},self.principal)
 def test_soap_escapes_arguments_and_only_control_commands_allowed(self):
  p=self.approved()
  with patch('freeqnap.players.exchange',return_value=b'<response/>') as call:
   soap(p,'SetAVTransportURI',{'CurrentURI':'http://host/a?x=1&y=2'})
   self.assertIn(b'&amp;',call.call_args.args[3])
  with patch('freeqnap.players.describe',return_value=p):
   for command in ['Delete','arbitrary','shell']:
    with self.assertRaises(ValueError):self.players.invoke('media.playback-control',{'player':p['id'],'command':command},self.principal)

 def test_http_stream_ranges_and_revoke(self):
  p=self.approved();ticket='a'*43;key='player-ticket:'+hashlib.sha256(ticket.encode()).hexdigest()
  record={'source':{'share':'media','path':'movie.mp4'},'path':'movie.mp4','etag':'fixed','expires':time.time()+60,'principal':self.principal['id'],'ip':'127.0.0.1','player':p['id']}
  self.state.set(key,record);self.players.start({'enabled':True,'address':'127.0.0.1','port':0});server=self.players.listener;self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
  def get(token,headers=None,method='GET'):
   c=http.client.HTTPConnection('127.0.0.1',server.server_port);c.request(method,'/stream/'+token,headers=headers or {});r=c.getresponse();value=(r.status,r.read(),r.getheader('Content-Range'));c.close();return value
  self.assertEqual(get(ticket,{'Range':'bytes=2-5'}),(206,b'2345','bytes 2-5/10'))
  self.assertEqual(get(ticket,method='HEAD')[1],b'')
  self.assertEqual(get('b'*43)[0],404)
  self.agents.revoke({'id':self.principal['id']});self.assertEqual(get(ticket)[0],404)

 def test_forward_and_rewind_use_reported_playhead(self):
  p=self.approved()
  with patch('freeqnap.players.describe',return_value=p),patch('freeqnap.players.soap',return_value=xml(b'<r><RelTime>00:02:00</RelTime></r>')) as call:
   self.players.invoke('media.playback-control',{'player':p['id'],'command':'forward','seconds':45},self.principal)
   self.assertEqual(call.call_args.args[1:],('Seek',{'Unit':'REL_TIME','Target':'00:02:45'}))
   self.players.invoke('media.playback-control',{'player':p['id'],'command':'rewind','seconds':300},self.principal)
   self.assertEqual(call.call_args.args[2]['Target'],'00:00:00')
