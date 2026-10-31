"""Opt-in DDNS profiles, isolated signed ddclient drivers and bounded fair retries."""
import hashlib,ipaddress,json,os,re,secrets,shutil,stat,subprocess,threading,time,urllib.request
from pathlib import Path
from .common import name
from ..state import atomic

KEY='ddns_profiles'
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('Address discovery redirects are refused')
# Only reviewed options: no raw configuration, shell, hooks, router credentials or proxy.
PROVIDERS={
 'cloudflare':{'label':'Cloudflare API token','protocol':'cloudflare','zone':True,'login':'token','families':[4,6]},
 'duckdns':{'label':'DuckDNS','protocol':'duckdns','login':'unused','families':[4,6]},
 'dynu':{'label':'Dynu','protocol':'dyndns2','server':'api.dynu.com','families':[4,6]},
 'dyndns':{'label':'DynDNS','protocol':'dyndns2','families':[4,6]},
 'noip':{'label':'No-IP','protocol':'noip','families':[4,6]},
 'digitalocean':{'label':'DigitalOcean','protocol':'digitalocean','zone':True,'login':'unused','families':[4,6]},
 'namecheap':{'label':'Namecheap','protocol':'namecheap','zone':True,'families':[4]},
 'freedns':{'label':'FreeDNS / afraid.org','protocol':'freedns','families':[4]},
 'freemyip':{'label':'FreeMyIP','protocol':'freemyip','login':'unused','families':[4]},
 'changeip':{'label':'ChangeIP','protocol':'changeip','families':[4]},
 'easydns':{'label':'easyDNS','protocol':'easydns','families':[4]},
 'ovh':{'label':'OVH DynHost','protocol':'ovh','families':[4]},
 'zoneedit':{'label':'ZoneEdit','protocol':'zoneedit1','families':[4]},
 'domeneshop':{'label':'Domeneshop / Domainnameshop','protocol':'domeneshop','families':[4]},
 'infomaniak':{'label':'Infomaniak','protocol':'infomaniak','families':[4]},
 'custom-dyndns2':{'label':'Custom DynDNS2 HTTPS provider','protocol':'dyndns2','custom_server':True,'families':[4,6]},
}

def hostname(value):
    if not isinstance(value,str) or len(value)>253 or value!=value.lower() or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+',value):raise ValueError('Use a lowercase fully qualified DNS hostname')
    try:ipaddress.ip_address(value)
    except ValueError:return value
    raise ValueError('A DNS hostname, not an address, is required')

def address(value,family):
    try:ip=ipaddress.ip_address(value)
    except (ValueError,TypeError):raise ValueError('A valid public address is required')
    if ip.version!=family or not ip.is_global or ip.is_multicast or ip.is_unspecified or ip.is_loopback:raise ValueError('DDNS requires a globally routable address of the selected family; it cannot fix CGNAT')
    return str(ip)

def credential(value,required=True):
    if not isinstance(value,str) or len(value)>1024 or required and not value or any(c.isspace() or c in "'\"\\,#" or ord(c)<32 for c in value):raise ValueError('Use a provider token without whitespace, quotes, backslashes, commas or #')
    return value

def validate(request):
    fields={'name','provider','hostname','zone','login','family','source','address','server','interval_minutes','enabled'}
    if not isinstance(request,dict) or set(request)!=fields:raise ValueError('Choose all DDNS profile settings')
    c=dict(request);c['name']=name(c['name']);p=PROVIDERS.get(c['provider'])
    if not p:raise ValueError('Choose a supported DDNS provider')
    c['hostname']=hostname(c['hostname']);c['zone']=hostname(c['zone']) if c['zone'] else ''
    if p.get('zone') and not c['zone']:raise ValueError('This provider requires its DNS zone')
    if c['zone'] and c['hostname']!=c['zone'] and not c['hostname'].endswith('.'+c['zone']):raise ValueError('The hostname must be inside its selected DNS zone')
    if type(c['family']) is not int or c['family'] not in p['families']:raise ValueError('This provider profile does not offer the selected address family')
    if c['source'] not in ('manual','public-egress'):raise ValueError('Choose manual address or detected public egress')
    c['address']=address(c['address'],c['family']) if c['source']=='manual' else ''
    if p.get('custom_server'):c['server']=hostname(c['server'])
    elif c['server']:raise ValueError('This provider uses its reviewed fixed update server')
    if type(c['enabled']) is not bool or type(c['interval_minutes']) is not int or not 5<=c['interval_minutes']<=1440:raise ValueError('Use a 5–1440 minute interval and explicit enable setting')
    c['login']=credential(c['login'] or p.get('login',''),required=True) if c['provider']!='namecheap' else c['zone']
    if c['provider']=='duckdns' and (not c['hostname'].endswith('.duckdns.org') or c['hostname'].count('.')!=2):raise ValueError('Use one registered name under duckdns.org')
    return c

