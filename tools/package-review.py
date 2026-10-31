#!/usr/bin/env python3
"""Create a reproducible source-only ZIP from the exact committed Git tree. No push."""
import argparse,hashlib,json,subprocess,zipfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]
def git(*args):return subprocess.check_output(['git','-C',str(ROOT),*args])
def digest(data):return hashlib.sha256(data).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if git('status','--porcelain').strip():raise SystemExit('Commit or reconcile all changes before packaging.')
 commit=git('rev-parse','HEAD').decode().strip();files=[]
 for item in git('ls-tree','-rz','HEAD').split(b'\0'):
  if not item:continue
  meta,path=item.split(b'\t',1);mode,kind,oid=meta.split();name=path.decode();parts=PurePosixPath(name).parts
  if kind!=b'blob' or mode==b'120000':raise SystemExit('Unsupported object: '+name)
  if any(x in ('.git','.private','.venv','dist','build','__pycache__') for x in parts):raise SystemExit('Private/generated path: '+name)
  if Path(name).suffix.lower() in ('.key','.pem','.img','.bin','.ko','.db','.sqlite','.sqlite3','.log','.heic'):raise SystemExit('Excluded artifact: '+name)
  data=git('show',commit+':'+name);files.append((name,data,mode))
 a.output.mkdir(parents=True,exist_ok=True);archive=a.output/'FreeQNAP-source-review.zip';manifest={'format':1,'project':'FreeQNAP','source_commit':commit,'scope':'Committed source and public documentation only; no Git history or OS binaries','files':[{'path':n,'bytes':len(d),'sha256':digest(d)} for n,d,m in files]}
 def put(z,name,data,mode=b'100644'):
  info=zipfile.ZipInfo('FreeQNAP/'+name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=(0o100755 if mode==b'100755' else 0o100644)<<16;z.writestr(info,data)
 with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for name,data,mode in files:put(z,name,data,mode)
  put(z,'SOURCE-MANIFEST.json',(json.dumps(manifest,indent=2)+'\n').encode())
 with zipfile.ZipFile(archive) as z:
  if z.testzip() is not None:raise SystemExit('ZIP integrity failed')
  for row in manifest['files']:
   if digest(z.read('FreeQNAP/'+row['path']))!=row['sha256']:raise SystemExit('ZIP member mismatch')
 (a.output/'SOURCE-MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
 checksum=digest(archive.read_bytes());(a.output/'SHA256SUMS').write_text(checksum+'  '+archive.name+'\n')
 print(json.dumps({'archive':str(archive),'source_commit':commit,'files':len(files),'bytes':archive.stat().st_size,'sha256':checksum,'published':False},indent=2))
if __name__=='__main__':main()
