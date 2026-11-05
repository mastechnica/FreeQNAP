"""Root-owned read-only collector, separated from the unprivileged web service."""
import argparse
import sqlite3
from pathlib import Path
from .inventory import collect
from .state import atomic

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('/run/freeqnap/inventory.json'))
    args = parser.parse_args()
    # Transfer observation never acquires the storage lock or touches file contents.
    # Failure must not prevent the independent hardware inventory from refreshing.
    from .transfer_context import collect_context
    try:
        atomic(args.output.with_name('transfer-context.json'), collect_context(), mode=0o640)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        pass
    from .storage_status import observe
    try:
        atomic(args.output.with_name('storage-status.json'), observe(), mode=0o640)
    except (OSError, ValueError):
        pass
    atomic(args.output, collect(), mode=0o640)
if __name__ == '__main__':
    main()
