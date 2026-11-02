#!/usr/bin/env python3
"""Development host controller: preflight, checked RAM loading and disk-root boot.

Disk execution and first-slot programming are separate guarded tools, not a unified wizard.
"""
import argparse
import base64
import secrets
import hashlib
import json
import os
from pathlib import Path
import re
import time
from core import Console,advance,save_private,verified_image,observed_profile,local_pair,parse_inventory,disk_plan


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    attach=sub.add_parser('attach');attach.add_argument('--session',type=Path,required=True);attach.add_argument('--capture',type=Path,required=True);attach.add_argument('--model',choices=['TS-431XeU'],required=True)
    inspect=sub.add_parser('inspect');inspect.add_argument('--session',type=Path,required=True)
    status=sub.add_parser('status');status.add_argument('--session',type=Path,required=True)
    load=sub.add_parser('load-ram');load.add_argument('--session',type=Path,required=True);load.add_argument('--release',type=Path,required=True);load.add_argument('--server-ip',required=True);load.add_argument('--target-ip',required=True);load.add_argument('--ethernet',choices=['al_eth1','al_eth3'],required=True)
    boot=sub.add_parser('boot-ram');boot.add_argument('--session',type=Path,required=True);boot.add_argument('--release',type=Path,required=True)
    diskboot=sub.add_parser('boot-installed');diskboot.add_argument('--session',type=Path,required=True);diskboot.add_argument('--release',type=Path,required=True);diskboot.add_argument('--server-ip',required=True);diskboot.add_argument('--target-ip',required=True);diskboot.add_argument('--ethernet',choices=['al_eth1','al_eth3'],required=True);diskboot.add_argument('--tftp-port',type=int,default=69)
    diskboot.add_argument('--maintenance-console',action='store_true',help='One RAM-only boot with a local serial maintenance shell; never save these boot arguments')
    diskboot.add_argument('--recovery-release',type=Path,help='Explicit maintenance-only release with an unchanged kernel and checked device-tree boot arguments')
    diskboot.add_argument('--reuse-verified-ram',action='store_true',help='Skip networking only when the complete existing RAM image matches the selected base CRC')
    inventory=sub.add_parser('inventory');inventory.add_argument('--session',type=Path,required=True)
    plan=sub.add_parser('plan-disks');plan.add_argument('--session',type=Path,required=True);plan.add_argument('--disk',action='append',required=True)
    credentials=sub.add_parser('password-mode');credentials.add_argument('--session',type=Path,required=True);credentials.add_argument('--mode',choices=['installer','first-login','deferred-key-only'],required=True)
    args=parser.parse_args();os.umask(0o077);args.session.mkdir(mode=0o700,parents=True,exist_ok=True);journal=args.session/'session.json'
    if args.action=='attach':
        if journal.exists():raise ValueError('Session already exists; use status/inspect rather than replacing it')
        capture=args.capture.resolve();console=Console(capture)
        save_private(args.session/'connection.json',{'capture':str(capture),'model':args.model,'port':console.ready['port']})
        advance(journal,'serial_ready',{'capture':str(capture),'model_attested':args.model})
        print('Serial attached. Power on the selected TS-431XeU; its countdown will be stopped by capture.');return
    state=json.loads(journal.read_text());connection=json.loads((args.session/'connection.json').read_text())
    if args.action=='password-mode':
        save_private(args.session/'credentials-plan.json',{'root_password_method':args.mode,'ssh_password_login_enabled':False,'plaintext_password_stored':False})
        print('Root password method saved: '+args.mode+'. No password has been collected or changed.');return
    if args.action=='status':
        from session_status import session_status
        print(json.dumps(session_status(args.session),indent=2));return
    console=Console(connection['capture'])
    if args.action=='boot-installed':
        operation=json.loads((args.session/'disk-operation.json').read_text())
        backup=json.loads((args.session/'original-flash-proof.json').read_text())
        plan=json.loads((args.session/'bound-disk-plan.json').read_text())
        if operation.get('status')!='installed_pending_boot_validation' or not backup.get('complete'):
            raise ValueError('Installed OS and complete verified original-flash backup required')
        if any(record.get('unit_fingerprint')!=plan['unit_fingerprint'] or record.get('install_id')!=plan['install_id'] for record in (operation,backup)):
            raise ValueError('Installation/backup identity mismatch')
        if not 1<=args.tftp_port<=65535:raise ValueError('Invalid temporary TFTP destination port')
        manifest,image=verified_image(args.release);server,target=local_pair(args.server_ip,args.target_ip)
        recovery_plan=None
        if args.maintenance_console:
            if args.recovery_release is None:raise ValueError('An explicit checked recovery release is required; U-Boot environment bootargs are ignored by this appended-DTB image')
            from recovery import overlay_plan,apply_overlay
            recovery_plan=overlay_plan(args.release,args.recovery_release)
        result={'image_sha256':hashlib.sha256(image).hexdigest(),'install_id':plan['install_id'],
            'unit_fingerprint':plan['unit_fingerprint'],'flash_writes':False,'maintenance_console':args.maintenance_console,'commands':{}}
        previous=args.session/'disk-boot-attempt.json'
        if previous.exists():save_private(args.session/('disk-boot-history-'+str(time.time_ns())+'.json'),json.loads(previous.read_text()))
        for command in ('printenv bootcmd bootargs loadaddr fdtaddr','nand info','sf probe','thermal_init'):
            output=console.command(command,30);result['commands'][command]=output
            if re.search(r'(?:ERROR|Error|FAILED|Unknown command)',output):raise ValueError('Fresh bootloader preflight failed')
        observed_profile(console.current().decode(errors='replace'),connection['model'])
        transfer_commands=[f'setenv ethact {args.ethernet}','setenv ethrotate no','setenv netretry no',
            f'setenv ipaddr {target}',f'setenv serverip {server}',f'setenv tftpdstp {args.tftp_port}',
            f'ping {server}',f'tftpboot 0x08000000 {server}:uImage']
        result['reuse_verified_ram']=args.reuse_verified_ram
        commands=([] if args.reuse_verified_ram else transfer_commands)+[f'crc32 08000000 {len(image):x}',
            'iminfo 08000000','thermal_get','run sata_cmd']
        for command in commands:
            output=console.command(command,180 if command.startswith('tftpboot') else 30)
            result['commands'][command]=output;save_private(args.session/'disk-boot-attempt.json',result)
            if re.search(r'(?:ERROR|Error|FDT_ERR|Retry count exceeded|Unknown command)',output):raise ValueError('RAM disk-boot preflight failed; no boot authorized')
            if command.startswith('ping ') and 'is alive' not in output:raise ValueError('Transfer host unreachable')
            if command.startswith('tftpboot ') and f'Bytes transferred = {len(image)} ' not in output:raise ValueError('Wrong or incomplete RAM image transfer')
            if command.startswith('crc32 ') and f'==> {manifest["artifacts"]["uImage"]["crc32"]}' not in output:raise ValueError('RAM image CRC mismatch')
            if command.startswith('iminfo ') and 'Verifying Checksum ... OK' not in output:raise ValueError('Invalid boot image')
            if command=='thermal_get':
                temperatures=re.findall(r'temprature: (\d+) degrees',output)
                if not temperatures or not 0<int(temperatures[-1])<70:raise ValueError('Unsafe or unavailable boot temperature')
        if args.maintenance_console:
            result['recovery']={k:v for k,v in recovery_plan.items() if k!='words'}
            def record(command,output):
                result['commands'][command]=output;save_private(args.session/'disk-boot-attempt.json',result)
            apply_overlay(console,recovery_plan,record)
            output=console.command('thermal_get');temperatures=re.findall(r'temprature: (\d+) degrees',output)
            if not temperatures or not 0<int(temperatures[-1])<70:raise ValueError('Boot temperature no longer accepted')
        start=console.log.stat().st_size;result['boot_serial_offset']=start;result['boot_requested_at']=time.time()
        save_private(args.session/'disk-boot-attempt.json',result);console.send('bootm 08000000 - ${fdtaddr}\r')
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            output=console.log.read_bytes()[start:]
            if b'FREEQNAP_RAM_READY:' in output or b'Kernel panic' in output:
                result['disk_boot_observed']=False;result['serial_output']=output.decode(errors='replace');save_private(args.session/'disk-boot-attempt.json',result)
                raise ValueError('Disk-root boot stopped or fell back to RAM; inspect serial output')
            if not args.maintenance_console and b'PID1 starting Debian.' in output and b' login: ' in output:
                result['disk_boot_observed']=True;result['serial_output']=output.decode(errors='replace');result['observed_at']=time.time()
                save_private(args.session/'disk-boot-attempt.json',result)
                print('Installed Debian boot observed using the checked RAM kernel. SSH/hardware acceptance still required; flash remains unchanged.');return
            if args.maintenance_console and b'PID1 starting Debian.' in output and re.search(rb'root@freeqnap-[^\r\n]+# ',output):
                result['maintenance_console_observed']=True;result['disk_boot_observed']=False;result['serial_output']=output.decode(errors='replace')
                save_private(args.session/'disk-boot-attempt.json',result)
                print('One-boot serial maintenance shell observed. Normal boot acceptance remains pending; flash and saved boot settings unchanged.');return
            time.sleep(.2)
        raise TimeoutError('No complete Debian disk-boot observation; inspect serial output')
    if args.action=='plan-disks':
        if state['phase']!='inventoried':raise ValueError('Fresh RAM inventory required')
        result=disk_plan(json.loads((args.session/'target-inventory.json').read_text()),args.disk)
        save_private(args.session/'disk-plan.json',result);print(json.dumps(result,indent=2));return
    if args.action=='boot-ram':
        if state['phase']!='ram_loaded':raise ValueError('Verified RAM load required')
        manifest,image=verified_image(args.release);proof=state['events'][-1]['evidence']
        if hashlib.sha256(image).hexdigest()!=proof['image_sha256']:raise ValueError('Image changed after loading')
        check=console.command(f'crc32 0x08000000 {len(image):x}')
        if f'==> {manifest["artifacts"]["uImage"]["crc32"]}' not in check:raise ValueError('Loaded RAM no longer matches image')
        temperature=console.command('thermal_get');readings=re.findall(r'temprature: (\d+) degrees',temperature)
        if not readings or not 0<int(readings[-1])<70:raise ValueError('Temperature not accepted for boot')
        console.command('run sata_cmd')
        start=console.log.stat().st_size;console.send('bootm 0x08000000 - ${fdtaddr}\r')
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            output=console.log.read_bytes()[start:]
            if b'FREEQNAP_RAM_READY:' in output:
                advance(journal,'ram_running',{'kernel':manifest['kernel'],'image_sha256':proof['image_sha256']})
                print('Generic image is running in RAM. Disk and flash installation have not run.');return
            time.sleep(.2)
        raise TimeoutError('No generic RAM-ready marker; inspect serial capture')
    if args.action=='inventory':
        if state['phase'] not in ('ram_running','inventoried'):raise ValueError('RAM-ready state required')
        script=(Path(__file__).parent/'target/inventory.sh').read_bytes()
        console.stage_bytes('/tmp/freeqnap-inventory.sh',script)
        output,code=console.shell('sh /tmp/freeqnap-inventory.sh',90)
        save_private(args.session/'inventory-observation.json',{'output':output,'exit_code':code})
        if code:raise ValueError('Read-only inventory failed; no disk plan authorized')
        result=parse_inventory(output)
        prior=args.session/'target-inventory.json'
        if state['phase']=='inventoried':
            previous=json.loads(prior.read_text())
            if result['unit_fingerprint']!=previous['unit_fingerprint']:raise ValueError('Target identity changed; reconcile before continuing')
            save_private(args.session/('inventory-history-'+str(time.time_ns())+'.json'),previous)
        save_private(prior,result)
        if state['phase']=='ram_running':advance(journal,'inventoried',{'unit_fingerprint':result['unit_fingerprint'],'disk_count':len(result['disks'])})
        print(json.dumps({'hardware_gates_passed':True,'disks':result['disks'],'writes_performed':False},indent=2));return
    if args.action=='inspect':
        if state['phase']!='serial_ready':raise ValueError('Inspection is only available before RAM loading; preserve the existing journal')
        result={}
        for command in ('version','bdinfo','printenv','nand info','nand bad','help tftpput','help hash','thermal_init','thermal_get'):
            output=console.command(command,90 if command=='nand bad' else 30);result[command]=output
            save_private(args.session/'bootloader-inspection.json',result)
        text=console.current().decode(errors='replace');profile=observed_profile(text,connection['model'])
        save_private(args.session/'observed-profile.json',profile)
        advance(journal,'inspected',{'profile':profile,'transcript_sha256':hashlib.sha256(text.encode()).hexdigest()})
        print(json.dumps({'phase':'inspected','profile':profile,'disk_writes':False,'flash_writes':False},indent=2));return
    if args.action=='load-ram':
        if state['phase']!='inspected':raise ValueError('Complete hardware inspection before RAM loading')
        manifest,image=verified_image(args.release);server,target=local_pair(args.server_ip,args.target_ip)
        profile=observed_profile(console.current().decode(errors='replace'),connection['model'])
        size=len(image);address=0x08000000
        result={}
        # Temporary RAM environment only; no saveenv and no flash operation.
        commands=[f'setenv ethact {args.ethernet}','setenv ethrotate no','setenv netretry no',f'setenv ipaddr {target}',f'setenv serverip {server}',f'ping {server}',f'tftpboot 0x{address:08x} {server}:uImage',f'crc32 0x{address:08x} {size:x}',f'iminfo 0x{address:08x}']
        for command in commands:
            output=console.command(command,120 if command.startswith('tftpboot') else 30);result[command]=output
            save_private(args.session/'ram-transfer.json',result)
            if re.search(r'(?:ERROR|Error|FDT_ERR|Retry count exceeded|Unknown command)',output):raise ValueError('Bootloader command failed; RAM boot not authorized')
            if command.startswith('ping ') and 'is alive' not in output:raise ValueError('Host not reachable; check either LAN or optional direct cable')
            if command.startswith('tftpboot ') and f'Bytes transferred = {size} ' not in output:raise ValueError('Incomplete transfer; RAM boot not authorized')
            if command.startswith('crc32 ') and f'==> {manifest["artifacts"]["uImage"]["crc32"]}' not in output:raise ValueError('RAM CRC mismatch; RAM boot not authorized')
            if command.startswith('iminfo ') and 'Verifying Checksum ... OK' not in output:raise ValueError('Bootloader image checksum rejected')
        advance(journal,'ram_loaded',{'image_sha256':hashlib.sha256(image).hexdigest(),'bytes':size,'load_address':hex(address),'transfer_checks_passed':True})
        print('Image is loaded and checked in RAM. No boot, disk or flash write was performed.');return


if __name__=='__main__':
    main()
