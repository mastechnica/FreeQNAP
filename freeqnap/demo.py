"""Synthetic read-only preview; never probes real disks or runs jobs."""
import time
from .nas.ddns import PROVIDERS
from .nas.health import DEFAULTS
from .nas.notifications import DEFAULT

def inventory():
    return {'sampled_at': time.time(), 'kernel': 'FreeQNAP development preview', 'architecture': 'armv7l', 'stale': False, 'errors': [], 'root': {'uuid': 'demo-os-mirror', 'target': '/'}, 'temperatures': [{'name': 'CPU', 'celsius': 43}], 'arrays': [{'device': '/dev/md-demo', 'state': 'active', 'degraded': 0, 'sync_action': 'idle', 'members': ['disk-a', 'disk-b']}], 'volumes': [{'target': '/', 'source': 'OS mirror', 'uuid': 'demo-os-mirror', 'total_bytes': 8 * 1024 ** 3, 'available_bytes': 6 * 1024 ** 3, 'system': True}], 'disks': [{'name': 'Demo disk ' + str(i), 'path': '/dev/demo' + str(i), 'type': 'disk', 'serial': 'DEMO-' + str(i), 'wwn': 'demo-wwn-' + str(i), 'size': 10 * 1000 ** 4, 'model': 'Example 10 TB disk', 'mountpoints': [], 'children': [{'uuid': 'demo-os-mirror', 'mountpoints': ['/']}] if i < 3 else []} for i in range(1, 5)]}


def nas():
    return {'pools':[{'name':'example-data','level':'mirror','encrypted':True,'mounted':False,'locked':True,'mountpoint':'/srv/freeqnap/volumes/example-data'}],
            'shares':[], 'users':[], 'repositories':[], 'libraries':[], 'jobs':[], 'services':{},
            'worker':{'worker_ok':True}, 'packages':{k:True for k in ('mdadm','cryptsetup','mkfs.ext4','smbd','ganesha.nfsd','netatalk','restic','gerbera','ffprobe')},
            'health':{'items':[{'id':'demo-alert','scope':'raid','source':'synthetic','severity':'warning','title':'Synthetic RAID synchronization example','details':{'operation':'example only'},'first_seen':time.time()-120,'last_seen':time.time(),'resolved_at':None,'acknowledged_at':None}],'active_total':1,'active_counts':{'warning':1},'monitor':{'checked_at':time.time()},'monitor_stale':False,'policy':DEFAULTS},
            'notifications':{'config':DEFAULT,'subscriptions':[],'outbox':[],'smtp_password_saved':False,'push_dependencies_available':True},
            'ddns':{'items':[],'providers':[{'id':k,**v} for k,v in PROVIDERS.items()],'driver_available':True},
            'physical_recovery_acceptance':False,'shutdown_metadata_followup_open':True,'demo':True}
