"""Certify CAD arm clearance throughout the prescribed demonstration motion."""

from __future__ import annotations

from itertools import combinations
import math

from .robot_kinematics import (
    compose_poses,
    forward_kinematics,
    pose_identity,
    rotate_vector,
)
from .robot_mesh_geometry import MeshRepository


def _dot(first, second):
    return sum(a * b for a, b in zip(first, second))


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]]


def _box_gap(first, second):
    return math.sqrt(sum(max(a - d, c - b, 0.) ** 2
                         for a, b, c, d in zip(*first, *second)))


def _maximal_weights(pairs):
    """Discard weights that never give the largest bound for nonnegative travel."""
    vectors = {weights for _, _, weights in pairs}
    return tuple(weights for weights in vectors if not any(
        other != weights and all(a >= b for a, b in zip(other, weights)) for other in vectors))


class ElbowUpClearance:
    """Check all CAD arm-to-car pairs and optionally nonadjacent arm pairs.

    The root pose cancels for this check. The demonstration locks passive
    suspension at its declared coordinates, and centered circular tires are
    invariant to axle rotation. Both assertions describe the prepared take;
    this checker does not certify suspension motion or clearance to the crop.
    """

    def __init__(self, robot, task, *, asset_root=None, mesh_repository=None):
        self.robot = robot
        data = robot.to_dict()
        joints = {joint['name']: joint for joint in data['joints']}
        self.jaw = task['demo_fixture']['gripper']['joint']
        self.defaults = dict(task['auxiliary_joint_positions'])
        self.coordinates = (*robot.joint_names, self.jaw)
        self.joint_limits = tuple(joints[name]['limits'] for name in self.coordinates)
        self.elbow_index = self.coordinates.index('arm_elbow_joint')
        by_child = {joint['child']: joint for joint in data['joints']}
        self.shapes = tuple({**shape, 'link': link['name']}
                            for link in data['links'] for shape in link['collisions'])
        self.meshes = mesh_repository if mesh_repository is not None else MeshRepository(
            asset_root, (shape['geometry'] for shape in self.shapes))
        links = {shape['link'] for shape in self.shapes}
        paths = {}
        for link in links:
            branch = []
            current = link
            while current in by_child:
                edge = by_child[current]
                branch.append(edge)
                current = edge['parent']
            paths[link] = tuple(reversed(branch))
        self._check_wheel_invariance(joints.values(), paths)

        mount = joints[robot.joint_names[0]]['parent']
        arm_links = {link for link, path in paths.items()
                     if link == mount or any(edge['parent'] == mount for edge in path)}
        self.names = tuple(f"{shape['link']}/{shape['name']}" for shape in self.shapes)
        radii = tuple(self._motion_radii(shape, paths[shape['link']]) for shape in self.shapes)
        excluded = {frozenset(pair['links']) for pair in data['collision_policy']['excluded_pairs']}
        vehicle_pairs, arm_pairs = [], []
        for first, second in combinations(range(len(self.shapes)), 2):
            left, right = self.shapes[first], self.shapes[second]
            a, b = left['link'], right['link']
            if a == b or (a not in arm_links and b not in arm_links):
                continue
            if frozenset((a, b)) in excluded:
                if a in arm_links and b in arm_links:
                    continue
                # The mounting interface exempts the original CAD chassis
                # member only, not the basket or the hardware added to it.
                fixed = right if a in arm_links else left
                if fixed['link'] == data['root_link'] and fixed['name'].startswith('rigid_mesh_'):
                    continue
            distance_weights = tuple(
                (radii[first].get(name, 0.) + radii[second].get(name, 0.))
                if (name in radii[first]) != (name in radii[second]) else 0.
                for name in self.coordinates)
            pair = first, second, distance_weights
            (arm_pairs if a in arm_links and b in arm_links else vehicle_pairs).append(pair)
        # Basket pairs first gives planning queries short witnesses for
        # typical low-deposit failures without changing the proof.
        vehicle_pairs.sort(key=lambda p: not any('/basket_' in self.names[i] for i in p[:2]))
        self._vehicle_pairs = tuple(vehicle_pairs)
        self._all_pairs = self._vehicle_pairs + tuple(arm_pairs)
        self._vehicle_weights = _maximal_weights(self._vehicle_pairs)
        self._all_weights = _maximal_weights(self._all_pairs)
        self.arm_chassis_pairs = tuple((self.names[a], self.names[b])
                                       for a, b, _ in self._vehicle_pairs)
        self._static_shapes = {}
        defaults = self._frames([0.] * len(self.coordinates))
        for i, shape in enumerate(self.shapes):
            if not radii[i]:
                self._static_shapes[i] = self._placed_shape(shape, defaults)
        self.straight_elbow_rad = self._straight_elbow(joints)

    def _check_wheel_invariance(self, joints, paths):
        for joint in joints:
            if joint.get('group') != 'drive':
                continue
            if joint['type'] != 'revolute':
                raise ValueError(f"Cannot omit drive motion for {joint['name']}: no revolute axle")
            for shape in self.shapes:
                if not any(edge['name'] == joint['name'] for edge in paths[shape['link']]):
                    continue
                local = compose_poses(joint['child_pose'], shape['pose'])
                axis = rotate_vector(local['quaternion_xyzw'], [0., 0., 1.])
                if (shape['link'] != joint['child'] or shape['geometry']['type'] != 'cylinder'
                        or math.hypot(*_cross(axis, joint['axis'])) > 1e-9
                        or math.hypot(*_cross(local['xyz_m'], joint['axis'])) > 1e-9):
                    raise ValueError(f"Cannot omit tire spin for {joint['name']}: no axial symmetry")

    def _straight_elbow(self, joints):
        elbow, wrist = joints['arm_elbow_joint'], joints['wrist_pitch_joint']
        shoulder = joints['arm_shoulder_joint']
        frames = self._frames([0.] * len(self.coordinates))
        shoulder_pose, elbow_pose, wrist_pose = [
            compose_poses(frames[joint['parent']], joint['origin']) for joint in (shoulder, elbow, wrist)]
        axis = rotate_vector(elbow_pose['quaternion_xyzw'], elbow['axis'])
        positions = [pose['xyz_m'] for pose in (shoulder_pose, elbow_pose, wrist_pose)]
        upper, lower = ([b - a for a, b in zip(first, second)]
                        for first, second in zip(positions, positions[1:]))
        upper, lower = ([a - _dot(vector, axis) * b for a, b in zip(vector, axis)]
                        for vector in (upper, lower))
        return -math.atan2(_dot(axis, _cross(upper, lower)), _dot(upper, lower))

    def _motion_radii(self, shape, path):
        box = self.meshes.conservative_world_bounds(
            {'geometry': shape['geometry'], 'pose': pose_identity()})
        reach = math.hypot(*shape['pose']['xyz_m']) + math.hypot(
            *(max(abs(a), abs(b)) for a, b in zip(*box)))
        radii = {}
        for edge in reversed(path):
            reach += math.hypot(*edge['child_pose']['xyz_m'])
            name = edge['name']
            if name in self.coordinates:
                radii[name] = 1. if edge['type'] == 'prismatic' else reach
            if edge['type'] == 'prismatic':
                q_values = (edge['limits']['lower'], edge['limits']['upper']) if name in self.coordinates else (
                    self.defaults.get(name, 0.),)
                reach += max(abs(q + edge['zero_offset']) for q in q_values)
            reach += math.hypot(*edge['origin']['xyz_m'])
        return radii

    def _frames(self, state, *, within_limits=True):
        return forward_kinematics(self.robot, {**self.defaults, **dict(zip(self.coordinates, state))},
                                  check_limits=within_limits)

    def _state(self, q, jaw, *, within_limits=True):
        positions = (*q, self.defaults[self.jaw] if jaw is None else jaw)
        if len(positions) != len(self.coordinates) or not all(map(math.isfinite, positions)):
            raise ValueError('Invalid arm or jaw coordinates for the CAD model')
        if within_limits and any(not limit['lower'] - 1e-12 <= value <= limit['upper'] + 1e-12
                                 for value, limit in zip(positions, self.joint_limits)):
            raise ValueError('Planned arm or jaw coordinate outside the CAD limits')
        return positions

    def _placed_shape(self, shape, frames):
        result = {**shape, 'pose': compose_poses(frames[shape['link']], shape['pose'])}
        return result, self.meshes.conservative_world_bounds(result)

    def _sample(self, state, pairs, clearance, span, *, within_limits=True, extra_query_m=0.):
        frames = self._frames(state, within_limits=within_limits)
        placements = self._static_shapes.copy()
        unresolved = []
        bound = math.inf
        for a, b, motion in pairs:
            radius = motion * span
            cutoff = clearance + radius + 1e-12
            for index in (a, b):
                if index not in placements:
                    placements[index] = self._placed_shape(self.shapes[index], frames)
            first, first_box = placements[a]
            second, second_box = placements[b]
            gap = _box_gap(first_box, second_box)
            # Split coarse sweeps instead of requesting the exact distance
            # between every CAD mesh in a large motion enclosure.
            query_limit = min(cutoff + extra_query_m, clearance + .025)
            if gap < query_limit:
                gap = self.meshes.shape_distance(first, second, limit=query_limit)
            if gap < clearance:
                return {'passed': False, 'reason': 'arm_geometry',
                        'pair': [self.names[a], self.names[b]], 'distance_m': gap}, [], None
            if gap < cutoff:
                unresolved.append((a, b, motion))
            else:
                bound = min(bound, gap - radius)
        return None, unresolved, bound

    def pose(self, q, jaw=None, *, clearance=.004, check_branch=True, arm_self=True):
        return self.segment(q, q, jaw, jaw, clearance=clearance, check_branch=check_branch,
                            arm_self=arm_self)

    def observed_pose(self, q, jaw, *, clearance=1e-9, arm_self=True, extra_query_m=0.):
        """Direct geometry check of a measured configuration, including slight joint drift."""
        state = self._state(q, jaw, within_limits=False)
        selected = self._all_pairs if arm_self else self._vehicle_pairs
        pairs = tuple((i, j, 0.) for i, j, _ in selected)
        failure, unresolved, bound = self._sample(
            state, pairs, clearance, 0., within_limits=False, extra_query_m=extra_query_m)
        if failure:
            return failure
        if unresolved:
            i, j, _ = unresolved[0]
            return {'passed': False, 'reason': 'uncertified_clearance',
                    'pair': [self.names[i], self.names[j]]}
        return {'passed': True, 'clearance_lower_bound_m': bound, 'pair': None}

    def observed_distance_loss_bound(self, first, second, *, arm_self=True):
        """Bound worst clearance loss between two poses, including readback drift."""
        first = self._state(first[:-1], first[-1], within_limits=False)
        second = self._state(second[:-1], second[-1], within_limits=False)
        limits = self.joint_limits[-1]
        jaws = [min(limits['upper'], max(limits['lower'], pose[-1])) for pose in (first, second)]
        # Revolute radius bounds cover angles outside the configured stops;
        # handle an out-of-range prismatic drift by clipping each endpoint
        # and adding its distance to the certified range.
        travel = [abs(b - a) for a, b in zip(first[:-1], second[:-1])]
        travel.append(abs(jaws[1] - jaws[0]))
        weights = self._all_weights if arm_self else self._vehicle_weights
        overrun = abs(first[-1] - jaws[0]) + abs(second[-1] - jaws[1])
        return max((_dot(weight, travel) for weight in weights), default=0.) + overrun

    def segment(self, start, end, jaw_start=None, jaw_end=None, *, clearance=.004,
                check_branch=True, arm_self=True, max_depth=16):
        """Certify an affine joint segment, including monotone quintic replay.

        For each pair, its separation can decrease from the interval midpoint
        by at most the sum of the two sets' vertex displacements. Revolute
        contributions are angular travel times an upper radius from that
        axis; prismatic contributions are linear travel. Shared ancestor
        motion is a rigid transform of both bodies and cancels. Any interval
        whose lower bound is inconclusive is split rather than admitted.
        """
        if not math.isfinite(clearance) or clearance <= 0:
            raise ValueError('Clearance must be finite and positive')
        a, b = self._state(start, jaw_start), self._state(end, jaw_end)
        elbow_margin = self.straight_elbow_rad - max(a[self.elbow_index], b[self.elbow_index])
        if check_branch and elbow_margin < math.radians(1):
            return {'passed': False, 'reason': 'elbow_branch', 'pair': None,
                    'elbow_up_margin_rad': elbow_margin,
                    'fraction': float(b[self.elbow_index] > a[self.elbow_index])}
        delta = [last - first for first, last in zip(a, b)]
        travel = tuple(abs(value) for value in delta)
        selected = self._all_pairs if arm_self else self._vehicle_pairs
        pairs = tuple((i, j, _dot(radius, travel)) for i, j, radius in selected)
        pending = [(0., 1., 0, pairs)]
        samples, bound = 0, math.inf
        while pending:
            lo, hi, depth, active = pending.pop()
            u = (lo + hi) / 2
            state = [value + u * change for value, change in zip(a, delta)]
            failure, missing, lower = self._sample(state, active, clearance, (hi - lo) / 2)
            samples += 1
            witness = {'fraction': u, 'arm_joints_rad': state[:-1], 'jaw_m': state[-1]}
            if failure:
                return {**failure, **witness, 'evaluated_midpoints': samples}
            bound = min(bound, lower)
            if not missing:
                continue
            if depth == max_depth or not any(delta):
                i, j, _ = missing[0]
                return {'passed': False, 'reason': 'uncertified_clearance',
                        'pair': [self.names[i], self.names[j]], **witness,
                        'fraction_interval': [lo, hi], 'evaluated_midpoints': samples}
            pending.extend(((u, hi, depth + 1, missing), (lo, u, depth + 1, missing)))
        return {'passed': True, 'reason': None, 'pair': None, 'clearance_lower_bound_m': bound,
                'elbow_up_margin_rad': elbow_margin, 'evaluated_midpoints': samples}
