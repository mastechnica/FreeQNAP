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
