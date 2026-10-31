#!/usr/bin/env python3
"""Real HTTP Range resume + aria2 restart, inside a fresh network namespace.

Uses only generated local data and loopback, never the internet or real data pools.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from freeqnap.nas.downloads import config_text

SOURCE='''import http.server,sys,time,pathlib
root=pathlib.Path(sys.argv[1]);data=(root/'source').read_bytes()
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):
  start=0;end=len(data)-1;range=self.headers.get('Range')
  if range:
   r=range.removeprefix('bytes=').split('-');start=int(r[0]);end=min(int(r[1]) if r[1] else end,end)
  with (root/'ranges').open('a') as f:f.write(str(start)+'\\n')
  self.send_response(206 if range else 200);self.send_header('Content-Length',str(end-start+1));self.send_header('Accept-Ranges','bytes');self.send_header('ETag','"fixture-stable"')
  if range:self.send_header('Content-Range','bytes '+str(start)+'-'+str(end)+'/'+str(len(data)))
  self.end_headers()
  try:
   for offset in __import__('builtins').range(start,end+1,65536):self.wfile.write(data[offset:min(offset+65536,end+1)]);self.wfile.flush();time.sleep(.02)
  except OSError:pass
http.server.ThreadingHTTPServer(('127.0.0.1',18080),Handler).serve_forever()
'''

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--confirm-isolated-test',action='store_true');p.add_argument('--inner',action='store_true');a=p.parse_args()
 if os.geteuid()!=0 or not a.confirm_isolated_test:raise SystemExit('Local-root test confirmation required')
 if not a.inner:os.execvp('unshare',['unshare','--net','--fork',sys.executable,str(Path(__file__).resolve()),'--inner','--confirm-isolated-test'])
 subprocess.run(['ip','link','set','lo','up'],check=True)
 procs=[]
 with tempfile.TemporaryDirectory(prefix='freeqnap-download-fixture-') as directory:
  root=Path(directory);root.chmod(0o755);target=root/'files';target.mkdir();target.chmod(0o700);os.chown(target,65534,65534)
  state=root/'engine';state.mkdir(mode=0o700);os.chown(state,65534,65534)
  source=bytes(range(256))*131072;(root/'source').write_bytes(source)
  token='only-an-isolated-test-token';options={'concurrent':2,'download_kib':0,'upload_kib':128,'seed_ratio':1,'seed_minutes':0}
  config=state/'aria2.conf';config.write_text(config_text(state,target,token,options));config.chmod(0o600);os.chown(config,65534,65534)
  session=state/'aria2.session';session.touch(mode=0o600);os.chown(session,65534,65534)
  server=subprocess.Popen(['python3','-c',SOURCE,str(root)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);procs.append(server)
  def start():
   p=subprocess.Popen(['setpriv','--reuid=65534','--regid=65534','--clear-groups','aria2c','--conf-path='+str(config)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);procs.append(p);return p
  def rpc(method,params=[]):
   request=urllib.request.Request('http://127.0.0.1:6800/jsonrpc',data=json.dumps({'jsonrpc':'2.0','id':'test','method':'aria2.'+method,'params':['token:'+token,*params]}).encode(),headers={'Content-Type':'application/json'})
   with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=3) as r:value=json.load(r)
   if 'error' in value:raise ValueError(str(value['error']))
   return value['result']
  try:
   engine=start();ready=False
   for _ in range(30):
    try:rpc('getVersion');ready=True;break
    except OSError:time.sleep(.1)
   assert ready,'aria2 configuration did not start'
   from freeqnap.nas.common import Context
   from freeqnap.nas.downloads import Downloads
   context=Context(root/'manager');(context.directory/'downloads-rpc-token').write_text(token)
   manager=Downloads(context)
   assert manager.rpc('tellStatus',['fedcba0987654321',['status']]) is None,'missing GID HTTP error was not reconciled'
   gid=rpc('addUri',[['http://127.0.0.1:18080/generated.bin'],{'gid':'1234567890abcdef','split':'1','max-connection-per-server':'1','out':'fixture.bin','pause':'false','checksum':'sha-256='+hashlib.sha256(source).hexdigest()}])
   progress=0
   for _ in range(40):
    progress=int(rpc('tellStatus',[gid,['completedLength']])['completedLength'])
    if progress>2*1024**2:break
    time.sleep(.1)
   assert 0<progress<len(source),'fixture did not capture partial download'
   engine.terminate();engine.wait(timeout=15)
   assert (target/'fixture.bin.aria2').is_file(),'resume control file missing'
   assert '1234567890abcdef' in session.read_text(),'durable session missing GID'
   before=len((root/'ranges').read_text().splitlines());engine=start()
   paused=False
   for _ in range(30):
    try:paused=rpc('tellStatus',[gid,['status']])['status']=='paused';break
    except OSError:time.sleep(.1)
   assert paused,'restored jobs must start paused until durable desired state is reconciled'
   rpc('unpause',[gid])
   done=False
   for _ in range(180):
    try:status=rpc('tellStatus',[gid,['status','completedLength']])
    except OSError:time.sleep(.1);continue
    if status['status']=='complete':done=True;break
    assert status['status']!='error','resumed download failed';time.sleep(.1)
   assert done,'resume timed out'
   assert hashlib.sha256((target/'fixture.bin').read_bytes()).digest()==hashlib.sha256(source).digest(),'download checksum mismatch'
   ranges=[int(v) for v in (root/'ranges').read_text().splitlines()[before:]]
   assert any(v>0 for v in ranges),'restart did not issue a nonzero HTTP Range'
   # RPC credentials cannot be omitted, even from local clients.
   req=urllib.request.Request('http://127.0.0.1:6800/jsonrpc',data=b'{"jsonrpc":"2.0","id":"x","method":"aria2.getVersion","params":[]}',headers={'Content-Type':'application/json'})
   try:
    with urllib.request.urlopen(req,timeout=3) as response:unauthorized=json.load(response)
   except urllib.error.HTTPError as error:
    assert error.code==400;unauthorized=json.load(error)
   assert 'error' in unauthorized
   print(json.dumps({'native_http_range_resume_after_engine_restart':True,'sha256_verified':True,'private_rpc_rejects_missing_token':True,'manager_handles_missing_gid_rpc_response':True,'engine_restore_starts_paused':True,'torrent_peer_transfer_tested':False},indent=2),flush=True)
  finally:
   for process in procs:
    if process.poll() is None:process.terminate()
   for process in procs:
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:process.kill();process.wait()
if __name__=='__main__':main()
