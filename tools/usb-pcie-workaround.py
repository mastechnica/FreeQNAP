#!/usr/bin/env python3
"""Exact-board EJ188 MRRS workaround. No reset, bind, disk or DMA-mask writes."""
import json,os,struct
from pathlib import Path

def capability(data):
    if len(data)<256:raise ValueError('PCI configuration is truncated')
    pos=data[0x34];seen=set()
    while pos:
        if pos in seen or pos<0x40 or pos>0xec or pos%4:raise ValueError('Invalid PCI capability chain')
        seen.add(pos)
        if data[pos]==0x10:return pos
        pos=data[pos+1]
    raise ValueError('PCI Express capability missing')

def desired(control):
    current=(control>>12)&7
    if current not in (0,2):raise ValueError('Unreviewed PCIe read-request setting')
    return control&~0x7000

def main():
    if os.geteuid()!=0:raise ValueError('Root required')
    if Path('/proc/device-tree/compatible').read_bytes().split(b'\0')[0]!=b'qnap,ts-431xeu':raise ValueError('Exact board required')
    p=Path('/sys/bus/pci/devices/0001:01:00.0')
    for key,value in {'vendor':'0x1b6f','device':'0x7052','revision':'0x00','class':'0x0c0330'}.items():
        if (p/key).read_text().strip()!=value:raise ValueError('Exact USB PCI function required')
    fd=os.open(str(p/'config'),os.O_RDWR)
    try:
        data=os.pread(fd,256,0);pos=capability(data)+8;old=struct.unpack_from('<H',data,pos)[0];new=desired(old)
        if new!=old:
            if os.pread(fd,2,pos)!=struct.pack('<H',old):raise ValueError('PCI state changed before write')
            if os.pwrite(fd,struct.pack('<H',new),pos)!=2:raise ValueError('Incomplete PCI configuration write')
        if os.pread(fd,2,pos)!=struct.pack('<H',new):raise ValueError('USB PCIe setting did not verify')
        print(json.dumps({'pci':p.name,'mrrs_bytes':128,'changed':new!=old,'old_control':old,'new_control':new,'disks_written':False}))
    finally:os.close(fd)
if __name__=='__main__':main()
