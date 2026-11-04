import base64,hashlib,json,os,struct,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import test_fileops
from freeqnap.nas.social_media import SocialMedia,verify_tags
from freeqnap.nas.social_worker import jpeg_clean,mp4_clean

class SocialTests(unittest.TestCase):
 def setUp(self):
  test_fileops.FileManagerTests.setUp(self);self.backend=SimpleNamespace(ctx=self.ctx,files=self.fm);self.media=SocialMedia(self.backend);self.source=self.a/'photo.jpg';self.source.write_bytes(b'private original');self.r={'recipient':'a'*32,'owner':'a'*32,'primary':True,'source':{'type':'files','share':'a','path':'photo.jpg'},'assignments':[]}
 def fake(self,fd,tool,*args,**kwargs):return b'image/jpeg\nclean pixels' if tool=='python3' else b'[{"File:FileType":"JPEG","JPEG:ImageWidth":10}]'
 def test_private_copy_ranges_ownership_source_binding_expiry_and_original(self):
  before=hashlib.sha256(self.source.read_bytes()).hexdigest()
  with patch('freeqnap.nas.social_media.decode',side_effect=self.fake):value=self.media.prepare(self.r)
  req={**self.r,'id':value['id'],'count':4};self.assertEqual(base64.b64decode(self.media.read(req)['data_base64']),b'clea');self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(),before)
  for changes in [{'recipient':'b'*32},{'owner':'b'*32},{'source':{'type':'files','share':'a','path':'other.jpg'}}]:
   with self.assertRaises(PermissionError):self.media.read({**req,**changes})
  self.media.records[value['id']]['expires']=time.time()-1
  with self.assertRaises(PermissionError):self.media.read(req)
 def test_verification_failure_removes_temporary_copy_and_never_falls_back(self):
  with patch('freeqnap.nas.social_media.decode',side_effect=[b'image/jpeg\nunsafe',b'[{"EXIF:GPSLatitude":45}]']):
   with self.assertRaises(ValueError):self.media.prepare(self.r)
  self.assertFalse(list(self.media.root.iterdir()));self.assertEqual(self.source.read_bytes(),b'private original')
 def test_jpeg_all_app_comments_removed_and_mp4_unknown_structure_refused(self):
  raw=b'\xff\xd8\xff\xe1\x00\x08secret\xff\xfe\x00\x05gps\xff\xda\x00\x02pixels\xff\xd9';clean=jpeg_clean(raw);self.assertNotIn(b'secret',clean);self.assertNotIn(b'gps',clean);self.assertIn(b'pixels',clean)
  box=lambda tag,data:struct.pack('>I4s',len(data)+8,tag)+data
  raw=box(b'moov',box(b'udta',b'GPS')+box(b'mvhd',b'technical'))+box(b'mdat',b'pixels');clean=mp4_clean(raw);self.assertNotIn(b'GPS',clean);self.assertIn(b'pixels',clean)
  with self.assertRaises(ValueError):mp4_clean(box(b'secr',b'private'))
 def test_verifier_rejects_all_duplicate_sensitive_fields_and_dates(self):
  for raw in [b'[{"XMP:Title":"secret"}]',b'[{"QuickTime:CreateDate":"2026:01:01 00:00:00"}]',b'[{"EXIF:GPSLatitude":0,"EXIF:GPSLatitude":45}]']:
   with self.assertRaises(ValueError):verify_tags(raw)
  verify_tags(b'[{"System:FileModifyDate":"2026:01:01", "QuickTime:CreateDate":"0000:00:00 00:00:00","QuickTime:Duration":4}]')

class SocialGatewayTests(unittest.TestCase):
 def test_session_derived_identity_and_disabled_permission(self):
  import test_accounts
  from freeqnap import accounts
  from freeqnap.personal_access import Gateway
  fixture=test_accounts.AccountsTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
  user,token,_=fixture.user();seen=[]
  def broker(action,payload=None):seen.append((action,payload));return {'data_base64':'eA=='} if action=='personal.invoke' else {'id':'safe-ticket'}
  fixture.device.request=broker;gateway=fixture.gateway(token);source={'type':'files','share':'my-files','path':'photo.jpg'}
  gateway.social('prepare',{'source':source,'owner':'b'*32,'recipient':'b'*32,'primary':True})
  action,payload=seen[-1];self.assertEqual(action,'personal.social-prepare');self.assertEqual(payload['owner'],user['id']);self.assertEqual(payload['recipient'],user['id']);self.assertFalse(payload['primary'])
  accounts.change(fixture.state,fixture.admin,{'action':'update','id':user['id'],'enabled':False})
  with self.assertRaises(PermissionError):gateway.social('read',{'source':source,'id':'safe-ticket'})
 def test_without_external_share_right_never_calls_broker(self):
  import test_accounts
  fixture=test_accounts.AccountsTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
  user,token,_=fixture.user(permissions=['files.read']);fixture.device.calls.clear()
  with self.assertRaises(PermissionError):fixture.gateway(token).social('prepare',{'source':{'type':'files','share':'my-files','path':'photo.jpg'}})
  self.assertFalse(fixture.device.calls)
