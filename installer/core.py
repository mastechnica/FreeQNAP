"""Host-side invariants for the experimental FreeQNAP installer."""
import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import struct
import time
import zlib

PROMPT = b'ALPINE_DB> '
STATES = ('new','serial_ready','inspected','ram_loaded','ram_running','inventoried')


def save_private(path, value):
    path=Path(path);path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.next')
    fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
        directory=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)
    except BaseException:
        temporary.unlink(missing_ok=True);raise


def advance(path, phase, evidence):
    path=Path(path)
    state=json.loads(path.read_text()) if path.exists() else {'schema':1,'phase':'new','events':[]}
    if phase not in STATES or STATES.index(phase)!=STATES.index(state['phase'])+1:
        raise ValueError('Invalid transition; reconcile current session state')
    previous=state['events'][-1]['hash'] if state['events'] else '0'*64
    event={'phase':phase,'at':time.time(),'previous':previous,'evidence':evidence}
    event['hash']=hashlib.sha256(json.dumps(event,sort_keys=True).encode()).hexdigest()
    state['phase']=phase;state['events'].append(event);save_private(path,state)
    return state


def verified_image(directory,*,allow_maintenance=False,allow_ram_only=False):
    directory=Path(directory);manifest=json.loads((directory/'manifest.json').read_text())
    for field in ('ram_only','flash_allowed'):
        if field in manifest and not isinstance(manifest[field],bool):raise ValueError('Invalid RAM/flash image restriction')
    restricted=manifest.get('ram_only') is True or manifest.get('flash_allowed') is False
    if restricted and not allow_ram_only:raise ValueError('RAM-only diagnostic cannot authorize normal boot or flash installation')
    if restricted and (manifest.get('ram_only') is not True or manifest.get('flash_allowed') is not False):raise ValueError('RAM-only image must explicitly prohibit flash installation')
    if manifest.get('one_boot_maintenance_only') and not allow_maintenance:raise ValueError('Maintenance images cannot be used for normal boot or flash installation')
    if manifest.get('schema')!=1 or manifest.get('model')!='TS-431XeU' or manifest.get('architecture')!='armhf':
        raise ValueError('Unsupported image manifest')
    record=manifest['artifacts']['uImage'];image=directory/'uImage'
    if image.is_symlink():raise ValueError('Boot artifact must not be a symlink')
    data=image.read_bytes()
    if len(data)!=record['bytes'] or not 64<len(data)<0x1000000 or hashlib.sha256(data).hexdigest()!=record['sha256']:
        raise ValueError('Image size/hash mismatch')
    header=bytearray(data[:64]);values=struct.unpack('>7I4B32s',header);header[4:8]=b'\0'*4
    if (values[0]!=0x27051956 or zlib.crc32(header)!=values[1] or values[3]!=len(data)-64
            or zlib.crc32(data[64:])!=values[6] or values[4:6]!=(0x8000,0x8000)
            or values[7:11]!=(5,2,2,0) or f'{zlib.crc32(data):08x}'!=record['crc32']):
        raise ValueError('Invalid ARM Linux legacy uImage wrapper')
    return manifest,data


def observed_profile(text, model):
    if model!='TS-431XeU':raise ValueError('Only the explicitly selected TS-431XeU is supported')
    required=('U-Boot 2015.07-alpine_db-', 'Board config ID: alpine_db_qnap',
              'DRAM:  2 GiB', 'NAND:  512 MiB', 'total 2 MiB')
    missing=[x for x in required if x not in text]
    if missing:raise ValueError('Boot family/geometry mismatch: '+', '.join(missing))
    if not re.search(r'Page size\s+2048\s+b',text) or not re.search(r'Erase size\s+131072\s+b',text):
        raise ValueError('Unsupported NAND page/erase geometry')
    if not re.search(r'bootcmd=nand read \$loadaddr 0 0x2000000;run sata_cmd;bootm \$loadaddr - \$fdtaddr;',text):
        raise ValueError('Unrecognized saved boot path; manual inspection required')
    return {'model_attested':model,'boot_family_match':True,'ram_bytes':0x80000000,
            'nand_bytes':0x20000000,'nand_page_bytes':2048,'nand_erase_bytes':131072,
            'spi_bytes':0x200000,'kernel_slot_bytes':0x2000000,'mcu_identity_verified':False}


def local_pair(server, target):
    server=ipaddress.IPv4Address(server);target=ipaddress.IPv4Address(target)
    if server==target or any(not ip.is_private or ip.is_loopback or ip.is_multicast or ip.is_link_local for ip in (server,target)):
        raise ValueError('Choose distinct private IPv4 addresses on the connected network')
    return str(server),str(target)


