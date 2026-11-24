#!/usr/bin/env python3
"""Prove arm clearance at the native joint-position samples of a V8 take."""

import argparse
from bisect import bisect_right
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from uchuva_gazebo.elbow_up_clearance import ElbowUpClearance
from uchuva_gazebo.harvest_pilot import sha256_file
from uchuva_gazebo.robot_spec import resolve_robot_profile


def _interval_at(times, stamp):
    return min(len(times) - 2, max(0, bisect_right(times, stamp) - 1))


def planned_state(times, rows, stamp, *, index=None):
    if index is None:
        index = _interval_at(times, stamp)
    a, b = rows[index:index + 2]
    u = min(1., max(0., (stamp - times[index]) / (times[index + 1] - times[index])))
    blend = u * u * u * (10. + u * (-15. + 6. * u))
    return [first + blend * (last - first) for first, last in zip(a, b)]


def _follow_rows(stream, capture_receipt):
    """Read flushed joint samples while the native capture owns the writer."""
    receipt = json.loads(capture_receipt.read_bytes())
    end = time.monotonic() + receipt['maximum_wall_seconds'] + 120.
    while True:
        position = stream.tell()
        line = stream.readline()
        if line.endswith('\n'):
            yield line
            continue
        try:
            status = json.loads(capture_receipt.read_bytes())['status']
        except json.JSONDecodeError:
            status = 'CAPTURING'
        stream.seek(position)
        if status in ('CAPTURED', 'FAILED'):
            yield from stream
            return
        if time.monotonic() >= end:
            raise TimeoutError('Native capture receipt did not reach a terminal status')
        time.sleep(.2)


def check_motion(clearance, times, poses, native, nominal_margin, *, interval_bounds=None,
                 require_nominal_clearance=False, follow_run=None):
    failures = []
    rows = exact_count = cached_count = 0
    first = last = minimum_gap = minimum_fold = None
    maximum_loss = maximum_gap = 0.
    max_error = [0.] * len(clearance.coordinates)
    required = nominal_margin if require_nominal_clearance else 1e-9
    anchor = None
    with native.open(encoding='utf-8') as stream:
        samples = _follow_rows(stream, follow_run) if follow_run is not None else iter(stream)
        header = next(samples, '').split()
        indices = [header.index(f'{name}_position') for name in clearance.coordinates]
        for line in samples:
            tokens = line.split()
            if len(tokens) != len(header):
                failures.append({'row': rows + 2, 'reason': 'incomplete_native_sample'})
                continue
            stamp = float(tokens[0])
            actual = [float(tokens[index]) for index in indices]
            if not math.isfinite(stamp) or not all(map(math.isfinite, actual)):
                failures.append({'row': rows + 2, 'reason': 'nonfinite_native_pose'})
                continue
            if stamp < 0 or (last is not None and stamp <= last):
                failures.append({'row': rows + 2, 'reason': 'invalid_sim_time', 'sim_time': stamp})
                continue
            first = stamp if first is None else first
            if last is not None:
                maximum_gap = max(maximum_gap, stamp - last)
            last = stamp
            rows += 1
            index = _interval_at(times, stamp)
            nominal = planned_state(times, poses, stamp, index=index)
            loss = clearance.observed_distance_loss_bound(nominal, actual)
            maximum_loss = max(maximum_loss, loss)
            max_error = [max(recorded, abs(a - b))
                         for recorded, a, b in zip(max_error, nominal, actual)]
            fold = clearance.straight_elbow_rad - actual[clearance.elbow_index]
            minimum_fold = fold if minimum_fold is None else min(minimum_fold, fold)
            if fold <= 0:
                failures.append({'sim_time': stamp, 'reason': 'observed_elbow_branch',
                                 'elbow_up_margin_rad': fold})
            planned_gap = nominal_margin if interval_bounds is None else interval_bounds[index]
            gap = planned_gap - loss
            if gap < required and anchor is not None:
                anchor_pose, anchor_gap = anchor
                gap = max(gap, anchor_gap - clearance.observed_distance_loss_bound(anchor_pose, actual))
                cached_count += gap >= required
            if gap < required:
                exact_count += 1
                result = clearance.observed_pose(actual[:-1], actual[-1], clearance=required,
                                                 extra_query_m=.005 if require_nominal_clearance else 0.)
                if not result['passed']:
                    failures.append({**result, 'sim_time': stamp,
                                     'arm_joints_rad': actual[:-1], 'jaw_m': actual[-1]})
                    continue
                gap = result['clearance_lower_bound_m']
                anchor = actual, gap
            minimum_gap = gap if minimum_gap is None else min(minimum_gap, gap)
    # The recorder normally samples every 50–52 ms. Missing observations
    # cannot confirm the corresponding part of a native run.
    if rows < 2 or not (first <= .06 and last >= times[-1] - .06 and maximum_gap <= .060000001):
        failures.append({'reason': 'incomplete_native_coverage'})
    return {
        'passed': not failures, 'scope': 'sampled_native_joint_positions',
        'samples': rows, 'first_sim_s': first, 'last_sim_s': last,
        'maximum_sample_gap_s': maximum_gap, 'exact_pose_fallbacks': exact_count,
        'cached_pose_certificate_hits': cached_count, 'required_clearance_m': required,
        'minimum_clearance_lower_bound_m': minimum_gap,
        'maximum_loss_bound_from_nominal_m': maximum_loss,
        'max_deviation_from_planned_coordinates': dict(zip(clearance.coordinates, max_error)),
        'minimum_elbow_up_margin_rad': minimum_fold, 'failures': failures,
    }


