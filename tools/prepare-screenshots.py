#!/usr/bin/env python3
"""Crop actual dashboard captures and mask identifiers and optionally substitute labeled scenic thumbnails."""
import argparse,hashlib,json
from pathlib import Path
from PIL import Image,ImageDraw,ImageChops,ImageOps
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--specs',type=Path,default=Path(__file__).resolve().parents[1]/'docs/assets/screenshots/capture-specs.json');p.add_argument('--date',default='2026-11-05');p.add_argument('--input-directory',type=Path,required=True);p.add_argument('--output-directory',type=Path,required=True);a=p.parse_args();a.output_directory.mkdir(parents=True,exist_ok=True);receipts={}
 for name,spec in json.loads(a.specs.read_text()).items():
  source=a.input_directory/('freeqnap-public-'+name+'-original.png');raw=source.read_bytes();original=Image.open(source).convert('RGB');crop=spec['crop'];clean=original.crop(crop);keep=Image.new('L',clean.size,255);draw=ImageDraw.Draw(clean);kd=ImageDraw.Draw(keep)
  for x1,y1,x2,y2 in spec['masks']:
   box=(x1-crop[0],y1-crop[1],x2-crop[0]-1,y2-crop[1]-1);draw.rectangle(box,fill='#26222b');kd.rectangle(box,fill=0)
  scenic=spec.get('scenic_thumbnails')
  if scenic:
   sheet=Image.open(Path(__file__).resolve().parents[1]/scenic['asset']).convert('RGB');cols,rows=scenic['grid']
   for i,(x1,y1,x2,y2) in enumerate(scenic['boxes']):
    tile=sheet.crop((round((i%cols)*sheet.width/cols),round((i//cols)*sheet.height/rows),round((i%cols+1)*sheet.width/cols),round((i//cols+1)*sheet.height/rows)))
    box=(x1-crop[0],y1-crop[1],x2-crop[0],y2-crop[1]);w,h=x2-x1,y2-y1
    frame=Image.new('RGB',(w,h),(8,8,10));photo=ImageOps.fit(tile,(w-4,h-4));shape=Image.new('L',photo.size,0);ImageDraw.Draw(shape).rounded_rectangle((0,0,photo.width-1,photo.height-1),radius=8,fill=255);frame.paste(photo,(2,2),shape)
    # Retain the visible unchecked selection and location-badge affordances.
    fd=ImageDraw.Draw(frame);fd.rounded_rectangle((w-45,9,w-10,44),radius=5,fill='#20232b');fd.rectangle((w-39,15,w-16,37),fill='white',outline='#bec1c9',width=2)
    fd.ellipse((16,h-35,36,h-15),fill='#11151c');fd.ellipse((22,h-29,30,h-21),outline='white',width=1);fd.line((26,h-32,26,h-18),fill='white',width=1);fd.line((19,h-25,33,h-25),fill='white',width=1)
    clean.paste(frame,box[:2]);kd.rectangle((box[0],box[1],box[2]-1,box[3]-1),fill=0)
  difference=ImageChops.difference(original.crop(crop),clean);outside=ImageChops.multiply(difference,Image.merge('RGB',(keep,keep,keep)));assert outside.getbbox() is None,'Changed original pixels outside documented replacement regions'
  out=a.output_directory/(name+'.png');clean.info.clear();clean.save(out,optimize=True)
  receipts[name]={'original_sha256':sha(raw),'output_sha256':sha(out.read_bytes()),'original_dimensions':list(original.size),'output_dimensions':list(clean.size),'crop_original_coordinates':crop,'opaque_masks_original_coordinates':spec['masks'],'outside_masks':'Original cropped pixels unchanged outside masks and any listed illustrative thumbnail regions','illustrative_thumbnail_regions':scenic['boxes'] if scenic else [],'capture_date':a.date,'source':'Running FreeQNAP dashboard; scenic thumbnails substituted for privacy' if scenic else 'Running FreeQNAP dashboard; no synthetic state or metrics'}
 (a.output_directory/'receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')
 print('Prepared',len(receipts),'original-pixel screenshot crops and redaction receipts.')
if __name__=='__main__':main()
