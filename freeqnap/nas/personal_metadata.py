"""Bounded, unprivileged metadata and JPEG generation; originals remain unchanged."""
import datetime,json,math,os,pwd,shutil,subprocess,tempfile,stat,secrets
from pathlib import Path

TAGS=['DateTimeOriginal','CreateDate','GPSLatitude','GPSLongitude','Make','Model','LensModel','ImageWidth','ImageHeight','Orientation','ContentIdentifier','Duration','Title','Keywords','Description','ImageDescription','Artist','Creator','Copyright','GPSAltitude']
def metadata(raw, fallback=None):
    value={}
    for source,target in [('Make','make'),('Model','camera'),('LensModel','lens'),('ContentIdentifier','live_id'),('Title','title'),('Description','description'),('ImageDescription','description'),('Artist','creator'),('Creator','creator'),('Copyright','copyright')]:
        if isinstance(raw.get(source),str):value[target]=raw[source][:500]
    date=raw.get('DateTimeOriginal') or raw.get('CreateDate') or fallback
    if isinstance(date,str):
        try:
            if len(date)>10 and date[4]==':' and date[7]==':':date=date[:10].replace(':','-')+date[10:]
            parsed=datetime.datetime.fromisoformat(date.replace('Z','+00:00'));value['taken']=parsed.isoformat();value['date_source']='embedded' if raw.get('DateTimeOriginal') or raw.get('CreateDate') else 'icloud'
        except ValueError:pass
    for source,target in [('ImageWidth','width'),('ImageHeight','height'),('Duration','duration')]:
        try:
            v=float(raw[source])
            if math.isfinite(v) and v>=0:value[target]=v
        except (KeyError,TypeError,ValueError):pass
    try:
        lat,lon=float(raw['GPSLatitude']),float(raw['GPSLongitude'])
        if math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180:value.update(latitude=lat,longitude=lon)
    except (KeyError,ValueError,TypeError):pass
    if isinstance(raw.get('Keywords'),list):value['tags']=[str(v)[:100] for v in raw['Keywords'][:64]]
    try:
        altitude=float(raw['GPSAltitude'])
        if math.isfinite(altitude):value['altitude']=altitude
    except (KeyError,TypeError,ValueError):pass
    return value

def managed_decoder():
    return os.geteuid()==0 and bool(os.environ.get('INVOCATION_ID'))

