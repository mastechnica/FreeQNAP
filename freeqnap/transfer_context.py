"""Read-only transfer path samples, independent of the long-running copy worker.

Only enrich rows already authorized by the broker. Never publish staging tokens,
raw plans, credentials, unrelated open descriptors, or another account's jobs.
"""
import contextlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import subprocess
import time

IDENT = re.compile(r'[a-f0-9]{32}\Z')


def read_json(path):
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('Transfer metadata exceeds observation limit')
    return json.loads(path.read_text())


@contextlib.contextmanager
def metadata_db(path):
    # A protected read-only collector cannot create SQLite's transient shared
    # memory file. With no WAL, immutable reads are safe only if the database
    # identity and absence of a WAL are unchanged after the complete read.
    path = Path(path)
    wal = path.with_name(path.name + '-wal')
    immutable = not wal.exists()
    before = path.stat()
    identity = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
    db = sqlite3.connect(path.as_uri() + '?mode=ro' + ('&immutable=1' if immutable else ''), uri=True, timeout=.25)
    try:
        db.execute('BEGIN')
        yield db
        if immutable and (wal.exists() or identity(path.stat()) != identity(before)):
            raise ValueError('Transfer metadata changed during observation')
    finally:
        db.close()


def setting(db, key, default):
    row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else default


def relative(value):
    if not isinstance(value, str) or '\x00' in value:
        raise ValueError('Invalid transfer path')
    p = PurePosixPath(value)
    if p.is_absolute() or '..' in p.parts:
        raise ValueError('Invalid relative transfer path')
    return p


def share_root(base, locations, config, share):
    if share.startswith('foreign:') and IDENT.fullmatch(share[8:]):
        record = read_json(base / 'foreign' / (share[8:] + '.json'))
        return Path(record['mountpoint']) / ('root' if record['format'] == 'apfs' else '')
    if share.startswith('pool:'):
        return Path(config['pools'][share[5:]]['mountpoint'])
    key = {'my-photos': 'personal-photos', 'my-radio': 'myradio', 'my-files': 'personal-files'}.get(share)
    if key:
        location = locations.get(key, {})
        return Path(config['pools'][location['pool']]['mountpoint']) / relative(location['location_folder'])
    return Path(config['shares'][share]['path'])


def open_files():
    """Observe only regular-file descriptors belonging to the pinned service PID."""
    result = subprocess.run(['systemctl', 'show', 'freeqnap-broker.service', '-p', 'MainPID', '--value'], capture_output=True, timeout=2, check=True)
    pid = result.stdout.decode().strip()
    if not pid.isdecimal() or int(pid) < 2:
        return []
    rows = []
    for fd in list(Path('/proc', pid, 'fd').iterdir())[:4096]:
        try:
            if stat.S_ISREG(fd.stat().st_mode):
                rows.append(Path(os.readlink(fd)))
        except OSError:
            continue
    return rows


def observe(base, directory, config, opened, now):
    rows = {}
    database = directory / 'state.sqlite3'
    if not database.exists():
        return rows
    with metadata_db(database) as db:
        db.row_factory = sqlite3.Row
        jobs = db.execute("SELECT id,payload FROM jobs WHERE kind='files.transfer' ORDER BY created DESC LIMIT 30").fetchall()
        locations = {key: setting(db, key, {}) for key in ('personal-photos', 'myradio', 'personal-files')}
    for job in jobs:
        try:
            if not IDENT.fullmatch(job['id']):
                continue
            payload = json.loads(job['payload'])
            plan_id = payload.get('plan_id')
            if not isinstance(plan_id, str) or not IDENT.fullmatch(plan_id):
                continue
            body = read_json(directory / 'plans' / (plan_id + '.json'))['body']
            source = share_root(base, locations, config, body['share'])
            target = share_root(base, locations, config, body['target_share']) / relative(body['target_path'])
            items = body['items']
            value = {'source': str(source), 'destination': str(target), 'selections': [str(relative(item['path'])) for item in items], 'target_share': body['target_share'], 'target_path': str(relative(body['target_path'])) if body['target_path'] else '', 'target_names': [item['name'] for item in items]}
            # A selected folder may have many identically named leaves. Match
            # the actual source descriptor; never guess from its basename.
            candidates = []
            record_path = directory / 'operations' / (job['id'] + '.json')
            record = read_json(record_path) if record_path.exists() else {}
            value['published_names'] = list(record.get('published', []))
            token = record.get('partial_stage', '')
            stage = None
            if IDENT.fullmatch(token):
                stage = Path(config['pools'][record['stage_pool']]['mountpoint']) / '.freeqnap' / 'transfers' / token
            for item in items:
                selected = source / relative(item['path'])
                for opened_file in opened:
                    if opened_file == selected or selected in opened_file.parents:
                        suffix = opened_file.relative_to(selected)
                        if stage is None or stage / suffix not in opened:
                            continue
                        final = target / relative(item['name']) / suffix
                        candidates.append((str(opened_file), str(final)))
            candidates = list(dict.fromkeys(candidates))
            if len(candidates) == 1:
                value.update(source_file=candidates[0][0], destination_file=candidates[0][1], sampled_file_at=now)
            rows[job['id']] = value
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return rows


def collect_context(directory=Path('/var/lib/freeqnap-system'), opened=None):
    base = Path(directory)
    with metadata_db(base / 'state.sqlite3') as db:
        config = setting(db, 'nas', {})
    now = time.time()
    if opened is None:
        try:
            opened = open_files()
        except (OSError, ValueError, subprocess.SubprocessError):
            opened = []
    rows = {}
    for namespace in [base] + sorted((base / 'personal').glob('*'))[:256]:
        if namespace != base and not IDENT.fullmatch(namespace.name):
            continue
        try:
            rows.update(observe(base, namespace, config, opened, now))
        except (OSError, ValueError, sqlite3.Error):
            continue
    return {'sampled_at': now, 'transfers': rows}


def enrich(result, path=Path('/run/freeqnap/transfer-context.json')):
    """The broker-selected rows are the authorization boundary, never request IDs."""
    try:
        sample = read_json(Path(path))
        if not 0 <= time.time() - sample['sampled_at'] <= 180:
            return result
        rows = []
        for row in result['transfers']:
            context = sample['transfers'].get(row['id'])
            rows.append({**row, 'paths': context} if context else row)
        return {**result, 'transfers': rows}
    except (OSError, ValueError, KeyError, TypeError):
        return result
