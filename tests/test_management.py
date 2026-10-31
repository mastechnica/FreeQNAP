import hashlib
import http.client
import json
import sqlite3
import tarfile
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from freeqnap import auth, backups, demo, plans
from freeqnap.jobs import Worker
from freeqnap.server import handler
from freeqnap.state import State

class CoreTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = State(self.root / 'state')
        self.dest = self.root / 'backups'

    def test_sqlite_wal_snapshot_private_and_sessionless(self):
        self.state.set('example', {'saved': True})
        with self.state.connect() as db:
            db.execute('INSERT INTO sessions VALUES(?,?,?)', ('old', 'csrf', time.time() + 999))
        result = backups.create(self.state.directory, self.dest)
        path = self.dest / result['name']
        self.assertTrue(backups.verify(path)['verified'])
        self.assertEqual(path.stat().st_mode & 511, 384)
        with tarfile.open(path) as tar:
            with (self.root / 'snapshot.db').open('wb') as stream:
                stream.write(tar.extractfile('configuration/state.sqlite3').read())
        from contextlib import closing
        with closing(sqlite3.connect(self.root / 'snapshot.db')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0], 0)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertIsNotNone(db.execute("SELECT value FROM settings WHERE key='example'").fetchone())
        self.assertFalse(backups.restore_preview(path)['can_restore'])

    def test_corruption_is_detected_and_last_good_survives_failed_backup(self):
        good = backups.create(self.state.directory, self.dest)
        with patch.object(backups, 'MAX_FILE', 1):
            with self.assertRaises(ValueError):
                backups.create(self.state.directory, self.dest)
        self.assertTrue(backups.verify(self.dest / good['name'])['verified'])
        path = self.dest / good['name']
        path.write_bytes(path.read_bytes() + b'corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            backups.verify(path)

    def test_malformed_receipt_does_not_hide_later_archives(self):
        first = backups.create(self.state.directory, self.dest)
        second = backups.create(self.state.directory, self.dest)
        (self.dest / (first['name'] + '.json')).write_text('{}')
        listed = backups.list_backups(self.dest)
        self.assertEqual(sum(item['verified'] for item in listed), 1)
        self.assertEqual(len(listed), 2)
        self.assertTrue(backups.verify(self.dest / second['name'])['verified'])

    def test_unsafe_member_is_rejected_even_with_matching_archive_hash(self):
        import io
        path = self.dest / 'freeqnap-config-unsafe.tar.gz'
        self.dest.mkdir()
        with tarfile.open(path, 'w:gz') as tar:
            member = tarfile.TarInfo('../outside')
            member.size = 3
            tar.addfile(member, io.BytesIO(b'bad'))
        receipt = {'bytes': path.stat().st_size, 'sha256': backups.digest(path)}
        (self.dest / (path.name + '.json')).write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            backups.verify(path)

    def test_retention_keeps_failed_diagnostics(self):
        incomplete = self.dest / 'failed.partial'
        self.dest.mkdir()
        incomplete.write_bytes(b'failed')
        for _ in range(4):
            backups.create(self.state.directory, self.dest, keep=2)
        self.assertEqual(len(list(self.dest.glob('*.tar.gz'))), 2)
        self.assertTrue(incomplete.exists())

    def test_mirror_missing_uuid_fails_without_fallback(self):
        result = backups.create(self.state.directory, self.dest)
        target = self.root / 'missing-volume'
        wrong = lambda *a, **k: json.dumps({'filesystems': [{'target': '/', 'uuid': 'os-root'}]})
        with self.assertRaisesRegex(ValueError, 'missing or changed'):
            backups.mirror(self.dest / result['name'], target, 'data-uuid', runner=wrong)
        self.assertFalse(target.exists())
        self.assertTrue(backups.verify(self.dest / result['name'])['verified'])

    def test_mirror_verified_and_no_overwrite(self):
        result = backups.create(self.state.directory, self.dest)
        target = self.root / 'data'
        correct = lambda *a, **k: json.dumps({'filesystems': [{'target': str(target), 'uuid': 'data'}]})
        copied = backups.mirror(self.dest / result['name'], target, 'data', runner=correct)
        self.assertEqual(copied['sha256'], result['sha256'])
        self.assertTrue(backups.mirror(self.dest / result['name'], target, 'data', runner=correct)['verified'])

    def test_failed_job_does_not_block_later_and_survives_restart(self):
        failed = self.state.enqueue('unknown', {})
        later = self.state.enqueue('config-backup', {})
        worker = Worker(self.state, self.dest)
        self.assertTrue(worker.one())
        self.assertTrue(worker.one())
        restarted = State(self.state.directory)
        statuses = {j['id']: j['status'] for j in restarted.jobs()}
        self.assertEqual(statuses[failed], 'retryable')
        self.assertEqual(statuses[later], 'succeeded')
        restarted.retry(failed)
        self.assertTrue(Worker(restarted, self.dest).one())
        self.assertEqual({j['id']: j['attempts'] for j in restarted.jobs()}[failed], 2)

    def test_interrupted_job_never_assumed_success_or_replayed(self):
        ident = self.state.enqueue('config-backup', {})
        self.state.claim()
        restarted = State(self.state.directory)
        restarted.reconcile_interrupted()
        self.assertEqual(restarted.jobs()[0]['status'], 'retryable')
        self.assertIsNone(restarted.claim())
        restarted.retry(ident)
        self.assertIsNotNone(restarted.claim())

    def test_daily_schedule_is_opt_in_persistent_and_coalesces(self):
        worker = Worker(self.state, self.dest)
        self.assertFalse(worker.schedule())
        self.state.set('backup_policy', {'daily': True, 'keep': 7})
        now = time.time()
        self.assertTrue(worker.schedule(now))
        self.assertFalse(worker.schedule(now + 999999))
        worker.one()
        self.assertFalse(Worker(State(self.state.directory), self.dest).schedule(now + 1))
        self.assertTrue(worker.schedule(now + 86401))

    def test_root_stale_and_changed_disks_are_rejected(self):
        value = demo.inventory()
        serials = [value['disks'][i]['serial'] for i in (2, 3)]
        plan = plans.pool_plan(value, 'data', 'mirror', serials)
        self.assertFalse(plan['execution_available'])
        self.assertTrue(plans.verify_plan(plan, value, plan['sha256']))
        with self.assertRaisesRegex(ValueError, 'protected'):
            plans.pool_plan(value, 'data', 'mirror', [value['disks'][0]['serial'], serials[0]])
        value['disks'][2]['wwn'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            plans.verify_plan(plan, value, plan['sha256'])
        value['sampled_at'] -= 121
        with self.assertRaisesRegex(ValueError, 'Fresh'):
            plans.pool_plan(value, 'data', 'mirror', serials)

    def test_enrollment_is_one_use_and_never_a_default_password(self):
        token=auth.enrollment(self.state)
        self.assertIsNone(auth.login(self.state,'some sufficiently long password'))
        with self.assertRaises(ValueError):auth.enroll(self.state,'wrong token','some sufficiently long password')
        auth.enroll(self.state,token,'some sufficiently long password')
        self.assertIsNotNone(auth.login(self.state,'some sufficiently long password'))
        self.assertIsNone(self.state.setting('enrollment'))
        with self.assertRaises(ValueError):auth.enroll(self.state,token,'a different long password')

    def test_auth_has_no_default_and_stores_only_hashes(self):
        self.assertIsNone(auth.login(self.state, 'admin'))
        self.state.set('administrator', auth.password_hash('a private test password'))
        self.assertIsNone(auth.login(self.state, 'wrong password'))
        token, csrf = auth.login(self.state, 'a private test password')
        self.assertEqual(auth.session(self.state, token)['csrf'], csrf)
        with self.state.connect() as db:
            self.assertEqual(db.execute('SELECT token_hash FROM sessions').fetchone()[0], hashlib.sha256(token.encode()).hexdigest())

class HTTPTests(unittest.TestCase):

    def start(self, preview=False):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.state = State(root / 'state')
        self.state.set('administrator', auth.password_hash('private test password'))
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler(self.state, root / 'backups', preview=preview))
        server.login_attempts = []
        server.auth_lock = threading.Lock()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.port = server.server_port

    def request(self, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port)
        h = {'Host': '127.0.0.1:' + str(self.port), 'Origin': 'http://127.0.0.1:' + str(self.port), 'Content-Type': 'application/json'}
        h.update(headers or {})
        conn.request('POST' if body is not None else 'GET', path, json.dumps(body) if body is not None else None, h)
        r = conn.getresponse()
        raw = r.read()
        result = (r.status, dict(r.getheaders()), json.loads(raw))
        conn.close()
        return result

    def test_no_header_impersonation_csrf_and_origin_enforced(self):
        self.start()
        self.assertEqual(self.request('/api/jobs', headers={'X-User': 'admin', 'X-Forwarded-User': 'admin'})[0], 401)
        code, headers, body = self.request('/api/login', {'password': 'private test password'})
        self.assertEqual(code, 200)
        cookie = headers['Set-Cookie'].split(';')[0]
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.assertEqual(self.request('/api/backups/create', {}, headers={'Cookie': cookie})[0], 403)
        h = {'Cookie': cookie, 'X-CSRF-Token': body['csrf']}
        self.assertEqual(self.request('/api/backups/create', {}, headers={**h, 'Origin': 'http://attacker.example'})[0], 403)
        self.assertEqual(self.request('/api/backups/create', {}, headers=h)[0], 202)
        self.assertEqual(self.request('/api/jobs', headers={'Host': 'attacker.example'})[0], 403)

    def test_synthetic_preview_cannot_download_host_files(self):
        self.start(True)
        self.assertEqual(self.request('/api/file?share=secret&path=file')[0],403)
        self.assertEqual(self.request('/api/system-backup?id='+('a'*32))[0],403)
        code,_,body=self.request('/api/nas/status')
        self.assertEqual(code,200);self.assertTrue(body['demo'])

    def test_desktop_script_is_served_as_local_javascript(self):
        self.start(True)
        connection=http.client.HTTPConnection('127.0.0.1',self.port)
        connection.request('GET','/file-desktop.js',headers={'Host':'127.0.0.1:'+str(self.port)})
        result=connection.getresponse();body=result.read();connection.close()
        self.assertEqual(result.status,200);self.assertEqual(result.getheader('Content-Type'),'text/javascript');self.assertIn(b'FreeQNAPDesktop',body)

    def test_pwa_assets_are_public_but_notification_and_ddns_mutations_require_login(self):
        self.start()
        for path,kind in (('/sw.js','text/javascript'),('/manifest.webmanifest','application/manifest+json'),('/icon-192.png','image/png'),('/notifications.js','text/javascript'),('/ddns.js','text/javascript')):
            connection=http.client.HTTPConnection('127.0.0.1',self.port);connection.request('GET',path,headers={'Host':'127.0.0.1:'+str(self.port)});response=connection.getresponse();body=response.read();connection.close();self.assertEqual(response.status,200);self.assertEqual(response.getheader('Content-Type'),kind);self.assertEqual(response.getheader('Cache-Control'),'no-store');self.assertTrue(body)
            if path=='/sw.js':self.assertEqual(response.getheader('Service-Worker-Allowed'),'/')
        for action in ('notifications.save','notifications.push-key','notifications.test','ddns.save','health.acknowledge'):
            self.assertEqual(self.request('/api/nas/'+action,{})[0],403)

    def test_recovery_archive_requires_login_and_preview_cannot_download(self):
        self.start()
        self.assertEqual(self.request('/api/system-backup?id='+('a'*32))[0],401)
        code,headers,body=self.request('/api/login',{'password':'private test password'})
        self.assertEqual(code,200)
        cookie=headers['Set-Cookie'].split(';')[0]
        self.assertEqual(self.request('/api/nas/backup.local-create',{'secret':{'password':'not saved fixture password'}},headers={'Cookie':cookie})[0],403)

    def test_synthetic_preview_cannot_mutate(self):
        self.start(True)
        code, _, body = self.request('/api/status')
        self.assertEqual(code, 200)
        self.assertTrue(body['demo'])
        self.assertFalse(body['capabilities']['pool_execution'])
        self.assertEqual(self.request('/api/backups/create', {})[0], 403)
        self.assertEqual(self.state.jobs(), [])
if __name__ == '__main__':
    unittest.main()
