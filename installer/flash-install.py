#!/usr/bin/env python3
"""First-slot installation after accepted normal boot; never writes SPI/boot2.

Every fault stops the procedure. No boot/reset is issued by this tool, including
after success. This is not an interrupted-flash recovery or upgrade mechanism.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import zlib
from core import Console,observed_profile,save_private,verified_image

SLOT=0x2000000
PAGE=2048
LOAD=0x08000000
READ=0x18000000
SPI=0x1c000000
BOOT2=0x0f800000
BOOTCMD='bootcmd=nand read $loadaddr 0 0x2000000;run sata_cmd;bootm $loadaddr - $fdtaddr;'


def validate_acceptance(plan,proof,backup,manifest,image,now=None):
    if manifest.get('ram_only') is True or manifest.get('flash_allowed') is False:raise ValueError('RAM-only diagnostics cannot authorize flash installation')
    now=time.time() if now is None else now
    for record in (proof,backup):
        if record.get('install_id')!=plan.get('install_id') or record.get('unit_fingerprint')!=plan.get('unit_fingerprint'):
            raise ValueError('OS/backup proof belongs to another installation')
    if not backup.get('complete') or not proof.get('normal_boot_accepted') or not 0<=now-proof.get('verified_at',0)<3600:
        raise ValueError('Fresh normal-boot acceptance and complete original backups required')
    if proof.get('image_sha256')!=hashlib.sha256(image).hexdigest() or proof.get('kernel')!=manifest['kernel']:
        raise ValueError('Accepted OS did not boot this exact image')
    if not proof.get('debug_shell_inactive') or any(x in proof.get('cmdline','') for x in ('debug_shell','systemd.mask=')):
        raise ValueError('Maintenance/recovery boot cannot authorize permanent installation')
    if proof.get('raid_degraded')!=0 or proof.get('raid_sync_action')!='idle' or proof.get('failed_units'):
        raise ValueError('Healthy synchronized OS mirror and clear service faults required')
    services={'eyeq-cooling','eyeq-drive-green','eyeq-buttons','eyeq-disk-leds','ssh','systemd-networkd','mdmonitor'}
    network=proof.get('network_restarts',{})
    if not network.get('passed') or not services<=proof.get('services',{}).keys() or any(proof['services'][s]!='active' for s in services):
        raise ValueError('Network and service acceptance required')
    for port in ('enp0s1','enp0s3'):
        rows=[r for r in network.get('results',[]) if r.get('interface')==port]
        if len(rows)<2 or len({r.get('cycle') for r in rows})!=len(rows) or not all(r.get('upload_download_sha256_match') for r in rows):
            raise ValueError('Two verified bidirectional restart cycles on each RJ45 required')
    if proof.get('root_password_status') not in ('L','P'):raise ValueError('Empty-password root configuration is not accepted')
    if not proof.get('temperatures') or any(not 0<t<70000 for t in proof['temperatures']):raise ValueError('Thermal acceptance missing')
    hardware=proof.get('hardware',{})
    if hardware.get('global_fan_mode')!='7' or len(hardware.get('fans',[]))!=3 or any(f.get('counter',0)<=0 for f in hardware['fans']):
        raise ValueError('Acknowledged cooling and three reporting fans required')
    if set(backup.get('backups',{}))!={'boot1-original.bin','boot2-original.bin','spi-original.bin'}:
        raise ValueError('Both original kernel slots and full SPI backup required')
    if not all(record.get('independent_reread_match') for record in backup['backups'].values()):
        raise ValueError('Independent original-flash reread proof required')


def crc_value(output):
    values=re.findall(r'CRC32 for [0-9a-f]+ \.\.\. [0-9a-f]+ ==> ([0-9a-f]{8})',output)
    if len(values)!=1:raise ValueError('Single fresh CRC observation required')
    return values[0]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['plan','preflight','program'])
    p.add_argument('--session',type=Path,required=True);p.add_argument('--release',type=Path,required=True)
    p.add_argument('--confirm-install-id')
    a=p.parse_args();session=a.session
    plan=json.loads((session/'bound-disk-plan.json').read_text())
    proof=json.loads((session/'normal-os-proof.json').read_text())
    backup=json.loads((session/'original-flash-proof.json').read_text())
    manifest,image=verified_image(a.release)
    validate_acceptance(plan,proof,backup,manifest,image)
    operation=json.loads((session/'disk-operation.json').read_text())
    if proof.get('root_uuid')!=operation.get('result',{}).get('root_fs_uuid') or proof.get('root_md_uuid')!=operation.get('result',{}).get('root_md_uuid'):
        raise ValueError('Accepted root/array does not match the installed disk operation')
    # Recheck saved backups themselves, not only booleans in a receipt.
    for name,record in backup['backups'].items():
        raw=(session/'original-flash'/name).read_bytes()
        if len(raw)!=record['bytes'] or hashlib.sha256(raw).hexdigest()!=record['sha256'] or f'{zlib.crc32(raw):08x}'!=record['crc32']:
            raise ValueError('Original flash backup file changed')
    padded=(len(image)+PAGE-1)//PAGE*PAGE
    expected_slot=image+bytes([255])*(SLOT-len(image))
    slot_crc=f'{zlib.crc32(expected_slot):08x}'
    summary={'install_id':plan['install_id'],'unit_fingerprint':plan['unit_fingerprint'],
        'image_sha256':hashlib.sha256(image).hexdigest(),'image_bytes':len(image),'write_bytes':padded,
        'nand_offset':0,'erase_bytes':SLOT,'expected_full_slot_crc32':slot_crc,
        'spi_writes':False,'environment_saves':False,'boot2_writes':False}
    if a.action=='plan':print(json.dumps({**summary,'flash_writes':False},indent=2));return
    c=Console(json.loads((session/'connection.json').read_text())['capture'])
    epoch=c.boot_offset();observations={}
    def command(text,timeout=180):
        if c.boot_offset()!=epoch:raise ValueError('Boot epoch changed; no subsequent operation authorized')
        output=c.command(text,timeout);observations[text]=output
        save_private(session/'flash-install-observations.json',{'boot_offset':epoch,'commands':observations})
        if re.search(r'ERROR|Error|FAILED|data abort|Unknown command|uncorrectable',output):raise ValueError('Bootloader operation failed; stop and inspect')
        return output
    def crc(address,size,expected):
        if crc_value(command(f'crc32 {address:x} {size:x}'))!=expected:raise ValueError('CRC mismatch; no subsequent operation authorized')
    def read_slot(offset):
        output=command(f'nand read {READ:x} {offset:x} {SLOT:x}')
        if f'{SLOT} bytes read: OK' not in output:raise ValueError('Incomplete NAND read')
    env=command('printenv bootcmd bootargs loadaddr fdtaddr')
    if BOOTCMD not in env:raise ValueError('Saved boot command differs from accepted stock path')
    command('nand info');bad=command('nand bad');command('sf probe')
    observed_profile(c.current().decode(errors='replace'),'TS-431XeU')
    if re.search(r'^\s*[0-9a-fA-F]{8}\s*$',bad,re.M):raise ValueError('Bad blocks require manual layout review')
    command('thermal_init');temperatures=re.findall(r'temprature: (\d+) degrees',command('thermal_get'))
    if not temperatures or not 0<int(temperatures[-1])<70:raise ValueError('Current bootloader temperature not accepted')
    crc(LOAD,len(image),manifest['artifacts']['uImage']['crc32'])
    if 'Verifying Checksum ... OK' not in command(f'iminfo {LOAD:x}'):raise ValueError('Loaded normal image rejected')
    read_slot(0);crc(READ,SLOT,backup['backups']['boot1-original.bin']['crc32'])
    if a.action=='preflight':
        read_slot(BOOT2);crc(READ,SLOT,backup['backups']['boot2-original.bin']['crc32'])
        command(f'sf read {SPI:x} 0 200000');crc(SPI,0x200000,backup['backups']['spi-original.bin']['crc32'])
        record={**summary,'boot_offset':epoch,'verified_at':time.time(),'flash_writes':False,'original_slots_and_spi_match':True}
        save_private(session/'flash-install-preflight.json',record);print(json.dumps(record,indent=2));return
    before=json.loads((session/'flash-install-preflight.json').read_text())
    if a.confirm_install_id!=plan['install_id'] or before['boot_offset']!=epoch or before['image_sha256']!=summary['image_sha256'] or not 0<=time.time()-before['verified_at']<900:
        raise ValueError('Exact install confirmation and fresh same-boot preflight required')
    command(f'mw.b {LOAD+len(image):x} ff {SLOT-len(image):x}');crc(LOAD,SLOT,slot_crc)
    record={**summary,'boot_offset':epoch,'write_started':True,'readback_verified':False,'started_at':time.time()}
    save_private(session/'flash-operation.json',record)
    if 'OK' not in command(f'nand erase 0 {SLOT:x}'):raise ValueError('Kernel-slot erase not acknowledged')
    if f'{padded} bytes written: OK' not in command(f'nand write {LOAD:x} 0 {padded:x}'):raise ValueError('Kernel-slot write incomplete')
    command(f'mw.b {READ:x} 0 {SLOT:x}');read_slot(0)
    if f'Total of {SLOT} byte(s) were the same' not in command(f'cmp.b {LOAD:x} {READ:x} {SLOT:x}'):
        raise ValueError('Full kernel-slot byte comparison failed')
    crc(READ,SLOT,slot_crc);crc(READ,len(image),manifest['artifacts']['uImage']['crc32'])
    if 'Verifying Checksum ... OK' not in command(f'iminfo {READ:x}'):raise ValueError('Readback image checksum rejected')
    read_slot(BOOT2);crc(READ,SLOT,backup['backups']['boot2-original.bin']['crc32'])
    command(f'sf read {SPI:x} 0 200000');crc(SPI,0x200000,backup['backups']['spi-original.bin']['crc32'])
    if BOOTCMD not in command('printenv bootcmd'):raise ValueError('Boot command changed unexpectedly')
    record.update(readback_verified=True,full_slot_byte_comparison=True,boot2_unchanged=True,full_spi_unchanged=True,bootcmd_unchanged=True,completed_at=time.time())
    save_private(session/'flash-operation.json',record)
    print('First kernel slot programmed and fully compared. Boot2, full SPI and saved boot command unchanged. Still stopped at U-Boot.')


if __name__=='__main__':main()