def render(config,password,ip):
    c=validate(config);p=PROVIDERS[c['provider']];ip=address(ip,c['family']);password=credential(password)
    lines=['daemon=0','foreground=yes','syslog=no','ssl=yes','timeout=20','use=disabled','usev4=disabled','usev6=disabled','protocol='+p['protocol'],'login='+c['login'],'password='+password,'usev'+str(c['family'])+'=ipv'+str(c['family']),'ipv'+str(c['family'])+'='+ip]
    if p.get('server') or p.get('custom_server'):lines.append('server='+p.get('server',c['server']))
    if p.get('zone') and c['provider']!='namecheap':lines.append('zone='+c['zone'])
    host=c['hostname']
    if c['provider']=='duckdns':host=host[:-len('.duckdns.org')]
    if c['provider']=='namecheap':host='@' if host==c['zone'] else host[:-len(c['zone'])-1]
    lines.append(host);return '\n'.join(lines)+'\n',host

def accepted_cache(path,host,ip,family):
    info=Path(path).lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size>65536:raise ValueError('DDNS cache is invalid')
    rows=[]
    for line in Path(path).read_text().splitlines():
        if not line or line.startswith('#'):continue
        fields,label=line.rsplit(None,1)
        if label!=host:continue
        parsed={}
        for part in fields.split(','):
            key,value=part.split('=',1)
            if key in parsed:raise ValueError('Ambiguous DDNS receipt')
            parsed[key]=value
        rows.append(parsed)
    if len(rows)!=1:raise ValueError('Missing exact-host DDNS receipt')
    row=rows[0];v=str(family);status=row.get('status-ipv'+v,row.get('status'));seen=row.get('ipv'+v,row.get('ip'));mtime=row.get('mtime-ipv'+v,row.get('mtime','0'))
    if status!='good' or seen!=ip or not re.fullmatch(r'\d+',mtime) or int(mtime)<=0:raise ValueError('Provider acceptance is not verified')
    return int(mtime)

