"""Independent network controller: early firewall, scoped DHCP, timed rollback."""
import hashlib
import json
import os
import signal
import socket
import time
from pathlib import Path
from .common import Context,canonical,run
from .network import DEFAULT,PREFIX,Network,validate,profiles,dnsmasq,firewall,lock
from ..state import atomic


def text(path,value,mode=0o600):
    path=Path(path);path.parent.mkdir(mode=0o755,parents=True,exist_ok=True);temp=path.with_name(path.name+'.next')
    with temp.open('w') as f:os.fchmod(f.fileno(),mode);f.write(value);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)
    fd=os.open(path.parent,os.O_DIRECTORY|os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

class Agent:
    def __init__(self,ctx=None,network_dir='/etc/systemd/network',config_dir='/etc/freeqnap-dhcp',runner=run,boot_id=None):
        self.ctx=ctx or Context();self.api=Network(self.ctx);self.root=self.api.root;self.network_dir=Path(network_dir);self.config_dir=Path(config_dir);self.run=runner;self.applied=None;self.started=set();self.boot=boot_id or Path('/proc/sys/kernel/random/boot_id').read_text().strip();self.last_rules=None
    def pending(self):
        path=self.root/'pending.json';return json.loads(path.read_text()) if path.exists() else None
    def set_pending(self,p):atomic(self.root/'pending.json',p);self.ctx.state.set('network_pending',p)
    def clear(self):
        for name in ['pending.json','confirmed.json','rollback-request.json']:(self.root/name).unlink(missing_ok=True)
        self.ctx.state.set('network_pending',None)
        fd=os.open(self.root,os.O_DIRECTORY|os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    def snapshot(self):return {p.name:p.read_text() for p in self.network_dir.glob(PREFIX+'*.network') if p.is_file() and not p.is_symlink()}
    def blocked_ips(self,cfg):
        p=cfg.get('private_lan')
        if not p:return []
        blocked={c['mac'] for c in p['clients'] if c['blocked']};ips={c['reservation'] for c in p['clients'] if c['blocked'] and c['reservation']}
        for c in self.api.status()['clients']:
            if c['mac'] in blocked:ips.update(c.get('addresses',[]))
        return sorted(ips)
    def enforce(self,cfg):
        value=firewall(cfg,self.blocked_ips(cfg))
        if value==self.last_rules:return
        path=self.root/'firewall.nft';text(path,value);self.run('nft','--check','-f',str(path));self.run('nft','-f',str(path));self.last_rules=value
    def apply_files(self,cfg,restoring=None):
        desired=profiles(cfg) if restoring is None else restoring
        old=self.snapshot();changed=old!=desired
        interfaces={f[len(PREFIX):-len('.network')] for f in old}
        if not changed:return False
        for filename,value in desired.items():
            if not filename.startswith(PREFIX) or '/' in filename or not filename.endswith('.network'):raise ValueError('Invalid owned network profile backup')
            text(self.network_dir/filename,value,0o644)
        for path in self.network_dir.glob(PREFIX+'*.network'):
            if path.name not in desired:
                if path.is_symlink():raise ValueError('Unexpected network profile symlink')
                path.unlink()
        self.run('networkctl','reload')
        interfaces|={p['interface'] for p in cfg['interfaces']};p=cfg.get('private_lan')
        if p:interfaces.add(p['interface'])
        interfaces|=self.started;self.started=interfaces
        if interfaces:self.run('networkctl','reconfigure',*sorted(interfaces),timeout=30)
        return changed
    def configure(self,cfg,restoring=None):
        cfg=validate(cfg);self.enforce(cfg)
        # A stopped/failed DHCP unit cannot broadcast on a stale port profile.
        value=dnsmasq(cfg);path=self.config_dir/'private-lan.conf'
        dhcp_changed=(value or '')!=(path.read_text() if path.exists() else '') or profiles(cfg)!=self.snapshot()
        if dhcp_changed or not value:self.run('systemctl','stop','freeqnap-dhcp.service')
        if value:
            path=self.config_dir/'private-lan.conf';text(path,value,0o644);self.run('dnsmasq','--test','--conf-file='+str(path))
        elif path.exists():path.unlink()
        changed=self.apply_files(cfg,restoring)
        # Reconcile VPN local-return exceptions and optional private-LAN gateway.
        from .vpn_runtime import load,enforce,rules,ROOT
        from .vpn import configuration_lock
        private=cfg.get('private_lan');signature=[private[k] for k in ['interface','address','route_via']] if private else None
        previous=self.ctx.state.setting('network_vpn_signature')
        if (changed or signature!=previous) and (ROOT/'active.json').exists():
            vpn=load()
            if vpn.get('client') or vpn.get('server'):
                self.run('systemctl','stop','freeqnap-vpn.service',timeout=45)
                with configuration_lock(ROOT):enforce(vpn);rules(vpn,cfg.get('private_lan'))
                self.run('systemctl','start','freeqnap-vpn.service')
        self.ctx.state.set('network_vpn_signature',signature)
        if cfg.get('private_lan') and cfg['private_lan']['route_via']!='none':self.run('sysctl','-w','net.ipv4.ip_forward=1')
        self.applied=hashlib.sha256(canonical(cfg)).hexdigest()
    def ready(self,cfg):
        live={p['interface']:p for p in self.api.ports()}
        for p in [*cfg['interfaces'],*([cfg['private_lan']] if cfg.get('private_lan') else [])]:
            r=live.get(p['interface'])
            if not r or r['mac']!=p['mac']:return False
            detail=json.loads(self.run('networkctl','--json=short','status',p['interface']))
            if detail.get('NetworkFile')!=str(self.network_dir/(PREFIX+p['interface']+'.network')) or detail.get('AdministrativeState')!='configured':return False
            expected=p.get('address')
            if expected and expected.split('/')[0] not in [v['local'] for v in r['addresses']]:return False
            if p.get('mode')=='dhcp' and r['state']=='UP' and not any(v['family']=='inet' for v in r['addresses']):return False
        p=cfg.get('private_lan')
        if p:self.run('systemctl','start','freeqnap-dhcp.service')
        return True
    def rollback(self,p,error=None):
        cfg=validate(p['previous']);atomic(self.root/'active.json',cfg)
        self.configure(cfg,restoring=p.get('profile_backups'))
        self.ctx.state.set('network_last_change',{'id':p['id'],'result':'rolled-back','reason':error,'at':time.time()})
        if p.get('job_id'):self.ctx.state.finish(p['job_id'],error='Network change rolled back: '+str(error))
        self.ctx.state.set('network_runtime',{'state':'rolled-back','at':time.time(),'error':error,'configuration_sha256':self.applied});self.clear()
    def prepare(self):
        """Restore any unconfirmed interrupted change before opening networking."""
        with lock(self.root):
            self.run('systemctl','stop','freeqnap-dhcp.service')
            p=self.pending();confirmed=self.root/'confirmed.json'
            acknowledged=bool(p and confirmed.exists() and json.loads(confirmed.read_text()).get('id')==p['id'])
            if acknowledged:
                self.ctx.state.set('network_last_change',{'id':p['id'],'result':'confirmed','at':time.time()})
                if p.get('job_id'):self.ctx.state.finish(p['job_id'],result={'network_change':'confirmed'})
                self.clear()
            elif p and (p['boot_id']!=self.boot or p['phase']!='requested'):
                previous=validate(p['previous']);desired=p.get('profile_backups')
                if desired is not None:
                    for filename,value in desired.items():
                        if not filename.startswith(PREFIX) or '/' in filename or not filename.endswith('.network'):raise ValueError('Invalid owned network profile backup')
                        text(self.network_dir/filename,value,0o644)
                    for filename in self.network_dir.glob(PREFIX+'*.network'):
                        if filename.name not in desired:filename.unlink()
                atomic(self.root/'active.json',previous)
                self.ctx.state.set('network_last_change',{'id':p['id'],'result':'rolled-back','reason':'Interrupted network change restored before network setup','at':time.time()})
                if p.get('job_id'):self.ctx.state.finish(p['job_id'],error='Interrupted network change restored; review a fresh plan')
                self.clear()
            self.enforce(validate(self.api.current()))

    def tick(self,startup=False):
        with lock(self.root):
            p=self.pending();cfg=validate(self.api.current())
            try:self.run('systemctl','is-active','systemd-networkd.service')
            except (ValueError,OSError):return
            if p:
                confirmed=self.root/'confirmed.json'
                if confirmed.exists() and json.loads(confirmed.read_text()).get('id')==p['id']:
                    self.clear();p=None
                elif (self.root/'rollback-request.json').exists() or p['boot_id']!=self.boot or (startup and p['phase']!='requested') or (p.get('deadline_monotonic') and time.monotonic()>=p['deadline_monotonic']):
                    self.rollback(p,'Unconfirmed, expired or interrupted network change restored');return
            digest=hashlib.sha256(canonical(cfg)).hexdigest()
            try:
                if p and p['phase']=='requested':
                    if digest!=p['configuration_sha256']:raise ValueError('Pending network configuration hash changed')
                    p.update(phase='applying',profile_backups=self.snapshot(),deadline_monotonic=time.monotonic()+120,deadline=time.time()+120);self.set_pending(p)
                if self.applied!=digest:self.configure(cfg)
                self.enforce(cfg)
                if self.ready(cfg):
                    if p and p['phase']=='applying':p['phase']='active';self.set_pending(p)
                    self.ctx.state.set('network_runtime',{'state':'running','configuration_sha256':digest,'private_lan_enabled':bool(cfg.get('private_lan')),'at':time.time()})
                else:self.ctx.state.set('network_runtime',{'state':'applying','configuration_sha256':digest,'at':time.time()})
            except Exception as error:
                self.ctx.state.set('network_runtime',{'state':'failed','error':str(error),'at':time.time()})
                if p:self.rollback(p,str(error))
                else:raise

def main():
    agent=Agent();stop=False
    def finish(*args):
        nonlocal stop;stop=True
    signal.signal(signal.SIGTERM,finish);signal.signal(signal.SIGINT,finish)
    # The empty default adds no DHCP service or interface profiles. At boot,
    # firewall preparation completes before networkd may configure any port.
    agent.prepare()
    notify=os.environ.get('NOTIFY_SOCKET')
    if notify:
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as sock:sock.connect(('\0'+notify[1:]) if notify.startswith('@') else notify);sock.sendall(b'READY=1')
    first=True
    while not stop:
        try:agent.tick(startup=first)
        except Exception as error:agent.ctx.state.set('network_runtime',{'state':'failed','error':str(error),'at':time.time()})
        first=False
        for _ in range(10):
            if stop:break
            time.sleep(.2)
if __name__=='__main__':main()
