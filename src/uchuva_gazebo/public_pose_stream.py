"""Strict public canonical-pose input boundary; no simulator truth fields."""
import json
import numpy as np


def load_public_pose_stream(path, rig):
    canonical={r['canonical_id'] for r in rig.values()}
    permitted={'R','t','source','stamp_ns','marker_id','canonical_pose_covariance',
               'version','uncertainty_status'}
    frames={};last=None
    with path.open() as stream:
        for line in stream:
            row=json.loads(line)
            if set(row)!={'stamp_ns','marker_poses'}:raise ValueError('Unexpected frame fields')
            stamp=row['stamp_ns']
            if type(stamp) is not int or (last is not None and stamp<=last):raise ValueError('Non-monotonic pose timestamps')
            last=stamp;converted={}
            for key,pose in row['marker_poses'].items():
                marker=int(key)
                if str(marker)!=key or marker not in canonical or marker not in rig:raise ValueError('Unknown canonical marker')
                if set(pose)-permitted:raise ValueError('Unexpected pose fields')
                if pose.get('source') not in ('RGB_ArUco_plus_relative_motion','RGB_ArUco'):raise ValueError('Unexpected pose source')
                if pose.get('stamp_ns',stamp)!=stamp or pose.get('marker_id',marker)!=marker:raise ValueError('Pose identity or timestamp mismatch')
                R=np.asarray(pose['R'],float);t=np.asarray(pose['t'],float)
                if R.shape!=(3,3) or t.shape!=(3,) or not np.isfinite(R).all() or not np.isfinite(t).all():raise ValueError('Invalid pose shape')
                if not np.allclose(R.T@R,np.eye(3),atol=1e-5) or np.linalg.det(R)<.999:raise ValueError('Invalid rotation')
                converted[marker]=dict(R=R.tolist(),t=t.tolist())
            frames[stamp]=converted
    return frames
