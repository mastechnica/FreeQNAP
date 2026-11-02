#!/usr/bin/env python3
"""Inspect, enable or disable PID-1 hardware supervision on a validated TS-431XeU.

Default is read-only. Never tests expiry on mounted disks. No application outage
or HTTP failure deliberately starves the watchdog; ordinary service recovery stays
separate. Enable only after attended RAM expiry and maintenance tests.
"""
import argparse,json,os,subprocess,time
from pathlib import Path
TARGET=Path('/etc/systemd/system.conf.d/80-freeqnap-watchdog.conf')
BUS=['busctl','--system']
DEST=['org.freedesktop.systemd1','/org/freedesktop/systemd1','org.freedesktop.systemd1.Manager']
def run(*args):return subprocess.check_output(list(args),text=True,timeout=10).strip()
def get(prop):return int(run(*BUS,'get-property',*DEST,prop).split()[1])
def set_runtime(value):subprocess.run([*BUS,'set-property',*DEST,'RuntimeWatchdogUSec','t',str(value)],check=True,timeout=10)
def inspect():
 b=Path('/sys/class/watchdog/watchdog0')
 return {'manager_microseconds':get('RuntimeWatchdogUSec'),'identity':(b/'identity').read_text().strip(),'state':(b/'state').read_text().strip(),'timeout_seconds':int((b/'timeout').read_text()),'nowayout':(b/'nowayout').read_text().strip()}
def sync_parent():
 fd=os.open(TARGET.parent,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('operation',choices=['status','enable','disable']);p.add_argument('--apply',action='store_true');p.add_argument('--validated-receipt',type=Path);a=p.parse_args()
 if os.geteuid()!=0 or Path('/proc/device-tree/compatible').read_bytes().split(b'\0')[0]!=b'qnap,ts-431xeu':raise ValueError('Exact NAS board and root required')
 before=inspect()
 if before['identity']!='sp805-wdt' or before['nowayout']!='0':raise ValueError('Unexpected watchdog or irreversible mode')
 if a.operation=='enable' and (get('RebootWatchdogUSec')!=0 or get('KExecWatchdogUSec')!=0):raise ValueError('Existing shutdown watchdog policy must be reconciled first')
 if a.operation=='status' or not a.apply:print(json.dumps({'read_only':True,'before':before}));return
 if a.operation=='enable':
  if not a.validated_receipt:raise ValueError('An exact-install physical validation receipt is required')
  info=a.validated_receipt.lstat()
  if a.validated_receipt.is_symlink() or info.st_uid!=0 or info.st_mode&0o077:raise ValueError('Private root-owned receipt required')
  receipt=json.loads(a.validated_receipt.read_text())
  if receipt.get('install_id')!=Path('/etc/freeqnap-install-id').read_text().strip() or receipt.get('three_ram_expiries_passed') is not True or receipt.get('disarm_passed') is not True:raise ValueError('Physical expiry/disarm acceptance missing')
  if before['manager_microseconds']!=0 or before['state']!='inactive':raise ValueError('Existing watchdog ownership must be reconciled first')
  if TARGET.exists():raise ValueError('Existing managed policy must be reviewed first')
  for name in ('eyeq-cooling','freeqnap-cooling','freeqnap-cooling-guard'):
   if run('systemctl','is-active',name)!='active':raise ValueError('Full cooling services must be running')
  status=json.loads(Path('/run/freeqnap-cooling/status.json').read_text())
  if status.get('level')!=7 or not 0<=time.monotonic()-status['monotonic']<3:raise ValueError('Fresh full cooling required before enabling watchdog')
  TARGET.parent.mkdir(parents=True,exist_ok=True)
  text='[Manager]\nRuntimeWatchdogSec=10s\nRebootWatchdogSec=off\nKExecWatchdogSec=off\n'
  fd=os.open(TARGET,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644)
  with os.fdopen(fd,'w') as f:f.write(text);f.flush();os.fsync(f.fileno())
  sync_parent()
  try:
   set_runtime(10000000)
   after=inspect()
   if after['state']!='active' or after['manager_microseconds']!=10000000 or after['timeout_seconds']!=10:raise ValueError('Runtime watchdog ownership/timeout mismatch')
  except BaseException:
   set_runtime(0);TARGET.unlink();sync_parent();raise
 else:
  expected='[Manager]\nRuntimeWatchdogSec=10s\nRebootWatchdogSec=off\nKExecWatchdogSec=off\n'
  if not TARGET.is_file() or TARGET.is_symlink() or TARGET.read_text()!=expected:raise ValueError('Refusing to remove an unknown watchdog policy')
  set_runtime(0)
  if inspect()['state']!='inactive':raise ValueError('Watchdog did not disarm; policy retained')
  TARGET.unlink();sync_parent()
 print(json.dumps({'before':before,'after':inspect(),'production_owner':'systemd PID 1','reboot_expiry_enabled':False,'kernel_expiry_test_performed':False}))
if __name__=='__main__':main()
