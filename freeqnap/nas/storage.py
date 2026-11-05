"""Identity-bound region plans, native MD/LUKS/ext4 creation and manual unlock."""
import json
import math
import os
import re
import secrets
import time
from pathlib import Path
from .common import name, secret, json_run
from .limits import require_ext4_size
from . import gpt
from .. import inventory
from ..state import atomic

LEVELS = {'mirror': ('1', 2, 2), 'raid5': ('5', 3, 4),
          'raid6': ('6', 4, 4), 'raid10': ('10', 4, 4)}

def identity(disk):
    return {key: disk.get(key) for key in ('path', 'serial', 'wwn', 'size', 'model')}

def walk(row):
    yield row
    for child in row.get('children', []):
        yield from walk(child)

class Storage:
    def __init__(self, context, collector=inventory.collect, internal_validator=None):
        self.ctx = context
        self.collect = collector
        self.internal_validator = internal_validator or self.internal_sata

    @staticmethod
    def internal_sata(device):
        sysdev = Path('/sys/class/block') / Path(device).name / 'device'
        return sysdev.exists() and any(re.fullmatch('ata[0-9]+', part) for part in sysdev.resolve().parts)

    def regions(self, request, single=False):
        data = self.collect()
        if data['errors'] or not data['root'].get('uuid') or not 0 <= time.time() - data['sampled_at'] < 120:
            raise ValueError('Fresh complete disk and root inventory is required')
        serials = request.get('disks', [])
        level = request.get('level')
        if level not in LEVELS or not isinstance(serials, list) or len(set(serials)) != len(serials) or not (1 if single else LEVELS[level][1]) <= len(serials) <= (1 if single else LEVELS[level][2]):
            raise ValueError('Select the required number of distinct disks')
        result = []
        for serial in serials:
            matches = [disk for disk in data['disks'] if disk['type'] == 'disk' and disk.get('serial') == serial]
            if len(matches) != 1:
                raise ValueError('Missing or ambiguous disk identity')
            disk = matches[0]
            if not disk.get('wwn') or not re.fullmatch('/dev/sd[a-z]+', disk['path']):
                raise ValueError('Internal SATA disk with serial and WWN required')
            if not self.internal_validator(disk['path']):
                raise ValueError('Pool creation accepts identified internal SATA only')
            is_os = any(row.get('uuid') == data['root']['uuid'] for row in walk(disk))
            table = json.loads(self.ctx.run('sfdisk', '--json', disk['path']))['partitiontable']
            if table.get('label') != 'gpt' or table.get('sectorsize') != 512:
                raise ValueError('A supported 512-byte-sector GPT layout is required; inspect/import other disks separately')
            partitions = table.get('partitions', [])
            if is_os:
                if request.get('allocation') != 'free-tail':
                    raise ValueError('OS disks require an explicit free-tail plan; never whole-disk erase')
                expected = {disk['path'] + '1', disk['path'] + '2'}
                if {p['node'] for p in partitions} != expected:
                    raise ValueError('OS disk must contain only the known boot/root partitions')
                if any(row.get('mountpoints') and '/' not in row['mountpoints'] for row in walk(disk) if row.get('uuid') != data['root']['uuid']):
                    raise ValueError('Unexpected active OS-disk partition')
                number = 3
            else:
                if partitions or disk.get('children') or disk.get('fstype') or any(any(row.get('mountpoints') or []) for row in walk(disk)):
                    raise ValueError('Selected data disk is not blank and unused; import or clear it explicitly first')
                number = 1
            start = max([2048] + [p['start'] + p['size'] for p in partitions])
            start = math.ceil(start / 2048) * 2048
            end = int(table['lastlba'])
            if end - start < 2 * 1024**2:
                raise ValueError('Less than 1 GiB of unused tail capacity')
            signatures = self.ctx.run('wipefs', '--json', '--no-act', disk['path'])
            result.append({'disk': identity(disk), 'os_disk': is_os, 'partition': disk['path'] + str(number),
                           'number': number, 'start': start, 'end': end, 'table': table,
                           'disk_signatures': json.loads(signatures)})
        return data['root']['uuid'], result

    def plan(self, request):
        pool_name = name(request.get('name'))
        if pool_name in self.ctx.config()['pools']:
            raise ValueError('Pool name already exists')
        root_uuid, regions = self.regions(request)
        body = {'name': pool_name, 'level': request['level'], 'allocation': request.get('allocation', 'blank-disks'),
                'disks': request['disks'], 'root_uuid': root_uuid, 'regions': regions,
                'encrypted': bool(request.get('encrypted')), 'filesystem': 'ext4',
                'mountpoint': '/srv/freeqnap/volumes/' + pool_name,
                'usable_bytes_before_overhead': min((r['end'] - r['start'] + 1) * 512 for r in regions) *
                 {'mirror': 1, 'raid5': len(regions) - 1, 'raid6': len(regions) - 2, 'raid10': len(regions) // 2}[request['level']]}
        count=request.get('volume_count',1)
        if isinstance(count,bool) or count not in (1,2):raise ValueError('Choose one or two data filesystems')
        body['volume_count']=count
        if count==2:
            names=[name(pool_name+'-'+str(i)) for i in (1,2)]
            if any(n in self.ctx.config()['pools'] for n in names):raise ValueError('A split volume name already exists')
            # Explicit bounded MD component size makes the reviewed final geometry exact.
            component=(min((r['end']-r['start']+1)*512 for r in regions)-128*1024**2)//(512*1024)*(512*1024)
            if component<1024**3:raise ValueError('Insufficient space for two data filesystems')
            factor={'mirror':1,'raid5':len(regions)-1,'raid6':len(regions)-2,'raid10':len(regions)//2}[body['level']]
            body['component_bytes']=component;body['usable_bytes_before_overhead']=component*factor
            body['layout']=gpt.layout(component*factor,512,names)
            for volume in body['layout']['volumes']:require_ext4_size(volume['bytes'],pointer_bytes=4,page_bytes=4096)
            body['review']='One internal MD array with two bounded GPT filesystems. Existing OS partitions are preserved. Both filesystems share the same RAID failure domain; initial sync and recovery tests remain required.'
        else:require_ext4_size(body['usable_bytes_before_overhead'])
        return self.ctx.plan('pool-create', body, 'CREATE ' + pool_name)

    def create(self, request):
        with self.ctx.lock():
            path, plan = self.ctx.reviewed(request, 'pool-create')
            body = plan['body']
            from ..access_scope import current
            if body['encrypted'] and not current():raise ValueError('Sign in before creating a private encrypted volume')
            if body.get('volume_count',1)==2:
                for volume in body['layout']['volumes']:
                    require_ext4_size(volume['bytes'],pointer_bytes=4,page_bytes=4096)
                    if volume['name'] in self.ctx.config()['pools']:raise ValueError('A split volume name became occupied')
            else:require_ext4_size(body['usable_bytes_before_overhead'])
            root_uuid, fresh = self.regions(body)
            if fresh != body['regions'] or root_uuid != body['root_uuid']:
                raise ValueError('Disk, region, signature or OS identity changed since review')
            password = secret(request.get('secret')) if body['encrypted'] else None
            self.ctx.consume(path, plan)
            operation = self.ctx.operation('pool-create', {'plan_id': plan['id'], 'pool': body['name']})
            journal = {'operation': operation, 'plan': plan['id'], 'steps': []}
            checkpoint = self.ctx.directory / 'operations' / (operation + '.json')
            def done(step):
                journal['steps'].append({'step': step, 'at': time.time()})
                atomic(checkpoint, journal)
            done('mutation-begun')
            try:
                for region in fresh:
                    device = region['disk']['path']
                    backup = self.ctx.directory / 'operations' / (operation + '-' + Path(device).name + '.gpt')
                    self.ctx.run('sgdisk', '--backup=' + str(backup), device)
                    backup.chmod(0o600)
                    self.ctx.run('sgdisk', f"--new={region['number']}:{region['start']}:{region['end']}",
                                 f"--typecode={region['number']}:fd00", f"--change-name={region['number']}:freeqnap-{body['name']}", device)
                    done('partition-table-written:' + device)
                    self.ensure_partition(region)
                    actual = json.loads(self.ctx.run('sfdisk', '--json', device))['partitiontable']['partitions']
                    actual = next(p for p in actual if p['node'] == region['partition'])
                    if actual['start'] != region['start'] or actual['size'] != region['end'] - region['start'] + 1:
                        raise ValueError('Created partition does not match the reviewed extent')
                    self.ctx.run('wipefs', '--all', region['partition'])
                    done('partition-prepared:' + region['partition'])
                md = '/dev/md/fq-' + body['name']
                self.ctx.run('mdadm', '--create', md, *(['--size='+str(body['component_bytes']//1024),'--data-offset=128M'] if body.get('volume_count')==2 else []), '--metadata=1.2', '--level=' + LEVELS[body['level']][0],
                             '--raid-devices=' + str(len(fresh)), '--bitmap=internal', '--homehost=freeqnap',
                             '--name=fq-' + body['name'], '--run', *[r['partition'] for r in fresh], timeout=90)
                done('array-created')
                detail = dict(line.split('=', 1) for line in self.ctx.run('mdadm', '--detail', '--export', md).splitlines() if '=' in line)
                if body.get('volume_count')==2:
                    return self.create_split(body,fresh,md,detail,operation,done,password)
                pool = {'name': body['name'], 'md_device': md, 'md_uuid': detail['MD_UUID'],
                        'regions': fresh, 'encrypted': body['encrypted'], 'mountpoint': body['mountpoint'],
                        'created_at': time.time(), 'operation': operation, 'level': body['level']}
                config = self.ctx.config();config['pools'][pool['name']] = pool;self.ctx.save(config)
                device = md
                if password is not None:
                    self.ctx.run('cryptsetup', 'luksFormat', '--type', 'luks2', '--batch-mode', '--cipher', 'aes-xts-plain64',
                                 '--key-size', '512', '--pbkdf', 'argon2id', '--pbkdf-memory', '131072',
                                 '--pbkdf-parallel', '2', '--iter-time', '2000', '--key-file', '-', md, data=password, timeout=180)
                    pool['luks_uuid'] = self.ctx.run('cryptsetup', 'luksUUID', md).strip()
                    config['pools'][pool['name']] = pool;self.ctx.save(config)
                    done('luks-header-created')
                    mapping = 'freeqnap-' + pool['name']
                    self.ctx.run('cryptsetup', 'open', '--type', 'luks2', '--key-file', '-', md, mapping, data=password, timeout=90)
                    device = '/dev/mapper/' + mapping
                self.ctx.run('mkfs.ext4', '-q', '-L', 'fq-' + pool['name'], device, timeout=180)
                pool['filesystem_uuid'] = self.ctx.run('blkid', '-s', 'UUID', '-o', 'value', device).strip()
                pool['block_device'] = device
                config['pools'][pool['name']] = pool;self.ctx.save(config)
                done('filesystem-created')
                from ..access_scope import claim
                claim(self.ctx,pool)
                self.mount(pool)
                done('mounted')
                self.ctx.state.finish(operation, result={'pool': pool['name'], 'initial_sync_must_be_checked': True})
                return {'operation': operation, 'pool': pool, 'initial_sync_must_be_checked': True}
            except Exception:
                self.ctx.state.finish(operation, error='Interrupted or failed storage mutation; inspect the durable operation ledger before reconciliation. Do not retry creation.')
                raise
            finally:
                password = None

    @staticmethod
    def kernel_partition_matches(region,sysroot=Path('/sys/class/block')):
        path=Path(sysroot)/Path(region['partition']).name
        if not path.exists():return False
        if int((path/'start').read_text())!=region['start'] or int((path/'size').read_text())!=region['end']-region['start']+1:raise ValueError('Kernel partition extent differs from reviewed GPT')
        return True

    def ensure_partition(self,region):
        # sgdisk can notify udev on an unused disk; mounted OS disks need BLKPG.
        # Never treat a generic partx error as success: prove the exact extent.
        if self.kernel_partition_matches(region):return
        try:self.ctx.run('partx','--add','--nr',str(region['number']),region['disk']['path'])
        except ValueError:
            if not self.kernel_partition_matches(region):raise
        self.ctx.run('udevadm','settle','--timeout=15')
        if not self.kernel_partition_matches(region):raise ValueError('Reviewed kernel partition is unavailable')

    def create_split(self,body,regions,md,detail,operation,done,password):
        def guard():
            observed=self.collect()
            if observed['errors'] or observed['root'].get('uuid')!=body['root_uuid']:raise ValueError('OS identity changed during split creation')
            for region in regions:
                matches=[d for d in observed['disks'] if identity(d)==region['disk']]
                if len(matches)!=1 or not self.internal_validator(matches[0]['path']):raise ValueError('Internal member identity changed during split creation')
            actual=dict(line.split('=',1) for line in self.ctx.run('mdadm','--detail','--export',md).splitlines() if '=' in line)
            if actual['MD_UUID']!=detail['MD_UUID'] or int(self.ctx.run('blockdev','--getsize64',md))!=body['layout']['bytes']:raise ValueError('Created array geometry or UUID differs from review')
        self.ctx.state.set('array_creation:'+operation,{'md_uuid':detail['MD_UUID'],'md_device':md,'regions':regions,'layout':body['layout'],'incomplete':True})
        guard();gpt.write(md,body['layout'],self.ctx.directory/'operations'/(operation+'-array-gpt'),guard)
        self.ctx.run('partx','--update',md);self.ctx.run('udevadm','settle','--timeout=15');done('array-gpt-created')
        created=[]
        for volume in body['layout']['volumes']:
            guard();pool={'name':volume['name'],'group':body['name'],'md_device':md,'md_uuid':detail['MD_UUID'],'regions':regions,'encrypted':body['encrypted'],'mountpoint':'/srv/freeqnap/volumes/'+volume['name'],'created_at':time.time(),'operation':operation,'level':body['level'],'partition_uuid':volume['uuid'],'array_partition':volume,'array_geometry_bytes':body['layout']['bytes']}
            device=self.data_device(pool);guard();self.ctx.run('wipefs','--all',device)
            if password is not None:
                guard();self.ctx.run('cryptsetup','luksFormat','--type','luks2','--batch-mode','--cipher','aes-xts-plain64','--key-size','512','--pbkdf','argon2id','--pbkdf-memory','131072','--pbkdf-parallel','2','--iter-time','2000','--key-file','-',device,data=password,timeout=180)
                pool['luks_uuid']=self.ctx.run('cryptsetup','luksUUID',device).strip();done(volume['name']+':luks-created')
                cfg=self.ctx.config();cfg['pools'][pool['name']]=pool;self.ctx.save(cfg)
                self.ctx.run('cryptsetup','open','--type','luks2','--key-file','-',device,'freeqnap-'+pool['name'],data=password,timeout=90);device='/dev/mapper/freeqnap-'+pool['name']
            guard();self.ctx.run('mkfs.ext4','-q','-b','4096','-i','262144','-m','0','-E','lazy_itable_init=1,lazy_journal_init=1','-L',('fq-'+pool['name'])[:16],device,timeout=600)
            pool['filesystem_uuid']=self.ctx.run('blkid','-s','UUID','-o','value',device).strip();pool['block_device']=device
            if not pool['filesystem_uuid']:raise ValueError('New filesystem UUID unavailable')
            cfg=self.ctx.config();cfg['pools'][pool['name']]=pool;self.ctx.save(cfg);created.append(pool);done(volume['name']+':filesystem-registered')
        from ..access_scope import claim
        for pool in created:claim(self.ctx,pool);self.mount(pool);done(pool['name']+':mounted')
        self.ctx.state.set('array_creation:'+operation,{'md_uuid':detail['MD_UUID'],'volumes':[p['name'] for p in created],'incomplete':False})
        result={'operation':operation,'volumes':[p['name'] for p in created],'md_uuid':detail['MD_UUID'],'initial_sync_must_be_checked':True}
        self.ctx.state.finish(operation,result=result);return result

    def data_device(self,pool):
        base=self.array_device(pool)
        if not pool.get('array_partition'):return base
        part=pool['array_partition'];rows=json.loads(self.ctx.run('lsblk','--json','--tree','--bytes','--output','PATH,TYPE,SIZE,PARTUUID,START',base))['blockdevices']
        if len(rows)!=1 or Path(rows[0]['path']).resolve()!=Path(base).resolve():raise ValueError('Array partition parent changed')
        candidates=[r for r in rows[0].get('children',[]) if r.get('type')=='part' and r.get('partuuid')==pool['partition_uuid']]
        if len(candidates)!=1 or int(candidates[0]['size'])!=part['bytes'] or int(candidates[0]['start'])*512!=part['start_bytes']:raise ValueError('Exact array partition identity/extent unavailable')
        ref='/dev/disk/by-partuuid/'+pool['partition_uuid']
        # Some Debian udev versions do not create by-partuuid links for MD partitions.
        # The recorded GPT UUID/extent and exact assembled parent remain mandatory.
        candidate=candidates[0]['path']
        if self.ctx.run('blkid','-s','PARTUUID','-o','value',candidate).strip()!=pool['partition_uuid']:raise ValueError('Array partition UUID changed')
        if Path(ref).exists():
            if Path(ref).resolve()!=Path(candidate).resolve():raise ValueError('Stable array partition link changed')
            return ref
        return candidate

    def mount(self, pool):
        from ..access_scope import claim,current,check
        if pool.get('encrypted'):
            lease=self.ctx.state.setting('volume-owner:'+pool['name'],{})
            check(self.ctx,pool,content=True)
        target = Path(pool['mountpoint'])
        target.mkdir(mode=0o000, parents=True, exist_ok=True)
        existing = self.ctx.run('findmnt', '-J', '-o', 'TARGET,UUID')
        mounts=[r for row in json.loads(existing)['filesystems'] for r in walk(row) if r.get('target')==str(target)]
        if mounts:
            if any(row.get('uuid')!=pool['filesystem_uuid'] for row in mounts):raise ValueError('Mountpoint already contains another filesystem')
            self.ctx.volume(pool['name']);return
        target.chmod(0o000)
        device = pool['block_device']
        if self.ctx.run('blkid', '-s', 'UUID', '-o', 'value', device).strip() != pool['filesystem_uuid']:
            raise ValueError('Filesystem identity changed')
        options='nodev,nosuid,noexec'+(',ro,noload' if pool.get('read_only') else '')
        self.ctx.run('systemd-mount', '--collect', '--type=ext4', '--options='+options, device, str(target),timeout=90)
        self.ctx.volume(pool['name'])
        if not pool.get('read_only'):target.chmod(0o700 if pool.get('encrypted') else 0o755)

    def unlock(self, request):
        from ..access_scope import current
        if not current():raise ValueError('Sign in to unlock a private encrypted volume')
        with self.ctx.lock():
            pool = self.ctx.config()['pools'].get(name(request.get('pool')))
            if not pool or not pool['encrypted'] or (not pool.get('filesystem_uuid') and not pool.get('imported')):
                raise ValueError('Choose a completely initialized encrypted pool')
            md = self.data_device(pool)
            if self.ctx.run('cryptsetup', 'luksUUID', md).strip() != pool['luks_uuid']:
                raise ValueError('Encrypted-volume identity changed')
            data = secret(request.get('secret'), existing=True)
            args=['cryptsetup','open','--type','luks2','--key-file','-']
            if pool.get('read_only'):args.append('--readonly')
            self.ctx.run(*args,md,'freeqnap-'+pool['name'],data=data,timeout=90)
            try:
                pool['block_device']='/dev/mapper/freeqnap-'+pool['name']
                if not pool.get('filesystem_uuid'):
                    if self.ctx.run('blkid','-s','TYPE','-o','value',pool['block_device']).strip()!='ext4':raise ValueError('Imported encrypted filesystem is unsupported; never format it')
                    pool['filesystem_uuid']=self.ctx.run('blkid','-s','UUID','-o','value',pool['block_device']).strip()
                    config=self.ctx.config();config['pools'][pool['name']]=pool;self.ctx.save(config)
                if pool.get('kind')=='usb':
                    pool['ejected']=False
                    config=self.ctx.config();config['pools'][pool['name']]=pool;self.ctx.save(config)
                from ..access_scope import claim
                claim(self.ctx,pool)
                self.mount(pool)
            except Exception:
                self.ctx.run('cryptsetup', 'close', 'freeqnap-' + pool['name']);raise
            return {'unlocked': True, 'pool': pool['name']}

    def lock(self, request, stop_services):
        with self.ctx.lock():
            pool, target = self.ctx.volume(name(request.get('pool')))
            if not pool['encrypted']:
                raise ValueError('The selected pool is not encrypted')
            from .volume_leases import idle
            idle(self.ctx,[pool['filesystem_uuid']])
            stop_services()
            self.ctx.run('systemd-mount', '--umount', str(target),timeout=90)  # Never force/lazy-unmount active writers.
            target.chmod(0o000)
            self.ctx.run('cryptsetup', 'close', 'freeqnap-' + pool['name'])
            return {'locked': True, 'pool': pool['name']}

    @staticmethod
    def normalized_uuid(value):
        return re.sub('[^a-f0-9]', '', value.lower())

    def array_device(self, pool):
        if pool.get('kind')=='usb':
            from .external import External
            return External(self.ctx).resolve(pool)
        for path in Path('/sys/class/block').glob('md*/md/uuid'):
            if self.normalized_uuid(path.read_text()) == self.normalized_uuid(pool['md_uuid']):
                return '/dev/' + path.parent.parent.name
        raise ValueError('The exact registered array is not assembled')

    def inspect_array(self, pool):
        if pool.get('kind')=='usb':raise ValueError('External hardware RAID membership/health is not managed by Linux MD')
        device = self.array_device(pool)
        detail = dict(line.split('=', 1) for line in self.ctx.run('mdadm', '--detail', '--export', device).splitlines() if '=' in line)
        if self.normalized_uuid(detail['MD_UUID']) != self.normalized_uuid(pool['md_uuid']):
            raise ValueError('Array identity changed')
        directory = Path('/sys/class/block') / Path(device).name / 'md'
        return {'device': device, 'state': (directory/'array_state').read_text().strip(),
                'degraded': int((directory/'degraded').read_text()),
                'sync_action': (directory/'sync_action').read_text().strip(),
                'members': ['/dev/'+p.name for p in (directory.parent/'slaves').iterdir()],
                'mismatch_count': int((directory/'mismatch_cnt').read_text()),
                'sync_progress':self.sync_progress((directory/'sync_completed').read_text()),
                'sync_speed_kib_per_second':(directory/'sync_speed').read_text().strip(),
                'raid_disks':int((directory/'raid_disks').read_text())}

    @staticmethod
    def sync_progress(value):
        match=re.fullmatch(r'\s*(\d+)\s*/\s*(\d+)\s*',value)
        if not match:return None
        done,total=map(int,match.groups())
        if total<=0 or done>total:return None
        return {'completed_sectors':done,'total_sectors':total,'percent':round(done*100/total,2)}

    def discover(self, request=None):
        observed = self.collect()
        if observed['errors']:raise ValueError('Complete disk inventory is required')
        groups = {}
        root_uuid = observed['root']['uuid']
        known = {self.normalized_uuid(p['md_uuid']) for p in self.ctx.config()['pools'].values() if p.get('md_uuid')}
        for disk in observed['disks']:
            if disk.get('type') != 'disk' or not disk.get('serial') or not disk.get('wwn') or not self.internal_validator(disk['path']):continue
            for child in disk.get('children', []):
                if child.get('type') != 'part' or any(r.get('uuid') == root_uuid for r in walk(child)):
                    continue
                if any(any(r.get('mountpoints') or []) for r in walk(child)):continue
                try:
                    raw=self.ctx.run('mdadm','--examine','--export',child['path'])
                    fields=dict(line.split('=',1) for line in raw.splitlines() if '=' in line)
                    ident=fields['MD_UUID']
                    if self.normalized_uuid(ident) in known:continue
                    if fields.get('MD_LEVEL') not in ('raid1','raid5','raid6','raid10'):continue
                    group=groups.setdefault(ident,{'uuid':ident,'level':fields['MD_LEVEL'],'expected_devices':int(fields['MD_DEVICES']),'members':[]})
                    group['members'].append({'path':child['path'],'disk':identity(disk),'member_uuid':fields.get('MD_DEV_UUID')})
                except (ValueError,KeyError):continue
        return {'arrays':list(groups.values()),'writes_performed':False}

    def import_plan(self, request):
        pool_name=name(request.get('name'))
        if pool_name in self.ctx.config()['pools']:raise ValueError('Pool name already exists')
        candidate=next((a for a in self.discover()['arrays'] if a['uuid']==request.get('uuid')),None)
        if not candidate:raise ValueError('Array is missing, active, protected or changed')
        if len({m['disk']['wwn'] for m in candidate['members']})!=len(candidate['members']):
            raise ValueError('Duplicate member identities')
        read_only=request.get('read_only') is True
        if len(candidate['members'])!=candidate['expected_devices'] and not read_only:
            raise ValueError('An incomplete array may only be imported read-only for recovery')
        return self.ctx.plan('pool-import',{'name':pool_name,'array':candidate,'read_only':read_only},'IMPORT '+pool_name)

    def import_array(self, request):
        with self.ctx.lock():
            path,plan=self.ctx.reviewed(request,'pool-import');body=plan['body']
            fresh=next((a for a in self.discover()['arrays'] if a['uuid']==body['array']['uuid']),None)
            if fresh!=body['array']:raise ValueError('Import member metadata changed')
            self.ctx.consume(path,plan)
            md='/dev/md/fq-'+body['name']
            args=['mdadm','--assemble',md,'--uuid='+fresh['uuid'],'--run']
            if body['read_only']:args.append('--readonly')
            self.ctx.run(*args,*[m['path'] for m in fresh['members']],timeout=90)
            kind=self.ctx.run('blkid','-s','TYPE','-o','value',md).strip()
            if kind not in ('ext4','crypto_LUKS'):raise ValueError('Imported array is assembled but filesystem is unsupported; no format was attempted')
            pool={'name':body['name'],'md_uuid':fresh['uuid'],'md_device':md,'level':fresh['level'],
                  'mountpoint':'/srv/freeqnap/volumes/'+body['name'],'encrypted':kind=='crypto_LUKS',
                  'read_only':body['read_only'],'imported':True,'members':fresh['members'],'created_at':time.time()}
            if pool['encrypted']:pool['luks_uuid']=self.ctx.run('cryptsetup','luksUUID',md).strip()
            else:
                pool['filesystem_uuid']=self.ctx.run('blkid','-s','UUID','-o','value',md).strip();pool['block_device']=md
            config=self.ctx.config();config['pools'][pool['name']]=pool;self.ctx.save(config)
            if not pool['encrypted']:self.mount(pool)
            return {'imported':pool,'filesystem_formatted':False}

    def check(self, request):
        pool=self.ctx.config()['pools'].get(name(request.get('pool')))
        if not pool:raise ValueError('Unknown pool')
        info=self.inspect_array(pool)
        if info['degraded'] or info['sync_action']!='idle':raise ValueError('A complete, idle array is required before a read consistency check')
        path=Path('/sys/class/block')/Path(info['device']).name/'md/sync_action'
        path.write_text('check\n')
        return {'check_started':True,'repair_requested':False}

    def replacement_plan(self, request):
        pool=self.ctx.config()['pools'].get(name(request.get('pool')))
        if not pool or not pool.get('regions'):raise ValueError('Choose a locally created pool with recorded region identities')
        info=self.inspect_array(pool)
        if info['sync_action']!='idle':raise ValueError('Wait for synchronization to finish')
        old=next((r for r in pool['regions'] if r['partition']==request.get('member')),None)
        if not old:raise ValueError('Select an exact recorded member')
        if old['partition'] in info['members'] and info['degraded']:
            raise ValueError('A degraded array cannot lose another present member through this workflow')
        if request.get('serial') in {r['disk']['serial'] for r in pool['regions']}:
            raise ValueError('Replacement must have a distinct, unused disk identity')
        probe={'disks':[request.get('serial')],'level':'mirror','allocation':'free-tail'}
        root,regions=self.regions(probe,single=True)
        replacement=regions[0]
        minimum=min(r['end']-r['start']+1 for r in pool['regions'])
        if replacement['end']-replacement['start']+1<minimum:raise ValueError('Replacement extent is smaller than the current members')
        return self.ctx.plan('member-replace',{'pool':pool['name'],'old':old,'replacement':replacement,'array':info,'root_uuid':root},
                             'REPLACE '+pool['name']+' '+old['disk']['serial'])

    def replace(self, request):
        with self.ctx.lock():
            path,plan=self.ctx.reviewed(request,'member-replace');body=plan['body'];pool=self.ctx.config()['pools'][body['pool']]
            if self.inspect_array(pool)!=body['array']:raise ValueError('Array state changed since review')
            _,regions=self.regions({'disks':[body['replacement']['disk']['serial']],'level':'mirror','allocation':'free-tail'},single=True)
            if regions[0]!=body['replacement']:raise ValueError('Replacement disk or free region changed')
            self.ctx.consume(path,plan);operation=self.ctx.operation('member-replace',{'plan_id':plan['id'],'pool':pool['name']})
            new=body['replacement'];md=body['array']['device']
            try:
                self.ctx.run('sgdisk',f"--new={new['number']}:{new['start']}:{new['end']}",f"--typecode={new['number']}:fd00",new['disk']['path'])
                self.ctx.run('partx','--add','--nr',str(new['number']),new['disk']['path']);self.ctx.run('udevadm','settle','--timeout=15')
                self.ctx.run('wipefs','--all',new['partition'])
                # Prepare the replacement while the current healthy members still serve data.
                # Fail/remove only the exact still-present recorded member, before adding a spare.
                if body['old']['partition'] in body['array']['members']:
                    fields=dict(line.split('=',1) for line in self.ctx.run('mdadm','--examine','--export',body['old']['partition']).splitlines() if '=' in line)
                    if self.normalized_uuid(fields['MD_UUID'])!=self.normalized_uuid(pool['md_uuid']):raise ValueError('Old member changed identity')
                    self.ctx.run('mdadm',md,'--fail',body['old']['partition'])
                    self.ctx.run('mdadm',md,'--remove',body['old']['partition'])
                self.ctx.run('mdadm',md,'--add',new['partition'])
                config=self.ctx.config();target=config['pools'][pool['name']]
                for target in config['pools'].values():
                    if target.get('md_uuid')==pool.get('md_uuid'):target['regions']=[new if r['partition']==body['old']['partition'] else r for r in target['regions']]
                self.ctx.save(config);result={'replacement_added':True,'pool':pool['name'],'rebuild_must_finish':True}
                self.ctx.state.finish(operation,result=result);return result
            except Exception:
                self.ctx.state.finish(operation,error='Replacement interrupted; preserve the exact array/member evidence and reconcile. Do not blindly retry.')
                raise

    def startup(self):
        """Exact recorded UUID/member assembly only. Encrypted pools stay locked."""
        errors=[]
        disks=self.collect()
        for pool in self.ctx.config()['pools'].values():
            try:
                if pool.get('kind')=='usb':
                    if not pool.get('encrypted') and pool.get('auto_mount') and not pool.get('ejected'):
                        from .external import External
                        pool['block_device']=External(self.ctx).resolve(pool)
                        cfg=self.ctx.config();cfg['pools'][pool['name']]=pool;self.ctx.save(cfg);self.mount(pool)
                    continue
                if not pool.get('filesystem_uuid') and not pool.get('imported'):continue
                try:self.array_device(pool)
                except ValueError:
                    members=[]
                    records=pool.get('regions',pool.get('members',[]))
                    for record in records:
                        original=record['disk'];matches=[d for d in disks['disks'] if d.get('serial')==original['serial'] and d.get('wwn')==original['wwn'] and d.get('size')==original['size']]
                        if len(matches)!=1:raise ValueError('A recorded data member is missing or changed; manual recovery required')
                        number=record.get('number') or int(re.search(r'(\d+)$',record['path'])[1])
                        members.append(matches[0]['path']+str(number))
                    args=['mdadm','--assemble','/dev/md/fq-'+pool['name'],'--uuid='+pool['md_uuid']]
                    if pool.get('read_only'):args+=['--readonly','--run']
                    self.ctx.run(*args,*members,timeout=60)
                if not pool['encrypted']:
                    if self.ctx.run('blockdev','--getro',self.array_device(pool)).strip()=='1' and not pool.get('read_only'):
                        raise ValueError('Array is in manual read-only recovery; resume writes only through a separately confirmed recovery plan')
                    # MD partitions can exist before udev has populated PARTUUID.
                    # Settle discovery, then retain every UUID/extent check below.
                    self.ctx.run('udevadm','settle','--timeout=15',timeout=20)
                    pool['block_device']=self.data_device(pool);cfg=self.ctx.config();cfg['pools'][pool['name']]=pool;self.ctx.save(cfg);self.mount(pool)
            except Exception as error:errors.append({'pool':pool['name'],'error':str(error)})
        self.ctx.state.set('startup_errors',errors)
        return errors

    def key_plan(self, request):
        pool=self.ctx.config()['pools'].get(name(request.get('pool')))
        if not pool or not pool['encrypted']:raise ValueError('Choose an encrypted data pool')
        md=self.data_device(pool)
        if self.ctx.run('cryptsetup','luksUUID',md).strip()!=pool['luks_uuid']:raise ValueError('LUKS identity changed')
        metadata=json.loads(self.ctx.run('cryptsetup','luksDump','--dump-json-metadata',md))
        import hashlib
        fingerprint=hashlib.sha256(json.dumps(metadata,sort_keys=True).encode()).hexdigest()
        return self.ctx.plan('luks-add-key',{'pool':pool['name'],'luks_uuid':pool['luks_uuid'],
                             'metadata_sha256':fingerprint,'existing_slots':sorted(metadata['keyslots'])},'ADD KEY '+pool['name'])

    def add_key(self, request):
        import hashlib
        import fcntl
        with self.ctx.lock():
            path,plan=self.ctx.reviewed(request,'luks-add-key');body=plan['body']
            pool=self.ctx.config()['pools'][body['pool']];md=self.data_device(pool)
            metadata=json.loads(self.ctx.run('cryptsetup','luksDump','--dump-json-metadata',md))
            if hashlib.sha256(json.dumps(metadata,sort_keys=True).encode()).hexdigest()!=body['metadata_sha256']:
                raise ValueError('LUKS key metadata changed since review')
            old=secret(request.get('existing_secret'), existing=True);new=secret(request.get('new_secret'))
            descriptors=[]
            try:
                for data in (old,new):
                    descriptor=os.memfd_create('freeqnap-key',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
                    descriptors.append(descriptor)
                    if os.write(descriptor,data)!=len(data):raise ValueError('Short memory-key write')
                    os.lseek(descriptor,0,os.SEEK_SET)
                    fcntl.fcntl(descriptor,fcntl.F_ADD_SEALS,fcntl.F_SEAL_WRITE|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_SEAL)
                original,recovery=descriptors
                self.ctx.run('cryptsetup','open','--test-passphrase','--key-file',f'/proc/self/fd/{original}',md,pass_fds=(original,),timeout=90)
                self.ctx.consume(path,plan)
                operation=self.ctx.operation('luks-add-key',{'pool':pool['name'],'plan_id':plan['id']})
                try:
                    self.ctx.run('cryptsetup','luksAddKey','--key-file',f'/proc/self/fd/{original}',
                                 '--pbkdf','argon2id','--pbkdf-memory','131072','--pbkdf-parallel','2',
                                 '--iter-time','2000',md,f'/proc/self/fd/{recovery}',pass_fds=tuple(descriptors),timeout=180)
                    os.lseek(recovery,0,os.SEEK_SET)
                    self.ctx.run('cryptsetup','open','--test-passphrase','--key-file',f'/proc/self/fd/{recovery}',md,pass_fds=(recovery,),timeout=90)
                    result={'pool':pool['name'],'new_key_verified':True,'existing_keys_removed':False}
                    self.ctx.state.finish(operation,result=result);return result
                except Exception:
                    self.ctx.state.finish(operation,error='Key update interrupted or verification failed. Existing slots were not removed; inspect before adding another key.')
                    raise
            finally:
                for descriptor in descriptors:os.close(descriptor)
                old=None;new=None

    def header_backup(self, request):
        pool=self.ctx.config()['pools'].get(name(request.get('pool')))
        if not pool or not pool['encrypted']:raise ValueError('Choose an encrypted data pool')
        md=self.data_device(pool)
        if self.ctx.run('cryptsetup','luksUUID',md).strip()!=pool['luks_uuid']:raise ValueError('LUKS identity changed')
        ident=secrets.token_hex(16);directory=self.ctx.directory/'headers';directory.mkdir(mode=0o700,exist_ok=True)
        path=directory/(ident+'.luks-header')
        self.ctx.run('cryptsetup','luksHeaderBackup',md,'--header-backup-file',str(path));path.chmod(0o600)
        self.ctx.state.set('header:'+ident,{'pool':pool['name'],'path':str(path),'created_at':time.time()})
        return {'artifact_id':ident,'filename':pool['name']+'-luks-header.bin','bytes':path.stat().st_size,'contains_unlock_key':False}

    def artifact_read(self, request):
        import base64
        import hashlib
        ident=request.get('id','')
        if not re.fullmatch('[a-f0-9]{32}',ident):raise ValueError('Unknown private artifact')
        item=self.ctx.state.setting('header:'+ident)
        if not item:raise ValueError('Unknown private artifact')
        path=self.ctx.directory/'headers'/(ident+'.luks-header')
        if str(path)!=item['path'] or path.is_symlink():raise ValueError('Artifact identity changed')
        offset=int(request.get('offset',0));count=int(request.get('count',512*1024))
        if offset<0 or not 1<=count<=512*1024:raise ValueError('Invalid artifact range')
        descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        try:
            info=os.fstat(descriptor);data=os.pread(descriptor,count,offset)
        finally:os.close(descriptor)
        return {'data_base64':base64.b64encode(data).decode(),'offset':offset,'total_bytes':info.st_size,
                'etag':f'{info.st_ino}-{info.st_size}-{info.st_mtime_ns}','filename':item['pool']+'-luks-header.bin'}
