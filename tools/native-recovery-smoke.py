#!/usr/bin/env python3
"""Explicit, private recovery capture/encryption test; no restore or disk layout writes."""
import argparse,base64,hashlib,json,os,secrets,shutil,sqlite3,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from freeqnap.nas.common import Context
from freeqnap.nas.system_recovery import SystemRecovery
from freeqnap.nas.local_recovery import LocalRecovery
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--confirm-private-capture',action='store_true',required=True);p.parse_args()
if os.geteuid()!=0 or Path('/proc/device-tree/compatible').read_bytes().split(b'\0')[0]!=b'qnap,ts-431xeu':raise SystemExit('Root on the spare supported NAS required')
root=Path('/var/lib/freeqnap-system/validation')/('recovery-'+secrets.token_hex(8));root.mkdir(mode=0o700,parents=True)
live=Context();fixture=Context(root);recovery=SystemRecovery(live);local=LocalRecovery(fixture,recovery);record=None
try:
 password=secrets.token_urlsafe(32);record=local.create({'secret':{'password':password}});archive,_=local.info(record['id']);sha=hashlib.sha256();offset=0
 while offset<record['bytes']:
  data=base64.b64decode(local.read({'id':record['id'],'offset':offset,'count':512*1024})['data_base64']);assert data;sha.update(data);offset+=len(data)
 assert sha.hexdigest()==record['sha256']
 with archive.open('rb') as encrypted,tempfile.TemporaryFile(dir=root) as verified:
  local.crypt(encrypted,verified,password.encode(),True);verified.seek(0);manifest=local.verify_tar(verified)
  import tarfile
  verified.seek(0)
  with tarfile.open(fileobj=verified,mode='r:gz') as tar:
   member=tar.extractfile('state/nas/state.sqlite3').read();database=root/'snapshot.sqlite3';database.write_bytes(member);database.chmod(0o600)
   with sqlite3.connect(database) as db:assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
  assert 'system/etc/shadow' in manifest['files'];assert any(k.endswith('/secrets.tdb') for k in manifest['files']);assert any(k.startswith('system/etc/ssh/ssh_host_') for k in manifest['files'])
 with archive.open('rb') as encrypted,tempfile.TemporaryFile(dir=root) as output:
  try:local.crypt(encrypted,output,b'intentionally incorrect validation password',True)
  except ValueError:pass
  else:raise AssertionError('Wrong password was accepted')
 assert password.encode() not in fixture.state.database.read_bytes()
 report={'real_private_capture':True,'files':record['files'],'encrypted_bytes':record['bytes'],'encrypted_download_sha256_matched':True,'decrypted_manifest_verified':True,'consistent_samba_credentials_captured':True,'wrong_password_denied':True,'export_password_not_persisted':True,'physical_data_disks_written':False,'live_configuration_restored':False,'full_disaster_restore_accepted':False}
 # Remove only this disposable validation archive/state. No owner archive is pruned.
 shutil.rmtree(root);print(json.dumps(report,indent=2))
except Exception:
 print('Private validation failure retained under '+str(root),file=sys.stderr);raise
