"""Fixed root-broker operation registry; independent, durable background jobs."""
import json
import os
import shutil
import socket
import threading
import time
import uuid
from pathlib import Path
from .common import Context, name
from .personal_photos import PersonalPhotos
from .personal_cloud import PersonalCloud
from .disk_reports import DiskReports
from .cooling import Cooling
from .alert_rules import AlertRules
from .status_light import StatusLight
from .metrics import Metrics
from .frontpanel import snapshot as frontpanel_snapshot
from .storage import Storage
from .array_recovery import ArrayRecovery
from .myradio import MyRadio
from .library_storage import LibraryStorage,FileLocation
from .personal import Personal
from .file_metadata import FileMetadata
from .power_button import status as power_button_status
from .sharing import Sharing, SERVICES
from .filebackup import FileBackups
from .backup_schedules import BackupSchedules
from .system_recovery import SystemRecovery
from .management_tls import ManagementTLS
from .local_recovery import LocalRecovery
from .health import Health
from .notifications import Notifications
from .ddns import DDNS
from .fileops import FileManager
from .media import Media
from .recovery import Recovery
from .vpn import VPN
from .downloads import Downloads
from .dlna import Access
from .external import External
from .network import Network
from .bundle import Bundles
from .archives import Archives
from .foreign import Foreign

