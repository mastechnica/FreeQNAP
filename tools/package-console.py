#!/usr/bin/env python3
"""Make a source-only console bundle without macOS resource forks or identity."""
import argparse,tarfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
with a.output.open('xb') as stream,tarfile.open(fileobj=stream,mode='w:gz',format=tarfile.PAX_FORMAT) as archive:
 for directory in ('freeqnap','web','deploy','tests','tools','docs'):
  for source in sorted((root/directory).rglob('*')):
   if not source.is_file() or source.is_symlink() or source.name.startswith('._') or '__pycache__' in source.parts or source.suffix=='.pyc':continue
   info=archive.gettarinfo(str(source),str(source.relative_to(root)));info.uid=info.gid=0;info.uname=info.gname='root';info.pax_headers={};info.mode=0o644
   with source.open('rb') as data:archive.addfile(info,data)
print(a.output)
