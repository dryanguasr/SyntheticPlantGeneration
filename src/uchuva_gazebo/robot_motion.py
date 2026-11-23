"""Motion adapter sharing the resolved link graph and collision primitives.

Individual primitive bounding boxes conservatively contain cylinders/spheres;
they never join separate fingers, wheels or links across empty space.
"""
from __future__ import annotations

import math

from .robot_kinematics import (forward_kinematics, solve_ik, collision_shapes,
    pose_identity, compose_poses, inverse_pose, transform_point, rotate_vector)
from .robot_sdf import pose_rpy


class ResolvedMotionConfig:
    def __init__(self, robot, task, *, asset_root=None, mesh_repository=None):
        robot.require_capability('collision_primitives')
        if not isinstance(task, dict) or task.get('orientation_mode') != 'position_direction':
            raise ValueError('Resolved harvest requires explicit robot_task orientation_mode=position_direction')
        direction = task.get('target_direction')
        if not isinstance(direction, (list, tuple)) or len(direction) != 3 or any(
                type(v) not in (int, float) or not math.isfinite(v) for v in direction):
            raise ValueError('robot_task.target_direction requires three finite components')
        length = math.sqrt(sum(v*v for v in direction))
        if length < 1e-12:
            raise ValueError('robot_task.target_direction cannot be zero')
        self.robot, self.task = robot, dict(task)
        self.mesh_repository = mesh_repository
        geometries = [s['geometry'] for link in robot.links for s in link['collisions']
                      if s['geometry']['type'] == 'mesh']
        if geometries and mesh_repository is None:
            if asset_root is None:
                raise ValueError('Mesh collision planning requires an explicit verified asset root')
            from .robot_mesh_geometry import MeshRepository
            self.mesh_repository = MeshRepository(asset_root, geometries)
        self.direction = [v/length for v in direction]
        axis = task.get('tool_axis')
        if not isinstance(axis, (list, tuple)) or len(axis) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in axis) or abs(sum(v*v for v in axis)-1) > 1e-7:
            raise ValueError('robot_task.tool_axis must explicitly specify a unit vector in the tool frame')
        self.tool_axis = list(axis)
        tolerance = task.get('orientation_tolerance_rad')
        if type(tolerance) not in (int, float) or not math.isfinite(tolerance) or not 0 < tolerance < math.pi:
            raise ValueError('robot_task requires a preregistered positive orientation_tolerance_rad below pi')
        self.frame = task.get('tool_frame', 'tcp')
        by_name = {j['name']: j for j in robot.joints}
        self.joint_limits = [(by_name[n]['limits']['lower'], by_name[n]['limits']['upper']) for n in robot.joint_names]
        if self.frame not in {f['name'] for f in robot.frames}:
            raise ValueError(f'Unknown task frame: {self.frame}')
        self.aux_positions = dict(task.get('auxiliary_joint_positions', {}))
        missing = [j['name'] for j in robot.joints if j.get('group') in ('passive', 'gripper')
                   and j['name'] not in self.aux_positions]
        if missing:
            raise ValueError(f'Planning requires explicit passive/gripper joint positions: {missing}')

    def positions(self, values):
        if len(values) != len(self.robot.joint_names):
            raise ValueError('Resolved joint vector does not match the arm contract')
        return {**self.aux_positions, **dict(zip(self.robot.joint_names, values))}

    def for_direction(self, direction):
        return ResolvedMotionConfig(self.robot, {**self.task, 'target_direction': list(direction)},
                                    mesh_repository=self.mesh_repository)

    def for_observed_joints(self, positions):
        """Use measured passive/jaw coordinates in clearance, never stale zeros."""
        names = set(self.aux_positions)
        if not names <= positions.keys():
            raise ValueError('Missing observed passive/gripper joint state')
        return ResolvedMotionConfig(self.robot, {**self.task,
            'auxiliary_joint_positions': {n: positions[n] for n in names}}, mesh_repository=self.mesh_repository)

    def solve(self, target, pitch=0, roll=0, *, seed=None):
        if pitch != 0 or roll != 0:
            raise ValueError('Resolved IK uses the explicit task direction, not proxy Euler constraints')
        result = solve_ik(self.robot, target, target_direction=self.direction,
                          tool_frame=self.frame, tool_axis=self.tool_axis,
                          orientation_mode='position_direction', seed=seed)
        if not result.success:
            raise ValueError(f'Resolved robot IK failed: {result.reason}; position={result.position_error_m}, direction={result.direction_error_rad}')
        values = result.joint_positions
        return tuple(values[name] for name in self.robot.joint_names) if isinstance(values, dict) else tuple(values)

    def fk(self, values):
        pose = forward_kinematics(self.robot, self.positions(values))[self.frame]
        return {'position_m': pose['xyz_m'], 'rpy_rad': pose_rpy(pose)[3:],
                'quaternion_xyzw': pose['quaternion_xyzw']}

    def world_shapes(self, values, base):
        if len(base) == 4:
            base_pose = {'xyz_m': list(base[:3]), 'quaternion_xyzw': [0, 0, math.sin(base[3]/2), math.cos(base[3]/2)]}
        elif len(base) == 7:
            base_pose = {'xyz_m': list(base[:3]), 'quaternion_xyzw': list(base[3:])}
        else:
            raise ValueError('Base pose requires xyz/yaw or xyz/xyzw')
        poses = forward_kinematics(self.robot, self.positions(values), base_pose=base_pose)
        return collision_shapes(self.robot, poses), poses[self.frame]


