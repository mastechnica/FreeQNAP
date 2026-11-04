"""Explicit read-only sessions for foreign encrypted USB media, never data pools."""
import base64,contextlib,hashlib,json,os,re,secrets,shutil,stat,time
from pathlib import Path
from .files import Files,relative
from .common import canonical
from .storage import walk
from .limits import require_ext4_size
from ..state import atomic

FORMATS={'crypto_LUKS':'luks','BitLocker':'bitlk','apfs':'apfs','ntfs':'ntfs','exfat':'exfat','vfat':'vfat'}

def unlock_secret(value):
    if not isinstance(value,dict):raise ValueError('Enter the existing disk password or upload a key')
    if set(value)=={'password'}:
        text=value['password']
        if not isinstance(text,str) or not 1<=len(text.encode())<=4096 or any(ord(c)<32 for c in text):raise ValueError('Existing passwords must be 1–4096 bytes without control characters')
        return text.encode()
    if set(value)=={'key_base64'}:
        try:data=base64.b64decode(value['key_base64'],validate=True)
        except (ValueError,TypeError):raise ValueError('Invalid key file')
        if not 1<=len(data)<=4096:raise ValueError('Key files must be 1–4096 bytes')
        return data
    raise ValueError('Choose a password or uploaded key; server file paths are never accepted')

