"""RGB-only vegetation ROI prototype and native-scale overlapping inference.

The first stage is an explicit colour/shape heuristic, not a learned bush model.
No simulator labels, markers, telemetry or evaluation masks enter this module.
"""
import time
import cv2
import numpy as np
import torch
from ultralytics.engine.results import Results


def bush_rois(image):
    h,w=image.shape[:2]
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    vegetation=cv2.inRange(hsv,np.array([20,35,18]),np.array([100,255,255]))
    vegetation=cv2.morphologyEx(vegetation,cv2.MORPH_CLOSE,np.ones((31,31),np.uint8))
    count,labels,stats,_=cv2.connectedComponentsWithStats(vegetation)
    boxes=[]
    for x,y,bw,bh,area in stats[1:]:
        if area<h*w*.004 or bh<h*.15:continue
        pad=max(16,round(.08*max(bw,bh)))
        boxes.append((max(0,x-pad),max(0,y-pad),min(w,x+bw+pad),min(h,y+bh+pad)))
    return [tuple(map(int,box)) for box in boxes]


def tile_boxes(roi,size=640,overlap=.2):
    if size<32 or not 0<=overlap<1:raise ValueError('Invalid tile configuration')
    x1,y1,x2,y2=map(int,roi);stride=max(1,round(size*(1-overlap)))
    def starts(a,b):
        if b-a<=size:return [a]
        values=list(range(a,b-size+1,stride))
        if values[-1]!=b-size:values.append(b-size)
        return values
    return [(x,y,min(x+size,x2),min(y+size,y2)) for y in starts(y1,y2) for x in starts(x1,x2)]


def predict_roi(model,image,size=960,mode='tiles',tile_size=640,overlap=.2):
    start=time.perf_counter();h,w=image.shape[:2]
    rois=[(0,0,w,h)] if mode=='all_tiles' else bush_rois(image)
    crops=sorted(set(box for roi in rois for box in (tile_boxes(roi,tile_size,overlap) if mode in ('tiles','all_tiles','safe_tiles') else [roi])))
    if mode=='safe_tiles':
        # The colour heuristic cannot certify absence of dry or occluded calyces.
        covered=np.zeros((h,w),bool)
        for x1,y1,x2,y2 in crops:covered[y1:y2,x1:x2]=True
        crops+=[box for box in tile_boxes((0,0,w,h),tile_size,overlap)
                if not covered[box[1]:box[3],box[0]:box[2]].all()]
        crops=sorted(set(crops))
    candidates=[];inference_ms=0.
    for x1,y1,x2,y2 in crops:
        crop=image[y1:y2,x1:x2]
        if mode in ('tiles','all_tiles','safe_tiles'):
            # Pad instead of resizing: preserve native sampling at model input.
            canvas=np.full((tile_size,tile_size,3),114,np.uint8)
            canvas[:y2-y1,:x2-x1]=crop;network_size=tile_size
        else:canvas=crop;network_size=size
        result=model.predict(canvas,imgsz=network_size,conf=.001,device=0,retina_masks=True,max_det=300,verbose=False)[0]
        inference_ms+=result.speed['inference']
        if result.masks is None:continue
        for box,mask in zip(result.boxes.data.cpu().numpy(),result.masks.data.cpu().numpy()):
            local=mask[:y2-y1,:x2-x1]>.5
            if not local.any():continue
            binary=np.zeros((h,w),bool);binary[y1:y2,x1:x2]=local
            ys,xs=np.nonzero(binary)
            candidates.append((float(box[4]),int(box[5]),binary,[xs.min(),ys.min(),xs.max()+1,ys.max()+1]))
    # Class-aware mask NMS avoids deleting adjacent capachos by box overlap alone.
    kept=[]
    for candidate in sorted(candidates,key=lambda r:-r[0]):
        score,cls,mask,box=candidate;duplicate=False
        for _,other_cls,other,other_box in kept:
            if cls!=other_cls or box[2]<=other_box[0] or other_box[2]<=box[0] or box[3]<=other_box[1] or other_box[3]<=box[1]:continue
            intersection=np.count_nonzero(mask & other)
            if intersection/max(1,np.count_nonzero(mask | other))>.5:duplicate=True;break
        if not duplicate:kept.append(candidate)
        if len(kept)>=300:break
    boxes=np.array([[*b,s,c] for s,c,m,b in kept],dtype=np.float32).reshape(-1,6)
    masks=np.stack([m for s,c,m,b in kept]).astype(np.float32) if kept else np.zeros((0,h,w),np.float32)
    result=Results(orig_img=image,path='',names=model.names,boxes=torch.from_numpy(boxes),masks=torch.from_numpy(masks))
    result.speed={'inference':inference_ms,'preprocess':0.,'postprocess':0.}
    result.roi_diagnostics=dict(method='RGB vegetation heuristic; not learned bush detector',rois=rois,tiles=len(crops),mode=mode,tile_size=tile_size,overlap=overlap,total_seconds=time.perf_counter()-start)
    return result
