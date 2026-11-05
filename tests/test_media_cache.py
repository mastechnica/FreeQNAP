import unittest
from freeqnap import media_cache

class MediaCacheTests(unittest.TestCase):
 def test_only_previews_and_artwork_are_cacheable(self):
  self.assertTrue(media_cache.preview_resource(True,False,'thumbnail','x.jpg',True));self.assertTrue(media_cache.preview_resource(False,True,'cover','cover.jpg',True));self.assertTrue(media_cache.preview_resource(False,False,None,'Movie/poster.jpg',True));self.assertFalse(media_cache.preview_resource(True,False,'original','private.jpg',True));self.assertFalse(media_cache.preview_resource(False,False,None,'passwords.txt',False))
 def test_revalidation_is_scoped_and_not_a_public_fresh_cache(self):
  a=media_cache.tag('file','user-a','share-a');self.assertNotEqual(a,media_cache.tag('file','user-b','share-a'));self.assertNotEqual(a,media_cache.tag('file','user-a','share-b'));self.assertTrue(media_cache.matches('W/'+a,a));self.assertTrue(media_cache.matches('"other", '+a,a));self.assertFalse(media_cache.matches('"other"',a));self.assertIn('private',media_cache.POLICY);self.assertIn('no-cache',media_cache.POLICY);self.assertIn('must-revalidate',media_cache.POLICY)
