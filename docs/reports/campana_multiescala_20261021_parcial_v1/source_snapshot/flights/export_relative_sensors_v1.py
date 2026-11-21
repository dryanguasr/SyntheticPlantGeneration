"""Private CPU simulator: export noisy relative motion after full-route validation.

Never import this exporter in an estimator: it deliberately reads private poses.
The estimator receives only sensors_public plus its sanitized admission receipt.
It must obtain its initial marker-relative pose from real RGB ArUco decoding.
"""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FROZEN = REPO / 'outputs/frozen_field_pilot_20261019/frozen/src/uchuva_gazebo'
MOTION_SHA = 'be1ff23f70ebd0e5b1063364eebc969a68cc0607ed206f07d273ac916651c77b'
MODEL_KEYS = {'version', 'frame', 'interval_seconds', 'covariance_order',
              'translation_density_m_per_sqrt_s', 'rotation_density_rad_per_sqrt_s',
              'noise_status', 'noise_distribution', 'bias', 'correlated_drift'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')


def load_motion_contract():
    path = FROZEN / 'motion_observations.py'
    require(sha(path) == MOTION_SHA, 'Frozen relative-motion contract changed')
    spec = importlib.util.spec_from_file_location('frozen_relative_motion_export_v1', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.RelativeMotion


def validate_sensor_protocol(config):
    require(config['version'] == 'full-routes-relative-sensors/1', 'Unknown sensor protocol')
    require(config['scope'] == 'validation_only_after_completed_captures_and_public_validation', 'Validation only')
    require(config['fps'] == 4 and config['required_interval_ns'] == 250_000_000, 'Expected 4Hz / 0.25s')
    require(config['meters_per_blender_unit'] == 0.125, 'Unapproved metric scale')
    noise = config['noise']
    require(noise['translation_density_m_per_sqrt_s'] == 0.005, 'Frozen translation density differs')
    require(noise['rotation_density_rad_per_sqrt_s'] == 0.002, 'Frozen rotation density differs')
    require(noise['status'] == 'engineering_heuristic_not_physically_calibrated', 'Do not claim calibration')
    require(config['marker']['coded_side_m'] == 0.2, 'Explicit coded marker side must be 0.20m')
    require(config['marker']['dictionary'] == 'DICT_4X4_50', 'Marker dictionary differs')
    require(config['marker']['triangulation_requires_explicit_marker_id'], 'Explicit marker identity required')
    require(config['public_sensor_files'] == ['relative_motion.jsonl', 'sensor_model.json'], 'Public allowlist differs')
    seeds = list(config['sensor_seed_by_scene'].values())
    require(len(seeds) == len(set(seeds)), 'Each route needs independent sensor seed')
    require(all(type(s) is int and s not in range(914140, 914146) for s in seeds), 'Forbidden sensor seed')


def optical_pose(matrix_world, meters_per_bu):
    """Blender local x-right/y-up/z-back to optical x-right/y-down/z-forward."""
    matrix = np.asarray(matrix_world, dtype=float)
    require(matrix.shape == (4, 4) and np.isfinite(matrix).all(), 'Invalid private camera matrix')
    require(np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-8, rtol=0), 'Invalid homogeneous row')
    rotation = matrix[:3, :3] @ np.diag([1., -1., -1.])
    require(np.allclose(rotation.T @ rotation, np.eye(3), atol=2e-6, rtol=0), 'Camera rotation is not orthonormal')
    require(abs(np.linalg.det(rotation) - 1) < 2e-6, 'Camera rotation is not right-handed')
    return rotation, matrix[:3, 3] * meters_per_bu


def generate_motion(poses, stamps, config, scene_name):
    """Return only noisy measurements. Never serialize clean increments or RNG noise."""
    validate_sensor_protocol(config)
    require(len(poses) == len(stamps) and len(poses) >= 2, 'Need matching pose/time sequences')
    require(all(type(s) is int for s in stamps), 'Integer nanosecond timestamps required')
    require(all(b - a == config['required_interval_ns'] for a, b in zip(stamps, stamps[1:])), 'Missing/out-of-order frames or wrong dt')
    RelativeMotion = load_motion_contract()
    rng = np.random.default_rng(config['sensor_seed_by_scene'][scene_name])
    density = np.array([config['noise']['translation_density_m_per_sqrt_s']] * 3 +
                       [config['noise']['rotation_density_rad_per_sqrt_s']] * 3)
    rows = []
    for i, ((rotation, position), (next_rotation, next_position)) in enumerate(zip(poses, poses[1:])):
        dt = (stamps[i + 1] - stamps[i]) / 1e9
        sigma = density * math.sqrt(dt)
        perturbation = rng.normal(size=6) * sigma
        translation = rotation.T @ (next_position - position) + perturbation[:3]
        relative_rotation = cv2.Rodrigues(perturbation[3:])[0] @ rotation.T @ next_rotation
        rotation_vector = cv2.Rodrigues(relative_rotation)[0].reshape(3)
        rows.append(RelativeMotion(stamps[i], stamps[i + 1], tuple(translation), tuple(rotation_vector),
                    tuple(map(tuple, np.diag(sigma ** 2)))).to_dict())
    return rows


def public_model(config):
    return dict(version='relative-sensor-model/1', frame='previous_camera',
        interval_seconds=config['required_interval_ns']/1e9,
        covariance_order=config['noise']['covariance_order'],
        translation_density_m_per_sqrt_s=config['noise']['translation_density_m_per_sqrt_s'],
        rotation_density_rad_per_sqrt_s=config['noise']['rotation_density_rad_per_sqrt_s'],
        noise_status=config['noise']['status'], noise_distribution=config['noise']['distribution'],
        bias='not_simulated', correlated_drift='not_simulated')


def validate_public_sensor_payload(rows, model):
    """Strict structural allowlist, including nested scalar/vector/matrix values."""
    require(set(model) == MODEL_KEYS, 'Unexpected sensor model fields')
    require(model['version'] == 'relative-sensor-model/1' and model['frame'] == 'previous_camera', 'Invalid model frame')
    require(model['interval_seconds'] == 0.25, 'Public model dt differs')
    require(model['covariance_order'] == ['tx_m', 'ty_m', 'tz_m', 'rx_rad', 'ry_rad', 'rz_rad'], 'Covariance units/order differ')
    require(model['translation_density_m_per_sqrt_s'] == 0.005 and model['rotation_density_rad_per_sqrt_s'] == 0.002, 'Public noise differs')
    require(model['noise_status'] == 'engineering_heuristic_not_physically_calibrated', 'Uncalibrated noise required')
    require(model['noise_distribution'] == 'independent_zero_mean_gaussian_per_increment', 'Noise distribution differs')
    require(model['bias'] == model['correlated_drift'] == 'not_simulated', 'Unexpected drift declaration')
    RelativeMotion = load_motion_contract()
    for index, row in enumerate(rows):
        RelativeMotion.from_dict(row)
        require(type(row['start_stamp_ns']) is int and type(row['end_stamp_ns']) is int, 'Integer timestamps only')
        require(row['end_stamp_ns'] - row['start_stamp_ns'] == 250_000_000, 'Wrong sensor interval')
        require(row['source'] == 'simulated_noisy_odometry', 'Unexpected sensor source')
        require(np.allclose(row['covariance_6x6'], np.diag([0.005**2*0.25]*3 + [0.002**2*0.25]*3), rtol=0, atol=1e-15), 'Wrong dt covariance')
        if index:
            require(rows[index-1]['end_stamp_ns'] == row['start_stamp_ns'], 'Motion chain gap')


def checked_public_files(public, receipt):
    require(set(receipt) == {'version', 'passed', 'public_files'} and receipt['passed'] is True,
            'Unexpected/failed public RGB admission')
    require(receipt['version'] == 'public-inference-admission/1', 'Unsupported RGB receipt')
    files = receipt['public_files']
    actual = {p.relative_to(public).as_posix() for p in public.rglob('*') if p.is_file()}
    require(actual == set(files), 'RGB public file allowlist mismatch')
    for name, expected in files.items():
        path = public / name
        require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'Unsafe public path')
        require(not path.is_symlink() and path.resolve().is_relative_to(public.resolve()), 'Public path escapes package')
        require(sha(path) == expected, 'RGB public hash mismatch: ' + name)
    frames = read(public / 'frames.json')
    require(all(set(row) == {'stamp_ns', 'filename', 'rgb_sha256'} for row in frames), 'Unexpected frame fields')
    expected = {'frames.json', 'calibration.json', 'marker_dimensions.json'} | {'rgb/'+f['filename'] for f in frames}
    require(actual == expected, 'Unexpected RGB private data or missing RGB')
    for row in frames:
        require(row['filename'] == str(row['stamp_ns'])+'.png', 'RGB timestamp/filename mismatch')
        require(files['rgb/'+row['filename']] == row['rgb_sha256'], 'Frame RGB hash mismatch')
    return frames