def shape_box(shape):
    geometry = shape['geometry']
    kind = geometry['type']
    if kind == 'box':
        half = [v/2 for v in geometry['size_m']]
    elif kind == 'sphere':
        half = [geometry['radius_m']]*3
    elif kind == 'cylinder':
        half = [geometry['radius_m'], geometry['radius_m'], geometry['length_m']/2]
    else:
        raise ValueError(f'No conservative clearance adapter for robot geometry {kind}; supply traced primitive decomposition')
    return half


def box_separation(first, first_half, second, second_half):
    """Conservative separation using all 15 oriented-box SAT directions.

    A positive projection gap is a lower bound on Euclidean separation. A
    nonpositive result cannot certify clearance, including degenerate axes.
    """
    axes = [[rotate_vector(row['pose']['quaternion_xyzw'], [int(i == j) for i in range(3)]) for j in range(3)] for row in (first, second)]
    directions = axes[0]+axes[1]
    for a in axes[0]:
        for b in axes[1]:
            directions.append([a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]])
    delta = [b-a for a, b in zip(first['pose']['xyz_m'], second['pose']['xyz_m'])]
    gaps = []
    for axis in directions:
        norm = math.sqrt(sum(v*v for v in axis))
        if norm < 1e-12:
            continue
        axis = [v/norm for v in axis]
        radii = [sum(h*abs(sum(a*b for a, b in zip(axis, basis))) for h, basis in zip(half, basis_set))
                 for half, basis_set in zip((first_half, second_half), axes)]
        gaps.append(abs(sum(a*b for a, b in zip(delta, axis)))-sum(radii))
    return max(gaps)


