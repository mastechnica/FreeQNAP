#!/usr/bin/env python3
"""Crop actual dashboard captures and mask identifiers; never generate UI pixels."""
import argparse,hashlib,json
from pathlib import Path
from PIL import Image,ImageDraw,ImageChops
SPECS={
 'overview':{'crop':[0,164,2678,1536],'masks':[]},
 'files':{'crop':[0,164,2678,1788],'masks':[[100,1124,256,1156],[211,1281,330,1314],[1373,1124,1530,1156],[1483,1281,1609,1314]]},
 'network':{'crop':[0,164,2678,1760],'masks':[[1036,911,1620,950]]},
}
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input-directory',type=Path,required=True);p.add_argument('--output-directory',type=Path,required=True);a=p.parse_args();a.output_directory.mkdir(parents=True,exist_ok=True);receipts={}
 for name,spec in SPECS.items():
  source=a.input_directory/('freeqnap-public-'+name+'-original.png');raw=source.read_bytes();original=Image.open(source).convert('RGB');crop=spec['crop'];clean=original.crop(crop);keep=Image.new('L',clean.size,255);draw=ImageDraw.Draw(clean);kd=ImageDraw.Draw(keep)
  for x1,y1,x2,y2 in spec['masks']:
   box=(x1-crop[0],y1-crop[1],x2-crop[0]-1,y2-crop[1]-1);draw.rectangle(box,fill='#26222b');kd.rectangle(box,fill=0)
  difference=ImageChops.difference(original.crop(crop),clean);outside=ImageChops.multiply(difference,Image.merge('RGB',(keep,keep,keep)));assert outside.getbbox() is None,'Changed original pixels outside redaction masks'
  out=a.output_directory/(name+'.png');clean.info.clear();clean.save(out,optimize=True)
  receipts[name]={'original_sha256':sha(raw),'output_sha256':sha(out.read_bytes()),'original_dimensions':list(original.size),'output_dimensions':list(clean.size),'crop_original_coordinates':crop,'opaque_masks_original_coordinates':spec['masks'],'outside_masks':'Original cropped pixels unchanged','capture_date':'2026-10-31','source':'Running FreeQNAP dashboard; no synthetic state or metrics'}
 (a.output_directory/'receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')
 print('Prepared three original-pixel screenshot crops and redaction receipts.')
if __name__=='__main__':main()
