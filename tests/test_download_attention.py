import io,tempfile,unittest,contextlib,json
from pathlib import Path
from unittest.mock import Mock
from freeqnap.nas.common import Context
from freeqnap.nas.downloads import Downloads
from freeqnap.nas.download_discovery import discover
from freeqnap.nas.download_problems import problem
from freeqnap.access_scope import using
A='a'*32
class DownloadAttentionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.ctx=Context(Path(self.tmp.name));self.m=Downloads(self.ctx);self.m.target=Mock();self.ctx.state.set('downloads_settings',{'pool':'fixture'})
 def add(self,**extra):
  with using('user:'+A):return self.m.add({'url':'https://example.org/file.zip',**extra})['job']
 def opener(self,html):
  @contextlib.contextmanager
  def open_(url,**kwargs):
   r=io.BytesIO(html.encode());r.getheader=lambda key:'text/html';yield r,url
  return open_
 def test_archive_style_base_preserves_identifier_and_original_listing(self):
  start='https://archive.org/download/fixture-item';html='<base href="/download/fixture-item/"><a href="Season.1.zip">file</a>'
  result=discover({'url':start},self.opener(html));self.assertEqual(result['source_page'],start);self.assertEqual(result['items'][0]['url'],start+'/Season.1.zip')
 def test_external_base_outside_folder_and_first_base_cannot_escape(self):
  for base in ('https://other.org/files/','/private/'):
   result=discover({'url':'https://example.org/files/'},self.opener('<base href="'+base+'"><base href="/files/"><a href="file.zip">file</a>'));self.assertEqual(result['items'],[]);self.assertEqual(result['failed_pages'],1)
 def test_scoped_base_entities_and_relative_paths(self):
  result=discover({'url':'https://example.org/files/list'},self.opener('<base href="sub/"><a href="one.zip?a=1&amp;b=2">f</a><a href="https://other.org/no.zip">outside</a>'));self.assertEqual(result['items'][0]['url'],'https://example.org/files/sub/one.zip?a=1&b=2');self.assertEqual(len(result['items']),1)
 def test_source_page_is_validated_retained_and_separate_from_private_source(self):
  row=self.add(source_page='https://example.org/listing');self.assertEqual(row['source_page'],'https://example.org/listing');self.assertNotIn('url',row)
  for page in ('javascript:alert(1)','https://user:secret@example.org/','magnet:?xt=urn:btih:'+'a'*40):
   with self.assertRaises(ValueError):self.add(source_page=page)
 def test_fixed_messages_do_not_publish_engine_paths_tokens_or_markup(self):
  for code in ('3','9','16','24','32','99'):
   result=problem({'state':'error','error_code':code,'errorMessage':'/private/token <script>secret</script>'});self.assertTrue(result['reason']);self.assertTrue(result['next_step']);self.assertNotIn('secret',json.dumps(result));self.assertFalse(result['automatic_retry'])
  self.assertTrue(problem({'state':'error','error_code':'6'})['automatic_retry']);self.assertIsNone(problem({'state':'active'}));self.assertIn('damaged',problem({'recovery_required':True})['reason'])
 def status(self,gid,code='3'):
  return {'status':'error','errorCode':code,'errorMessage':'Resource not found','totalLength':'0','completedLength':'0'}
 def test_permanent_error_stops_repeated_submissions_but_is_removable(self):
  row=self.add();self.m.rpc=Mock(side_effect=lambda method,args:self.status(row['gid']) if method=='tellStatus' else 'OK');self.m.reconcile();self.m.reconcile();stored=self.m.jobs()[row['id']];self.assertTrue(stored['attention_required']);self.assertEqual(sum(c.args[0]=='tellStatus' for c in self.m.rpc.call_args_list),1);self.assertFalse(any(c.args[0]=='addUri' for c in self.m.rpc.call_args_list));self.assertIn('File not found',self.m.status()['jobs'][0]['problem']['reason'])
  self.m.control({'id':row['id'],'action':'remove'});self.m.reconcile();self.assertNotIn(row['id'],self.m.jobs());self.assertIn(row['id'],self.ctx.state.setting('downloads_retained_files'))
 def test_explicit_retry_reuses_gid_and_partial_location_once_without_delay(self):
  row=self.add();rows=self.m.jobs();rows[row['id']].update(state='error',error_code='3',attention_required=True,next_retry=10**12);self.ctx.state.set('downloads_jobs',rows);self.m.control({'id':row['id'],'action':'resume'})
  self.m.rpc=Mock(side_effect=lambda method,args:self.status(row['gid']) if method=='tellStatus' else 'OK');self.m.reconcile();calls=[c.args for c in self.m.rpc.call_args_list];submit=[c for c in calls if c[0]=='addUri'];self.assertEqual(len(submit),1);self.assertEqual(submit[0][1][1]['gid'],row['gid']);self.assertEqual(submit[0][1][1]['dir'],'/srv/freeqnap/download-work/'+row['id']);self.assertLess([v[0] for v in calls].index('removeDownloadResult'),[v[0] for v in calls].index('addUri'))
  self.m.reconcile();self.assertTrue(self.m.jobs()[row['id']]['attention_required']);self.assertEqual(sum(c.args[0]=='addUri' for c in self.m.rpc.call_args_list),1)
 def test_transient_failures_continue_automatic_retry(self):
  row=self.add();self.m.rpc=Mock(side_effect=lambda method,args:self.status(row['gid'],'6') if method=='tellStatus' else 'OK');self.m.reconcile();self.assertTrue(any(c.args[0]=='addUri' for c in self.m.rpc.call_args_list));self.assertFalse(self.m.jobs()[row['id']].get('attention_required',False))