def resolved_world_clearance(values, base, cylinders, fruits, held, config, report_cap=.5):
    from .harvest_clearance import _segment_box_distance, _point_box_distance, _point_segment_distance
    shapes, tcp = config.world_shapes(values, base)
    repository = config.mesh_repository
    boxes = [(s, None if s['geometry']['type'] == 'mesh' else shape_box(s), inverse_pose(s['pose'])) for s in shapes]
    if any(half is None for _, half, _ in boxes) and repository is None:
        raise ValueError('Mesh clearance requires its verified geometry repository')
    # These enclosures only reject pairs that cannot improve the current
    # minimum. Every potentially limiting mesh pair still uses its triangles.
    bounds = ([repository.conservative_world_bounds(shape) for shape in shapes]
              if repository is not None else None)
    minimum, held_min, held_robot_min = report_cap, report_cap, report_cap
    limiting = limiting_held = limiting_held_robot = None
    drive_links = {j['child'] for j in config.robot.joints if j.get('group') == 'drive'}
    exclusions = {tuple(sorted(row['links'])) for row in config.robot.data['collision_policy']['excluded_pairs']}
    for index, (first, first_half, _) in enumerate(boxes):
        for second_index in range(index+1, len(boxes)):
            second, second_half, _ = boxes[second_index]
            pair = tuple(sorted((first['link'], second['link'])))
            if first['link'] == second['link'] or pair in exclusions:
                continue
            if first_half is None or second_half is None:
                a, b = bounds[index], bounds[second_index]
                lower_bound = math.sqrt(sum(max(a[0][i]-b[1][i], b[0][i]-a[1][i], 0)**2
                                            for i in range(3)))
                if lower_bound >= minimum:
                    continue
                gap = repository.shape_distance(first, second, limit=minimum)
            else:
                gap = box_separation(first, first_half, second, second_half)
            if gap < minimum:
                minimum, limiting = gap, [first['link']+'/'+first['name'], second['link']+'/'+second['name']]
    for shape, half, inverse in boxes:
        name = shape['link']+'/'+shape['name']
        center = shape['pose']['xyz_m']
        if half is None:
            low, high = repository.world_bounds(shape)
            center = [(a+b)/2 for a,b in zip(low, high)]
            bound = math.dist(low, high)/2
        else:
            bound = math.sqrt(sum(v*v for v in half))
        # A previous penetration must not shrink the spatial query inside the
        # body: deeper intersections still contribute to the reported minimum.
        nearby = cylinders.near(center, bound+max(0, minimum)) if hasattr(cylinders, 'near') else cylinders
        for obstacle in nearby:
            gap = (repository.segment_distance(shape, obstacle['start'], obstacle['end'],
                                                limit=max(0, minimum+obstacle['radius']))
                   if half is None else _segment_box_distance(transform_point(inverse, obstacle['start']),
                   transform_point(inverse, obstacle['end']), half))-obstacle['radius']
            if gap < minimum:
                minimum, limiting = gap, [name, obstacle['id']]
        for fruit in fruits:
            if held is not None and fruit['id'] == held['id']:
                continue
            gap = (repository.point_distance(shape, fruit['center_world_m'],
                                              limit=max(0, minimum+fruit['radius_m'])) if half is None
                   else _point_box_distance(transform_point(inverse, fruit['center_world_m']), half))-fruit['radius_m']
            if gap < minimum:
                minimum, limiting = gap, [name, fruit['id']]
        if shape['link'] not in drive_links:
            if half is None:
                gap = low[2]
            else:
                axes = [rotate_vector(shape['pose']['quaternion_xyzw'], [int(i==j) for i in range(3)]) for j in range(3)]
                gap = center[2]-sum(abs(axis[2])*h for axis, h in zip(axes, half))
            if gap < minimum:
                minimum, limiting = gap, [name, 'ground']
    if held is not None:
        # The original offset is expressed in the CUT posture's tool frame,
        # rather than rotating a world-space vector as if wrist roll were zero.
        if 'held_offset_in_tool_m' not in held:
            raise ValueError('Resolved held clearance requires the audited cut-frame attachment offset')
        center = transform_point(tcp, held['held_offset_in_tool_m'])
        radius = held['radius_m']
        held_min, limiting_held = min(report_cap, center[2]-radius), 'ground'
        nearby = cylinders.near(center, radius+max(0, held_min)) if hasattr(cylinders, 'near') else cylinders
        for obstacle in nearby:
            gap = _point_segment_distance(center, obstacle['start'], obstacle['end'])-radius-obstacle['radius']
            if gap < held_min:
                held_min, limiting_held = gap, obstacle['id']
        for fruit in fruits:
            if fruit['id'] != held['id']:
                gap = math.dist(center, fruit['center_world_m'])-radius-fruit['radius_m']
                if gap < held_min:
                    held_min, limiting_held = gap, fruit['id']
        for shape, half, inverse in boxes:
            gap = (repository.point_distance(shape, center,
                                              limit=max(0, held_robot_min+radius)) if half is None
                   else _point_box_distance(transform_point(inverse, center), half))-radius
            if gap < held_robot_min:
                held_robot_min, limiting_held_robot = gap, shape['link']+'/'+shape['name']
    return {'robot_clearance_m': minimum, 'held_clearance_m': held_min if held else None,
            'held_robot_clearance_m': held_robot_min if held else None,
            'limiting_robot_pair': limiting, 'limiting_held_obstacle': limiting_held,
            'limiting_held_robot_link': limiting_held_robot, 'tcp_world_m': tcp['xyz_m'],
            'robot_spec_sha256': config.robot.sha256}
