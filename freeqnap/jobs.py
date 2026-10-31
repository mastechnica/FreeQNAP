"""A failed backup remains retryable and does not block later jobs."""
import json, time
from pathlib import Path
from . import backups

class Worker:

    def __init__(self, state, destination):
        self.state = state
        self.destination = Path(destination)

    def one(self):
        job = self.state.claim()
        if job is None:
            return False
        try:
            payload = json.loads(job['payload'])
            if job['kind'] == 'config-backup':
                policy = self.state.setting('backup_policy', {})
                keep = int(payload.get('keep', policy.get('keep', 7)))
                result = backups.create(self.state.directory, self.destination, keep=keep)
                if policy.get('mirror'):
                    result['mirror'] = backups.mirror(self.destination / result['name'], policy['mirror']['path'], policy['mirror']['uuid'], keep)
            elif job['kind'] == 'verify-backup':
                name = payload['name']
                if Path(name).name != name or not name.startswith('freeqnap-config-') or (not name.endswith('.tar.gz')):
                    raise ValueError('Managed archive name required')
                result = backups.verify(self.destination / name)
            else:
                raise ValueError('Unknown job kind')
            self.state.finish(job['id'], result=result)
        except Exception as error:
            self.state.finish(job['id'], error=str(error))
        return True

    def schedule(self, now=None):
        """One daily job at most; missed intervals coalesce instead of flooding."""
        now = time.time() if now is None else now
        policy = self.state.setting('backup_policy', {})
        if not policy.get('daily'):
            return False
        with self.state.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT value FROM settings WHERE key='backup_last_scheduled'").fetchone()
            last = json.loads(row[0]) if row else 0
            if now - last < 86400:
                return False
            if db.execute("SELECT count(*) FROM jobs WHERE kind='config-backup' AND status IN ('queued','running')").fetchone()[0]:
                return False
            if db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0] >= 128:
                return False
            import secrets
            ident = secrets.token_hex(16)
            db.execute('INSERT INTO jobs(id,kind,payload,status,created,updated) VALUES(?,?,?,?,?,?)', (ident, 'config-backup', '{}', 'queued', now, now))
            db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('backup_last_scheduled', json.dumps(now)))
        return True
