#!/usr/bin/env python3
"""Replace a stock DEVICESCAN policy with explicit stable internal SATA targets.

Preserves existing options/notification preferences. Does not probe USB bridges,
run disk tests, alter custom per-device policies or send a test notification.
"""
import argparse,hashlib,json,os,pathlib,subprocess,sys,tempfile,time

def plan():
 path=pathlib.Path('/etc/smartd.conf');text=path.read_text();active=[s for s in text.splitlines() if s.strip() and not s.lstrip().startswith('#')]
 if len(active)!=1 or not active[0].startswith('DEVICESCAN '):return None,{'changed':False,'custom_policy_retained':True,'review_usb_exclusions_manually':True}
 options=active[0][len('DEVICESCAN'):];disks=json.loads(subprocess.check_output(['lsblk','-J','-d','-o','PATH,TYPE,TRAN']))['blockdevices'];targets=[]
 for d in disks:
  if d['type']!='disk' or d.get('tran')!='sata':continue
  device=pathlib.Path(d['path']);ancestry=(pathlib.Path('/sys/class/block')/device.name/'device').resolve(strict=True)
  if any(p.name.startswith('usb') for p in ancestry.parents):raise ValueError('USB ancestry disagrees with SATA transport')
  links=sorted(p for p in pathlib.Path('/dev/disk/by-id').glob('wwn-*') if p.is_symlink() and p.resolve()==device)
  if len(links)!=1:raise ValueError('One stable internal SATA WWN is required')
  targets.append(str(links[0]))
 if not targets or len(set(targets))!=len(targets):raise ValueError('No unambiguous internal SATA monitoring targets')
 lines=[('# FreeQNAP replaced stock automatic bus scan with explicit internal SATA targets.' if line==active[0] else line) for line in text.splitlines()]
 lines.extend(t+options for t in targets);return ('\n'.join(lines)+'\n'),{'changed':True,'internal_targets':len(targets),'usb_auto_probe':False,'notification_options_preserved':True,'old_sha256':hashlib.sha256(text.encode()).hexdigest()}

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');a=parser.parse_args();value,result=plan()
 if a.apply and value is not None:
  if os.geteuid()!=0:raise SystemExit('Local root required')
  old=pathlib.Path('/etc/smartd.conf');backup=pathlib.Path('/var/lib/freeqnap-system/smartd');backup.mkdir(mode=0o700,parents=True,exist_ok=True);saved=backup/(result['old_sha256']+'.conf')
  if not saved.exists():
   with saved.open('x') as f:os.chmod(saved,0o600);f.write(old.read_text());f.flush();os.fsync(f.fileno())
  fd,tmp=tempfile.mkstemp(prefix='.freeqnap-smartd-',dir='/etc')
  try:
   with os.fdopen(fd,'w') as f:os.fchmod(f.fileno(),0o600);f.write(value);f.flush();os.fsync(f.fileno())
   os.replace(tmp,old);directory=os.open('/etc',os.O_DIRECTORY|os.O_RDONLY)
   try:os.fsync(directory)
   finally:os.close(directory)
  finally:pathlib.Path(tmp).unlink(missing_ok=True)
 print(json.dumps(result),flush=True)
if __name__=='__main__':main()
