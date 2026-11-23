#!/usr/bin/env python3
"""Fixed-base CAD mass matrix and gravity load; no hardware identification.

The Jacobian energy calculation includes every descendant rigid body's CAD
mass, COM and rotated inertia. It ignores compliance, actuator inertia,
friction, payloads absent from the profile and Coriolis terms.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))
from uchuva_gazebo.robot_spec import resolve_robot_profile
from uchuva_gazebo.robot_kinematics import (
    forward_kinematics, compose_poses, rotate_vector, transform_point,
)


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def arm_dynamics(robot, positions=None, gravity=(0, 0, -9.81)):
    data = robot.to_dict()
    poses = forward_kinematics(robot, positions)
    by_child = {row['child']: row for row in data['joints']}
    joints = {row['name']: row for row in data['joints']}
    names = list(robot.joint_names)
    n = len(names)
    matrix = [[0.0]*n for _ in names]
    load = [0.0]*n
    axes, origins = {}, {}
    for name in names:
        row = joints[name]
        pose = compose_poses(poses[row['parent']], row['origin'])
        axes[name] = rotate_vector(pose['quaternion_xyzw'], row['axis'])
        origins[name] = pose['xyz_m']
    for body in data['links']:
        ancestors, current = set(), body['name']
        while current in by_child:
            row = by_child[current]
            ancestors.add(row['name'])
            current = row['parent']
        inertia = body['inertial']
        mass = inertia['mass_kg']
        pose = poses[body['name']]
        center = transform_point(pose, inertia['com_m'])
        xx, yy, zz, xy, xz, yz = inertia['tensor_kg_m2']
        tensor = [[xx, xy, xz], [xy, yy, yz], [xz, yz, zz]]
        q = pose['quaternion_xyzw']
        inverse_q = [-q[0], -q[1], -q[2], q[3]]
        linear, angular_local = [], []
        for name in names:
            if name not in ancestors:
                linear.append([0.0]*3)
                angular_local.append([0.0]*3)
            elif joints[name]['type'] == 'revolute':
                linear.append(cross(axes[name], [a-b for a, b in zip(center, origins[name])]))
                angular_local.append(rotate_vector(inverse_q, axes[name]))
            elif joints[name]['type'] == 'prismatic':
                linear.append(axes[name])
                angular_local.append([0.0]*3)
            else:
                raise ValueError('Arm generalized coordinate must be movable')
        for i in range(n):
            load[i] -= mass * dot(linear[i], gravity)
            for j in range(n):
                inertia_times_axis = [dot(row, angular_local[j]) for row in tensor]
                matrix[i][j] += mass*dot(linear[i], linear[j])+dot(angular_local[i], inertia_times_axis)
    return {'joint_names': names, 'mass_matrix': matrix,
            'gravity_compensation_effort': dict(zip(names, load)),
            'locked_other_joints_inertia': dict(zip(names, [matrix[i][i] for i in range(n)]))}


def report(robot):
    zero = {name: 0.0 for name in robot.joint_names}
    rows = {row['name']: row for row in robot.to_dict()['joints']}
    # Finite samples are explicitly not a certified continuous extremum.
    points = [[rows[name]['limits']['lower'], 0, rows[name]['limits']['upper']]
              for name in robot.joint_names]
    peaks = {name: {'absolute_effort': 0.0, 'positions': None} for name in robot.joint_names}
    for values in itertools.product(*points):
        positions = dict(zip(robot.joint_names, values))
        for name, value in arm_dynamics(robot, positions)['gravity_compensation_effort'].items():
            if abs(value) > peaks[name]['absolute_effort']:
                peaks[name] = {'absolute_effort': abs(value), 'positions': positions}
    return {'schema_version': 'fixed-base-arm-dynamics/1.0', 'robot_spec_sha256': robot.sha256,
            'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'scope': 'CAD rigid-body fixed-base estimate, gravity 9.81 m/s2; no hardware torque or continuous rating inferred.',
            'zero': arm_dynamics(robot, zero), 'sampled_gravity_extrema': peaks,
            'sample_count': 3**len(robot.joint_names),
            'sampling': 'Declared lower/zero/upper product. Finite samples, not a guaranteed bound.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = report(resolve_robot_profile(args.profile))
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps(result['zero'], indent=2))


if __name__ == '__main__':
    main()
