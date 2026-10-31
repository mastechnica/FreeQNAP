"""Root-only transient APFS launcher. A password is consumed from volatile /run."""
import json,os,re,stat,subprocess,sys
from pathlib import Path

def main():
    path=Path(sys.argv[1]);ident=path.stem
    if os.geteuid()!=0 or path.parent!=Path('/run/freeqnap-foreign') or not re.fullmatch('[a-f0-9]{32}',ident):raise SystemExit('Invalid private APFS launch')
    def load(p):
        fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o077 or info.st_size>8192:raise ValueError('Unsafe handoff')
            return os.read(fd,8193)
        finally:os.close(fd)
    cfg=json.loads(load(path));key=path.with_suffix('.secret');password=load(key);key.unlink();path.unlink()
    source=cfg['source'];usb=bool(re.fullmatch('/dev/sd[a-z]+[0-9]*',source));loop=re.fullmatch('/dev/(loop[0-9]+)(p[0-9]+)?',source)
    if loop:
        # No dashboard route selects loops. Permit owned test images for the explicit fixture tool.
        backing=Path('/sys/class/block')/loop[1]/'loop/backing_file';file=Path(backing.read_text().strip())
        if not file.is_relative_to('/var/lib/freeqnap-validation') or file.stat().st_uid!=0 or file.parent.stat().st_mode&0o077:raise SystemExit('Invalid loop fixture')
    if not (usb or loop) or cfg['mountpoint']!='/srv/freeqnap/foreign/'+ident or isinstance(cfg['volume_index'],bool) or not isinstance(cfg['volume_index'],int) or not 0<=cfg['volume_index']<=255:raise SystemExit('Invalid APFS mount')
    env={**os.environ,'FREEQNAP_PASSWORD_STDIN':'1'}
    result=subprocess.run(['/usr/local/libexec/freeqnap-apfs-fuse','-v',str(cfg['volume_index']),'-o','ro,nodev,nosuid,noexec,fsname='+cfg['source'],cfg['source'],cfg['mountpoint']],input=password+b'\n',stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env,timeout=100)
    raise SystemExit(result.returncode)
if __name__=='__main__':main()
