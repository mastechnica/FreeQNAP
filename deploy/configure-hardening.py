#!/usr/bin/env python3
"""Inspect or apply the exact-board policy disabling unprivileged eBPF.

Default is read-only. Privileged BPF, networking and notification settings are
unchanged. This does not repair firmware IBE configuration or certify mitigation.
"""
import argparse,json,os,re
from pathlib import Path
BOARD=Path('/proc/device-tree/compatible')
RUNTIME=Path('/proc/sys/kernel/unprivileged_bpf_disabled')
TARGET=Path('/etc/sysctl.d/90-freeqnap-hardening.conf')

def policy(value):
    if value not in (0,1,2):raise ValueError('Unknown BPF policy')
    # Preserve an already irreversible administrator restriction.
    desired=1 if value==1 else 2
    return desired,'# FreeQNAP: privileged BPF remains available.\nkernel.unprivileged_bpf_disabled = '+str(desired)+'\n'

def policy_paths():
    paths=[Path('/etc/sysctl.conf')]
    for directory in ('/etc/sysctl.d','/run/sysctl.d','/usr/local/lib/sysctl.d','/usr/lib/sysctl.d','/lib/sysctl.d'):
        paths.extend(Path(directory).glob('*.conf'))
    return paths

def apply(enabled=False):
    if os.geteuid()!=0 or BOARD.read_bytes().split(b'\0')[0]!=b'qnap,ts-431xeu':raise ValueError('Exact NAS board and root required')
    before=int(RUNTIME.read_text());desired,text=policy(before)
    if TARGET.is_symlink():raise ValueError('Refusing symlink policy')
    if TARGET.exists() and TARGET.read_text()!=text:raise ValueError('Existing policy must be reconciled first')
    conflicts=[]
    for path in policy_paths():
        if path==TARGET or not path.is_file():continue
        for line in path.read_text().splitlines():
            match=re.match(r'^\s*-?kernel[./]unprivileged_bpf_disabled\s*=\s*(\S+)',line)
            if match and match[1]!=str(desired):conflicts.append(str(path))
    if enabled and conflicts:raise ValueError('Conflicting BPF policy requires review')
    if enabled:
        TARGET.parent.mkdir(parents=True,exist_ok=True)
        if not TARGET.exists():
            fd=os.open(TARGET,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
            with os.fdopen(fd,'w') as stream:stream.write(text);stream.flush();os.fsync(stream.fileno())
            fd=os.open(TARGET.parent,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
        # Never reload unrelated sysctl settings; retain the policy on failure.
        if before!=desired:RUNTIME.write_text(str(desired)+'\n')
        if int(RUNTIME.read_text())!=desired:raise ValueError('Runtime BPF restriction did not verify; policy retained')
    return {'read_only':not enabled,'before':before,'after':int(RUNTIME.read_text()),'policy_saved':TARGET.exists(),'conflicting_policy_count':len(conflicts),'privileged_bpf_changed':False,'firmware_mitigation_verified':False}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--apply',action='store_true');a=p.parse_args();print(json.dumps(apply(a.apply)))
if __name__=='__main__':main()
