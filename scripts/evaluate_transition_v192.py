"""V191 bounded detector diagnosis on V187 validation only. No plant/training changes."""
import json,hashlib
from pathlib import Path
import cv2,numpy as np,torch
from PIL import Image,ImageDraw,ImageFont
from ultralytics import YOLO
from field_roi_patch_pilot import vegetation_roi,tile_boxes,deduplicate
from evaluate_field_pilot import match,metrics
r=Path('outputs/integral_diagnosis_20261014');p=r/'field_tracking_v187';out=r/'transition_training_v192/evaluation';out.mkdir(exist_ok=True)
variants={'baseline':(384,256,.25),'fine_tuned':(384,256,.25)}
(out/'protocol.json').write_text(json.dumps(dict(variants=variants,split='V187 validation eight consecutive frames; correlated views, exploratory only',model='V192 vs frozen V186',selection_test=False,plants_changed=False,training=True,mask_iou=.5,scope='V192 two-epoch hard-example training vs V186. Same inference, no threshold tuning.'),indent=2))
frames=json.loads((p/'predictions/observations.json').read_text());mapping=json.loads((p/'evaluator_private/class_mapping_private.json').read_text());model=YOLO(str(r/'transition_training_v192/training/weights/last.pt'));totals={};examples=[];baseline_items=[]
prototype_shapes=[]
def capture_proto(module,args,result):
 value=result[0] if isinstance(result,tuple) else result
 shape=list(value.shape)
 if shape not in prototype_shapes:prototype_shapes.append(shape)
model.model.model[-1].proto.register_forward_hook(capture_proto)
for variant,(size,stride,conf) in variants.items():
 cm=np.zeros((4,4),int);counts=dict(tp=0,fp=0,fn=0);records=[]
 for i,f in enumerate(frames):
  rgb=np.array(Image.open(p/'public/rgb'/f['filename']).convert('RGB'));h,w=rgb.shape[:2]
  if variant=='baseline':masks=np.load(p/'predictions'/(str(f['stamp_ns'])+'.npz'))['masks'];labels=f['detections']
  else:
   roi,_=vegetation_roi(rgb);candidates=[]
   for ti,(x1,y1,x2,y2) in enumerate(tile_boxes(roi,w,h,size=size,stride=stride)):
    result=model.predict(rgb[y1:y2,x1:x2,::-1].copy(),imgsz=960,rect=False,conf=conf,retina_masks=True,max_det=300,device=0,verbose=False)[0]
    if result.masks is not None:
     for m,c,s in zip(result.masks.data.cpu().numpy(),result.boxes.cls.cpu().tolist(),result.boxes.conf.cpu().tolist()):
      full=np.zeros((h,w),bool);full[y1:y2,x1:x2]=m.astype(bool)
      if full.any():candidates.append((full,dict(class_id=int(c),confidence=float(s),tile=ti)))
    del result;torch.cuda.empty_cache()
   kept=deduplicate(candidates);masks=np.asarray([m for m,l in kept],dtype=bool).reshape(-1,h,w);labels=[l for m,l in kept]
   np.savez_compressed(out/f'{variant}_{i}.npz',masks=masks);(out/f'{variant}_{i}.json').write_text(json.dumps(labels))
  a=json.loads((p/f'evaluator_private/view_{i:03d}/annotations_private.json').read_text());maskrgb=np.array(Image.open(p/f'evaluator_private/view_{i:03d}/mask_calyx_crisp_v2.png').convert('RGB')).astype(np.uint32);packed=maskrgb[:,:,0]*65536+maskrgb[:,:,1]*256+maskrgb[:,:,2];native=np.zeros((h,w),np.uint16);truth=[]
  for key,item in a['items'].items():
   if item['semantic_class']!='calyx' or not item['visible_pixels']:continue
   col=a['palette'][key];mid=len(truth)+1;native[packed==col[0]*65536+col[1]*256+col[2]]=mid
   truth.append(dict(mask_id=mid,pixels=item['visible_pixels'],class_id=mapping[item['instance_id']]['class_id'],instance_id=item['instance_id'],bbox=item['bbox_xywh']))
  cc,_,_=match(native,truth,masks,labels)
  for c in cc:
   for k in counts:counts[k]+=c[k]
  remaining=set(range(len(truth)));matched={};best=np.zeros(len(truth))
  for j in sorted(range(len(labels)),key=lambda j:-labels[j]['confidence']):
   hist=np.bincount(native[masks[j]].astype(np.int64),minlength=len(truth)+1);area=masks[j].sum();ious=np.array([hist[t['mask_id']]/max(1,area+t['pixels']-hist[t['mask_id']]) for t in truth]);best=np.maximum(best,ious)
   pairs=[(ious[k],k) for k in remaining]
   if pairs and max(pairs)[0]>=.5:
    _,k=max(pairs);remaining.remove(k);matched[k]=j;cm[truth[k]['class_id'],labels[j]['class_id']]+=1
   else:cm[3,labels[j]['class_id']]+=1
  for k in remaining:cm[truth[k]['class_id'],3]+=1
  items=[]
  for k,t in enumerate(truth):
   pred=labels[matched[k]]['class_id'] if k in matched else None
   row=dict(t,predicted_class=pred,best_iou=float(best[k]),frame=i);items.append(row)
   if variant=='baseline':baseline_items.append(row)
  records.append(items)
  print(variant,i,len(labels),flush=True)
 totals[variant]=dict(metrics(counts),confusion=cm.tolist(),items=records)