class DDNS:
    def __init__(self,ctx,cache_root='/var/lib/freeqnap-ddns',runner=None):self.ctx=ctx;self.cache_root=Path(cache_root);self.lock=threading.Lock();self.runner=runner or self.execute
    def execute(self,args):
        import pwd
        account=pwd.getpwnam('freeqnap-ddns')
        if account.pw_uid==0 or account.pw_shell not in ('/usr/sbin/nologin','/sbin/nologin'):raise ValueError('DDNS requires its dedicated non-login service account')
        p=subprocess.run(args,capture_output=True,text=True,timeout=55)
        return p.returncode,p.stdout+'\n'+p.stderr
    def records(self):return self.ctx.state.setting(KEY,{})
    def status(self,request=None):
        items=[]
        for ident,r in sorted(self.records().items()):items.append({'name':ident,**r['config'],**r.get('runtime',{}),'credentials_saved':True,'revision':r['revision']})
        return {'items':items,'providers':[{'id':k,**v} for k,v in PROVIDERS.items()],'driver_available':bool(shutil.which('ddclient')),'enabled_by_default':False,'firewall_changed':False,'public_https_certificate_issued':False,'address_discovery':'Public-egress uses ipify over verified HTTPS; VPN egress may differ from the router WAN.'}
    def plan(self,request):
        c=validate(request);old=self.records().get(c['name'])
        return self.ctx.plan('ddns-profile',{'config':c,'before_revision':old['revision'] if old else None,'review':'Opt-in external DNS updates for this exact hostname. Enabling contacts the selected provider using its saved credentials; public-egress discovery also contacts ipify. It opens no firewall ports, does not solve CGNAT and does not issue a public HTTPS certificate. A VPN may cause a different detected public address. No raw hooks or shell configuration is accepted.'},'SAVE DDNS '+c['name'])
    def apply(self,request):
        with self.lock,self.ctx.lock():
            path,plan=self.ctx.reviewed(request,'ddns-profile');c=validate(plan['body']['config']);records=self.records();old=records.get(c['name'])
            if (old['revision'] if old else None)!=plan['body']['before_revision']:raise ValueError('DDNS profile changed after review')
            if not old and len(records)>=16:raise ValueError('At most sixteen DDNS profiles are supported')
            if c['enabled'] and any(r['config']['enabled'] and r['config']['hostname']==c['hostname'] and r['config']['family']==c['family'] and k!=c['name'] for k,r in records.items()):raise ValueError('Another enabled profile already controls this hostname/address family')
            password=request.get('password')
            if password is None:
                if not old or old['config']['provider']!=c['provider']:raise ValueError('Enter the provider password or API token')
                secret_file=old['credential_file']
            else:
                password=credential(password);secret_file='ddns-'+secrets.token_hex(16)+'.json'
            self.ctx.consume(path,plan)
            if password is not None:atomic(self.ctx.directory/'secrets'/secret_file,{'password':password})
            records[c['name']]={'revision':secrets.token_hex(16),'config':c,'credential_file':secret_file,'runtime':{'next_attempt_at':time.time(),'failures':0,'state':'waiting' if c['enabled'] else 'disabled'}};self.ctx.state.set(KEY,records)
        return self.status()
    def remove(self,request):
        ident=name(request.get('name'))
        if request.get('confirmation')!='REMOVE DDNS '+ident:raise ValueError('Type REMOVE DDNS followed by its name')
        with self.lock,self.ctx.lock():
            records=self.records()
            if ident not in records:raise ValueError('Unknown DDNS profile')
            del records[ident];self.ctx.state.set(KEY,records)
        return {'removed':ident,'provider_record_deleted':False,'private_credential_retained_for_review':True}
    def request_update(self,request):
        ident=name(request.get('name'))
        with self.lock:
            records=self.records();r=records.get(ident)
            if not r or not r['config']['enabled']:raise ValueError('Enable a reviewed DDNS profile before requesting an update')
            # A manual click cannot bypass provider error/rate backoff.
            r['runtime']['next_attempt_at']=max(time.time(),r['runtime'].get('retry_not_before',0));self.ctx.state.set(KEY,records)
        return {'requested':ident,'backoff_respected':True}
    def command(self,file,unit,cache):
        return ['systemd-run','--quiet','--wait','--collect','--pipe','--unit='+unit,'--property=User=freeqnap-ddns','--property=Group=freeqnap-ddns','--property=StateDirectory=freeqnap-ddns','--property=StateDirectoryMode=0700','--property=UMask=0077','--property=NoNewPrivileges=yes','--property=ProtectSystem=strict','--property=ProtectHome=yes','--property=PrivateTmp=yes','--property=PrivateDevices=yes','--property=CapabilityBoundingSet=','--property=RestrictSUIDSGID=yes','--property=RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6','--property=RuntimeMaxSec=45','--property=LoadCredential=config:'+str(file),'/usr/bin/ddclient','-daemon=0','-foreground','-file=/run/credentials/'+unit+'.service/config','-cache='+str(cache)]
    def discover_address(self,c):
        if c['source']=='manual':return c['address']
        url='https://api.ipify.org' if c['family']==4 else 'https://api6.ipify.org'
        with urllib.request.build_opener(NoRedirect()).open(url,timeout=10) as response:
            if response.geturl()!=url or response.status!=200:raise ValueError('Unexpected address discovery response')
            data=response.read(129)
        if len(data)>128:raise ValueError('Invalid address discovery response')
        return address(data.decode('ascii').strip(),c['family'])
    def tick(self,now=None):
        if not self.lock.acquire(blocking=False):return
        try:
            now=time.time() if now is None else now;records=self.records();due=sorted((r['runtime'].get('next_attempt_at',0),k) for k,r in records.items() if r['config']['enabled'] and r['runtime'].get('next_attempt_at',0)<=now)
            if not due:return
            _,ident=due[0];r=records[ident];c=r['config'];runtime=r['runtime'];runtime['last_attempt_at']=now
            try:
                if not shutil.which('ddclient'):raise ValueError('Install ddclient first')
                ip=self.discover_address(c);secret_path=self.ctx.directory/'secrets'/r['credential_file']
                if secret_path.is_symlink() or secret_path.stat().st_size>4096:raise ValueError('Invalid private credential')
                config,host=render(c,json.loads(secret_path.read_text())['password'],ip)
                directory=self.ctx.directory/'ddns';directory.mkdir(mode=0o700,exist_ok=True);file=directory/(r['revision']+'.conf');temporary=file.with_suffix('.next')
                with temporary.open('x') as out:os.fchmod(out.fileno(),0o600);out.write(config);out.flush();os.fsync(out.fileno())
                os.replace(temporary,file);unit='freeqnap-ddns-'+secrets.token_hex(12);cache=self.cache_root/(r['revision']+'.cache')
                args=self.command(file,unit,cache)
                # Debian installs the program in /usr/bin; no secret appears in argv.
                code,output=self.runner(args)
                if code or re.search(r'^(?:FAILED|FATAL|ERROR):',output,re.M):raise ValueError('DDNS provider request failed')
                accepted=accepted_cache(cache,host,ip,c['family'])
                if accepted>time.time()+60:raise ValueError('DDNS receipt time is in the future')
                runtime.update(state='provider-accepted' if accepted>=now-1 else 'unchanged-previously-accepted',last_provider_acceptance_at=accepted,last_checked_address=ip,failures=0,next_attempt_at=now+c['interval_minutes']*60,last_error=None,retry_not_before=0)
            except Exception:
                failures=runtime.get('failures',0)+1;delay=max(c['interval_minutes']*60,min(86400,300*2**min(failures-1,8)));runtime.update(state='retrying',failures=failures,last_error='Address discovery, isolated driver or provider acceptance failed. Credentials and earlier acceptance are retained; inspect the local service privately.',next_attempt_at=now+delay,retry_not_before=now+delay)
            self.ctx.state.set(KEY,records)
        finally:self.lock.release()

    def health(self):
        from .health import fault
        return [fault(name,'warning','Dynamic DNS update needs attention',{'profile':name,'last_provider_acceptance_at':row['runtime'].get('last_provider_acceptance_at')}) for name,row in self.records().items() if row['config']['enabled'] and row['runtime'].get('state')=='retrying']
