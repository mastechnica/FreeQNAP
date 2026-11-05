import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from freeqnap.transfer_context import collect_context, enrich, metadata_db

class TransferContextTests(unittest.TestCase):
 def test_exact_nested_paths_authorized_rows_only_and_no_staging(self):
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp);owner='a'*32;job='b'*32;plan='c'*32;p=base/'personal'/owner;p.mkdir(parents=True)
   for directory in (base,p):
    with sqlite3.connect(directory/'state.sqlite3') as db:
     db.executescript('CREATE TABLE settings(key TEXT,value TEXT); CREATE TABLE jobs(id TEXT,kind TEXT,payload TEXT,created REAL);')
   with sqlite3.connect(base/'state.sqlite3') as db:db.execute('INSERT INTO settings VALUES(?,?)',('nas',json.dumps({'pools':{'data-1':{'mountpoint':'/data'}},'shares':{'usb':{'path':'/usb'}}})))
   with sqlite3.connect(p/'state.sqlite3') as db:
    db.execute('INSERT INTO settings VALUES(?,?)',('personal-photos',json.dumps({'pool':'data-1','location_folder':'members/example/Photos'})))
    db.execute('INSERT INTO jobs VALUES(?,?,?,?)',(job,'files.transfer',json.dumps({'plan_id':plan}),0))
   (p/'plans').mkdir();(p/'plans'/(plan+'.json')).write_text(json.dumps({'body':{'share':'usb','target_share':'my-photos','target_path':'Import','items':[{'path':'Trip','name':'Trip'}]}}))
   (p/'operations').mkdir();(p/'operations'/(job+'.json')).write_text(json.dumps({'partial_stage':'d'*32,'stage_pool':'data-1'}))
   stage=Path('/data/.freeqnap/transfers')/('d'*32)
   before=(p/'state.sqlite3').read_bytes()
   sample=collect_context(base,opened=[Path('/usb/Trip/Day 2/image.jpg'),stage/'Day 2/image.jpg',Path('/unrelated/secret.txt')])
   value=sample['transfers'][job];self.assertEqual(value['source_file'],'/usb/Trip/Day 2/image.jpg');self.assertEqual(value['destination_file'],'/data/members/example/Photos/Import/Trip/Day 2/image.jpg')
   self.assertEqual(before,(p/'state.sqlite3').read_bytes())
   output=base/'sample.json';output.write_text(json.dumps(sample))
   self.assertEqual(enrich({'transfers':[]},output),{'transfers':[]})
   self.assertNotIn('paths',enrich({'transfers':[{'id':'other-account'}]},output)['transfers'][0])
   self.assertIn('paths',enrich({'transfers':[{'id':job}]},output)['transfers'][0])
   unrelated=collect_context(base,opened=[Path('/usb/Trip/other.jpg')]);self.assertNotIn('source_file',unrelated['transfers'][job])
   ambiguous=collect_context(base,opened=[Path('/usb/Trip/a/image.jpg'),Path('/usb/Trip/b/image.jpg')]);self.assertNotIn('source_file',ambiguous['transfers'][job])
   sample['sampled_at']=time.time()-181;output.write_text(json.dumps(sample));self.assertNotIn('paths',enrich({'transfers':[{'id':job}]},output)['transfers'][0])

 def test_database_changed_during_immutable_observation_is_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'state.sqlite3'
   with sqlite3.connect(path) as db:db.execute('CREATE TABLE settings(key TEXT,value TEXT)')
   with self.assertRaisesRegex(ValueError,'changed during observation'):
    with metadata_db(path) as reader:
     reader.execute('SELECT * FROM settings').fetchall()
     with sqlite3.connect(path) as writer:writer.execute("INSERT INTO settings VALUES('new','value')")

if __name__=='__main__':unittest.main()
