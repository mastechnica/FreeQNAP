import json,sqlite3,unittest
from freeqnap.nas.myradio import catalog_indexes
class CatalogIndexTests(unittest.TestCase):
 def test_title_and_facet_indexes_match_real_queries_and_preserve_rows(self):
  with sqlite3.connect(':memory:') as db:
   db.execute('CREATE TABLE radio_assets(category TEXT,hidden INTEGER,name TEXT,metadata TEXT)')
   db.executemany('INSERT INTO radio_assets VALUES(?,?,?,?)',[('music',0,str(n),json.dumps({'title':str(n),'artist':'Artist','album':'Album','genre':'Jazz'})) for n in range(200)])
   catalog_indexes(db);catalog_indexes(db)
   plan=str(list(db.execute("EXPLAIN QUERY PLAN SELECT * FROM radio_assets WHERE category=? AND hidden=? ORDER BY lower(coalesce(json_extract(metadata,'$.title'),name)) LIMIT 120",('music',0))))
   self.assertIn('radio_title_page',plan);self.assertEqual(db.execute('SELECT count(*) FROM radio_assets').fetchone()[0],200)
   for field in ('artist','author','album','genre'):
    self.assertIn('radio_facet_'+field,str(list(db.execute("EXPLAIN QUERY PLAN SELECT DISTINCT json_extract(metadata,'$."+field+"') AS value FROM radio_assets WHERE category=? AND hidden=0 AND value IS NOT NULL AND value!='' ORDER BY value LIMIT 300",('music',)))))
