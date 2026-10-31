#!/usr/bin/env python3
"""Audit base-image identity and configuration access before distribution."""
import argparse
from pathlib import PurePosixPath
import tarfile


def audit(path):
    with tarfile.open(path,'r:gz') as archive:
        rows={str(PurePosixPath(m.name)):m for m in archive.getmembers()}
        def member(name):
            if name not in rows:raise ValueError('Required base image member missing: '+name)
            return rows[name]
        for name in ('etc','etc/systemd','etc/systemd/network'):
            m=member(name)
            if not m.isdir() or not m.mode&0o001:raise ValueError('Network configuration directory is not traversable by its service user')
        network=member('etc/systemd/network/10-freeqnap-wired.network')
        if not network.isfile() or network.uid!=0 or not network.mode&0o004 or network.mode&0o022:
            raise ValueError('Network profile must be root-owned, service-readable and protected from other writers')
        data=archive.extractfile(network).read().decode()
        if 'DHCP=yes' not in data.splitlines() or any(line.startswith(('Address=','Gateway=')) for line in data.splitlines()):
            raise ValueError('Generic base network profile must retain DHCP defaults')
        machine=member('etc/machine-id')
        if not machine.isfile() or machine.uid!=0 or not machine.mode&0o004 or machine.mode&0o022:
            raise ValueError('Empty machine identity file must remain readable by network services')
        if archive.extractfile(machine).read()!=b'':raise ValueError('Base contains an inherited machine identity')
        shadow=archive.extractfile(member('etc/shadow')).read().decode()
        root=next((line.split(':',2)[1] for line in shadow.splitlines() if line.startswith('root:')),'')
        if not root.startswith(('!','*')):raise ValueError('Base root password must be locked')
        if any(name=='root/.ssh/authorized_keys' or name.startswith('etc/ssh/ssh_host_') or name=='etc/freeqnap-install-id' for name in rows):
            raise ValueError('Base contains a per-installation credential or identity')
    return {'identity_free':True,'root_password_locked':True,'dhcp_profile_service_readable':True}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive');a=p.parse_args()
    print(audit(a.archive))
