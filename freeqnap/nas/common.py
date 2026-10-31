"""Shared validation and fixed-command execution for privileged NAS operations."""
import contextlib
import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import time
from pathlib import Path
from ..state import State, atomic

IDENT = re.compile(r'[a-z][a-z0-9-]{0,30}\Z')

def name(value):
    if not isinstance(value, str) or not IDENT.fullmatch(value):
        raise ValueError('Use a lowercase name, starting with a letter; maximum 31 characters')
    return value

def run(*args, data=None, timeout=60, env=None, pass_fds=()):
    result = subprocess.run(list(args), input=data, capture_output=True, timeout=timeout,
                            env=env, pass_fds=pass_fds)
    if result.returncode:
        # Never propagate command input or an unrestricted subprocess diagnostic.
        raise ValueError(f'{Path(args[0]).name} failed (exit {result.returncode}); inspect the local service journal')
    return result.stdout.decode('utf-8', 'replace')

def json_run(*args, **kwargs):
    return json.loads(run(*args, **kwargs))

def secret(value, *, existing=False):
    """Passwords or uploaded binary keys, only in request memory and stdin."""
    import base64
    if not isinstance(value, dict):
        raise ValueError('A private password or key is required')
    if set(value) == {'password'}:
        text = value['password']
        if not isinstance(text, str) or not (1 if existing else 12) <= len(text) <= 1024 or any(ord(c) < 32 for c in text):
            raise ValueError('Enter the existing password without control characters' if existing else 'Use at least 12 characters without control characters')
        return text.encode()
    if set(value) == {'key_base64'}:
        try:
            data = base64.b64decode(value['key_base64'], validate=True)
        except (ValueError, TypeError) as error:
            raise ValueError('Invalid key file') from error
        if not (1 if existing else 32) <= len(data) <= 4096:
            raise ValueError('Key files must contain 32–4096 bytes')
        return data
    raise ValueError('Choose password or key, not a server file path')

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()

class Context:
    def __init__(self, directory='/var/lib/freeqnap-system', runner=run):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.state = State(self.directory)
        self.run = runner

    def config(self):
        return self.state.setting('nas', {'version': 1, 'pools': {}, 'shares': {}, 'users': {},
                                         'repositories': {}, 'libraries': {}})

    def save(self, value):
        self.state.set('nas', value)

    @contextlib.contextmanager
    def lock(self):
        with (self.directory / 'operations.lock').open('a') as stream:
            os.fchmod(stream.fileno(), 0o600)
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def plan(self, kind, body, confirmation):
        ident = secrets.token_hex(16)
        value = {'id': ident, 'kind': kind, 'created_at': time.time(), 'body': body,
                 'confirmation': confirmation, 'consumed': False}
        value['digest'] = hashlib.sha256(canonical(value)).hexdigest()
        atomic(self.directory / 'plans' / (ident + '.json'), value)
        return value

    def reviewed(self, request, kind):
        ident = request.get('plan_id', '')
        if not re.fullmatch('[a-f0-9]{32}', ident):
            raise ValueError('A reviewed plan is required')
        path = self.directory / 'plans' / (ident + '.json')
        value = json.loads(path.read_text())
        computed=hashlib.sha256(canonical({k:v for k,v in value.items() if k!='digest'})).hexdigest()
        if not secrets.compare_digest(computed,value.get('digest','')):raise ValueError('Stored plan contents changed')
        if value['kind'] != kind or value['consumed'] or not 0 <= time.time() - value['created_at'] < 600:
            raise ValueError('Plan is expired, used, or belongs to another operation')
        if not secrets.compare_digest(str(request.get('digest', '')), value['digest']):
            raise ValueError('Reviewed plan digest changed')
        if request.get('confirmation') != value['confirmation']:
            raise ValueError('Type the exact confirmation shown in the plan')
        return path, value

    def consume(self, path, value):
        # Consumption precedes the first mutation. A crash requires reconciliation.
        value['consumed'] = True
        value['started_at'] = time.time()
        atomic(path, value)

    def operation(self, kind, payload):
        if any(word in canonical(payload).decode().lower() for word in ('key_base64', '"password"')):
            raise ValueError('Secrets must never enter persistent operation payloads')
        ident = self.state.enqueue(kind, payload)
        with self.state.connect() as database:
            database.execute("UPDATE jobs SET status='running',attempts=1 WHERE id=?", (ident,))
        return ident

    def volume(self, pool_id):
        pool = self.config()['pools'].get(name(pool_id))
        if not pool:
            raise ValueError('Unknown pool')
        if pool.get('kind')=='usb':
            from .external import attached
            attached(pool)
        target = Path(pool['mountpoint'])
        rows = json.loads(self.run('findmnt', '-J', '-M', str(target), '-o', 'TARGET,SOURCE,FSTYPE,UUID,FSROOT,OPTIONS'))['filesystems']
        # A propagated mount may be reported twice through systemd's private RW
        # bind aliases. Accept only byte-identical records for the same FS root;
        # differing overmounts, options or source identities still fail closed.
        rows=list({json.dumps(row,sort_keys=True):row for row in rows}.values())
        if len(rows) != 1 or rows[0]['uuid'] != pool['filesystem_uuid'] or rows[0]['fstype'] != 'ext4' or rows[0].get('fsroot')!='/':
            raise ValueError('Pool is locked, unmounted or has changed identity')
        if pool.get('block_device'):
            expected=os.stat(pool['block_device']);source=os.stat(rows[0]['source'])
            if not stat.S_ISBLK(expected.st_mode) or not stat.S_ISBLK(source.st_mode) or expected.st_rdev!=source.st_rdev:raise ValueError('Mounted block device differs from the registered volume')
        return pool, target

    def relative(self, pool_id, relative, *, existing=True):
        pool, root = self.volume(pool_id)
        if not isinstance(relative, str) or len(relative) > 2048 or any(ord(c) < 32 for c in relative):
            raise ValueError('Invalid relative path')
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts or any(part.startswith('.freeqnap') for part in path.parts):
            raise ValueError('Choose a path inside the data pool')
        current = root
        for part in path.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError('Symbolic links are not followed by administrative operations')
        resolved = current.resolve(strict=existing)
        if resolved != root and root not in resolved.parents:
            raise ValueError('Path escapes the selected volume')
        if existing and resolved.stat().st_dev != root.stat().st_dev:
            raise ValueError('Nested mount is not part of the selected volume')
        return pool, resolved
