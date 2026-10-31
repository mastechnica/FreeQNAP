#!/usr/bin/env python3
"""Deterministic privacy masks on owner-provided photographs; no generative edits.

Inputs stay outside the repository. Only PNG pixels are exported; metadata is omitted.
Coordinates use the 1152x2048 viewing orientation, scaled to the original resolution.
"""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageChops

MASKS = {
    'motherboard': [(0,145,270,380), (0,515,275,855), (438,588,494,675),
                    (412,1345,495,1544), (545,1474,842,1552), (845,784,893,925),
                    (706,440,861,540), (577,295,650,394)],
    'uart0-debug': [(0,0,307,235)],
}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--kind',choices=MASKS,required=True)
    args=parser.parse_args()
    if args.output.exists():raise SystemExit('Refusing to overwrite an existing reviewed asset')
    original=Image.open(args.source).convert('RGB')
    edited=original.copy();mask=Image.new('L',original.size,0)
    draw=ImageDraw.Draw(edited);allowed=ImageDraw.Draw(mask)
    scaled=[]
    for box in MASKS[args.kind]:
        rectangle=tuple(round(v*(original.width/1152 if i%2==0 else original.height/2048)) for i,v in enumerate(box))
        draw.rectangle(rectangle,fill=(90,94,99));allowed.rectangle(rectangle,fill=255);scaled.append(rectangle)
    difference=ImageChops.difference(original,edited).convert('L')
    outside=ImageChops.multiply(difference,ImageChops.invert(mask))
    if outside.getbbox():raise SystemExit('Pixels outside approved masks changed')
    # A fresh image excludes source EXIF, GPS, thumbnails and identifying metadata.
    output=Image.frombytes('RGB',edited.size,edited.tobytes())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    output.save(args.output,format='PNG',optimize=True)
    check=Image.open(args.output)
    if check.info:raise SystemExit('Unexpected output metadata')
    receipt={'kind':args.kind,'pixels':list(original.size),'mask_rectangles':scaled,
             'outside_mask_pixels_unchanged':True,'source_metadata_copied':False,
             'sha256':hashlib.sha256(args.output.read_bytes()).hexdigest(),
             'method':'Opaque deterministic masks; generative preview rejected and not included'}
    args.output.with_suffix('.redaction.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(args.output)
if __name__=='__main__':main()
