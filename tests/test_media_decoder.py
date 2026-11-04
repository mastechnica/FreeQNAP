import contextlib,fcntl,os,stat,subprocess,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from freeqnap.nas.personal_metadata import decode,managed_decode

class ManagedDecoderTests(unittest.TestCase):
 def exercise(self,timeout=False):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);source=root/'original';source.write_bytes(b'original bytes');real_open=os.open
   with source.open('r+b') as stream:
    def mapped(value):return root/'private-output' if str(value)=='/var/lib/freeqnap-system/decoder-output' else Path(value)
    def opener(path,flags,*a,**kw):return real_open(source,os.O_RDONLY) if str(path).startswith('/proc/self/fd/') else real_open(path,flags,*a,**kw)
    calls=[]
    def run(command,**kwargs):
     calls.append(command)
     if command[0]=='systemctl':return SimpleNamespace(returncode=0)
     self.assertIn('--property=User=nobody',command);self.assertIn('--property=PrivateNetwork=yes',command);self.assertIn('--property=RestrictSUIDSGID=yes',command);self.assertIn('--property=NoNewPrivileges=yes',command)
     stdin=next(v for v in command if v.startswith('--property=StandardInput=file:'))
     inherited=int(stdin.rsplit('/',1)[1]);self.assertEqual(fcntl.fcntl(inherited,fcntl.F_GETFL)&os.O_ACCMODE,os.O_RDONLY)
     self.assertEqual(command[-5:],['--','/usr/bin/fixture','-fd','0','fd:'])
     if timeout:raise subprocess.TimeoutExpired(command,10)
     output=next(v.split('file:',1)[1] for v in command if v.startswith('--property=StandardOutput=file:'));Path(output).write_bytes(b'derived output')
     return SimpleNamespace(returncode=0)
    with patch('freeqnap.nas.personal_metadata.Path',side_effect=mapped),patch.object(Path,'lstat',return_value=SimpleNamespace(st_mode=stat.S_IFDIR|0o700,st_uid=0)),patch('freeqnap.nas.personal_metadata.os.open',side_effect=opener),patch('freeqnap.nas.personal_metadata.subprocess.run',side_effect=run):
     if timeout:
      with self.assertRaisesRegex(ValueError,'time limit'):managed_decode(stream.fileno(),'/usr/bin/fixture',['-fd',str(stream.fileno()),'fd:'],10,384*1024**2)
      self.assertEqual(calls[-1][0:2],['systemctl','stop']);self.assertTrue(calls[-1][-1].startswith('freeqnap-decoder-'))
     else:self.assertEqual(managed_decode(stream.fileno(),'/usr/bin/fixture',['-fd',str(stream.fileno()),'fd:'],10,384*1024**2),b'derived output')
    self.assertEqual(source.read_bytes(),b'original bytes')
 def test_manager_receives_readonly_input_and_preserves_service_protections(self):self.exercise()
 def test_timeout_stops_only_its_exact_helper(self):self.exercise(timeout=True)
 def test_service_path_uses_manager_without_an_in_service_setuid(self):
  with patch('freeqnap.nas.personal_metadata.managed_decoder',return_value=True),patch('freeqnap.nas.personal_metadata.shutil.which',return_value='/usr/bin/ffmpeg'),patch('freeqnap.nas.personal_metadata.managed_decode',return_value=b'jpeg') as call:
   self.assertEqual(decode(123,'ffmpeg',['-i','fd:'],memory_limit=384*1024**2),b'jpeg');self.assertEqual(call.call_args.args[0:2],(123,'/usr/bin/ffmpeg'))
