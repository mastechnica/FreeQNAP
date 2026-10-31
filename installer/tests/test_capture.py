import json
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import tempfile
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import Console

class CaptureTest(unittest.TestCase):
 def test_real_broker_and_autoboot_after_long_banner(self):
  master,slave=pty.openpty();name=os.ttyname(slave)
  with tempfile.TemporaryDirectory() as folder:
   capture=Path(folder)/'capture';capture.mkdir()
   process=subprocess.Popen([sys.executable,str(Path(__file__).resolve().parents[1]/'capture.py'),'--port',name,'--directory',str(capture),'--stop-autoboot'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
   try:
    deadline=time.monotonic()+5
    while not (capture/'ready.json').exists():
     if process.poll() is not None:self.fail(process.stderr.read().decode())
     if time.monotonic()>deadline:self.fail('capture not ready')
     time.sleep(.02)
    os.write(master,b'U-Boot 2015.07-alpine_db-test\r\n'+b'x'*5000+b'\r\nHit any key to stop autoboot: 10')
    self.assertTrue(select.select([master],[],[],5)[0]);self.assertEqual(os.read(master,32),b' ')
    os.write(master,b'\r\nALPINE_DB> \r\nExecuting application...\r\nU-Boot 2015.07-alpine_db-test\r\nHit any key to stop autoboot: 10')
    self.assertTrue(select.select([master],[],[],5)[0]);self.assertEqual(os.read(master,32),b' ')
    os.write(master,b'\r\nALPINE_DB> ');time.sleep(.1)
    console=Console(capture);console.send('version\r')
    self.assertTrue(select.select([master],[],[],5)[0]);self.assertEqual(os.read(master,100),b'version\r')
    self.assertTrue(console.arm_autoboot()['armed']);self.assertFalse(select.select([master],[],[],.1)[0])
    os.write(master,b'Hit any key to stop autoboot: 10');self.assertFalse(select.select([master],[],[],.1)[0])
    os.write(master,b'\r\nU-Boot 2015.07-alpine_db-test\r\n');self.assertFalse(select.select([master],[],[],.1)[0])
    os.write(master,b'Hit any key to stop autoboot: 10')
    self.assertTrue(select.select([master],[],[],5)[0]);self.assertEqual(os.read(master,32),b' ')
    self.assertEqual((capture/'console.bin').stat().st_mode&0o777,0o600)
    self.assertEqual((capture/'ready.json').stat().st_mode&0o777,0o600)
    self.assertFalse(console.request({'disarm_autoboot':True})['armed'])
    os.write(master,b'\r\nExecuting application...\r\nU-Boot 2015.07-alpine_db-test\r\nHit any key to stop autoboot: 10')
    self.assertFalse(select.select([master],[],[],.2)[0])
   finally:
    process.terminate();process.wait(timeout=5);process.stderr.close();os.close(master);os.close(slave)

if __name__=='__main__':unittest.main()
