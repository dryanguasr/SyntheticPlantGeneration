"""Recoverable RGB-only native-tile inference for every original exposure.

Keeps low-confidence proposals and cross-tile suppression evidence for the
evaluator. Network-internal proposal/NMS losses remain explicitly unobserved.
"""
import argparse
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import write,sha,check_deadline


def native_tiles(width,height,size=960,overlap=.2):
    """Fixed stride with padding at the border, not enlarged border overlap."""
    if size<32 or not 0<=overlap<1 or width<=0 or height<=0:raise ValueError('Invalid native tiling')
    stride=max(1,round(size*(1-overlap)))
    def starts(length):
        result=[0]
        while result[-1]+size<length:result.append(result[-1]+stride)
        return result
    return [(x,y,min(x+size,width),min(y+size,height)) for y in starts(height) for x in starts(width)]


def suppress(proposals,masks,threshold=.5):
    kept=[]
    for index in sorted(range(len(proposals)),key=lambda i:-proposals[i]['confidence']):
        item=proposals[index];duplicate=None
        for other in kept:
            a,b=item['box_xyxy_px'],proposals[other]['box_xyxy_px']
            if a[2]<=b[0] or b[2]<=a[0] or a[3]<=b[1] or b[3]<=a[1]:continue
            intersection=np.count_nonzero(masks[index]&masks[other])
            union=np.count_nonzero(masks[index]|masks[other])
            cutoff=threshold if item['class_id']==proposals[other]['class_id'] else .8
            if intersection/max(1,union)>cutoff:
                duplicate=other;break
        item['cross_tile_suppressed_by']=duplicate
        if duplicate is None:kept.append(index)
    return kept


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--public',type=Path,required=True);p.add_argument('--model',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--confidence',type=float,default=.14614614614614616)
    p.add_argument('--layout',choices=('tiles','full'),default='tiles')
    p.add_argument('--input-size',type=int,choices=(640,960,1280),default=960)
    a=p.parse_args()
    from ultralytics import YOLO
    frames=json.loads((a.public/'frames.json').read_text())
    if any(set(f)!={'stamp_ns','filename'} for f in frames):raise ValueError('Non-public frame fields')
    config=dict(version='continuous-predictions/1.0',model_sha256=sha(a.model),
        frames_sha256=sha(a.public/'frames.json'),confidence=a.confidence,tile_size=960,overlap=.2,
        proposal_floor=.001,coverage='full RGB, no vegetation filter',
        edge_policy='fixed native stride, pad partial final tile; no shift enlarging overlap',
        cross_tile_nms=dict(same_class_iou=.5,different_class_iou=.8,keep='higher confidence; all discarded evidence retained'),
        internal_nms_evidence='Unavailable: absence below proposal floor or network NMS cannot be distinguished',
        inputs=['RGB','timestamps'],ground_truth_inputs=False)
    if a.layout!='tiles' or a.input_size!=960:
        config.update(version='continuous-predictions/1.1',layout=a.layout,input_size=a.input_size,
            tile_size=a.input_size if a.layout=='tiles' else None,
            overlap=.2 if a.layout=='tiles' else None,
            edge_policy='fixed native stride and padding' if a.layout=='tiles' else 'full image; model letterbox')
    a.output.mkdir(parents=True,exist_ok=True)
    provenance=a.output/'configuration.json'
    if provenance.exists() and json.loads(provenance.read_text())!=config:raise ValueError('Existing cache protocol differs')
    write(provenance,config);model=YOLO(a.model);begin=time.perf_counter();completed=0
    for f in frames:
        check_deadline(a.root)
        stamp=f['stamp_ns'];target=a.output/str(stamp);record=target.with_suffix('.json');masks_path=target.with_suffix('.npz')
        if record.exists():
            old=json.loads(record.read_text())
            if masks_path.exists() and old['masks_sha256']==sha(masks_path):completed+=1;continue
            raise ValueError(f'Corrupt completed cache frame {stamp}')
        path=Path(f['filename'])
        if path.is_absolute() or '..' in path.parts:raise ValueError('Non-public RGB path')
        image=cv2.imread(str(a.public/'rgb'/path));started=time.perf_counter()
        if image is None:raise ValueError(f'Unreadable RGB {stamp}')
        h,w=image.shape[:2];proposals=[];masks=[]
        tiles=native_tiles(w,h,a.input_size,.2) if a.layout=='tiles' else [(0,0,w,h)]
        for tile_id,(x,y,xx,yy) in enumerate(tiles):
            if a.layout=='tiles':
                canvas=np.full((a.input_size,a.input_size,3),114,np.uint8)
                canvas[:yy-y,:xx-x]=image[y:yy,x:xx]
            else:canvas=image
            prediction=model.predict(canvas,imgsz=a.input_size,conf=.001,device=0,retina_masks=True,max_det=300,verbose=False)[0]
            if prediction.masks is None:continue
            for local_id,(box,mask) in enumerate(zip(prediction.boxes.data.cpu().numpy(),prediction.masks.data.cpu().numpy())):
                binary=np.zeros((h,w),bool);binary[y:yy,x:xx]=mask[:yy-y,:xx-x]>.5
                ys,xs=np.nonzero(binary)
                if not len(xs):continue
                proposals.append(dict(observation_id=f'{stamp}:{len(proposals)}',tile_id=tile_id,
                    tile_detection_id=local_id,confidence=float(box[4]),class_id=int(box[5]),
                    box_xyxy_px=[int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)],
                    center_px=[float(xs.mean()),float(ys.mean())]))
                masks.append(binary)
        kept=suppress(proposals,masks)
        for index,item in enumerate(proposals):
            item['mask_reference']=dict(archive=f'{stamp}.npz',index=index,encoding='numpy_packbits_row_major')
            item['accepted']=index in kept and item['confidence']>=a.confidence
            item['rejection_reason']='cross_tile_mask_nms' if index not in kept else ('below_operating_confidence' if item['confidence']<a.confidence else None)
        packed=np.packbits(np.stack(masks).reshape(len(masks),h*w),axis=1) if masks else np.zeros((0,(h*w+7)//8),np.uint8)
        temporary=target.with_suffix('.partial.npz');np.savez_compressed(temporary,packed_masks=packed,shape=np.array([h,w]))
        temporary.replace(masks_path)
        write(record,dict(stamp_ns=stamp,rgb_sha256=sha(a.public/'rgb'/path),tiles=tiles,proposals=proposals,
            masks_sha256=sha(masks_path),seconds=time.perf_counter()-started))
        completed+=1
        if completed%30==0:print('FRAME_CACHE',completed,len(frames),flush=True)
    write(a.output/'completion.json',dict(completed=True,frames=completed,configuration_sha256=sha(provenance),
        invocation_seconds=time.perf_counter()-begin,all_frame_seconds=sum(json.loads((a.output/f"{f['stamp_ns']}.json").read_text())['seconds'] for f in frames)))


if __name__=='__main__':main()
