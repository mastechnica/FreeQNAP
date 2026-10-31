#!/usr/bin/env python3
"""Review-package checks, not a build or hardware certification."""
import hashlib,json,re,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
errors=[]
for path in root.rglob('*'):
 if any(p in ('.git','.private','__pycache__','.venv','dist','build') for p in path.relative_to(root).parts) or not path.is_file():continue
 relative=path.relative_to(root)
 if path.suffix in ('.bin','.img','.heic','.pem','.key','.db','.sqlite3','.log','.ko'):errors.append(str(relative)+': private/binary file not allowed')
 if path.suffix.lower() in ('.md','.py','.sh','.js','.html','.c','.h','.json','.service','.conf'):
  text=path.read_text()
  if relative!=Path('tools/check-package.py') and re.search(r'/Users/|BEGIN [A-Z ]*PRIVATE KEY[-]*\r?\n[A-Za-z0-9+/]{20}|ssh-ed25519 AAAA',text):errors.append(str(relative)+': private path/key marker')
  if path.suffix=='.md':
   for target in re.findall(r'\]\(([^)]+)\)',text):
    if '://' in target or target.startswith('#'):continue
    if not (path.parent/target.split('#')[0]).exists():errors.append(str(relative)+': missing link '+target)
for name,expected in json.loads((root/'docs/hardware-source-files.json').read_text()).items():
 if hashlib.sha256((root/name).read_bytes()).hexdigest()!=expected:errors.append(name+': source hash changed; review and update inventory')
for name in ('installer/target/init','docs/INSTALLING.md','docs/SOURCES.md','licenses/GPL-2.0.txt'):
 if not (root/name).is_file():errors.append(name+': required file missing')
if errors:print('\n'.join(errors));sys.exit(1)
print('PASS: source inventory, required files, Markdown links and private-path/key-marker checks. Manual secret/license review is still required.')
