#!/usr/bin/env python3
"""Bounded read-only Ethernet repair acceptance; never repair or restart a service."""
import argparse,json,math,os,signal,subprocess,sys,time
from pathlib import Path

FAULTS='Unhandled fault|asynchronous external abort|Kernel panic|I/O error|oom-kill|Out of memory|blocked for more than'


def run(*args):
    return subprocess.run(args,capture_output=True,text=True,timeout=12,check=True).stdout


def require(condition,message):
    if not condition:raise ValueError(message)


def private_json(path,value):
    with path.open('x') as stream:
        os.chmod(path,0o600);json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--boot-id',required=True)
    p.add_argument('--source-version',required=True)
    p.add_argument('--root-uuid',required=True)
    p.add_argument('--volume',action='append',required=True,help='Exact mounted path:filesystem UUID')
    p.add_argument('--seconds',type=int,default=600)
    a=p.parse_args()
    if not 60<=a.seconds<=7200:p.error('Choose 60–7200 seconds; record actual acceptance duration')
    require(Path('/proc/device-tree/compatible').read_bytes().split(b'\0')[0]==b'qnap,ts-431xeu','Wrong board')
    require(not a.directory.exists(),'Never overwrite a previous acceptance campaign')
    os.umask(0o077);a.directory.mkdir(mode=0o700,parents=True)
    volumes=[('/',a.root_uuid)]+[tuple(v.split(':',1)) for v in a.volume]
    require(all(len(v)==2 and Path(v[0]).is_absolute() for v in volumes),'Invalid volume identity')
    sys.path.insert(0,'/opt/freeqnap/current')
    from freeqnap.nas.broker import Client
    services=['freeqnap-broker','freeqnap-console','freeqnap-cooling','freeqnap-cooling-guard','freeqnap-https']
    pids={name:int(run('systemctl','show',name,'--property=MainPID','--value').strip()) for name in services}
    require(all(pids.values()),'Required service has no running process')
    started=time.monotonic();samples=0;reads=0;previous={}
    def stopped(*_):raise RuntimeError('Acceptance monitor stopped; no automatic retry')
    signal.signal(signal.SIGTERM,stopped)
    try:
        while True:
            require(Path('/proc/sys/kernel/random/boot_id').read_text().strip()==a.boot_id,'Boot changed')
            require(Path('/sys/module/al_eth/srcversion').read_text().strip()==a.source_version,'Loaded Ethernet module changed')
            require(run('uname','-r').strip()=='6.12.114-eyeq-ts431xeu-freeqnap1','Kernel ABI changed')
            for name,count in [('md126',4),('md127',2)]:
                md=Path('/sys/class/block')/name/'md'
                require((md/'degraded').read_text().strip()=='0' and int((md/'raid_disks').read_text())==count,'RAID membership changed')
                require((md/'sync_action').read_text().strip()=='idle','RAID consistency/recovery work requires review')
            for mount,uuid in volumes:
                require(run('findmnt','-rn','-T',mount,'-o','TARGET,UUID').strip()==mount+' '+uuid,'Mount identity changed')
            now=time.monotonic();cool=json.loads(Path('/run/freeqnap-cooling/status.json').read_text());guard=json.loads(Path('/run/freeqnap-cooling/guard.json').read_text())
            for value in (cool,guard):require(value['boot_id']==a.boot_id and 0<=now-value['monotonic']<6,'Cooling telemetry is stale')
            require(cool['level']==7 and not cool['fault'] and guard['ready'],'Full cooling/guard unavailable')
            sample=cool['sample'];require(len(sample['fans'])==3 and all(f['rpm']>5000 for f in sample['fans']),'Fan readings require review')
            require(math.isfinite(sample['cpu_c']) and sample['cpu_c']<65 and all(math.isfinite(t) and t<52 for t in sample['disks_c']),'Temperature acceptance limit reached')
            for _ in range(10):require(bool(json.loads(run('ip','-j','link','show'))),'Empty link dump')
            counters={}
            for port in Path('/sys/class/net').iterdir():
                if not (port/'device').exists():continue
                counters[port.name]=[int((port/'statistics'/n).read_text()) for n in ('rx_bytes','tx_bytes')];reads+=2
                if port.name in previous:require(all(n>=o for n,o in zip(counters[port.name],previous[port.name])),'Network counters reset')
            previous=counters
            before=time.monotonic();state=Client(timeout=12).request('nas.status');latency=time.monotonic()-before
            require(state.get('health',{}).get('monitor_stale') is False,'Native health monitor is stale')
            require(not state['health'].get('monitor',{}).get('failed_scopes'),'Health probes failed')
            for name,pid in pids.items():
                require(run('systemctl','is-active',name).strip()=='active','Required service inactive')
                require(int(run('systemctl','show',name,'--property=MainPID','--value').strip())==pid,'Required service restarted')
            journal=subprocess.run(['journalctl','-k','-b','--no-pager','-g',FAULTS],capture_output=True,text=True,timeout=12)
            require(journal.returncode in (0,1),'Kernel log unavailable')
            if journal.returncode==0:
                (a.directory/'kernel-faults.txt').write_text(journal.stdout);raise ValueError('New kernel fault detected')
            samples+=1;elapsed=time.monotonic()-started
            point={'elapsed_seconds':elapsed,'native_status_seconds':latency,'cpu_c':sample['cpu_c'],'disks_c':sample['disks_c'],'fan_rpms':[f['rpm'] for f in sample['fans']],'alert_counts':state['health'].get('active_counts',{}),'counter_reads':reads}
            with (a.directory/'samples.jsonl').open('a') as stream:stream.write(json.dumps(point)+'\n');stream.flush();os.fsync(stream.fileno())
            if elapsed>=a.seconds:break
            time.sleep(min(10,a.seconds-elapsed))
        result={'status':'passed','duration_seconds':time.monotonic()-started,'samples':samples,'link_dumps':samples*10,'counter_reads':reads,'service_pids_stable':True,'boot_id':a.boot_id,'source_version':a.source_version,'physical_other_port_tested':False,'flash_changed':False}
    except Exception as error:
        result={'status':'failed','duration_seconds':time.monotonic()-started,'samples':samples,'error':str(error),'error_type':type(error).__name__,'automatic_retry':False}
        private_json(a.directory/'result.json',result);raise
    private_json(a.directory/'result.json',result);print(json.dumps(result))


if __name__=='__main__':main()
