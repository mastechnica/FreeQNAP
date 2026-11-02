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
        self.metrics = Metrics(self.ctx)
        self.status_light = StatusLight(self.ctx)
        self.disk_reports = DiskReports(self.ctx)
        self.cooling = Cooling()
        self.alert_rules = AlertRules(self.ctx)
        self.storage = Storage(self.ctx)
        self.management_tls = ManagementTLS(self.ctx)
        self.sharing = Sharing(self.ctx)
        self.backups = FileBackups(self.ctx)
        self.backup_schedules = BackupSchedules(self.ctx)
        self.system_recovery = SystemRecovery(self.ctx)
        self.local_recovery = LocalRecovery(self.ctx,self.system_recovery)
        self.files = FileManager(self.ctx)
        self.bundles = Bundles(self.ctx,self.files)
        self.archives = Archives(self.ctx,self.files,self.bundles)
        self.media = Media(self.ctx)
        self.personal_photos=PersonalPhotos(self.ctx)
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
        config = self.ctx.config()
        pools = [];arrays={}
        for pool in config['pools'].values():
            value = {**pool, 'mounted': False, 'locked': pool['encrypted']}
            try:
                _, mount = self.ctx.volume(pool['name'])
                space = os.statvfs(mount)
                value.update(mounted=True, locked=False, available_bytes=space.f_bavail * space.f_frsize,
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
        direct = {
            'nas.status': lambda _: self.status(),
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
            'files.list': self.files.list, 'files.read': self.files.read, 'files.mkdir': self.files.mkdir,
            'files.upload-begin': self.files.upload_begin, 'files.upload-chunk': self.files.upload_chunk,
            'files.upload-finish': self.files.upload_finish, 'files.move-plan': self.files.move_plan,
            'files.move': self.files.move, 'files.transfer-plan': self.files.transfer_plan,
            'files.stages':self.files.stages,'files.stage-plan':self.files.stage_plan,'files.stage-remove':self.files.stage_remove,
            'files.delete-plan': self.files.delete_plan, 'files.trash': self.files.trash_items, 'files.recycle-policy': self.files.policy_apply, 'files.recycle-policy-plan':self.files.policy_plan, 'files.recycle-plan':self.files.recycle_plan,
            'files.purge-plan': self.files.purge_plan, 'files.purge': self.files.purge,
            'recovery.list': self.recovery.list, 'recovery.plan': self.recovery.plan, 'recovery.apply': self.recovery.apply,
            'photos.status':lambda r:self.personal_photos.status(r), 'photos.configure':self.personal_photos.configure,
            'photos.related':self.personal_photos.related, 'photos.catalog':self.personal_photos.catalog, 'photos.places':self.personal_photos.places,
            'photos.read':self.personal_photos.read, 'photos.annotate':self.personal_photos.annotate,
            'photos.album-create':self.personal_photos.album, 'photos.album-add':self.personal_photos.album_add,
            'photos.import-folder':self.personal_photos.import_folder, 'photos.pause':self.personal_cloud.pause,
            'photos.icloud-status':self.personal_cloud.status, 'photos.icloud-save':self.personal_cloud.save,
            'photos.icloud-login':self.personal_cloud.login, 'photos.icloud-code':self.personal_cloud.code,
            'photos.icloud-run':self.personal_cloud.run,
            'media.save': lambda r: self.save_library(r), 'media.catalog': self.media.catalog,
            'media.provider-status':self.media.provider_status, 'media.provider-save':self.media.provider_save, 'media.scanner-settings':self.media.scanner_settings, 'media.scanner-status':self.media.scanner_status, 'media.artwork':self.media.artwork, 'media.lookup': self.media.lookup, 'media.metadata': self.media.apply_metadata,
            'jobs.retry': self.retry, 'system.plan': self.system_plan, 'system.apply': self.system_apply,
        }
        if not isinstance(request, dict):raise ValueError('JSON object required')
        if action in direct:return direct[action](request)
        if action in ('backup.system-run','backup.run', 'backup.check', 'backup.restore', 'media.scan','files.transfer','files.delete','files.recycle','files.archive'):
            # Queue payloads contain only references, never credentials/unlock material.
            schema = {'backup.system-run':{'repository'},'files.archive':{'plan_id','digest','confirmation'},'backup.run': {'repository','shares','same_pool_confirmation'}, 'backup.check': {'repository','read_data'}, 'backup.restore': {'repository','snapshot','pool','include'}, 'media.scan': {'library'},'files.transfer':{'plan_id','digest','confirmation'},'files.delete':{'plan_id','digest','confirmation'},'files.recycle':{'plan_id','digest','confirmation'}}
            if set(request) - schema[action]:
                raise ValueError('Credentials cannot be saved in a job')
            return {'job_id': self.ctx.state.enqueue(action, request)}
        raise ValueError('Unknown or unsupported NAS operation')

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
        request = json.loads(job['payload'])
        actions = {
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
