"""Explicit, bounded TFTP receiver for original flash-slot backups only."""
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import time
import zlib
from core import save_private

SIZES={'boot1-original.bin':32*1024**2,'boot2-original.bin':32*1024**2,'spi-original.bin':2*1024**2}


def backup_directory(directory):
    path=Path(directory)
    if path.is_symlink() or not path.is_dir() or path.stat().st_uid!=os.geteuid() or path.stat().st_mode&0o077:
        raise ValueError('An existing private backup directory owned by the serving user is required')
    return path.resolve()


def negotiate_options(fields,expected_size):
    fields=list(fields)
    if fields and fields[-1]==b'':fields.pop()
    if len(fields)%2:raise ValueError('Malformed TFTP options')
    options={}
    for key,value in zip(fields[::2],fields[1::2]):
        key=key.decode('ascii').lower();value=value.decode('ascii')
        if key in options:raise ValueError('Duplicate TFTP option')
        options[key]=value
    accepted={};block_size=512
    if 'blksize' in options:
        size=int(options['blksize'])
        if not 8<=size<=65464:raise ValueError('Invalid requested TFTP block size')
        block_size=min(size,1468);accepted['blksize']=str(block_size)
    if 'tsize' in options:
        if int(options['tsize'])!=expected_size:raise ValueError('Requested backup size differs from exact allowlist size')
        accepted['tsize']=str(expected_size)
    acknowledgement=struct.pack('!H',6)+b''.join(k.encode()+b'\0'+v.encode()+b'\0' for k,v in accepted.items()) if accepted else struct.pack('!HH',4,0)
    return block_size,acknowledgement,options


def receive_backup(bind,peer,name,directory,*,timeout=2,retries=6,options=()):
    if name not in SIZES:raise ValueError('Backup name is not allowlisted')
    directory=backup_directory(directory);destination=directory/name;partial=directory/(name+'.part')
    block_size,initial_ack,requested=negotiate_options(options,SIZES[name])
    print('BACKUP REQUEST '+name+' '+json.dumps({'requested_options':requested,'accepted_block_bytes':block_size}),flush=True)
    if destination.exists() or destination.is_symlink() or (directory/(name+'.json')).exists():raise FileExistsError('Backup already exists; no overwrite permitted')
    fd=os.open(partial,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    digest=hashlib.sha256();crc=0;total=0;block=1;last=0;complete=False
    deadline=time.monotonic()+600
    try:
        with os.fdopen(fd,'wb') as output,socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as transfer:
            transfer.bind((bind,0));transfer.settimeout(timeout)
            while True:
                if time.monotonic()>deadline:raise TimeoutError('Flash backup exceeded its bounded transfer lifetime')
                ack=initial_ack if last==0 else struct.pack('!HH',4,last%65536)
                for attempt in range(retries):
                    transfer.sendto(ack,peer)
                    try:packet,sender=transfer.recvfrom(2048)
                    except socket.timeout:continue
                    if sender!=peer or len(packet)<4 or packet[:2]!=b'\0\3':continue
                    number=struct.unpack('!H',packet[2:4])[0]
                    if number==last%65536:continue # Lost ACK: resend, never append twice.
                    if number!=block%65536:continue
                    break
                else:raise TimeoutError('Flash backup transfer timed out')
                data=packet[4:]
                if len(data)>block_size:raise ValueError(f'Backup block {len(data)} exceeds negotiated {block_size} bytes')
                if total+len(data)>SIZES[name]:raise ValueError('Backup exceeds the explicitly allowed size')
                output.write(data);digest.update(data);crc=zlib.crc32(data,crc);total+=len(data)
                last=block;block+=1
                if len(data)<block_size:
                    if total!=SIZES[name]:raise ValueError('Incomplete flash backup')
                    output.flush();os.fsync(output.fileno())
                    os.link(partial,destination);partial.unlink()
                    save_private(directory/(name+'.json'),{'schema':1,'bytes':total,'sha256':digest.hexdigest(),
                        'crc32':f'{crc:08x}','received_at':time.time(),'uart_crc_verified':False})
                    transfer.sendto(struct.pack('!HH',4,last%65536),peer)
                    complete=True
                    # A retransmitted final block only receives another ACK.
                    end=time.monotonic()+timeout
                    while time.monotonic()<end:
                        transfer.settimeout(max(.01,end-time.monotonic()))
                        try:packet,sender=transfer.recvfrom(2048)
                        except socket.timeout:break
                        if sender==peer and packet[:4]==struct.pack('!HH',3,last%65536):
                            transfer.sendto(struct.pack('!HH',4,last%65536),peer)
                    return {'bytes':total,'sha256':digest.hexdigest(),'crc32':f'{crc:08x}'}
    finally:
        # Preserve failed partial data for explicit reconciliation; never call
        # it a usable backup, and never replace it on an automatic retry.
        if not complete:print('BACKUP INCOMPLETE; partial retained; flash commit stays blocked',flush=True)
