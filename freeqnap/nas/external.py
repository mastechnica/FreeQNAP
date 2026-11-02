"""Identified USB storage, separately managed from internal/boot RAID.

No vendor RAID/SMART commands, automatic formatting, cross-enclosure MD arrays,
or sysfs removal. Linux-visible ext4/LUKS2 volumes only in this milestone.
"""
import hashlib
import contextlib
import json
import os
import re
import time
from pathlib import Path
from .common import canonical,name,secret
from .limits import require_ext4_size
from . import gpt,crypto_profiles
from .. import inventory
from ..state import atomic

COLUMNS='NAME,PATH,TYPE,SIZE,MODEL,SERIAL,WWN,TRAN,FSTYPE,UUID,PARTUUID,MOUNTPOINTS,RO'

def walk(row):
    yield row
    for child in row.get('children',[]):yield from walk(child)

def usb_probe(device,sysroot='/sys'):
    if not re.fullmatch(r'/dev/sd[a-z]+',str(device)):raise ValueError('Only an identified USB SCSI disk is supported')
    root=Path(sysroot);block=root/'class/block'/Path(device).name
    path=(block/'device').resolve(strict=True)
    usb=next((p for p in (path,*path.parents) if (p/'idVendor').exists() and (p/'idProduct').exists()),None)
    if not usb:raise ValueError('Device is not on a USB storage transport')
    def read(p,default=''):
        try:return p.read_text().strip()
        except OSError:return default
    interface=next((p for p in (path,*path.parents) if (p/'bInterfaceNumber').exists()),None)
    scsi=next((p.name for p in (path,*path.parents) if re.fullmatch(r'[0-9]+:[0-9]+:[0-9]+:[0-9]+',p.name)),None)
    serial=read(usb/'serial');vid=read(usb/'idVendor').lower();pid=read(usb/'idProduct').lower()
    if not re.fullmatch('[a-f0-9]{4}',vid) or not re.fullmatch('[a-f0-9]{4}',pid):raise ValueError('Invalid USB descriptor identity')
    stable={'vendor_id':vid,'product_id':pid,'serial':serial,'interface':read(interface/'bInterfaceNumber') if interface else '', 'channel':scsi.split(':')[1] if scsi else '', 'target':scsi.split(':')[2] if scsi else '', 'lun':scsi.split(':')[-1] if scsi else ''}
    enclosure={k:stable[k] for k in ('vendor_id','product_id','serial')}
    driver=(interface/'driver').resolve().name if interface and (interface/'driver').exists() else 'unknown'
    size=int(read(block/'size','0'))*512
    return {'identity':stable,'id':hashlib.sha256(canonical(stable)).hexdigest()[:32],
            'enclosure_id':hashlib.sha256(canonical(enclosure)).hexdigest()[:32],
            'stable':bool(serial and stable['interface'] and stable['lun']),
            'disk_sequence':read(block/'diskseq'),'port':usb.name,'product':read(usb/'product'),'manufacturer':read(usb/'manufacturer'),
            'speed_mbps':read(usb/'speed'),'driver':driver,'bytes':size,
            'profile_hint':'TR-004' if 'TR-004' in read(usb/'product').upper() else 'generic USB storage',
            'member_health':'Unavailable; no vendor pass-through commands issued'}

def attached(pool):
    record=pool.get('external') or {};current=usb_probe(record.get('disk_path',''))
    if current['identity']!=record.get('identity') or current['bytes']!=record.get('bytes') or current.get('disk_sequence')!=record.get('disk_sequence'):
        raise ValueError('USB enclosure/LUN identity or size changed; exports are unavailable')
    return current

def enclosures():
    rows=[]
    for node in Path('/sys/bus/usb/devices').glob('*'):
        try:
            if not (node/'idVendor').exists() or not any((p/'bInterfaceClass').read_text().strip()=='08' for p in node.glob(node.name+':*') if (p/'bInterfaceClass').exists()):continue
            def optional(field):
                try:return (node/field).read_text().strip()
                except OSError:return ''
            identity={k:optional(f) for k,f in (('vendor_id','idVendor'),('product_id','idProduct'),('serial','serial'))}
            rows.append({'id':hashlib.sha256(canonical(identity)).hexdigest()[:32],**identity,'product':optional('product'),'speed_mbps':optional('speed'),'port':node.name})
        except (OSError,ValueError):continue
    return rows

