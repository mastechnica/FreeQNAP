"""Read-only front-button capabilities; no unvalidated input or buzzer commands."""
import json
from pathlib import Path

def status(request=None):
    policy={}
    try:policy=json.loads(Path('/etc/eyeq-buttons.json').read_text())
    except (OSError,ValueError):pass
    return {'power_action':policy.get('power','observe'),'reset_action':policy.get('reset','observe'),
            'raw_power_edges_accepted':False,'five_tap_shutdown_available':False,'pitched_melody_available':False,
            'reason':'The accepted controller reports a sustained press after about two seconds, not individual quick taps. Its validated buzzer command has a fixed tone; no pitched audio output is available.',
            'next_validation':'Passive raw-input discovery with the owner present, then isolated five-tap and melody tests. Existing held-button shutdown remains unchanged.',
            'requested_sequence':{'presses':5,'melody':'shutdown-melody.json','enabled':False}}
