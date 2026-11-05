#!/usr/bin/env python3
"""Expose only configured photo-volume device metadata to the isolated album worker.

Run as root after choosing archive storage. Device I/O remains denied by the
worker's PrivateDevices policy. This does not mount or unlock a volume.
"""
import json,os,re,stat,subprocess
from pathlib import Path
if os.geteuid()!=0:raise SystemExit('Run as root on the NAS after choosing archive storage.')
import sqlite3
base=Path('/var/lib/freeqnap-system');paths=set()
with sqlite3.connect('file:'+str(base/'state.sqlite3')+'?mode=ro',uri=True) as db:
 row=db.execute("SELECT value FROM settings WHERE key='nas'").fetchone()
 if not row:raise SystemExit('NAS storage configuration is missing.')
 config=json.loads(row[0])
for dbpath in [base/'state.sqlite3',*sorted((base/'personal').glob('[a-f0-9]'*32+'/state.sqlite3'))]:
 if dbpath.is_symlink() or not dbpath.is_file():continue
 with sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True) as db:
  row=db.execute("SELECT value FROM settings WHERE key='personal-photos'").fetchone()
 if not row:continue
 cfg=json.loads(row[0]);pool=config.get('pools',{}).get(cfg.get('pool'),{})
 if not pool.get('block_device'):continue
 device=pool['block_device'];mount=pool.get('mountpoint','')
 if not isinstance(device,str) or not re.fullmatch(r'/dev/(?:disk/by-(?:uuid|partuuid)/[a-fA-F0-9-]+|mapper/[A-Za-z0-9_.+-]+|md[0-9]+(?:p[0-9]+)?|sd[a-z]+[0-9]*)',device):raise SystemExit('Unexpected volume device path; inspect archive configuration.')
 rows=json.loads(subprocess.check_output(['findmnt','-J','-M',mount,'-o','SOURCE,UUID,FSROOT,FSTYPE']))['filesystems']
 if len(rows)!=1 or rows[0]['uuid']!=cfg['filesystem_uuid'] or rows[0]['fsroot']!='/' or rows[0]['fstype']!='ext4':raise SystemExit('Archive is unavailable or its mounted identity changed.')
 actual=Path(rows[0]['source']).resolve(strict=True);a=os.stat(device);b=actual.stat()
 if not stat.S_ISBLK(a.st_mode) or not stat.S_ISBLK(b.st_mode) or a.st_rdev!=b.st_rdev or not re.fullmatch(r'/dev/[A-Za-z0-9_./+-]+',str(actual)):raise SystemExit('Archive block-device identity changed.')
 paths.update((device,str(actual)))
folder=Path('/etc/systemd/system/freeqnap-icloud-albums.service.d');folder.mkdir(mode=0o755,exist_ok=True)
target=folder/'archive-device-metadata.conf';raw='[Service]\n# Device node visibility only; PrivateDevices and its I/O denial remain enabled.\nBindReadOnlyPaths=\n'+('BindReadOnlyPaths='+' '.join(sorted(paths))+'\n' if paths else '')
tmp=target.with_suffix('.next');tmp.write_text(raw);tmp.chmod(0o644);os.replace(tmp,target)
subprocess.run(['systemctl','daemon-reload'],check=True)
print('Configured metadata visibility for',len(paths),'specific device paths; device I/O stays blocked.')
