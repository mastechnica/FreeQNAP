#!/usr/bin/env python3
"""Two local BitTorrent peers and bounded ENOSPC recovery in private namespaces.
No public tracker/DHT/peer traffic or production download state is used.
"""
import argparse,base64,hashlib,http.server,json,os,secrets,shutil,socket,struct,subprocess,sys,tempfile,threading,time,urllib.parse,urllib.request
from pathlib import Path


def encode(value):
    if isinstance(value,int):return b'i'+str(value).encode()+b'e'
    if isinstance(value,bytes):return str(len(value)).encode()+b':'+value
    if isinstance(value,list):return b'l'+b''.join(map(encode,value))+b'e'
    if isinstance(value,dict):return b'd'+b''.join(encode(k)+encode(value[k]) for k in sorted(value))+b'e'
    raise TypeError('Unsupported bencode fixture')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--confirm-isolated-test',action='store_true',required=True);p.add_argument('--inner',action='store_true');p.add_argument('--full-destination',action='store_true');a=p.parse_args()
    if os.geteuid()!=0 or sys.platform!='linux':raise SystemExit('Linux root fixture required')
    if not a.inner:os.execvp('unshare',['unshare','--mount','--net','--fork','--propagation','private',sys.executable,str(Path(__file__).resolve()),'--confirm-isolated-test','--inner',*(['--full-destination'] if a.full_destination else [])])
    subprocess.run(['mount','--make-rprivate','/'],check=True);subprocess.run(['ip','link','set','lo','up'],check=True)
    if not shutil.which('aria2c'):raise SystemExit('aria2 required')
    processes=[];mounts=[];server=None;report={}
    with tempfile.TemporaryDirectory(prefix='freeqnap-torrent-fixture-') as directory:
        root=Path(directory)
        try:
            subprocess.run(['mount','-t','tmpfs','-o','size=64m,mode=755','tmpfs',str(root)],check=True);mounts.append(root)
            seed=root/'seed';seed.mkdir();target=root/'target';target.mkdir()
            subprocess.run(['mount','-t','tmpfs','-o',('size=4m,mode=700,uid=65534,gid=65534' if a.full_destination else 'size=24m,mode=700,uid=65534,gid=65534'),'tmpfs',str(target)],check=True);mounts.append(target)
            payload=os.urandom((12 if a.full_destination else 2)*1024**2);(seed/'fixture.bin').write_bytes(payload);os.chown(seed,65534,65534);os.chown(seed/'fixture.bin',65534,65534)
            piece=256*1024;info={b'length':len(payload),b'name':b'fixture.bin',b'piece length':piece,b'pieces':b''.join(hashlib.sha1(payload[i:i+piece]).digest() for i in range(0,len(payload),piece)),b'private':1}
            torrent=encode({b'announce':b'http://127.0.0.1:18081/announce',b'info':info});announces=[]
            class Tracker(http.server.BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_GET(self):
                    query=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query);port=int(query.get('port',['0'])[0]);announces.append(port)
                    peers=socket.inet_aton('127.0.0.1')+struct.pack('!H',16881) if port==16882 else b''
                    data=encode({b'interval':1,b'complete':1,b'incomplete':1,b'peers':peers});self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            server=http.server.ThreadingHTTPServer(('127.0.0.1',18081),Tracker);threading.Thread(target=server.serve_forever,daemon=True).start()
            token=secrets.token_hex(24)
            def start(label,folder,rpcport,btport):
                state=root/label;state.mkdir(mode=0o700);os.chown(state,65534,65534)
                config=state/'aria2.conf';config.write_text('\n'.join(['enable-rpc=true','rpc-listen-all=false','rpc-listen-port='+str(rpcport),'rpc-secret='+token,'dir='+str(folder),'enable-dht=false','enable-dht6=false','enable-peer-exchange=false','bt-enable-lpd=false','disable-ipv6=true','listen-port='+str(btport),'bt-tracker-interval=1','bt-tracker-connect-timeout=3','seed-time=2','seed-ratio=0','file-allocation=none','continue=true','always-resume=true','allow-overwrite=false','auto-file-renaming=false','check-integrity=true','bt-hash-check-seed=true','max-overall-download-limit=1M','console-log-level=error','summary-interval=0','log='+str(state/'engine.log'),'log-level=error'])+'\n');config.chmod(0o600);os.chown(config,65534,65534)
                proc=subprocess.Popen(['setpriv','--reuid=65534','--regid=65534','--clear-groups','aria2c','--conf-path='+str(config)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);processes.append(proc)
                def rpc(method,params=()):
                    req=urllib.request.Request('http://127.0.0.1:'+str(rpcport)+'/jsonrpc',data=json.dumps({'jsonrpc':'2.0','id':'fixture','method':'aria2.'+method,'params':['token:'+token,*params]}).encode(),headers={'Content-Type':'application/json'})
                    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=3) as response:value=json.load(response)
                    if 'error' in value:raise RuntimeError('Isolated RPC rejected '+method)
                    return value['result']
                for _ in range(50):
                    try:rpc('getVersion');return rpc
                    except OSError:time.sleep(.1)
                raise RuntimeError('Isolated engine unavailable')
            seedrpc=start('seed-state',seed,16800,16881);leechrpc=start('target-state',target,16801,16882)
            encoded=base64.b64encode(torrent).decode();seedgid=seedrpc('addTorrent',[encoded,[],{}])
            deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                if int(seedrpc('tellStatus',[seedgid,['completedLength']])['completedLength'])==len(payload):break
                time.sleep(.2)
            else:raise AssertionError('Seeder integrity check did not finish')
            gid=leechrpc('addTorrent',[encoded,[],{}]);deadline=time.monotonic()+60
            if a.full_destination:
                while time.monotonic()<deadline:
                    row=leechrpc('tellStatus',[gid,['status','completedLength','errorCode']])
                    if row['status']=='error':break
                    time.sleep(.2)
                else:raise AssertionError('Full destination did not report bounded failure')
                if not 0<int(row['completedLength'])<len(payload):raise AssertionError('No verified partial torrent before ENOSPC')
                if row.get('errorCode') not in ('9','16'):raise AssertionError('Unexpected torrent failure code '+str(row.get('errorCode')))
                if not (target/'fixture.bin.aria2').is_file():raise AssertionError('Partial torrent control file lost')
                report['real_torrent_full_destination_retains_partial']=True
                subprocess.run(['mount','-o','remount,size=24m',str(target)],check=True)
                leechrpc('removeDownloadResult',[gid]);gid=leechrpc('addTorrent',[encoded,[],{}]);deadline=time.monotonic()+60
            damaged=False
            while time.monotonic()<deadline:
                row=leechrpc('tellStatus',[gid,['status','completedLength','errorCode','errorMessage']])
                if int(row['completedLength'])==len(payload):break
                if row['status']=='error':
                    if a.full_destination and row.get('errorCode')=='1' and 'segment file' in row.get('errorMessage',''):
                        damaged=True;break
                    raise AssertionError('Unexpected torrent failure code '+str(row.get('errorCode')))
                time.sleep(.2)
            else:
                print(json.dumps({'incomplete_peer_status':row,'seeder_status':seedrpc('tellStatus',[seedgid,['status','uploadLength','connections']]),'tracker_announces':len(announces)}),flush=True)
                raise AssertionError('Local torrent transfer timed out')
            if not damaged:
                if hashlib.sha256((target/'fixture.bin').read_bytes()).digest()!=hashlib.sha256(payload).digest():raise AssertionError('Torrent payload differs')
            if 16882 not in announces:raise AssertionError('Local tracker was not used')
            report.update(local_two_peer_torrent_transfer=not damaged,sha256_verified=not damaged,
                          damaged_control_file_observed=damaged,automatic_corrupt_marker_recovery_accepted=False,
                          public_peer_network_used=False,production_queue_changed=False,full_destination_test=a.full_destination)
        finally:
            for proc in processes:
                if proc.poll() is None:proc.terminate()
            for proc in processes:
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
            if server:server.shutdown();server.server_close()
            for mount in reversed(mounts):subprocess.run(['umount',str(mount)],check=True)
    report['temporary_ram_fixtures_removed']=True;print(json.dumps(report,indent=2))

if __name__=='__main__':main()