def filesystem_label(ident):
    """Keep readable ext4 labels without truncating distinguishing suffixes."""
    ident=name(ident)
    if len('FQ-'+ident)<=16:return 'FQ-'+ident
    if len(ident)<=16:return ident
    return ident[:9]+'-'+hashlib.sha256(ident.encode()).hexdigest()[:6]

class External:
    def __init__(self,ctx,collector=None,probe=usb_probe,path_validator=None):
        self.ctx=ctx;self.collect=collector or self.inventory;self.probe=probe
        self.fixture=probe is not usb_probe or path_validator is not None
        self.path_validator=path_validator or (lambda p:bool(re.fullmatch('/dev/sd[a-z]+',p)))
    def inventory(self):
        disks=json.loads(self.ctx.run('lsblk','-J','-b','-o',COLUMNS))['blockdevices']
        root=json.loads(self.ctx.run('findmnt','-J','-M','/','-o','UUID,SOURCE'))['filesystems'][0]
        return {'disks':disks,'root':root,'sampled_at':time.time(),'errors':[]}
    def discover(self,request=None):
        observed=self.collect();rows=[]
        if observed.get('errors') or not observed.get('root',{}).get('uuid') or not 0<=time.time()-observed['sampled_at']<120:raise ValueError('Fresh complete root/device inventory is required')
        for disk in observed['disks']:
            if disk.get('type')!='disk':continue
            try:usb=self.probe(disk['path'])
            except (OSError,ValueError):continue
            protected=any(r.get('uuid')==observed['root']['uuid'] or '/' in (r.get('mountpoints') or []) for r in walk(disk))
            rows.append({'id':usb['id'],'usb':usb,'disk':disk,'protected':protected,'install_target':False,
                         'eligible':usb['stable'] and not protected,'raid_mode':'Managed by enclosure; not inferred from volume count'})
        return {'enclosures':enclosures(),'devices':rows,'writes_performed':False,'vendor_commands_issued':False,'supported_managed_filesystems':['ext4','LUKS2/ext4'], 'format_never_automatic':True}
    def select(self,ident):
        if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{32}',ident):raise ValueError('Select a discovered USB enclosure/LUN')
        rows=[r for r in self.discover()['devices'] if r['id']==ident]
        if len(rows)!=1:raise ValueError('USB identity is missing or ambiguous')
        row=rows[0]
        if not row['eligible'] or not self.path_validator(row['disk']['path']):raise ValueError('A stable serial-numbered USB device, separate from the OS, is required')
        if row['usb']['bytes']!=int(row['disk']['size']):raise ValueError('USB capacity observations disagree')
        return row
    def idle(self,row,allowed_pools=()):
        disk=row['disk'];allowed=set(allowed_pools)
        for item in walk(disk):
            mounts=[m for m in item.get('mountpoints') or [] if m]
            if mounts:raise ValueError('External device has mounted filesystems; unmount/eject it first')
            if item is not disk and item.get('type') not in ('part',):raise ValueError('Device has active RAID/crypto/other holders')
            path=Path('/sys/class/block')/Path(item['path']).name/'holders'
            if path.exists() and any(path.iterdir()):raise ValueError('External device has active holders')
        for pool in self.ctx.config()['pools'].values():
            if pool.get('kind')=='usb' and pool['external']['id']==row['id'] and pool['name'] not in allowed:
                raise ValueError('This external LUN is already registered')
        swaps=self.ctx.run('swapon','--show','--noheadings','--raw','--output','NAME').splitlines()
        paths={r['path'] for r in walk(disk)}
        if any(s.strip() in paths for s in swaps):raise ValueError('External device is active swap')
    def stable_path(self,row):
        if self.fixture:return row['disk']['path']
        matches=sorted(p for p in Path('/dev/disk/by-id').glob('usb-*') if not re.search(r'-part[0-9]+$',p.name) and p.is_symlink() and p.resolve()==Path(row['disk']['path']))
        if not matches:raise ValueError('No stable USB by-id link exists; initialization is unavailable')
        return str(matches[0])
    def record(self,row,device):
        return {**row['usb'],'disk_path':row['disk']['path'],'device_path':device,'disk_serial':row['disk'].get('serial'),'wwn':row['disk'].get('wwn')}
    def import_idle(self,row,uuid):
        selected=[r for r in walk(row['disk']) if r.get('uuid')==uuid]
        if len(selected)!=1:raise ValueError('Selected external filesystem is missing or ambiguous')
        item=selected[0]
        if any(item.get('mountpoints') or []):raise ValueError('Selected external filesystem is already mounted')
        holders=Path('/sys/class/block')/Path(item['path']).name/'holders'
        if holders.exists() and any(holders.iterdir()):raise ValueError('Selected external filesystem has active holders')
        if item.get('children'):raise ValueError('Selected external filesystem has an active storage stack')
        for pool in self.ctx.config()['pools'].values():
            if pool.get('kind')=='usb' and uuid in (pool.get('filesystem_uuid'),pool.get('luks_uuid')):raise ValueError('This filesystem is already registered')
        swaps=self.ctx.run('swapon','--show','--noheadings','--raw','--output','NAME').splitlines()
        if item['path'] in [s.strip() for s in swaps]:raise ValueError('Selected external device is active swap')
        # Sibling partitions may remain mounted: import never repartitions or
        # formats the LUN, and only the chosen direct filesystem is opened.

    def import_plan(self,request):
        ident=name(request.get('name'));row=self.select(request.get('id'));self.import_idle(row,request.get('uuid'))
        if ident in self.ctx.config()['pools']:raise ValueError('Volume name already exists')
        selected=[r for r in walk(row['disk']) if r.get('uuid')==request.get('uuid') and r.get('fstype') in ('ext4','crypto_LUKS')]
        if len(selected)!=1:raise ValueError('Select one detected ext4/LUKS filesystem by its exact UUID')
        source=selected[0];require_ext4_size(source['size'])
        if not self.path_validator(row['disk']['path']) or not (source['path']==row['disk']['path'] or re.fullmatch(re.escape(row['disk']['path'])+('p' if row['disk']['path'][-1].isdigit() else '')+r'[0-9]+',source['path'])):raise ValueError('Filesystem is not a direct external disk or partition')
        # Refuse cloned duplicate filesystem UUIDs anywhere, including another LUN.
        allrows=self.collect()['disks']
        if sum(r.get('uuid')==source['uuid'] for d in allrows for r in walk(d))!=1:raise ValueError('Filesystem UUID is ambiguous')
        ro=request.get('read_only',True);auto=request.get('auto_mount',False)
        if not isinstance(ro,bool) or not isinstance(auto,bool):raise ValueError('Choose explicit mount options')
        if not ro and (row['disk'].get('ro') or source.get('ro')):raise ValueError('External device is read-only')
        body={'name':ident,'external':self.record(row,source['path']),'source':source,'disk_identity':row,'read_only':ro,'auto_mount':auto,
              'mountpoint':'/srv/freeqnap/volumes/'+ident,'encrypted':source['fstype']=='crypto_LUKS'}
        return self.ctx.plan('usb-import',body,'IMPORT USB '+ident)
    def import_volume(self,request):
        from .storage import Storage
        with self.ctx.lock():
            path,plan=self.ctx.reviewed(request,'usb-import');body=plan['body'];fresh=self.select(body['external']['id']);self.import_idle(fresh,body['source']['uuid'])
            source=[r for r in walk(fresh['disk']) if r.get('uuid')==body['source']['uuid']]
            if fresh!=body['disk_identity'] or len(source)!=1 or source[0]!=body['source']:raise ValueError('USB device/filesystem changed after review')
            self.ctx.consume(path,plan)
            pool={'name':body['name'],'kind':'usb','level':'External enclosure volume','external':body['external'],'mountpoint':body['mountpoint'],
                  'read_only':body['read_only'],'auto_mount':body['auto_mount'],'ejected':False,'encrypted':body['encrypted'],'imported':True,
                  'block_device':body['source']['path'],'filesystem_uuid':None if body['encrypted'] else body['source']['uuid'],
                  'luks_uuid':body['source']['uuid'] if body['encrypted'] else None,'hardware_raid_health':'unavailable'}
            if pool['encrypted'] and self.ctx.run('cryptsetup','luksDump','--dump-json-metadata',pool['block_device']).strip()=='':raise ValueError('Only existing LUKS2 volumes are supported')
            cfg=self.ctx.config();cfg['pools'][pool['name']]=pool;self.ctx.save(cfg)
            if not pool['encrypted']:Storage(self.ctx).mount(pool)
            return {'imported':pool['name'],'read_only':pool['read_only'],'requires_unlock':pool['encrypted'],'data_formatted':False}
    def create_plan(self,request):
        ident=name(request.get('name'));row=self.select(request.get('id'));self.idle(row)
        if ident in self.ctx.config()['pools']:raise ValueError('Volume name already exists')
        count=request.get('volume_count',1)
        if isinstance(count,bool) or not isinstance(count,int) or not 1<=count<=8:raise ValueError('Choose one to eight bounded external volumes')
        names=[ident] if count==1 else [name(ident+'-'+str(i+1)) for i in range(count)]
        if len({filesystem_label(n) for n in names})!=len(names):raise ValueError('Filesystem labels collide; choose a different volume name')
        if any(n in self.ctx.config()['pools'] for n in names):raise ValueError('An external volume name already exists')
        if row['disk']['size']<1024**3:raise ValueError('A data volume of at least 1 GiB is required')
        if any(item.get('ro') for item in walk(row['disk'])):raise ValueError('External device or partition is read-only; release its write protection before formatting')
        encrypted=request.get('encrypted',True)
        if not isinstance(encrypted,bool):raise ValueError('Choose encryption explicitly')
        profile=crypto_profiles.profile(request.get('encryption_profile',crypto_profiles.DEFAULT))
        if not encrypted and 'encryption_profile' in request:raise ValueError('Encryption profile applies only to an encrypted volume')
        dev=row['disk']['path']
        signatures=json.loads(self.ctx.run('wipefs','--json','--no-act',dev))
        geometry=json.loads(self.ctx.run('blockdev','--getss',dev));size=int(self.ctx.run('blockdev','--getsize64',dev))
        if geometry not in (512,4096) or size!=row['disk']['size']:raise ValueError('Unsupported or changed external geometry')
        proposed=gpt.layout(size,geometry,names)
        body={'name':ident,'layout':proposed,'disk_identity':row,'external':self.record(row,dev),'signatures':signatures,'sector_bytes':geometry,
              'encrypted':encrypted,'encryption_profile':profile['id'] if encrypted else None,'encryption_details':profile if encrypted else None,'mountpoint':'/srv/freeqnap/volumes/'+ident,'filesystem':'ext4','filesystem_profile':{'block_bytes':4096,'bytes_per_inode':262144,'reserved_percent':0},'auto_mount':False,'stable_device':self.stable_path(row),
              'review':'All existing partitions/data in this presented USB LUN will be erased. Enclosure RAID mode is not changed. Never mix this volume with the internal RAID.'}
        return self.ctx.plan('usb-create',body,'ERASE EXTERNAL '+ident)
    def create(self,request):
        from .storage import Storage
        with self.ctx.lock():
            path,plan=self.ctx.reviewed(request,'usb-create');body=plan['body'];row=self.select(body['external']['id']);self.idle(row)
            if len({filesystem_label(v['name']) for v in body['layout']['volumes']})!=len(body['layout']['volumes']):raise ValueError('Filesystem labels collide; review another name')
            for volume in body['layout']['volumes']:
                require_ext4_size(volume['bytes'])
                if volume['name'] in self.ctx.config()['pools']:raise ValueError('Volume name became occupied')
            if body['encrypted']:crypto_profiles.profile(body.get('encryption_profile',crypto_profiles.DEFAULT))
            device=row['disk']['path']
            if row!=body['disk_identity'] or json.loads(self.ctx.run('wipefs','--json','--no-act',device))!=body['signatures'] or int(self.ctx.run('blockdev','--getss',device))!=body['sector_bytes']:raise ValueError('External identity, signature or geometry changed after review')
            def guard():
                current=self.select(row['id'])
                if current['usb']['identity']!=row['usb']['identity'] or current['usb']['bytes']!=row['usb']['bytes'] or current['disk']['path']!=device or current['usb'].get('disk_sequence')!=row['usb'].get('disk_sequence'):raise ValueError('External device changed during initialization; stopping before the next write')
            stable_device=self.stable_path(row)
            if stable_device!=body['stable_device']:raise ValueError('Stable USB path changed since review')
            password=secret(request.get('secret')) if body['encrypted'] else None
            self.ctx.consume(path,plan);job=self.ctx.operation('usb-create',{'plan_id':plan['id'],'pool':body['name']})
            checkpoint={'job':job,'steps':[]};record=self.ctx.directory/'operations'/(job+'.json')
            def step(value):checkpoint['steps'].append({'step':value,'at':time.time()});atomic(record,checkpoint)
            step('mutation-begun');opened=False
            try:
                volumes=body['layout']['volumes']
                if len(volumes)>1:
                    guard();gpt.write(stable_device,body['layout'],self.ctx.directory/'external-preformat'/plan['id'],guard)
                else:
                    guard();self.ctx.run('wipefs','--all',stable_device);guard();self.ctx.run('sgdisk','--zap-all',stable_device)
                    guard();self.ctx.run('sgdisk','--new=1:0:0','--typecode=1:8300','--change-name=1:FREEQNAP_EXTERNAL',stable_device)
                self.ctx.run('partx','--update',device);self.ctx.run('udevadm','settle','--timeout=15');step('partitions-created')
                created=[]
                for v in volumes:
                    guard();partition=device+('p' if device[-1].isdigit() else '')+str(v['number'])
                    fresh=self.select(row['id']);parts=[r for r in walk(fresh['disk']) if r['path']==partition]
                    direct=[r for r in fresh['disk'].get('children',[]) if r['type']=='part']
                    if len(direct)!=len(volumes) or len(parts)!=1 or not parts[0].get('partuuid') or fresh['usb']['identity']!=row['usb']['identity']:raise ValueError('New external partition identity could not be verified')
                    if len(volumes)>1 and (parts[0]['partuuid']!=v['uuid'] or int(parts[0]['size'])!=v['bytes']):raise ValueError('Split partition UUID or size differs from reviewed layout')
                    require_ext4_size(parts[0]['size'])
                    pool={'name':v['name'],'group':body['name'],'kind':'usb','level':'External enclosure volume','external':self.record(fresh,partition),
                          'partition_uuid':parts[0]['partuuid'],'encrypted':body['encrypted'],'read_only':False,'auto_mount':False,'ejected':False,'mountpoint':'/srv/freeqnap/volumes/'+v['name'],'hardware_raid_health':'unavailable'}
                    partition_ref=partition if self.fixture else '/dev/disk/by-partuuid/'+parts[0]['partuuid']
                    if not self.fixture and Path(partition_ref).resolve()!=Path(partition):raise ValueError('Stable external partition link is not ready')
                    guard();self.ctx.run('wipefs','--all',partition_ref);step(v['name']+':partition-signatures-cleared')
                    block=partition_ref
                    if body['encrypted']:
                        guard();self.ctx.run(*crypto_profiles.format_args(body.get('encryption_profile',crypto_profiles.DEFAULT)),partition_ref,data=password,timeout=180)
                        pool['encryption_profile']=body.get('encryption_profile',crypto_profiles.DEFAULT)
                        pool['luks_uuid']=self.ctx.run('cryptsetup','luksUUID',partition_ref).strip();step(v['name']+':luks-created')
                        guard();self.ctx.run('cryptsetup','open','--type','luks2','--key-file','-',partition_ref,'freeqnap-'+pool['name'],data=password,timeout=180);opened=True;block='/dev/mapper/freeqnap-'+pool['name']
                    guard();self.ctx.run('mkfs.ext4','-q','-F','-b','4096','-i','262144','-m','0','-E','lazy_itable_init=1,lazy_journal_init=1','-L',filesystem_label(pool['name']),block,timeout=600);step(v['name']+':filesystem-created')
                    pool['filesystem_uuid']=self.ctx.run('blkid','-s','UUID','-o','value',block).strip();pool['block_device']=block
                    if not pool['filesystem_uuid']:raise ValueError('New filesystem UUID unavailable')
                    cfg=self.ctx.config();cfg['pools'][pool['name']]=pool;self.ctx.save(cfg);created.append(pool);step(v['name']+':volume-registered')
                for pool in created:Storage(self.ctx).mount(pool)
                result={'created':body['name'],'volumes':[p['name'] for p in created],'encrypted':body['encrypted'],'enclosure_raid_configuration_changed':False}
                self.ctx.state.finish(job,result=result);return result
            except Exception:
                self.ctx.state.finish(job,error='External initialization interrupted. Keep exact enclosure/LUN/partition evidence; no blind format retry.');raise
            finally:password=None
    def resolve(self,pool):
        row=self.select(pool['external']['id'])
        if row['usb']['identity']!=pool['external']['identity'] or row['usb']['bytes']!=pool['external']['bytes']:raise ValueError('External enclosure/LUN changed')
        key='uuid';value=pool.get('luks_uuid') if pool['encrypted'] else pool.get('filesystem_uuid')
        rows=[r for r in walk(row['disk']) if r.get(key)==value]
        if len(rows)!=1:raise ValueError('Registered external filesystem/LUKS identity is missing or ambiguous')
        if pool.get('partition_uuid') and rows[0].get('partuuid')!=pool['partition_uuid']:raise ValueError('External partition identity changed')
        pool['external']=self.record(row,rows[0]['path'])
        return rows[0]['path']
    def mount(self,request):
        from .storage import Storage
        with self.ctx.lock():
            pool=self.ctx.config()['pools'].get(name(request.get('pool')))
            if not pool or pool.get('kind')!='usb':raise ValueError('Choose an external volume')
            if pool['encrypted']:raise ValueError('Unlock the encrypted external volume in Storage')
            pool['block_device']=self.resolve(pool);pool['ejected']=False
            cfg=self.ctx.config();cfg['pools'][pool['name']]=pool;self.ctx.save(cfg);Storage(self.ctx).mount(pool)
            return {'mounted':pool['name']}
    def eject_plan(self,request):
        row=self.select(request.get('id'));enclosure=row['usb']['enclosure_id']
        rows=[r for r in self.discover()['devices'] if r['usb']['enclosure_id']==enclosure]
        pools=[p['name'] for p in self.ctx.config()['pools'].values() if p.get('kind')=='usb' and p['external']['enclosure_id']==enclosure]
        return self.ctx.plan('usb-eject',{'enclosure':enclosure,'devices':rows,'pools':pools,'review':'Stop dependent shares/media/downloads, unmount all registered volumes in this enclosure and flush. No force/lazy unmount; no vendor power/RAID command.'},'EJECT USB')
    def flush(self,device):
        self.ctx.run('blockdev','--flushbufs',device)
        try:
            self.ctx.run('sg_sync',device,timeout=60)
            return {'method':'scsi-sync','device_cache_flush_supported':True}
        except ValueError as error:
            # sg3_utils status 9 is specifically unsupported operation code.
            # Never treat medium/hardware errors, resets or write-back caches as safe.
            if not str(error).startswith('sg_sync failed (exit 9);') or not re.fullmatch(r'/dev/sd[a-z]+',device):raise
            policy=(Path('/sys/class/block')/Path(device).name/'queue/write_cache').read_text().strip()
            if policy!='write through':raise ValueError('Device cannot flush its cache; safe eject refused') from error
            return {'method':'reported-write-through-no-sync-opcode','device_cache_flush_supported':False}

    def eject(self,request,stop_services):
        with self.ctx.lock():
            path,plan=self.ctx.reviewed(request,'usb-eject');body=plan['body']
            fresh=[r for r in self.discover()['devices'] if r['usb']['enclosure_id']==body['enclosure']]
            if fresh!=body['devices']:raise ValueError('Enclosure/LUN state changed; review a fresh eject plan')
            if any(j['status'] in ('queued','running') for j in self.ctx.state.jobs()):raise ValueError('Wait for active operations before ejecting storage')
            registered=self.ctx.config()['pools'];allowed_mounts={p['mountpoint'] for p in registered.values() if p.get('kind')=='usb' and p['external']['enclosure_id']==body['enclosure']}
            for row in fresh:
                for item in walk(row['disk']):
                    if any(m and m not in allowed_mounts for m in item.get('mountpoints') or []):raise ValueError('Enclosure contains a mount outside FreeQNAP; eject refused')
            self.ctx.consume(path,plan);stop_services(body['pools'])
            for ident in body['pools']:
                pool=registered[ident]
                # Unmount a known filesystem even after its USB attachment vanished.
                # Do not follow a replacement/foreign overmount at this location.
                tree=json.loads(self.ctx.run('findmnt','-J','-o','TARGET,SOURCE,UUID,FSTYPE,FSROOT,OPTIONS'))['filesystems']
                mounts=[r for node in tree for r in walk(node) if r.get('target')==pool['mountpoint']]
                if mounts:
                    if any(r.get('uuid')!=pool.get('filesystem_uuid') or r.get('fstype')!='ext4' or r.get('fsroot')!='/' for r in mounts):raise ValueError('Foreign filesystem at external mountpoint; eject refused')
                    self.ctx.run('systemd-mount','--umount',pool['mountpoint'],timeout=90)
                if pool['encrypted'] and Path('/dev/mapper/freeqnap-'+ident).exists():self.ctx.run('cryptsetup','close','freeqnap-'+ident)
                pool['ejected']=True
            # Recheck unmounted/no-holder state after dependent services closed.
            flushes=[]
            for row in fresh:
                current=self.select(row['id']);self.idle(current,body['pools']);flushes.append({'id':row['id'],**self.flush(current['disk']['path'])})
            cfg=self.ctx.config()
            for ident in body['pools']:cfg['pools'][ident]=registered[ident]
            self.ctx.save(cfg)
            return {'safe_to_unplug':True,'device_powered_off':False,'enclosure_raid_configuration_changed':False,'flush':flushes}

    def file_view(self,request,*,registered_pool=False):
        from .files import Files,relative
        ident=name(request.get('pool'));pool=self.ctx.config()['pools'].get(ident)
        if not pool or not registered_pool and pool.get('kind')!='usb':raise ValueError('Choose a registered external volume')
        context=self.ctx
        class View(Files):
            @contextlib.contextmanager
            def directory(self,share_id,path=''):
                pool,mount=context.volume(ident)
                descriptor=os.open(mount,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                try:
                    device=os.fstat(descriptor).st_dev
                    if device!=mount.stat().st_dev:raise ValueError('External volume changed')
                    for component in relative(path):
                        child=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=descriptor)
                        os.close(descriptor);descriptor=child
                        if os.fstat(descriptor).st_dev!=device:raise ValueError('Nested mounts are not followed')
                    context.volume(ident)
                    yield descriptor,{},pool
                finally:os.close(descriptor)
        return View(self.ctx)
    def list_files(self,request,*,registered_pool=False):return self.file_view(request,registered_pool=registered_pool).list({'share':'external','path':request.get('path',''),'query':request.get('query',''),'offset':request.get('offset',0),'limit':request.get('limit',100)})
    def read_file(self,request,*,registered_pool=False):return self.file_view(request,registered_pool=registered_pool).read({'share':'external','path':request.get('path',''),'offset':request.get('offset',0),'count':request.get('count',512*1024)})
    def forget_plan(self,request):
        ident=name(request.get('pool'));pool=self.ctx.config()['pools'].get(ident)
        if not pool or pool.get('kind')!='usb':raise ValueError('Choose an external volume')
        self.can_forget(pool)
        return self.ctx.plan('usb-forget',{'pool':pool,'review':'Remove only this unmounted external volume registration. Data, encryption header, old snapshots and retained job history remain; their old pool references will be unavailable.'},'FORGET USB '+ident)
    def can_forget(self,pool):
        cfg=self.ctx.config();ident=pool['name']
        if any(row.get('pool')==ident for group in ('shares','repositories','libraries') for row in cfg[group].values()):raise ValueError('Remove dependent exports/repositories/libraries before forgetting the volume')
        settings=self.ctx.state.setting('downloads_settings')
        if settings and settings['pool']==ident:raise ValueError('Download settings/history still depend on this volume')
        if any(j['status'] in ('queued','running') for j in self.ctx.state.jobs()):raise ValueError('Wait for active operations')
        if Path('/dev/mapper/freeqnap-'+ident).exists():raise ValueError('Lock/eject the encrypted volume first')
        # findmnt exit 1 explicitly means absent; all other command failures fail closed.
        rows=json.loads(self.ctx.run('findmnt','-J','-o','TARGET'))['filesystems']
        def targets(row):
            yield row.get('target')
            for child in row.get('children',[]):yield from targets(child)
        if pool['mountpoint'] in {t for row in rows for t in targets(row)}:raise ValueError('Unmount/eject this volume first')
    def forget(self,request):
        with self.ctx.lock():
            path,plan=self.ctx.reviewed(request,'usb-forget');pool=plan['body']['pool'];cfg=self.ctx.config()
            if cfg['pools'].get(pool['name'])!=pool:raise ValueError('Volume registration changed since review')
            self.can_forget(pool);self.ctx.consume(path,plan);del cfg['pools'][pool['name']];self.ctx.save(cfg)
            return {'registration_removed':pool['name'],'data_deleted':False}