class Backend:
    def __init__(self, context=None):
        self.ctx = context or Context()
        from .user_usage import Usage
        self.user_usage=Usage(self)
        self.metrics = Metrics(self.ctx)
        self.status_light = StatusLight(self.ctx)
        self.disk_reports = DiskReports(self.ctx)
        self.cooling = Cooling()
        self.alert_rules = AlertRules(self.ctx)
        self.storage = Storage(self.ctx)
        self.array_recovery = ArrayRecovery(self.ctx,self.storage)
        self.my_radio = MyRadio(self.ctx)
        self.management_tls = ManagementTLS(self.ctx)
        self.sharing = Sharing(self.ctx)
        self.backups = FileBackups(self.ctx)
        self.backup_schedules = BackupSchedules(self.ctx)
        self.system_recovery = SystemRecovery(self.ctx)
        self.local_recovery = LocalRecovery(self.ctx,self.system_recovery)
        self.files = FileManager(self.ctx)
        self.file_metadata=FileMetadata(self.ctx,self.files)
        self.bundles = Bundles(self.ctx,self.files)
        self.archives = Archives(self.ctx,self.files,self.bundles)
        self.media = Media(self.ctx)
        self.personal_photos=PersonalPhotos(self.ctx)
        self.library_storage=LibraryStorage(self.ctx,self.my_radio,self.personal_photos)
        self.personal_files=FileLocation(self.ctx,self.library_storage.owner)
        self.personal=Personal(self)
        from .social_media import SocialMedia
        self.social=SocialMedia(self)
        self.personal_cloud=PersonalCloud(self.personal_photos)
        self.recovery = Recovery(self.ctx,self.files)
        self.external = External(self.ctx)
        self.foreign = Foreign(self.ctx,self.external)
        self.network = Network(self.ctx)
        self.vpn = VPN(self.ctx)
        self.downloads = Downloads(self.ctx)
        self.dlna = Access(self.ctx)
        if not self.ctx.state.setting('dlna_udn'):
            self.ctx.state.set('dlna_udn', 'uuid:' + str(uuid.uuid4()))
        self.stop_event = threading.Event()
        self.last_active = None
        self.health = {'worker_ok': True, 'last_checked': None, 'error': None}
        self.alerts = Health(self.ctx,schedules=self.backup_schedules)
        self.notifications = Notifications(self.ctx)
        self.ddns = DDNS(self.ctx)
        self.alerts.optional_checks={'personal-photos':self.personal_cloud.health,'cooling':self.cooling.health,'watchdog':self.cooling.watchdog_health,'notifications':self.notifications.health,'ddns':self.ddns.health,'workers':self.worker_alerts,'https':self.https_alerts}

    def status(self):
        from ..access_scope import metadata
        with metadata():return self.status_metadata()

    def status_metadata(self):
        config = self.ctx.config()
        pools = [];arrays={}
        for pool in config['pools'].values():
            value = {**pool, 'mounted': False, 'locked': pool['encrypted']}
            try:
                _, mount = self.ctx.volume(pool['name'])
                space = os.statvfs(mount)
                from ..access_scope import check
                try:check(self.ctx,pool,content=True);private_access=True
                except ValueError:private_access=False
                value.update(private=bool(pool.get('encrypted')),content_access=private_access,mounted=True, locked=False, available_bytes=space.f_bavail * space.f_frsize,
                             total_bytes=space.f_blocks * space.f_frsize)
            except (ValueError, OSError):pass
            if pool.get('md_uuid') and pool.get('kind')!='usb':
                if pool['md_uuid'] not in arrays:
                    try:arrays[pool['md_uuid']]=self.storage.inspect_array(pool)
                    except (ValueError,OSError,KeyError):arrays[pool['md_uuid']]={'unavailable':True}
                value['array']=arrays[pool['md_uuid']]
            pools.append(value)
        services = {}
        for service in (*SERVICES,'freeqnap-vpn','freeqnap-vpn-firewall','freeqnap-downloads'):
            try:services[service] = self.ctx.run('systemctl', 'show', service, '--property=ActiveState', '--value').strip()
            except ValueError:services[service] = 'inactive-or-failed'
        return {'pools': pools, 'shares': list(config['shares'].values()), 'users': list(config['users'].values()),
                'repositories': [self.backups.public(row) for row in config['repositories'].values()],
                'libraries': list(config['libraries'].values()), 'services': services,
                'jobs': self.ctx.state.jobs(), 'worker': self.health,
                'packages': {binary: bool(shutil.which(binary)) for binary in
                             ('mdadm', 'cryptsetup', 'mkfs.ext4', 'smbd', 'ganesha.nfsd', 'netatalk', 'restic', 'gerbera', 'ffprobe','openvpn','wg','wireguard-go','aria2c','nft','tdbbackup','gpg')},
                'local_recovery_backups':self.local_recovery.list(), 'backup_schedules':self.backup_schedules.list(), 'system_recovery_stages':self.system_recovery.stages(), 'startup_errors': self.ctx.state.setting('startup_errors',[]),
                'network':self.network.status(), 'vpn': self.vpn.status(), 'downloads': self.downloads.status(), 'dlna_access': self.dlna.list(),
                'cooling':self.optional_status(self.cooling), 'notifications':self.optional_status(self.notifications), 'ddns':self.optional_status(self.ddns), 'health':self.alert_status(), 'management_tls':self.management_tls.status(), 'physical_recovery_acceptance': False, 'shutdown_metadata_followup_open': True}

    def dispatch(self, action, request):
        if action=='access.invoke':
            from ..access_scope import using
            if set(request)!={'actor','action','payload'} or request['action'].startswith('access.'):raise ValueError('Invalid access envelope')
            with using(request['actor']):
                result=self.dispatch(request['action'],request['payload'])
                return result
        if action.startswith(('myradio.','photos.')):
            from ..access_scope import check
            cfg=self.ctx.state.setting('myradio' if action.startswith('myradio.') else 'personal-photos',{})
            pool=self.ctx.config()['pools'].get(cfg.get('pool'),{})
            if pool:check(self.ctx,pool,content=True)
        if action=='users.usage':return self.user_usage.status(request)
        if action=='activity.system':return self.system_activity()
        if action=='activity.jobs':return self.job_activity(request)
        if action=='personal.social-prepare':return self.social.prepare(request)
        if action=='personal.social-read':return self.social.read(request)
        if action=='personal.social-discard':return self.social.discard(request)
        if action=='personal.shared':return self.personal.shared(request)
        if action=='personal.control':return self.personal.control(request)
        if action=='personal.options':return {'shares':list(self.ctx.config()['shares'].values()),'pools':{k:{'filesystem_uuid':v['filesystem_uuid']} for k,v in self.ctx.config()['pools'].items()}}
        if action=='personal.invoke':return self.personal.invoke(request)
        direct = {
            'nas.status': lambda _: self.status(),
            'library.folders':lambda r:self.files.list({'share':'pool:'+r['pool'],'path':r.get('path',''),'offset':r.get('offset',0),'limit':r.get('limit',200)}), 'library.files-status':self.personal_files.status,'library.files-plan':self.personal_files.plan,'library.files-apply':self.personal_files.apply,
            'library.storage-plan':self.library_storage.plan,
            'myradio.status':self.my_radio.status,
            'myradio.configure':self.my_radio.configure,
            'myradio.catalog':self.my_radio.catalog,
            'myradio.item':self.my_radio.item,
            'myradio.read':self.my_radio.read,
            'myradio.book-text':self.my_radio.book_text,
            'myradio.upload-begin':self.my_radio.upload_begin,
            'myradio.upload-chunk':self.my_radio.upload_chunk,
            'myradio.upload-finish':self.my_radio.upload_finish,
            'myradio.metadata':self.my_radio.metadata,
            'myradio.artwork':self.my_radio.artwork,
            'myradio.artwork-url':self.my_radio.artwork_url,
            'myradio.progress':self.my_radio.progress,
            'myradio.lookup':self.my_radio.lookup,
            'myradio.station-artwork':self.my_radio.station_artwork, 'myradio.stations':self.my_radio.stations,
            'myradio.station-save':self.my_radio.station_save,
            'myradio.station-check':self.my_radio.station_check,
            'myradio.station-source':self.my_radio.station_source,
            'myradio.podcasts':self.my_radio.feeds,
            'myradio.podcast-add':self.my_radio.feed_add,
            'myradio.podcast-refresh':self.my_radio.feed_refresh,
            'myradio.import-url':lambda r:self.my_radio.queue_url(r,self.ctx.state.enqueue), 'myradio.resume-download':lambda r:self.my_radio.retry_download(r,self.ctx.state.enqueue), 'myradio.episode-download':lambda r:self.my_radio.episode_download(r,self.ctx.state.enqueue),
            'raid.recovery-status':self.array_recovery.status,
            'raid.inspect-plan':lambda r:self.array_recovery.plan({**r,'mode':'readonly'}), 'raid.inspect-apply':lambda r:self.array_recovery.apply(r,'readonly'),
            'raid.resume-plan':lambda r:self.array_recovery.plan({**r,'mode':'resume'}), 'raid.resume-apply':lambda r:self.array_recovery.apply(r,'resume'),
            'raid.mount-plan':lambda r:self.array_recovery.plan({**r,'mode':'mount'}), 'raid.mount-apply':lambda r:self.array_recovery.apply(r,'mount'),
            'raid.backup-read':self.array_recovery.download,
            'raid.backups':self.array_recovery.backup_list, 'raid.backup-remove':self.array_recovery.backup_remove,
            'system.button-status':power_button_status,
            'notifications.status':self.notifications.status, 'notifications.save':self.notifications.save, 'notifications.push-key':self.notifications.public_key, 'notifications.subscribe':self.notifications.subscribe, 'notifications.unsubscribe':self.notifications.unsubscribe, 'notifications.test':self.notifications.test, 'notifications.retry-plan':self.notifications.retry_plan, 'notifications.retry':self.notifications.retry, 'notifications.discard':self.notifications.discard,
            'ddns.status':self.ddns.status, 'ddns.plan':self.ddns.plan, 'ddns.save':self.ddns.apply, 'ddns.remove':self.ddns.remove, 'ddns.update':self.ddns.request_update,
            'vpn.peers-status':self.vpn.peer_status, 'smart.status':self.disk_reports.status, 'smart.history':self.disk_reports.history, 'smart.schedule':self.disk_reports.save, 'notifications.rules':self.alert_rules.status, 'notifications.rules-save':self.alert_rules.save, 'notifications.buzzer':self.alert_rules.sound, 'health.alerts':self.alerts.list, 'health.acknowledge':self.alerts.acknowledge, 'health.settings':self.alerts.settings,
            'system.cooling-status':self.cooling.status, 'system.cooling-history':self.cooling.history, 'system.cooling-mode':self.cooling.mode, 'system.watchdog-status':self.cooling.watchdog,
            'system.https-status':self.management_tls.status, 'system.https-ca':self.management_tls.public_ca,
            'network.status':self.network.status,'network.plan':self.network.plan,'network.apply':self.network.apply,
            'network.confirm':self.network.confirm,'network.rollback':self.network.rollback,'network.client-plan':self.network.client_plan,
            'vpn.status': self.vpn.status, 'vpn.plan': self.vpn.plan, 'vpn.apply': self.vpn.apply,
            'vpn.confirm': self.vpn.confirm, 'vpn.rollback': self.vpn.rollback,
            'vpn.peer': self.vpn.peer, 'vpn.revoke': self.vpn.revoke, 'vpn.wireguard-profile':self.vpn.wireguard_profile,
            'downloads.status': self.downloads.status, 'downloads.setup': self.downloads.setup,
            'downloads.add': self.downloads.add, 'downloads.control': self.downloads.control,
            'downloads.files':self.downloads.list_files,'downloads.read':self.downloads.read_file,
            'media.dlna-options':self.dlna.options, 'media.dlna-options-save':self.dlna.save_options, 'media.client-profile':self.dlna.client_profile, 'system.frontpanel':lambda r:frontpanel_snapshot(), 'network.history':self.metrics.network_history, 'system.history':self.metrics.history, 'media.clients': self.dlna.list, 'media.approve': self.dlna.approve,
            'external.unlock-capabilities':self.foreign.capabilities, 'external.unlock-plan':self.foreign.plan, 'external.unlock':self.foreign.unlock, 'external.lock-session':self.foreign.lock, 'external.session-files':self.foreign.files, 'external.session-read':lambda r:self.foreign.files(r,True),
            'external.discover':self.external.discover,'external.import-plan':self.external.import_plan,'external.import':self.external.import_volume,
            'external.create-plan':self.external.create_plan,'external.create':self.external.create,'external.mount':self.external.mount,
            'external.eject-plan':self.external.eject_plan,'external.eject':self.eject_external,
            'external.files':self.external.list_files,'external.read':self.external.read_file,
            'external.forget-plan':self.external.forget_plan,'external.forget':self.external.forget,
            'storage.plan': self.storage.plan, 'storage.create': self.storage.create,
            'storage.discover': self.storage.discover, 'storage.import-plan': self.storage.import_plan,
            'storage.import': self.storage.import_array, 'storage.check': self.storage.check,
            'storage.replace-plan': self.storage.replacement_plan, 'storage.replace': self.storage.replace,
            'storage.unlock': self.storage.unlock,
            'encryption.key-plan': self.storage.key_plan, 'encryption.add-key': self.storage.add_key,
            'encryption.header-backup': self.storage.header_backup, 'artifacts.read': self.storage.artifact_read,
            'storage.lock': lambda r: self.lock_volume(r),
            'users.save': self.sharing.user, 'shares.save': self.sharing.share,
            'shares.apply': lambda _: self.sharing.apply(),
            'shares.toggle': self.sharing.toggle, 'shares.remove': self.sharing.remove,
            'backup.local-create':self.local_recovery.create, 'backup.local-list':self.local_recovery.list, 'backup.local-read':self.local_recovery.read, 'backup.system-stage-plan':self.system_recovery.stage_plan, 'backup.system-stage-remove':self.system_recovery.stage_remove, 'backup.system-stages':self.system_recovery.stages,
            'backup.schedule-plan':self.backup_schedules.plan, 'backup.schedule-save':self.backup_schedules.apply, 'backup.schedule-list':self.backup_schedules.list, 'backup.schedule-run':self.backup_schedules.run_now, 'backup.schedule-delete-plan':self.backup_schedules.delete_plan, 'backup.schedule-delete':self.backup_schedules.delete,
            'repositories.create': self.backups.repository,
            'repositories.snapshots': lambda r: self.backups.snapshots(r['repository']),
            'repositories.prune-plan': self.backups.prune_plan,
            'repositories.prune': self.backups.prune,
            'files.archive-plan':self.archives.plan, 'files.bundle':self.bundles.start,'files.bundle-info':self.bundles.info,'files.bundle-node':self.bundles.node,'files.bundle-read':self.bundles.read,
            'files.pool-list':lambda r:self.external.list_files(r,registered_pool=True), 'files.pool-read':lambda r:self.external.read_file(r,registered_pool=True),
            'files.metadata-read':self.file_metadata.read,'files.metadata-plan':self.file_metadata.plan,'files.metadata-apply':self.file_metadata.apply,
            'files.media-neighbors':self.files.media_neighbors,'files.list': self.files.list, 'files.read': self.files.read, 'files.mkdir': self.files.mkdir,
            'files.upload-begin': self.files.upload_begin, 'files.upload-chunk': self.files.upload_chunk,
            'files.upload-finish': self.files.upload_finish, 'files.move-plan': self.files.move_plan,
            'files.move': self.files.move, 'files.transfer-plan': self.files.transfer_plan,
            'files.transfer-resume-plan':self.files.transfer_resume_plan, 'files.transfer-retry-plan':self.files.transfer_retry_plan, 'files.transfers':self.files.transfers, 'files.stages':self.files.stages,'files.stage-plan':self.files.stage_plan,'files.stage-remove':self.files.stage_remove,
            'files.delete-plan': self.files.delete_plan, 'files.trash': self.files.trash_items, 'files.recycle-policy': self.files.policy_apply, 'files.recycle-policy-plan':self.files.policy_plan, 'files.recycle-plan':self.files.recycle_plan,
            'files.purge-plan': self.files.purge_plan, 'files.purge': self.files.purge,
            'recovery.list': self.recovery.list, 'recovery.plan': self.recovery.plan, 'recovery.apply': self.recovery.apply,
            'photos.metadata-read':self.personal_photos.metadata_read,'photos.metadata-plan':self.personal_photos.metadata_plan,'photos.metadata-apply':self.personal_photos.metadata_apply,
            'photos.status':lambda r:self.personal_photos.status(r), 'photos.configure':self.personal_photos.configure,
            'photos.related':self.personal_photos.related, 'photos.catalog':self.personal_photos.catalog, 'photos.places':self.personal_photos.places,
            'photos.read':self.personal_photos.read, 'photos.annotate':self.personal_photos.annotate,
            'photos.album-create':self.personal_photos.album, 'photos.album-add':self.personal_photos.album_add,
            'photos.import-folder':self.personal_photos.import_folder, 'photos.pause':self.personal_cloud.pause,
            'photos.icloud-check':self.personal_cloud.check, 'photos.icloud-status':self.personal_cloud.status, 'photos.icloud-save':self.personal_cloud.save,
            'photos.icloud-login':self.personal_cloud.login, 'photos.icloud-code':self.personal_cloud.code,
            'photos.icloud-run':self.personal_cloud.run,
            'media.save': lambda r: self.save_library(r), 'media.catalog': self.media.catalog,
            'media.provider-status':self.media.provider_status, 'media.provider-save':self.media.provider_save, 'media.scanner-settings':self.media.scanner_settings, 'media.scanner-status':self.media.scanner_status, 'media.artwork':self.media.artwork, 'media.lookup': self.media.lookup, 'media.metadata': self.media.apply_metadata,
            'jobs.retry': self.retry, 'system.plan': self.system_plan, 'system.apply': self.system_apply,
        }
        if not isinstance(request, dict):raise ValueError('JSON object required')
        if action in direct:return direct[action](request)
        if action in ('library.storage-apply','myradio.scan','myradio.import-folder','myradio.station-refresh','backup.system-run','backup.run', 'backup.check', 'backup.restore', 'media.scan','files.transfer','files.delete','files.recycle','files.archive'):
            # Queue payloads contain only references, never credentials/unlock material.
            schema = {'library.storage-apply':{'plan_id','digest','confirmation'},'myradio.scan':set(),'myradio.import-folder':{'category','share','path'},'myradio.station-refresh':{'group','query','country'},'backup.system-run':{'repository'},'files.archive':{'plan_id','digest','confirmation'},'backup.run': {'repository','shares','same_pool_confirmation'}, 'backup.check': {'repository','read_data'}, 'backup.restore': {'repository','snapshot','pool','include'}, 'media.scan': {'library'},'files.transfer':{'plan_id','digest','confirmation'},'files.delete':{'plan_id','digest','confirmation'},'files.recycle':{'plan_id','digest','confirmation'}}
            if set(request) - schema[action]:
                raise ValueError('Credentials cannot be saved in a job')
            return {'job_id': self.ctx.state.enqueue(action, request)}
        raise ValueError('Unknown or unsupported NAS operation')

    def job_activity(self,r):
        from .. import activity
        from ..state import State
        from ..access_scope import current
        actor=current();admin=r.get('administrator') is True;events=[]
        scopes=[self.ctx.state]
        personal=self.ctx.directory/'personal'
        if personal.exists():
            for path in personal.iterdir():
                if path.is_dir() and len(path.name)==32 and (admin or actor=='user:'+path.name):scopes.append(State(path))
        for state in scopes:
            activity.ensure(state)
            with state.connect() as db:
                query="SELECT at,actor,operation,outcome,severity FROM activity_events WHERE scope='private'";args=[]
                if not admin:query+=' AND actor=?';args=[actor]
                events.extend(dict(v) for v in db.execute(query+' ORDER BY id DESC LIMIT 100',args))
        return sorted(events,key=lambda v:v['at'],reverse=True)[:100]

    def system_activity(self):
        from .. import activity
        activity.ensure(self.ctx.state)
        try:
            boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            with self.ctx.state.connect() as db:
                db.execute('BEGIN IMMEDIATE');row=db.execute("SELECT value FROM settings WHERE key='activity-boot'").fetchone()
                if not row or json.loads(row[0])!=boot:
                    db.execute("INSERT INTO activity_events(at,actor,operation,outcome,scope,severity,bytes) VALUES(?,'system','system.boot-observed','changed','system','info',0)",(time.time(),))
                    db.execute("INSERT OR REPLACE INTO settings VALUES('activity-boot',?)",(json.dumps(boot),))
        except OSError:pass
        with self.ctx.state.connect() as db:
            labels={'inventory':'Hardware monitoring','raid':'RAID protection and maintenance','smart':'Disk health','space':'Storage capacity','temperature':'System temperature','jobs':'Background operations','schedules':'Scheduled backups','services':'NAS services','personal-photos':'Photo archive service','cooling':'Cooling','watchdog':'Hardware watchdog','notifications':'Notification service','ddns':'Dynamic DNS','workers':'Background services','https':'Local HTTPS'}
            health=[{'id':'health:'+str(v['id']),'at':v['created'],'operation':'system.health.'+v['kind'],'severity':v['severity'],'outcome':'changed','summary':labels.get(v['scope'].removeprefix('monitor-'),'System health')+' · '+v['severity']+' · '+v['kind']} for v in db.execute('SELECT e.id,e.created,e.kind,e.severity,a.scope FROM health_events e JOIN health_alerts a ON a.id=e.alert_id ORDER BY e.id DESC LIMIT 100')]
            events=[dict(v) for v in db.execute("SELECT id,at,operation,outcome,severity FROM activity_events WHERE scope='system' ORDER BY id DESC LIMIT 100")]
        return sorted(health+events,key=lambda v:v['at'],reverse=True)[:100]

    def system_plan(self, request):
        if self.personal_photos.busy.locked() or self.personal_cloud.auth_lock.locked():raise ValueError('Pause and wait for personal photo activity before changing system power')
        operation=request.get('operation')
        if operation not in ('restart','shutdown'):raise ValueError('Choose restart or shutdown')
        active=[job for job in self.ctx.state.jobs() if job['status'] in ('queued','running')]
        if active:raise ValueError('Wait for or reconcile active jobs before changing system power')
        return self.ctx.plan('system-power',{'operation':operation,'shutdown_metadata_followup_open':True},operation.upper()+' NAS')

    def system_apply(self, request):
        if self.personal_photos.busy.locked() or self.personal_cloud.auth_lock.locked():raise ValueError('Personal photo activity started; pause and review power operation again')
        with self.ctx.lock():
            path,plan=self.ctx.reviewed(request,'system-power')
            if any(job['status'] in ('queued','running') for job in self.ctx.state.jobs()):raise ValueError('An operation started after the power plan; wait and review again')
            self.ctx.consume(path,plan)
            from .. import activity
            activity.record(self.ctx.state,'system','system.'+plan['body']['operation'],'accepted',scope='system')
            action='reboot' if plan['body']['operation']=='restart' else 'poweroff'
            timer=threading.Timer(2,lambda:self.ctx.run('systemctl',action));timer.daemon=True;timer.start()
            return {'scheduled':plan['body']['operation'],'delay_seconds':2}

    def retry(self, request):
        ident = request.get('id')
        jobs = {job['id']: job for job in self.ctx.state.jobs()}
        if ident not in jobs or jobs[ident]['kind'] not in ('backup.run','backup.system-run', 'backup.check', 'media.scan'):
            raise ValueError('This operation requires a new reviewed plan or restore stage, not blind retry')
        if jobs[ident]['kind']=='backup.system-run':
            with self.ctx.lock():
                if self.ctx.state.setting('system_stage_deleted:'+ident):raise ValueError('Capture was explicitly removed; start a new system backup')
                self.ctx.state.retry(ident)
        else:self.ctx.state.retry(ident)
        return {'queued': True}

    def lock_volume(self, request):
        try:
            def stop_dependents():
                self.sharing.stop()
                settings=self.downloads.settings()
                if settings and settings['pool']==request.get('pool'):self.ctx.run('systemctl','stop','freeqnap-downloads.service')
            return self.storage.lock(request, stop_dependents)
        finally:
            # A busy volume must not leave unrelated or still-mounted shares offline.
            self.sharing.apply()
            self.configure_media()

    def save_library(self, request):
        result = self.media.library(request)
        self.configure_media()
        return result

    def configure_media(self):
        xml, libraries = self.media.dlna_config()
        self.ctx.run('systemctl', 'stop', 'freeqnap-dlna', timeout=45)
        path = Path('/etc/freeqnap/gerbera.xml')
        path.write_text(xml);path.chmod(0o644)
        if libraries:
            self.dlna.interface = libraries[0].get('interface','enp0s1')
            self.dlna.apply()
            # Grant read/traverse only on explicitly designated media folders.
            # Existing nested permissions are not silently rewritten recursively.
            for library in libraries:
                self.ctx.run('setfacl', '-m', 'u:gerbera:rx,d:u:gerbera:rx', library['path'])
            self.ctx.run('systemctl', 'start', 'freeqnap-dlna', timeout=45)
        return {'dlna_libraries': [row['name'] for row in libraries], 'default_deny':True}

    def execute(self, job):
        from ..access_scope import using
        with self.ctx.state.connect() as db:row=db.execute('SELECT actor FROM job_principals WHERE id=?',(job['id'],)).fetchone()
        with using(row['actor'] if row else None):return self.execute_scoped(job)

    def execute_scoped(self, job):
        request = json.loads(job['payload'])
        actions = {
            'library.storage-apply':self.library_storage.apply, 'myradio.scan':self.my_radio.scan, 'myradio.import-folder':self.my_radio.import_folder,'myradio.station-refresh':self.my_radio.station_refresh,'myradio.download':self.my_radio.download,
            'backup.system-run':lambda r:self.system_recovery.backup(r,job['id'],self.backups), 'backup.run': self.backups.backup, 'backup.check': self.backups.check,
            'backup.restore': lambda r: self.backups.restore(r, job['id']),
            'files.archive':lambda r:self.archives.apply(r,job['id']), 'media.scan': self.media.scan, 'files.transfer':lambda r:self.files.transfer(r,job['id']), 'files.delete':self.files.move, 'files.recycle':lambda r:self.files.recycle(r,job['id']),
        }
        try:
            if job['kind'] not in actions:raise ValueError('Unknown queued operation')
            result = actions[job['kind']](request)
            if job['kind'] == 'media.scan' and not result['complete']:
                raise ValueError('Media scan incomplete; progress is retained. Inspect errors/limits and explicitly retry.')
            self.ctx.state.finish(job['id'], result=result)
        except Exception as error:
            self.ctx.state.finish(job['id'], error=str(error))

    def worker(self):
        while not self.stop_event.is_set():
            try:
                job = self.ctx.state.claim()
                if job:self.execute(job)
                else:self.personal.one()
                self.personal.tick()
                self.social.cleanup()
                self.health.update(worker_ok=True, last_checked=time.time(), error=None)
            except Exception as error:
                self.health.update(worker_ok=False, last_checked=time.time(), error=str(error))
            self.stop_event.wait(.5)

    def guardian(self):
        """A disappeared/locked mount must stop dependent service exports."""
        while not self.stop_event.is_set():
            try:
                active = tuple((row['name'], row['pool']) for row in self.sharing.active())
                if active != self.last_active:
                    with self.ctx.lock():
                        self.sharing.apply();self.configure_media();self.last_active = active
                self.health.pop('guardian_error',None)
            except Exception as error:
                self.health['guardian_error'] = str(error)
                # Fail closed: stop exports; retain root-owned desired configuration.
                for service in SERVICES[:4]:
                    try:self.ctx.run('systemctl', 'stop', service, timeout=15)
                    except Exception:pass
            try:self.dlna.observe()
            except Exception:pass
            self.stop_event.wait(2)

    def disk_report_worker(self):
        while not self.stop_event.is_set():
            try:self.disk_reports.tick();self.health.pop('disk_reports_error',None)
            except Exception:self.health['disk_reports_error']='SMART reports/schedules need attention; existing reports retained'
            self.stop_event.wait(60)

    def metrics_worker(self):
        while not self.stop_event.is_set():
            try:self.metrics.sample();self.health.pop('metrics_error',None)
            except (OSError,ValueError,KeyError):self.health['metrics_error']='System history collection unavailable'
            self.stop_event.wait(30)

    def download_worker(self):
        while not self.stop_event.is_set():
            try:self.downloads.reconcile();self.health.pop('downloads_error',None)
            except Exception:self.health['downloads_error']='Engine unavailable; download jobs retained'
            self.stop_event.wait(5)

    def eject_external(self,request):
        def stop(pools):
            self.sharing.stop()
            settings=self.downloads.settings()
            if settings and settings['pool'] in pools:self.ctx.run('systemctl','stop','freeqnap-downloads.service')
        try:return self.external.eject(request,stop)
        finally:self.sharing.apply();self.configure_media()

    def recycle_worker(self):
        while not self.stop_event.is_set():
            try:self.files.expire();self.health.pop('recycle_error',None)
            except Exception:self.health['recycle_error']='Recycle cleanup incomplete; records and remaining data retained'
            self.stop_event.wait(300)

    def backup_schedule_worker(self):
        while not self.stop_event.is_set():
            try:self.backup_schedules.tick();self.health.pop('backup_scheduler_error',None)
            except Exception:self.health['backup_scheduler_error']='Backup scheduling unavailable; policies and jobs retained'
            self.stop_event.wait(30)

    def alert_status(self):
        try:
            value=self.alerts.list()
            try:value['external_delivery_enabled']=any(c['enabled'] for c in self.notifications.current()['config'].values())
            except (ValueError,KeyError,TypeError):value['external_delivery_enabled']=None
            return value
        except (OSError,ValueError,KeyError,TypeError):return {'available':False,'monitor_stale':True,'error':'Local health monitor state is unavailable; other NAS controls remain independent'}

    def health_worker(self):
        while not self.stop_event.is_set():
            try:self.alerts.tick();self.health.pop('health_monitor_error',None)
            except Exception:self.health['health_monitor_error']='Local health monitoring needs attention; other workers continue'
            if not self.stop_event.is_set():
                try:self.status_light.update(self.alerts.list());self.health.pop('status_light_error',None)
                except Exception:self.health['status_light_error']='Physical status light could not be updated; other services continue'
            self.stop_event.wait(30)

    def optional_status(self,service):
        try:return service.status()
        except (OSError,ValueError,KeyError,TypeError):return {'available':False,'error':'Optional service state is unavailable; other NAS functions remain independent'}

    def notification_worker(self):
        while not self.stop_event.is_set():
            try:self.notifications.tick();self.health.pop('notification_worker_error',None)
            except Exception:self.health['notification_worker_error']='Notification worker needs attention; queued items retained'
            try:self.alert_rules.tick();self.health.pop('buzzer_error',None)
            except Exception:self.health['buzzer_error']='Buzzer command unavailable; dashboard alerts remain active'
            self.stop_event.wait(2)

    def ddns_worker(self):
        while not self.stop_event.is_set():
            try:self.ddns.tick();self.health.pop('ddns_worker_error',None)
            except Exception:self.health['ddns_worker_error']='DDNS worker needs attention; profiles and prior results retained'
            self.stop_event.wait(15)

    def worker_alerts(self):
        from .health import fault
        out=[fault(key,'warning','A NAS background worker needs attention',{'worker':key}) for key,value in list(self.health.items()) if key.endswith('_error') and value]
        if not self.health.get('worker_ok',False):out.append(fault('jobs','warning','The NAS job worker needs attention'))
        return out

    def https_alerts(self):
        from .health import fault
        info=self.management_tls.status();out=[]
        if not info.get('configured'):return out
        if not info.get('available'):out.append(fault('endpoint','critical','Configured LAN HTTPS is unavailable; use the SSH tunnel'))
        days=info.get('certificate',{}).get('days_remaining')
        if days is not None and days<30:out.append(fault('certificate','critical' if days<7 else 'warning','LAN HTTPS certificate expires soon',{'days_remaining':days}))
        return out

    def personal_photo_worker(self):
        while not self.stop_event.is_set():
            try:self.personal_cloud.tick()
            except Exception:self.personal_photos.progress(state='needs-attention',message='Photo scheduler needs attention; originals retained')
            self.stop_event.wait(30)
