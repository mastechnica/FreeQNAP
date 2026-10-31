#!/usr/bin/env python3
"""Render the small repo-native logo primitives to PWA PNGs; development-only Pillow."""
from pathlib import Path
import re,xml.etree.ElementTree as ET
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parents[1];svg=ET.parse(root/'web/icon.svg').getroot();ns='{http://www.w3.org/2000/svg}'
rect=svg.find(ns+'rect');circle=svg.find(ns+'circle');path=svg.find(ns+'path')
assert len(svg)==3 and svg.attrib['viewBox']=='0 0 512 512' and all(v is not None for v in (rect,circle,path))
assert re.fullmatch(r'M[0-9. ]+L[0-9. ]+L[0-9. ]+Z',path.attrib['d'])
coords=list(map(float,re.findall(r'[0-9.]+',path.attrib['d'])));points=list(zip(coords[::2],coords[1::2]))
for size in (192,512):
 scale=4;factor=size*scale/512;im=Image.new('RGBA',(size*scale,size*scale));draw=ImageDraw.Draw(im)
 draw.rounded_rectangle((0,0,size*scale,size*scale),radius=float(rect.attrib['rx'])*factor,fill=rect.attrib['fill'])
 cx,cy,r,w=[float(circle.attrib[k])*factor for k in ('cx','cy','r','stroke-width')]
 draw.ellipse((cx-r-w/2,cy-r-w/2,cx+r+w/2,cy+r+w/2),fill=circle.attrib['stroke']);draw.ellipse((cx-r+w/2,cy-r+w/2,cx+r-w/2,cy+r-w/2),fill=circle.attrib['fill'])
 pts=[(x*factor,y*factor) for x,y in points];width=float(path.attrib['stroke-width'])*factor
 draw.line([*pts,pts[0]],fill=path.attrib['stroke'],width=round(width),joint='curve')
 for x,y in pts:draw.ellipse((x-width/2,y-width/2,x+width/2,y+width/2),fill=path.attrib['stroke'])
 target=root/'web'/f'icon-{size}.png';im.resize((size,size),Image.Resampling.LANCZOS).save(target,optimize=True)
 with Image.open(target) as check:assert check.size==(size,size);check.verify()
 print(target)
