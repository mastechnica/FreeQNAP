"""Reviewable pool planning; operating-system disks are never whole-disk targets."""
import hashlib, json, re, secrets, time
LEVELS = {'mirror': (2, 2), 'raid5': (3, 4), 'raid6': (4, 4), 'raid10': (4, 4)}

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()

def pool_plan(inventory, name, level, serials):
    if not re.fullmatch('[a-z][a-z0-9-]{0,30}', name):
        raise ValueError('Use a short lowercase pool name')
    if level not in LEVELS or not LEVELS[level][0] <= len(serials) <= LEVELS[level][1] or len(set(serials)) != len(serials):
        raise ValueError('Wrong number of unique disks for the selected layout')
    if inventory.get('stale') or not 0 <= time.time() - inventory['sampled_at'] < 120 or inventory.get('errors'):
        raise ValueError('Fresh complete inventory required')
    if not inventory.get('root', {}).get('uuid'):
        raise ValueError('Identified OS root required')
    root_uuid = inventory['root']['uuid']
    selected = []

    def descendants(row):
        yield row
        for child in row.get('children', []):
            yield from descendants(child)
    for serial in serials:
        rows = [d for d in inventory['disks'] if d.get('type') == 'disk' and d.get('serial') == serial]
        if len(rows) != 1:
            raise ValueError('Disk identity missing or ambiguous')
        disk = rows[0]
        all_rows = list(descendants(disk))
        if any((r.get('uuid') == root_uuid or '/' in (r.get('mountpoints') or []) for r in all_rows)):
            raise ValueError('Operating-system disk is protected; only separately prepared data regions may be used')
        if disk.get('children') or disk.get('fstype') or any((any(r.get('mountpoints') or []) for r in all_rows)):
            raise ValueError('Whole-disk planning accepts only blank unused data disks')
        if not disk.get('wwn') or int(disk.get('size', 0)) < 16 * 1024 ** 3:
            raise ValueError('Immutable identity and supported capacity required')
        selected.append({k: disk.get(k) for k in ('path', 'serial', 'wwn', 'size', 'model')})
    smallest = min((d['size'] for d in selected))
    factor = {'mirror': 1, 'raid5': len(selected) - 1, 'raid6': len(selected) - 2, 'raid10': len(selected) // 2}[level]
    result = {'format': 1, 'id': secrets.token_hex(16), 'created_at': time.time(), 'name': name, 'level': level, 'members': selected, 'root_uuid': root_uuid, 'filesystem': 'ext4', 'estimated_usable_bytes': smallest * factor, 'mountpoint': '/srv/freeqnap/volumes/' + name, 'destructive': True, 'writes_performed': False, 'execution_available': False, 'execution_limit': 'Reviewed partition/array execution and failure/rebuild acceptance are required before this public path is enabled'}
    return {**result, 'sha256': hashlib.sha256(canonical(result)).hexdigest()}

def verify_plan(plan, inventory, digest):
    body = {k: v for k, v in plan.items() if k != 'sha256'}
    if hashlib.sha256(canonical(body)).hexdigest() != digest or plan.get('sha256') != digest:
        raise ValueError('Reviewed plan changed')
    if not 0 <= time.time() - plan['created_at'] < 600:
        raise ValueError('Reviewed plan expired')
    fresh = pool_plan(inventory, plan['name'], plan['level'], [m['serial'] for m in plan['members']])
    if fresh['members'] != plan['members'] or fresh['root_uuid'] != plan['root_uuid']:
        raise ValueError('Disk or OS identity changed')
    return True