(out/'results.json').write_text(json.dumps(totals,indent=2))
# Diagnostic breakdown uses visible raster area, never mask-fill as an occlusion rate.
bins={}
for low,high in [(1,25),(25,100),(100,400),(400,10**9)]:
 rows=[v for v in baseline_items if low<=v['pixels']<high];missing=[v for v in rows if v['predicted_class'] is None]
 bins[str((low,high))]=dict(total=len(rows),omitted=len(missing),omission_rate=len(missing)/max(1,len(rows)),median_best_iou_omitted=float(np.median([v['best_iou'] for v in missing])) if missing else None)
(out/'diagnosis.json').write_text(json.dumps(dict(visible_area_bins=bins,omitted_with_overlap_025_050=sum(v['predicted_class'] is None and .25<=v['best_iou']<.5 for v in baseline_items),omitted_with_iou_below_010=sum(v['predicted_class'] is None and v['best_iou']<.1 for v in baseline_items),occlusion_fraction_not_available=True),indent=2))
# Representative cases: area quantiles per failure type, unique identities, deterministic.
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',18)
categories=[('Omitida pequeÃ±a',lambda v:v['predicted_class'] is None and v['pixels']<100),('Omitida mediana/grande',lambda v:v['predicted_class'] is None and v['pixels']>=100),('Pintona â†’ madura',lambda v:v['class_id']==0 and v['predicted_class']==1)]
sheet=Image.new('RGB',(960,900),'#f5f5f5');draw=ImageDraw.Draw(sheet);selected=[]
for row,(name,condition) in enumerate(categories):
 unique={}
 for v in baseline_items:
  if condition(v):unique.setdefault(v['instance_id'],v)
 pool=sorted(unique.values(),key=lambda v:v['pixels'])
 for col,q in enumerate([.2,.5,.8]):
  if not pool:continue
  v=pool[round(q*(len(pool)-1))];selected.append(v);im=Image.open(p/'public/rgb'/frames[v['frame']]['filename']).convert('RGB');x,y,bw,bh=v['bbox'];cx=x+bw/2;cy=y+bh/2;side=max(100,bw+40,bh+40);left=max(0,min(im.width-side,cx-side/2));top=max(0,min(im.height-side,cy-side/2));crop=im.crop((int(left),int(top),int(left+side),int(top+side))).resize((300,240));cd=ImageDraw.Draw(crop);cd.rectangle(((x-left)*300/side,(y-top)*240/side,(x+bw-left)*300/side,(y+bh-top)*240/side),outline='#ff3535',width=2);sheet.paste(crop,(col*320,row*300+50));draw.text((col*320+5,row*300+3),name,font=font,fill='black');draw.text((col*320+5,row*300+25),f"Vista {v['frame']+1} | {v['pixels']} px | IoU {v['best_iou']:.2f}",font=font,fill='black')
sheet.save(out/'ejemplos_representativos.jpg');(out/'examples.json').write_text(json.dumps(selected,indent=2))
print(json.dumps({k:{a:b for a,b in v.items() if a!='items'} for k,v in totals.items()}))

(out/'resolution_audit.json').write_text(json.dumps(dict(input_size=960,native_patch=384,scale=2.5,prototype_shapes=prototype_shapes,detection_strides=model.model.model[-1].stride.cpu().tolist(),training_mask_ratio=2,criterion='>=100 native visible pixels and native bbox min side>=8; heuristic not hard theoretical minimum'),indent=2))
