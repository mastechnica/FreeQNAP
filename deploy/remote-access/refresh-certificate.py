#!/usr/bin/env python3
"""Refresh only the dedicated remote proxy after its existing TLS bundle changes."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import os

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--certificate',type=Path,required=True)
p.add_argument('--key',type=Path,required=True)
p.add_argument('--stamp',type=Path,required=True)
a=p.parse_args()
os.umask(0o077)
for path in (a.certificate,a.key):
    if not path.is_file() or path.stat().st_size>65536:raise SystemExit('Invalid TLS bundle')
subprocess.run(['openssl','x509','-in',str(a.certificate),'-checkend','3600','-noout'],check=True,stdout=subprocess.DEVNULL)
cert=subprocess.check_output(['openssl','x509','-in',str(a.certificate),'-pubkey','-noout'])
key=subprocess.check_output(['openssl','pkey','-in',str(a.key),'-pubout'],stderr=subprocess.DEVNULL)
if cert!=key:raise SystemExit('TLS certificate and key do not match; running proxy retained')
digest=hashlib.sha256(a.certificate.read_bytes()+a.key.read_bytes()).hexdigest()
if a.stamp.exists() and a.stamp.read_text().strip()!=digest:
    subprocess.run(['systemctl','try-restart','auraview-freeqnap-proxy.service'],check=True)
a.stamp.parent.mkdir(parents=True,exist_ok=True)
temp=a.stamp.with_suffix('.new');temp.write_text(digest+'\n');temp.chmod(0o600);temp.replace(a.stamp)
