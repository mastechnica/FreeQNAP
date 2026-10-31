#!/usr/bin/env python3
"""Private root-password setup. No password/hash belongs in CLI arguments or logs."""
import argparse
from datetime import datetime,timezone
import getpass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import warnings


def validate_password(password):
    if not isinstance(password,str) or len(password)<12:
        raise ValueError('Use at least 12 characters for the root password.')
    if len(password.encode('utf-8'))>1024 or any(c in password for c in ('\r','\n','\0')):
        raise ValueError('Password contains an unsupported character or is too long.')
    return password


def prompt_password(reader=getpass.getpass):
    # Never fall back to an echoed terminal read.
    with warnings.catch_warnings():
        warnings.simplefilter('error',getpass.GetPassWarning)
        first=reader('New root password: ')
        second=reader('Confirm root password: ')
    validate_password(first)
    if first!=second:raise ValueError('The passwords do not match.')
    return first


def identified_root(root, expected):
    root=Path(root)
    if os.geteuid()!=0:raise PermissionError('Root privileges required on the installation target')
    if root.is_symlink() or not re.fullmatch('[0-9a-f]{32}',expected):raise ValueError('Invalid installation target')
    marker=root/'etc/freeqnap-install-id'
    if marker.is_symlink() or not marker.is_file() or marker.stat().st_uid!=0 or marker.stat().st_mode&0o022:
        raise ValueError('Protected installation marker required')
    if marker.read_text().strip()!=expected:raise ValueError('Installation identity mismatch')
    return root.resolve()


def password_set(root,expected,password):
    root=identified_root(root,expected);validate_password(password)
    command=['/usr/sbin/chpasswd'] if root==Path('/') else ['/usr/sbin/chroot',str(root),'/usr/sbin/chpasswd']
    # Input goes directly to the local target utility, never through a shell.
    result=subprocess.run(command,input='root:'+password+'\n',text=True,capture_output=True,timeout=30)
    if result.returncode:raise RuntimeError('Root password update failed; setup remains required.')
    shadow=root/'etc/shadow'
    entry=next((r.split(':',2)[1] for r in shadow.read_text().splitlines() if r.startswith('root:')),'')
    if not entry.startswith('$'):raise RuntimeError('Root password did not become usable; setup remains required.')
    state=root/'etc/freeqnap';state.mkdir(mode=0o700,parents=True,exist_ok=True)
    path=state/'credentials.json';temporary=state/'credentials.next'
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:
        json.dump({'root_password_set':True,'at':datetime.now(timezone.utc).isoformat(),
                   'ssh_password_policy_changed':False},stream);stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)
    (state/'require-root-password').unlink(missing_ok=True)


def password_defer(root,expected):
    root=identified_root(root,expected)
    key=root/'root/.ssh/authorized_keys'
    if key.is_symlink() or not key.is_file() or key.stat().st_uid!=os.geteuid() or key.stat().st_mode&0o077 or not key.read_text().startswith('ssh-ed25519 '):
        raise ValueError('A protected administrator key is required to defer password setup')
    entry=next((r.split(':',2)[1] for r in (root/'etc/shadow').read_text().splitlines() if r.startswith('root:')),'')
    if not entry.startswith(('!','*')):raise ValueError('Deferral requires an already locked root password; existing passwords are not changed')
    config=(root/'etc/ssh/sshd_config.d/00-freeqnap.conf').read_text()
    for rule in ('PasswordAuthentication no','KbdInteractiveAuthentication no','PermitEmptyPasswords no','PermitRootLogin prohibit-password'):
        if rule not in config.splitlines():raise ValueError('Key-only SSH policy required')
    state=root/'etc/freeqnap';state.mkdir(mode=0o700,parents=True,exist_ok=True)
    path=state/'root-password-deferred';path.write_text('Root password remains locked. Administrator SSH key is enabled. Set a local password later with passwd.\n');path.chmod(0o600)
    (state/'require-root-password').unlink(missing_ok=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',choices=['/','/target'],default='/')
    p.add_argument('--expected-install-id')
    p.add_argument('--stdin',action='store_true',help='Internal installer mode over the pinned encrypted transport')
    p.add_argument('--defer',action='store_true',help='Keep root password locked and allow the supplied SSH key; set a password later with passwd')
    a=p.parse_args();root=Path(a.root)
    if a.stdin and a.defer:raise ValueError('Choose one password setup method')
    if not a.stdin and not a.defer and not (root/'etc/freeqnap/require-root-password').exists():return
    expected=a.expected_install_id or (root/'etc/freeqnap-install-id').read_text().strip()
    identified_root(root,expected)
    if a.defer:
        password_defer(root,expected)
        print('Password setup deferred. Root password stays locked; administrator SSH key remains available. Set a password later with passwd.')
        return
    if a.stdin:
        raw=sys.stdin.buffer.read(1026)
        if len(raw)>1025:raise ValueError('Password input too long')
        if raw.endswith(b'\n'):raw=raw[:-1]
        password_set(root,expected,raw.decode('utf-8'))
        return
    print('FreeQNAP first login: choose the local root password. Input is hidden.')
    while True:
        try:password=prompt_password()
        except ValueError as error:print(str(error));continue
        password_set(root,expected,password)
        print('Root password set. Continuing startup. SSH password policy is unchanged.')
        return


if __name__=='__main__':
    try:main()
    except (KeyboardInterrupt,EOFError,getpass.GetPassWarning):raise SystemExit('Password setup is incomplete; no echoed fallback is allowed.')
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):raise SystemExit('Password setup failed; check the local console. No password was logged.')