def managed_decode(fd, executable, args, timeout, memory_limit, output_limit=8*1024**2):
    """PID 1 opens read-only stdin and drops UID before applying its syscall guard.

    No original path, shell, network access or write-capable input is delegated.
    Temporary derived output stays in a private directory shared with PID 1.
    """
    base=Path('/var/lib/freeqnap-system/decoder-output');base.mkdir(mode=0o700,parents=True,exist_ok=True)
    info=base.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o700:raise ValueError('Private decoder output directory is unsafe')
    unit='freeqnap-decoder-'+secrets.token_hex(12)
    with tempfile.TemporaryDirectory(dir=base) as folder:
        output=Path(folder)/'output';output.touch(mode=0o600)
        readonly=os.open('/proc/self/fd/'+str(fd),os.O_RDONLY|os.O_CLOEXEC)
        try:
            before=os.fstat(fd);after=os.fstat(readonly)
            if (before.st_dev,before.st_ino)!=(after.st_dev,after.st_ino):raise ValueError('Decoder input identity changed')
            fixed=list(args)
            if '-fd' in fixed:fixed[fixed.index('-fd')+1]='0'
            fixed=[('/proc/self/fd/0' if arg=='/proc/self/fd/'+str(fd) else arg) for arg in fixed]
            properties=['User=nobody','Group=nogroup','NoNewPrivileges=yes','PrivateNetwork=yes','PrivateTmp=yes','PrivateDevices=yes','ProtectSystem=strict','ProtectHome=yes','ProtectKernelTunables=yes','ProtectKernelModules=yes','ProtectControlGroups=yes','RestrictSUIDSGID=yes','RestrictAddressFamilies=AF_UNIX','InaccessiblePaths=-/srv -/etc/freeqnap -/run/freeqnap -/var/backups',
                        'ReadWritePaths='+folder,'StandardInput=file:/proc/'+str(os.getpid())+'/fd/'+str(readonly),'StandardOutput=file:'+str(output),'StandardError=null',
                        'LimitAS='+str(memory_limit),'MemoryMax='+str(memory_limit+32*1024**2),'LimitFSIZE='+str(output_limit),'LimitCPU=30','TasksMax=32','RuntimeMaxSec='+str(timeout),'TimeoutStopSec=2','KillMode=control-group']
            command=['systemd-run','--quiet','--wait','--collect','--unit='+unit]
            for value in properties:command+=['--property='+value]
            try:
                result=subprocess.run(command+['--',executable,*fixed],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=timeout+8,close_fds=True)
            except subprocess.TimeoutExpired:
                subprocess.run(['systemctl','stop',unit],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
                raise ValueError('Media decoder exceeded its time limit') from None
            if result.returncode:raise ValueError('This file could not be decoded by the isolated media helper')
            with output.open('rb') as stream:raw=stream.read(output_limit+1)
            if len(raw)>output_limit:raise ValueError('Decoder output limit exceeded')
            return raw
        finally:os.close(readonly)

def decode(fd, tool, args, timeout=35, memory_limit=768*1024**2, output_limit=8*1024**2):
    executable=shutil.which(tool)
    if not executable:raise ValueError('Install the optional media decoder packages')
    if managed_decoder():return managed_decode(fd,executable,args,timeout,memory_limit,output_limit)
    prefix=[]
    if os.geteuid()==0:
        nobody=pwd.getpwnam('nobody')
        for command in ('unshare','setpriv','prlimit'):
            if not shutil.which(command):raise ValueError('Unprivileged decoder isolation is unavailable')
        prefix=['unshare','--net','--','setpriv','--reuid='+str(nobody.pw_uid),'--regid='+str(nobody.pw_gid),'--clear-groups','--no-new-privs']
    if shutil.which('prlimit'):prefix+=['prlimit','--as='+str(memory_limit),'--cpu=30','--fsize='+str(output_limit),'--']
    # Never inherit an ingestion FD with write permission into a decoder.
    readonly=os.open('/proc/self/fd/'+str(fd),os.O_RDONLY|os.O_CLOEXEC)
    try:
        before=os.fstat(fd);after=os.fstat(readonly)
        if (before.st_dev,before.st_ino)!=(after.st_dev,after.st_ino):raise ValueError('Decoder input identity changed')
        args=list(args)
        if '-fd' in args:args[args.index('-fd')+1]=str(readonly)
        args=[('/proc/self/fd/'+str(readonly)) if arg=='/proc/self/fd/'+str(fd) else arg for arg in args]
        with tempfile.TemporaryFile() as output:
            process=subprocess.Popen(prefix+[executable,*args],stdin=readonly if tool in ('exiftool','pdftotext') else subprocess.DEVNULL,stdout=output,stderr=subprocess.DEVNULL,pass_fds=(readonly,),close_fds=True)
            try:code=process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:process.kill();process.wait();raise ValueError('Photo decoder exceeded its time limit') from None
            if code:raise ValueError('This file could not be decoded')
            output.seek(0);data=output.read(output_limit+1)
            if len(data)>output_limit:raise ValueError('Decoder output limit exceeded')
            return data
    finally:os.close(readonly)

def inspect(fd,fallback=None):
    try:
        data=decode(fd,'exiftool',['-json','-n','-api','LargeFileSupport=1',*['-'+t for t in TAGS],'-'])
        rows=json.loads(data);return metadata(rows[0] if rows else {},fallback)
    except (ValueError,OSError,KeyError,json.JSONDecodeError):return {**metadata({},fallback),'metadata_unavailable':True}

def jpeg(fd,large=False,memory_limit=768*1024**2):
    width=1600 if large else 384
    return decode(fd,'ffmpeg',['-nostdin','-v','error','-threads','1','-protocol_whitelist','fd,pipe','-fd',str(fd),'-i','fd:','-frames:v','1','-vf',fr'scale=min({width}\,iw):-2','-f','image2pipe','-c:v','mjpeg','-q:v','4','pipe:1'],memory_limit=memory_limit)
