"""Small, bounded GPT layouts, including disks beyond ARM32 buffered-I/O range.

Metadata accesses use aligned O_DIRECT, including the secondary GPT. The caller
must protect OS devices, review immutable identities, and guard every write.
"""
import fcntl
import hashlib
import mmap
import os
import stat
import struct
import uuid
import zlib
from pathlib import Path
from ..state import atomic
from .limits import require_ext4_size

ALIGN=1024**2
LINUX_DATA=uuid.UUID('0fc63daf-8483-4772-8e79-3d69d8477de4')

def layout(size,sector,names):
    if sector not in (512,4096) or size%sector or not 1<=len(names)<=8:raise ValueError('Unsupported aligned GPT geometry')
    start=ALIGN;end=(size-ALIGN)//ALIGN*ALIGN
    span=(end-start)//len(names)//ALIGN*ALIGN
    if span<1024**3:raise ValueError('Each external volume needs at least 1 GiB')
    rows=[]
    for i,name in enumerate(names):
        first=start+i*span;last=end if i==len(names)-1 else first+span
        require_ext4_size(last-first)
        rows.append({'number':i+1,'name':name,'uuid':str(uuid.uuid4()),'start_bytes':first,'bytes':last-first})
    return {'disk_uuid':str(uuid.uuid4()),'bytes':size,'sector_bytes':sector,'volumes':rows}

def images(plan):
    size=plan['bytes'];sector=plan['sector_bytes'];count=size//sector
    entries=bytearray(16384)
    for v in plan['volumes']:
        offset=(v['number']-1)*128
        entries[offset:offset+128]=struct.pack('<16s16sQQQ72s',LINUX_DATA.bytes_le,uuid.UUID(v['uuid']).bytes_le,v['start_bytes']//sector,(v['start_bytes']+v['bytes'])//sector-1,0,v['name'].encode('utf-16-le')[:72].ljust(72,b'\0'))
    entries_crc=zlib.crc32(entries)
    def header(current,other,table):
        h=bytearray(sector)
        struct.pack_into('<8sIIIIQQQQ16sQIII',h,0,b'EFI PART',0x10000,92,0,0,current,other,ALIGN//sector,(size-ALIGN)//ALIGN*ALIGN//sector-1,uuid.UUID(plan['disk_uuid']).bytes_le,table,128,128,entries_crc)
        struct.pack_into('<I',h,16,zlib.crc32(h[:92]));return h
    primary=bytearray(ALIGN);secondary=bytearray(ALIGN)
    # Protective MBR is 512 bytes even on 4Kn devices.
    primary[446:462]=struct.pack('<B3sB3sII',0,b'\0\x02\0',0xee,b'\xff'*3,1,min(count-1,0xffffffff));primary[510:512]=b'\x55\xaa'
    primary[sector:2*sector]=header(1,count-1,2);primary[2*sector:2*sector+len(entries)]=entries
    table_sector=count-1-len(entries)//sector;relative=table_sector*sector-(size-ALIGN)
    secondary[relative:relative+len(entries)]=entries;secondary[-sector:]=header(count-1,1,table_sector)
    return [(size-ALIGN,bytes(secondary)),(0,bytes(primary))]

def transfer(fd,offset,data=None,length=ALIGN):
    with mmap.mmap(-1,length) as buf:
        if data is not None:
            if len(data)!=length:raise ValueError('Aligned metadata length mismatch')
            buf[:]=data;n=os.pwritev(fd,[buf],offset)
            if n!=length:raise OSError('Short direct metadata write; do not retry initialization')
            return
        n=os.preadv(fd,[buf],offset)
        if n!=length:raise OSError('Short direct metadata read; initialization refused')
        return buf[:]

def write(device,plan,backup,guard):
    """Back up both metadata regions, then write and verify both GPT copies.

    The original filesystem data is not backed up. On failure the caller retains
    its operation checkpoint; there is no automatic retry or table restoration.
    """
    guard();expected=os.stat(device);size=plan['bytes']
    if not stat.S_ISBLK(expected.st_mode):raise ValueError('GPT initialization requires a protected block device')
    backup=Path(backup);backup.mkdir(mode=0o700,parents=True,exist_ok=False)
    fd=os.open(device,os.O_RDWR|os.O_DIRECT|os.O_EXCL|os.O_CLOEXEC)
    try:
        if os.fstat(fd).st_rdev!=expected.st_rdev:raise ValueError('Block identity changed opening GPT target')
        actual=struct.unpack('=Q',fcntl.ioctl(fd,0x80001272 | (struct.calcsize('P')<<16),b'\0'*8))[0]
        sector=struct.unpack('=I',fcntl.ioctl(fd,0x1268,b'\0'*4))[0]
        if actual!=size or sector!=plan['sector_bytes']:raise ValueError('Opened GPT target geometry changed')
        saved=[]
        for offset,label in [(0,'first-mib'),(size-ALIGN,'last-mib')]:
            guard();data=transfer(fd,offset);path=backup/(label+'.bin')
            with path.open('xb') as f:
                os.chmod(path,0o600);f.write(data);f.flush();os.fsync(f.fileno())
            saved.append({'offset':offset,'bytes':len(data),'file':path.name,'sha256':hashlib.sha256(data).hexdigest()})
        atomic(backup/'manifest.json',{'layout':plan,'regions':saved,'full_data_backup':False})
        for offset,data in images(plan):
            guard();transfer(fd,offset,data=data);os.fsync(fd)
            if transfer(fd,offset)!=data:raise OSError('GPT direct readback mismatch; initialization stopped')
        guard()
    finally:os.close(fd)
