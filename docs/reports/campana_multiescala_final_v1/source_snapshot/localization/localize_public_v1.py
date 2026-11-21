"""CPU marker-relative localization. Only public RGB/motion and frozen tracks.

No simulator pose, geometry, masks, true identity, or path planner is imported.
The two predeclared variants share the historical unchanged geometric gates.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import importlib
import json
from pathlib import Path
import sys
import time
import types

import cv2
import numpy as np
import psutil


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_frozen(folder, protocol):
    for filename, digest in protocol['frozen_module_sha256'].items():
        require(sha(folder / filename) == digest, 'Frozen code changed: ' + filename)
    package = types.ModuleType('metric_frozen_geometry_v1')
    package.__path__ = [str(folder)]
    sys.modules[package.__name__] = package
    modules = [importlib.import_module(package.__name__ + '.' + name)
               for name in ['multiview', 'marker_motion_fusion', 'localization', 'motion_observations']]
    return modules


def verify_files(folder, expected):
    require({p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()} == set(expected),
            'Public allowlist mismatch')
    for name, digest in expected.items():
        path = folder / name
        require(not Path(name).is_absolute() and '..' not in Path(name).parts and
                path.resolve().is_relative_to(folder.resolve()) and not path.is_symlink(), 'Unsafe public path')
        require(sha(path) == digest, 'Input hash changed: ' + name)


def validate_public(args, protocol, motion_module):
    admission = read(args.rgb_admission)
    require(set(admission) == {'version', 'passed', 'public_files'} and admission['passed'], 'Invalid RGB receipt')
    verify_files(args.public, admission['public_files'])
    frames = read(args.public / 'frames.json')
    require(all(set(f) == {'stamp_ns', 'filename', 'rgb_sha256'} for f in frames), 'Unexpected frame fields')
    require(set(admission['public_files']) == {'frames.json', 'calibration.json', 'marker_dimensions.json'} |
            {'rgb/' + f['filename'] for f in frames}, 'Unexpected public payload')
    for previous, current in zip(frames, frames[1:]):
        require(current['stamp_ns'] - previous['stamp_ns'] == 250_000_000, 'Incorrect frame interval')
    calibration = read(args.public / 'calibration.json')
    require(set(calibration) == {'width','height','intrinsic_matrix','distortion_coefficients','camera_model'}, 'Unexpected calibration keys')
    require(calibration['width'] == 1280 and calibration['height'] == 720 and
            all(x == 0 for x in calibration['distortion_coefficients']), 'Unexpected camera model')
    marker = read(args.public / 'marker_dimensions.json')
    require(set(marker) == {'dictionary','coded_side_m','board_side_m'} and marker['coded_side_m'] == .20 and
            marker['dictionary'] == 'DICT_4X4_50', 'Explicit coded marker side must be 0.20m')
    sensor_admission = read(args.sensor_admission)
    require(set(sensor_admission) == {'version','passed','sensor_files','rgb_frames_sha256',
            'rgb_calibration_sha256','marker_dimensions_sha256'} and sensor_admission['passed'], 'Invalid sensor receipt')
    require(set(sensor_admission['sensor_files']) == {'relative_motion.jsonl','sensor_model.json'}, 'Unexpected sensor files')
    verify_files(args.sensors, sensor_admission['sensor_files'])
    for key, filename in [('rgb_frames_sha256','frames.json'),('rgb_calibration_sha256','calibration.json'),
                          ('marker_dimensions_sha256','marker_dimensions.json')]:
        require(sensor_admission[key] == sha(args.public / filename), 'Sensor/RGB binding differs')
    model = read(args.sensors / 'sensor_model.json')
    require(set(model) == {'version','frame','interval_seconds','covariance_order','translation_density_m_per_sqrt_s',
            'rotation_density_rad_per_sqrt_s','noise_status','noise_distribution','bias','correlated_drift'}, 'Unexpected sensor model fields')
    require(model['interval_seconds'] == .25 and model['bias'] == model['correlated_drift'] == 'not_simulated', 'Sensor interval/drift differs')
    motions = [json.loads(line) for line in (args.sensors / 'relative_motion.jsonl').read_text().splitlines()]
    require(len(motions) == len(frames)-1, 'Motion count differs')
    for i, row in enumerate(motions):
        motion_module.RelativeMotion.from_dict(row)
        require(row['start_stamp_ns'] == frames[i]['stamp_ns'] and row['end_stamp_ns'] == frames[i+1]['stamp_ns'], 'Motion chain mismatch')
    observations = read(args.observations)
    require(len(observations) == len(frames), 'Tracking count mismatch')
    for i, (frame, observation) in enumerate(zip(frames, observations)):
        require(set(observation) == {'frame','stamp_ns','filename','prediction_record_sha256','detections'}, 'Unexpected track frame keys')
        require(observation['frame'] == i and observation['stamp_ns'] == frame['stamp_ns'] and
                observation['filename'] == frame['filename'], 'Tracking/RGB mismatch')
        for d in observation['detections']:
            require(set(d) == {'class_id','confidence','tile','box_xyxy_px','center_px','track_id','appearance'}, 'Unexpected detection fields')
            require(np.isfinite(d['center_px']).all() and len(d['center_px']) == 2, 'Invalid centroid')
    return frames, np.asarray(calibration['intrinsic_matrix'], float), motions, observations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['public','rgb-admission','sensors','sensor-admission','observations','protocol','out','frozen-src']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    protocol = read(args.protocol)
    require(protocol['version'] == 'full-routes-metric-localization/1', 'Unknown protocol')
    require(sha(Path(__file__)) == protocol['estimator_sha256'], 'Estimator changed after freeze')
    multiview, fusion_module, localization, motion_module = load_frozen(args.frozen_src, protocol)
    require(psutil.virtual_memory().available / 2**30 >= 6.5, 'RAM admission denied')
    frames, K, motions, observations = validate_public(args, protocol, motion_module)
    if args.out.exists():
        raise FileExistsError('Preserve completed or partial localization: ' + str(args.out))
    args.out.mkdir(parents=True)
    minimum_free = psutil.virtual_memory().available / 2**30
    def guard(stage, completed):
        nonlocal minimum_free
        free = psutil.virtual_memory().available / 2**30
        minimum_free = min(minimum_free, free)
        require(free >= 3, 'RAM early stop protects 2GiB reserve')
        write(args.out / 'progress.json', dict(pid=__import__('os').getpid(), stage=stage, completed=completed,
            free_gib=free, minimum_free_gib=minimum_free, timestamp=time.time()))
    binding = dict(protocol_sha256=sha(args.protocol), estimator_sha256=sha(Path(__file__)),
        tracking_sha256=sha(args.observations), rgb_receipt_sha256=sha(args.rgb_admission),
        sensor_receipt_sha256=sha(args.sensor_admission))
    write(args.out / 'input_binding.json', binding)
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))
    fusion = None
    poses = []
    groups = {'visual_only': defaultdict(list), 'fused': defaultdict(list)}
    for i, (frame, observation) in enumerate(zip(frames, observations)):
        guard('poses', i)
        if fusion is not None and i:
            fusion.predict(motions[i-1])
        image = cv2.imread(str(args.public / 'rgb' / frame['filename']))
        require(image is not None and image.shape == (720,1280,3), 'Invalid RGB')
        corners, ids, _ = detector.detectMarkers(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
        decoded = []
        accepted = []
        for marker_id, corner in sorted(zip([] if ids is None else ids.ravel().tolist(), corners), key=lambda p:p[0]):
            points = corner.reshape(4,2)
            pose = multiview.marker_pose(points, K, side=.20, max_error=3., ambiguity_gap=.25)
            entry = dict(marker_id=int(marker_id), corners_pixels=points.tolist(), pose_result=pose, fusion_accepted=False)
            decoded.append(entry)
            if pose['status'] != 'estimated':
                continue
            if fusion is not None and fusion.marker_id != marker_id:
                entry['fusion_rejection'] = 'uncalibrated_marker_component'
                continue
            accepted.append(dict(marker_id=int(marker_id), stamp_ns=frame['stamp_ns'], R=pose['R'], t=pose['t'], source='RGB_ArUco'))
            try:
                Q = fusion_module.marker_projection_covariance(pose['R'], pose['t'], K, .20, corner_sigma_px=.5)
                if fusion is None:
                    fusion = fusion_module.MarkerMotionFusion(int(marker_id), gate=16.8)
                entry['fusion_accepted'] = fusion.correct(frame['stamp_ns'], int(marker_id), pose['R'], pose['t'], Q)
                if not entry['fusion_accepted']:
                    entry['fusion_rejection'] = fusion.rejections[-1]
            except ValueError as exc:
                entry['fusion_rejection'] = str(exc)
        row = dict(frame=i, stamp_ns=frame['stamp_ns'], decoded=decoded,
            visual_only=accepted[0] if accepted else None, fused=fusion.camera_from_marker() if fusion else None)
        poses.append(row)
        with (args.out / 'poses.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(row, allow_nan=False) + '\n')
        for variant in groups:
            pose = row[variant]
            if pose is None:
                continue
            for j, detection in enumerate(observation['detections']):
                groups[variant][detection['track_id']].append(dict(R=pose['R'],t=pose['t'],
                    marker_id=pose['marker_id'], point_px=detection['center_px'], stamp_ns=frame['stamp_ns'],
                    observation_id=f'{i}:{j}', frame=i, prediction_index=j, class_id=detection['class_id']))
    all_tracks = sorted({d['track_id'] for o in observations for d in o['detections']})
    summaries = {}
    for variant, tracks in groups.items():
        reasons = Counter()
        estimates = 0
        with (args.out / (variant + '_triangulation.jsonl')).open('x',encoding='utf-8') as stream:
            for i, track in enumerate(all_tracks):
                if i % 25 == 0:
                    guard('triangulation_' + variant, i)
                obs = tracks.get(track, [])
                result = localization.robust_triangulate(obs, K)
                reasons[result.get('reason',result['status'])] += 1
                estimates += result['status'] == 'estimated'
                stream.write(json.dumps(dict(track_id=track, available_pose_observations=len(obs),
                    observation_ids=[o['observation_id'] for o in obs], result=result), allow_nan=False) + '\n')
        summaries[variant] = dict(pose_frames=sum(p[variant] is not None for p in poses),
            tracks=len(all_tracks), tracks_with_pose_observations=len(tracks), estimated_tracks=estimates,
            rejection_reasons=dict(reasons))
    guard('complete', len(frames))
    write(args.out / 'summary.json', dict(version=protocol['version'], complete=True, frames=len(frames),
        private_inputs=False, rerendered=False, detector_reinference=False, tracker_rerun=False,
        decoded_frames=sum(bool(p['decoded']) for p in poses),
        accepted_marker_pose_frames=sum(p['visual_only'] is not None for p in poses),
        fusion_visual_updates=sum(d['fusion_accepted'] for p in poses for d in p['decoded']),
        marker_pose_outcomes=dict(Counter(d['pose_result'].get('reason',d['pose_result']['status']) for p in poses for d in p['decoded'])),
        fusion_rejections=[] if fusion is None else fusion.rejections,
        variants=summaries, minimum_free_gib=minimum_free, binding=binding,
        output_sha256={p.name:sha(p) for p in args.out.glob('*.jsonl')}))


if __name__ == '__main__':
    main()
