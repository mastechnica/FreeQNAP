import unittest
import contextlib
from pathlib import Path
from unittest.mock import patch
from freeqnap.nas.cooling import Cooling

class CoolingControlTests(unittest.TestCase):
    def test_unaccepted_auto_refused_before_hardware_or_config(self):
        with patch('freeqnap.nas.cooling.cooling.accepted',return_value=False), patch('freeqnap.nas.cooling.cooling.board') as board, patch('freeqnap.nas.cooling.atomic') as write:
            with self.assertRaisesRegex(ValueError,'unavailable'):Cooling().mode({'mode':'auto'})
            board.assert_not_called();write.assert_not_called()

    def test_full_intent_is_saved_before_hardware_request(self):
        events=[]
        with patch('freeqnap.nas.cooling.cooling.control_lock',side_effect=contextlib.nullcontext), patch('freeqnap.nas.cooling.cooling.RUNTIME',Path('/nonexistent-freeqnap-test-runtime')), patch('freeqnap.nas.cooling.cooling.board'), patch('freeqnap.nas.cooling.cooling.full',side_effect=lambda:events.append('full')), patch('freeqnap.nas.cooling.atomic',side_effect=lambda *a,**k:events.append('save')):
            self.assertTrue(Cooling().mode({'mode':'full'})['applied'])
        self.assertEqual(events,['save','full'])

    def test_failed_hardware_keeps_full_speed_intent(self):
        with patch('freeqnap.nas.cooling.cooling.control_lock',side_effect=contextlib.nullcontext), patch('freeqnap.nas.cooling.cooling.RUNTIME',Path('/nonexistent-freeqnap-test-runtime')), patch('freeqnap.nas.cooling.cooling.board'), patch('freeqnap.nas.cooling.cooling.full',side_effect=ValueError('bad ACK')), patch('freeqnap.nas.cooling.atomic') as write:
            with self.assertRaisesRegex(ValueError,'bad ACK'):Cooling().mode({'mode':'full'})
            write.assert_called_once()
            self.assertEqual(write.call_args.args[1]['mode'],'full')

    def test_extra_fields_and_low_speed_refused(self):
        for r in ({'mode':'low'},{'mode':'auto','speed':0},{'mode':True},{}):
            with self.assertRaises(ValueError):Cooling().mode(r)
