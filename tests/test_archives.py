import base64,contextlib,gzip,io,os,stat,tarfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import test_fileops
from freeqnap.archive_reader import safe_member
from freeqnap.nas.archives import Archives
from freeqnap.nas.bundle import Bundles
from freeqnap.zipstream import write_zip

class ArchiveTests(unittest.TestCase):
 def review(self,plan):return {k:plan[v] for k,v in [('plan_id','id'),('digest','digest'),('confirmation','confirmation')]}
 def setUp(self):
  test_fileops.FileManagerTests.setUp(self);self.bundles=Bundles(self.ctx,self.fm);self.archives=Archives(self.ctx,self.fm,self.bundles)
  import sys
  if sys.platform!='linux':
   from freeqnap.nas.fileops import rename_exclusive
   p=patch('freeqnap.nas.archives.rename_exclusive',side_effect=rename_exclusive);p.start();self.addCleanup(p.stop)
 def zipped(self,name='input.zip',entries=None):
  with zipfile.ZipFile(self.a/name,'w',compression=zipfile.ZIP_DEFLATED) as z:
   for key,value in (entries or {'folder/file.txt':b'hello','empty':b''}).items():z.writestr(key,value)
  return name
 def extract(self,name,mode='named',**extra):
  p=self.archives.plan({'operation':'extract','share':'a','path':name,'destination':mode,**extra});return self.archives.apply(self.review(p))
 def reader(self,action,payload):return {'files.bundle-node':self.bundles.node,'files.bundle-read':self.bundles.read}[action](payload)
 def test_zip_selection_stream_roundtrip_and_no_disk_stage(self):
  (self.a/'one').write_bytes(b'hello'*1000);(self.a/'dir').mkdir();(self.a/'dir/two').write_bytes(b'two')
  ticket=self.bundles.start({'share':'a','paths':['one','dir']});out=io.BytesIO();write_zip(out,self.reader,self.bundles.info(ticket))
  with zipfile.ZipFile(io.BytesIO(out.getvalue())) as z:self.assertEqual(z.testzip(),None);self.assertEqual(z.read('dir/two'),b'two');self.assertEqual(z.read('one'),b'hello'*1000)
  self.assertFalse((self.ctx.mount/'.freeqnap').exists())
 def test_whole_folder_download_and_ticket_scope(self):
  (self.a/'file').write_bytes(b'selected');ticket=self.bundles.start({'share':'a','paths':['']});out=io.BytesIO();write_zip(out,self.reader,self.bundles.info(ticket))
  with zipfile.ZipFile(io.BytesIO(out.getvalue())) as z:self.assertEqual(z.read('a/file'),b'selected')
  ticket=self.bundles.start({'share':'a','paths':['file']})
  with self.assertRaises(ValueError):self.bundles.read({**ticket,'path':'../outside'})
  with self.assertRaises(ValueError):self.bundles.node({**ticket,'path':'other'})
 def test_changed_download_is_invalid_zip_without_central_directory(self):
  (self.a/'file').write_bytes(b'x'*600000);ticket=self.bundles.start({'share':'a','paths':['file']});out=io.BytesIO();calls=0
  def reader(action,payload):
   nonlocal calls
   value=self.reader(action,payload)
   if action=='files.bundle-read':
    calls+=1
    if calls==2:value['etag']='changed'
   return value
  with self.assertRaises(ValueError):write_zip(out,reader,self.bundles.info(ticket))
  self.assertFalse(zipfile.is_zipfile(io.BytesIO(out.getvalue())))
 def test_selection_overlap_symlinks_and_portable_paths(self):
  (self.a/'dir').mkdir();(self.a/'dir/file').touch();(self.a/'link').symlink_to(self.a/'dir/file')
  for paths in [['dir','dir/file'],['link']]:
   with self.assertRaises(ValueError):self.bundles.start({'share':'a','paths':paths})
  for name in ['/etc/passwd','../outside','a/../outside','a\\outside','C:bad','.freeqnap/x','a//b','a/./b','a\x00b']:
   with self.assertRaises(ValueError):safe_member(name)
 def test_named_extract_current_extract_and_collision(self):
  name=self.zipped();result=self.extract(name);self.assertEqual(result['published'],['input']);self.assertEqual((self.a/'input/folder/file.txt').read_bytes(),b'hello')
  self.zipped('second.zip',{'here.txt':b'here'});self.extract('second.zip','current');self.assertEqual((self.a/'here.txt').read_bytes(),b'here')
  self.zipped('collision.zip',{'here.txt':b'overwrite','other':b'new'})
  with self.assertRaises(ValueError):self.extract('collision.zip','current')
  self.assertEqual((self.a/'here.txt').read_bytes(),b'here');self.assertFalse((self.a/'other').exists())
 def test_tar_and_gzip_supported_without_external_programs(self):
  with tarfile.open(self.a/'sample.tar.gz','w:gz') as tar:
   info=tarfile.TarInfo('./nested/item');info.size=4;tar.addfile(info,io.BytesIO(b'data'))
  self.extract('sample.tar.gz');self.assertEqual((self.a/'sample/nested/item').read_bytes(),b'data')
  (self.a/'single.txt.gz').write_bytes(gzip.compress(b'compressed'));self.extract('single.txt.gz');self.assertEqual((self.a/'single.txt/single.txt').read_bytes(),b'compressed')
 def test_zip_slip_link_duplicate_and_expansion_refused(self):
  for n,entries in [('slip.zip',{'../outside':b'bad'}),('limit.zip',{'big':b'x'*4096})]:
   self.zipped(n,entries)
   with self.assertRaises(ValueError):self.extract(n,max_output_bytes=100)
  self.assertFalse((self.ctx.mount/'outside').exists());self.assertFalse((self.a/'slip').exists());self.assertFalse((self.a/'limit').exists())
  with tarfile.open(self.a/'link.tar','w') as tar:
   item=tarfile.TarInfo('link');item.type=tarfile.SYMTYPE;item.linkname='/etc/passwd';tar.addfile(item)
  with self.assertRaises(ValueError):self.extract('link.tar')
  with zipfile.ZipFile(self.a/'duplicate.zip','w') as z:z.writestr('same',b'a');z.writestr('same',b'b')
  with self.assertRaises(ValueError):self.extract('duplicate.zip')
 def test_create_verified_zip_no_overwrite_and_stale_review(self):
  (self.a/'one').write_bytes(b'content');p=self.archives.plan({'operation':'zip','share':'a','paths':['one'],'filename':'saved.zip'});r=self.archives.apply(self.review(p));self.assertEqual(r['published'],['saved.zip'])
  with zipfile.ZipFile(self.a/'saved.zip') as z:self.assertEqual(z.read('one'),b'content');self.assertIsNone(z.testzip())
  with self.assertRaises(ValueError):self.archives.plan({'operation':'zip','share':'a','paths':['one'],'filename':'saved.zip'})
  p=self.archives.plan({'operation':'zip','share':'a','paths':['one'],'filename':'new.zip'});(self.a/'one').write_text('changed')
  with self.assertRaises(ValueError):self.archives.apply(self.review(p))
  self.assertFalse((self.a/'new.zip').exists())
 def test_archive_failure_job_does_not_stop_later_jobs(self):
  from freeqnap.nas.backend import Backend
  
  with patch('freeqnap.nas.backend.Access'):
   backend=Backend(self.ctx)
  self.zipped('bad.zip',{'../outside':b'bad'});self.zipped('good.zip',{'ok':b'ok'})
  for name in ['bad.zip','good.zip']:
   p=backend.dispatch('files.archive-plan',{'operation':'extract','share':'a','path':name});backend.dispatch('files.archive',self.review(p))
  backend.execute(self.ctx.state.claim());backend.execute(self.ctx.state.claim());jobs=self.ctx.state.jobs()
  self.assertEqual(sorted(j['status'] for j in jobs),['retryable','succeeded']);self.assertEqual((self.a/'good/ok').read_bytes(),b'ok')
