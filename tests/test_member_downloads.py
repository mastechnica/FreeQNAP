import io,json,tempfile,time,unittest,contextlib
from pathlib import Path
from unittest.mock import Mock,patch
from types import SimpleNamespace
from freeqnap.nas.common import Context
from freeqnap.nas.downloads import Downloads
from freeqnap.nas.member_services import downloads,health
from freeqnap.nas.download_discovery import discover
from freeqnap.access_scope import using
from freeqnap.nas.health import Health,fault
A='a'*32;B='b'*32
class MemberDownloadsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.ctx=Context(Path(self.tmp.name));self.manager=Downloads(self.ctx);self.manager.target=Mock();self.ctx.state.set('downloads_settings',{'pool':'fixture'})
 def add(self,owner):
  with using('user:'+owner):return downloads(self.manager,owner,'downloads.add',{'url':'https://example.org/file.zip'})['job']
 def test_private_queue_controls_retained_files_and_no_legacy_adoption(self):
  a=self.add(A);b=self.add(B)
  self.assertEqual([r['id'] for r in downloads(self.manager,A,'downloads.status',{})['jobs']],[a['id']])
  for action in ('downloads.control','downloads.files','downloads.read'):
   with self.assertRaises(ValueError):downloads(self.manager,A,action,{'id':b['id'],'action':'remove'})
  downloads(self.manager,A,'downloads.control',{'id':a['id'],'action':'pause'})
  self.assertEqual(self.manager.jobs()[a['id']]['desired'],'paused')
  self.ctx.state.set('downloads_retained_files',{b['id']:b,a['id']:a,'legacy':{'id':'legacy','label':'private'}})
  self.assertEqual(len(downloads(self.manager,A,'downloads.status',{})['retained_files']),1)
 def test_members_cannot_configure_engine_or_forge_identity(self):
  with self.assertRaises(ValueError):downloads(self.manager,A,'downloads.setup',{})
  with using('user:'+B),self.assertRaises(ValueError):downloads(self.manager,A,'downloads.add',{'url':'https://example.org/x'})
 def test_member_health_excludes_private_incidents_and_detail_paths(self):
  h=Health(self.ctx);h.reconcile('jobs',[fault('private','warning','Another user filename',{'job_id':'secret'})],time.time());h.reconcile('space',[fault('root','critical','Filesystem capacity needs attention',{'mountpoint':'/secret/path','used_percent':99})],time.time())
  view=health(SimpleNamespace(alerts=h));self.assertEqual(view['active_total'],1);self.assertNotIn('secret',json.dumps(view));self.assertTrue(view['read_only'])
class DiscoveryTests(unittest.TestCase):
 def opener(self,pages):
  @contextlib.contextmanager
  def open_(url,**kwargs):
   self.seen.append(url)
   kind,data=pages[url];r=io.BytesIO(data.encode());r.getheader=lambda key:kind
   yield r,url
  return open_
 def test_depth_zero_and_one_stay_in_folder_and_site_and_deduplicate(self):
  pages={'https://example.org/files/':('text/html','<a href="one.zip">x</a><a href="one.zip#x">dup</a><a href="sub/">sub</a><a href="../private.zip">up</a><a href="https://other.org/x.zip">out</a>'),'https://example.org/files/sub/':('text/html','<a href="two.bin">two</a><a href="deeper/">deep</a>')}
  self.seen=[];r=discover({'url':'https://example.org/files/','depth':0},self.opener(pages));self.assertEqual([x['name'] for x in r['items']],['one.zip']);self.assertEqual(len(self.seen),1)
  self.seen=[];r=discover({'url':'https://example.org/files/','depth':1},self.opener(pages));self.assertEqual({x['name'] for x in r['items']},{'one.zip','two.bin'});self.assertEqual(len(self.seen),2);self.assertTrue(r['preview_only'])
 def test_direct_files_and_opaque_download_links(self):
  pages={'https://example.org/files/':('text/html','<a href="get?id=1">download</a>'),'https://example.org/files/get?id=1':('application/zip','x')};self.seen=[]
  r=discover({'url':'https://example.org/files/'},self.opener(pages));self.assertEqual(len(r['items']),1);self.assertEqual(r['items'][0]['url'],'https://example.org/files/get?id=1')
 def test_invalid_depth_and_credentials_fail_before_fetch(self):
  for req in ({'url':'https://example.org/','depth':True},{'url':'https://example.org/','depth':6},{'url':'https://user:pass@example.org/'},{'url':'file:///etc/passwd'}):
   with self.assertRaises(ValueError):discover(req,Mock(side_effect=AssertionError('must not fetch')))
 def test_redirect_origin_is_checked_before_dns_or_request(self):
  from freeqnap.nas.public_http import open_url
  with patch('freeqnap.nas.public_http.target') as target:
   with self.assertRaises(ValueError):
    with open_url('https://other.org/',allowed_origin=('https','example.org',443)):pass
   target.assert_not_called()
 def test_discovery_file_limit_is_explicit_not_claimed_complete(self):
  self.seen=[];html=''.join('<a href="%d.zip">x</a>'%i for i in range(505));r=discover({'url':'https://example.org/files/'},self.opener({'https://example.org/files/':('text/html',html)}));self.assertEqual(len(r['items']),500);self.assertTrue(r['truncated'])

 def test_discovery_continues_after_first_500_files(self):
  self.seen=[]
  start='https://example.org/files/'
  pages={start:('text/html',''.join('<a href="%d.zip">file</a>'%i for i in range(1073)))}
  names=[];offset=0
  while offset is not None:
   page=discover({'url':start,'offset':offset},self.opener(pages))
   names.extend(item['name'] for item in page['items']);offset=page['next_offset']
  self.assertEqual(names,[str(i)+'.zip' for i in range(1073)])
