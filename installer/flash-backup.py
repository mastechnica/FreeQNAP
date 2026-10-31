#!/usr/bin/env python3
"""Read and verify original kernel slots and full SPI through vendor U-Boot.

No erase, programming, environment save, reset or boot command exists here.
The separately started one-client TFTP helper must explicitly allow backups.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import zlib
from core import Console,local_pair,observed_profile,save_private
from backups import SIZES

READ=0x10000000
REREAD=0x14000000
SLOTS={'boot1-original.bin':('nand',0,0x2000000),
       'boot2-original.bin':('nand',0x0f800000,0x2000000),
       'spi-original.bin':('spi',0,0x200000)}


def crc_result(output):
    matches=re.findall(r'CRC32 for [0-9a-f]+ \.\.\. [0-9a-f]+ ==> ([0-9a-f]{8})',output)
    if len(matches)!=1:raise ValueError('No single fresh U-Boot CRC result')
    return matches[0]


def verified_local_backup(path,expected_crc):
    name=Path(path).name
    if name not in SIZES or path.is_symlink() or not path.is_file():raise ValueError('Missing regular flash backup')
    raw=path.read_bytes()
    if len(raw)!=SIZES[name] or f'{zlib.crc32(raw):08x}'!=expected_crc:raise ValueError('Host backup does not match UART-observed CRC/size')
    receipt=json.loads(path.with_name(name+'.json').read_text())
    sha=hashlib.sha256(raw).hexdigest()
    if receipt['bytes']!=len(raw) or receipt['sha256']!=sha or receipt['crc32']!=expected_crc:raise ValueError('Backup receiver receipt mismatch')
    return sha


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--session',type=Path,required=True)
    p.add_argument('--server-ip',required=True);p.add_argument('--target-ip',required=True)
    p.add_argument('--ethernet',choices=['al_eth1','al_eth3'],required=True)
    a=p.parse_args();server,target=local_pair(a.server_ip,a.target_ip)
    connection=json.loads((a.session/'connection.json').read_text())
    plan=json.loads((a.session/'bound-disk-plan.json').read_text())
    directory=a.session/'original-flash'
    c=Console(connection['capture']);boot_text=c.current()
    if not boot_text.endswith(b'ALPINE_DB> '):raise ValueError('Fresh stopped U-Boot required')
    boot_hash=hashlib.sha256(boot_text).hexdigest();results={}
    def command(text,timeout=120):
        output=c.command(text,timeout)
        if re.search(r'(?:ERROR|Error|FAILED|failure|data abort|Unknown command|Retry count exceeded)',output):raise ValueError('Bootloader read/transfer failed; no further operation authorized')
        results[text]=output
        save_private(a.session/'flash-backup-observations.json',{'boot_initial_sha256':boot_hash,'commands':results,'flash_writes':False})
        return output
    command('printenv bootcmd bootargs loadaddr fdtaddr')
    command('nand info');bad=command('nand bad')
    if re.search(r'^\s*[0-9a-fA-F]{8}\s*$',bad,re.M):raise ValueError('Bad blocks require manual layout review')
    command('sf probe')
    profile=observed_profile(c.current().decode(errors='replace'),connection['model'])
    if '32M(boot1_kernel),216M(boot1_rootfs2),32M(boot2_kernel)' not in results['printenv bootcmd bootargs loadaddr fdtaddr']:
        raise ValueError('Unrecognized NAND slot map')
    command('thermal_init');temperature=command('thermal_get')
    readings=re.findall(r'temprature: (\d+) degrees',temperature)
    if len(readings)!=1 or not 0<int(readings[0])<70:raise ValueError('Temperature unavailable or too high')
    for text in (f'setenv ethact {a.ethernet}','setenv ethrotate no','setenv netretry no','setenv tftpdstp 69',
                 f'setenv ipaddr {target}',f'setenv serverip {server}'):
        command(text)
    if 'is alive' not in command('ping '+server):raise ValueError('Backup receiver host unreachable')
    proof={'schema':1,'unit_fingerprint':plan['unit_fingerprint'],'install_id':plan['install_id'],
           'profile':profile,'boot_initial_sha256':boot_hash,'flash_writes':False,'backups':{}}
    def read(kind,address,offset,size):
        text=f'nand read {address:x} {offset:x} {size:x}' if kind=='nand' else f'sf read {address:x} {offset:x} {size:x}'
        output=command(text)
        if kind=='nand' and f'{size} bytes read: OK' not in output:raise ValueError('Incomplete NAND read')
        return crc_result(command(f'crc32 {address:x} {size:x}'))
    for name,(kind,offset,size) in SLOTS.items():
        first=read(kind,READ,offset,size)
        second=read(kind,REREAD,offset,size)
        if first!=second:raise ValueError('Independent flash reads disagree')
        path=directory/name
        if not path.exists():
            output=command(f'tftpput {READ:x} {size:x} {server}:{name}',300)
            if f'Bytes transferred = {size} ' not in output:raise ValueError('Incomplete flash backup upload')
        deadline=time.monotonic()+10
        while not path.with_name(name+'.json').exists():
            if time.monotonic()>deadline:raise ValueError('Backup receiver receipt not available')
            time.sleep(.1)
        sha=verified_local_backup(path,first)
        receipt=json.loads(path.with_name(name+'.json').read_text());receipt['uart_crc_verified']=True;receipt['independent_reread_crc32']=second
        save_private(path.with_name(name+'.json'),receipt)
        proof['backups'][name]={'bytes':size,'sha256':sha,'crc32':first,'independent_reread_match':True}
        save_private(a.session/'original-flash-proof.json',proof)
        print('VERIFIED '+name+'; independent U-Boot reads and saved file match',flush=True)
    proof['completed_at']=time.time();proof['complete']=True
    save_private(a.session/'original-flash-proof.json',proof)
    print('Original flash backups verified. Still stopped at U-Boot; no flash write or boot performed.')


if __name__=='__main__':main()
