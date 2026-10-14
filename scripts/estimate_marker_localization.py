"""Estimate capacho locations using only a public RGB/calibration bundle."""
import argparse,collections,json,sys,time
from pathlib import Path
import cv2
import numpy as np
from ultralytics import YOLO
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import write,sha,check_deadline
from uchuva_gazebo.multiview import Tracker,marker_pose,triangulate
from uchuva_gazebo.localization import PersistentTracker,canonical_pose,robust_triangulate,reconcile
from uchuva_gazebo.roi_tiling import predict_roi


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--public',type=Path,required=True)
    p.add_argument('--model',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--variant',choices=['baseline','persistent'],required=True);p.add_argument('--tile-size',type=int,default=640)
    p.add_argument('--mode',choices=['all_tiles','tiles','safe_tiles'],default='all_tiles');p.add_argument('--confidence',type=float,default=.14614614614614616)
    p.add_argument('--detections-cache',type=Path)
    p.add_argument('--refine-corners',action='store_true')
    p.add_argument('--adaptive-sampling',action='store_true')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    calibration=json.loads((a.public/'calibration.json').read_text());frames=json.loads((a.public/'frames.json').read_text())
    if any(set(f)!={'stamp_ns','filename'} for f in frames):raise ValueError('Only public timestamps and filenames permitted')
    K=calibration['K'];rig={v['id']:v for v in calibration['rig']}
    cached=None
    if a.detections_cache:
        provenance=json.loads((a.detections_cache/'provenance.json').read_text())
        if provenance['model_sha256']!=sha(a.model) or provenance['frames_sha256']!=sha(a.public/'frames.json') or provenance['mode']!=a.mode or provenance['tile_size']!=a.tile_size or provenance['confidence']!=a.confidence:
            raise ValueError('Detection cache protocol mismatch')
        cached={r['stamp_ns']:r for r in map(json.loads,(a.detections_cache/'observations.jsonl').read_text().splitlines())}
    model=None if cached is not None else YOLO(a.model)
    tracker=Tracker() if a.variant=='baseline' else PersistentTracker()
    detector_parameters=cv2.aruco.DetectorParameters()
    if a.refine_corners:detector_parameters.cornerRefinementMethod=cv2.aruco.CORNER_REFINE_SUBPIX
    detector=cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100),detector_parameters)
    tracks=collections.defaultdict(list);descriptors=collections.defaultdict(list);classes=collections.defaultdict(list)
    pose_history={};pose_rejections=collections.Counter();latencies=[];last_detection=-1e9;begin=time.perf_counter();count=0
    with (a.output/'observations.jsonl').open('w',encoding='utf-8') as stream:
        for frame in frames:
            check_deadline(a.root);stamp=frame['stamp_ns'];now=stamp/1e9
            filename=Path(frame['filename'])
            if filename.is_absolute() or '..' in filename.parts:raise ValueError('Non-public RGB path')
            image=cv2.imread(str(a.public/'rgb'/filename))
            if image is None:raise ValueError('Unreadable RGB')
            period=.999
            if a.adaptive_sampling:
                if cached is not None:raise ValueError('Adaptive sampling needs new RGB detections')
                active_lengths=[len(classes[tid]) for tid in getattr(tracker,'tracks',{})]
                if not active_lengths or np.median(active_lengths)<5:period=.199
            detect=now-last_detection>=period
            if not detect:
                if a.variant=='persistent':tracker.update(image,None,stamp)
                continue
            started=time.perf_counter();last_detection=now
            result=predict_roi(model,image,mode=a.mode,tile_size=a.tile_size) if cached is None else None
            # ROI absence is uncertainty, not proof of an empty plant scene.
            if cached is None and a.mode=='tiles' and not result.roi_diagnostics['rois']:
                result=predict_roi(model,image,mode='all_tiles',tile_size=a.tile_size)
            detections=[] if cached is None else [dict(d) for d in cached[stamp]['detections']]
            for index,box in enumerate(result.boxes.data.numpy() if result is not None else []):
                if box[4]<a.confidence:continue
                mask=result.masks.data[index].numpy()>.5;ys,xs=np.nonzero(mask)
                if not len(xs):continue
                detections.append(dict(box_xyxy_px=box[:4].tolist(),center_px=[float(np.mean(xs)),float(np.mean(ys))],confidence=float(box[4]),class_id=int(box[5]),observation_id=f'{stamp}:{len(detections)}'))
            tracker.update(image,detections,stamp)
            corners,ids,_=detector.detectMarkers(image);poses={}
            if ids is not None:
                for corner,identifier in zip(corners,ids.ravel()):
                    identifier=int(identifier)
                    if identifier not in rig or list(ids.ravel()).count(identifier)!=1:continue
                    pose=marker_pose(corner,K,side=calibration['marker_side_m'])
                    if a.variant=='persistent' and pose.get('reason')=='ambiguous_marker_pose' and identifier in pose_history:
                        old=pose_history[identifier]
                        if now-old['time']<=2:
                            choices=sorted(pose['candidates'],key=lambda v:np.linalg.norm(np.asarray(v['R'])-old['R'])+np.linalg.norm(np.asarray(v['t'])-old['t']))
                            if np.linalg.norm(np.asarray(choices[0]['R'])-old['R'])<.5:
                                pose=dict(status='estimated',**choices[0],disambiguation='bounded temporal continuity')
                    if pose['status']!='estimated':pose_rejections[pose['reason']]+=1;continue
                    pose_history[identifier]=dict(time=now,R=pose['R'],t=pose['t'])
                    poses[identifier]=canonical_pose(pose,rig[identifier])
            for detection in detections:
                tid=detection['track_id'];classes[tid].append(detection['class_id'])
                if 'appearance' not in detection:
                    from uchuva_gazebo.localization import appearance
                    detection['appearance']=appearance(image,detection['box_xyxy_px']).tolist()
                descriptors[tid].append(detection['appearance'])
                for identifier,pose in poses.items():
                    canonical=rig[identifier]['canonical_id']
                    tracks[(tid,canonical)].append(dict(**pose,marker_id=canonical,point_px=detection['center_px'],stamp_ns=stamp,observation_id=detection['observation_id']))
            latency=time.perf_counter()-started;latencies.append(latency)
            stream.write(json.dumps(dict(stamp_ns=stamp,detections=detections,marker_poses=poses,seconds=latency))+'\n');stream.flush()
            count+=1
            if count%10==0:print('RGB_LOCALIZATION',a.variant,count,len(tracks),flush=True)
    by_track=collections.defaultdict(list);rejected=[]
    for (tid,marker),observations in tracks.items():
        check_deadline(a.root)
        fit=(triangulate if a.variant=='baseline' else robust_triangulate)(observations,K)
        if fit['status']!='estimated':rejected.append(dict(track_id=tid,marker_id=marker,**fit));continue
        x,y,z=fit['position_marker_m']
        # Public engineering envelope; not plant-specific ground truth.
        if abs(x)>1.2 or not -.25<=y<=3 or not -1.5<=z<=.7:
            rejected.append(dict(track_id=tid,marker_id=marker,status='unavailable',reason='outside_public_plant_envelope'));continue
        desc=np.mean(descriptors[tid],axis=0);desc=desc/max(np.linalg.norm(desc),1e-9)
        by_track[tid].append(dict(**fit,marker_id=marker,track_ids=[tid],class_id=collections.Counter(classes[tid]).most_common(1)[0][0],appearance=desc.tolist(),stamps=[o['stamp_ns'] for o in observations],observation_ids=[o['observation_id'] for o in observations],association_cost=float(abs(x)+.3*abs(z+.18))))
    candidates=[]
    for tid,values in by_track.items():
        values.sort(key=lambda v:v['association_cost'])
        if len(values)>1 and values[1]['association_cost']-values[0]['association_cost']<.15:
            rejected.append(dict(track_id=tid,status='provisional',reason='ambiguous_plant_marker'));continue
        candidates.append(values[0])
    maps=reconcile(candidates) if a.variant=='persistent' else [dict(map_id=f'calyx_{i:06d}',**v) for i,v in enumerate(candidates)]
    for item in maps:item['state']='provisional' if item.get('reconciliation_status')=='ambiguous' else 'confirmed'
    write(a.output/'map.json',dict(version='calyx-marker-map/1.0',units='metres',axes='canonical marker: x right, y up, z outward',center_semantics='triangulated visible-mask centroid proxy for capacho centre; bias evaluated separately',objects=maps,rejected=rejected))
    write(a.output/'association_rejections.json',tracker.rejections)
    write(a.output/'provenance.json',dict(version='marker-localization-estimator/1.0',variant=a.variant,model_sha256=sha(a.model),calibration_sha256=sha(a.public/'calibration.json'),frames_sha256=sha(a.public/'frames.json'),inputs=['RGB','timestamps','camera calibration','public rigid marker calibration'],ground_truth_inputs=False,tile_size=a.tile_size,mode=a.mode,confidence=a.confidence,refine_corners=a.refine_corners,adaptive_sampling=a.adaptive_sampling,detections_cache=str(a.detections_cache) if a.detections_cache else None,latency_scope='cached detections excluded; not end-to-end' if cached is not None else 'end-to-end',seconds=time.perf_counter()-begin,segmented_frames=count,median_seconds=float(np.median(latencies)),p95_seconds=float(np.percentile(latencies,95)),marker_rejections=dict(pose_rejections),confirmed=sum(m['state']=='confirmed' for m in maps)))
    print('LOCALIZATION_COMPLETE',a.variant,len(maps),flush=True)


if __name__=='__main__':main()
