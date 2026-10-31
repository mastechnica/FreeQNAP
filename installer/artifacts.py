#!/usr/bin/env python3
"""Serve only hash-pinned release artifacts to one installation target."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler,HTTPServer
import ipaddress
import json
from pathlib import Path
import time


def load_artifacts(directory):
    directory=Path(directory)
    manifest=json.loads((directory/'manifest.json').read_text())
    result={}
    for name in ('debian-armhf-base.tar.gz','uImage'):
        record=manifest.get('artifacts',{}).get(name)
        if not record:continue
        path=directory/name
        if path.is_symlink() or not path.is_file():raise ValueError('A regular release artifact is required')
        data=path.read_bytes()
        if len(data)!=record['bytes'] or hashlib.sha256(data).hexdigest()!=record['sha256']:
            raise ValueError('Release artifact checksum mismatch')
        # Retain immutable bytes; replacing a file cannot change an active server.
        result['/'+name]=data
    if not result:raise ValueError('No supported release artifacts')
    return result


def handler_for(artifacts,client):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.client_address[0]!=client:
                self.send_error(403);return
            data=artifacts.get(self.path)
            if data is None:self.send_error(404);return
            self.send_response(200)
            self.send_header('Content-Type','application/octet-stream')
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            try:self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):pass
        def log_message(self,*_):pass
    return Handler


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--release',type=Path,required=True)
    p.add_argument('--bind',required=True);p.add_argument('--client',required=True)
    p.add_argument('--port',type=int,default=8098);p.add_argument('--seconds',type=int,default=7200)
    a=p.parse_args()
    for address in (a.bind,a.client):
        ip=ipaddress.IPv4Address(address)
        if not ip.is_private or ip.is_loopback or ip.is_multicast or ip.is_unspecified:raise ValueError('Private wired IPv4 addresses required')
    if a.bind==a.client or not 1024<=a.port<=65535 or not 1<=a.seconds<=28800:raise ValueError('Invalid address, port or lifetime')
    artifacts=load_artifacts(a.release)
    with HTTPServer((a.bind,a.port),handler_for(artifacts,a.client)) as server:
        server.timeout=.5
        print(f'READY {a.bind}:{a.port}; only {a.client}; {len(artifacts)} pinned artifact(s); no uploads',flush=True)
        deadline=time.monotonic()+a.seconds
        while time.monotonic()<deadline:server.handle_request()


if __name__=='__main__':main()
