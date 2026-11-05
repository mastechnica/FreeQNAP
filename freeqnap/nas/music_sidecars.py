"""Identity-bound local music metadata; unrelated release NFOs stay untouched."""
import hashlib,json,os,stat
from .myradio import FIELDS
KEYS={'title','artist','album','album_artist','genre','year','track','disc','composer','description'}
def name(leaf):
 value=leaf+'.metadata.json'
 return value if len(value.encode())<=255 else '.freeqnap-track-'+hashlib.sha256(leaf.encode()).hexdigest()[:24]+'.json'
def document(leaf,st,metadata):
 return {'schema':1,'application':'FreeQNAP music metadata','file':{'name':leaf,'inode':st.st_ino,'bytes':st.st_size,'mtime_ns':st.st_mtime_ns},'metadata':{k:v for k,v in metadata.items() if k in KEYS}}
def read(parent,leaf,st):
 try:
  fd=os.open(name(leaf),os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent)
  try:
   info=os.fstat(fd)
   if not stat.S_ISREG(info.st_mode) or info.st_dev!=st.st_dev or info.st_size>64*1024:return {}
   value=json.loads(os.read(fd,64*1024+1))
  finally:os.close(fd)
  if value.get('schema')!=1 or value.get('application')!='FreeQNAP music metadata' or value.get('file')!={'name':leaf,'inode':st.st_ino,'bytes':st.st_size,'mtime_ns':st.st_mtime_ns}:return {}
  metadata=value['metadata']
  if not isinstance(metadata,dict) or set(metadata)-KEYS:return {}
  if any(not isinstance(v,str) or len(v)>FIELDS[k] or any(ord(c)<32 and c not in '\n\t' for c in v) for k,v in metadata.items()):return {}
  return metadata
 except (OSError,ValueError,KeyError,TypeError):return {}
