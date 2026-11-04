"""Provider-neutral, default-deny agent credentials and operation grants.

Only the administrator session manages credentials. Bearer tokens never inherit
browser privileges; every invocation rechecks expiry, revocation and exact rights.
"""
import hashlib
import json
import re
import secrets
import time
from pathlib import Path

BACKEND_OPERATIONS = frozenset(json.loads(Path(__file__).with_name('agent_operations.json').read_text()))
PLAYER_OPERATIONS = frozenset(['media.players','media.players-discover','media.play','media.playback-control','media.playback-status'])
ADMIN_ONLY=frozenset(['photos.icloud-login','photos.icloud-code','photos.icloud-status','photos.icloud-save'])
OPERATIONS = (BACKEND_OPERATIONS | PLAYER_OPERATIONS) - ADMIN_ONLY
# Explicit lists: a new operation never expands an existing role or token.
PRESETS = {
    'my-radio-reader':['myradio.status','myradio.catalog','myradio.item','myradio.read','myradio.book-text','myradio.stations','myradio.podcasts'],
    'my-radio-editor':['myradio.catalog','myradio.metadata','myradio.artwork','myradio.artwork-url','myradio.lookup','myradio.upload-begin','myradio.upload-chunk','myradio.upload-finish','myradio.import-url','myradio.import-folder','myradio.scan'],
    'personal-photo-reader':['photos.status','photos.catalog','photos.places','photos.read','photos.related'],
    'personal-photo-editor':['photos.catalog','photos.annotate','photos.album-create','photos.album-add'],
    'health-reader': ['health.alerts','smart.status','smart.history','system.frontpanel','system.history','network.status','network.history'],
    'media-editor': ['media.catalog','media.provider-status','media.scanner-status','media.lookup','media.metadata','media.artwork','media.scan'],
    'media-playback': ['media.catalog','media.players','media.play','media.playback-control','media.playback-status'],
    'file-reader': ['files.list','files.read','files.pool-list','files.pool-read'],
    'file-editor': ['files.list','files.read','files.mkdir','files.upload-begin','files.upload-chunk','files.upload-finish','files.move-plan','files.move','files.transfer-plan','files.transfer','files.recycle-plan','files.recycle'],
    'download-manager': ['downloads.status','downloads.add','downloads.control','downloads.files','downloads.read'],
}
READ_ONLY = frozenset(PRESETS['my-radio-reader'] + ['files.metadata-read','photos.metadata-read','files.media-neighbors','library.files-status','raid.recovery-status','raid.backups','system.button-status','myradio.station-source'] + PRESETS['personal-photo-reader'] + ['media.players','media.playback-status'] + PRESETS['health-reader'] + PRESETS['file-reader'] + ['nas.status','notifications.status','notifications.rules','ddns.status','vpn.status','vpn.peers-status','downloads.status','downloads.files','downloads.read','media.catalog','media.provider-status','media.scanner-status','media.clients','media.dlna-options','external.discover','external.unlock-capabilities','external.files','external.read','external.session-files','external.session-read','backup.schedule-list','backup.system-stages','backup.local-list','repositories.snapshots','files.stages','files.trash','recovery.list','system.https-status','system.https-ca'])
SENSITIVE = frozenset(['myradio.read','myradio.book-text','raid.backup-read','photos.read','photos.places','vpn.wireguard-profile','artifacts.read','backup.local-read','encryption.header-backup'])

class Denied(ValueError): pass
class Limited(ValueError): pass

