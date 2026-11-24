"""Replay public visual poses and noisy odometry; not a localization evaluation."""
import json
import argparse
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.marker_motion_fusion import MarkerMotionFusion,canonical_visual_measurements,marker_projection_covariance
from uchuva_lsystem.segmentation_cycles import write,sha


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-name',default='pose_fusion_v2')
    parser.add_argument('--max-unanchored-seconds',type=float)
    parser.add_argument('--projection-covariance',action='store_true')
    args=parser.parse_args()
    if Path(args.output_name).name!=args.output_name:raise ValueError('Output must be a directory name')
    if args.max_unanchored_seconds is not None and args.max_unanchored_seconds<=0:raise ValueError('Positive visual-anchor lifetime required')
    root=ROOT/'outputs/integral_diagnosis_20261014'
    source=ROOT/'outputs/continuous_row_20261008/estimates/offline_every_frame/observations.jsonl'
    out=root/args.output_name;out.mkdir(exist_ok=False)
    calibration=json.loads((ROOT/'outputs/continuous_row_20261008/public/calibration.json').read_text())
    canonical={str(r['id']):r['canonical_id'] for r in calibration['rig']}
    rig={str(r['id']):r for r in calibration['rig']}
    # Isotropic marker-pose measurement uncertainty is a declared initial guess.
    Q=np.diag([.02**2]*3+[.05**2]*3)
    for profile in ('low','nominal','high'):
        path=root/'public_motion'/f'{profile}.jsonl'
        motion={r['end_stamp_ns']:r for r in map(json.loads,path.open())}
        filters={};last_visual={};expired=0;n=0;visual=0;accepted=0;propagated=0;gap_resets=0
        with (out/f'{profile}.jsonl').open('w') as stream,source.open() as records:
            for line in records:
                row=json.loads(line);stamp=row['stamp_ns'];n+=1
                for marker in list(filters):
                    if args.max_unanchored_seconds is not None and (stamp-last_visual[marker])/1e9>args.max_unanchored_seconds:
                        del filters[marker];expired+=1;continue
                    f=filters[marker]
                    if f.stamp==stamp:continue
                    increment=motion.get(stamp)
                    if increment is None or increment['start_stamp_ns']!=f.stamp:
                        del filters[marker];gap_resets+=1;continue
                    f.predict(increment)
                observed_canonical={str(canonical[k]) for k in row['marker_poses']}
                for decoded,pose in row['marker_poses'].items():
                    marker=canonical[decoded]
                    measurement_Q=Q
                    if args.projection_covariance:
                        relation=rig[decoded]
                        Rmc=np.asarray(relation['R_marker_from_canonical'])
                        tmc=np.asarray(relation['t_marker_from_canonical_m'])
                        # Recover decoded-marker pose for its actual four corners.
                        Rcm=np.asarray(pose['R'])@Rmc.T
                        tcm=np.asarray(pose['t'])-Rcm@tmc
                        local_Q=marker_projection_covariance(Rcm,tcm,calibration['K'],calibration['marker_side_m'])
                        basis=np.zeros((6,6));basis[:3,:3]=Rmc.T;basis[3:,3:]=Rmc.T
                        measurement_Q=basis@local_Q@basis.T
                    # Historical poses are already canonical; only the key is decoded ID.
                    visual+=1
                    f=filters.setdefault(marker,MarkerMotionFusion(marker))
                    valid=f.correct(stamp,marker,pose['R'],pose['t'],measurement_Q)
                    accepted+=valid
                    if valid:last_visual[marker]=stamp
                poses={str(k):f.camera_from_marker() for k,f in filters.items()}
                propagated+=sum(k not in observed_canonical for k in poses)
                stream.write(json.dumps(dict(stamp_ns=stamp,marker_poses=poses))+'\n')
        write(out/f'{profile}_summary.json',dict(version='pose-fusion-replay/1.0',profile=profile,
            frames=n,visual_measurements=visual,accepted_visual_updates=accepted,
            propagated_marker_frames=propagated,gap_resets=gap_resets,
            expired_visual_anchors=expired,max_unanchored_seconds=args.max_unanchored_seconds,
            lifetime_status='engineering_heuristic_development_ablation',
            source_public_observations_sha256=sha(source),motion_sha256=sha(path),
            marker_covariance_heuristic=None if args.projection_covariance else Q.tolist(),
            marker_covariance_method='projection_jacobian_corner_sigma_0.5px' if args.projection_covariance else 'fixed_diagonal',
            limitation='Propagation is not a detection or correct localization; geometry and error evaluation pending',
            uncertainty_status='uncalibrated_first_order_covariance'))
        print('FUSION',profile,n,visual,accepted,flush=True)


if __name__=='__main__':main()
