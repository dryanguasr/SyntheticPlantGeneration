"""RGB-only pilot inference. Inputs deliberately exclude masks, inventory and telemetry."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
import cv2

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'desktop')]
from uchuva_aruco.vision import VisionEngine, Settings
from uchuva_gazebo.multiview import Tracker, marker_pose, triangulate


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rgb',type=Path,required=True)
    p.add_argument('--frames',type=Path,required=True,help='Public RGB-only timestamp index')
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--assets',type=Path,default=ROOT/'mobile/android/app/src/main/assets')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    config=json.loads(args.config.read_text());frames=json.loads(args.frames.read_text())
    if any(set(f)-{'stamp_ns','filename'} for f in frames):raise ValueError('RGB-only index required')
    engine=VisionEngine(args.assets)
    if engine.model_hash!=config['model_sha256']:raise ValueError('Frozen detector hash differs')
    settings=Settings(side_cm=10,confidence=.25,dictionary='DICT_4X4_100')
    K=config['camera']['K'];tracker=Tracker();tracks=defaultdict(list)
    writer=cv2.VideoWriter(str(args.output/'annotated_5hz.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),5,(1280,720))
    if not writer.isOpened():raise RuntimeError('Cannot open video writer')
    with (args.output/'observations.jsonl').open('w') as stream:
        for i,frame in enumerate(frames):
            filename=Path(frame['filename'])
            if filename.is_absolute() or '..' in filename.parts:raise ValueError('RGB path must stay within RGB directory')
            image=cv2.imread(str(args.rgb/filename))
            if image is None:raise ValueError(f'Missing RGB {filename}')
            _,result=engine.analyze(image,settings,frame_id=i,media_time_ms=frame['stamp_ns']/1e6)
            result['stamp_ns']=frame['stamp_ns']; tracker.update(image,result['detections'],frame['stamp_ns'])
            poses={}
            for marker in result['markers']:
                identifier=marker['id']
                if sum(m['id']==identifier for m in result['markers'])!=1:
                    poses[identifier]={'status':'unavailable','reason':'duplicate_marker_id'}
                else:poses[identifier]=marker_pose(marker['corners_px'],K)
            result['marker_poses']=poses
            for j,det in enumerate(result['detections']):
                det['observation_id']=f'{frame["stamp_ns"]}:{j}'
                det['depth_status']='unknown';det['multiview_candidates']=[]
                for marker_id,pose in poses.items():
                    if pose['status']!='estimated':continue
                    key=(det['track_id'],marker_id)
                    tracks[key].append({'stamp_ns':frame['stamp_ns'],'observation_id':det['observation_id'],
                        'point_px':det['center_px'],'marker_id':marker_id,'R':pose['R'],'t':pose['t']})
                    det['multiview_candidates'].append({'marker_id':marker_id,'status':'pending_multiview'})
                if not det['multiview_candidates']:det['position_3d_unavailable_reason']='marker_absent_or_pose_rejected'
                x1,y1,x2,y2=map(round,det['box_xyxy_px'])
                cv2.rectangle(image,(x1,y1),(x2,y2),(80,240,160),2)
                cv2.putText(image,f'{det["track_id"][6:]} {det["confidence"]:.2f}',(x1,max(20,y1-4)),
                            cv2.FONT_HERSHEY_SIMPLEX,.4,(80,240,160),1)
            for marker in result['markers']:
                import numpy as np
                points=np.array(marker['corners_px'],np.int32)
                cv2.polylines(image,[points],True,(255,180,30),2)
                cv2.putText(image,str(marker['id']),tuple(points[0]),cv2.FONT_HERSHEY_SIMPLEX,.5,(255,180,30),1)
            cv2.putText(image,f't={frame["stamp_ns"]/1e9:.2f}s | capachos={len(result["detections"])} | ArUcos={len(poses)}',
                        (15,25),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),2)
            writer.write(image);stream.write(json.dumps(result)+'\n')
            if i%50==0:print(f'RGB-only inference {i}/{len(frames)}',flush=True)
    writer.release()
    with (args.output/'reconstructions.jsonl').open('w') as stream:
        for (track,marker),obs in tracks.items():
            result=triangulate(obs,K)
            stream.write(json.dumps({'track_id':track,'marker_id':marker,**result,'observations_used':obs})+'\n')
    (args.output/'association_rejections.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in tracker.rejections))
    (args.output/'provenance.json').write_text(json.dumps({'script_version':config['script_version'],
        'seed':config['seed'],'parameter_preset':config['parameter_preset'],'model_sha256':engine.model_hash,
        'configuration_sha256':hashlib.sha256(args.config.read_bytes()).hexdigest(),
        'inputs':['RGB','simulation timestamps','ideal calibration','known marker side'],
        'ground_truth_inputs':False,'frames':len(frames)},indent=2))


if __name__=='__main__':main()
