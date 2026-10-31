"""Root-owned read-only collector, separated from the unprivileged web service."""
import argparse
from pathlib import Path
from .inventory import collect
from .state import atomic

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('/run/freeqnap/inventory.json'))
    args = parser.parse_args()
    atomic(args.output, collect(), mode=0o640)
if __name__ == '__main__':
    main()
