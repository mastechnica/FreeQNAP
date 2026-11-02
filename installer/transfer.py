#!/usr/bin/env python3
"""One-client boot TFTP; optional explicit, bounded original-flash backups."""
import argparse
import hashlib
import re
import errno
import json
import os
import signal
import socket
import struct
import sys
import time
from core import verified_image,local_pair
from backups import backup_directory,receive_backup,SIZES


def bind_when_available(server, address, wait_seconds=300, *, emit=print,
                        clock=time.monotonic, sleep=time.sleep):
    """Wait for an existing host configuration to become active; never set it."""
    deadline=clock()+wait_seconds
    announced=False
    while True:
        try:
            server.bind(address)
            return
        except OSError as error:
            if error.errno!=errno.EADDRNOTAVAIL:
                raise
            if not announced:
                emit(f'WAITING for host address {address[0]}. Bring the selected network link online; for a direct cable, power on the NAS. Serial capture must already be armed.',flush=True)
                announced=True
            if clock()>=deadline:
                raise TimeoutError(f'Host address {address[0]} is still unavailable. Check the cable and host network configuration, then retry.') from error
            sleep(min(.5,max(0,deadline-clock())))


def load_boot_images(directory,*,allow_ram_only=False,additional_ram_release=None,rollback_release=None,rollback_sha256=None):
    if additional_ram_release and rollback_release:raise ValueError('Choose a comparison image or a rollback image, not both')
    if rollback_sha256 and not rollback_release:raise ValueError('Rollback pin requires a rollback release')
    manifest,payload=verified_image(directory,allow_ram_only=allow_ram_only)
    images={b'uImage':payload}
    if additional_ram_release:
        if not allow_ram_only or manifest.get('ram_only') is not True or manifest.get('flash_allowed') is not False:raise ValueError('Paired diagnostic serving requires two explicit RAM-only releases')
        extra,data=verified_image(additional_ram_release,allow_ram_only=True)
        kernel=manifest.get('kernel') or manifest.get('kernel_release');other=extra.get('kernel') or extra.get('kernel_release')
        if extra.get('ram_only') is not True or extra.get('flash_allowed') is not False or not isinstance(kernel,str) or not kernel or other!=kernel:raise ValueError('Both paired images must prohibit flash and use the same kernel')
        images[b'experiment.uImage']=data
    if rollback_release:
        if not allow_ram_only or manifest.get('ram_only') is not True or manifest.get('flash_allowed') is not False:raise ValueError('Rollback serving requires an explicit flash-prohibited RAM candidate')
        if not isinstance(rollback_sha256,str) or not re.fullmatch(r'[0-9a-f]{64}',rollback_sha256):raise ValueError('Pin the independently verified installed-image SHA-256')
        rollback,data=verified_image(rollback_release)
        if rollback.get('generic_root_selector') is not True or hashlib.sha256(data).hexdigest()!=rollback_sha256:raise ValueError('Rollback image is not the pinned generic installed image')
        images[b'rollback.uImage']=data
    return images

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--release',required=True);p.add_argument('--bind',required=True)
    p.add_argument('--allow-ram-only',action='store_true',help='Explicitly serve a RAM-only diagnostic that normal boot/flash tools reject')
    p.add_argument('--additional-ram-release',help='Serve one same-kernel RAM-only comparison as experiment.uImage')
    p.add_argument('--rollback-release',help='Also serve a separately pinned installed generic image as rollback.uImage')
    p.add_argument('--rollback-sha256',help='Independent prior installed-image verification SHA-256, required with --rollback-release')
    p.add_argument('--client',required=True);p.add_argument('--port',type=int,default=69)
    p.add_argument('--receive-backups',help='Opt in to receiving only three original flash backups into an existing private directory; never overwrite')
    p.add_argument('--log-file',help='Append metadata-only server diagnostics to a private local file')
    p.add_argument('--wait-seconds',type=int,default=300,
                   help='Wait for the chosen host address to become active; no adapter is configured')
    p.add_argument('--seconds',type=int,default=3600);a=p.parse_args()
    bind,client=local_pair(a.bind,a.client);images=load_boot_images(a.release,allow_ram_only=a.allow_ram_only,additional_ram_release=a.additional_ram_release,rollback_release=a.rollback_release,rollback_sha256=a.rollback_sha256)
    if a.allow_ram_only and a.receive_backups:raise ValueError('RAM diagnostics do not enable backup uploads')
    if not 1<=a.port<=65535:raise ValueError('Invalid UDP port')
    if not 0<=a.wait_seconds<=3600:raise ValueError('Address wait must be between zero and 3600 seconds')
    server=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    bind_when_available(server,(bind,a.port),a.wait_seconds)
    server.settimeout(.5)
    if os.geteuid()==0:
        uid=int(os.environ.get('SUDO_UID','0'));gid=int(os.environ.get('SUDO_GID','0'))
        if uid<=0 or gid<=0:raise ValueError('Start via sudo from a normal user; service drops privileges')
        os.setgroups([]);os.setgid(gid);os.setuid(uid)
    backups=backup_directory(a.receive_backups) if a.receive_backups else None
    if a.log_file:
        fd=os.open(a.log_file,os.O_WRONLY|os.O_APPEND|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
        st=os.fstat(fd)
        if st.st_uid!=os.geteuid() or st.st_mode&0o077:os.close(fd);raise ValueError('Private owned log file required')
        output=os.fdopen(fd,'a',buffering=1)
        class LogOutput:
            def __init__(self,original):self.original=original
            def write(self,value):self.original.write(value);output.write(value)
            def flush(self):self.original.flush();output.flush()
        sys.stdout=LogOutput(sys.stdout)
    running=True
    def stop(*_):
        nonlocal running
        running=False
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    mode='three bounded original-flash backups; no overwrite' if backups else 'no uploads'
    print(f'READY {bind}:{a.port}; client {client}; {len(images)} pinned boot image(s); UID={os.geteuid()}; {mode}',flush=True)
    deadline=time.monotonic()+min(max(a.seconds,1),28800)
    while running and time.monotonic()<deadline:
        try:request,peer=server.recvfrom(2048)
        except socket.timeout:continue
        if peer[0]!=client:continue
        fields=request[2:].split(b'\0')
        if request[:2]==b'\0\2' and backups and len(fields)>=3 and fields[1].lower()==b'octet':
            try:
                name=fields[0].decode('ascii')
                if name not in SIZES:raise ValueError('Only three exact original-flash backup names are allowed')
                result=receive_backup(bind,peer,name,backups,options=fields[2:])
                print('BACKUP RECEIVED '+name+' '+json.dumps(result)+'; UART CRC comparison still required',flush=True)
            except (OSError,ValueError) as error:
                server.sendto(struct.pack('!HH',5,2)+b'Backup refused; inspect private receiver log\0',peer)
                print('BACKUP REFUSED: '+str(error),flush=True)
            continue
        if request[:2]!=b'\0\1' or len(fields)<3 or fields[0] not in images or fields[1].lower()!=b'octet':
            server.sendto(struct.pack('!HH',5,2)+b'Only the pinned boot image can be read\0',peer);continue
        payload=images[fields[0]]
        print('TRANSFER START '+fields[0].decode('ascii'),flush=True)
        complete=True
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as transfer:
            transfer.bind((bind,0));transfer.settimeout(2)
            for block,offset in enumerate(range(0,len(payload)+1,512),1):
                data=payload[offset:offset+512];packet=struct.pack('!HH',3,block%65536)+data
                for attempt in range(6):
                    transfer.sendto(packet,peer)
                    try:reply,sender=transfer.recvfrom(2048)
                    except socket.timeout:continue
                    if sender==peer and reply==struct.pack('!HH',4,block%65536):break
                else:complete=False;break
                if not running:complete=False;break
                if len(data)<512:break
        print('TRANSFER COMPLETE; target CRC still required' if complete else 'TRANSFER FAILED; RAM boot must remain blocked',flush=True)
    server.close()


if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:raise SystemExit(130)
    except (OSError,ValueError) as error:
        raise SystemExit('Boot server not started: '+str(error))
