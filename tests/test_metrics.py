import unittest,tempfile,time,json
from pathlib import Path
from types import SimpleNamespace
from freeqnap.state import State
from freeqnap.nas.metrics import Metrics,rates
class MetricsTests(unittest.TestCase):
 def test_counter_resets_and_history(self):
  self.assertIsNone(rates(100,10,30));self.assertIsNone(rates(1,2,0));self.assertEqual(rates(0,300,30),10)
  with tempfile.TemporaryDirectory() as root:
   m=Metrics(SimpleNamespace(state=State(Path(root))));now=time.time()
   with m.ctx.state.connect() as db:
    db.execute('INSERT INTO system_metrics VALUES(?,?)',(now,json.dumps({'time':now,'cpu':25})))
   self.assertFalse(m.history({'hours':1})['stale']);self.assertEqual(len(m.history({'hours':24})['points']),1)
   with self.assertRaises(ValueError):m.history({'hours':100})
 def test_hourly_rollups_split_weighted_and_ignore_gaps(self):
  with tempfile.TemporaryDirectory() as root:
   m=Metrics(SimpleNamespace(state=State(Path(root))));now=time.time();boundary=int(now//3600)*3600
   with m.ctx.state.connect() as db:
    m.accumulate(db,boundary-10,boundary+20,100,200)
    rows=db.execute('SELECT * FROM network_hours ORDER BY hour').fetchall()
   self.assertEqual(len(rows),2);self.assertEqual(sum(r['seconds'] for r in rows),30)
   data=m.network_history({});self.assertEqual(data['periods'][0]['rx_average'],100)
   self.assertEqual(data['periods'][0]['tx_bytes'],6000)
   self.assertTrue(data['stale']);self.assertEqual(data['periods'][3]['observed_seconds'],30)
 def test_empty_network_history_is_unknown_not_zero_average(self):
  with tempfile.TemporaryDirectory() as root:
   m=Metrics(SimpleNamespace(state=State(Path(root))))
   self.assertIsNone(m.network_history({})['periods'][0]['rx_average'])
