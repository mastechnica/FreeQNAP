"""Explicit local-user read-only library shares; no anonymous/media-network export."""
import secrets,time,json,re
from . import accounts
KINDS={'music','books','podcasts','photos'}
def ensure(state):
 accounts.ensure(state)
 with state.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS personal_library_shares(id TEXT PRIMARY KEY,owner TEXT NOT NULL,recipient TEXT NOT NULL,kind TEXT NOT NULL,created REAL NOT NULL,revoked REAL,scope TEXT NOT NULL)')
def listing(state,user):
 ensure(state)
 with state.connect() as db:
  rows=[dict(v) for v in db.execute('SELECT s.id,s.owner,s.recipient,s.kind,s.created,s.revoked,s.scope,o.label AS owner_label,r.label AS recipient_label FROM personal_library_shares s JOIN local_accounts o ON o.id=s.owner JOIN local_accounts r ON r.id=s.recipient WHERE s.owner=? OR s.recipient=? ORDER BY s.created DESC',(user['id'],user['id']))]
  targets=[dict(v) for v in db.execute('SELECT id,label FROM local_accounts WHERE enabled=1 AND id!=? ORDER BY label',(user['id'],))]
 for row in rows:row['scope']=json.loads(row['scope'])
 return {'shared_with_me':[v for v in rows if v['recipient']==user['id'] and not v['revoked']],'shared_by_me':[v for v in rows if v['owner']==user['id'] and not v['revoked']],'recipients':targets,'access':'read-only'}
def change(state,user,r):
 ensure(state)
 with state.connect() as db:
  db.execute('BEGIN IMMEDIATE')
  if r.get('action')=='share':
   if not accounts.permitted(user,'libraries.share'):raise PermissionError('Library sharing is not enabled for this account')
   recipient=r.get('recipient');kind=r.get('kind')
   if kind not in KINDS or recipient==user['id'] or not db.execute('SELECT 1 FROM local_accounts WHERE id=? AND enabled=1',(recipient,)).fetchone():raise ValueError('Choose a library and another enabled local user')
   permission='photos.read' if kind=='photos' else 'myradio.read'
   if not accounts.permitted(user,permission):raise PermissionError('You do not have access to this library')
   scope=r.get('scope',{'mode':'library'})
   if not isinstance(scope,dict) or set(scope)-{'mode','ids'} or scope.get('mode') not in ('library','albums','items'):raise ValueError('Choose whole library, albums or individual items')
   if kind!='photos' and scope!={'mode':'library'}:raise ValueError('Audio libraries share as complete collections')
   if scope['mode']!='library' and (not isinstance(scope.get('ids'),list) or not 1<=len(scope['ids'])<=1000 or any(not isinstance(v,str) for v in scope['ids'])):raise ValueError('Select 1–1000 items or albums')
   if scope['mode']!='library' and any(not re.fullmatch('[a-f0-9]{'+('64' if scope['mode']=='items' else '32')+'}',v) for v in scope['ids']):raise ValueError('Invalid selected item or album identity')
   if scope['mode']=='library':scope={'mode':'library'}
   ident=secrets.token_hex(16);db.execute('INSERT INTO personal_library_shares VALUES(?,?,?,?,?,NULL,?)',(ident,user['id'],recipient,kind,time.time(),json.dumps(scope)));accounts.audit(db,user['id'],'library-share',recipient)
  elif r.get('action')=='revoke':
   row=db.execute('SELECT * FROM personal_library_shares WHERE id=? AND owner=?',(r.get('id'),user['id'])).fetchone()
   if not row:raise ValueError('Only the owner can revoke this share')
   db.execute('UPDATE personal_library_shares SET revoked=? WHERE id=?',(time.time(),row['id']));accounts.audit(db,user['id'],'library-revoke',row['recipient'])
  else:raise ValueError('Choose share or revoke')
 return {'updated':True,'originals_retained':True}
def resolve(state,user,ident):
 ensure(state)
 with state.connect() as db:
  row=db.execute('SELECT s.*,o.enabled,o.primary_admin,o.label FROM personal_library_shares s JOIN local_accounts o ON o.id=s.owner WHERE s.id=? AND (s.recipient=? OR s.owner=?) AND s.revoked IS NULL',(ident,user['id'],user['id'])).fetchone()
 if not row or not row['enabled']:raise PermissionError('This library is unavailable or no longer shared with you')
 result=dict(row);result['scope']=json.loads(result['scope']);return result
