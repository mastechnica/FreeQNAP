"""Atomic private configuration archives, consistent SQLite, bounded retention."""
import fcntl, hashlib, json, os, re, shutil, sqlite3, stat, tarfile, tempfile, time, secrets
from pathlib import Path
from .state import atomic
MAX_FILE = 64 * 1024 ** 2
MAX_TOTAL = 256 * 1024 ** 2

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024 ** 2), b''):
            h.update(data)
    return h.hexdigest()

def mounted(destination, expected_uuid, runner=None):
    import subprocess
    p = Path(destination).resolve()
    rows = json.loads((runner or subprocess.check_output)(['findmnt', '-J', '-T', str(p), '-o', 'TARGET,UUID'], text=True))['filesystems']
    if len(rows) != 1 or rows[0].get('uuid') != expected_uuid:
        raise ValueError('Destination volume is missing or changed; no fallback to OS root')
    return p

def create(source, destination, keep=7):
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    if not 1 <= keep <= 365:
        raise ValueError('Retention must be 1–365 successful archives')
    if not source.is_dir() or destination == source or source in destination.parents:
        raise ValueError('Backup destination cannot be inside source')
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination.chmod(0o700)
    with (destination / '.backup.lock').open('a') as lock:
        os.fchmod(lock.fileno(), 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        name = 'freeqnap-config-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + secrets.token_hex(4) + '.tar.gz'
        target = destination / name
        partial = destination / (name + '.partial')
        total = 0
        try:
            with tempfile.TemporaryDirectory(prefix='.stage-', dir=destination) as work:
                stage = Path(work)
                files = {}
                excluded = []
                for item in sorted(source.rglob('*')):
                    info = item.lstat()
                    if not stat.S_ISREG(info.st_mode) or item.name.endswith(('-wal', '-shm')):
                        continue
                    relative = item.relative_to(source)
                    if info.st_size > MAX_FILE or total + info.st_size > MAX_TOTAL:
                        raise ValueError('Configuration archive exceeds bounded size')
                    out = stage / 'configuration' / relative
                    out.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    with item.open('rb') as original:
                        sqlite_header = original.read(16) == b'SQLite format 3\x00'
                    if sqlite_header:
                        src = sqlite3.connect(item.as_uri() + '?mode=ro', uri=True)
                        dst = sqlite3.connect(out)
                        try:
                            src.backup(dst)
                            tables = {r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                            for table in ('sessions', 'oidc_states'):
                                if table in tables:
                                    dst.execute('DELETE FROM ' + table)
                            dst.commit()
                            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                                raise ValueError('SQLite integrity verification failed')
                        finally:
                            src.close()
                            dst.close()
                    elif item.suffix in ('.db', '.sqlite', '.sqlite3'):
                        excluded.append(str(relative))
                        continue
                    else:
                        shutil.copyfile(item, out)
                    out.chmod(0o600)
                    actual_size = out.stat().st_size
                    if actual_size > MAX_FILE or total + actual_size > MAX_TOTAL:
                        raise ValueError('Snapshot exceeds bounded archive size')
                    total += actual_size
                    files[str(out.relative_to(stage))] = digest(out)
                manifest = {'format': 'freeqnap-config-v1', 'created_at': time.time(), 'files': files, 'sqlite_consistent': True, 'sessions_excluded': True, 'excluded_non_sqlite_databases': excluded, 'data_files_included': False, 'os_or_flash_included': False, 'automatic_restore_available': False}
                atomic(stage / 'manifest.json', manifest)
                with tarfile.open(partial, 'w:gz') as tar:
                    for item in sorted(stage.rglob('*')):
                        if item.is_file():
                            tar.add(item, arcname=str(item.relative_to(stage)), recursive=False)
            partial.chmod(0o600)
            with partial.open('rb') as stream:
                os.fsync(stream.fileno())
            checksum = digest(partial)
            os.replace(partial, target)
            atomic(destination / (name + '.json'), {'sha256': checksum, 'bytes': target.stat().st_size, 'manifest': manifest})
            verify(target)
            accepted = []
            for path in sorted(destination.glob('freeqnap-config-*.tar.gz'), key=lambda p: p.stat().st_mtime, reverse=True):
                try:
                    verify(path)
                    accepted.append(path)
                except (OSError, ValueError, tarfile.TarError):
                    continue
            for old in accepted[keep:]:
                old.unlink()
                old.with_name(old.name + '.json').unlink()
            return {'name': name, 'sha256': checksum, 'bytes': target.stat().st_size, 'files': len(files), 'sessions_excluded': True}
        except BaseException:
            raise

def verify(path):
    """Bounded, non-extracting verification; malformed metadata is a failure."""
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Regular managed archive required')
    try:
        receipt_path = path.with_name(path.name + '.json')
        if receipt_path.is_symlink() or receipt_path.stat().st_size > 8 * 1024**2:
            raise ValueError('Invalid archive receipt')
        receipt = json.loads(receipt_path.read_text())
        if not isinstance(receipt, dict) or not isinstance(receipt.get('bytes'), int) or not re.fullmatch('[0-9a-f]{64}', str(receipt.get('sha256', ''))):
            raise ValueError('Malformed archive receipt')
        if path.stat().st_size > MAX_TOTAL * 2 or path.stat().st_size != receipt['bytes'] or digest(path) != receipt['sha256']:
            raise ValueError('Archive checksum mismatch')
        with tarfile.open(path) as tar:
            rows = []
            total = 0
            names = set()
            for member in tar:
                total += member.size
                if len(rows) >= 20000 or total > MAX_TOTAL + MAX_FILE:
                    raise ValueError('Archive exceeds verification bounds')
                if not member.isfile() or member.name in names or Path(member.name).is_absolute() or '..' in Path(member.name).parts or not 0 <= member.size <= MAX_FILE:
                    raise ValueError('Unsafe archive members')
                names.add(member.name)
                rows.append(member)
            if 'manifest.json' not in names:
                raise ValueError('Archive manifest missing')
            manifest = json.load(tar.extractfile('manifest.json'))
            if not isinstance(manifest, dict) or manifest.get('format') != 'freeqnap-config-v1' or not isinstance(manifest.get('files'), dict):
                raise ValueError('Unsupported archive manifest')
            if names != set(manifest['files']) | {'manifest.json'}:
                raise ValueError('Archive contains unexpected/missing files')
            for name, expected in manifest['files'].items():
                if not name.startswith('configuration/') or not re.fullmatch('[0-9a-f]{64}', str(expected)):
                    raise ValueError('Invalid archive member record')
                if hashlib.sha256(tar.extractfile(name).read()).hexdigest() != expected:
                    raise ValueError('Archive member checksum mismatch')
        return {'verified': True, 'name': path.name, 'sha256': receipt['sha256'], 'files': len(manifest['files']), 'restore_execution_available': False}
    except (KeyError, TypeError, AttributeError, EOFError) as error:
        raise ValueError('Malformed archive metadata') from error

def list_backups(directory):
    result = []
    for path in sorted(Path(directory).glob('freeqnap-config-*.tar.gz'), reverse=True):
        try:
            result.append(verify(path))
        except (OSError, ValueError, tarfile.TarError) as e:
            result.append({'name': path.name, 'verified': False, 'error': str(e)})
    return result

def restore_preview(path):
    result = verify(path)
    with tarfile.open(path) as tar:
        manifest = json.load(tar.extractfile('manifest.json'))
    return {**result, 'files': sorted(manifest['files']), 'sessions_restored': False, 'can_restore': False, 'reason': 'Restore execution requires separate target mapping, stopped writers and accepted recovery tests; it is never automatic.'}

def mirror(archive, destination, expected_uuid, keep=7, runner=None):
    """Copy one verified archive; a missing data mount must never fill OS root."""
    archive = Path(archive)
    if not 1 <= keep <= 365:
        raise ValueError('Retention must be 1–365 successful archives')
    verify(archive)
    destination = mounted(destination, expected_uuid, runner)
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination.chmod(0o700)
    with (destination / '.backup.lock').open('a') as lock:
        os.fchmod(lock.fileno(), 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        target = destination / archive.name
        if target.exists():
            existing = verify(target)
            if existing['sha256'] != digest(archive):
                raise ValueError('Existing mirror differs; no overwrite')
            return existing
        partial = target.with_name(target.name + '.partial')
        fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with archive.open('rb') as src, os.fdopen(fd, 'wb') as dst:
            shutil.copyfileobj(src, dst, 1024 ** 2)
            dst.flush()
            os.fsync(dst.fileno())
        mounted(destination, expected_uuid, runner)
        if digest(partial) != digest(archive):
            raise ValueError('Mirror checksum mismatch')
        os.replace(partial, target)
        atomic(target.with_name(target.name + '.json'), json.loads(archive.with_name(archive.name + '.json').read_text()))
        result = verify(target)
        accepted = []
        for path in sorted(destination.glob('freeqnap-config-*.tar.gz'), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                verify(path)
                accepted.append(path)
            except (OSError, ValueError, tarfile.TarError):
                continue
        for old in accepted[keep:]:
            old.unlink()
            old.with_name(old.name + '.json').unlink()
        return result
