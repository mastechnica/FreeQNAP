"""Systemd-owned VPN runtime. Its early-boot firewall persists after failure.

No global route/ruleset flush. Pending changes roll back independently of the UI
and broker. Host management remains on explicitly reviewed directly connected LAN.
"""
import argparse
import fcntl
import hashlib
import ipaddress
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from .common import Context, run, canonical
from .vpn import CLIENT, SERVER, ROUTE_TABLE, firewall, openvpn_client, wireguard, configuration_lock
from ..state import atomic

ROOT=Path('/var/lib/freeqnap-system/vpn')
STOP=False

def write(path,text,mode=0o600):
    path=Path(path);path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.next')
    with temporary.open('w') as stream:
        os.fchmod(stream.fileno(),mode);stream.write(text);stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)

def load():
    path=ROOT/'active.json'
    return json.loads(path.read_text()) if path.exists() else {'version':1,'client':None,'server':None}

def private_lan():
    from .network import Network,validate
    return validate(Network(Context()).current()).get('private_lan')

def enforce(config):
    path=ROOT/'firewall.nft';write(path,firewall(config,private_lan()))
    run('nft','--check','-f',str(path));run('nft','-f',str(path))

def remove_rules():
    path=ROOT/'owned-rules.json'
    if not path.exists():return
    for args in json.loads(path.read_text()):
        # Recorded argv is private root-owned, but constrain it even on recovery.
        if not isinstance(args,list) or len(args)>20 or args[:2] not in (['ip','-4'],['ip','-6']) or args[2:4]!=['rule','add']:raise ValueError('Invalid owned route record')
        attempt=args[:];attempt[3]='del'
        try:run(*attempt)
        except ValueError:pass
    atomic(path,[])

def rules(config,private=None):
    remove_rules();c=config.get('client');s=config.get('server');owned=[]
    if private is None:private=private_lan()
    def add(*args):
        value=list(args);owned.append(value);atomic(ROOT/'owned-rules.json',owned);run(*value)
    if c:
        # Unreachable defaults prevent fallback even before a tunnel exists.
        for family in ('-4','-6'):
            run('ip',family,'route','replace','unreachable','default','metric','42760','table',str(ROUTE_TABLE))
            add('ip',family,'rule','add','priority','9990','fwmark',str(ROUTE_TABLE),'lookup','main')
            for lan in (c['lan_networks']+([str(ipaddress.ip_interface(private['address']).network)] if private else [])) if family=='-4' else []:add('ip',family,'rule','add','priority','10000','to',lan,'lookup','main')
            if s and family=='-4':add('ip',family,'rule','add','priority','10000','to',s['subnet'],'lookup','main')
            if c['full_tunnel']:add('ip',family,'rule','add','priority','10010','lookup',str(ROUTE_TABLE))
        for source in c['gateway_clients']+([s['subnet']] if s and s['gateway'] else [])+([str(ipaddress.ip_interface(private['address']).network)] if private and private['route_via']=='vpn' else []):
            add('ip','-4','rule','add','priority','10020','from',source,'lookup',str(ROUTE_TABLE))
    return owned

def route_tunnel(c):
    """Run after interface exists; never install a host main-table default."""
    rows=json.loads(run('ip','-j','address','show','dev',CLIENT))
    infos=[v for row in rows for v in row.get('addr_info',[])]
    if not any(a['family']=='inet' for a in infos):return False
    run('ip','-4','route','replace','default','dev',CLIENT,'metric','10','table',str(ROUTE_TABLE))
    if any(a['family']=='inet6' and a.get('scope')=='global' for a in infos):run('ip','-6','route','replace','default','dev',CLIENT,'metric','10','table',str(ROUTE_TABLE))
    if c['full_tunnel']:
        run('resolvectl','dns',CLIENT,*c['dns']);run('resolvectl','domain',CLIENT,'~.');run('resolvectl','default-route',CLIENT,'yes')
    return True

def wg_start(config,server=False):
    interface=SERVER if server else CLIENT
    try:run('ip','link','add',interface,'type','wireguard')
    except ValueError:run('wireguard-go',interface)
    if server:
        keypath=ROOT/'server.key'
        if not keypath.exists():write(keypath,run('wg','genkey'))
        conf=wireguard(config,keypath.read_text().strip());s=config['server'];net=ipaddress.ip_network(s['subnet']);addresses=[str(net.network_address+1)+'/'+str(net.prefixlen)]
    else:conf=wireguard(config);addresses=config['client']['addresses']
    path=ROOT/('server.wg' if server else 'client.wg');write(path,conf)
    run('wg','setconf',interface,str(path))
    for ip in addresses:run('ip','address','add',ip,'dev',interface)
    run('ip','link','set','dev',interface,'mtu','1380','up')

