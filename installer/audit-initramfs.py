#!/usr/bin/env python3
"""Read-only generic-bootstrap identity lint for a directory or uncompressed newc CPIO.

This is a release gate, not proof that arbitrary binaries are secret-free or authentic.
Reports only offending paths/categories, never key or configuration contents.
"""
import argparse,json,os,re,stat
from pathlib import Path,PurePosixPath

MAX_TOTAL=128*1024**2;MAX_FILES=20000
PERSONAL_ROOT='/'+'Users'+'/'
REQUIRED={'init','bin/busybox','freeqnap/boot-record.sh','freeqnap/boot-policy.sh','freeqnap/select-root.sh'}
FORBIDDEN={'etc/freeqnap-install-id','freeqnap/installation.conf','freeqnap/selected.conf','etc/machine-id','var/lib/dbus/machine-id','etc/resolv.conf','etc/fstab'}

def safe_name(value):
    if value in ('.','./'):return ''
    path=PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or '\x00' in value:raise ValueError('Unsafe bootstrap archive path')
    return str(path)

def directory_entries(root):
    root=Path(root)
    if root.is_symlink() or not root.is_dir():raise ValueError('Use a real bootstrap directory')
    total=0;count=0
    for parent,dirs,files in os.walk(root,followlinks=False):
        for leaf in sorted(dirs+files):
            path=Path(parent)/leaf;info=path.lstat();relative=str(path.relative_to(root));count+=1
            if count>MAX_FILES:raise ValueError('Bootstrap file-count limit')
            if stat.S_ISREG(info.st_mode):
                total+=info.st_size
                if total>MAX_TOTAL:raise ValueError('Bootstrap size limit')
                data=path.read_bytes()
            elif stat.S_ISLNK(info.st_mode):data=os.readlink(path).encode()
            else:data=b''
            yield relative,info.st_mode,data

def cpio_entries(path):
    path=Path(path);info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size>MAX_TOTAL:raise ValueError('Use a bounded regular CPIO file')
    with path.open('rb') as stream:raw=stream.read(MAX_TOTAL+1)
    if len(raw)>MAX_TOTAL:raise ValueError('Bootstrap archive size limit')
    offset=0;count=0;seen=set();ended=False
    while offset<len(raw):
        header=raw[offset:offset+110]
        if len(header)!=110 or header[:6] not in (b'070701',b'070702'):raise ValueError('Uncompressed newc/CRC CPIO required')
        try:fields=[int(header[6+i*8:14+i*8],16) for i in range(13)]
        except ValueError:raise ValueError('Malformed CPIO header')
        mode=fields[1];size=fields[6];namesize=fields[11]
        if not 1<=namesize<=4096 or size>MAX_TOTAL:raise ValueError('Invalid CPIO entry bounds')
        start=offset+110;name=raw[start:start+namesize]
        if len(name)!=namesize or not name.endswith(b'\0') or b'\0' in name[:-1]:raise ValueError('Invalid CPIO filename')
        value=name[:-1].decode('utf-8');data_start=(start+namesize+3)&~3;end=data_start+size
        if end>len(raw):raise ValueError('Truncated CPIO data')
        data=raw[data_start:end];offset=(end+3)&~3
        if header[:6]==b'070702' and sum(data)&0xffffffff!=fields[12]:raise ValueError('CPIO checksum mismatch')
        if value=='TRAILER!!!':
            if size or any(raw[offset:]):raise ValueError('Unexpected data after CPIO trailer')
            ended=True;break
        value=safe_name(value)
        if not value:continue
        if value in seen:raise ValueError('Duplicate bootstrap archive path')
        seen.add(value);count+=1
        if count>MAX_FILES:raise ValueError('Bootstrap file-count limit')
        yield value,mode,data
    if not ended:raise ValueError('Missing CPIO trailer')

def audit(entries):
    seen=set();violations=[]
    for path,mode,data in entries:
        path=safe_name(path)
        if not path:continue
        seen.add(path);parts=PurePosixPath(path).parts
        private_home=parts[0] in ('root','home') and not stat.S_ISDIR(mode)
        runtime_state=(parts[0] in ('run','tmp') or path.startswith(('var/log/','var/tmp/','var/lib/'))) and not stat.S_ISDIR(mode)
        if runtime_state:violations.append({'path':path,'reason':'inherited runtime state'})
        if private_home or '/.ssh/' in '/'+path or path.startswith('etc/ssh/ssh_host_') or path.startswith('etc/dropbear/dropbear_') and 'host_key' in path:
            violations.append({'path':path,'reason':'inherited home/SSH credential or host identity'})
        if path in FORBIDDEN and data.strip() and not stat.S_ISDIR(mode):violations.append({'path':path,'reason':'per-installation identity or inherited network/mount state'})
        if path in REQUIRED and not stat.S_ISREG(mode):violations.append({'path':path,'reason':'bootstrap entry point must be a regular file'})
        if stat.S_ISLNK(mode):
            target=data.decode('utf-8',errors='replace')
            if PERSONAL_ROOT in target or '.private/' in target:violations.append({'path':path,'reason':'personal build-host symlink'})
        text_file=path=='init' or path.startswith(('etc/','freeqnap/'))
        if text_file and stat.S_ISREG(mode) and b'\0' not in data:
            text=data.decode('utf-8',errors='replace')
            if re.search(r'-----BEGIN (?:OPENSSH |RSA |EC |ENCRYPTED )?PRIVATE KEY-----|ssh-(?:ed25519|rsa) [A-Za-z0-9+/]{24,}',text):violations.append({'path':path,'reason':'embedded key material'})
            if PERSONAL_ROOT in text or '.private/' in text:violations.append({'path':path,'reason':'personal build-host path'})
            if re.search(r'(?mi)^\s*(?:Address|Gateway|DNS|MACAddress)\s*=',text):violations.append({'path':path,'reason':'fixed network identity in generic bootstrap'})
            if path=='etc/shadow':
                roots=[line.split(':')[1] for line in text.splitlines() if line.startswith('root:')]
                if len(roots)!=1 or not roots[0].startswith(('!','*')):violations.append({'path':path,'reason':'root password is not locked'})
            if path=='etc/passwd':
                for line in text.splitlines():
                    fields=line.split(':')
                    if len(fields)!=7:raise ValueError('Malformed bootstrap account file')
                    try:uid=int(fields[2])
                    except ValueError:raise ValueError('Malformed bootstrap account UID') from None
                    if uid==0 and fields[0]!='root':violations.append({'path':path,'reason':'additional root-equivalent account'})
                    if fields[0]!='nobody' and uid>=1000:violations.append({'path':path,'reason':'inherited human account'})
    missing=sorted(REQUIRED-seen)
    if missing:violations.append({'missing_required':missing})
    if violations:raise ValueError(json.dumps({'generic_bootstrap_audit':False,'violations':violations},sort_keys=True))
    return {'generic_bootstrap_audit':True,'entries_checked':len(seen),'inherited_identity_detected':False,'scope':'Known identity/configuration paths and readable bootstrap configuration; not binary authenticity, exhaustive secret scanning or hardware acceptance'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('path',type=Path);p.add_argument('--cpio',action='store_true');a=p.parse_args();print(json.dumps(audit(cpio_entries(a.path) if a.cpio else directory_entries(a.path)),indent=2))
if __name__=='__main__':main()
