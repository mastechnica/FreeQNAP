import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from freeqnap.nas.common import Context
from freeqnap.nas.storage import Storage
class StartupDiscovery(unittest.TestCase):
 def test_partition_tags_settle_before_exact_resolution(self):
  with tempfile.TemporaryDirectory() as directory:
   settled=[]
   def run(*args,**kwargs):
    if args==('blockdev','--getro','/dev/fixture'):return '0'
    self.assertEqual(args,('udevadm','settle','--timeout=15'));settled.append(True);return ''
   ctx=Context(Path(directory),runner=run);config=ctx.config();config['pools']['data']={'name':'data','filesystem_uuid':'fixture-fs','md_uuid':'fixture-md','encrypted':False};ctx.save(config);store=Storage(ctx)
   def device(pool):
    if not settled:raise ValueError('Exact array partition identity/extent unavailable')
    return '/dev/fixture-partition'
   with patch.object(store,'collect',return_value={'disks':[]}),patch.object(store,'array_device',return_value='/dev/fixture'),patch.object(store,'data_device',side_effect=device),patch.object(store,'mount') as mount:
    self.assertEqual(store.startup(),[]);mount.assert_called_once();self.assertEqual(ctx.config()['pools']['data']['block_device'],'/dev/fixture-partition')
 def test_settling_never_overrides_wrong_partition_identity(self):
  with tempfile.TemporaryDirectory() as directory:
   ctx=Context(Path(directory),runner=lambda *a,**kw:'');config=ctx.config();config['pools']['data']={'name':'data','filesystem_uuid':'fixture-fs','encrypted':False};ctx.save(config);store=Storage(ctx)
   with patch.object(store,'collect',return_value={'disks':[]}),patch.object(store,'array_device',return_value='/dev/fixture'),patch.object(store,'data_device',side_effect=ValueError('Exact array partition identity/extent unavailable')),patch.object(store,'mount') as mount:
    errors=store.startup();self.assertEqual(len(errors),1);mount.assert_not_called();self.assertIn('extent',errors[0]['error'])

 def test_manual_readonly_recovery_is_not_turned_into_a_writable_mount_at_restart(self):
  with tempfile.TemporaryDirectory() as directory:
   calls=[]
   def run(*args,**kwargs):calls.append(args);return '1'
   ctx=Context(Path(directory),runner=run);cfg=ctx.config();cfg['pools']['data']={'name':'data','filesystem_uuid':'fixture-fs','md_uuid':'fixture-md','encrypted':False};ctx.save(cfg);store=Storage(ctx)
   with patch.object(store,'collect',return_value={'disks':[]}),patch.object(store,'array_device',return_value='/dev/fixture'),patch.object(store,'mount') as mount:
    errors=store.startup();mount.assert_not_called();self.assertIn('separately confirmed',errors[0]['error'])
    self.assertEqual(calls,[('blockdev','--getro','/dev/fixture')])
