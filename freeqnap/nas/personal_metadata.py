"""Bounded, unprivileged metadata and JPEG generation; originals remain unchanged."""
import datetime,json,math,os,pwd,shutil,subprocess,tempfile

TAGS=['DateTimeOriginal','CreateDate','GPSLatitude','GPSLongitude','Make','Model','LensModel','ImageWidth','ImageHeight','Orientation','ContentIdentifier','Duration','Title','Keywords']
def metadata(raw, fallback=None):
    value={}
    for source,target in [('Make','make'),('Model','camera'),('LensModel','lens'),('ContentIdentifier','live_id'),('Title','title')]:
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
    return value

def decode(fd, tool, args, timeout=35):
    executable=shutil.which(tool)
    if not executable:raise ValueError('Install the optional photo decoder packages')
    prefix=[]
    if os.geteuid()==0:
        nobody=pwd.getpwnam('nobody')
        for command in ('unshare','setpriv','prlimit'):
            if not shutil.which(command):raise ValueError('Unprivileged decoder isolation is unavailable')
        prefix=['unshare','--net','--','setpriv','--reuid='+str(nobody.pw_uid),'--regid='+str(nobody.pw_gid),'--clear-groups','--no-new-privs']
    if shutil.which('prlimit'):prefix+=['prlimit','--as='+str(768*1024**2),'--cpu=30','--fsize='+str(8*1024**2),'--']
    # Never inherit an ingestion FD with write permission into a decoder.
    readonly=os.open('/proc/self/fd/'+str(fd),os.O_RDONLY|os.O_CLOEXEC)
    try:
        before=os.fstat(fd);after=os.fstat(readonly)
        if (before.st_dev,before.st_ino)!=(after.st_dev,after.st_ino):raise ValueError('Decoder input identity changed')
        args=list(args)
        if '-fd' in args:args[args.index('-fd')+1]=str(readonly)
        with tempfile.TemporaryFile() as output:
            process=subprocess.Popen(prefix+[executable,*args],stdin=readonly if tool=='exiftool' else subprocess.DEVNULL,stdout=output,stderr=subprocess.DEVNULL,pass_fds=(readonly,),close_fds=True)
            try:code=process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:process.kill();process.wait();raise ValueError('Photo decoder exceeded its time limit') from None
            if code:raise ValueError('This file could not be decoded')
            output.seek(0);data=output.read(8*1024**2+1)
            if len(data)>8*1024**2:raise ValueError('Decoder output limit exceeded')
            return data
    finally:os.close(readonly)

def inspect(fd,fallback=None):
    try:
        data=decode(fd,'exiftool',['-json','-n','-api','LargeFileSupport=1',*['-'+t for t in TAGS],'-'])
        rows=json.loads(data);return metadata(rows[0] if rows else {},fallback)
    except (ValueError,OSError,KeyError,json.JSONDecodeError):return {**metadata({},fallback),'metadata_unavailable':True}

def jpeg(fd,large=False):
    width=1600 if large else 384
    return decode(fd,'ffmpeg',['-nostdin','-v','error','-threads','1','-protocol_whitelist','fd,pipe','-fd',str(fd),'-i','fd:','-frames:v','1','-vf',fr'scale=min({width}\,iw):-2','-f','image2pipe','-c:v','mjpeg','-q:v','4','pipe:1'])
