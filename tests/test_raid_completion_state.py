import unittest
from tools.raid_completion_state import completion_ready

class CompletionStateTests(unittest.TestCase):
    def test_os_resync_queued_behind_data_recovery(self):
        self.assertFalse(completion_ready(0,"resync","delayed",1,"recover"))
    def test_scheduled_os_check_queued_behind_data_recovery(self):
        self.assertFalse(completion_ready(0,"check","delayed",1,"recover"))
    def test_os_resync_running_after_data_finished(self):
        self.assertFalse(completion_ready(0,"resync","100 / 200",0,"idle"))
    def test_both_arrays_required_for_acceptance(self):
        self.assertTrue(completion_ready(0,"idle","none",0,"idle"))
        self.assertFalse(completion_ready(0,"idle","none",1,"recover"))
    def test_degraded_os_refused(self):
        with self.assertRaises(ValueError):completion_ready(1,"resync","delayed",1,"recover")
    def test_stopped_degraded_data_refused(self):
        with self.assertRaises(ValueError):completion_ready(0,"idle","none",1,"idle")
    def test_unexpected_reshape_refused(self):
        with self.assertRaises(ValueError):completion_ready(0,"reshape","100 / 200",1,"recover")
    def test_unexplained_delay_refused(self):
        with self.assertRaises(ValueError):completion_ready(0,"resync","delayed",0,"idle")
