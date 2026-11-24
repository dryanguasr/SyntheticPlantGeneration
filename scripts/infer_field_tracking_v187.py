"""V187 public-input inference; no evaluator masks or camera poses are read."""
import json,sys,hashlib
from pathlib import Path
import cv2,numpy as np,torch
from ultralytics import YOLO
ROOT=Path.cwd();sys.path.insert(0,str(ROOT/'src'))
from field_roi_patch_pilot import vegetation_roi,tile_boxes,deduplicate
from uchuva_gazebo.mask_tracking import MaskTracker
r=ROOT/'outputs/integral_diagnosis_20261014';public=r/'field_tracking_v187/public';out=r/'field_tracking_v187/predictions';out.mkdir(exist_ok=True)
weights=r/'field_memory_recovery_v186/training/weights/last.pt';model=YOLO(str(weights));tracker=MaskTracker();rows=[]
frames=json.loads((public/'frames.json').read_text());video=cv2.VideoWriter(str(out/'tracking_2fps.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),2,(1280,720))
for f in frames:
 bgr=cv2.imread(str(public/'rgb'/f['filename']));rgb=bgr[:,:,::-1].copy();h,w=rgb.shape[:2];roi,method=vegetation_roi(rgb);tiles=tile_boxes(roi,w,h);candidates=[]
 for ti,(x1,y1,x2,y2) in enumerate(tiles):
  result=model.predict(rgb[y1:y2,x1:x2,::-1].copy(),imgsz=960,rect=False,conf=.25,retina_masks=True,max_det=300,device=0,verbose=False)[0]
  if result.masks is not None:
   for mask,cl,score in zip(result.masks.data.cpu().numpy(),result.boxes.cls.cpu().tolist(),result.boxes.conf.cpu().tolist()):
    full=np.zeros((h,w),bool);full[y1:y2,x1:x2]=mask.astype(bool)
    if full.any():candidates.append((full,dict(class_id=int(cl),confidence=float(score),tile=ti)))
  del result;torch.cuda.empty_cache()
 kept=deduplicate(candidates);masks=[m for m,_ in kept];detections=[]
 for mask,label in kept:
  yy,xx=np.nonzero(mask);box=[int(xx.min()),int(yy.min()),int(xx.max())+1,int(yy.max())+1]
  detections.append(dict(label,box_xyxy_px=box,center_px=[float(xx.mean()),float(yy.mean())]))
 tracker.update(bgr,detections,f['stamp_ns'],masks)
 canvas=bgr.copy()
 for mask,d in zip(masks,detections):
  ident=int(d['track_id'].split('_')[-1]);color=np.array([(ident*67+70)%230,(ident*113+90)%230,(ident*41+140)%230])
  canvas[mask]=(canvas[mask]*.5+color*.5).astype(np.uint8);x,y=d['box_xyxy_px'][:2]
  cv2.putText(canvas,str(ident),(x,y),cv2.FONT_HERSHEY_SIMPLEX,.35,(255,255,255),1,cv2.LINE_AA)
 cv2.putText(canvas,'V186 ROI | predicted track IDs | no ground truth',(15,25),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),1)
 stem=Path(f['filename']).stem;cv2.imwrite(str(out/(stem+'.jpg')),canvas);video.write(canvas)
 np.savez_compressed(out/(stem+'.npz'),masks=np.asarray(masks,dtype=bool).reshape(-1,h,w))
 rows.append(dict(f,roi=roi,tiles=tiles,detections=detections));(out/'observations.json').write_text(json.dumps(rows,indent=2));print(stem,len(detections),flush=True)
video.release()
(out/'summary.json').write_text(json.dumps(dict(frames=len(rows),detections=sum(len(x['detections']) for x in rows),track_ids=tracker.next_id,model_sha256=hashlib.sha256(weights.read_bytes()).hexdigest(),public_frames_sha256=hashlib.sha256((public/'frames.json').read_bytes()).hexdigest(),identity_accuracy_evaluated=False,metric_localization=False,confidence=.25,geometry_changed=False),indent=2))
