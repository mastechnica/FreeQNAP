"""Per-volume copy leases. Call mutation checks while holding the metadata lock."""
import contextlib
import fcntl
import hashlib
import os
from pathlib import Path


def base(ctx):
    return getattr(ctx, 'base', ctx)


@contextlib.contextmanager
def lease(ctx, keys, exclusive=False):
    directory = base(ctx).directory / 'volume-leases'
    directory.mkdir(mode=0o700, exist_ok=True)
    with contextlib.ExitStack() as stack:
        for key in sorted(set(keys)):
            if not isinstance(key, str) or not key:
                raise ValueError('Volume identity unavailable for transfer protection')
            path = directory / (hashlib.sha256(key.encode()).hexdigest()+'.lock')
            fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            stack.callback(os.close, fd)
            try:
                fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('This volume is being used by an active transfer. Wait for that transfer before unmounting, locking or ejecting it.') from None
        yield


def idle(ctx, keys):
    # The enclosing metadata lock prevents a new copy from acquiring a shared
    # lease between this check and the completed unmount/eject mutation.
    with lease(ctx, keys, exclusive=True):
        pass
