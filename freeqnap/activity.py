"""Private activity ledger: allowlisted event fields, never request bodies."""
import re,time
SAFE=re.compile(r'[A-Za-z0-9_.:/-]{1,160}\Z')
SCHEMA="CREATE TABLE IF NOT EXISTS activity_events(id INTEGER PRIMARY KEY AUTOINCREMENT,at REAL NOT NULL,actor TEXT NOT NULL,operation TEXT NOT NULL,outcome TEXT NOT NULL,scope TEXT NOT NULL,severity TEXT NOT NULL,bytes INTEGER NOT NULL DEFAULT 0); CREATE INDEX IF NOT EXISTS activity_actor ON activity_events(actor,id);"
def ensure(state):
 with state.connect() as db:db.executescript(SCHEMA)
def record(state,actor,operation,outcome='succeeded',scope='private',severity='info',size=0):
 ensure(state)
 if not SAFE.fullmatch(actor) or not SAFE.fullmatch(operation) or outcome not in ('succeeded','accepted','denied','failed','started','resolved','changed') or scope not in ('private','system') or severity not in ('info','warning','critical'):raise ValueError('Invalid audit event')
 with state.connect() as db:db.execute('INSERT INTO activity_events(at,actor,operation,outcome,scope,severity,bytes) VALUES(?,?,?,?,?,?,?)',(time.time(),actor,operation,outcome,scope,severity,max(0,min(int(size),2**60))))
def listing(state,user,query):
 ensure(state);before=int(query.get('before',0));limit=max(1,min(100,int(query.get('limit',50))));where=['1=1'];args=[]
 if str(query.get('include_polls','0'))!='1':where += ["operation!='session' AND operation NOT LIKE 'nas.%status'"]
 if user['role']!='administrator':where+=['(actor=? OR scope=?)'];args+=['user:'+user['id'],'system']
 elif query.get('user'):where+=['actor=?'];args+=['user:'+query['user']]
 if before:where+=['id<?'];args+=[before]
 with state.connect() as db:rows=[dict(v) for v in db.execute('SELECT * FROM activity_events WHERE '+' AND '.join(where)+' ORDER BY id DESC LIMIT ?',args+[limit+1])]
 more=len(rows)>limit;rows=rows[:limit]
 for row in rows:
  if user['role']!='administrator' and row['scope']=='system':row['actor']='system'
 return {'events':rows,'next_before':rows[-1]['id'] if more else None,'coverage':'Dashboard and API requests from this update onward. Shared hardware/service notices are included. Operating-system shell and SMB/NFS/AFP file actions are not a complete per-user audit. Byte counts are response sizes, not disk-space charges.'}
def security_events(state,user):
 with state.connect() as db:
  where='' if user['role']=='administrator' else ' WHERE actor=?';args=[] if not where else [user['id']]
  return [dict(v) for v in db.execute('SELECT at,actor,action,target FROM account_audit'+where+' ORDER BY id DESC LIMIT 100',args)]
