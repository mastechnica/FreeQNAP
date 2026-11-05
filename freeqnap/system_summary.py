"""Read-only, allowlisted appliance telemetry for signed-in family accounts."""
import math
import threading
import time
from . import inventory


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def project_inventory(raw):
    volumes = []
    seen = set()
    data_index = 0
    for volume in sorted(raw.get('volumes', []), key=lambda v: not v.get('system', False)):
        identity = volume.get('uuid') or volume.get('source') or volume.get('target')
        if identity and identity in seen:
            continue
        if identity:
            seen.add(identity)
        if not volume.get('system'):
            data_index += 1
        volumes.append({'label': 'System' if volume.get('system') else 'Data volume '+str(data_index), 'total_bytes': number(volume.get('total_bytes')), 'available_bytes': number(volume.get('available_bytes'))})
    return {
        'sampled_at': number(raw.get('sampled_at')),
        'stale': bool(raw.get('stale', True)),
        'errors': ['Hardware inventory needs attention'] if raw.get('errors') else [],
        'disks': [{k: d.get(k) for k in ('name', 'path', 'type', 'size', 'model', 'tran')} for d in raw.get('disks', []) if d.get('type') == 'disk'],
        'smart': [{'device': d.get('device'), 'passed': d.get('passed') if isinstance(d.get('passed'), bool) else None, 'temperature': number(d.get('temperature')), 'not_polled': bool(d.get('not_polled'))} for d in raw.get('smart', [])],
        'arrays': [{'name': str(d.get('device', '')).split('/')[-1], 'state': d.get('state'), 'degraded': number(d.get('degraded')), 'sync_action': d.get('sync_action'), 'members': len(d.get('members', []))} for d in raw.get('arrays', [])],
        'volumes': volumes,
        'temperatures': [{'celsius': number(d.get('celsius'))} for d in raw.get('temperatures', [])],
    }


def project_health(raw):
    labels = {'raid': 'RAID protection', 'inventory': 'Hardware monitoring', 'smart': 'Disk health', 'space': 'Storage capacity', 'cooling': 'Cooling', 'workers': 'Background services', 'https': 'Secure dashboard', 'usb': 'USB storage', 'network': 'Network', 'watchdog': 'Hardware watchdog'}
    items = [{'severity': d['severity'], 'title': labels.get(str(d.get('scope', '')).removeprefix('monitor-'), 'System health'), 'since': number(d.get('first_seen'))} for d in raw.get('items', []) if d.get('resolved_at') is None and d.get('severity') in ('critical', 'warning', 'info')]
    return {'items': items, 'active_total': raw.get('active_total', len(items)), 'active_counts': {k: raw.get('active_counts', {}).get(k, 0) for k in ('critical', 'warning', 'info')}, 'monitor_stale': bool(raw.get('monitor_stale', True))}


def project_history(raw):
    keys = ('time', 'cpu', 'memory', 'memory_total', 'temperature', 'rx', 'tx', 'load', 'cores', 'uptime')
    return {'points': [{k: number(p.get(k)) for k in keys} for p in raw.get('points', [])], 'stale': bool(raw.get('stale', True))}


def project_frontpanel(raw):
    return {'available': bool(raw.get('available')), 'ports': [{'bay': p.get('bay'), 'present': bool(p.get('present')), 'green': bool(p.get('green')), 'disk': 'Drive installed' if p.get('present') else None} for p in raw.get('ports', [])], 'network': {k: {'up': v.get('up') if isinstance(v.get('up'), bool) else None, 'activity': bool(v.get('activity')), 'speed_mbps': number(v.get('speed_mbps'))} for k, v in raw.get('network', {}).items() if k in ('lan1', 'lan2')}}


class Summary:
    def __init__(self, broker, snapshot):
        from .nas.broker import Client
        self.broker = Client(broker.path, timeout=3) if isinstance(broker, Client) else broker
        self.snapshot = snapshot
        self.lock = threading.Lock()
        self.cached = None
        self.at = 0

    def read(self):
        with self.lock:
            if self.cached is not None and time.monotonic()-self.at < 10:
                return self.cached
            try:
                if self.snapshot is None:
                    raise ValueError('No hardware snapshot configured')
                value = project_inventory(inventory.snapshot(self.snapshot))
            except (OSError, ValueError, RuntimeError):
                value = project_inventory({'stale': True, 'errors': [True]})
            for key, operation, payload, project in [('health','health.alerts',{},project_health), ('history','system.history',{'hours':24},project_history), ('frontpanel','system.frontpanel',{},project_frontpanel)]:
                try:
                    value[key] = project(self.broker.request(operation, payload))
                except (OSError, ValueError, RuntimeError, KeyError, TypeError):
                    value[key] = {'unavailable': True, 'monitor_stale': True, 'stale': True}
            self.cached = value
            self.at = time.monotonic()
            return value