class Foreign:
    def __init__(self,ctx,external):self.ctx=ctx;self.external=external
    def prepare_target(self,target):
        # ntfs-3g enables allow_other by default. Keep the parent root-private
        # even when the mounted filesystem presents permissive root modes.
        base=target.parent;base.mkdir(mode=0o700,parents=True,exist_ok=True)
        fd=os.open(base,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            if os.fstat(fd).st_uid!=os.geteuid():raise ValueError('Foreign mount parent has unexpected ownership')
            os.fchmod(fd,0o700);os.mkdir(target.name,mode=0o700,dir_fd=fd);os.fsync(fd)
        finally:os.close(fd)
    def capabilities(self,request=None):
        fuse=Path('/dev/fuse').exists();apfs=Path('/usr/local/libexec/freeqnap-apfs-fuse').is_file();crypt=bool(shutil.which('cryptsetup'));ntfs=bool(shutil.which('ntfs-3g'))
        return {'formats':[
            {'format':'LUKS1 / LUKS2','available':crypt,'access':'read-only import; ext4, NTFS, exFAT or FAT inner filesystem','physical_acceptance':False},
            {'format':'BitLocker / BitLocker To Go','available':crypt and fuse and ntfs and Path('/sys/module/dm_zero').exists(),'access':'password or recovery password; read-only NTFS','physical_acceptance':False,'limits':'TPM-only, damaged/unsupported protectors and incomplete encryption can be unavailable'},
            {'format':'FileVault APFS','available':fuse and apfs,'access':'experimental read-only software-encrypted APFS, password or personal recovery key','physical_acceptance':False,'limits':'Hardware-bound T2/Apple silicon encryption is unsupported; not every APFS feature/variant is supported'}],
            'sessions':self.sessions(),'automatic_unlock':False,'passwords_saved':False,'universal_format_support':False}
    def source(self,request):
        row=self.external.select(request.get('id'));path=request.get('source');items=[r for r in walk(row['disk']) if r.get('path')==path and r.get('fstype') in FORMATS]
        if len(items)!=1:raise ValueError('Choose one detected LUKS, BitLocker or APFS partition')
        item=items[0]
        if not (path==row['disk']['path'] or re.fullmatch(re.escape(row['disk']['path'])+('p' if row['disk']['path'][-1].isdigit() else '')+r'[0-9]+',path)):raise ValueError('Only a direct USB disk/partition is accepted')
        if not (item.get('uuid') or item.get('partuuid')):raise ValueError('A persistent volume/partition identity is required')
        # Reject this volume if it is already mounted, mapped, registered or swapped.
        if any(item.get('mountpoints') or []) or item.get('children'):raise ValueError('Selected USB partition is already active')
        holders=Path('/sys/class/block')/Path(path).name/'holders'
        if holders.exists() and any(holders.iterdir()):raise ValueError('Selected USB partition has active holders')
        if path in self.ctx.run('swapon','--show','--noheadings','--raw','--output','NAME').splitlines():raise ValueError('Selected USB partition is active swap')
        for pool in self.ctx.config()['pools'].values():
            if pool.get('kind')=='usb' and pool['external']['id']==row['id'] and (pool['external'].get('device_path')==path or item.get('uuid') in [pool.get('luks_uuid'),pool.get('filesystem_uuid')]):raise ValueError('Use the registered volume unlock instead')
        for session in self.sessions():
            if session['source']==path and session['active']:raise ValueError('This USB volume already has an unlocked session')
        return row,item
    def plan(self,request):
        row,item=self.source(request);volume=request.get('volume_index',0)
        if isinstance(volume,bool) or not isinstance(volume,int) or not 0<=volume<=255:raise ValueError('APFS volume index must be 0–255')
        body={'id':row['id'],'source':item['path'],'disk_identity':row,'item':item,'format':FORMATS[item['fstype']],'volume_index':volume,'review':'Read-only mount/unlock only. No formatting, filesystem repair, journal replay, automatic shares or saved password. Unsupported inner filesystems/protectors are rejected. Existing short disk passwords are accepted; new-volume password policy is unchanged.'}
        return self.ctx.plan('foreign-unlock',body,'MOUNT USB READ ONLY' if item['fstype'] in ('ntfs','exfat','vfat') else 'UNLOCK USB READ ONLY')
    def unlock(self,request):
        with self.ctx.lock():
            plan_path,plan=self.ctx.reviewed(request,'foreign-unlock');b=plan['body'];row,item=self.source(b)
            if row!=b['disk_identity'] or item!=b['item']:raise ValueError('USB identity/attachment changed since review')
            plain=b['format'] in ('ntfs','exfat','vfat');password=b'' if plain else unlock_secret(request.get('secret'));ident=secrets.token_hex(16);mapping='freeqnap-foreign-'+ident;target=Path('/srv/freeqnap/foreign')/ident;unit='freeqnap-foreign-'+ident+'.service';opened=False
            self.ctx.consume(plan_path,plan);self.prepare_target(target);record={'id':ident,'source':b['source'],'external_id':b['id'],'disk_identity':row,'item':item,'format':b['format'],'mountpoint':str(target),'created_at':time.time(),'read_only':True,'unit':unit,'mapping':mapping if b['format'] not in ('apfs','ntfs','exfat','vfat') else None,'status':'opening'}
            atomic(self.ctx.directory/'foreign'/ (ident+'.json'),record)
            try:
                if plain:
                    kind=b['format'];options='ro,nodev,nosuid,noexec'
                    if kind=='ntfs':
                        if not shutil.which('ntfs-3g') or not Path('/dev/fuse').exists():raise ValueError('NTFS needs ntfs-3g and the FUSE module')
                        kind='ntfs-3g';options+=',norecover'
                    self.ctx.run('systemd-mount','--collect','--type='+kind,'--options='+options,b['source'],str(target),timeout=90)
                elif b['format']=='apfs':
                    if not Path('/usr/local/libexec/freeqnap-apfs-fuse').is_file() or not Path('/dev/fuse').exists():raise ValueError('Install the reviewed APFS reader and matching FUSE module first')
                    if 'password' not in request['secret']:raise ValueError('APFS expects a password or personal recovery key in the password field')
                    # FUSE checks the mounter's group as well as UID. Match the broker's
                    # primary group; do not use allow_other to bypass its access boundary.
                    # Password never appears in argv, environment, persistent state or journal.
                    runtime=Path('/run/freeqnap-foreign');runtime.mkdir(mode=0o700,exist_ok=True);runtime.chmod(0o700)
                    fs=json.loads(self.ctx.run('findmnt','-J','-T',str(runtime),'-o','FSTYPE'))['filesystems']
                    if len(fs)!=1 or fs[0]['fstype']!='tmpfs':raise ValueError('APFS password handoff requires volatile /run tmpfs')
                    config=runtime/(ident+'.json');secret=runtime/(ident+'.secret');atomic(config,{'source':b['source'],'mountpoint':str(target),'volume_index':b['volume_index']})
                    fd=os.open(secret,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                    try:
                        with os.fdopen(fd,'wb') as stream:stream.write(password)
                        self.ctx.run('systemd-run','--quiet','--collect','--unit='+unit,'--property=Type=forking','--property=Group='+str(os.getegid()),'--property=TimeoutStartSec=120','--property=StandardOutput=null','--property=StandardError=null','--property=NoNewPrivileges=yes','--working-directory=/opt/freeqnap/current','/usr/bin/python3','-B','-m','freeqnap.nas.foreign_worker',str(config),timeout=130)
                    finally:secret.unlink(missing_ok=True);config.unlink(missing_ok=True)
                else:
                    args=['cryptsetup','open','--type',b['format'],'--readonly','--tries','1']
                    if b['format']=='bitlk' and 'password' in request['secret']:password+=b'\n'
                    else:args+=['--key-file','-']
                    if b['format']=='luks':args+=['--disable-external-tokens']
                    self.ctx.run(*args,b['source'],mapping,data=password,timeout=120);opened=True;record['mapping']=mapping;device='/dev/mapper/'+mapping
                    if self.ctx.run('blockdev','--getro',device).strip()!='1':raise ValueError('Unlocked mapping is not read-only')
                    kind=self.ctx.run('blkid','-s','TYPE','-o','value',device).strip();record['inner_filesystem']=kind
                    options='ro,nodev,nosuid,noexec'
                    if kind=='ext4':require_ext4_size(item['size']);kind='ext4';options+=',noload'
                    elif kind=='ntfs':
                        if not shutil.which('ntfs-3g') or not Path('/dev/fuse').exists():raise ValueError('NTFS needs ntfs-3g and the matching FUSE module')
                        kind='ntfs-3g';options+=',norecover'
                    elif kind not in ('exfat','vfat'):raise ValueError('Unsupported inner filesystem; no repair/format is attempted')
                    self.ctx.run('systemd-mount','--collect','--type='+kind,'--options='+options,device,str(target),timeout=90)
                self.validate(record);record['status']='mounted';atomic(self.ctx.directory/'foreign'/(ident+'.json'),record)
                return {'unlocked':True,'session':ident,'read_only':True,'password_saved':False}
            except Exception:
                # Unmount only the mount created for this new private session.
                try:
                    if os.path.ismount(target):self.ctx.run('systemd-mount','--umount',str(target),timeout=90)
                    if b['format']=='apfs':self.ctx.run('systemctl','stop',unit,timeout=90)
                    if opened:self.ctx.run('cryptsetup','close',mapping)
                except (ValueError,OSError):pass
                raise
            finally:password=None
    def record(self,ident):
        if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{32}',ident):raise ValueError('Choose an unlocked USB session')
        return json.loads((self.ctx.directory/'foreign'/(ident+'.json')).read_text())
    def validate(self,record):
        row=self.external.select(record['external_id']);old=record['disk_identity']
        for k in ('id','identity','bytes','disk_sequence'):
            if row['usb'].get(k)!=old['usb'].get(k):raise ValueError('USB attachment changed; unlock again')
        rows=json.loads(self.ctx.run('findmnt','-J','-M',record['mountpoint'],'-o','TARGET,SOURCE,FSTYPE,FSROOT,OPTIONS'))['filesystems'];rows=list({json.dumps(r,sort_keys=True):r for r in rows}.values())
        if len(rows)!=1 or rows[0].get('target')!=record['mountpoint'] or rows[0].get('fsroot')!='/' or not {'ro','nodev','nosuid','noexec'}<=set(rows[0]['options'].split(',')):raise ValueError('USB session mount is missing or not safely read-only')
        current=[r for r in walk(row['disk']) if r.get('path')==record['source']]
        if len(current)!=1 or any(current[0].get(k)!=record['item'].get(k) for k in ('uuid','partuuid','size','fstype')):raise ValueError('USB partition identity changed')
        source='/dev/mapper/'+record['mapping'] if record['mapping'] else record['source']
        expected=os.stat(source);actual=os.stat(rows[0]['source'])
        if not stat.S_ISBLK(expected.st_mode) or not stat.S_ISBLK(actual.st_mode) or expected.st_rdev!=actual.st_rdev:raise ValueError('USB session mounted source changed')
        if record['mapping'] and self.ctx.run('blockdev','--getro',source).strip()!='1':raise ValueError('Decrypted mapping became writable')
        return record
    def sessions(self):
        rows=[]
        for path in sorted((self.ctx.directory/'foreign').glob('*.json')):
            try:
                record=json.loads(path.read_text());active=os.path.ismount(record['mountpoint'])
                if active:
                    try:self.validate(record)
                    except (OSError,ValueError,KeyError):active=False
            except (OSError,ValueError,KeyError):continue
            rows.append({k:record[k] for k in ('id','source','format','mountpoint','created_at')}|{'active':active,'read_only':True,'mapping_open':bool(record.get('mapping') and Path('/dev/mapper/'+record['mapping']).exists())})
        return rows[-64:]
    def lock(self,request):
        with self.ctx.lock():
            record=self.record(request.get('session'))
            if os.path.ismount(record['mountpoint']):
                self.validate(record);self.ctx.run('systemd-mount','--umount',record['mountpoint'],timeout=90)
            if record['mapping'] and Path('/dev/mapper/'+record['mapping']).exists():self.ctx.run('cryptsetup','close',record['mapping'])
            elif not record['mapping']:
                units=self.ctx.run('systemctl','list-units','--all','--no-legend','--plain',record['unit'])
                if any(line.split() and line.split()[0]==record['unit'] for line in units.splitlines()):self.ctx.run('systemctl','stop',record['unit'],timeout=90)
            return {'locked':True}
    def file_view(self,session):
        record=self.validate(self.record(session));owner=self
        class View(Files):
            @contextlib.contextmanager
            def directory(self,share_id,path=''):
                owner.validate(record);mount=Path(record['mountpoint'])/('root' if record['format']=='apfs' else '');fd=os.open(mount,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                try:
                    device=os.fstat(fd).st_dev
                    if device!=mount.stat().st_dev:raise ValueError('USB session mount changed')
                    for component in relative(path):
                        child=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=child
                        if os.fstat(fd).st_dev!=device:raise ValueError('Nested mounted filesystems are not followed')
                    owner.validate(record);pool={'name':'foreign:'+record['id'],'mountpoint':str(mount),'read_only':True,'filesystem_uuid':str(record.get('item',{}).get('uuid') or record.get('item',{}).get('partuuid') or 'session:'+record['id'])+':'+str(record.get('volume_index',0))};yield fd,{'name':'foreign:'+record['id'],'path':str(mount),'gid':os.getegid(),'pool':pool['name'],'read_only':True},pool
                finally:os.close(fd)
        return View(self.ctx)
    def files(self,request,read=False):
        fs=self.file_view(request.get('session'));payload={**request,'share':'foreign'}
        return fs.read(payload) if read else fs.list(payload)
