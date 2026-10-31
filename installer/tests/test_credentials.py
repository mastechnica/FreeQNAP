import importlib.util
from pathlib import Path
import unittest
import warnings
import getpass
import tempfile
from unittest.mock import patch

path=Path(__file__).resolve().parents[1]/'target/credentials.py'
spec=importlib.util.spec_from_file_location('credentials',path);credentials=importlib.util.module_from_spec(spec);spec.loader.exec_module(credentials)

class CredentialTests(unittest.TestCase):
 def test_deferral_retains_locked_password_and_requires_key_and_key_only_policy(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory)
   for sub in ('root/.ssh','etc/freeqnap','etc/ssh/sshd_config.d'):(root/sub).mkdir(parents=True,exist_ok=True)
   key=root/'root/.ssh/authorized_keys';key.write_text('ssh-ed25519 test-public-key\n');key.chmod(0o600)
   shadow=root/'etc/shadow';shadow.write_text('root:!:20000:0:99999:7:::\n')
   config=root/'etc/ssh/sshd_config.d/00-freeqnap.conf';config.write_text('PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitEmptyPasswords no\nPermitRootLogin prohibit-password\n')
   marker=root/'etc/freeqnap/require-root-password';marker.touch()
   with patch.object(credentials,'identified_root',return_value=root),patch.object(credentials.os,'geteuid',return_value=key.stat().st_uid):
    credentials.password_defer(root,'a'*32)
    self.assertEqual(shadow.read_text(),'root:!:20000:0:99999:7:::\n');self.assertFalse(marker.exists());self.assertTrue((root/'etc/freeqnap/root-password-deferred').exists())
    key.chmod(0o644)
    with self.assertRaises(ValueError):credentials.password_defer(root,'a'*32)
    key.chmod(0o600);shadow.write_text('root:$existing-hash:20000:0:99999:7:::\n')
    with self.assertRaises(ValueError):credentials.password_defer(root,'a'*32)
    shadow.write_text('root:!:20000:0:99999:7:::\n');config.write_text('PasswordAuthentication yes\n')
    with self.assertRaises(ValueError):credentials.password_defer(root,'a'*32)
 def test_hidden_confirmation(self):
  answers=iter(['example-passphrase-2026','example-passphrase-2026'])
  self.assertEqual(credentials.prompt_password(lambda _:next(answers)),'example-passphrase-2026')
 def test_mismatch_and_injection_rejected(self):
  answers=iter(['example-passphrase-2026','different-passphrase-2026'])
  with self.assertRaises(ValueError):credentials.prompt_password(lambda _:next(answers))
  for password in ('short','x'*1025,'long-passphrase\nroot:injected','long-passphrase\r','long-passphrase\0'):
   with self.assertRaises(ValueError):credentials.validate_password(password)
 def test_echoed_fallback_is_forbidden(self):
  def reader(_):warnings.warn('no private terminal',getpass.GetPassWarning);return 'example-passphrase-2026'
  with self.assertRaises(getpass.GetPassWarning):credentials.prompt_password(reader)
 def test_no_payload_in_validation_error(self):
  password='secret-payload\nsecond-user'
  with self.assertRaises(ValueError) as result:credentials.validate_password(password)
  self.assertNotIn('secret-payload',str(result.exception))

if __name__=='__main__':unittest.main()
