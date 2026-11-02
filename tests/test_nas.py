import base64
import copy
import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from freeqnap.nas.common import Context, secret
from freeqnap.nas.storage import Storage
from freeqnap.nas.sharing import render
from freeqnap.nas.files import Files, relative
from freeqnap.nas.filebackup import FileBackups
from freeqnap.nas.media import nfo

class Fixture(Context):
    def __init__(self, root):
        self.commands = []
        super().__init__(root / 'system', runner=self.fake_run)
        self.mount = root / 'volume';self.mount.mkdir()
        self.save({'pools': {'data': {'name': 'data', 'mountpoint': str(self.mount), 'filesystem_uuid': 'fixture-uuid'}},
                   'shares': {}, 'users': {}, 'repositories': {}, 'libraries': {}})
    def fake_run(self, *args, **kwargs):
        self.commands.append((args, {k: v for k, v in kwargs.items() if k != 'data'}))
        if args[0] == 'sfdisk':
            dev = args[-1]
            parts = [{'node': dev+'1', 'start': 2048, 'size': 1024}, {'node': dev+'2', 'start': 4096, 'size': 8192}] if dev == '/dev/sda' else []
            return json.dumps({'partitiontable': {'label': 'gpt', 'sectorsize': 512, 'lastlba': 50*1024**2, 'partitions': parts}})
        if args[0] == 'wipefs':return '{"signatures":[]}'
        if args[0] == 'systemctl':return 'active\n'
        raise ValueError('Unexpected fixture command')
    def volume(self, ident):
        pool = self.config()['pools'].get(ident)
        if not pool:raise ValueError('Unknown fixture pool')
        return pool, self.mount

