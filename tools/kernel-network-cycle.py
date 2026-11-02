#!/usr/bin/env python3
"""One attended, identity-bound RJ45 close/open cycle; default is read-only.

Run --apply only in a separately supervised service with an ExecStopPost link-up
fallback and a serial console. Never uses driver unbind, PCI reset or saved network
configuration. Host upload/download proof is a separate acceptance requirement.
"""
import argparse,ipaddress,json,os,re,subprocess,time
from pathlib import Path

def run(*args,timeout=10):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=timeout).strip()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--interface',choices=['enp0s1','enp0s3'],required=True);p.add_argument('--expected-mac',required=True);p.add_argument('--expected-install-id',required=True);p.add_argument('--expected-kernel',required=True);p.add_argument('--peer',required=True);p.add_argument('--result',type=Path,required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
    if os.geteuid()!=0 or Path('/proc/device-tree/compatible').read_bytes().split(b'\0')[0]!=b'qnap,ts-431xeu':raise ValueError('Exact NAS board and root required')
    if Path('/etc/freeqnap-install-id').read_text().strip()!=a.expected_install_id or os.uname().release!=a.expected_kernel:raise ValueError('Unexpected installation or kernel')
    if not re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}',a.expected_mac):raise ValueError('Exact MAC required')
    net=Path('/sys/class/net')/a.interface
    if (net/'address').read_text().strip()!=a.expected_mac or (net/'carrier').read_text().strip()!='1':raise ValueError('Expected connected RJ45 required')
    other=[n for n in ('enp0s0','enp0s1','enp0s3') if n!=a.interface and Path('/sys/class/net',n,'carrier').read_text().strip()=='1']
    if other:raise ValueError('Use one connected NAS uplink to prove the exact traffic path')
    peer=ipaddress.IPv4Address(a.peer)
    addresses=json.loads(run('ip','-j','address','show','dev',a.interface))[0]['addr_info']
    ips=[r['local'] for r in addresses if r['family']=='inet' and peer in ipaddress.IPv4Network(r['local']+'/'+str(r['prefixlen']),strict=False)]
    if len(ips)!=1:raise ValueError('Unique on-link test address required')
    route=json.loads(run('ip','-j','route','get',str(peer),'from',ips[0]))
    if len(route)!=1 or route[0]['dev']!=a.interface:raise ValueError('Traffic would use another interface')
    cool=json.loads(Path('/run/freeqnap-cooling/status.json').read_text())
    if cool['level']!=7 or cool.get('fault') or not 0<=time.monotonic()-cool['monotonic']<3:raise ValueError('Fresh full cooling required')
    arrays={}
    for n in ('md126','md127'):
        d=Path('/sys/block',n,'md');arrays[n]={k:(d/k).read_text().strip() for k in ('uuid','degraded','sync_action')}
        if arrays[n]['degraded']!='0' or arrays[n]['sync_action']!='idle':raise ValueError('Healthy idle arrays required')
    if not a.apply:print(json.dumps({'read_only':True,'interface':a.interface,'connected':True,'exact_path_verified':True}));return
    parent=a.result.parent.resolve()
    if not parent.is_relative_to('/var/lib/freeqnap-validation') or parent.stat().st_uid!=0 or parent.stat().st_mode&0o077 or a.result.is_symlink():raise ValueError('Existing private root-owned validation directory required')
    fd=os.open(a.result,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.close(fd)
    result={'stage':'running','kernel':os.uname().release,'interface':a.interface,'mac':a.expected_mac,'address':ips[0],'arrays_before':arrays,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    def save():
        tmp=a.result.with_suffix('.tmp');fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:json.dump(result,f,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(tmp,a.result)
    save();started=time.monotonic()
    try:
        try:run('ip','link','set','dev',a.interface,'down');time.sleep(1)
        finally:run('ip','link','set','dev',a.interface,'up')
        run('networkctl','reconfigure',a.interface,timeout=15)
        end=time.monotonic()+30
        while time.monotonic()<end:
            if (net/'carrier').read_text().strip()=='1':break
            time.sleep(.2)
        else:raise ValueError('Link did not return')
        run('ping','-I',a.interface,'-c','3','-W','2',str(peer),timeout=10)
        log=run('dmesg','--color=never');recent=[]
        for line in log.splitlines():
            stamp=re.match(r'^\[\s*([0-9.]+)\]',line)
            if stamp and float(stamp[1])>=started and re.search(r'dma.*(?:error|fail|timeout|fault)|data abort|Oops:|BUG:|soft lockup|NETDEV WATCHDOG',line,re.I):recent.append(line)
        if recent:raise ValueError('Kernel fault during network cycle; inspect UART/journal')
        for n,old in arrays.items():
            d=Path('/sys/block',n,'md')
            if {k:(d/k).read_text().strip() for k in old}!=old:raise ValueError('Array identity or health changed')
        result.update(stage='PASSED',seconds=time.monotonic()-started,interface_ping_verified=True,kernel_faults_detected=False,host_transfer_proof_pending=True);save();print(json.dumps({'stage':'PASSED','interface':a.interface,'host_transfer_proof_pending':True}))
    except BaseException as e:
        result.update(stage='FAILED',error=str(e),seconds=time.monotonic()-started);save();raise
if __name__=='__main__':main()
