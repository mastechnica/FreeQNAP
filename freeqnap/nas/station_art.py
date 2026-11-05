"""Station logos through bounded public fetches; deterministic local fallback art."""
import base64,hashlib,html,json,os,re,tempfile,threading,time
from pathlib import Path
from . import public_http
from .personal_metadata import jpeg
_SLOT=threading.BoundedSemaphore(1)
PALETTES=[('#113e56','#209bc0'),('#45236c','#c557bb'),('#6d2339','#e36853'),('#164b43','#36b58b'),('#3a3572','#6386de'),('#614021','#daab43')]
def fallback(name,genre,ident):
 a,b=PALETTES[int(hashlib.sha256(ident.encode()).hexdigest()[:4],16)%len(PALETTES)];initials=''.join(p[0] for p in name.split()[:2]).upper() or 'FM'
 return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 384 384"><defs><linearGradient id="g" x2="1" y2="1"><stop stop-color="{a}"/><stop offset="1" stop-color="{b}"/></linearGradient></defs><rect width="384" height="384" rx="28" fill="url(#g)"/><g fill="none" stroke="#fff" opacity=".13" stroke-width="2"><circle cx="310" cy="70" r="80"/><circle cx="310" cy="70" r="125"/><circle cx="310" cy="70" r="170"/></g><path d="M65 267v-18m20 28v-38m20 45v-52m20 45v-38m20 28v-18" stroke="#fff" opacity=".7" stroke-width="7" stroke-linecap="round"/><text x="38" y="62" fill="#fff" opacity=".75" font-family="sans-serif" font-size="16" letter-spacing="4">LIVE RADIO</text><text x="35" y="205" fill="#fff" font-family="sans-serif" font-weight="700" font-size="110">{html.escape(initials[:2])}</text><text x="38" y="335" fill="#fff" font-family="sans-serif" font-size="17">{html.escape((genre or 'YOUR SOUND. LIVE.')[:28].upper())}</text></svg>'.encode()
def artwork(ctx,request):
 ident=request.get('id','')
 if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{32}',ident):raise ValueError('Choose a radio station')
 with ctx.state.connect() as db:row=db.execute('SELECT name,metadata FROM radio_stations WHERE id=?',(ident,)).fetchone()
 if not row:raise ValueError('Station not found')
 meta=json.loads(row['metadata']);url=meta.get('favicon');raw=None;kind='image/svg+xml';cache=ctx.directory/'radio-station-art';cache.mkdir(mode=0o700,exist_ok=True)
 if isinstance(url,str) and url:
  key=hashlib.sha256(('raster-v2\0'+url).encode()).hexdigest();path=cache/(key+'.jpg');failed=cache/(key+'.failed')
  if path.is_file() and not path.is_symlink() and time.time()-path.stat().st_mtime<7*86400:raw=path.read_bytes();kind='image/jpeg'
  elif not (failed.exists() and time.time()-failed.stat().st_mtime<3600) and _SLOT.acquire(False):
   try:
    data=public_http.fetch(url,512*1024)
    if not (data.startswith((b'\x89PNG\r\n\x1a\n',b'\xff\xd8\xff',b'GIF87a',b'GIF89a',b'\x00\x00\x01\x00')) or data[:4]==b'RIFF' and data[8:12]==b'WEBP'):raise ValueError('Unsupported station image')
    with tempfile.TemporaryFile() as source:
     source.write(data);source.flush();source.seek(0);decoded=jpeg(source.fileno(),memory_limit=384*1024**2)
    if not decoded.startswith(b'\xff\xd8') or len(decoded)>256*1024:raise ValueError('Invalid station thumbnail')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(decoded)
    raw=decoded;kind='image/jpeg'
   except (ValueError,OSError,KeyError):failed.touch(mode=0o600)
   finally:_SLOT.release()
 # Only cached, derived artwork is expired; no originals or library data are touched.
 for old in sorted(cache.glob('*'),key=lambda p:p.stat().st_mtime,reverse=True)[256:]:
  if old.is_file() and not old.is_symlink():old.unlink()
 if raw is None:raw=fallback(row['name'],str(meta.get('tags') or '').split(',')[0],ident)
 return {'mime':kind,'data_base64':base64.b64encode(raw).decode(),'station_icon':kind=='image/jpeg'}
