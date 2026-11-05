"""Private, bounded transfer telemetry; never exposes unpublished staging paths."""
import os,stat,time
from ..state import atomic

class Meter:
 def __init__(self,record,checkpoint):
  self.record=record;self.checkpoint=checkpoint;self.last=time.monotonic();self.flushed=0
  self.value={'phase':'scanning','started_at':time.time(),'updated_at':time.time(),'total_bytes':0,'total_files':0,'totals_ready':False,'copied_bytes':0,'verified_bytes':0,'files_completed':0,'copy_seconds':0.,'verify_seconds':0.,'current_file':''};checkpoint['progress']=self.value;self.flush(True)
 def tick(self,phase=None,copied=0,verified=0,files=0,current=None,force=False):
  now=time.monotonic();key={'copying':'copy_seconds','verifying':'verify_seconds'}.get(self.value['phase'])
  if key:self.value[key]+=now-self.last
  self.last=now
  if phase:self.value['phase']=phase
  if current is not None:self.value['current_file']=current
  self.value['copied_bytes']+=copied;self.value['verified_bytes']+=verified;self.value['files_completed']+=files;self.flush(force)
 def flush(self,force=False):
  now=time.monotonic()
  if force or now-self.flushed>=.5:self.value['updated_at']=time.time();atomic(self.record,self.checkpoint);self.flushed=now
 def scan(self,parent,leaf,device,depth=0):
  if depth>64:raise ValueError('Transfer tree depth limit reached')
  before=os.stat(leaf,dir_fd=parent,follow_symlinks=False)
  if before.st_dev!=device or leaf.startswith('.freeqnap'):raise ValueError('Nested mounts and reserved folders cannot be copied')
  if stat.S_ISREG(before.st_mode):
   self.value['total_files']+=1;self.value['total_bytes']+=before.st_size
   if self.value['total_files']>200000:raise ValueError('Transfer file limit reached')
  elif stat.S_ISDIR(before.st_mode):
   fd=os.open(leaf,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
   try:
    self.value['scanned_folders']=self.value.get('scanned_folders',0)+1
    if self.value['scanned_folders']>200000:raise ValueError('Transfer directory limit reached')
    for name in os.listdir(fd):self.scan(fd,name,device,depth+1)
   finally:os.close(fd)
  else:raise ValueError('Symlinks and special files cannot be copied')
  self.flush()

def summarize(p,status):
 total=p.get('total_bytes',0);copy=p.get('copied_bytes',0);verify=p.get('verified_bytes',0)
 cr=copy/p['copy_seconds'] if p.get('copy_seconds',0)>0 else 0;vr=verify/p['verify_seconds'] if p.get('verify_seconds',0)>0 else 0
 stale=status=='running' and time.time()-p.get('updated_at',0)>30
 eta=None
 if status=='running' and p.get('totals_ready') and cr>0 and not stale:
  eta=max(0,total-copy)/cr+max(0,total-verify)/(vr or cr)
 percent=100. if status=='succeeded' else min(99.9,100*(copy+verify)/(2*total)) if total and p.get('totals_ready') else None
 return {**p,'percent':percent,'copy_bytes_per_second':cr,'verify_bytes_per_second':vr,'eta_seconds':eta,'stale':stale}
