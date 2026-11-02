import importlib.util,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('cooling_fault',Path(__file__).resolve().parents[1]/'tools/cooling-fault-validation.py')
fault=importlib.util.module_from_spec(spec);spec.loader.exec_module(fault)

class CoolingFaultScopeTests(unittest.TestCase):
    def test_default_preflight_never_signals_writes_or_changes_fan_mode(self):
        value={'level':7,'cpu_c':50,'disks_c':[33]*4}
        with patch.object(fault.os,'umask'),patch.object(fault,'read_plan',return_value={'body':{}}),patch.object(fault.cooling,'configuration',return_value={'mode':'full'}),patch.object(fault.cooling,'attended_trial',return_value=None),patch.object(fault.cooling,'sample',return_value=value),patch.object(fault.cooling,'decide',return_value={'fault':False}),patch.object(fault.cooling,'full') as full,patch.object(fault.os,'kill') as kill,patch.object(fault,'atomic') as write,patch('sys.argv',['fault','--plan','private-plan.json']),patch('builtins.print'):
            fault.main();full.assert_not_called();kill.assert_not_called();write.assert_not_called()
