import json,os,tempfile,time,types,unittest
from pathlib import Path
from unittest.mock import patch
from freeqnap.nas.cooling import Cooling

class CoolingHistoryTests(unittest.TestCase):
    def test_bounded_sanitized_history_skips_partial_rows(self):
        real_fstat=os.fstat
        def trusted(fd):
            x=real_fstat(fd);return types.SimpleNamespace(st_uid=0,st_mode=x.st_mode,st_size=x.st_size)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);now=time.time()
            row={'time':now,'boot_id':'PRIVATE-BOOT','generation':'PRIVATE-GEN','level':6,'sample':{'cpu_c':51,'disks_c':[32,33,34,35],'fans':[{'rpm':8000},{'rpm':8010},{'rpm':7680}]}}
            (root/'history.jsonl').write_text(json.dumps(row)+'\n{partial')
            with patch('freeqnap.nas.cooling.HISTORY_DIRECTORY',root),patch('freeqnap.nas.cooling.os.fstat',side_effect=trusted):
                result=Cooling().history({'limit':1})
            self.assertFalse(result['stale']);self.assertEqual(len(result['points']),1)
            self.assertEqual(result['points'][0]['hottest_disk'],35)
            self.assertNotIn('PRIVATE',json.dumps(result))
    def test_bad_limits_and_symlinks_refused(self):
        for request in ({'limit':True},{'limit':241},{'limit':0},{'path':'/etc/shadow'}):
            with self.assertRaises(ValueError):Cooling().history(request)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'history.jsonl').symlink_to('/etc/hosts')
            with patch('freeqnap.nas.cooling.HISTORY_DIRECTORY',root):
                with self.assertRaises(OSError):Cooling().history({})
