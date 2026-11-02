import unittest
from freeqnap.nas.crypto_profiles import profile,format_args
class CryptoProfiles(unittest.TestCase):
 def test_xts_double_key_sizes_and_bounded_kdf(self):
  for ident,bits in [('aes256-xts',512),('aes128-xts',256)]:
   p=profile(ident);args=format_args(ident);self.assertEqual(p['key_bits'],bits);self.assertEqual(args[args.index('--key-size')+1],str(bits));self.assertEqual(p['cipher'],'aes-xts-plain64');self.assertEqual(p['pbkdf'],'argon2id');self.assertEqual(p['memory_kib'],131072)
 def test_unrecognized_profiles_fail_closed(self):
  for v in ['cbc','plain','none','aes512',{},None]:
   with self.assertRaises(ValueError):format_args(v)
