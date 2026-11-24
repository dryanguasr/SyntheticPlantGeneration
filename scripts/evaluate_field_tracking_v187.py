"""Private native-mask evaluation, after public-only V187 inference."""
import json,sys
from pathlib import Path
import numpy as np
from PIL import Image
from evaluate_field_pilot import match
r=Path('outputs/integral_diagnosis_20261014/field_tracking_v187');p=r/'evaluator_private';mapping=json.loads((p/'class_mapping_private.json').read_text());obs=json.loads((r/'predictions/observations.json').read_text());assert len(obs)==8
counts=dict(tp=0,fp=0,fn=0);last={};transitions=0;changes=0;details=[]
for i,frame in enumerate(obs):
 folder=p/f'view_{i:03d}';a=json.loads((folder/'annotations_private.json').read_text());rgb=np.array(Image.open(folder/'mask_calyx_crisp_v2.png').convert('RGB'));packed=rgb.astype(np.uint32);packed=packed[:,:,0]*65536+packed[:,:,1]*256+packed[:,:,2]
 native=np.zeros(rgb.shape[:2],np.uint16);labels=[]
 for k,item in a['items'].items():
  if item['semantic_class']!='calyx' or not item['visible_pixels']:continue
  color=a['palette'][k];mask=packed==(color[0]*65536+color[1]*256+color[2]);mid=len(labels)+1;native[mask]=mid
  labels.append(dict(mask_id=mid,pixels=item['visible_pixels'],instance_id=item['instance_id'],class_id=mapping[item['instance_id']]['class_id']))
 masks=np.load(r/'predictions'/(str(frame['stamp_ns'])+'.npz'))['masks'];cc,mm,missed=match(native,labels,masks,frame['detections'])
 for c in cc:
  for key in counts:counts[key]+=c[key]
 for m in mm:
  identity=labels[m['truth']]['instance_id'];track=frame['detections'][m['prediction']]['track_id']
  if identity in last and last[identity][0]==i-1:transitions+=1;changes+=last[identity][1]!=track
  last[identity]=(i,track)
 details.append(dict(stamp_ns=frame['stamp_ns'],classes=cc,matches=mm,visible_truth=len(labels)))
precision=counts['tp']/max(1,counts['tp']+counts['fp']);recall=counts['tp']/max(1,counts['tp']+counts['fn'])
result=dict(counts,precision=precision,recall=recall,f1=2*precision*recall/max(1e-12,precision+recall),consecutive_matched_truth_pairs=transitions,changed_ids_between_consecutive_matches=changes,identity_metric_limit='Only class-aware IoU>=0.5 matches in adjacent frames; not IDF1 and excludes missed detections.',frames=details,production_promotion=False,metric_localization_pending=True)
(p/'evaluation.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='frames'}))
