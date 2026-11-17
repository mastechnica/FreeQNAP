import os
from pathlib import Path
from unittest.mock import patch
import unittest,test_myradio
from freeqnap.nas.prepared_audio import register
class PreparedAudioTests(unittest.TestCase):
 setUp=test_myradio.MyRadioTests.setUp
 upload=test_myradio.MyRadioTests.upload
 def test_replacement_requires_exact_old_identity_and_updates_filename(self):
  old=self.upload(b'old','book.m4b');item=self.radio.asset(old['id']);folder=self.volume/'.freeqnap-myradio'/'books'/old['id'];(folder/'new.m4b').write_bytes(b'new audio')
  with self.assertRaises(ValueError):register(self.radio,'books',old['id'],'new.m4b',{'title':'New'})
  pin={k:item[k] for k in ('path','inode','bytes','mtime_ns')};bad={**pin,'inode':-1}
  with self.assertRaises(ValueError):register(self.radio,'books',old['id'],'new.m4b',{'title':'New'},replace_identity=bad)
  result=register(self.radio,'books',old['id'],'new.m4b',{'title':'New','author':'Writer'},replace_identity=pin)
  self.assertEqual(result['name'],'new.m4b');self.assertEqual(result['metadata']['playable'],'audio');self.assertTrue((folder/'book.m4b').exists())
 def test_prepared_identity_avoids_redecoding_but_preserves_manual_edits(self):
  old=self.upload(b'music','music.mp3','music');register(self.radio,'music',old['id'],'music.mp3',{'title':'Tagged title','artist':'Artist','album':'Album'})
  self.radio.metadata({'id':old['id'],'metadata':{'title':'My edit'}})
  with patch('freeqnap.nas.myradio.audio_metadata',side_effect=AssertionError('Unneeded decode')):self.assertTrue(self.radio.scan({})['complete'])
  self.assertEqual(self.radio.asset(old['id'])['metadata']['title'],'My edit')
 def test_invalid_metadata_cover_and_link_are_rejected(self):
  old=self.upload(b'music','music.mp3','music')
  for fields in ({'owner':'forged'},{'duration':float('nan')},{'title':'bad\x00title'}):
   with self.assertRaises(ValueError):register(self.radio,'music',old['id'],'music.mp3',fields)
  with self.assertRaises(ValueError):register(self.radio,'music',old['id'],'music.mp3',{},b'<svg/>')
  folder=self.volume/'.freeqnap-myradio'/'music'/old['id'];target=folder.parent/('b'*32);target.mkdir();(target/'link.mp3').symlink_to(folder/'music.mp3')
  with self.assertRaises(OSError):register(self.radio,'music','b'*32,'link.mp3',{})
 def test_ape_is_retained_without_a_false_browser_playback_claim(self):
  old=self.upload(b'music','song.ape','music');r=register(self.radio,'music',old['id'],'song.ape',{'title':'Lossless'})
  self.assertEqual(r['metadata']['playable'],'original-only')

 def test_proven_missing_audio_is_not_advertised_as_playable(self):
  old=self.upload(b'tag-only','missing.mp3','music');v=register(self.radio,'music',old['id'],'missing.mp3',{'title':'Song','disc':'2','audio_status':'unavailable','metadata_sources':{'title':'reviewed-online'}})
  self.assertEqual(v['metadata']['playable'],'original-only');self.assertIn('decodable audio',v['metadata']['reading_note']);self.assertEqual(v['metadata']['disc'],'2')

 def test_batch_flushes_artifacts_before_catalog_commit_and_preserves_audio(self):
  from freeqnap.nas.prepared_audio import batch
  import hashlib,json
  old=self.upload(b'unchanged audio','song.mp3','music');item=self.radio.asset(old['id']);folder=self.volume/'.freeqnap-myradio'/'music'/old['id'];audio=folder/'song.mp3';before=(audio.stat().st_ino,hashlib.sha256(audio.read_bytes()).hexdigest());seen=[]
  def synced(fd):
   self.assertEqual(json.loads((folder/'metadata.json').read_text())['title'],'Reviewed')
   self.assertNotEqual(self.radio.asset(old['id'])['metadata']['title'],'Reviewed');seen.append(True)
  with self.radio.root() as root,patch('freeqnap.nas.prepared_audio._sync_filesystem',side_effect=synced):
   with batch(self.radio,root) as (writer,db):register(writer,'music',old['id'],'song.mp3',{'title':'Reviewed'},root_fd=root,connection=db)
  self.assertEqual(seen,[True]);self.assertEqual(self.radio.asset(old['id'])['metadata']['title'],'Reviewed');self.assertEqual((audio.stat().st_ino,hashlib.sha256(audio.read_bytes()).hexdigest()),before)

 def test_batch_flush_failure_rolls_back_catalog_and_retains_reconcilable_metadata(self):
  from freeqnap.nas.prepared_audio import batch
  import json
  old=self.upload(b'original','song.mp3','music');before=self.radio.asset(old['id']);folder=self.volume/'.freeqnap-myradio'/'music'/old['id']
  with self.radio.root() as root,patch('freeqnap.nas.prepared_audio._sync_filesystem',side_effect=OSError('fixture flush failure')):
   with self.assertRaises(OSError):
    with batch(self.radio,root) as (writer,db):register(writer,'music',old['id'],'song.mp3',{'title':'Staged'},root_fd=root,connection=db)
  self.assertEqual(self.radio.asset(old['id'])['metadata'],before['metadata']);self.assertEqual(json.loads((folder/'metadata.json').read_text())['title'],'Staged');self.assertEqual((folder/'song.mp3').read_bytes(),b'original')

 def test_batch_exception_and_repeated_identity_do_not_commit_partial_catalog(self):
  from freeqnap.nas.prepared_audio import batch
  old=self.upload(b'original','song.mp3','music');before=self.radio.asset(old['id'])
  with self.radio.root() as root,patch('freeqnap.nas.prepared_audio._sync_filesystem') as flush:
   with self.assertRaises(ValueError):
    with batch(self.radio,root) as (writer,db):
     register(writer,'music',old['id'],'song.mp3',{'title':'One'},root_fd=root,connection=db)
     register(writer,'music',old['id'],'song.mp3',{'title':'Two'},root_fd=root,connection=db)
   flush.assert_not_called()
  self.assertEqual(self.radio.asset(old['id'])['metadata'],before['metadata'])

 def test_batch_cannot_overwrite_an_original_or_accept_an_unmarked_root(self):
  from freeqnap.nas.prepared_audio import batch
  with self.radio.root() as root,patch('freeqnap.nas.prepared_audio._sync_filesystem'):
   with batch(self.radio,root) as (writer,db):
    with self.assertRaises(ValueError):writer.write_file(root,'original.mp3',b'forbidden')
  fd=os.open(self.volume,os.O_RDONLY|os.O_DIRECTORY)
  try:
   with self.assertRaises((ValueError,OSError)):
    with batch(self.radio,fd):pass
  finally:os.close(fd)

 def test_batch_supports_maximum_length_metadata_names(self):
  from freeqnap.nas.prepared_audio import batch
  leaf='x'*241+'.metadata.json'
  self.assertEqual(len(leaf.encode()),255)
  with self.radio.root() as root,patch('freeqnap.nas.prepared_audio._sync_filesystem'):
   with batch(self.radio,root) as (writer,db):writer.write_file(root,leaf,b'{"verified":true}')
  self.assertEqual((self.volume/'.freeqnap-myradio'/leaf).read_bytes(),b'{"verified":true}')
