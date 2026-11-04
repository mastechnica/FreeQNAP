"""Local identities, roles and revocable sessions, independent of a cloud provider."""
import hashlib,json,re,secrets,sqlite3,time,threading
from .auth import password_hash
PERMISSIONS={'myradio.read','myradio.write','photos.read','photos.write','photos.icloud','files.read','files.write','storage.choose','libraries.share','metadata.edit','social.share'}
DEFAULT=sorted(PERMISSIONS)
USERNAME=re.compile(r'[a-z][a-z0-9._-]{1,39}\Z')

def text(v,n=120):
    if not isinstance(v,str) or not v.strip() or len(v)>n or any(ord(c)<32 for c in v):raise ValueError('Enter valid account text')
    return v.strip()

_SCHEMA_LOCK=threading.RLock()
def ensure(state):
    with _SCHEMA_LOCK:return _ensure(state)

def _ensure(state):
    with state.connect() as db:
        db.executescript("""CREATE TABLE IF NOT EXISTS local_accounts(id TEXT PRIMARY KEY,username TEXT COLLATE NOCASE UNIQUE NOT NULL,label TEXT NOT NULL,role TEXT NOT NULL,permissions TEXT NOT NULL,password TEXT NOT NULL,enabled INTEGER NOT NULL,must_change INTEGER NOT NULL,version INTEGER NOT NULL,primary_admin INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS account_storage(user_id TEXT PRIMARY KEY,assignments TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS account_sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL,version INTEGER NOT NULL,source TEXT NOT NULL,idle_expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS account_audit(id INTEGER PRIMARY KEY AUTOINCREMENT,at REAL NOT NULL,actor TEXT NOT NULL,action TEXT NOT NULL,target TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS external_identities(issuer TEXT NOT NULL,subject TEXT NOT NULL,user_id TEXT NOT NULL,PRIMARY KEY(issuer,subject));
        CREATE TABLE IF NOT EXISTS oidc_transactions(state_hash TEXT PRIMARY KEY,binding_hash TEXT NOT NULL,payload TEXT NOT NULL,expires REAL NOT NULL);""")
        db.execute('BEGIN IMMEDIATE')
        stored=state.setting('administrator')
        if stored and not db.execute('SELECT 1 FROM local_accounts').fetchone():
            ident=secrets.token_hex(16)
            db.execute('INSERT INTO local_accounts VALUES(?,?,?,?,?,?,1,0,1,1,?)',(ident,'admin','Administrator','administrator',json.dumps(DEFAULT),json.dumps(stored),time.time()))
            db.execute("INSERT OR IGNORE INTO account_sessions SELECT token_hash,?,1,'local',expires FROM sessions",(ident,))


def public(row):return {k:row[k] for k in ('id','username','label','role','enabled','must_change','primary_admin')}|{'permissions':json.loads(row['permissions'])}
def permitted(user,permission):return user and (user['role']=='administrator' or permission in user['permissions'])
def audit(db,actor,action,target):db.execute('INSERT INTO account_audit(at,actor,action,target) VALUES(?,?,?,?)',(time.time(),actor,action,target))
def verify(row,password):
    try:
        v=json.loads(row['password']);return secrets.compare_digest(password_hash(password,v['salt'])['hash'],v['hash'])
    except (ValueError,TypeError,KeyError):return False

def create_session(state,row,source='local',seconds=43200):
    token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(24);now=time.time()
    with state.connect() as db:
        live=db.execute('SELECT * FROM local_accounts WHERE id=?',(row['id'],)).fetchone()
        if not live or not live['enabled'] or live['version']!=row['version']:raise ValueError('Account access changed; sign in again')
        db.execute('DELETE FROM sessions WHERE expires<?',(now,))
        key=hashlib.sha256(token.encode()).hexdigest()
        db.execute('DELETE FROM account_sessions WHERE token_hash NOT IN (SELECT token_hash FROM sessions)')
        db.execute('INSERT INTO sessions VALUES(?,?,?)',(key,csrf,now+seconds))
        db.execute('INSERT INTO account_sessions VALUES(?,?,?,?,?)',(key,row['id'],row['version'],source,now+min(3600,seconds)))
    return token,csrf

