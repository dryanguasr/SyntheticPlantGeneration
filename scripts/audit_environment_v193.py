"""Audit V193 annotations for all foreground/neighbour capachos and show full views."""
import json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
r=Path('outputs/integral_diagnosis_20261014');o=r/'field_environment_v193';p=o/'evaluator_private';mapping=json.loads((p/'class_mapping_private.json').read_text());protocol=json.loads((p/'environment_protocol.json').read_text());records=[]
for e in protocol['plants']:assert hashlib.sha256(Path(e['source']).read_bytes()).hexdigest()==e['source_sha256']
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',22);colors=np.array([[255,180,40],[40,210,255],[240,90,200]])
for i in range(2):
 folder=p/f'view_{i:03d}';a=json.loads((folder/'annotations_private.json').read_text());mask=np.array(Image.open(folder/'mask_calyx_crisp_v2.png').convert('RGB')).astype(np.uint32);packed=mask[:,:,0]*65536+mask[:,:,1]*256+mask[:,:,2];values,counts=np.unique(packed,return_counts=True);counts=dict(zip(values.tolist(),counts.tolist()));known=set();rgb=np.array(Image.open(folder/'rgb.png').convert('RGB'));overlay=rgb.copy();visible={};pixels={}
 for key,item in a['items'].items():
  color=a['palette'][key];code=color[0]*65536+color[1]*256+color[2];known.add(code);assert counts.get(code,0)==item['visible_pixels']
  if item['semantic_class']=='calyx':
   entry=mapping[item['instance_id']];assert entry['class_id'] in (0,1,2)
   if item['visible_pixels']:
    plant=entry['plant_id'];visible[plant]=visible.get(plant,0)+1;pixels[plant]=pixels.get(plant,0)+item['visible_pixels'];region=packed==code;overlay[region]=(overlay[region]*.5+colors[entry['class_id']]*.5).astype(np.uint8)
  elif key!='0':assert item['visible_pixels']==0
 assert set(counts)<=known
 Image.fromarray(overlay).save(o/f'view_{i:03d}_masks.jpg');records.append(dict(view=i,visible_instances_by_plant=visible,visible_pixels_by_plant=pixels,mask_palette_passed=True))
 sheet=Image.new('RGB',(1280,1500),'white');sheet.paste(Image.fromarray(rgb),(0,30));sheet.paste(Image.fromarray(overlay),(0,780));draw=ImageDraw.Draw(sheet);draw.text((12,3),'V193 — entorno de cultivo, plantas intactas',font=font,fill='black');draw.text((12,751),'Máscaras originales: pintona naranja | madura cian | sobremadura magenta',font=font,fill='black');sheet.save(o/f'view_{i:03d}_rgb_masks.jpg')
old=Image.open(r/'field_tracking_v187/evaluator_private/view_003/rgb.png').convert('RGB');new=Image.open(p/'view_000/rgb.png').convert('RGB');sheet=Image.new('RGB',(1280,1500),'white');sheet.paste(old,(0,30));sheet.paste(new,(0,780));draw=ImageDraw.Draw(sheet);draw.text((12,3),'Antes: V187 — mismo encuadre',font=font,fill='black');draw.text((12,751),'Después: V193 — vecinos, suelo y cielo; misma planta y cámara',font=font,fill='black');sheet.save(o/'antes_despues.jpg')
(o/'verification.json').write_text(json.dumps(dict(views=records,source_hashes_unchanged=True,all_neighbor_calyces_annotated=True,training_eligible=False,limitation='Environment-only demonstration; procedural ground cover, not validated photorealism. Same validation plants reused, no training promotion.'),indent=2));print(json.dumps(records))