class Console:
    def __init__(self, capture):
        self.capture=Path(capture);self.ready=json.loads((self.capture/'ready.json').read_text())
        self.log=self.capture/'console.bin'
        os.kill(self.ready['pid'],0)
    def current(self):
        data=self.log.read_bytes()
        starts=list(re.finditer(rb'U-Boot 2015\.07-[^\r\n]*\r?\n(?:\r?\n)*I2C:',data))
        index=starts[-1].start() if starts else data.find(b'U-Boot 2015.07-')
        return data[index:] if index>=0 else data
    def boot_offset(self):
        data=self.log.read_bytes()
        starts=list(re.finditer(rb'U-Boot 2015\.07-[^\r\n]*\r?\n(?:\r?\n)*I2C:',data))
        return starts[-1].start() if starts else -1
    def request(self, request):
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            client.settimeout(60);client.connect(self.ready['control_socket'])
            client.sendall(json.dumps(request).encode()+b'\n');reply=b''
            while not reply.endswith(b'\n'):
                chunk=client.recv(4096)
                if not chunk:raise OSError('Capture broker closed before acknowledgement')
                reply+=chunk
            result=json.loads(reply)
            if not result.get('ok'):raise OSError(result.get('error','Serial send failed'))
            return result
    def send(self,text):return self.request({'send':text})
    def arm_autoboot(self):return self.request({'arm_autoboot':True})
    def command(self, text, timeout=30):
        if re.match(r'^\s*(?:scsi\b|ext4load\b)',text):
            raise ValueError('Vendor disk-loading path is unaccepted and faulted during discovery; use the verified network/RAM recovery path')
        if '\r' in text or '\n' in text or not self.current().endswith(PROMPT):
            raise ValueError('Expected current U-Boot prompt and one command')
        epoch=self.boot_offset();start=self.log.stat().st_size;self.send(text+'\r');deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            output=self.log.read_bytes()[start:]
            if self.boot_offset()!=epoch or re.search(rb'data abort|Resetting CPU|Kernel panic',output,re.I):
                raise RuntimeError('Unexpected bootloader fault/restart; no subsequent command authorized')
            if len(output)>len(text)+1 and output.endswith(PROMPT):return output.decode(errors='replace')
            time.sleep(.05)
        raise TimeoutError('No fresh U-Boot prompt; no subsequent action authorized')

    def shell(self, text, timeout=45, *, maintenance=False):
        """Internal transport for explicit RAM-stage operations, with fresh completion."""
        current=self.current()
        ready=(b'FREEQNAP_MAINTENANCE_READY' in current and b'systemd.debug_shell=ttyS0' in current) if maintenance else b'FREEQNAP_RAM_READY:' in current
        if '\r' in text or '\n' in text or not ready:
            raise ValueError('One command and a captured FreeQNAP RAM shell are required')
        marker='__FREEQNAP_DONE_'+secrets.token_hex(8)+'__'
        line="{ "+text+"; }; result=$?; printf '\\n"+marker+":%s\\n' \"$result\"\r"
        if len(line.encode())>768:raise ValueError('RAM shell line too long; use checksum-verified chunked staging')
        start=self.log.stat().st_size;self.send(line);deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            output=self.log.read_bytes()[start:].decode(errors='replace')
            match=re.search(r'(?:^|[\r\n])'+re.escape(marker)+r':([0-9]+)\r?\n',output)
            if match:return output,int(match[1])
            time.sleep(.1)
        raise TimeoutError('No fresh RAM operation completion; inspect transcript before retrying')

    def stage_bytes(self, destination, payload):
        """Stage only a private RAM file, using lines below BusyBox editing limits."""
        if not re.fullmatch(r'/tmp/freeqnap-[A-Za-z0-9_.-]+',destination):
            raise ValueError('Only a named FreeQNAP RAM temporary file can be staged')
        if not isinstance(payload,bytes) or not 0<len(payload)<=1024*1024:
            raise ValueError('Unsupported serial staging payload size')
        directory='/tmp/freeqnap-transfer-'+secrets.token_hex(8)
        _,code=self.shell('umask 077; mkdir -m 700 '+directory)
        if code:raise OSError('Private RAM staging directory could not be created')
        encoded=base64.b64encode(payload).decode()
        for offset in range(0,len(encoded),384):
            _,code=self.shell("printf '%s' '"+encoded[offset:offset+384]+"' >> "+directory+'/payload.b64')
            if code:raise OSError('Serial staging failed; no staged program authorized')
        digest=hashlib.sha256(payload).hexdigest()
        command="test ! -L "+destination+" && base64 -d "+directory+"/payload.b64 > "+directory+"/verified && printf '%s\\n' '"+digest+'  '+directory+"/verified' | sha256sum -c - && chmod 700 "+directory+'/verified && mv '+directory+'/verified '+destination+' && rm '+directory+'/payload.b64 && rmdir '+directory
        output,code=self.shell(command)
        if code or ': OK' not in output:raise OSError('RAM payload checksum not verified; no staged program authorized')
        return digest


