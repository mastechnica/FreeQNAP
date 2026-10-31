#!/usr/bin/env python3
"""Exclusive standard-library serial capture with a private command socket.

No boot commands, network settings or flash writes are issued automatically.
The optional stop-autoboot mode sends one space at an explicit U-Boot countdown.
"""
import argparse
import codecs
import fcntl
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import socket
import termios
import time
import tty


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--stop-autoboot', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    args.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = (args.directory/'capture.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    previous = termios.tcgetattr(fd)
    fcntl.ioctl(fd, termios.TIOCEXCL)
    tty.setraw(fd, termios.TCSANOW)
    settings = termios.tcgetattr(fd)
    settings[2] = (settings[2] & ~(termios.PARENB | termios.CSTOPB | termios.CSIZE | termios.HUPCL | getattr(termios,'CRTSCTS',0))) | termios.CS8 | termios.CLOCAL | termios.CREAD
    settings[4] = settings[5] = termios.B115200
    termios.tcsetattr(fd, termios.TCSANOW, settings)
    # macOS limits Unix socket paths to 104 bytes; the project path is longer.
    short_root = Path('/private/tmp') if Path('/private/tmp').is_dir() else Path('/tmp')
    tag = hashlib.sha256(str(args.directory.resolve()).encode()).hexdigest()[:10]
    short_directory = short_root/('eyeq-uart-'+str(os.getuid())+'-'+tag)
    short_directory.mkdir(mode=0o700,exist_ok=True)
    if short_directory.is_symlink() or short_directory.stat().st_uid != os.getuid() or short_directory.stat().st_mode & 0o077:
        raise RuntimeError('Private owned socket directory required')
    endpoint = short_directory/'control.sock'
    # The exclusive directory lock establishes that no live broker owns it.
    endpoint.unlink(missing_ok=True)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(endpoint)); endpoint.chmod(0o600); listener.listen(2)
    running = True
    def stop(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
    window = b''; interrupted = False; seen_boot = False
    received=0;last_handoff=-1
    clients = {}
    with (args.directory/'console.bin').open('ab', buffering=0) as raw, (args.directory/'console.log').open('a', buffering=1) as log, (args.directory/'events.jsonl').open('a', buffering=1) as events:
        def event(kind, **fields):
            events.write(json.dumps({'time':time.time(), 'event':kind, **fields})+'\n')
        def send(data):
            if len(data)>8192:
                raise ValueError('Command exceeds 8192 bytes')
            deadline=time.monotonic()+10
            for byte in data:
                while True:
                    try:
                        if os.write(fd,bytes([byte]))==1:break
                    except BlockingIOError:pass
                    if time.monotonic()>deadline:raise TimeoutError('Serial write timeout')
                    select.select([], [fd], [], .05)
                time.sleep(.003)
        info = {'pid':os.getpid(),'port':args.port,'baud':115200,'format':'8N1',
                'log':str(args.directory/'console.log'),'control_socket':str(endpoint),
                'stop_autoboot':args.stop_autoboot}
        (args.directory/'ready.json').write_text(json.dumps(info,indent=2)+'\n')
        event('ready',**info)
        log.write('[capture] READY: 115200 8N1; waiting for NAS power-on.\n')
        print(json.dumps(info),flush=True)
        try:
            while running:
                readable,_,_=select.select([fd,listener,*clients],[],[],.5)
                for item in readable:
                    if item==fd:
                        try:data=os.read(fd,65536)
                        except BlockingIOError:continue
                        if not data:raise OSError('Serial device disconnected')
                        raw.write(data);log.write(decoder.decode(data));log.flush()
                        combined=window+data
                        combined_start=received-len(window);received+=len(data)
                        handoff=combined.rfind(b'Executing application...')
                        if handoff>=0 and combined_start+handoff>last_handoff:
                            last_handoff=combined_start+handoff
                            interrupted=False;seen_boot=False
                            combined=combined[handoff+len(b'Executing application...'):]
                            event('new_boot_handoff')
                        if not seen_boot:
                            banner=combined.rfind(b'U-Boot ')
                            if banner>=0:combined=combined[banner:];seen_boot=True
                        window=combined[-4096:]
                        if seen_boot and b'ALPINE_DB>' not in window:
                            # A countdown is required; banners alone never send data.
                            if args.stop_autoboot and not interrupted and b'Hit any key to stop autoboot' in window:
                                send(b' ');interrupted=True;event('autoboot_stop_sent')
                                log.write('\n[capture] Sent autoboot stop; awaiting U-Boot prompt.\n')
                    elif item==listener:
                        client,_=listener.accept();client.setblocking(False);clients[client]=b''
                    else:
                        chunk=item.recv(8193)
                        if not chunk:item.close();clients.pop(item);continue
                        clients[item]+=chunk
                        if len(clients[item])>16384:
                            item.close();clients.pop(item);continue
                        if b'\n' not in clients[item]:continue
                        line,_=clients[item].split(b'\n',1)
                        try:
                            request=json.loads(line)
                            if request=={'arm_autoboot':True}:
                                # Require a new observed boot banner/countdown.
                                # Arming alone never transmits a serial byte.
                                args.stop_autoboot=True;interrupted=False;seen_boot=False;window=b''
                                event('autoboot_armed');reply={'ok':True,'armed':True}
                            elif request=={'disarm_autoboot':True}:
                                args.stop_autoboot=False;event('autoboot_disarmed');reply={'ok':True,'armed':False}
                            else:
                                if set(request)!={'send'} or not isinstance(request['send'],str):raise ValueError('Supply a send string or explicit autoboot arm request')
                                data=request['send'].encode();send(data)
                                event('manual_send',bytes=len(data))
                                reply={'ok':True,'bytes':len(data)}
                        except (ValueError,TypeError,TimeoutError) as error:reply={'ok':False,'error':str(error)}
                        item.setblocking(True);item.settimeout(2)
                        try:item.sendall(json.dumps(reply).encode()+b'\n')
                        except OSError:pass
                        item.close();clients.pop(item)
        finally:
            event('stopped');log.write('\n[capture] STOPPED\n')
            for client in clients:client.close()
            listener.close();endpoint.unlink(missing_ok=True)
            (args.directory/'ready.json').unlink(missing_ok=True)
            termios.tcsetattr(fd,termios.TCSANOW,previous);os.close(fd)


if __name__=='__main__':
    main()
