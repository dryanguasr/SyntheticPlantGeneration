import json,sys
from pathlib import Path
import numpy as np,cv2
sys.path.insert(0,str(Path.cwd()/'src'))
from uchuva_gazebo.multiview import marker_pose
from uchuva_gazebo.marker_motion_fusion import MarkerMotionFusion,marker_projection_covariance
r=Path('outputs/integral_diagnosis_20261014/field_localization_v188');p=r.parent/'field_tracking_v187/public';K=np.array(json.loads((p/'calibration.json').read_text())['K']);board=json.loads((p/'board.json').read_text());motions={v['end_stamp_ns']:v for v in map(json.loads,(p/'relative_motion.jsonl').read_text().splitlines())}
params=cv2.aruco.DetectorParameters();params.cornerRefinementMethod=cv2.aruco.CORNER_REFINE_SUBPIX;detector=cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),params);fusion=MarkerMotionFusion(board['marker_id']);rows=[]
for f in json.loads((p/'frames.json').read_text()):
 stamp=f['stamp_ns'];image=cv2.imread(str(p/'rgb'/f['filename']));corners,ids,_=detector.detectMarkers(image);pose=None;correction=None
 if fusion.stamp is not None:fusion.predict(motions[stamp])
 if ids is not None:
  for c,id_ in zip(corners,ids.ravel()):
   if int(id_)!=board['marker_id']:continue
   pose=marker_pose(c,K,side=board['black_square_side_m'])
   if pose['status']=='estimated':
    Q=marker_projection_covariance(pose['R'],pose['t'],K,board['black_square_side_m']);correction=fusion.correct(stamp,board['marker_id'],pose['R'],pose['t'],Q)
 rows.append(dict(stamp_ns=stamp,ids=[] if ids is None else ids.ravel().tolist(),visual_pose=pose,correction_accepted=correction,fused=fusion.camera_from_marker()))
(r/'poses_public.json').write_text(json.dumps(dict(truth_used=False,rows=rows,rejections=fusion.rejections,corner_noise_px=.5,noise_status='engineering heuristic, uncalibrated'),indent=2));print([(x['ids'],x['correction_accepted']) for x in rows])

from collections import defaultdict,Counter
from uchuva_gazebo.localization import robust_triangulate
observations=json.loads((r.parent/'field_tracking_v187/predictions/observations.json').read_text())
fits={}
for variant in ('visual_pose','fused'):
 tracks=defaultdict(list)
 for frame,row in zip(observations,rows):
  assert frame['stamp_ns']==row['stamp_ns']
  pose=row[variant]
  if pose is None or pose.get('status','estimated')!='estimated':continue
  for j,d in enumerate(frame['detections']):
   tracks[d['track_id']].append(dict(R=pose['R'],t=pose['t'],marker_id=board['marker_id'],point_px=d['center_px'],stamp_ns=frame['stamp_ns'],observation_id=str(frame['stamp_ns'])+':'+str(j)))
 fits[variant]=[dict(track_id=tid,**robust_triangulate(obs,K)) for tid,obs in tracks.items()]
(r/'triangulation.json').write_text(json.dumps(fits,indent=2))
print({v:dict(Counter(x.get('reason',x['status']) for x in items)) for v,items in fits.items()})