def login(state,username,password):
    ensure(state)
    valid_username=isinstance(username,str) and 1<=len(username)<=40
    username=username if valid_username else '!invalid'
    with state.connect() as db:row=db.execute('SELECT * FROM local_accounts WHERE username=?',(username,)).fetchone()
    if not row or not row['enabled'] or not verify(row,password):
        # Equal-cost rejection for unknown users; no usernames/passwords in audit.
        if not row:password_hash('unknown account timing padding', '00'*16)
        with state.connect() as db:audit(db,'anonymous','login-denied','')
        return None
    result=create_session(state,row)
    with state.connect() as db:audit(db,row['id'],'local-login',row['id'])
    return result

def session(state,token):
    if not isinstance(token,str) or len(token)>128:return None
    ensure(state);key=hashlib.sha256(token.encode()).hexdigest();now=time.time()
    with state.connect() as db:
        s=db.execute('SELECT s.csrf,s.expires,a.* FROM sessions s JOIN account_sessions a ON a.token_hash=s.token_hash WHERE s.token_hash=?',(key,)).fetchone()
        if not s or s['expires']<=now or s['idle_expires']<=now:return None
        row=db.execute('SELECT * FROM local_accounts WHERE id=?',(s['user_id'],)).fetchone()
        if not row or not row['enabled'] or row['version']!=s['version']:return None
        db.execute('UPDATE account_sessions SET idle_expires=? WHERE token_hash=?',(min(s['expires'],now+3600),key))
        return {'csrf':s['csrf'],'expires':s['expires'],'source':s['source'],'user':public(row)}

def listing(state):
    ensure(state)
    with state.connect() as db:
        users=[public(v) for v in db.execute('SELECT * FROM local_accounts ORDER BY primary_admin DESC,username')]
        identities=[dict(v) for v in db.execute('SELECT issuer,subject,user_id FROM external_identities')]
        history=[dict(v) for v in db.execute('SELECT at,actor,action,target FROM account_audit ORDER BY id DESC LIMIT 100')]
    with state.connect() as db:storage={v['user_id']:json.loads(v['assignments']) for v in db.execute('SELECT * FROM account_storage')}
    return {'storage_assignments':storage,'users':users,'identities':identities,'audit':history,'permissions':sorted(PERMISSIONS),'roles':['administrator','member'],'cloud_optional':True}

