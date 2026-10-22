"""Public RGB-only marker adapter; no simulator pose, expected IDs or world map.

This is an interface guard for later localization, not a localization pipeline.
Explicit coded side avoids the historical0.10m default; explicit marker_id
avoids the historical triangulation KeyError. Reprojection gates are unchanged.
"""
import hashlib
import importlib.util
from pathlib import Path

import cv2
import numpy as np

FROZEN = Path(__file__).resolve().parents[3]/'outputs/frozen_field_pilot_20261019/frozen/src/uchuva_gazebo/multiview.py'
FROZEN_SHA = '14c7b2405839339909b34394ef20643d97db6524cc67d2b2449eabc37e51e4c0'
POSE_KEYS = {'marker_id', 'stamp_ns', 'R', 't', 'coded_side_m', 'corners_pixels', 'reprojection_rmse_px', 'source'}


def decode_marker_poses(rgb, intrinsic_matrix, stamp_ns, *, coded_side_m):
    """Use only decoder-observed IDs. No marker visible means no returned pose."""
    if coded_side_m != 0.2:
        raise ValueError('This frozen campaign requires explicit0.20m encoded side')
    if hashlib.sha256(FROZEN.read_bytes()).hexdigest() != FROZEN_SHA:
        raise ValueError('Frozen multiview implementation changed')
    spec = importlib.util.spec_from_file_location('marker_contract_multiview_v1', FROZEN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    image = np.asarray(rgb)
    if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
        raise ValueError('Expected uint8 RGB image')
    K = np.asarray(intrinsic_matrix, dtype=float)
    if K.shape != (3,3) or not np.isfinite(K).all() or K[0,0] <= 0 or K[1,1] <= 0:
        raise ValueError('Invalid public intrinsics')
    if type(stamp_ns) is not int:
        raise ValueError('Integer timestamp required')
    decoder = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))
    corners, ids, _ = decoder.detectMarkers(cv2.cvtColor(image, cv2.COLOR_RGB2GRAY))
    output = []
    if ids is None:
        return output
    for identifier, corner in zip(ids.ravel().tolist(), corners):
        points = corner.reshape(4,2)
        result = module.marker_pose(points, K, side=coded_side_m)
        if result['status'] != 'estimated':
            continue
        output.append(dict(marker_id=int(identifier), stamp_ns=stamp_ns,
            R=result['R'], t=result['t'], coded_side_m=coded_side_m,
            corners_pixels=points.tolist(), reprojection_rmse_px=result['reprojection_rmse_px'],
            source='actual_RGB_ArUco_decode'))
    return output


def triangulation_observation(decoded_pose, point_px):
    """Materialize marker_id explicitly instead of silently losing the pose key."""
    if set(decoded_pose) != POSE_KEYS or decoded_pose['source'] != 'actual_RGB_ArUco_decode':
        raise ValueError('Use a decoded RGB pose, with no extra/private fields')
    if type(decoded_pose['marker_id']) is not int or not 0 <= decoded_pose['marker_id'] < 50:
        raise ValueError('Explicit decoded marker_id required')
    if decoded_pose['coded_side_m'] != 0.2:
        raise ValueError('Marker size differs')
    R, t, point = np.asarray(decoded_pose['R']), np.asarray(decoded_pose['t']), np.asarray(point_px)
    if R.shape != (3,3) or t.shape != (3,) or point.shape != (2,):
        raise ValueError('Invalid pose or image point dimensions')
    if not all(np.isfinite(value).all() for value in (R,t,point)):
        raise ValueError('Nonfinite pose/image point')
    return dict(marker_id=decoded_pose['marker_id'], R=R.tolist(), t=t.tolist(), point_px=point.tolist(),
                stamp_ns=decoded_pose['stamp_ns'])
