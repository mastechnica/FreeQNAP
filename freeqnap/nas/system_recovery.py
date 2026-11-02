"""Private bounded NAS recovery snapshots; never an automatic system restore."""
import hashlib,json,os,platform,re,shutil,sqlite3,stat,time
from pathlib import Path
from .common import name
from ..state import atomic

LIMIT=128*1024**2

class SystemRecovery:
    def __init__(self,ctx,root=Path('/')):self.ctx=ctx;self.root=Path(root)
    def host(self,path):return self.root/path.lstrip('/')
    def capture(self,ident):
        with self.ctx.lock():return self._capture(ident)
    def _capture(self,ident):
        if self.ctx.state.setting('system_stage_deleted:'+str(ident)):raise ValueError('This capture was explicitly removed; start a new system backup')
        if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{32}',ident):raise ValueError('A durable system-backup job ID is required')
        if self.ctx.state.setting('network_pending') or self.ctx.state.setting('vpn_pending'):raise ValueError('Confirm or roll back pending network/VPN changes before recovery capture')
        base=self.ctx.directory/'system-recovery';base.mkdir(mode=0o700,exist_ok=True);stage=base/ident
        if stage.exists():self.verify(stage);return stage
        if len(list(base.iterdir()))>=8:raise ValueError('Eight retained recovery stages need reconciliation before another capture')
        free=os.statvfs(base)
        if free.f_bavail*free.f_frsize<LIMIT+512*1024**2:raise ValueError('Insufficient OS space for the bounded private recovery stage')
        stage.mkdir(mode=0o700)
        for parent in (base,self.ctx.directory):
            fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:os.fsync(fd)
            finally:os.close(fd)
        files={};total=0;excluded=[]
        def copy(path,archive_name,sqlite=False):
            nonlocal total
            if archive_name in files:return
            if len(files)>=20000:raise ValueError('Recovery file-count limit')
            info=path.lstat()
            if not stat.S_ISREG(info.st_mode):raise ValueError('Recovery capture refuses symlinks/special files: '+archive_name)
            if info.st_size>64*1024**2 or total+info.st_size>LIMIT:raise ValueError('Recovery snapshot size limit; private incomplete stage retained')
            output=stage/archive_name;output.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
            if sqlite:
                src=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);dst=sqlite3.connect(output)
                try:
                    src.backup(dst);tables={r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    if 'sessions' in tables:dst.execute('DELETE FROM sessions')
                    if 'settings' in tables:dst.execute("DELETE FROM settings WHERE key IN ('enrollment','oidc_states')")
                    dst.commit()
                    if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Recovery database snapshot failed integrity verification')
                finally:src.close();dst.close()
            else:
                src=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
                try:
                    before=os.fstat(src)
                    if before.st_ino!=info.st_ino or before.st_dev!=info.st_dev:raise ValueError('Recovery source changed')
                    with os.fdopen(os.open(output,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600),'wb') as out:
                        while data:=os.read(src,1024*1024):
                            if out.tell()+len(data)>64*1024**2 or total+out.tell()+len(data)>LIMIT:raise ValueError('Recovery source grew past size limit')
                            out.write(data)
                        out.flush();os.fsync(out.fileno())
                    after=os.fstat(src)
                    if (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):raise ValueError('Recovery source changed during capture')
                finally:os.close(src)
            output.chmod(0o600)
            fd=os.open(output,os.O_RDONLY|os.O_NOFOLLOW)
            try:os.fsync(fd)
            finally:os.close(fd)
            size=output.stat().st_size;total+=size
            if total>LIMIT:raise ValueError('Recovery snapshot exceeds limit')
            files[archive_name]={'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'bytes':size,'original_uid':info.st_uid,'original_gid':info.st_gid,'original_mode':stat.S_IMODE(info.st_mode),'sqlite_consistent':sqlite}
        # Only selected state/configuration, never arbitrary user paths or logs.
        copy(self.ctx.state.database,'state/nas/state.sqlite3',True)
        # Console authentication lives in a separate service-owned directory.
        # Keep the broker's write boundary intact; recovery creates a fresh admin.
        for directory in ('secrets','headers','network','vpn'):
            source=self.ctx.directory/directory
            if source.exists():
                for file in sorted(source.rglob('*')):
                    if file.is_symlink():raise ValueError('Unexpected symlink in private recovery source')
                    if file.is_file():copy(file,'state/nas/'+directory+'/'+str(file.relative_to(source)))
        token=self.ctx.directory/'downloads-rpc-token'
        if token.exists():copy(token,'state/nas/downloads-rpc-token')
        required=self.host('/etc/freeqnap-install-id')
        if not required.is_file():raise ValueError('Installation identity is required for system recovery capture')
        fixed=['/etc/freeqnap-install-id','/etc/fstab','/etc/hostname','/etc/hosts','/etc/passwd','/etc/group','/etc/shadow','/etc/gshadow','/etc/mdadm/mdadm.conf','/etc/systemd/system.conf.d/80-freeqnap-watchdog.conf','/etc/sysctl.d/90-freeqnap-hardening.conf']
        for file in fixed:
            source=self.host(file)
            if source.exists():copy(source,'system'+file)
        for parent,patterns in [('/etc/ssh',['ssh_host_*','sshd_config','sshd_config.d']),('/etc/systemd/network',['*freeqnap*']),('/etc/systemd/system',['freeqnap-*','eyeq-*','systemd-networkd.service.d','systemd-networkd-wait-online.service.d']),('/etc/modules-load.d',['freeqnap-*'])]:
            for pattern in patterns:
                for source in sorted(self.host(parent).glob(pattern)):
                    if source.is_symlink():raise ValueError('Unexpected config symlink: '+str(source))
                    if source.is_dir():
                        for item in sorted(source.rglob('*')):
                            if item.is_file() or item.is_symlink():copy(item,'system/'+str(item.relative_to(self.root)))
                    else:copy(source,'system/'+str(source.relative_to(self.root)))
        for parent in ('/etc/freeqnap','/etc/freeqnap-https','/etc/freeqnap-dhcp','/usr/local/share/eyeq','/etc/samba','/etc/chrony'):
            source=self.host(parent)
            if source.exists():
                if source.is_symlink():raise ValueError('Recovery configuration root cannot be a symlink')
                for item in sorted(source.rglob('*')):
                    if item.is_file() or item.is_symlink():copy(item,'system/'+str(item.relative_to(self.root)))
        # Samba credentials require tdbbackup's consistent read, never a raw live TDB copy.
        for path in sorted(self.host('/var/lib/samba').rglob('*.tdb')):
            if not shutil.which('tdbbackup'):raise ValueError('Install tdb-tools to snapshot Samba credentials consistently')
            suffix='.freeqnap-'+ident;temporary=Path(str(path)+suffix)
            try:
                self.ctx.run('tdbbackup','-s',suffix,str(path));copy(temporary,'system/'+str(path.relative_to(self.root)))
            finally:temporary.unlink(missing_ok=True)
        app=self.host('/opt/freeqnap/current')
        if app.exists():
            app=app.resolve()
            if self.root==Path('/') and not app.is_relative_to('/opt/freeqnap/releases'):raise ValueError('Unexpected application generation path')
            for folder in ('freeqnap','web','docs'):
                for item in sorted((app/folder).rglob('*')):
                    if '__pycache__' in item.parts or item.suffix=='.pyc':continue
                    if item.is_file() or item.is_symlink():copy(item,'application/'+folder+'/'+str(item.relative_to(app/folder)))
        kernel=platform.release();modules=self.host('/lib/modules/'+kernel+'/updates/freeqnap')
        if modules.exists():
            for file in sorted(modules.glob('*.ko')):copy(file,'system/lib/modules/'+kernel+'/updates/freeqnap/'+file.name)
        for binary in ('/usr/lib/systemd/system-shutdown/eyeq-poweroff','/usr/local/libexec/freeqnap-apfs-fuse'):
            file=self.host(binary)
            if file.exists():copy(file,'system'+binary)
        for directory in sorted([p for p in stage.rglob('*') if p.is_dir()],key=lambda p:len(p.parts),reverse=True):
            fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:os.fsync(fd)
            finally:os.close(fd)
        manifest={'format':'freeqnap-system-recovery-v1','created_at':time.time(),'installation_id':required.read_text().strip(),'kernel':kernel,'files':files,'total_bytes':total,'sessions_and_enrollment_excluded':True,'console_login_database_included':False,'fresh_console_administrator_required':True,'root_authorized_keys_included':False,'contains_credentials_and_private_keys':True,'automatic_restore_supported':False,'identity_files_require_rebinding':['system/etc/freeqnap-install-id','system/etc/mdadm/mdadm.conf','system/etc/fstab','system/etc/ssh'],'os_disk_image_included':False,'flash_image_included':False,'review':'Restore privately to staging. Never copy these databases live or publish this bundle as a file share. Reconcile jobs, schedules, device identities, accounts and export policies before activation.'}
        atomic(stage/'manifest.json',manifest)
        self.verify(stage);return stage
    def verify(self,stage):
        stage=Path(stage);m=json.loads((stage/'manifest.json').read_text())
        if m.get('format')!='freeqnap-system-recovery-v1':raise ValueError('Incomplete/unrecognized recovery snapshot retained; reconcile before retry')
        for relative,info in m['files'].items():
            if Path(relative).is_absolute() or '..' in Path(relative).parts:raise ValueError('Unsafe recovery manifest')
            file=stage/relative
            if file.is_symlink() or not file.is_file() or file.stat().st_size!=info['bytes'] or hashlib.sha256(file.read_bytes()).hexdigest()!=info['sha256']:raise ValueError('Private recovery stage changed; reconcile before retry')
        return m
    def backup(self,request,operation,backups):
        entry=backups.get(name(request.get('repository')));stage=self.capture(operation);manifest=self.verify(stage)
        result=backups.command(entry,'backup','--quiet','--tag','freeqnap-system','--',str(stage));rows=[json.loads(v) for v in result.splitlines() if v.strip()];summary=next((v for v in reversed(rows) if v.get('message_type')=='summary'),None)
        if not summary or not re.fullmatch('[a-f0-9]{64}',summary.get('snapshot_id','')):raise ValueError('No unambiguous successful recovery snapshot; private stage retained')
        backups.command(entry,'check',timeout=3600);self.verify(stage)
        record={'repository':entry['name'],'snapshot_id':summary['snapshot_id'],'captured_at':manifest['created_at'],'files':len(manifest['files']),'bytes':manifest['total_bytes'],'encrypted_in_repository':True,'full_disaster_restore_tested':False,'private_stage':str(stage)}
        try:
            shutil.rmtree(stage);record.pop('private_stage');record['private_stage_removed']=True
        except OSError:record['private_stage_removed']=False;record['warning']='Encrypted backup succeeded; private capture stage cleanup needs review'
        self.ctx.state.set('system_backup:'+operation,record)
        return record

    def stages(self,request=None):
        rows=[]
        for path in sorted((self.ctx.directory/'system-recovery').glob('*')):
            if not path.is_dir() or not re.fullmatch('[a-f0-9]{32}',path.name):continue
            with self.ctx.state.connect() as db:job=db.execute('SELECT status FROM jobs WHERE id=?',(path.name,)).fetchone()
            rows.append({'id':path.name,'status':job['status'] if job else 'unknown','complete_manifest':(path/'manifest.json').is_file(),'contains_private_configuration':True})
        return {'items':rows,'maximum_retained_stages':8}
    def stage_plan(self,request):
        ident=request.get('id');path=self.stage_info(ident);info=path.stat()
        return self.ctx.plan('system-stage-delete',{'id':ident,'identity':[info.st_dev,info.st_ino,info.st_mtime_ns],'review':'Remove only this failed private recovery capture. Encrypted repository snapshots, original live configuration and job history are retained. A subsequent backup requires a new job/capture.'},'DELETE PRIVATE RECOVERY STAGE '+ident)
    def stage_info(self,ident):
        if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{32}',ident):raise ValueError('Choose a private recovery stage')
        with self.ctx.state.connect() as db:job=db.execute("SELECT kind,status FROM jobs WHERE id=?",(ident,)).fetchone()
        successful=self.ctx.state.setting('system_backup:'+ident,{}) or self.ctx.state.setting('local_system_backup:'+ident,{})
        if not job or job['kind'] not in ('backup.system-run','system-local-capture') or not (job['status']=='retryable' or (job['status']=='succeeded' and (successful.get('snapshot_id') or successful.get('sha256')) and not successful.get('private_stage_removed'))):raise ValueError('Only failed inactive or already-backed-up private captures can be removed')
        path=self.ctx.directory/'system-recovery'/ident
        if path.is_symlink() or not path.is_dir():raise ValueError('Private stage is missing or changed')
        return path
    def stage_remove(self,request):
        with self.ctx.lock():
            planpath,plan=self.ctx.reviewed(request,'system-stage-delete');b=plan['body'];path=self.stage_info(b['id']);info=path.stat()
            if [info.st_dev,info.st_ino,info.st_mtime_ns]!=b['identity']:raise ValueError('Private recovery stage changed')
            self.ctx.consume(planpath,plan);shutil.rmtree(path)
            self.ctx.state.set('system_stage_deleted:'+b['id'],{'deleted_at':time.time()})
        return {'private_stage_removed':b['id'],'encrypted_snapshots_kept':True}
