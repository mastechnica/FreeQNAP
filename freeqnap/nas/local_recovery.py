"""Password-encrypted local recovery downloads, without saved export passwords."""
import base64,hashlib,json,os,re,secrets,shutil,stat,subprocess,tarfile,tempfile,time
from pathlib import Path
from .common import secret
from .system_recovery import LIMIT

class LocalRecovery:
    def __init__(self,ctx,recovery):self.ctx=ctx;self.recovery=recovery

    def crypt(self,source,destination,password,decrypt=False):
        # Passphrase travels through an inherited pipe, never argv/environment/state.
        read,write=os.pipe()
        try:
            os.write(write,password+b'\n');os.close(write);write=None
            with tempfile.TemporaryDirectory(prefix='recovery-gpg-',dir=self.ctx.directory) as home:
                args=['gpg','--no-options','--homedir',home,'--batch','--no-tty','--pinentry-mode','loopback','--no-symkey-cache','--passphrase-fd',str(read)]
                args+=['--decrypt'] if decrypt else ['--symmetric','--cipher-algo','AES256','--s2k-mode','3','--s2k-digest-algo','SHA512','--s2k-count','65011712']
                result=subprocess.run(args,stdin=source,stdout=destination,stderr=subprocess.PIPE,pass_fds=(read,),timeout=180)
                if result.returncode:raise ValueError('Recovery encryption/password verification failed; accepted backups were retained')
        finally:
            os.close(read)
            if write is not None:os.close(write)

    def verify_tar(self,stream):
        total=0;members={};manifest=None
        with tarfile.open(fileobj=stream,mode='r:gz') as archive:
            for member in archive:
                if not member.isfile() or member.name in members or Path(member.name).is_absolute() or '..' in Path(member.name).parts or not 0<=member.size<=64*1024**2 or len(members)>=20001:raise ValueError('Unsafe recovery archive')
                total+=member.size
                if total>LIMIT+8*1024**2:raise ValueError('Recovery archive exceeds limit')
                data=archive.extractfile(member).read();members[member.name]=hashlib.sha256(data).hexdigest()
                if member.name=='manifest.json':manifest=json.loads(data)
        if not manifest or manifest.get('format')!='freeqnap-system-recovery-v1' or set(members)!=set(manifest.get('files',{}))|{'manifest.json'}:raise ValueError('Incomplete recovery manifest')
        if any(members[k]!=v['sha256'] for k,v in manifest['files'].items()):raise ValueError('Recovery member checksum mismatch')
        return manifest

    def create(self,request):
        if set(request)!={'secret'} or set(request['secret'])!={'password'}:raise ValueError('Choose an export password; server key paths are not accepted')
        password=secret(request['secret'])
        if not shutil.which('gpg'):raise ValueError('Install GnuPG for encrypted recovery exports')
        # Insert an already-running operation atomically; workers never see its password.
        ident=secrets.token_hex(16);now=time.time()
        with self.ctx.state.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT count(*) FROM jobs WHERE kind='system-local-capture' AND status='running'").fetchone()[0]:raise ValueError('A local recovery capture is already running')
            if db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]>=128:raise ValueError('Active job capacity reached; previous backups retained')
            db.execute('INSERT INTO jobs(id,kind,payload,status,created,updated,attempts) VALUES(?,?,?,?,?,?,?)',(ident,'system-local-capture','{}','running',now,now,1))
        try:
            directory=self.ctx.directory/'local-recovery';directory.mkdir(mode=0o700,exist_ok=True)
            if len(list(directory.iterdir()))>=8:raise ValueError('Eight retained archives/partials need review; no accepted backup was deleted')
            stage=self.recovery.capture(ident);manifest=self.recovery.verify(stage)
            free=os.statvfs(directory)
            if free.f_bavail*free.f_frsize<3*LIMIT+512*1024**2:raise ValueError('Insufficient space for bounded encrypted archive verification')
            target=directory/('freeqnap-recovery-'+ident+'.tar.gz.gpg');partial=target.with_suffix('.gpg.partial')
            # TemporaryFile is unlinked immediately on Unix. No named plaintext archive.
            with tempfile.TemporaryFile(dir=self.ctx.directory) as plain:
                with tarfile.open(fileobj=plain,mode='w:gz',format=tarfile.PAX_FORMAT) as archive:
                    for item in sorted(stage.rglob('*')):
                        if item.is_symlink():raise ValueError('Recovery stage changed')
                        if item.is_file():
                            info=archive.gettarinfo(str(item),str(item.relative_to(stage)));info.uid=info.gid=0;info.uname=info.gname='root';info.mode=0o600;info.pax_headers={}
                            with item.open('rb') as source:archive.addfile(info,source)
                self.recovery.verify(stage);plain.seek(0)
                with partial.open('xb') as encrypted:
                    os.fchmod(encrypted.fileno(),0o600);self.crypt(plain,encrypted,password);encrypted.flush();os.fsync(encrypted.fileno())
            with partial.open('rb') as encrypted,tempfile.TemporaryFile(dir=self.ctx.directory) as verified:
                self.crypt(encrypted,verified,password,True);verified.seek(0);self.verify_tar(verified)
            checksum=hashlib.sha256(partial.read_bytes()).hexdigest();os.replace(partial,target)
            fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:os.fsync(fd)
            finally:os.close(fd)
            info=target.stat();record={'id':ident,'filename':target.name,'created_at':manifest['created_at'],'sha256':checksum,'bytes':info.st_size,'files':len(manifest['files']),'encrypted':True,'encryption':'OpenPGP AES256 + integrity protection','password_saved':False,'independent_backup':False,'identity':[info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns]}
            self.ctx.state.set('local_system_backup:'+ident,record)
            try:shutil.rmtree(stage)
            except OSError:record['warning']='Encrypted archive verified; private capture stage cleanup needs review';self.ctx.state.set('local_system_backup:'+ident,record)
            self.ctx.state.finish(ident,result=record);return record
        except Exception:
            self.ctx.state.finish(ident,error='Encrypted configuration capture failed; accepted archives retained. Inspect private stages before a new attempt.');raise
        finally:password=None

    def info(self,ident):
        if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{32}',ident):raise ValueError('Choose a local recovery archive')
        record=self.ctx.state.setting('local_system_backup:'+ident)
        if not record:raise ValueError('Unknown accepted recovery archive')
        path=self.ctx.directory/'local-recovery'/record['filename'];info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns]!=record['identity']:raise ValueError('Local recovery archive changed')
        return path,record

    def list(self,request=None):
        with self.ctx.state.connect() as db:rows=db.execute("SELECT value FROM settings WHERE key LIKE 'local_system_backup:%'").fetchall()
        items=[]
        for row in rows:
            record=json.loads(row['value'])
            try:self.info(record['id']);record['available']=True
            except (OSError,ValueError):record['available']=False
            items.append(record)
        return {'items':sorted(items,key=lambda r:r['created_at'],reverse=True),'maximum_archives':8,'independent_backup':False}

    def read(self,request):
        path,record=self.info(request.get('id'));offset=request.get('offset',0);count=request.get('count',512*1024)
        if isinstance(offset,bool) or not isinstance(offset,int) or offset<0 or isinstance(count,bool) or not isinstance(count,int) or not 1<=count<=512*1024:raise ValueError('Invalid recovery download range')
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        try:
            info=os.fstat(fd)
            if [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns]!=record['identity']:raise ValueError('Local recovery archive changed')
            data=os.pread(fd,count,offset)
        finally:os.close(fd)
        return {'data_base64':base64.b64encode(data).decode(),'offset':offset,'total_bytes':record['bytes'],'etag':record['sha256'],'filename':record['filename']}