def write_equal_or_new(path, payload):
    if path.exists():
        require(path.read_bytes() == payload, 'Existing output differs; preserve and investigate: '+str(path))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def export(root, scene_name, protocol_sha256, sensor_protocol_sha256, check_only=False):
    cv2.setNumThreads(1)
    protocol_path = root/'protocol.json'
    config_path = root/'sensor_protocol_v1.json'
    require(sha(protocol_path) == protocol_sha256, 'Campaign protocol hash differs')
    require(sha(config_path) == sensor_protocol_sha256, 'Sensor protocol hash differs')
    config, protocol = read(config_path), read(protocol_path)
    validate_sensor_protocol(config)
    require(sha(root/config['historical_review']) == config['historical_review_sha256'], 'Historical recovery review changed')
    scene = next(s for s in protocol['scenes'] if s['name'] == scene_name)
    require(scene['split'] == 'val' and scene['fps'] == 4 and scene['kind'] == 'flight', 'Validation flights at4Hz only')
    plants_seeds = {p['seed'] for s in protocol['scenes'] for p in s['plants']}
    require(not plants_seeds.intersection(config['sensor_seed_by_scene'].values()), 'Sensor/plant seed reuse')
    require(not plants_seeds.intersection(range(914140,914146)), 'Reserved seeds prohibited')
    flight = root/'flights'/scene_name
    validation_path = flight/'validation_v1.json'
    validation = read(validation_path)
    require(validation['passed'] and validation['hashes_palette_classes_ids_passed'] and validation['public_allowlist_passed'], 'Capture/public validation must pass first')
    require(validation['protocol_sha256'] == protocol_sha256, 'Validation bound to different campaign protocol')
    # Existing Windows validators serialize Path using backslashes; normalize
    # names only, never rewrite or weaken their hash bindings.
    validation_sources = {Path(name).as_posix(): digest for name, digest in validation['source_hashes'].items()}
    public = flight/'public'
    admission_path = flight/'public_admission_v1.json'
    frames = checked_public_files(public, read(admission_path))
    require(len(frames) == scene['views'] == len(scene['trajectory']), 'Incomplete captures')
    marker = read(public/'marker_dimensions.json')
    require(set(marker) == {'dictionary', 'coded_side_m', 'board_side_m'}, 'Unexpected marker fields, including expected IDs')
    require(marker['dictionary'] == config['marker']['dictionary'] and marker['coded_side_m'] == 0.2,
            'Explicit encoded side0.20m is required; no0.10m default')
    require(math.isclose(marker['board_side_m'], config['marker']['board_side_m']), 'Board scale differs')
    captures = root/'captures'/scene_name
    board = read(captures/'board_private.json')
    require(board['meters_per_bu'] == config['meters_per_blender_unit'], 'Private metric scale differs')
    require(math.isclose(board['side_bu']*board['meters_per_bu'], 0.2), 'Private coded side differs')
    poses, stamps, source_hashes = [], [], {}
    for index, row in enumerate(frames):
        folder = captures/f'view_{index:03d}'
        for name in ('camera_private.json','capture.json'):
            path = folder/name
            relative = path.relative_to(root).as_posix()
            require(validation_sources.get(relative) == sha(path), 'Private input not bound by successful validation: '+relative)
            source_hashes[relative] = sha(path)
        capture, camera = read(folder/'capture.json'), read(folder/'camera_private.json')
        require(capture['view'] == index and capture['scene'] == scene_name and capture['split'] == 'val', 'Wrong private frame')
        require(capture['stamp_ns'] == row['stamp_ns'] == scene['trajectory'][index]['stamp_ns'], 'Private/public time mismatch')
        require(capture['rgb_sha256'] == row['rgb_sha256'], 'Private/public RGB mismatch')
        poses.append(optical_pose(camera['matrix_world'], config['meters_per_blender_unit']))
        stamps.append(row['stamp_ns'])
    rows = generate_motion(poses, stamps, config, scene_name)
    model = public_model(config)
    validate_public_sensor_payload(rows, model)
    outputs = {'relative_motion.jsonl': ''.join(json.dumps(row, allow_nan=False)+'\n' for row in rows).encode('utf-8'),
               'sensor_model.json': json_bytes(model)}
    sensor_public = flight/'sensors_public'
    if sensor_public.exists():
        require(not sensor_public.is_symlink(), 'Sensor public symlink forbidden')
        existing = {p.relative_to(sensor_public).as_posix() for p in sensor_public.rglob('*') if p.is_file()}
        require(existing <= set(outputs), 'Unexpected file in sensor public directory')
        require(all(not p.is_symlink() for p in sensor_public.rglob('*')), 'Sensor symlink forbidden')
    result = dict(version='relative-sensor-export-private/1', passed=True, check_only=check_only,
        scene=scene_name, frames=len(frames), increments=len(rows), interval_seconds=0.25,
        sensor_seed=config['sensor_seed_by_scene'][scene_name], exact_pose_exported=False,
        sensor_protocol_sha256=sensor_protocol_sha256, campaign_protocol_sha256=protocol_sha256,
        exporter_sha256=sha(Path(__file__)), frozen_motion_contract_sha256=MOTION_SHA,
        validation_sha256=sha(validation_path), rgb_admission_sha256=sha(admission_path),
        private_source_hashes=source_hashes,
        output_hashes={name:hashlib.sha256(data).hexdigest() for name,data in outputs.items()},
        marker_pose_estimated=False, localization_performed=False,
        limitations=config['limitations'])
    # Verify source hashes again before committing any output; never repair a hash mismatch.
    for name, expected in source_hashes.items():
        require(sha(root/name) == expected, 'Private source changed during export')
    require(sha(protocol_path) == protocol_sha256 and sha(config_path) == sensor_protocol_sha256, 'Protocol changed during export')
    checked_public_files(public, read(admission_path))
    if not check_only:
        for name, payload in outputs.items():
            write_equal_or_new(sensor_public/name, payload)
        receipt = dict(version='public-relative-sensor-admission/1', passed=True,
            sensor_files=result['output_hashes'], rgb_frames_sha256=sha(public/'frames.json'),
            rgb_calibration_sha256=sha(public/'calibration.json'),
            marker_dimensions_sha256=sha(public/'marker_dimensions.json'))
        write_equal_or_new(flight/'sensors_public_admission_v1.json', json_bytes(receipt))
        write_equal_or_new(flight/'sensor_export_private_v1.json', json_bytes(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=HERE)
    parser.add_argument('--scene', choices=['legacy','vertical','orbit'], required=True)
    parser.add_argument('--protocol-sha256', required=True)
    parser.add_argument('--sensor-protocol-sha256', required=True)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    result = export(args.root.resolve(), args.scene, args.protocol_sha256, args.sensor_protocol_sha256, args.check_only)
    print(json.dumps({key:result[key] for key in ('passed','scene','frames','increments','interval_seconds','check_only')}, indent=2))
