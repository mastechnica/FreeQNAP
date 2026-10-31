#!/usr/bin/env python3
"""Check local showcase links, image receipts and clean PNG exports."""
import hashlib,json,struct
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit,unquote
ROOT=Path(__file__).resolve().parents[1]
class Links(HTMLParser):
 def __init__(self):super().__init__();self.links=[];self.ids=set()
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if 'id' in a:self.ids.add(a['id'])
  for key in ('href','src'):
   if a.get(key):self.links.append(a[key])
def main():
 errors=[]
 for source,copy in [('LICENSE','docs/LICENSE.txt'),('SECURITY.md','docs/SECURITY.md')]:
  if (ROOT/source).read_bytes()!=(ROOT/copy).read_bytes():errors.append('Showcase source copy mismatch: '+copy)
 for path in (ROOT/'docs').rglob('*.html'):
  p=Links();p.feed(path.read_text())
  for link in p.links:
   u=urlsplit(link)
   if u.scheme or u.netloc:continue
   target=(path.parent/unquote(u.path)).resolve() if u.path else path
   if not target.is_relative_to(ROOT):errors.append('Link leaves package: '+str(path.relative_to(ROOT)));continue
   if target.is_dir():target=target/'index.html'
   if not target.exists():errors.append('Missing '+link+' in '+str(path.relative_to(ROOT)));continue
   if u.fragment and target.suffix=='.html':
    q=Links();q.feed(target.read_text())
    if u.fragment not in q.ids:errors.append('Missing anchor '+link)
 receipts=json.loads((ROOT/'docs/assets/screenshots/receipts.json').read_text())
 for name,receipt in receipts.items():
  raw=(ROOT/'docs/assets/screenshots'/f'{name}.png').read_bytes()
  if hashlib.sha256(raw).hexdigest()!=receipt['output_sha256']:errors.append('Screenshot hash mismatch: '+name)
  if list(struct.unpack('>II',raw[16:24]))!=receipt['output_dimensions']:errors.append('Screenshot dimensions mismatch: '+name)
  at=8
  while at<len(raw):
   n=struct.unpack('>I',raw[at:at+4])[0];kind=raw[at+4:at+8]
   if kind not in (b'IHDR',b'IDAT',b'IEND'):errors.append('Unexpected PNG metadata: '+name+' '+repr(kind))
   at+=n+12
 if errors:raise SystemExit('\n'.join(errors))
 print('PASS: HTML local links/anchors, screenshot hashes/dimensions and metadata-free PNG chunks.')
if __name__=='__main__':main()
