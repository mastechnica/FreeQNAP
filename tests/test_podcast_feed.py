import io,unittest
from xml.etree import ElementTree as ET
from freeqnap.nas.podcast_feed import snapshot
class PodcastFeedTests(unittest.TestCase):
 def test_recent_snapshot_is_bounded_and_retains_feed_identity_and_enclosures(self):
  raw=('<rss><channel><title>Show</title><description>About</description>'+''.join('<item><title>Episode '+str(i)+'</title><guid>'+str(i)+'</guid><enclosure url="https://public.example/'+str(i)+'.mp3" type="audio/mpeg"/></item>' for i in range(700))+'</channel></rss>').encode();out=ET.fromstring(snapshot(io.BytesIO(raw),max_items=3));self.assertEqual(out.findtext('channel/title'),'Show');items=out.findall('channel/item');self.assertEqual(len(items),3);self.assertEqual(items[0].findtext('guid'),'0');self.assertEqual(items[-1].find('enclosure').get('url'),'https://public.example/2.mp3')
 def test_atom_namespaces_are_normalized(self):
  raw=b'<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom</title><entry><title>One</title><id>one</id><published>date</published><link rel="enclosure" href="https://public.example/a.mp3" type="audio/mpeg"/></entry></feed>';out=ET.fromstring(snapshot(io.BytesIO(raw)));self.assertEqual(out.findtext('channel/title'),'Atom');self.assertEqual(out.findtext('channel/item/guid'),'one')
 def test_entities_and_input_limit_are_rejected(self):
  for raw in [b'<!DOCTYPE rss [<!ENTITY x "unsafe">]><rss/>',b'<rss><channel>'+b'x'*200]:
   with self.assertRaises(ValueError):snapshot(io.BytesIO(raw),max_input=100)
 def test_incomplete_xml_is_not_a_success_without_a_complete_episode(self):
  with self.assertRaises(ValueError):snapshot(io.BytesIO(b'<rss><channel><item><title>unfinished'))

 def test_truncated_tail_and_excessive_nesting_are_rejected(self):
  for raw in [b'<rss><channel><item><title>One</title></item>',b'<rss>'+b'<x>'*65]:
   with self.assertRaises(ValueError):snapshot(io.BytesIO(raw))
