"""Register locally verified audio without decoding the same album repeatedly.

Internal maintenance/import helper, deliberately not an HTTP operation. Callers
must pin and verify originals before invoking it. No input path is followed.
"""
import contextlib,json,math,os,stat,time
from pathlib import Path

def identity(st):return {'inode':st.st_ino,'bytes':st.st_size,'mtime_ns':st.st_mtime_ns}

def register(radio,kind,ident,leaf,metadata,cover=None,replace_identity=None,root_fd=None,connection=None):
 from .myradio import category,filename,IDENT,FIELDS,clean
 from .personal_photos import directory
 kind=category(kind);leaf=filename(leaf)
 if not isinstance(ident,str) or not IDENT.fullmatch(ident):raise ValueError('Invalid audio identity')
 allowed=set(FIELDS)|{'disc','codec','duration','identification_status','metadata_sources','audio_status','audio_warning'}
 if not isinstance(metadata,dict) or set(metadata)-allowed:raise ValueError('Unknown prepared audio metadata')
 value={}
 for k,v in metadata.items():
  if k=='audio_status':
   if v not in ('unavailable','verified-header'):raise ValueError('Invalid audio availability')
   value[k]=v
  elif k=='duration':
   if not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=30*86400:raise ValueError('Invalid duration')
   value[k]=v
  elif k=='metadata_sources':
   if not isinstance(v,dict) or len(v)>20 or any(a not in allowed or b not in ('embedded','folder-consensus','existing-album-nfo','filename-needs-review','reviewed-folder','reviewed-online','reviewed-artwork') for a,b in v.items()):raise ValueError('Invalid metadata provenance')
   value[k]=v
  else:value[k]=clean(v,FIELDS.get(k,100))
 if cover is not None and (not isinstance(cover,bytes) or not cover.startswith(b'\xff\xd8\xff') or not 1<=len(cover)<=256*1024):raise ValueError('Invalid prepared cover')
 path=kind+'/'+ident+'/'+leaf
 try:old=radio.asset(ident)
 except ValueError:old=None
 if old and old['path']!=path:
  if not replace_identity or any(old.get(k)!=v for k,v in replace_identity.items()) or set(replace_identity)!={'path','inode','bytes','mtime_ns'}:raise ValueError('Reviewed replacement identity required')
  with radio.opened(old):pass
 with (radio.root() if root_fd is None else contextlib.nullcontext(root_fd)) as root,directory(root,(kind,ident)) as folder:
  cfg=radio.config();radio.marker(root,{'library_id':cfg['library_id'],'filesystem_uuid':cfg['filesystem_uuid']})
  fd=os.open(leaf,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=folder)
  try:
   st=os.fstat(fd)
   if not stat.S_ISREG(st.st_mode) or st.st_dev!=os.fstat(root).st_dev:raise ValueError('Prepared original identity changed')
   value['title']=value.get('title') or Path(leaf).stem
   value['playable']='original-only' if value.get('audio_status')=='unavailable' or Path(leaf).suffix.lower() in ('.aax','.ape','.wma') else 'audio'
   if value.get('audio_status')=='unavailable':value['reading_note']='This source did not contain decodable audio in the library review. The original is preserved; replace it with a valid original before playback.'
   elif value['playable']=='original-only':value['reading_note']='Original audio retained unchanged. Use a compatible authorized player or link a browser-compatible companion edition.'
   if kind=='books':value['book_type']='audiobook';value['author']=value.get('author') or value.get('artist','')
   value['_prepared']=identity(st)
   if cover is not None:value.update(has_cover=True,custom_cover=True)
   elif old and old['metadata'].get('has_cover'):value.update(has_cover=True,custom_cover=bool(old['metadata'].get('custom_cover')))
   with (radio.ctx.state.connect() if connection is None else contextlib.nullcontext(connection)) as db:
    if old:
     n=db.execute('UPDATE radio_assets SET path=?,name=?,bytes=?,inode=?,mtime_ns=?,metadata=? WHERE id=? AND path=? AND inode=? AND bytes=? AND mtime_ns=?',(path,leaf,st.st_size,st.st_ino,st.st_mtime_ns,json.dumps(value),ident,old['path'],old['inode'],old['bytes'],old['mtime_ns'])).rowcount
     if n!=1:raise ValueError('Catalog changed during prepared import')
    else:db.execute('INSERT INTO radio_assets(id,category,path,name,bytes,inode,mtime_ns,metadata,created) VALUES(?,?,?,?,?,?,?,?,?)',(ident,kind,path,leaf,st.st_size,st.st_ino,st.st_mtime_ns,json.dumps(value),time.time()))
   if cover is not None:radio.write_file(folder,'cover.jpg',cover)
   if cfg.get('save_sidecars'):radio.write_file(folder,'metadata.json',json.dumps(value,ensure_ascii=False,indent=2).encode())
  finally:os.close(fd)
 return radio.public({'id':ident,'category':kind,'name':leaf,'bytes':st.st_size,'metadata':value,'created':old['created'] if old else time.time(),'favorite':old['favorite'] if old else 0,'hidden':old['hidden'] if old else 0})
