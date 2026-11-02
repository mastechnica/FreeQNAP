import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from freeqnap.nas.cooling import Cooling

class WatchdogHealthTests(unittest.TestCase):
    def test_configured_but_inactive_reports_critical_without_opening_device(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config=root/'policy.conf';base=root/'sysfs';base.mkdir()
            for n,v in {'identity':'sp805-wdt','state':'inactive','timeout':'10','nowayout':'0'}.items():(base/n).write_text(v)
            with patch('freeqnap.nas.cooling.WATCHDOG_CONFIG',config),patch('freeqnap.nas.cooling.WATCHDOG_SYSFS',base):
                self.assertEqual(Cooling().watchdog_health(),[])
                config.write_text('[Manager]\nRuntimeWatchdogSec=10s\n')
                self.assertEqual(Cooling().watchdog_health()[0]['severity'],'critical')
                (base/'state').write_text('active')
                self.assertEqual(Cooling().watchdog_health(),[])
                (base/'identity').unlink()
                self.assertEqual(Cooling().watchdog_health()[0]['severity'],'critical')
