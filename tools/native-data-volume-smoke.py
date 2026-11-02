#!/usr/bin/env python3
"""Bounded disposable file/restore campaign on two explicitly identified mounted data volumes.

No repartitioning, RAID mutation, unmount, service export or permanent NAS configuration.
The two volumes may share hardware; this test is not an independent disaster backup.
"""
import argparse,base64,hashlib,http.client,json,mmap,os,secrets,shutil,sqlite3,stat,subprocess,sys,threading,time
from pathlib import Path
from urllib.parse import urlencode
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from freeqnap.nas.common import Context,name
from freeqnap.nas.fileops import FileManager,remove_tree
from freeqnap.nas.filebackup import FileBackups
from freeqnap.nas.recovery import Recovery
from freeqnap.nas.archives import Archives
from freeqnap.nas.bundle import Bundles
from freeqnap.state import State
from freeqnap.server import NASHTTPServer,handler
from freeqnap import auth
import freeqnap
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--confirm-bounded-data-fixture',action='store_true',required=True);p.add_argument('--source-pool',required=True);p.add_argument('--source-uuid',required=True);p.add_argument('--destination-pool',required=True);p.add_argument('--destination-uuid',required=True);a=p.parse_args()
if sys.platform!='linux' or os.geteuid()!=0:raise SystemExit('Explicit Linux root test required')
if a.source_pool==a.destination_pool:raise SystemExit('Choose two distinct explicitly identified pools')
media=Path(freeqnap.__file__).resolve().parents[1]/'web/demo-media/video.mp4'
if not media.is_file():raise SystemExit('Installed test video fixture is missing; no data files created')
ident=secrets.token_hex(8);root=Path('/var/lib/freeqnap-validation')/('data-'+ident);root.mkdir(mode=0o700,parents=True);ctx=Context(root/'state');folders=[];server=None;report={};repository=None;repo_identity=None

def run(*args,**kwargs):
 result=subprocess.run(args,capture_output=True,timeout=120,**kwargs)
 if result.returncode:raise ValueError(Path(args[0]).name+' failed in bounded data fixture')
 return result.stdout

def configured():
 with sqlite3.connect('file:/var/lib/freeqnap-system/state.sqlite3?mode=ro',uri=True) as db:
  row=db.execute("SELECT value FROM settings WHERE key='nas'").fetchone()
  if not row:raise ValueError('No commissioned NAS data configuration')
  return row[0]

def review(plan):return {'plan_id':plan['id'],'digest':plan['digest'],'confirmation':plan['confirmation']}
def digest(file):
 value=hashlib.sha256()
 with Path(file).open('rb') as stream:
  while block:=stream.read(1024*1024):value.update(block)
 return value.hexdigest()
def direct(file,length):
 if length%4096:raise ValueError('Direct fixture length must be aligned')
 fd=os.open(file,os.O_RDONLY|os.O_DIRECT);value=hashlib.sha256()
 try:
  with mmap.mmap(-1,1024*1024) as buffer:
   for offset in range(0,length,1024*1024):
    count=os.preadv(fd,[buffer],offset)
    if count!=min(1024*1024,length-offset):raise ValueError('Short direct read')
    value.update(buffer[:count])
 finally:os.close(fd)
 return value.hexdigest()

