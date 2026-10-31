"""Checked RAM-only recovery overlay; never changes kernel code or flash."""
import hashlib
from pathlib import Path
import struct
import zlib
from core import verified_image

SUFFIX=b' systemd.debug_shell=ttyS0 systemd.mask=serial-getty@ttyS0.service'


def dt_properties(data):
    if len(data)<40:raise ValueError('Truncated device tree')
    magic,total,off_struct,off_strings,off_reserve,version,last,bootcpu,size_strings,size_struct=struct.unpack('>10I',data[:40])
    if magic!=0xd00dfeed or total!=len(data) or version!=17 or last>17 or off_struct+size_struct>total or off_strings+size_strings>total:
        raise ValueError('Invalid device tree boundaries')
    strings=data[off_strings:off_strings+size_strings];position=off_struct;end=off_struct+size_struct;stack=[];properties={}
    while position<end:
        token=struct.unpack_from('>I',data,position)[0];position+=4
        if token==1:
            stop=data.index(b'\0',position,end);name=data[position:stop].decode('ascii');stack.append(name);position=(stop+4)&~3
            node=('/'+'/'.join(stack[1:]),None)
            if node in properties:raise ValueError('Duplicate device tree node')
            properties[node]=b''
        elif token==2:
            if not stack:raise ValueError('Unbalanced device tree')
            stack.pop()
        elif token==3:
            length,name_offset=struct.unpack_from('>II',data,position);position+=8
            if not stack or position+length>end or name_offset>=len(strings):raise ValueError('Invalid device tree property')
            stop=strings.index(b'\0',name_offset);name=strings[name_offset:stop].decode('ascii')
            key=('/'+'/'.join(stack[1:]),name)
            if key in properties:raise ValueError('Duplicate device tree property')
            properties[key]=data[position:position+length];position=(position+length+3)&~3
        elif token==4:continue
        elif token==9:
            if stack:raise ValueError('Unbalanced device tree end')
            break
        else:raise ValueError('Invalid device tree token')
    else:raise ValueError('Missing device tree end')
    reserve_end=off_reserve
    while True:
        if reserve_end+16>len(data):raise ValueError('Truncated memory reservations')
        entry=data[reserve_end:reserve_end+16];reserve_end+=16
        if entry==b'\0'*16:break
    return properties,data[off_reserve:reserve_end],bootcpu


def overlay_plan(base_directory,recovery_directory):
    _,base=verified_image(base_directory);manifest,recovery=verified_image(recovery_directory,allow_maintenance=True)
    if not manifest.get('one_boot_maintenance_only'):raise ValueError('Explicit maintenance-only manifest required')
    kernel=(Path(base_directory)/'zImage').read_bytes();offset=64+len(kernel)
    if offset%4 or recovery[64:offset]!=kernel or base[64:offset]!=kernel:
        raise ValueError('Recovery kernel must be byte-identical to the base kernel')
    old,reservations,cpu=dt_properties(base[offset:]);new,new_reservations,new_cpu=dt_properties(recovery[offset:])
    key=('/chosen','bootargs')
    expected=old.get(key,b'').rstrip(b'\0')+SUFFIX+b'\0'
    if not old.get(key) or new.get(key)!=expected:raise ValueError('Only the explicit serial maintenance boot arguments are allowed')
    if {k:v for k,v in old.items() if k!=key}!={k:v for k,v in new.items() if k!=key} or reservations!=new_reservations or cpu!=new_cpu:
        raise ValueError('Recovery must not change hardware properties or reserved memory')
    if len(recovery)-offset>16384 or len(recovery)%4:raise ValueError('Recovery device tree size/alignment unsupported')
    words=[]
    for start,stop in ((0,64),(offset,len(recovery))):
        for index in range(start,stop,4):
            value=recovery[index:index+4]
            if base[index:index+4]!=value:words.append((0x08000000+index,int.from_bytes(value,'little')))
    return {'words':words,'base_bytes':len(base),'base_crc32':f'{zlib.crc32(base):08x}',
        'recovery_bytes':len(recovery),'recovery_crc32':f'{zlib.crc32(recovery):08x}',
        'recovery_sha256':hashlib.sha256(recovery).hexdigest(),'kernel_sha256':hashlib.sha256(kernel).hexdigest()}


def apply_overlay(console,plan,record):
    check=console.command(f'crc32 08000000 {plan["base_bytes"]:x}')
    if '==> '+plan['base_crc32'] not in check:raise ValueError('Base RAM image changed before recovery overlay')
    for offset in range(0,len(plan['words']),3):
        group=plan['words'][offset:offset+3]
        command=';'.join(f'mw.l {address:x} {word:08x} 1' for address,word in group)
        response=console.command(command)
        if any(s in response for s in ('Unknown command','Error','ERROR','Usage:')):raise ValueError('RAM recovery overlay stopped; do not boot')
        record(command,response)
    check=console.command(f'crc32 08000000 {plan["recovery_bytes"]:x}')
    record('recovery-crc32',check)
    if '==> '+plan['recovery_crc32'] not in check:raise ValueError('Complete recovery RAM image CRC mismatch; do not boot')
    check=console.command('iminfo 08000000');record('recovery-iminfo',check)
    if 'Verifying Checksum ... OK' not in check:raise ValueError('Recovery image wrapper/data checksum rejected')
