"""Private, durable state and fair independent job bookkeeping."""
import contextlib, hashlib, json, os, secrets, sqlite3, time
from pathlib import Path

def atomic(path, value, mode=0o600):
    p = Path(path)
    p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = p.with_name(p.name + '.' + secrets.token_hex(8) + '.next')
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, p)
        fd = os.open(p.parent, os.O_RDONLY)
        os.fsync(fd)
        os.close(fd)
    finally:
        temp.unlink(missing_ok=True)

class State:

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.database = self.directory / 'state.sqlite3'
        with self.connect() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL); CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,kind TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,result TEXT,error TEXT); CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,csrf TEXT NOT NULL,expires REAL NOT NULL);')
        self.database.chmod(0o600)

    @contextlib.contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA synchronous=FULL')
        try:
            with db:
                yield db
        finally:
            db.close()

    def setting(self, key, default=None):
        with self.connect() as db:
            r = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(r[0]) if r else default

    def set(self, key, value):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (key, json.dumps(value)))

    def enqueue(self, kind, payload):
        ident = secrets.token_hex(16)
        now = time.time()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0] >= 128:
                raise ValueError('Active job capacity reached; retained failed jobs are unchanged')
            db.execute('INSERT INTO jobs(id,kind,payload,status,created,updated) VALUES(?,?,?,?,?,?)', (ident, kind, json.dumps(payload), 'queued', now, now))
        return ident

    def jobs(self):
        with self.connect() as db:
            rows = db.execute('SELECT id,kind,status,created,updated,attempts,result,error FROM jobs ORDER BY created DESC LIMIT 200').fetchall()
        return [dict(r) for r in rows]

    def claim(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            r = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created,id LIMIT 1").fetchone()
            if not r:
                return None
            db.execute("UPDATE jobs SET status='running',attempts=attempts+1,updated=? WHERE id=?", (time.time(), r['id']))
            return dict(r)

    def finish(self, ident, result=None, error=None):
        with self.connect() as db:
            db.execute('UPDATE jobs SET status=?,result=?,error=?,updated=? WHERE id=?', ('retryable' if error else 'succeeded', json.dumps(result) if result is not None else None, str(error)[:1000] if error else None, time.time(), ident))

    def retry(self, ident):
        with self.connect() as db:
            cur = db.execute("UPDATE jobs SET status='queued',updated=? WHERE id=? AND status='retryable'", (time.time(), ident))
            if cur.rowcount != 1:
                raise ValueError('Only an explicitly selected retryable job can be retried')

    def reconcile_interrupted(self):
        with self.connect() as db:
            db.execute("UPDATE jobs SET status='retryable',error='Interrupted; inspect output before explicit retry',updated=? WHERE status='running'", (time.time(),))