def openvpn_start(config,server=False):
    if server:
        from .vpn_pki import ensure, server_config
        with configuration_lock(ROOT):ensure(ROOT/'pki')
        text=server_config(config['server'],ROOT/'pki')
    else:
        c=config['client'];text=openvpn_client(c,ROOT)
        if c.get('username'):write(ROOT/'provider-login',c['username']+'\n'+c['password']+'\n')
    path=ROOT/('server.ovpn' if server else 'client.ovpn');write(path,text)
    # No configuration is accepted from a path supplied by the network/UI.
    return subprocess.Popen(['openvpn','--config',str(path)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True)

def cleanup(processes):
    for process in processes:
        process.terminate()
    for process in processes:
        try:process.wait(timeout=15)
        except subprocess.TimeoutExpired:process.kill();process.wait()
    for interface in (CLIENT,SERVER):
        try:run('ip','link','delete',interface)
        except ValueError:pass
    # Keep kill-switch + unreachable routes/rules in place until another reviewed configuration.

def _check_pending(ctx):
    path=ROOT/'pending.json'
    if not path.exists():return False
    pending=json.loads(path.read_text());confirmed=ROOT/'confirmed.json'
    if confirmed.exists() and json.loads(confirmed.read_text()).get('id')==pending['id']:
        path.unlink();return False
    if time.time()<pending['deadline']:return False
    previous=ROOT/'previous.json'
    atomic(ROOT/'active.json',json.loads(previous.read_text()) if previous.exists() else {'version':1,'client':None,'server':None})
    path.unlink();ctx.state.set('vpn_pending',None)
    ctx.state.set('vpn_last_rollback',{'at':time.time(),'reason':'Local confirmation timed out'})
    return True

def check_pending(ctx):
    # Do not block a systemctl restart held by the broker's configuration lock.
    with (ROOT/'operations.lock').open('a') as stream:
        try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return False
        try:return _check_pending(ctx)
        finally:fcntl.flock(stream,fcntl.LOCK_UN)

def main():
    global STOP
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--firewall',action='store_true');parser.add_argument('--disable',action='store_true');args=parser.parse_args()
    if os.geteuid()!=0:raise SystemExit('Local root required')
    ROOT.mkdir(mode=0o700,parents=True,exist_ok=True);ctx=Context()
    if args.disable:
        atomic(ROOT/'active.json',{'version':1,'client':None,'server':None});(ROOT/'pending.json').unlink(missing_ok=True);ctx.state.set('vpn_pending',None)
        remove_rules();enforce(load());return
    if args.firewall:enforce(load());return
    signal.signal(signal.SIGTERM,lambda *_:globals().__setitem__('STOP',True));signal.signal(signal.SIGINT,lambda *_:globals().__setitem__('STOP',True))
    while not STOP:
        processes=[];config=load();started=time.time()
        try:
            # Firewall goes first, even if driver/setup/authentication fails later.
            enforce(config);rules(config)
            c=config.get('client');s=config.get('server')
            if (c or s) and not Path('/dev/net/tun').exists():raise ValueError('Load the matching TUN driver before enabling VPN services')
            # wg_start uses wireguard-go when the optional in-kernel implementation is absent.
            if c:
                if c['type']=='wireguard':wg_start(config)
                else:processes.append(openvpn_start(config))
            if s:
                if s['type']=='wireguard':wg_start(config,True)
                else:processes.append(openvpn_start(config,True))
            if c and c['gateway_clients'] or s:
                run('sysctl','-w','net.ipv4.ip_forward=1')
                # No redirect advertisement; gateway clients are owner-configured.
                run('sysctl','-w','net.ipv4.conf.all.send_redirects=0')
                for interface in ('enp0s1','enp0s3'):run('sysctl','-w','net.ipv4.conf.'+interface+'.send_redirects=0')
            routed=False
            while not STOP:
                if check_pending(ctx):break
                if any(p.poll() is not None for p in processes):raise ValueError('OpenVPN stopped; policy remains fail closed')
                try:
                    if c:routed=route_tunnel(c)
                except ValueError:routed=False
                handshake=None
                if c and c['type']=='wireguard':
                    try:
                        values=run('wg','show',CLIENT,'latest-handshakes').splitlines();handshake=max((int(v.split()[1]) for v in values),default=0)
                    except ValueError:pass
                ctx.state.set('vpn_runtime',{'state':'running','config_sha256':hashlib.sha256(canonical(config)).hexdigest(),'started_at':started,'updated_at':time.time(),'tunnel_address_ready':routed,'latest_handshake':handshake,'firewall':'enforced','peer_connectivity_verified':False})
                time.sleep(2)
        except Exception:
            ctx.state.set('vpn_runtime',{'state':'error','updated_at':time.time(),'error':'VPN setup or process failed; inspect local service. Kill switch retained; no automatic WAN fallback.'})
            # Independent deadline still works if interface/key/auth setup fails.
            while not STOP:
                if check_pending(ctx):break
                time.sleep(2)
        finally:cleanup(processes)
    ctx.state.set('vpn_runtime',{'state':'stopped','kill_switch_retained':bool(load().get('client'))})
if __name__=='__main__':main()
