"""Linux peer-credential-checked Unix broker. No network listener or raw command API."""
import argparse
import grp
import json
import os
import pwd
import signal
import socket
import socketserver
import struct
import threading
from pathlib import Path
from .backend import Backend
from .common import Context

MAX_FRAME = 2 * 1024**2

class Client:
    def __init__(self, path='/run/freeqnap/broker.sock'):
        self.path = str(path)

    def request(self, action, payload=None):
        raw = json.dumps({'action': action, 'payload': payload or {}}).encode() + b'\n'
        if len(raw) > MAX_FRAME:raise ValueError('NAS request too large')
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(600);connection.connect(self.path);connection.sendall(raw)
            stream = connection.makefile('rb')
            data = stream.readline(MAX_FRAME + 1)
            if len(data) > MAX_FRAME or not data.endswith(b'\n'):raise ValueError('Invalid broker response')
            value = json.loads(data)
            if not value.get('ok'):raise ValueError(value.get('error', 'NAS operation failed'))
            return value['result']

class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = False
    def __init__(self, path, backend, uid):
        self.backend = backend;self.allowed_uid = uid;self.capacity = threading.BoundedSemaphore(16)
        super().__init__(str(path), Handler)

    def process_request(self, request, address):
        if not self.capacity.acquire(blocking=False):request.close();return
        try:super().process_request(request, address)
        except Exception:self.capacity.release();raise

    def process_request_thread(self, request, address):
        try:super().process_request_thread(request, address)
        finally:self.capacity.release()

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(600)
        credentials = self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i'))
        _, uid, _ = struct.unpack('3i', credentials)
        if uid not in (0, self.server.allowed_uid):return
        try:
            raw = self.rfile.readline(MAX_FRAME + 1)
            if len(raw) > MAX_FRAME or not raw.endswith(b'\n'):raise ValueError('Invalid request frame')
            request = json.loads(raw)
            if set(request) != {'action', 'payload'}:raise ValueError('Invalid request envelope')
            result = self.server.backend.dispatch(request['action'], request['payload'])
            reply = {'ok': True, 'result': result}
        except (ValueError, KeyError, TypeError, OSError) as error:
            # No payload, secret or subprocess stdin is ever logged/returned.
            reply = {'ok': False, 'error': str(error)[:500]}
        raw = json.dumps(reply).encode() + b'\n'
        if len(raw) > MAX_FRAME:raw = b'{"ok":false,"error":"Response exceeds limit; narrow the selection"}\n'
        self.wfile.write(raw)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket', type=Path, default=Path('/run/freeqnap/broker.sock'))
    parser.add_argument('--state', type=Path, default=Path('/var/lib/freeqnap-system'))
    args = parser.parse_args()
    if os.geteuid() != 0 or not hasattr(socket, 'SO_PEERCRED'):raise SystemExit('Root on Linux is required')
    account = pwd.getpwnam('freeqnap');group = grp.getgrnam('freeqnap')
    args.socket.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    import fcntl
    args.state.mkdir(mode=0o700,parents=True,exist_ok=True)
    lock = (args.state / '.broker.lock').open('a');fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if args.socket.exists():args.socket.unlink()
    backend = Backend(Context(args.state));backend.ctx.state.reconcile_interrupted();backend.notifications.reconcile_sending();backend.my_radio.reconcile_downloads();backend.storage.startup()
    with Server(args.socket, backend, account.pw_uid) as server:
        os.chown(args.socket, 0, group.gr_gid);args.socket.chmod(0o660)
        # Two independent jobs permit a slow repository to coexist with other work.
        for _ in range(2):threading.Thread(target=backend.worker, daemon=True).start()
        threading.Thread(target=backend.guardian, daemon=True).start()
        threading.Thread(target=backend.download_worker, daemon=True).start()
        threading.Thread(target=backend.recycle_worker, daemon=True).start()
        threading.Thread(target=backend.backup_schedule_worker, daemon=True).start()
        threading.Thread(target=backend.health_worker, daemon=True).start()
        threading.Thread(target=backend.notification_worker, daemon=True).start()
        threading.Thread(target=backend.ddns_worker, daemon=True).start()
        threading.Thread(target=backend.metrics_worker, daemon=True).start()
        threading.Thread(target=backend.disk_report_worker, daemon=True).start()
        def radio_refresh():
            import time
            while not backend.stop_event.wait(60):
                try:backend.my_radio.refresh_due_feeds()
                except Exception:pass
        threading.Thread(target=radio_refresh,daemon=True).start()
        threading.Thread(target=backend.personal_photo_worker, daemon=True).start()
        print('FreeQNAP privileged broker ready on private Unix socket', flush=True)
        try:server.serve_forever()
        finally:backend.stop_event.set();backend.personal_photos.stop.set();args.socket.unlink(missing_ok=True)
if __name__ == '__main__':main()
