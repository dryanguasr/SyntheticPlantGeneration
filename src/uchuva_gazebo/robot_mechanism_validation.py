"""Independent observed closure/gear audits; FK tree agreement is insufficient."""
from __future__ import annotations

import math

SUSPENSION_POSITION_TOLERANCE_M = .001
GRIPPER_POSITION_TOLERANCE_M = .0005
CLOSURE_ROTATION_TOLERANCE_RAD = .001
GEAR_COORDINATE_TOLERANCE_RAD = .001


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _observed_pose(value):
    xyz, q = value['xyz_m'], value['quaternion_xyzw']
    if len(xyz) != 3 or len(q) != 4 or not all(_finite(v) for v in [*xyz,*q]):
        raise ValueError('Invalid native mechanism pose')
    if abs(sum(v*v for v in q)-1) > 1e-6:
        raise ValueError('Native mechanism quaternion is not unit length')
    return xyz, q


def audit_mechanism_sample(robot, joint_positions, link_poses):
    """Compare native physical body/auxiliary poses and measured gear q.

    Poses must share one coordinate frame. No predicted FK poses or commanded
    joint values may be substituted by callers for missing observations.
    """
    data = robot.to_dict()
    closures, gears, failures = [], [], []
    for row in data.get('closures', []):
        body, auxiliary = row['body'], row['auxiliary']
        if body not in link_poses or auxiliary not in link_poses:
            failures.append(row['name']+': native body/auxiliary observation missing')
            continue
        a, aq = _observed_pose(link_poses[body])
        b, bq = _observed_pose(link_poses[auxiliary])
        position = math.dist(a, b)
        cosine = abs(sum(x*y for x,y in zip(aq,bq)))/math.sqrt(sum(x*x for x in aq)*sum(x*x for x in bq))
        rotation = 2*math.acos(min(1.0,cosine))
        if body.startswith('carrier_'):
            tolerance = SUSPENSION_POSITION_TOLERANCE_M
        elif body.startswith('gripper_'):
            tolerance = GRIPPER_POSITION_TOLERANCE_M
        else:
            raise ValueError('Closure lacks an explicit frozen diagnostic category: '+body)
        passed = position <= tolerance and rotation <= CLOSURE_ROTATION_TOLERANCE_RAD
        closures.append({'name': row['name'], 'body': body, 'auxiliary': auxiliary,
            'position_error_m': position, 'orientation_error_rad': rotation,
            'position_tolerance_m': tolerance, 'orientation_tolerance_rad': CLOSURE_ROTATION_TOLERANCE_RAD,
            'passed': passed})
        if not passed:
            failures.append(row['name']+': observed closure residual exceeds frozen threshold')
    for row in data.get('gear_couplings', []):
        driver, follower = joint_positions.get(row['driver']), joint_positions.get(row['follower'])
        if not _finite(driver) or not _finite(follower):
            failures.append(row['name']+': native gear coordinate missing or nonfinite')
            continue
        error = follower-row['ratio']*driver-row['offset']
        passed = abs(error) <= GEAR_COORDINATE_TOLERANCE_RAD
        gears.append({'name': row['name'], 'driver_position_rad': driver, 'follower_position_rad': follower,
                      'coordinate_error_rad': error, 'tolerance_rad': GEAR_COORDINATE_TOLERANCE_RAD,
                      'passed': passed})
        if not passed:
            failures.append(row['name']+': observed gear residual exceeds frozen threshold')
    return {'passed': not failures, 'closures': closures, 'gears': gears, 'failures': failures}


def audit_passive_gear_commands(robot, telemetry):
    """The passive gear may transmit constraint effort but no motor command."""
    data = robot.to_dict()
    if telemetry.get('robot_spec_sha256') != robot.sha256:
        raise ValueError('Native telemetry belongs to another robot profile')
    rows = telemetry.get('joints', [])
    observed = {row['name']: row for row in rows}
    if len(observed) != len(rows):
        raise ValueError('Duplicate native joint observation')
    followers, failures = [], []
    for gear in data.get('gear_couplings', []):
        name = gear['follower']
        row = observed.get(name)
        if row is None:
            failures.append(name+': passive follower observation missing')
            continue
        command = row.get('force_command') if row.get('force_command_available') else 0.0
        maximum = row.get('max_abs_force_command_window')
        passed = _finite(command) and _finite(maximum) and abs(command) <= 1e-12 and abs(maximum) <= 1e-12
        followers.append({'name':name,'motor_command':command,'maximum_motor_command_window':maximum,'passed':passed})
        if not passed:
            failures.append(name+': passive follower contains a motor command')
    return {'passed':not failures,'followers':followers,'failures':failures}