class NAS(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name);self.ctx = Fixture(self.root)
    def inventory(self):
        return {'sampled_at': time.time(), 'errors': [], 'root': {'uuid': 'fixture-root'},
                'disks': [{'path': '/dev/sd'+d, 'serial': 'TEST-'+d, 'wwn': 'fixture-'+d, 'size': 100*1024**3,
                           'type': 'disk', 'model': 'Fixture only', 'mountpoints': [],
                           'children': [{'uuid': 'fixture-root', 'mountpoints': ['/']}] if d == 'a' else []} for d in 'abc']}
    def test_os_whole_disk_refused_before_any_write(self):
        store = Storage(self.ctx, self.inventory, lambda _: True)
        with self.assertRaisesRegex(ValueError, 'OS disks'):
            store.plan({'name': 'test', 'level': 'mirror', 'disks': ['TEST-a', 'TEST-b']})
        self.assertFalse(any(c[0][0] in ('sgdisk', 'mdadm', 'wipefs') and '--all' in c[0] for c in self.ctx.commands))
    def test_region_plan_does_not_overlap_os_and_changed_wwn_prevents_commit(self):
        data = self.inventory();store = Storage(self.ctx, lambda: data, lambda _: True)
        plan = store.plan({'name': 'test', 'level': 'mirror', 'disks': ['TEST-a', 'TEST-b'], 'allocation': 'free-tail', 'encrypted': True})
        region = plan['body']['regions'][0]
        self.assertEqual(region['number'], 3);self.assertGreaterEqual(region['start'], 12288)
        data['disks'][1]['wwn'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'changed'):
            store.create({'plan_id': plan['id'], 'digest': plan['digest'], 'confirmation': 'CREATE test', 'secret': {'password': 'private fixture password'}})
        self.assertFalse(any(c[0][0] in ('sgdisk', 'mdadm', 'cryptsetup') for c in self.ctx.commands))
        self.assertNotIn('private fixture password', self.ctx.state.database.read_bytes().decode('latin1'))
    def test_plan_confirmation_expiry_and_reuse(self):
        value = self.ctx.plan('test', {'fixture': True}, 'EXACT')
        request = {'plan_id': value['id'], 'digest': value['digest'], 'confirmation': 'wrong'}
        with self.assertRaises(ValueError):self.ctx.reviewed(request, 'test')
        request['confirmation'] = 'EXACT';path, value = self.ctx.reviewed(request, 'test');self.ctx.consume(path, value)
        with self.assertRaises(ValueError):self.ctx.reviewed(request, 'test')
    def test_existing_volume_password_does_not_use_creation_policy(self):
        self.assertEqual(secret({"password":"ninechars"}, existing=True), b"ninechars")
        with self.assertRaises(ValueError):secret({"password":"ninechars"})
        for password in ("", "bad\npassword"):
            with self.assertRaises(ValueError):secret({"password":password}, existing=True)
    def test_secret_and_queue_boundaries(self):
        self.assertEqual(secret({'key_base64': base64.b64encode(b'x'*32).decode()}), b'x'*32)
        for value in ({'path': '/root/key'}, {'password': 'short'}, {'key_base64': 'bad'}, {'password': 'long enough password', 'extra': True}):
            with self.assertRaises(ValueError):secret(value)
        with self.assertRaisesRegex(ValueError, 'Secrets'):self.ctx.operation('wrong', {'password': 'must not persist'})
        self.assertFalse(self.ctx.state.jobs())
    def test_protocol_render_has_no_guest_and_nfs_client_scope(self):
        config = {'users': {'tester': {'uid': 1000}}}
        share = {'name': 'media', 'path': '/srv/freeqnap/volumes/data/media', 'users': ['tester'],
                 'protocols': ['smb','nfs','afp'], 'read_only': False, 'nfs_clients': ['192.0.2.0/24'],
                 'nfs_user': 'tester', 'gid': 1000, 'export_id': 10}
        value = render(config, [share], 'freeqnap-test')
        self.assertIn('smb encrypt = required', value['smb']);self.assertIn('guest ok = no', value['smb'])
        self.assertIn('Access_Type = None', value['nfs']);self.assertIn('192.0.2.0/24', value['nfs'])
        share['path'] += '\n[evil]'
        with self.assertRaises(ValueError):render(config,[share],'freeqnap-test')
    def test_file_browser_does_not_follow_symlink_or_escape(self):
        folder = self.ctx.mount/'files';folder.mkdir();outside=self.root/'secret';outside.write_text('private')
        (folder/'escape').symlink_to(outside)
        cfg=self.ctx.config();cfg['shares']['files']={'name':'files','pool':'data','path':str(folder),'gid':os.getgid()};self.ctx.save(cfg)
        files=Files(self.ctx)
        self.assertTrue(files.list({'share':'files'})['entries'][0]['symlink'])
        with self.assertRaises(OSError):files.read({'share':'files','path':'escape'})
        for value in ('../secret','/etc/shadow','.freeqnap/secret'):
            with self.assertRaises(ValueError):relative(value)
    def test_partial_restic_failure_cannot_become_successful_snapshot(self):
        folder=self.ctx.mount/'files';folder.mkdir()
        cfg=self.ctx.config();cfg['shares']['files']={'name':'files','pool':'data','path':str(folder)}
        cfg['repositories']['repo']={'name':'repo','kind':'sftp','initialized':True};self.ctx.save(cfg)
        backups=FileBackups(self.ctx)
        with patch.object(backups,'command',side_effect=ValueError('restic exit 3')):
            with self.assertRaises(ValueError):backups.backup({'repository':'repo','shares':['files']})
        self.assertEqual(self.ctx.state.setting('successful_snapshots',{}),{})
    def test_restore_is_staged_and_never_uses_latest_or_overwrite(self):
        cfg=self.ctx.config();cfg['repositories']['repo']={'name':'repo','kind':'sftp'};self.ctx.save(cfg)
        backups=FileBackups(self.ctx)
        with self.assertRaises(ValueError):backups.restore({'repository':'repo','snapshot':'latest','pool':'data'},'fixture')
        with patch.object(backups,'command',side_effect=lambda entry,*a,**kw:json.dumps([{'id':'a'*64,'tags':['freeqnap'],'paths':['/fixture']}]) if a[0]=='snapshots' else '') as command:
            result=backups.restore({'repository':'repo','snapshot':'a'*64,'pool':'data'},'fixture')
        self.assertFalse(result['live_files_replaced']);self.assertIn('--verify', command.call_args.args)
        self.assertNotIn('--delete', command.call_args.args)
    def test_mount_loss_after_restic_summary_keeps_snapshot_unaccepted(self):
        folder=self.ctx.mount/'files';folder.mkdir();cfg=self.ctx.config();cfg['shares']['files']={'name':'files','pool':'data','path':str(folder)};cfg['repositories']['repo']={'name':'repo','kind':'sftp','initialized':True};self.ctx.save(cfg);backups=FileBackups(self.ctx)
        def command(entry,*args,**kwargs):
            if args[0]=='backup':
                self.ctx.volume=lambda _:(_ for _ in ()).throw(ValueError('Source disconnected'))
                return json.dumps({'message_type':'summary','snapshot_id':'b'*64})
            return ''
        with patch.object(backups,'command',side_effect=command):
            with self.assertRaisesRegex(ValueError,'disconnected'):backups.backup({'repository':'repo','shares':['files']})
        self.assertEqual(self.ctx.state.setting('successful_snapshots',{}),{})

    def test_replaced_source_root_cannot_accept_snapshot_or_erase_last_good(self):
        for replacement,when in (('directory','backup'),('symlink','backup'),('directory','check')):
            with self.subTest(replacement=replacement,when=when):
                folder=self.ctx.mount/('files-'+replacement+'-'+when);folder.mkdir()
                cfg=self.ctx.config();cfg['shares']['files']={'name':'files','pool':'data','path':str(folder)};cfg['repositories']['repo']={'name':'repo','kind':'sftp','initialized':True};self.ctx.save(cfg)
                self.ctx.state.set('successful_snapshots',{'repo':['a'*64]});backups=FileBackups(self.ctx)
                def command(entry,*args,**kwargs):
                    if args[0]==when:
                        old=folder.with_name(folder.name+'-original');folder.rename(old)
                        if replacement=='directory':folder.mkdir()
                        else:folder.symlink_to(old,target_is_directory=True)
                    if args[0]=='backup':return json.dumps({'message_type':'summary','snapshot_id':'b'*64})
                    if args[0]=='check':return ''
                    raise AssertionError('Unexpected backup command')
                with patch.object(backups,'command',side_effect=command):
                    with self.assertRaisesRegex(ValueError,'directory changed'):backups.backup({'repository':'repo','shares':['files']})
                self.assertEqual(self.ctx.state.setting('successful_snapshots'),{'repo':['a'*64]})

    def test_system_retention_reviews_and_prunes_only_its_tag(self):
        cfg=self.ctx.config();cfg['repositories']['repo']={'name':'repo','kind':'sftp'};self.ctx.save(cfg);self.ctx.state.set('repository_check:repo',{'checked_at':time.time(),'read_all_data':True});backups=FileBackups(self.ctx);calls=[]
        def command(entry,*args,**kwargs):calls.append(args);return '[]'
        with patch.object(backups,'command',side_effect=command):
            plan=backups.prune_plan({'repository':'repo','scope':'system','keep_last':3});backups.prune({'plan_id':plan['id'],'digest':plan['digest'],'confirmation':plan['confirmation']})
        self.assertTrue(all(c[c.index('--tag')+1]=='freeqnap-system' for c in calls));self.assertIn('--prune',calls[-1])

    def test_local_nfo_preserves_metadata_and_rejects_entities(self):
        self.assertEqual(nfo(b'<movie><title>Fixture</title><year>2026</year></movie>')['title'],'Fixture')
        with self.assertRaises(ValueError):nfo(b'<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/shadow">]><movie/>')

    def test_identical_mount_namespace_aliases_are_accepted_but_other_roots_refused(self):
        pool={'name':'data','mountpoint':str(self.ctx.mount),'filesystem_uuid':'fixture-uuid'}
        context=Context(self.root/'identity',runner=lambda *a,**kw:json.dumps({'filesystems':rows}))
        context.save({'pools':{'data':pool}})
        row={'target':str(self.ctx.mount),'source':'/dev/fixture','uuid':'fixture-uuid','fstype':'ext4','fsroot':'/','options':'rw,nodev,nosuid,noexec'}
        rows=[row.copy(),row.copy()]
        self.assertEqual(context.volume('data')[0]['name'],'data')
        rows[1]['source']='/dev/other'
        with self.assertRaises(ValueError):context.volume('data')
        rows=[{**row,'fsroot':'/wrong-subdirectory'}]
        with self.assertRaises(ValueError):context.volume('data')
        rows=[row.copy(),{**row,'options':'ro'}]
        with self.assertRaises(ValueError):context.volume('data')

    def test_unsupported_encrypted_import_closes_mapping_after_unlock(self):
        cfg=self.ctx.config();cfg['pools']['data'].update(encrypted=True,imported=True,luks_uuid='fixture-luks',filesystem_uuid=None);self.ctx.save(cfg)
        def runner(*args,**kwargs):
            self.ctx.commands.append((args,{}))
            if args[:2]==('cryptsetup','luksUUID'):return 'fixture-luks'
            if args[0]=='blkid':return 'ntfs'
            if args[0]=='cryptsetup':return ''
            raise ValueError('Unexpected command')
        self.ctx.run=runner;storage=Storage(self.ctx)
        with patch.object(storage,'array_device',return_value='/dev/fixture'):
            with self.assertRaisesRegex(ValueError,'unsupported'):storage.unlock({'pool':'data','secret':{'password':'fixture private password'}})
        self.assertIn((('cryptsetup','close','freeqnap-data'),{}),self.ctx.commands)
        self.assertIsNone(self.ctx.config()['pools']['data']['filesystem_uuid'])

if __name__ == '__main__':unittest.main()
