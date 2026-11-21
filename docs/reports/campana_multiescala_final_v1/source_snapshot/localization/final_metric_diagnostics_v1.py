"""Private post-evaluation explanation, no estimator change or rerun."""
from collections import Counter
import itertools
import json
from pathlib import Path
import cv2
import numpy as np
from localize_public_v1 import read,write,sha,require

ROOT=Path(__file__).resolve().parent
FULL=ROOT.parent
require(all((ROOT/'private_evaluation'/r/'summary.json').exists() for r in ['legacy','vertical','orbit']), 'Wait for evaluation')
dictionary=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
decoder=cv2.aruco.ArucoDetector(dictionary)
marker=cv2.aruco.generateImageMarker(dictionary,8,180)
reflection={}
for name,pattern in [('original',marker),('horizontal_reflection',marker[:,::-1]),('vertical_reflection',marker[::-1,:])]:
    _,ids,_=decoder.detectMarkers(cv2.copyMakeBorder(pattern,30,30,30,30,cv2.BORDER_CONSTANT,value=255))
    reflection[name]=[] if ids is None else ids.ravel().tolist()
board=read(FULL/'geometry_private/board_private.json');Rwm=np.asarray(board['R_world_from_marker']);origin=np.asarray(board['center_world_bu'])
diagnosis=dict(version='marker-reflection-diagnosis/1',marker_id=8,controlled_2d_reflection_fixture=reflection,
    estimator_modified=False,marker_modified=False,rerendered=False,routes={})
for route in ['legacy','vertical','orbit']:
    poses=[json.loads(s) for s in (ROOT/'public_estimates'/route/'poses.jsonl').read_text().splitlines()]
    errors=read(ROOT/'private_evaluation'/route/'pose_errors.json');bad=[]
    for e in errors:
        if e['variant']!='visual_only' or e['orientation_error_degrees']<=90:continue
        camera=read(FULL/'captures'/route/f"view_{e['frame']:03d}/camera_private.json")
        center=Rwm.T@(np.asarray(camera['matrix_world'])[:3,3]-origin)*board['meters_per_bu']
        d=poses[e['frame']]['decoded']
        bad.append(dict(frame=e['frame'],phase=e['phase'],side=e['side'],
            camera_marker_normal_coordinate_m=float(center[2]),
            behind_marker_plane=bool(center[2]<0),orientation_error_degrees=e['orientation_error_degrees'],
            position_error_m=e['position_error_m'],visual_fusion_update_accepted=any(x['fusion_accepted'] for x in d),
            marker_reprojection_rmse_px=[x['pose_result'].get('reprojection_rmse_px') for x in d]))
    summary=read(ROOT/'private_evaluation'/route/'summary.json')
    diagnosis['routes'][route]=dict(bad_visual_poses_over_90deg=len(bad),behind_marker_plane=sum(x['behind_marker_plane'] for x in bad),
        accepted_by_fusion=sum(x['visual_fusion_update_accepted'] for x in bad),cases=bad,
        marker_updates_rejected=len(summary['public_stage_summary']['fusion_rejections']))
diagnosis['evidence']='The unchanged detector decodes ID8 on mirrored synthetic patterns. Every listed case uses actual flight RGB decoding and private camera-side/orientation checks; these checks never feed the estimator.'
diagnosis['interpretation']='Planar reprojection and decoded ID alone cannot certify front-face correspondence for this pattern and two-sided synthetic board. Fusion innovation rejects listed large inconsistencies; retained drift and initial pose error remain.'
write(ROOT/'marker_reflection_diagnosis_v1.json',diagnosis)

# A narrowly scoped delivery audit checks new outputs and arithmetic without rerunning localization.
checks=[]
for route in ['legacy','vertical','orbit']:
    s=read(ROOT/'private_evaluation'/route/'summary.json')
    require(s['passed'] and s['native_matching_confusions_reproduced']==s['frames'],'Matching check failed')
    public=ROOT/'public_estimates'/route
    for name,digest in s['public_stage_summary']['output_sha256'].items():require(sha(public/name)==digest,'Estimate changed')
    for name,digest in s['output_sha256'].items():require(sha(ROOT/'private_evaluation'/route/name)==digest,'Evaluation changed')
    for v,m in s['calyx'].items():
        require(m['strictly_attributed_tracks']+sum(m['attribution_rejections'].values())==m['estimated_tracks'],'Attribution arithmetic')
        for scope,c in m['coverage'].items():
            require(0<=c['unique_localized']<=c['unique_visible'],'Coverage arithmetic')
    checks.append(dict(route=route,frames=s['frames'],hashes_passed=True,arithmetic_passed=True))
write(ROOT/'delivery_audit_v1.json',dict(passed=True,routes=checks,localization_executed_and_evaluated=True,
    scientific_promotion=False,negative_marker_poses_preserved=True,
    protocol_sha256=sha(ROOT/'protocol.json'),estimator_sha256=sha(ROOT/'localize_public_v1.py'),
    evaluator_sha256=sha(ROOT/'evaluate_metric_private_v1.py')))
print(json.dumps(diagnosis['routes'],indent=2))