try:
 original=configured();live=json.loads(original);cfg=ctx.config();pool_names=[name(a.source_pool),name(a.destination_pool)]
 for pool_id,uuid in zip(pool_names,[a.source_uuid,a.destination_uuid]):
  pool=live['pools'][pool_id]
  if pool['filesystem_uuid']!=uuid or pool.get('read_only') or pool.get('kind')=='usb' or pool.get('encrypted'):raise ValueError('Fixture requires the exact reviewed writable internal unencrypted volume')
  cfg['pools'][pool_id]=pool
 ctx.save(cfg)
 for index,pool_id in enumerate(pool_names):
  pool,mount=ctx.volume(pool_id);folder=mount/('fq-validation-'+ident+'-'+str(index));folder.mkdir(mode=0o700);info=folder.stat();folders.append((pool_id,folder,info.st_dev,info.st_ino));share='validation-'+str(index);cfg['shares'][share]={'name':share,'pool':pool_id,'path':str(folder),'gid':0,'enabled':True,'protocols':[],'users':[]}
 ctx.save(cfg);first,second=[f[1] for f in folders];files=FileManager(ctx);bundles=Bundles(ctx,files);archives=Archives(ctx,files,bundles);recovery=Recovery(ctx,files)
 payload=os.urandom(4*1024**2);expected=hashlib.sha256(payload).hexdigest();upload=files.upload_begin({'share':'validation-0','path':'payload.bin','bytes':len(payload)});chain='0'*64
 for offset in range(0,len(payload),512*1024):
  chunk=payload[offset:offset+512*1024];sha=hashlib.sha256(chunk).hexdigest();files.upload_chunk({'upload_id':upload['upload_id'],'offset':offset,'data_base64':base64.b64encode(chunk).decode(),'sha256':sha});chain=hashlib.sha256((chain+sha).encode()).hexdigest()
 files.upload_finish({'upload_id':upload['upload_id'],'hash_chain':chain});assert direct(first/'payload.bin',len(payload))==expected;report['chunked_upload_and_direct_read_hash']=True
 text=first/'Café_测试.txt';text.write_bytes('Unicode test metadata\n'.encode());text.chmod(0o640);os.setxattr(text,'user.freeqnap-fixture',b'fixture-xattr');run('setfacl','-m','u:65534:r--',str(text));original_mode=stat.S_IMODE(text.stat().st_mode);original_acl=run('getfacl','-cp',str(text));original_xattrs={k:os.getxattr(text,k) for k in os.listxattr(text)}
 transfer=files.transfer_plan({'share':'validation-0','paths':['payload.bin'],'target_share':'validation-1','target_path':'','new_name':'copied.bin','mode':'copy'});files.transfer(review(transfer));assert direct(second/'copied.bin',len(payload))==expected
 renamed=files.transfer_plan({'share':'validation-1','paths':['copied.bin'],'target_share':'validation-1','target_path':'','new_name':'renamed.bin','mode':'move'});files.transfer(review(renamed));assert not (second/'copied.bin').exists();report['cross_filesystem_copy_and_atomic_rename']=True
 try:files.transfer_plan({'share':'validation-0','paths':['payload.bin'],'target_share':'validation-1','new_name':'renamed.bin'})
 except ValueError:pass
 else:raise AssertionError('Copy would overwrite an existing target')
 recycled=files.move_plan({'share':'validation-1','path':'renamed.bin'});files.move(review(recycled));item=next(r for r in recovery.list()['items'] if r['kind']=='trash');recovery.apply(review(recovery.plan({'kind':'trash','id':item['id'],'share':'validation-1','name':'recovered.bin'})));assert direct(second/'recovered.bin',len(payload))==expected;report['recycle_and_reviewed_restore']=True
 zipped=archives.plan({'operation':'zip','share':'validation-0','paths':['payload.bin','Café_测试.txt'],'filename':'fixture.zip','max_output_bytes':16*1024**2});archives.apply(review(zipped));extract=archives.plan({'operation':'extract','share':'validation-0','path':'fixture.zip','destination':'named','max_output_bytes':16*1024**2});archives.apply(review(extract));assert digest(first/'fixture/payload.bin')==expected;report['zip_creation_and_named_extraction']=True
 files.mkdir({'share':'validation-0','name':'current-extraction'});extract=archives.plan({'operation':'extract','share':'validation-0','path':'fixture.zip','target_path':'current-extraction','destination':'current','max_output_bytes':16*1024**2});archives.apply(review(extract));assert digest(first/'current-extraction/payload.bin')==expected;report['current_folder_extraction']=True
 # A real protected HTTP endpoint reads these physical-volume files using disposable login state.
 shutil.copyfile(media,first/'video.mp4');webstate=State(root/'web');password=secrets.token_urlsafe(32);webstate.set('administrator',auth.password_hash(password))
 class FileBroker:
  def request(self,action,payload):
   return {'files.read':files.read,'files.bundle-info':bundles.info,'files.bundle-node':bundles.node,'files.bundle-read':bundles.read}[action](payload)
 server=NASHTTPServer(('127.0.0.1',0),handler(webstate,root/'web-backups',broker=FileBroker()));server.auth_lock=threading.Lock();server.login_attempts=[];threading.Thread(target=server.serve_forever,daemon=True).start();port=server.server_port
 def request(path,body=None,cookie=None,extra=None):
  c=http.client.HTTPConnection('127.0.0.1',port,timeout=30);headers={'Host':'127.0.0.1:'+str(port),'Origin':'http://127.0.0.1:'+str(port),'Content-Type':'application/json'}
  if cookie:headers['Cookie']=cookie
  headers.update(extra or {});c.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,headers);r=c.getresponse();data=r.read();out=(r.status,dict(r.getheaders()),data);c.close();return out
 code,headers,data=request('/api/login',{'password':password});assert code==200;cookie=headers['Set-Cookie'].split(';')[0];path='/api/file?'+urlencode({'share':'validation-0','path':'video.mp4','inline':'1'});code,headers,data=request(path,cookie=cookie,extra={'Range':'bytes=0-63'});assert code==206 and data==media.read_bytes()[:64] and headers['Content-Type']=='video/mp4' and headers['Content-Disposition'].startswith('inline');assert request(path)[0]==401;report['real_volume_authenticated_media_range_and_denial']=True
 ticket=bundles.start({'share':'validation-0','paths':['Café_测试.txt','video.mp4'],'filename':'selected.zip'});code,headers,data=request('/api/zip?'+urlencode({'ticket':ticket['ticket']}),cookie=cookie);assert code==200
 import io,zipfile
 with zipfile.ZipFile(io.BytesIO(data)) as zipped:assert zipped.testzip() is None and zipped.read('video.mp4')==media.read_bytes()
 report['authenticated_multi_file_zip_download']=True;server.shutdown();server.server_close();server=None
 backup=FileBackups(ctx);repo_name='validation-'+ident;backup.repository({'name':repo_name,'kind':'local','pool':pool_names[1],'password':secrets.token_urlsafe(32)});repository=Path(backup.get(repo_name)['path']);repo_identity=repository.stat().st_ino
 try:backup.backup({'repository':repo_name,'shares':['validation-0']})
 except ValueError:pass
 else:raise AssertionError('Two filesystems sharing one RAID were accepted without acknowledgment')
 result=backup.backup({'repository':repo_name,'shares':['validation-0'],'same_pool_confirmation':'SAME POOL '+repo_name});backup.check({'repository':repo_name,'read_data':True});assert not result['independent_disaster_backup'];report['same_raid_warning_and_restic_full_data_check']=True
 (first/'payload.bin').write_bytes(b'Modified after snapshot; must not be overwritten');restore_id=ctx.operation('backup.restore',{'repository':repo_name});restored=backup.restore({'repository':repo_name,'snapshot':result['snapshot_id'],'pool':pool_names[1]},restore_id);ctx.state.finish(restore_id,result=restored);stage=Path(restored['staging_directory']);restored_source=stage/str(first).lstrip('/');assert direct(restored_source/'payload.bin',len(payload))==expected;restored_text=restored_source/text.name;assert stat.S_IMODE(restored_text.stat().st_mode)==original_mode;assert run('getfacl','-cp',str(restored_text))==original_acl;assert {k:os.getxattr(restored_text,k) for k in os.listxattr(restored_text)}==original_xattrs;assert (first/'payload.bin').read_bytes().startswith(b'Modified after snapshot');report['staged_restore_bytes_modes_acls_xattrs_and_no_live_overwrite']=True
 promote=recovery.plan({'kind':'restore','id':restore_id,'share':'validation-1','name':'restored-proof'});recovery.apply(review(promote));assert direct(second/'restored-proof'/str(first).lstrip('/')/'payload.bin',len(payload))==expected;report['reviewed_atomic_restore_promotion']=True
 entry=dict(backup.get(repo_name));wrong=root/'wrong-password';wrong.write_text(secrets.token_urlsafe(32));wrong.chmod(0o600);entry['password_file']=str(wrong)
 try:backup.command(entry,'snapshots',timeout=30)
 except ValueError:pass
 else:raise AssertionError('Wrong backup password was accepted')
 backup.check({'repository':repo_name,'read_data':True});report['wrong_password_denied_and_last_good_retained']=True
 assert configured()==original,'Production NAS configuration changed during test'
 report.update(production_configuration_unchanged=True,physical_data_filesystems_used=True,raid_membership_changed=False,boot_or_flash_changed=False,independent_disaster_backup_accepted=False,bare_metal_recovery_accepted=False,payload_bytes=len(payload),payload_sha256=expected)
 # Delete only this tool's newly owned disposable roots after every verification succeeds.
 for pool_id,folder,device,inode in folders:
  ctx.volume(pool_id);info=folder.stat();assert info.st_dev==device and info.st_ino==inode and folder.name.startswith('fq-validation-'+ident)
  fd=os.open(folder.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
  try:remove_tree(fd,folder.name,device)
  finally:os.close(fd)
 assert repository.stat().st_ino==repo_identity and repository.name==repo_name
 fd=os.open(repository.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:remove_tree(fd,repository.name,repository.stat().st_dev)
 finally:os.close(fd)
 report['owned_test_files_cleaned']=True;(root/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
finally:
 if server:server.shutdown();server.server_close()