class Agents:
    def __init__(self, state):
        self.state=state
        with state.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS agent_tokens(
                id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
                grants TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL,
                revoked REAL, last_used REAL, window REAL NOT NULL DEFAULT 0, hits INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS agent_handles(kind TEXT NOT NULL, value TEXT NOT NULL, owner TEXT NOT NULL,
                PRIMARY KEY(kind,value));
                CREATE TABLE IF NOT EXISTS agent_audit(id INTEGER PRIMARY KEY AUTOINCREMENT,
                at REAL NOT NULL, principal TEXT NOT NULL, operation TEXT NOT NULL, outcome TEXT NOT NULL);''')

    def catalog(self):
        return {'version':1,'operations':[{'id':op,'group':op.split('.')[0],
                'label':op.replace('.',' · ').replace('-',' '),
                'access':'sensitive export' if op in SENSITIVE else 'read' if op in READ_ONLY else 'change',
                'scope':'NAS-wide; no per-folder restriction'} for op in sorted(OPERATIONS)],
                'presets':PRESETS,'api_base':'/api/agent/v1',
                'capabilities':{'shell':False,'credential_delegation':False,'renderer_playback':'owner-approved UPnP AVTransport; direct play only'}}

    def issue(self, request):
        if set(request)-{'name','grants','days'}:raise ValueError('Unknown token settings')
        name=request.get('name');grants=request.get('grants');days=request.get('days',30)
        if not isinstance(name,str) or not 1<=len(name.strip())<=80 or any(ord(c)<32 for c in name):raise ValueError('Enter an agent name (1–80 characters)')
        if not isinstance(grants,list) or not grants or len(grants)>len(OPERATIONS) or any(not isinstance(x,str) or x not in OPERATIONS for x in grants):raise ValueError('Choose specific supported permissions')
        if type(days) is not int or not 1<=days<=365:raise ValueError('Choose an expiry from 1–365 days')
        now=time.time();ident=secrets.token_hex(12);token='fqn_'+secrets.token_urlsafe(32)
        with self.state.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT count(*) FROM agent_tokens WHERE revoked IS NULL AND expires>?',(now,)).fetchone()[0]>=64:raise ValueError('64 active credentials maximum; revoke unused credentials first')
            db.execute('INSERT INTO agent_tokens(id,token_hash,name,grants,created,expires) VALUES(?,?,?,?,?,?)',
                (ident,hashlib.sha256(token.encode()).hexdigest(),name.strip(),json.dumps(sorted(set(grants))),now,now+days*86400))
        self.audit(ident,'credential.issue','issued')
        return {'id':ident,'token':token,'expires_at':now+days*86400,'shown_once':True}

    def listing(self):
        with self.state.connect() as db:
            rows=db.execute('SELECT id,name,grants,created,expires,revoked,last_used FROM agent_tokens ORDER BY (revoked IS NULL AND expires>?) DESC,created DESC LIMIT 320',(time.time(),)).fetchall()
            audit=[dict(r) for r in db.execute('SELECT at,principal,operation,outcome FROM agent_audit ORDER BY id DESC LIMIT 100')]
        return {'tokens':[{**dict(r),'grants':json.loads(r['grants'])} for r in rows],'audit':audit}

    def revoke(self, request):
        with self.state.connect() as db:
            count=db.execute('UPDATE agent_tokens SET revoked=? WHERE id=? AND revoked IS NULL',(time.time(),request.get('id'))).rowcount
        self.audit(str(request.get('id'))[:24],'credential.revoke','revoked' if count else 'unchanged')
        return {'revoked':True}

    def authenticate(self, header):
        if not isinstance(header,str) or not re.fullmatch(r'Bearer fqn_[A-Za-z0-9_-]{43}',header):raise Denied('Valid agent bearer token required')
        digest=hashlib.sha256(header[7:].encode()).hexdigest();now=time.time()
        with self.state.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM agent_tokens WHERE token_hash=? AND revoked IS NULL AND expires>?',(digest,now)).fetchone()
            if not row:raise Denied('Agent credential is invalid, expired or revoked')
            hits=row['hits']+1 if now-row['window']<60 else 1
            if hits>120:raise Limited('Agent request limit reached; wait one minute')
            db.execute('UPDATE agent_tokens SET hits=?,window=?,last_used=? WHERE id=?',(hits,row['window'] if now-row['window']<60 else now,now,row['id']))
        return {'id':row['id'],'grants':frozenset(json.loads(row['grants']))}

    def audit(self, principal, operation, outcome):
        # Intentionally excludes bodies, paths, headers, error strings and tokens.
        with self.state.connect() as db:
            db.execute('INSERT INTO agent_audit(at,principal,operation,outcome) VALUES(?,?,?,?)',(time.time(),principal,operation,outcome))
            db.execute('DELETE FROM agent_audit WHERE id <= (SELECT coalesce(max(id),0)-10000 FROM agent_audit)')

    def own(self, principal, kind, value):
        with self.state.connect() as db:
            row=db.execute('SELECT owner FROM agent_handles WHERE kind=? AND value=?',(kind,value)).fetchone()
        if not row or row['owner']!=principal['id']:raise Denied('This operation reference belongs to another session or agent')

    def invoke(self, principal, operation, payload, broker):
        # Unknown operations have no wildcard or administrator fallback.
        if operation not in OPERATIONS or operation not in principal['grants']:
            self.audit(principal['id'],operation if operation in OPERATIONS else 'unknown','denied')
            raise Denied('Permission not granted for this operation')
        if not isinstance(payload,dict):raise ValueError('JSON object required')
        for key,kind in [('plan_id','plan'),('upload_id','upload'),('ticket','ticket')]:
            if key in payload:self.own(principal,kind,payload[key])
        if (operation.startswith('files.') or operation in ('myradio.import-folder','photos.import-folder')) and isinstance(payload.get('share'),str) and payload['share'].startswith('foreign:'):
            self.own(principal,'foreign',payload['share'][8:])
        if operation=='jobs.retry':self.own(principal,'job',payload.get('id'))
        if operation in ('external.lock-session','external.session-files','external.session-read'):
            self.own(principal,'foreign',payload.get('session',payload.get('id')))
        with self.state.connect() as db:
            db.execute('DELETE FROM agent_handles WHERE owner IN (SELECT id FROM agent_tokens WHERE revoked IS NOT NULL OR expires<=?)',(time.time(),))
            if db.execute('SELECT count(*) FROM agent_handles WHERE owner=?',(principal['id'],)).fetchone()[0]>=10000:
                raise Limited('Credential operation-reference limit reached; issue a replacement credential')
        # Revalidate immediately before dispatch, including revocation while waiting.
        with self.state.connect() as db:
            row=db.execute('SELECT revoked,expires FROM agent_tokens WHERE id=?',(principal['id'],)).fetchone()
        if not row or row['revoked'] or row['expires']<=time.time():raise Denied('Credential no longer active')
        self.audit(principal['id'],operation,'started')
        try:result=broker.request(operation,payload)
        except Exception:
            self.audit(principal['id'],operation,'failed');raise
        if isinstance(result,dict):
            handles=[]
            if 'digest' in result and 'confirmation' in result and 'id' in result:handles.append(('plan',result['id']))
            for key,kind in [('upload_id','upload'),('ticket','ticket'),('job_id','job')]:
                if key in result:handles.append((kind,result[key]))
            if operation=='external.unlock':
                if result.get('id'):handles.append(('foreign',result['id']))
                if result.get('session'):handles.append(('foreign',result['session']))
            with self.state.connect() as db:
                for kind,value in handles:
                    db.execute('INSERT OR IGNORE INTO agent_handles VALUES(?,?,?)',(kind,value,principal['id']))
        self.audit(principal['id'],operation,'accepted')
        return result
