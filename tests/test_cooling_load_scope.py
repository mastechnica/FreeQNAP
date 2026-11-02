import importlib.util
import unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('cooling_load',Path(__file__).resolve().parents[1]/'tools/cooling-load-validation.py')
load=importlib.util.module_from_spec(spec);spec.loader.exec_module(load)

class CoolingLoadScopeTests(unittest.TestCase):
    def test_initial_guard_stays_supported(self):
        self.assertTrue(load.thermal_scope({'cpu_stop_c':65,'disk_stop_c':48}))
    def test_reviewed_guard_needs_exact_basis_and_unchanged_kernel_trip(self):
        b={'cpu_stop_c':70,'disk_stop_c':48,'thermal_basis':'stock-dts-105-current-trip-80'}
        self.assertTrue(load.thermal_scope(b,80000))
        for trip in (None,70000,90000,105000):self.assertFalse(load.thermal_scope(b,trip))
        self.assertFalse(load.thermal_scope({**b,'thermal_basis':'unknown'},80000))
    def test_higher_or_malformed_limits_refused(self):
        for cpu in (70.0,True,75,80,105):
            self.assertFalse(load.thermal_scope({'cpu_stop_c':cpu,'disk_stop_c':48,'thermal_basis':'stock-dts-105-current-trip-80'},80000))