def parse_inventory(text):
    fields={}
    for line in text.splitlines():
        if not line.startswith('__FREEQNAP_FIELD__|'):continue
        _,key,value=line.split('|',2)
        if key in fields or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,64}',key):raise ValueError('Duplicate or invalid inventory field')
        fields[key]=base64.b64decode(value,validate=True).decode(errors='strict').strip('\x00\n')
    required={'kernel','board','compatible','cpu','memory','mounts','mdstat','swaps','cooling_ack','factory_macs_verified','existing_root_failed','disks'}
    if not required<=fields.keys():raise ValueError('Incomplete read-only target inventory')
    if fields['cooling_ack']!='1' or fields['factory_macs_verified']!='1' or fields['existing_root_failed']!='0':raise ValueError('Target hardware/root gate failed')
    if 'qnap,ts-431xeu' not in fields['compatible'].split('\x00'):raise ValueError('Target DT compatibility mismatch')
    if not fields['kernel'].startswith('6.12.114-eyeq-ts431xeu-freeqnap'):raise ValueError('Unexpected target kernel')
    processors=re.findall(r'^processor\s*:',fields['cpu'],re.M)
    memory=re.search(r'^MemTotal:\s*(\d+) kB',fields['memory'],re.M)
    if len(processors)!=4 or not memory or not 1700000<int(memory[1])<2200000:raise ValueError('Expected four cores and approximately 2 GiB RAM')
    temperatures=[int(v) for k,v in fields.items() if k.startswith('thermal.')]
    if not temperatures or any(not 0<t<70000 for t in temperatures):raise ValueError('Thermal readings unavailable or outside installation limit')
    macs=sorted(set(v for k,v in fields.items() if k.startswith('mac.') and re.fullmatch(r'[0-9a-f]{2}(:[0-9a-f]{2}){5}',v) and int(v[:2],16)&3==0 and v!='00:00:00:00:00:00'))
    if len(macs)!=3:raise ValueError('Three verified factory interface MACs required')
    disks=json.loads(fields.pop('disks'))['blockdevices']
    for disk in disks:
        if disk.get('type')!='disk':continue
        prefix='disk.'+disk.get('name','')
        raw=fields.get(prefix+'.vpd80')
        if raw:
            data=bytes.fromhex(raw)
            if len(data)<5 or data[1]!=0x80 or int.from_bytes(data[2:4],'big')!=len(data)-4:
                raise ValueError('Invalid disk serial VPD framing')
            serial=data[4:].decode('ascii').strip()
            if not re.fullmatch(r'[A-Za-z0-9_. -]{1,64}',serial):raise ValueError('Invalid disk serial')
            if disk.get('serial') and disk['serial']!=serial:raise ValueError('Conflicting disk serial observations')
            disk['serial']=serial
        wwid=fields.get(prefix+'.wwid','')
        if wwid.startswith('naa.') and re.fullmatch(r'naa\.[0-9a-f]{16}',wwid):
            normalized='0x'+wwid[4:]
            if disk.get('wwn') and disk['wwn']!=normalized:raise ValueError('Conflicting disk WWN observations')
            disk['wwn']=normalized
    return {'fields':fields,'disks':disks,'unit_fingerprint':hashlib.sha256('\n'.join(macs).encode()).hexdigest(),'recorded_at':time.time()}


def disk_plan(inventory, serials):
    if len(serials)!=2 or len(set(serials))!=2:raise ValueError('Select two distinct disk serials for the initial supported OS mirror')
    if not 0<=time.time()-inventory['recorded_at']<900:raise ValueError('Target inventory is stale')
    if re.search(r'\bmd[0-9]+\s*:',inventory['fields']['mdstat']):raise ValueError('An active array requires reconciliation before disk installation')
    rows=[]
    for serial in serials:
        matches=[d for d in inventory['disks'] if d.get('type')=='disk' and d.get('serial')==serial]
        if len(matches)!=1:raise ValueError('Disk identity missing or ambiguous')
        disk=matches[0]
        physical=inventory['fields'].get('disk.'+disk.get('name',Path(disk.get('path','')).name)+'.sysfs','')
        if '/0000:00:09.0/' not in physical or disk.get('ro') is True:raise ValueError('Only writable internal SATA disks are supported')
        if not re.fullmatch(r'/dev/sd[a-z]',disk.get('path','')) or disk['size']<16*1024**3:raise ValueError('Unsupported disk path/capacity')
        pending=[disk]
        while pending:
            part=pending.pop();pending.extend(part.get('children',[]))
            if any(part.get('mountpoints') or []):raise ValueError('Selected disk or a child is mounted')
            active_swaps={line.split()[0] for line in inventory['fields']['swaps'].splitlines()[1:] if line.split()}
            if part.get('path') in active_swaps:raise ValueError('Selected disk contains active swap')
        rows.append({k:disk.get(k) for k in ('path','serial','wwn','model','size')})
    return {'schema':1,'unit_fingerprint':inventory['unit_fingerprint'],'disks':rows,
        'boot_partition_bytes':512*1024**2,'os_mirror_member_bytes':8*1024**3,
        'remaining_capacity':'reserved and unformatted','destructive':True,'writes_performed':False,
        'requires_separate_disk_erase_confirmation':True}