def audit(package, source_package, *, require_nominal_clearance=False, follow_run=None):
    manifest = json.loads((package / 'demo_manifest.json').read_bytes())
    files = manifest['files_sha256']
    proof_path = package / manifest['elbow_up_clearance']
    plan_path = package / 'trajectory.tsv'
    for path in (proof_path, plan_path):
        if not path.resolve().is_relative_to(package.resolve()) or sha256_file(path) != files[path.name]:
            raise ValueError(f'Take artefact differs from its frozen digest: {path.name}')
    proof = json.loads(proof_path.read_bytes())
    planned = [[float(value) for value in line.split()] for line in plan_path.read_text().splitlines()]
    times = [row[0] for row in planned]
    margin = proof['clearance_m']
    if (not proof['passed'] or not math.isfinite(margin) or margin <= 0
            or times[0] != 0 or len(proof['intervals']) != len(times) - 1
            or any(b <= a or not row['passed'] or row['clearance_lower_bound_m'] < margin - 1e-12
                   or abs(row['start_sim_s'] - a) > 1e-9 or abs(row['end_sim_s'] - b) > 1e-9
                   for a, b, row in zip(times, times[1:], proof['intervals']))):
        raise ValueError('Nominal clearance does not cover the complete frozen trajectory')

    source = source_package if source_package is not None else Path(manifest['source_package'])
    source_manifest = source / 'manifest.json'
    if sha256_file(source_manifest) != manifest['source_manifest_sha256']:
        raise ValueError('Different frozen CAD source package')
    contents = json.loads(source_manifest.read_bytes())
    robot = resolve_robot_profile(contents['robot_config'])
    clearance = ElbowUpClearance(robot, contents['robot_task'], asset_root=source)
    if (robot.sha256 != proof['robot_spec_sha256']
            or len(clearance.arm_chassis_pairs) != proof['arm_chassis_pairs']):
        raise ValueError('Nominal certificate does not match the CAD clearance pair set')
    poses = [row[5:5 + len(clearance.coordinates)] for row in planned]
    native = package / 'native_motion.tsv'
    result = check_motion(clearance, times, poses, native, margin,
                          interval_bounds=[row['clearance_lower_bound_m'] for row in proof['intervals']],
                          require_nominal_clearance=require_nominal_clearance, follow_run=follow_run)
    result['trajectory_sha256'] = files[plan_path.name]
    result['nominal_proof_sha256'] = files[proof_path.name]
    result['native_motion_sha256'] = sha256_file(native)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--source-package', type=Path)
    parser.add_argument('--require-nominal-clearance', action='store_true',
                        help='Prove the nominal millimetre threshold at every native configuration')
    parser.add_argument('--follow-run', type=Path, metavar='RUN_JSON',
                        help='Read flushed samples until the capture receipt reaches a terminal state')
    args = parser.parse_args()
    result = audit(args.package, args.source_package,
                   require_nominal_clearance=args.require_nominal_clearance, follow_run=args.follow_run)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
