"""Evaluate frozen RGB-only predictions against held-separate Gazebo instance masks."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time
import cv2
import numpy as np
import torch
from ultralytics import YOLO
from ultralytics.utils.metrics import ap_per_class
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import VERSION,CLASSES,write,sha,check_deadline
from uchuva_gazebo.segmentation_evaluation import decode_panoptic_rgb,mask_matches,mask_confusion


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--flight',type=Path,required=True);p.add_argument('--model',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--size',type=int,default=960)
    p.add_argument('--confidence',type=float,required=True)
    p.add_argument('--scope',choices=['development','final','technical'],default='development')
    p.add_argument('--inference-mode',choices=['full','roi','tiles'],default='full')
    p.add_argument('--tile-size',type=int,default=640)
    p.add_argument('--tile-overlap',type=float,default=.2)
    a=p.parse_args();check_deadline(a.root);a.output.mkdir(parents=True,exist_ok=False)
    pairs=json.loads((a.flight/'paired/pairs.json').read_text())
    if pairs['error'] or not pairs['pairs']:raise ValueError('No valid synchronized capture')
    reference_path=a.flight/'reference_lock.json'
    reference_verified=False
    if reference_path.exists():
        lock=json.loads(reference_path.read_text())
        if sha(a.flight/'paired/pairs.json')!=lock['pairs_sha256']:raise ValueError('Fixed reference manifest changed')
        for path,digest in lock['sha256'].items():
            if sha(a.flight/'paired'/path)!=digest:raise ValueError('Fixed reference pixels changed')
        reference_verified=True
    validation=json.loads((a.flight/'segmentation_validation.json').read_text())
    if not validation['passed']:raise ValueError('Flight validation gate failed')
    if a.scope=='final' and not (a.root/'winner_selection.json').exists():
        raise ValueError('Final evaluation requires frozen development winner')
    (a.output/'predictions').mkdir()
    telemetry=json.loads((a.flight/'telemetry.json').read_text())['samples']
    stamps=np.array([sample['t'] for sample in telemetry])
    mission=json.loads((a.flight.parent/'mission.json').read_text())
    route=np.array([sample['position'][:2] for sample in telemetry],float)
    planned=np.array([point['position'][:2] for point in mission['waypoints']],float)
    route_min=np.minimum(route.min(axis=0),planned.min(axis=0))
    route_span=np.maximum(np.maximum(route.max(axis=0),planned.max(axis=0))-route_min,.1)
    def route_pixels(points):
        normalized=(points-route_min)/route_span
        return np.column_stack((12+normalized[:,0]*196,108-normalized[:,1]*80)).astype(np.int32)
    planned_pixels=route_pixels(planned);executed_pixels=route_pixels(route)
    targets={point['phase']:point.get('target_plant_id') for point in mission['waypoints']}
    chosen={}
    for row in pairs['pairs']:
        bucket=round(row['stamp_ns']/1e9)
        if bucket not in chosen or abs(row['stamp_ns']-bucket*1e9)<abs(chosen[bucket]['stamp_ns']-bucket*1e9):chosen[bucket]=row
    model=YOLO(a.model);thresholds=np.arange(.5,1,.05)
    all_tp=[];all_collapsed=[];all_conf=[];all_cls=[];all_gt=[];frames=[];strata=Counter();latencies=[]
    confusion=np.zeros((4,4),int);native_codes=set();native_hits=set();role_counts=Counter();speeds=[]
    detector=cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100))
    video=None
    for index,row in enumerate(chosen.values()):
        check_deadline(a.root)
        image=cv2.imread(str(a.flight/'paired'/row['rgb']));h,w=image.shape[:2]
        # Predictor receives only the RGB; ground truth is loaded afterwards.
        torch.cuda.synchronize();start=time.perf_counter()
        if a.inference_mode=='full':
            result=model.predict(image,imgsz=a.size,conf=.001,device=0,retina_masks=True,max_det=300,verbose=False)[0]
        else:
            from uchuva_gazebo.roi_tiling import predict_roi
            result=predict_roi(model,image,a.size,a.inference_mode,a.tile_size,a.tile_overlap)
        torch.cuda.synchronize();latencies.append(time.perf_counter()-start);speeds.append(result.speed)
        truth=cv2.imread(str(a.flight/'paired'/row['mask']))[:,:,::-1].astype(np.uint32)
        codes=decode_panoptic_rgb(truth)
        if codes.shape!=(h,w):raise ValueError('RGB/mask shape mismatch')
        identities,pixels=np.unique(codes,return_counts=True)
        native_codes.update(int(v) for v in identities if v)
        gt=[]
        for identity,area in zip(identities,pixels):
            if not identity:continue
            binary=codes==identity;ys,xs=np.nonzero(binary);label=int(identity)//65536
            gt.append(dict(id=int(identity),cls=(label-1)%3,plant=(label-1)//3,area=int(area),
                bbox=[int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)]))
        masks=result.masks.data.cpu().numpy()>.5 if result.masks is not None else np.zeros((0,h,w),bool)
        boxes=result.boxes.xyxy.cpu().numpy();classes=result.boxes.cls.cpu().numpy().astype(int)
        confidence=result.boxes.conf.cpu().numpy();order=np.argsort(-confidence)
        masks,boxes,classes,confidence=masks[order],boxes[order],classes[order],confidence[order]
        np.savez_compressed(a.output/'predictions'/f"{row['stamp_ns']}.npz",
            image_shape=np.array([h,w]),packed_masks=np.packbits(masks,axis=-1),
            boxes=boxes,classes=classes,confidence=confidence)
        ious=np.zeros((len(masks),len(gt)))
        for i,(mask,box) in enumerate(zip(masks,boxes)):
            area=int(mask.sum())
            for j,reference in enumerate(gt):
                x1,y1,x2,y2=reference['bbox']
                if box[2]<x1 or box[0]>x2 or box[3]<y1 or box[1]>y2:continue
                intersection=np.count_nonzero(mask[y1:y2,x1:x2]&(codes[y1:y2,x1:x2]==reference['id']))
                ious[i,j]=intersection/max(1,area+reference['area']-intersection)
        gt_cls=np.array([r['cls'] for r in gt],int)
        tp,matched_at_50=mask_matches(ious,classes,gt_cls,thresholds)
        collapsed,_=mask_matches(ious,classes,gt_cls,thresholds,collapse=True)
        operating=confidence>=a.confidence
        confusion+=mask_confusion(ious[operating],classes[operating],gt_cls)
        hits={j for i,j in matched_at_50.items() if operating[i]}
        native_hits.update(gt[j]['id'] for j in hits)
        nearest=int(np.abs(stamps-row['stamp_ns']/1e9).argmin())
        phase=telemetry[nearest]['phase'];target_name=targets.get(phase)
        target_plant=int(target_name.split('_')[-1]) if target_name else None
        for j,reference in enumerate(gt):
            side=reference['area']**.5;band='<16' if side<16 else '16-31' if side<32 else '32-63' if side<64 else '>=64'
            strata[(reference['cls'],band,'gt')]+=1;strata[(reference['cls'],band,'tp')]+=j in hits
            role=('unassigned_transit' if target_plant is None else 'target' if reference['plant']==target_plant else 'background')
            role_counts[(role,'observations')]+=1;role_counts[(role,'matched')]+=j in hits
        corners,ids,_=detector.detectMarkers(image);markers=[] if ids is None else ids.ravel().tolist()
        frame=dict(stamp_ns=row['stamp_ns'],visible_instances=len(gt),predictions=int(operating.sum()),
            tp=len(hits),fp=int(operating.sum())-len(hits),fn=len(gt)-len(hits),aruco_ids=markers,
            gt_by_plant=dict(Counter(r['plant'] for r in gt)),target_plant=target_plant,phase=phase,
            native_instance_codes=[r['id'] for r in gt],matched_native_codes=[gt[j]['id'] for j in sorted(hits)])
        frame['inference_protocol']={'mode':a.inference_mode,'tile_size':a.tile_size,'overlap':a.tile_overlap,'roi':getattr(result,'roi_diagnostics',None)}
        frames.append(frame);all_tp.append(tp);all_collapsed.append(collapsed);all_conf.append(confidence);all_cls.append(classes);all_gt.append(gt_cls)
        overlay=image.copy()
        colors=np.array([[65,190,90],[20,180,240],[170,90,180]])
        for i in np.flatnonzero(operating):overlay[masks[i]]=(overlay[masks[i]]*.45+colors[classes[i]]*.55).astype(np.uint8)
        if ids is not None:cv2.aruco.drawDetectedMarkers(overlay,corners,ids)
        cv2.putText(overlay,f'{index} TP {len(hits)} FN {len(gt)-len(hits)} ArUco {markers}',(12,26),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),2)
        # Presentation only: evaluated RGB remains unchanged; telemetry never enters YOLO.
        route_panel=np.full((120,220,3),30,np.uint8)
        cv2.polylines(route_panel,[planned_pixels],False,(130,130,130),1)
        cv2.polylines(route_panel,[executed_pixels[:nearest+1]],False,(60,210,110),2)
        cv2.circle(route_panel,tuple(executed_pixels[nearest]),4,(40,80,255),-1)
        cv2.putText(route_panel,'Recorrido XY / odometria',(7,16),cv2.FONT_HERSHEY_SIMPLEX,.4,(235,235,235),1)
        overlay[h-130:h-10,w-230:w-10]=route_panel
        if video is None:video=cv2.VideoWriter(str(a.output/'segmentation.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),5,(w,h))
        video.write(overlay)
        if index%20==0:cv2.imwrite(str(a.output/f'example_{index:04d}.jpg'),overlay)
        print('EVAL',index,frame['tp'],frame['fn'],flush=True)
    if video:video.release()
    tp=np.concatenate(all_tp);conf=np.concatenate(all_conf);cls=np.concatenate(all_cls);target=np.concatenate(all_gt)
    metrics=ap_per_class(tp,conf,cls,target,plot=False,names=dict(enumerate(CLASSES)))
    collapsed_metrics=ap_per_class(np.concatenate(all_collapsed),conf,np.zeros_like(cls),np.zeros_like(target),plot=False,names={0:'capacho'})
    perclass=[{'class_id':int(c),'name':CLASSES[c],'mask_ap50':float(metrics[5][i,0]),'mask_ap50_95':float(metrics[5][i].mean())} for i,c in enumerate(metrics[6])]
    totals={k:sum(f[k] for f in frames) for k in ('tp','fp','fn','visible_instances','predictions')}
    write(a.output/'metrics.json',dict(script_version=VERSION,seed=20261002,parameter_preset='frozen_gazebo_mask_evaluation',
        model_sha256=sha(a.model),operating_confidence=a.confidence,frames=len(frames),totals=totals,
        mask_map50_95=float(metrics[5].mean()) if metrics[5].size else 0,per_class=perclass,
        class_collapsed_mask_map50_95=float(collapsed_metrics[5].mean()) if collapsed_metrics[5].size else 0,
        operating_precision=totals['tp']/max(1,totals['predictions']),operating_recall=totals['tp']/max(1,totals['visible_instances']),
        confusion_matrix=confusion.tolist(),confusion_axes='rows truth, columns prediction; final index unmatched/background',
        distinct_native_codes=len(native_codes),distinct_native_codes_detected=len(native_hits),
        physical_unique_count_status='native_render_instances_in_static_world; anatomical_ID_mapping_not_assumed',
        role_recall=[{'role':role,'observations':role_counts[(role,'observations')],
            'matched':role_counts[(role,'matched')],
            'recall':role_counts[(role,'matched')]/max(1,role_counts[(role,'observations')])}
            for role in ('target','background','unassigned_transit')],
        strata=[dict(class_id=c,size_equivalent_pixels=b,kind=k,count=v) for (c,b,k),v in strata.items()],
        marker_frame_fraction=sum(bool(f['aruco_ids']) for f in frames)/len(frames),
        median_pipeline_seconds=float(np.median(latencies[1:] or latencies)),
        median_model_inference_ms=float(np.median([s['inference'] for s in speeds[1:] or speeds])),
        observation_unit='per_image_including_repeated_instances',scope=f'synthetic_{a.scope}_not_real_transfer',
        capture_manifest_sha256=sha(a.flight/'paired/pairs.json'),
        fixed_reference_verified=reference_verified,
        presentation_video={'fps':5,'sample_frequency_hz':1,'speed_factor':5,'not_an_analysis_input':True,
                            'route_inset':'planned and executed XY; simulator odometry, evaluator presentation only'}))
    write(a.output/'frames.json',{'script_version':VERSION,'seed':20261002,'parameter_preset':'frozen_gazebo_mask_evaluation','frames':frames})


if __name__=='__main__':main()
