"""PRIVILEGED evaluator experiments: never estimator inputs or deployable scores."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.flight_control import world_to_body
from uchuva_gazebo.segmentation_evaluation import decode_panoptic_rgb
from uchuva_gazebo.offline_reconciliation import fit_sequence,representative_views
from uchuva_lsystem.segmentation_cycles import write


def true_marker_pose(sample,marker):
    normal=np.asarray(marker['normal_world']);up=np.array([0,0,1]);right=np.cross(up,normal)
    world_from_marker=np.column_stack((right,up,normal))
    body_from_world=np.column_stack([world_to_body(np.eye(3)[:,i],sample['quaternion_xyzw']) for i in range(3)])
    cv_from_body=np.array([[0,-1,0],[0,0,-1],[1,0,0]])
    R=cv_from_body@body_from_world@world_from_marker
    t=cv_from_body@(body_from_world@(np.asarray(marker['center_world_m'])-sample['position'])-[.068,0,.005])
    return dict(R=R.tolist(),t=t.tolist())


def main():
    p=argparse.ArgumentParser()
    for name in ('flight','truth','public','estimates','evaluation','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    truth=json.loads(a.truth.read_text());objects=truth['objects'];frames={f['stamp_ns']:f for f in truth['frames']}
    K=np.asarray(json.loads((a.public/'calibration.json').read_text())['K'])
    markers={m['id']:m for m in json.loads((a.flight.parent/'preflight.json').read_text())['markers']}
    telemetry=json.loads((a.flight/'telemetry.json').read_text())['samples'];times=np.array([s['t'] for s in telemetry])
    pairs={p['stamp_ns']:p for p in json.loads((a.flight/'paired/pairs.json').read_text())['pairs']}
    streams={name:defaultdict(list) for name in ('true_pose_original_tracks','true_pose_true_identity_predicted_centroid','true_pose_true_identity_visible_centroid','true_pose_projected_geometric_centre')}
    matches={};bias=[];time_errors=[]
    for line in (a.evaluation/'frame_diagnostics.jsonl').open():
        frame=json.loads(line)
        for m in frame['matches']:matches[m['observation_id']]=m['matched_code']
    for line in (a.estimates/'observations.jsonl').open():
        frame=json.loads(line);stamp=frame['stamp_ns'];sample=telemetry[int(np.argmin(abs(times-stamp/1e9)))];time_errors.append(abs(sample['t']-stamp/1e9))
        poses={};native=cv2.imread(str(a.flight/'paired'/pairs[stamp]['mask']));codes=decode_panoptic_rgb(native[:,:,::-1])
        for entry in frames[stamp]['instances']:
            code=str(entry['code']);obj=objects[code]
            if obj['role']!='target':continue
            marker=obj['canonical_marker_id'];pose=poses.setdefault(marker,true_marker_pose(sample,markers[marker]))
            point=np.asarray(pose['R'])@obj['position_marker_m']+pose['t']
            if point[2]<=0:continue
            projection=K@point;projection=projection[:2]/projection[2]
            ys,xs=np.nonzero(codes==int(code));centroid=np.array([xs.mean(),ys.mean()]);bias.append(float(np.linalg.norm(centroid-projection)))
            for name,pixel in [('true_pose_true_identity_visible_centroid',centroid),('true_pose_projected_geometric_centre',projection)]:
                streams[name][code].append(dict(**pose,marker_id=marker,point_px=pixel.tolist(),stamp_ns=stamp,observation_id=f'{stamp}:{code}'))
        for d in frame['detections']:
            code=matches.get(d['observation_id'])
            if code is None or objects[code]['role']!='target':continue
            marker=objects[code]['canonical_marker_id'];pose=poses[marker]
            observation=dict(**pose,marker_id=marker,point_px=d['center_px'],stamp_ns=stamp,observation_id=d['observation_id'])
            streams['true_pose_true_identity_predicted_centroid'][code].append(observation)
            # Keep the predicted temporal identity, rather than repairing it.
            streams['true_pose_original_tracks'][(d['track_id'],marker)].append(dict(**observation,truth_code=code))
    results={}
    for name,groups in streams.items():
        rows=[]
        for key,observations in groups.items():
            code=key if isinstance(key,str) else max({o['truth_code'] for o in observations},key=lambda c:sum(o['truth_code']==c for o in observations))
            fit=fit_sequence(observations,K)
            error=float(np.linalg.norm(np.asarray(fit['position_marker_m'])-objects[code]['position_marker_m'])) if fit['status']=='estimated' else None
            rows.append(dict(group=str(key),code=code,error_m=error,**fit))
        errors=[r['error_m'] for r in rows if r['error_m'] is not None]
        results[name]=dict(rows=rows,estimated=len(errors),median_error_m=float(np.median(errors)) if errors else None,
            p95_error_m=float(np.percentile(errors,95)) if errors else None,
            unique_targets_with_error_le_5cm=len({r['code'] for r in rows if r['error_m'] is not None and r['error_m']<=.05}))
    write(a.output/'privileged_diagnostics.json',dict(version='privileged-geometry-diagnostics/1.0',
        deployable=False,estimator_input=False,experiments=results,
        visible_centroid_to_projected_geometric_centre_median_px=float(np.median(bias)) if bias else None,
        visible_centroid_to_projected_geometric_centre_p95_px=float(np.percentile(bias,95)) if bias else None,
        simulator_pose_timestamp_nearest_max_error_seconds=max(time_errors,default=None),
        limitation='Privileged conditional experiments; differences are diagnostic associations, not independent causal effect estimates. Pose uses nearest logged timestamp.'))


if __name__=='__main__':main()
