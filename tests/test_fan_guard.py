import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('fan_step', Path(__file__).resolve().parents[1] / 'tools/fan-step-validation.py')
fan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fan)


class FanGuardTests(unittest.TestCase):
    def test_retries_only_lock_contention(self):
        busy = subprocess.CompletedProcess([], 2, b'', b'MCU lock: Resource temporarily unavailable')
        ok = subprocess.CompletedProcess([], 0, b'', b'')
        with patch.object(fan.subprocess, 'run', side_effect=[busy, ok]) as run, patch.object(fan, 'snapshot', return_value={'level': 7}), patch.object(fan.time, 'sleep'):
            self.assertEqual(fan.full(), {'level': 7})
            self.assertEqual(run.call_count, 2)

    def test_protocol_error_is_retained_without_retry(self):
        bad = subprocess.CompletedProcess([], 1, b'', b'MCU full-speed ACK/readback unavailable')
        with patch.object(fan.subprocess, 'run', return_value=bad) as run:
            with self.assertRaisesRegex(ValueError, 'ACK/readback unavailable'):
                fan.full()
            self.assertEqual(run.call_count, 1)

    def test_lock_wait_is_bounded(self):
        busy = subprocess.CompletedProcess([], 2, b'', b'MCU lock: Resource temporarily unavailable')
        with patch.object(fan.subprocess, 'run', return_value=busy) as run, patch.object(fan.time, 'monotonic', side_effect=[0, 5]):
            with self.assertRaisesRegex(ValueError, 'MCU lock:'):
                fan.full()
            self.assertEqual(run.call_count, 1)
