"""Read-only Linux inventory; collectors never format, assemble or test-write."""
import json, os, re, subprocess, time
from pathlib import Path

def command(*args, timeout=15):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError('Inventory command failed: ' + args[0])
    return p.stdout

def collect():
    errors = []
    try:
        disks = json.loads(command('lsblk', '-J', '-b', '-o', 'NAME,PATH,TYPE,SIZE,MODEL,SERIAL,WWN,TRAN,FSTYPE,UUID,PARTUUID,MOUNTPOINTS,RO'))['blockdevices']
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as e:
        disks = []
        errors.append(str(e))
    try:
        root = json.loads(command('findmnt', '-J', '-o', 'TARGET,SOURCE,FSTYPE,UUID,OPTIONS', '/'))['filesystems'][0]
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as e:
        root = {}
        errors.append(str(e))
    arrays = []
    for directory in Path('/sys/class/block').glob('md*/md'):
        try:
            arrays.append({'device': '/dev/' + directory.parent.name, 'uuid': (directory / 'uuid').read_text().strip(), 'state': (directory / 'array_state').read_text().strip(), 'degraded': int((directory / 'degraded').read_text()), 'sync_action': (directory / 'sync_action').read_text().strip(), 'members': [p.name for p in (directory.parent / 'slaves').iterdir()]})
        except OSError as e:
            errors.append(str(e))
    volumes = []
    try:
        for row in json.loads(command('findmnt', '-J', '-o', 'TARGET,SOURCE,FSTYPE,UUID,OPTIONS'))['filesystems']:

            def visit(r):
                if r.get('uuid'):
                    try:
                        s = os.statvfs(r['target'])
                        volumes.append({**r, 'total_bytes': s.f_blocks * s.f_frsize, 'available_bytes': s.f_bavail * s.f_frsize, 'system': r['target'] == '/'})
                    except OSError:
                        pass
                for child in r.get('children', []):
                    visit(child)
            visit(row)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as e:
        errors.append(str(e))
    smart_results = []
    for disk in disks:
        device = disk.get('path', '')
        if disk.get('type') != 'disk' or not re.fullmatch('/dev/sd[a-z]+', device):
            continue
        if disk.get('tran')=='usb' or any(re.fullmatch('usb[0-9]+',part) for part in (Path('/sys/class/block')/Path(device).name/'device').resolve().parts):
            smart_results.append({'device':device,'available':False,'passed':None,'not_polled':True,'error':'USB member health unavailable; automatic vendor pass-through probes are disabled'})
            continue
        try:
            result = smart(device)
            if result['raw'].get('serial_number') and result['raw']['serial_number'].strip() != str(disk.get('serial', '')).strip():
                raise ValueError('Drive identity changed during SMART read')
            smart_results.append(result)
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            smart_results.append({'device': device, 'available': False, 'passed': None, 'error': str(error)})
    temperatures = []
    for p in Path('/sys/class/thermal').glob('thermal_zone*/temp'):
        try:
            temperatures.append({'name': p.parent.name, 'celsius': int(p.read_text()) / 1000})
        except (OSError, ValueError):
            pass
    return {'sampled_at': time.time(), 'kernel': os.uname().release, 'architecture': os.uname().machine, 'disks': disks, 'root': root, 'arrays': arrays, 'volumes': volumes, 'smart': smart_results, 'temperatures': temperatures, 'errors': errors, 'stale': False}

def smart(device):
    if not re.fullmatch('/dev/sd[a-z]+', device):
        raise ValueError('Select an inventoried SATA disk')
    p = subprocess.run(['smartctl', '-i', '-H', '-A', '-l', 'selftest', '-n', 'standby', '-j', device], capture_output=True, text=True, timeout=15)
    data = json.loads(p.stdout or '{}')
    return {'device': device, 'exit_flags': p.returncode, 'available': bool(data.get('device')) and (not p.returncode & 3), 'passed': data.get('smart_status', {}).get('passed'), 'temperature': data.get('temperature', {}).get('current'), 'raw': data, 'self_test_started': False}

def snapshot(path=None):
    if path:
        value = json.loads(Path(path).read_text())
        value['stale'] = not 0 <= time.time() - value['sampled_at'] < 120
        return value
    return collect()
