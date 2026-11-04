"""Isolated media cleaner; original input is read-only, networking is disabled."""
import json,os,struct,subprocess,sys,tempfile
from pathlib import Path
LIMIT=128*1024**2

def jpeg_clean(data):
 if not data.startswith(b'\xff\xd8'):raise ValueError('Invalid JPEG')
 out=bytearray(data[:2]);i=2
 while i<len(data):
  start=i
  if data[i]!=255:raise ValueError('Invalid JPEG marker')
  while i<len(data) and data[i]==255:i+=1
  if i>=len(data):raise ValueError('Truncated JPEG')
  marker=data[i];i+=1
  if marker==0xda:return bytes(out)+data[start:]
  if marker==0xd9:return bytes(out)+data[start:i]
  if i+2>len(data):raise ValueError('Truncated JPEG')
  size=int.from_bytes(data[i:i+2],'big')
  if size<2 or i+size>len(data):raise ValueError('Invalid JPEG segment')
  if not (0xe0<=marker<=0xef or marker==0xfe):out+=data[start:i+size]
  i+=size
 raise ValueError('Incomplete JPEG')

# Only structural MP4 boxes and required codec parameters survive. Fragmented
# output uses relative fragment addressing, so removing moov metadata is safe.
CONTAINERS={b'moov',b'trak',b'mdia',b'minf',b'dinf',b'stbl',b'mvex',b'moof',b'traf',b'mfra'}
LEAVES={b'ftyp',b'mdat',b'mvhd',b'tkhd',b'mdhd',b'hdlr',b'vmhd',b'smhd',b'dref',b'stsd',b'stts',b'stsc',b'stsz',b'stco',b'co64',b'stss',b'ctts',b'trex',b'mfhd',b'tfhd',b'tfdt',b'trun',b'tfra',b'mfro',b'free',b'skip',b'sdtp',b'sidx'}
def mp4_clean(data):
 out=bytearray();i=0
 while i<len(data):
  if i+8>len(data):raise ValueError('Invalid MP4')
  n,tag=struct.unpack('>I4s',data[i:i+8])
  if n<8 or i+n>len(data):raise ValueError('Invalid MP4 box')
  body=data[i+8:i+n]
  if tag in (b'udta',b'meta',b'uuid'):pass
  elif tag in CONTAINERS:
   body=mp4_clean(body);out+=struct.pack('>I4s',len(body)+8,tag)+body
  elif tag==b'hdlr':
   if len(body)<24:raise ValueError('Invalid handler box')
   body=body[:24]+b'\0';out+=struct.pack('>I4s',len(body)+8,tag)+body
  elif tag in LEAVES:out+=data[i:i+n]
  else:raise ValueError('Unrecognized MP4 structure; cannot guarantee metadata removal')
  i+=n
 return bytes(out)

def run(source):
 with tempfile.TemporaryDirectory() as folder:
  inp=Path(folder)/'input';out=Path(folder)/'output'
  with open(source,'rb') as src,inp.open('wb') as dest:
   while True:
    data=src.read(1024*1024)
    if not data:break
    dest.write(data)
    if dest.tell()>LIMIT:raise ValueError('Too large')
  probe=subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-show_streams','-of','json',str(inp)],capture_output=True,timeout=30,check=True)
  streams=json.loads(probe.stdout)['streams'];videos=[s for s in streams if s['codec_type']=='video'];audio=[s for s in streams if s['codec_type']=='audio']
  if not videos:raise ValueError('Choose a photo or video')
  v=videos[0];codec=v['codec_name'];common=['ffmpeg','-nostdin','-v','error','-threads','1','-protocol_whitelist','file,pipe','-i',str(inp),'-map','0:'+str(v['index']),'-map_metadata','-1','-map_chapters','-1']
  image=codec in ('mjpeg','png','webp','tiff','bmp','gif') or int(v.get('nb_frames','0') or 0)==1
  if image:
   command=common+['-frames:v','1','-vf',r'scale=min(4096\,iw):-2','-c:v','mjpeg','-q:v','3','-f','image2',str(out)];mime=b'image/jpeg'
  else:
   if codec not in ('h264','hevc'):raise ValueError('Only H.264 and HEVC video can be cleaned without transcoding')
   a=next((s for s in audio if s['codec_name']=='aac'),None)
   if audio and not a:raise ValueError('Only AAC audio is supported for private video sharing')
   if a:common+=['-map','0:'+str(a['index'])]
   command=common+['-c','copy','-bsf:v','filter_units=remove_types='+('6' if codec=='h264' else '39|40|62|63'),'-metadata','encoder=','-fflags','+bitexact','-flags:v','+bitexact','-movflags','frag_keyframe+empty_moov+default_base_moof','-f','mp4',str(out)];mime=b'video/mp4'
  subprocess.run(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=120,check=True)
  raw=out.read_bytes()
  if len(raw)>LIMIT:raise ValueError('Too large')
  raw=jpeg_clean(raw) if image else mp4_clean(raw)
  sys.stdout.buffer.write(mime+b'\n'+raw)
if __name__=='__main__':
 try:run(sys.argv[1])
 except Exception:sys.exit(1)
