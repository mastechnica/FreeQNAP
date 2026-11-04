"""Local NAS administrator credentials; no shared password or header trust."""
import getpass, hashlib, secrets, time, warnings

def password_hash(password, salt=None):
    if not isinstance(password, str) or len(password) < 12 or len(password.encode()) > 1024 or any((c in password for c in ('\n', '\r', '\x00'))):
        raise ValueError('Use a password of at least 12 characters without control characters')
    salt = salt or secrets.token_hex(16)
    return {'salt': salt, 'hash': hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()}

def initialize(state):
    if state.setting('administrator'):
        raise ValueError('Administrator already configured; do not silently replace credentials')
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        a = getpass.getpass('New FreeQNAP administrator password: ')
        b = getpass.getpass('Confirm password: ')
    if a != b:
        raise ValueError('Passwords do not match')
    state.set('administrator', password_hash(a))

def login(state,password,username='admin'):
    from .accounts import login as account_login
    return account_login(state,username,password)

def session(state,token):
    from .accounts import session as account_session
    return account_session(state,token)

def enrollment(state):
    """A short-lived, one-use bootstrap secret; never a shared default password."""
    if state.setting('administrator'):
        raise ValueError('Administrator is already configured')
    token = secrets.token_urlsafe(32)
    state.set('enrollment', {'hash': hashlib.sha256(token.encode()).hexdigest(), 'expires': time.time() + 1800})
    return token

def enroll(state, token, password):
    if not isinstance(token, str) or len(token) > 128:
        raise ValueError('Invalid enrollment token')
    with state.connect() as database:
        database.execute('BEGIN IMMEDIATE')
        if database.execute("SELECT 1 FROM settings WHERE key='administrator'").fetchone():
            raise ValueError('Administrator already configured')
        row = database.execute("SELECT value FROM settings WHERE key='enrollment'").fetchone()
        import json
        value = json.loads(row[0]) if row else {}
        if value.get('expires', 0) < time.time() or not secrets.compare_digest(value.get('hash', ''), hashlib.sha256(token.encode()).hexdigest()):
            raise ValueError('Enrollment token is invalid or expired')
        hashed=password_hash(password)
        database.execute('INSERT INTO settings VALUES(?,?)', ('administrator', json.dumps(hashed)))
        database.execute("DELETE FROM settings WHERE key='enrollment'")
    return {'administrator_configured': True}