def change(state,actor,r):
    ensure(state)
    if actor['role']!='administrator':raise PermissionError('Administrator access required')
    action=r.get('action')
    if action not in ('create','update','set-password','revoke-sessions'):raise ValueError('Choose a supported account action')
    allowed={'action','id','username','label','role','permissions','password','enabled','must_change'}
    if set(r)-allowed:raise ValueError('Unknown account setting')
    hashed=password_hash(r['password']) if action in ('create','set-password') else None
    with state.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=None if action=='create' else db.execute('SELECT * FROM local_accounts WHERE id=?',(r.get('id'),)).fetchone()
        if action!='create' and not row:raise ValueError('Account not found')
        ident=secrets.token_hex(16) if row is None else row['id']
        if action in ('create','update'):
            role=r.get('role',row['role'] if row else 'member');enabled=r.get('enabled',bool(row['enabled']) if row else True)
            if role not in ('administrator','member') or type(enabled)is not bool:raise ValueError('Choose account role and enabled state')
            permissions=r.get('permissions',json.loads(row['permissions']) if row else DEFAULT)
            if not isinstance(permissions,list) or len(permissions)>len(PERMISSIONS) or any(type(v)is not str or v not in PERMISSIONS for v in permissions):raise ValueError('Choose explicit account permissions')
            label=text(r.get('label',row['label'] if row else r.get('username')))
            if row and row['primary_admin'] and (role!='administrator' or not enabled):raise ValueError('Keep the original local administrator enabled for recovery')
            if row and row['role']=='administrator' and row['enabled'] and (role!='administrator' or not enabled):
                if db.execute("SELECT count(*) FROM local_accounts WHERE role='administrator' AND enabled=1 AND id!=?",(ident,)).fetchone()[0]<1:raise ValueError('Keep at least one enabled local administrator')
            if row:
                db.execute('UPDATE local_accounts SET label=?,role=?,permissions=?,enabled=?,version=version+1 WHERE id=?',(label,role,json.dumps(sorted(set(permissions))),int(enabled),ident))
            else:
                user=text(r.get('username'),40).lower()
                if not USERNAME.fullmatch(user):raise ValueError('Username: 2–40 lowercase letters, numbers, dot, dash or underscore; start with a letter')
                if db.execute('SELECT count(*) FROM local_accounts').fetchone()[0]>=32:raise ValueError('This NAS supports up to 32 local accounts')
                if db.execute('SELECT 1 FROM local_accounts WHERE username=?',(user,)).fetchone():raise ValueError('Username already exists')
                db.execute('INSERT INTO local_accounts VALUES(?,?,?,?,?,?,?,1,1,0,?)',(ident,user,label,role,json.dumps(sorted(set(permissions))),json.dumps(hashed),int(enabled),time.time()))
        elif action=='set-password':
            db.execute('UPDATE local_accounts SET password=?,must_change=1,version=version+1 WHERE id=?',(json.dumps(hashed),ident))
            if row['primary_admin']:db.execute("UPDATE settings SET value=? WHERE key='administrator'",(json.dumps(hashed),))
        else:db.execute('UPDATE local_accounts SET version=version+1 WHERE id=?',(ident,))
        db.execute('DELETE FROM sessions WHERE token_hash IN (SELECT token_hash FROM account_sessions WHERE user_id=?)',(ident,));db.execute('DELETE FROM account_sessions WHERE user_id=?',(ident,));audit(db,actor['id'],action,ident)
    return {'id':ident,'updated':True,'files_retained':True,'sessions_revoked':True}

def change_password(state,user,r):
    hashed=password_hash(r.get('password'))
    with state.connect() as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM local_accounts WHERE id=?',(user['id'],)).fetchone()
        if not row or not verify(row,r.get('current_password')):raise ValueError('Current password is incorrect')
        db.execute('UPDATE local_accounts SET password=?,must_change=0,version=version+1 WHERE id=?',(json.dumps(hashed),user['id']))
        if row['primary_admin']:db.execute("UPDATE settings SET value=? WHERE key='administrator'",(json.dumps(hashed),))
        db.execute('DELETE FROM sessions WHERE token_hash IN (SELECT token_hash FROM account_sessions WHERE user_id=?)',(user['id'],));db.execute('DELETE FROM account_sessions WHERE user_id=?',(user['id'],));audit(db,user['id'],'change-password',user['id'])
    return {'changed':True,'sign_in_again':True}


def assignments(state,user_id):
    with state.connect() as db:r=db.execute('SELECT assignments FROM account_storage WHERE user_id=?',(user_id,)).fetchone()
    return json.loads(r[0]) if r else []

def set_storage(state,actor,target,rows):
    if actor['role']!='administrator':raise PermissionError('Administrator access required')
    with state.connect() as db:
        if not db.execute('SELECT 1 FROM local_accounts WHERE id=?',(target,)).fetchone():raise ValueError('Account not found')
        db.execute('INSERT INTO account_storage VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET assignments=excluded.assignments',(target,json.dumps(rows)));audit(db,actor['id'],'storage-assignments',target)
    return {'updated':True,'files_retained':True}
