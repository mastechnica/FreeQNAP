import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from freeqnap import cooling

class CoolingRuntimeTests(unittest.TestCase):
    def test_guard_and_lease_freshness(self):
        self.assertTrue(cooling.guardian_valid({'boot_id':'a','monotonic':10,'ready':True},11,'a'))
        for v in ({}, {'boot_id':'a','monotonic':8,'ready':True},{'boot_id':'b','monotonic':10,'ready':True},{'boot_id':'a','monotonic':12,'ready':True}):
            self.assertFalse(cooling.guardian_valid(v,11,'a'))
        self.assertTrue(cooling.lease_valid({'boot_id':'a','expires':12,'level':6},11,'a'))
        for v in ({'boot_id':'a','expires':10,'level':6},{'boot_id':'a','expires':20,'level':6},{'boot_id':'a','expires':12,'level':0}):
            self.assertFalse(cooling.lease_valid(v,11,'a'))

    def test_no_low_levels(self):
        with patch.object(cooling,'board') as board:
            for v in (0,1,5,8,True,'6'):
                with self.assertRaises(ValueError):cooling.set_level(v)
            board.assert_not_called()

    def test_configuration_missing_defaults_full(self):
        with patch.object(cooling,'trusted',side_effect=FileNotFoundError):
            self.assertEqual(cooling.configuration()['mode'],'full')
            self.assertFalse(cooling.accepted())

    def test_error_does_not_blindly_retry(self):
        bad=subprocess.CompletedProcess([],1,b'',b'bad ACK')
        with patch.object(cooling.subprocess,'run',return_value=bad) as run:
            with self.assertRaisesRegex(ValueError,'bad ACK'):cooling.full()
            self.assertEqual(run.call_count,1)

    def test_pid_is_bound_to_boot_and_start(self):
        with patch.object(cooling,'boot_id',return_value='a'),patch.object(cooling,'ticks',return_value='77'):
            self.assertTrue(cooling.alive({'pid':42,'boot_id':'a','start_ticks':'77'}))
            for p in ({'pid':1,'boot_id':'a','start_ticks':'77'},{'pid':42,'boot_id':'b','start_ticks':'77'},{'pid':42,'boot_id':'a','start_ticks':'78'}):
                self.assertFalse(cooling.alive(p))

    def test_guard_latches_before_killing_owner_and_restoring(self):
        events=[]
        lease={'pid':42,'start_ticks':'77','boot_id':'a','expires':0,'level':6,'generation':'g'}
        with tempfile.TemporaryDirectory() as tmp, patch.object(cooling,'RUNTIME',Path(tmp)), patch.object(cooling,'board'), patch.object(cooling,'singleton',return_value=7), patch.object(cooling,'boot_id',return_value='a'), patch.object(cooling,'trusted',return_value=lease), patch.object(cooling,'alive',return_value=True), patch.object(cooling,'full',side_effect=lambda:events.append(('full',))), patch.object(cooling,'publish',side_effect=lambda name,value:events.append((name,value))), patch.object(cooling.os,'kill',side_effect=lambda pid,sig:events.append(('kill',pid))), patch.object(cooling.time,'sleep',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):cooling.guardian()
        kill=next(i for i,e in enumerate(events) if e[0]=='kill')
        self.assertTrue(any(e[0]=='guard.json' and e[1]['ready'] is False for e in events[:kill]))
        self.assertTrue(any(e[0]=='fault.json' and e[1]['generation']=='g' for e in events[:kill]))
        self.assertEqual(events[kill+1],('full',))
        self.assertTrue(any(e[0]=='fault.json' and e[1]['full_verified'] is True for e in events[kill+2:]))

    def test_attended_trial_expires_and_binds_exact_install_and_boot(self):
        trial={'owner_watching':True,'boot_id':'a','install_id':'unit','generation':'a'*32,'started':10,'deadline':610,'lease_expires':22}
        self.assertTrue(cooling.trial_valid(trial,20,'a','unit'))
        for now,boot,unit in [(9,'a','unit'),(610,'a','unit'),(20,'b','unit'),(20,'a','other')]:
            self.assertFalse(cooling.trial_valid(trial,now,boot,unit))
        for changes in ({'deadline':1811},{'owner_watching':False},{'generation':'bad'},{'started':True},{'lease_expires':19},{'lease_expires':24}):
            self.assertFalse(cooling.trial_valid({**trial,**changes},20,'a','unit'))

    def test_dead_trial_owner_cannot_authorize_reduction(self):
        with patch.object(cooling,'trusted',return_value={}),patch.object(cooling,'trial_valid',return_value=True),patch.object(cooling,'boot_id',return_value='a'),patch.object(cooling.Path,'read_text',return_value='unit'),patch.object(cooling,'alive',return_value=False):
            self.assertIsNone(cooling.attended_trial())
