"""Compare temporal protocols using the same cached RGB-only predictions."""
import argparse
from collections import defaultdict,Counter
import json
from pathlib import Path
import sys
import time
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.multiview import Tracker,marker_pose
from uchuva_gazebo.localization import canonical_pose,appearance
from uchuva_gazebo.mask_tracking import MaskTracker
from uchuva_gazebo.offline_reconciliation import fit_sequence,reconcile_offline
from uchuva_lsystem.segmentation_cycles import write,sha,check_deadline


def main():
    p=argparse.ArgumentParser()
    for name in ('root','public','cache','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--protocol',choices=['historical_1hz','historical_every_frame','offline_every_frame'],required=True)
    p.add_argument('--mask-overlap-device',choices=['cpu','cuda'],default='cpu')
    p.add_argument('--flow-device',choices=['cpu','cuda'],default='cpu')
    p.add_argument('--resume-observations',type=Path)
    p.add_argument('--resume-flow-switch-frame',type=int,default=None)
    p.add_argument('--public-fused-poses',type=Path)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);begin=time.perf_counter()
    calibration=json.loads((a.public/'calibration.json').read_text());K=calibration['K']
    # This whitelist is publicly declared, not inferred from truth masks.
    allowed=set(calibration['target_marker_ids']);rig={r['id']:r for r in calibration['rig'] if r['id'] in allowed}
    fused={}
    if a.public_fused_poses:
        if a.resume_observations:raise ValueError('Pose ablation cannot reuse historical pose prefix')
        from uchuva_gazebo.public_pose_stream import load_public_pose_stream
        fused=load_public_pose_stream(a.public_fused_poses,rig)
    frames=json.loads((a.public/'frames.json').read_text())
    if a.public_fused_poses and any(f['stamp_ns'] not in fused for f in frames):raise ValueError('Missing fused timestamp')
    cache_config=json.loads((a.cache/'configuration.json').read_text())
    if cache_config['frames_sha256']!=sha(a.public/'frames.json'):raise ValueError('Cache frame mismatch')
    if not json.loads((a.cache/'completion.json').read_text())['completed']:raise ValueError('Incomplete inference cache')
    overlap_backend=None
    if a.mask_overlap_device=='cuda':
        if a.protocol!='offline_every_frame':raise ValueError('CUDA overlap requires mask tracking')
        from uchuva_gazebo.gpu_mask_overlap import CudaMaskOverlap
        overlap_backend=CudaMaskOverlap()
        print('MASK_OVERLAP_DEVICE cuda',flush=True)
    flow_backend=None
    if a.flow_device=='cuda':
        from uchuva_gazebo.cuda_sparse_flow import CudaSparseFlow
        flow_backend=CudaSparseFlow();print('OPTICAL_FLOW_DEVICE cuda',flush=True)
    tracker=MaskTracker(overlap_backend=overlap_backend,flow_backend=flow_backend) if a.protocol=='offline_every_frame' else Tracker()
    prefix=[]
    if a.resume_observations:
        if a.protocol!='offline_every_frame':raise ValueError('Prefix recovery is offline only')
        with a.resume_observations.open(encoding='utf-8') as saved:
            for line in saved:
                if not line.endswith('\n'):break
                prefix.append(json.loads(line))
        if [f['stamp_ns'] for f in prefix]!=[f['stamp_ns'] for f in frames[:len(prefix)]]:raise ValueError('Prefix timestamps mismatch')
        for f in prefix:
            for d in f['detections']:tracker.next_id=max(tracker.next_id,int(d['track_id'].split('_')[-1])+1)
        print('RESUME_PRESERVED_FRAMES',len(prefix),flush=True)
    params=cv2.aruco.DetectorParameters();params.cornerRefinementMethod=cv2.aruco.CORNER_REFINE_SUBPIX
    detector=cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100),params)
    tracks=defaultdict(list);descriptors=defaultdict(list);classes=defaultdict(Counter);stamps=defaultdict(list)
    pose_history={};last=-1e20;rejections=[];count=0
    with (a.output/'observations.jsonl').open('w',encoding='utf-8') as stream:
        for frame in frames:
            check_deadline(a.root);stamp=frame['stamp_ns'];now=stamp/1e9
            if a.protocol=='historical_1hz' and now-last<.999:continue
            last=now;path=Path(frame['filename'])
            if set(frame)!={'stamp_ns','filename'} or path.is_absolute() or '..' in path.parts:raise ValueError('Unsafe public frame')
            image=cv2.imread(str(a.public/'rgb'/path))
            cache=json.loads((a.cache/f'{stamp}.json').read_text())
            if cache['rgb_sha256']!=sha(a.public/'rgb'/path):raise ValueError('RGB changed since inference')
            indices=[i for i,v in enumerate(cache['proposals']) if v['accepted']]
            detections=[dict(cache['proposals'][i]) for i in indices]
            if a.protocol=='offline_every_frame':
                # Older saved frames need identity/pose verification but no
                # masks: only the recent motion window reconstructs the tracker.
                if count>=len(prefix) or stamp>=prefix[-1]['stamp_ns']-2100000000:
                    with np.load(a.cache/f'{stamp}.npz') as packed:
                        h,w=map(int,packed['shape']);masks=np.unpackbits(packed['packed_masks'][indices],axis=1,count=h*w).reshape(-1,h,w).astype(bool)
                if count<len(prefix):
                    saved=prefix[count]
                    if [d['observation_id'] for d in saved['detections']]!=[d['observation_id'] for d in detections]:raise ValueError('Prefix predictions mismatch')
                    detections=saved['detections']
                    if stamp>=prefix[-1]['stamp_ns']-2100000000:
                        tracker.restore_observation(image,detections,stamp,masks,use_cuda=a.resume_flow_switch_frame is not None and count>=a.resume_flow_switch_frame)
                else:tracker.update(image,detections,stamp,masks)
            else:tracker.update(image,detections,stamp)
            corners,ids,_=detector.detectMarkers(image);poses={};decoded=[] if ids is None else ids.ravel().tolist()
            for corner,identifier in zip(corners,decoded):
                if identifier not in rig or decoded.count(identifier)!=1:continue
                pose=marker_pose(corner,K,side=calibration['marker_side_m'])
                if pose.get('reason')=='ambiguous_marker_pose' and identifier in pose_history:
                    old=pose_history[identifier]
                    if now-old['time']<=2:
                        choices=sorted(pose['candidates'],key=lambda c:np.linalg.norm(np.asarray(c['R'])-old['R'])+np.linalg.norm(np.asarray(c['t'])-old['t']))
                        if np.linalg.norm(np.asarray(choices[0]['R'])-old['R'])<.5:pose=dict(status='estimated',**choices[0])
                if pose['status']!='estimated':
                    rejections.append(dict(stamp_ns=stamp,marker_id=identifier,reason=pose['reason']));continue
                pose_history[identifier]=dict(time=now,R=pose['R'],t=pose['t'])
                poses[identifier]=canonical_pose(pose,rig[identifier])
            if count<len(prefix):
                # Preserve previously emitted poses and detections; RGB marker
                # replay above restores temporal pose history without truth.
                poses=prefix[count]['marker_poses'];decoded=prefix[count]['decoded_marker_ids']
            if a.public_fused_poses:poses=fused[stamp]
            for d in detections:
                tid=d['track_id'];d.setdefault('appearance',appearance(image,d['box_xyxy_px']).tolist())
                descriptors[tid].append(d['appearance']);classes[tid][d['class_id']]+=1;stamps[tid].append(stamp)
                seen=set()
                for marker,pose in poses.items():
                    canonical=rig[int(marker)]['canonical_id']
                    if canonical in seen:continue
                    seen.add(canonical)
                    tracks[tid,canonical].append(dict(**pose,marker_id=canonical,point_px=d['center_px'],stamp_ns=stamp,observation_id=d['observation_id']))
            stream.write(json.dumps(dict(stamp_ns=stamp,detections=detections,marker_poses=poses,decoded_marker_ids=decoded))+'\n')
            count+=1
            if count%100==0:
                stream.flush();print('TRACKED',a.protocol,count,flush=True)
                if overlap_backend is not None:
                    cuda=overlap_backend.torch.cuda
                    print('CUDA_MEMORY_BYTES',cuda.memory_allocated(),cuda.memory_reserved(),
                          'ACTIVE_TRACKS',len(tracker.tracks),flush=True)
    fitted=defaultdict(list);rejected=[]
    supported_tracks={tid for tid,marker in tracks}
    for tid in stamps:
        if tid not in supported_tracks:rejected.append(dict(track_id=tid,status='unavailable',reason='no_target_marker_pose_during_track'))
    for (tid,marker),observations in tracks.items():
        check_deadline(a.root);fit=fit_sequence(observations,K)
        if fit['status']!='estimated':rejected.append(dict(track_id=tid,marker_id=marker,**fit));continue
        x,y,z=fit['position_marker_m']
        if abs(x)>1.2 or not -.25<=y<=3 or not -1.5<=z<=.7:
            rejected.append(dict(track_id=tid,marker_id=marker,reason='outside_public_plant_envelope'));continue
        descriptor=np.mean(descriptors[tid],axis=0);descriptor/=max(np.linalg.norm(descriptor),1e-9)
        fitted[tid].append(dict(**fit,marker_id=marker,track_ids=[tid],class_id=classes[tid].most_common(1)[0][0],
            appearance=descriptor.tolist(),source_observations=observations,all_stamps=stamps[tid],
            observation_ids=fit['inlier_observation_ids'],association_cost=float(abs(x)+.3*abs(z+.18))))
    candidates=[]
    for tid,values in fitted.items():
        values.sort(key=lambda v:v['association_cost']);item=values[0];item['state']='confirmed'
        if len(values)>1 and values[1]['association_cost']-item['association_cost']<.15:
            item['state']='provisional';item['rejection_reasons']=['ambiguous_plant_marker']
        candidates.append(item)
    decisions=[]
    if a.protocol=='offline_every_frame':
        provisional=[c for c in candidates if c['state']=='provisional']
        objects,decisions=reconcile_offline([c for c in candidates if c['state']=='confirmed'],K)
        for i,c in enumerate(provisional):c['map_id']=f'provisional_{i:06d}'
        objects+=provisional
    else:objects=[dict(map_id=f'calyx_{i:06d}',**c) for i,c in enumerate(candidates)]
    for item in objects:item.pop('source_observations',None)
    by_track={tid:item for item in objects for tid in item['track_ids']}
    reasons=defaultdict(list)
    for entry in rejected:reasons[entry['track_id']].append(entry.get('reason','cause_not_determined'))
    with (a.output/'reconciled_observations.jsonl').open('w',encoding='utf-8') as stream:
        for line in (a.output/'observations.jsonl').open(encoding='utf-8'):
            frame=json.loads(line)
            for detection in frame['detections']:
                item=by_track.get(detection['track_id'])
                detection.update(timestamp_ns=frame['stamp_ns'],persistent_id=item['map_id'] if item else None,
                    canonical_aruco=item['marker_id'] if item else None,position_xyz_m=item['position_marker_m'] if item else None,
                    uncertainty_m=item.get('uncertainty_m') if item else None,state=item['state'] if item else 'no_localizable',
                    rejection_reasons=item.get('rejection_reasons',[]) if item else reasons[detection['track_id']])
            stream.write(json.dumps(frame)+'\n')
    write(a.output/'map.json',dict(version='offline-calyx-map/2.0',units='metres',objects=objects,rejected=rejected,
        center_semantics='visible-mask centroid triangulation; bias relative to geometric capacho centre evaluated separately'))
    write(a.output/'reconciliation.json',decisions)
    write(a.output/'tracking_rejections.json',tracker.rejections);write(a.output/'pose_rejections.json',rejections)
    write(a.output/'provenance.json',dict(protocol=a.protocol,cache_configuration_sha256=sha(a.cache/'configuration.json'),
        calibration_sha256=sha(a.public/'calibration.json'),inputs=['RGB','timestamps','public camera and marker calibration']+(['public pose stream (see hash and source)'] if a.public_fused_poses else []),
        ground_truth_inputs=False,processed_frames=count,seconds=time.perf_counter()-begin,
        public_fused_poses_sha256=sha(a.public_fused_poses) if a.public_fused_poses else None,
        pose_ablation='External public pose stream; fixed detections and tracker; source cadence must be controlled' if a.public_fused_poses else None,
        mask_overlap_device=a.mask_overlap_device,cuda_overlap_calls=getattr(overlap_backend,'calls',0),
        cuda_overlap_pairs=getattr(overlap_backend,'pairs',0),
        flow_device=a.flow_device,cuda_flow_calls=getattr(flow_backend,'calls',0),
        resumed_frames=len(prefix),resume_observations_sha256=sha(a.resume_observations) if a.resume_observations else None,
        resume_flow_switch_frame=a.resume_flow_switch_frame,
        recovery_note='Saved detections and canonical poses retained; recent CPU flow reconstructed from RGB; prefix tracking rejection diagnostics unavailable' if prefix else None,
        comparison_note='Historical temporal tracker; common qualified geometry gate held constant to isolate cadence and reconciliation'))


if __name__=='__main__':main()
