import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('watchdog_policy',Path(__file__).resolve().parents[1]/'deploy/configure-watchdog.py')
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)

class WatchdogPolicyTests(unittest.TestCase):
    def base(self):return {'identity':'sp805-wdt','nowayout':'0','manager_microseconds':0,'state':'inactive','timeout_seconds':10}
    def test_inspection_never_opens_watchdog(self):
        with patch.object(w.os,'geteuid',return_value=0),patch.object(w.Path,'read_bytes',return_value=b'qnap,ts-431xeu\0'),patch.object(w,'inspect',return_value=self.base()),patch.object(w,'set_runtime') as arm,patch('sys.argv',['configure-watchdog.py','status']),patch('builtins.print'):
            w.main();arm.assert_not_called()
    def test_enable_requires_physical_receipt(self):
        with patch.object(w.os,'geteuid',return_value=0),patch.object(w.Path,'read_bytes',return_value=b'qnap,ts-431xeu\0'),patch.object(w,'inspect',return_value=self.base()),patch.object(w,'get',return_value=0),patch.object(w,'set_runtime') as arm,patch('sys.argv',['configure-watchdog.py','enable','--apply']):
            with self.assertRaisesRegex(ValueError,'receipt'):w.main()
            arm.assert_not_called()
    def test_irreversible_mode_refused(self):
        value=self.base();value['nowayout']='1'
        with patch.object(w.os,'geteuid',return_value=0),patch.object(w.Path,'read_bytes',return_value=b'qnap,ts-431xeu\0'),patch.object(w,'inspect',return_value=value),patch.object(w,'set_runtime') as arm,patch('sys.argv',['configure-watchdog.py','enable','--apply']):
            with self.assertRaisesRegex(ValueError,'irreversible'):w.main()
            arm.assert_not_called()
