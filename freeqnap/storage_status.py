"""Read-only observation of the shared storage lock; never bypasses that lock."""
import fcntl
import json
import os
from pathlib import Path
import stat
import time

MUTATIONS = frozenset(('external.import','external.mount','external.unlock','external.create','external.eject','external.forget','external.lock-session','storage.create','storage.unlock','storage.lock'))


def observe(path=Path('/var/lib/freeqnap-system/operations.lock')):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError('Invalid storage lock')
        busy = False
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            busy = True
        return {'busy': busy, 'sampled_at': time.time()}
    finally:
        os.close(fd)


def read(path=Path('/run/freeqnap/storage-status.json')):
    try:
        if path.stat().st_size > 4096:
            raise ValueError('Invalid storage observation')
        value = json.loads(path.read_text())
        if not isinstance(value['busy'], bool) or not 0 <= time.time()-value['sampled_at'] < 120:
            raise ValueError('Storage observation is stale')
        return value
    except (OSError, ValueError, KeyError, TypeError):
        return {'busy': None, 'unavailable': True}


def guard(operation, path=Path('/run/freeqnap/storage-status.json')):
    if operation not in MUTATIONS:
        return
    value = read(path)
    if value['busy'] is True:
        raise ValueError('Storage busy: a file copy or another storage operation is using the storage lock. Nothing was submitted. Wait for it to finish, then prepare a fresh confirmation.')
    if value['busy'] is None:
        raise ValueError('Storage availability could not be checked. Nothing was submitted. Refresh USB Storage in a moment before trying again.')
