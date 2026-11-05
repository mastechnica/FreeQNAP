"""Read-only, isolated primary HEIF-image decoder. Writes bounded RGB PPM only."""
import argparse,ctypes as C,os,re,sys

class Error(C.Structure):
 _fields_=[('code',C.c_int),('subcode',C.c_int),('message',C.c_char_p)]

def dimensions(width,height,edge):
 if not 0<width<=20000 or not 0<height<=20000 or width*height>80000000:raise ValueError('HEIF image exceeds preview dimensions')
 ratio=min(1,edge/max(width,height));return max(1,round(width*ratio)),max(1,round(height*ratio))

def render(source,edge):
 if not re.fullmatch(r'/proc/self/fd/[0-9]+',source) or edge not in (384,1600):raise ValueError('Invalid decoder input')
 lib=C.CDLL('libheif.so.1');ptr=C.c_void_p
 def bind(name,args,result):
  fn=getattr(lib,name);fn.argtypes=args;fn.restype=result;return fn
 alloc=bind('heif_context_alloc',[],ptr);free=bind('heif_context_free',[ptr],None)
 read=bind('heif_context_read_from_memory_without_copy',[ptr,ptr,C.c_size_t,ptr],Error)
 primary=bind('heif_context_get_primary_image_handle',[ptr,C.POINTER(ptr)],Error)
 release=bind('heif_image_handle_release',[ptr],None);image_release=bind('heif_image_release',[ptr],None)
 width=bind('heif_image_handle_get_width',[ptr],C.c_int);height=bind('heif_image_handle_get_height',[ptr],C.c_int)
 decode=bind('heif_decode_image',[ptr,C.POINTER(ptr),C.c_int,C.c_int,ptr],Error)
 scale=bind('heif_image_scale_image',[ptr,C.POINTER(ptr),C.c_int,C.c_int,ptr],Error)
 plane=bind('heif_image_get_plane_readonly',[ptr,C.c_int,C.POINTER(C.c_int)],ptr)
 threads=bind('heif_context_set_max_decoding_threads',[ptr,C.c_int],None)
 def check(error):
  if error.code:raise ValueError('HEIF primary image decoding failed')
 ctx=alloc();handle=ptr();image=ptr();scaled=ptr()
 if not ctx:raise ValueError('HEIF context unavailable')
 try:
  fd=int(source.rsplit('/',1)[1]);length=os.fstat(fd).st_size
  if not 0<length<=128*1024**2:raise ValueError('HEIF source exceeds preview input limit')
  raw=os.pread(fd,length,0)
  if len(raw)!=length:raise ValueError('HEIF source was truncated')
  source_buffer=C.create_string_buffer(raw);del raw
  threads(ctx,1);check(read(ctx,source_buffer,length,None));check(primary(ctx,C.byref(handle)))
  w,h=dimensions(width(handle),height(handle),edge)
  # RGB/interleaved RGB (8-bit); libheif assembles the primary grid and applies transforms.
  check(decode(handle,C.byref(image),1,10,None));check(scale(image,C.byref(scaled),w,h,None))
  stride=C.c_int();pixels=plane(scaled,10,C.byref(stride))
  if not pixels or not w*3<=stride.value<=100000:raise ValueError('Invalid HEIF pixel plane')
  out=sys.stdout.buffer;out.write(('P6\n%d %d\n255\n'%(w,h)).encode())
  for y in range(h):out.write(C.string_at(pixels+y*stride.value,w*3))
  out.flush()
 finally:
  if scaled:image_release(scaled)
  if image:image_release(image)
  if handle:release(handle)
  free(ctx)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--input',required=True);parser.add_argument('--edge',type=int,required=True);a=parser.parse_args()
 try:render(a.input,a.edge)
 except Exception:raise SystemExit('HEIF preview unavailable') from None
