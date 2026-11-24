"""Motion adapter sharing the resolved link graph and collision primitives.

Individual primitive bounding boxes conservatively contain cylinders/spheres;
they never join separate fingers, wheels or links across empty space.
"""
from __future__ import annotations

import math
from collections import OrderedDict

from .robot_kinematics import (forward_kinematics, solve_ik, collision_shapes,
    pose_identity, compose_poses, inverse_pose, transform_point, rotate_vector, axis_quaternion)
from .robot_sdf import pose_rpy


class ResolvedMotionConfig:
    def __init__(self, robot, task, *, asset_root=None, mesh_repository=None, self_collision_cache=None):
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
        from .robot_crop_collision_policy import crop_collision_exclusions
        self.crop_collision_excluded_shapes = crop_collision_exclusions(robot, self.task)
        self.mesh_repository = mesh_repository
        geometries = [s['geometry'] for link in robot.links for s in link['collisions']
                      if s['geometry']['type'] == 'mesh']
        if geometries and mesh_repository is None:
            if asset_root is None:
                raise ValueError('Mesh collision planning requires an explicit verified asset root')
            from .robot_mesh_geometry import MeshRepository
            self.mesh_repository = MeshRepository(asset_root, geometries)
        self.self_collision_cache = (_RigidPairDistanceCache(robot, self.mesh_repository)
                                     if self_collision_cache is None else self_collision_cache)
        if (self.self_collision_cache.robot_sha256 != robot.sha256 or
                self.self_collision_cache.repository is not self.mesh_repository):
            raise ValueError('Self-collision cache belongs to a different robot or mesh repository')
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
                                    mesh_repository=self.mesh_repository, self_collision_cache=self.self_collision_cache)

    def for_observed_joints(self, positions):
        """Use measured passive/jaw coordinates in clearance, never stale zeros."""
        names = set(self.aux_positions)
        if not names <= positions.keys():
            raise ValueError('Missing observed passive/gripper joint state')
        return ResolvedMotionConfig(self.robot, {**self.task,
            'auxiliary_joint_positions': {n: positions[n] for n in names}}, mesh_repository=self.mesh_repository,
            self_collision_cache=self.self_collision_cache)

    def for_target_cut(self, identifier):
        return ResolvedMotionConfig(self.robot, {**self.task, 'active_cut_target': identifier},
                                    mesh_repository=self.mesh_repository, self_collision_cache=self.self_collision_cache)

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


class _RigidPairDistanceCache:
    """Bounded LRU of self distances in the pair's common-ancestor frame.

    Geometry and link-local poses belong to one immutable RobotSpec. A pair
    depends only on coordinates in the two exclusive ancestry branches; root
    pose, common ancestors and unrelated joints cancel. Coordinates are never
    quantized. Saturated BVH queries store a lower bound, reusable only when it
    covers the requested cap. This does not certify continuous motion.
    """
    def __init__(self, robot, repository, max_entries=8192):
        if type(max_entries) is not int or max_entries < 1:
            raise ValueError('Self-collision LRU requires a positive bounded capacity')
        self.robot_sha256, self.repository = robot.sha256, repository
        self.max_entries = max_entries
        data = robot.to_dict()
        self.shapes = {link['name']+'/'+shape['name']: {**shape, 'link': link['name']}
                       for link in data['links'] for shape in link['collisions']}
        by_child = {joint['child']: joint for joint in data['joints']}
        self.paths = {}
        for link in data['links']:
            path, current = [], link['name']
            while current != data['root_link']:
                row = by_child[current]
                path.append(row)
                current = row['parent']
            self.paths[link['name']] = tuple(reversed(path))
        self.link_pair_plans = {}
        self.entries = OrderedDict()
        self.stats = {'hits': 0, 'misses': 0, 'cap_rechecks': 0, 'evictions': 0,
                      'exact_hits': 0, 'lower_bound_hits': 0}

    def _plan(self, first_link, second_link):
        key = first_link, second_link
        if key not in self.link_pair_plans:
            first, second = self.paths[first_link], self.paths[second_link]
            common = 0
            while common < min(len(first), len(second)) and first[common]['name'] == second[common]['name']:
                common += 1
            left, right = first[common:], second[common:]
            coordinates = tuple(sorted(row['name'] for row in (*left, *right) if row['type'] != 'fixed'))
            self.link_pair_plans[key] = left, right, coordinates
        return self.link_pair_plans[key]

    @staticmethod
    def _branch_pose(branch, positions):
        pose = pose_identity()
        for row in branch:
            motion = pose_identity()
            if row['type'] != 'fixed':
                q = positions.get(row['name'], 0) + row['zero_offset']
                if row['type'] == 'revolute':
                    motion['quaternion_xyzw'] = axis_quaternion(row['axis'], q)
                else:
                    motion['xyz_m'] = [q*v for v in row['axis']]
            pose = compose_poses(compose_poses(compose_poses(pose, row['origin']), motion), row['child_pose'])
        return pose

    def distance(self, first_name, second_name, positions, cap):
        first_name, second_name = sorted((first_name, second_name))
        first, second = self.shapes[first_name], self.shapes[second_name]
        left, right, coordinates = self._plan(first['link'], second['link'])
        values = tuple(positions.get(name, 0) for name in coordinates)
        if any(not math.isfinite(value) for value in values):
            raise ValueError('Self-collision cache coordinates must be finite')
        key = first_name, second_name, values
        entry = self.entries.get(key)
        if entry is not None:
            value, exact = entry
            if exact or value >= cap:
                self.entries.move_to_end(key)
                self.stats['hits'] += 1
                self.stats['exact_hits' if exact else 'lower_bound_hits'] += 1
                return min(value, cap) if exact else cap
            self.stats['cap_rechecks'] += 1
        self.stats['misses'] += 1
        # Evaluate in a deterministic rigid frame, independent of which base
        # pose or common-ancestor coordinate happened to populate the cache.
        a = {**first, 'pose': compose_poses(self._branch_pose(left, positions), first['pose'])}
        b = {**second, 'pose': compose_poses(self._branch_pose(right, positions), second['pose'])}
        first_half = None if a['geometry']['type'] == 'mesh' else shape_box(a)
        second_half = None if b['geometry']['type'] == 'mesh' else shape_box(b)
        if first_half is None or second_half is None:
            if self.repository is None:
                raise ValueError('Self-collision mesh query requires the verified repository')
            low_a, high_a = self.repository.conservative_world_bounds(a)
            low_b, high_b = self.repository.conservative_world_bounds(b)
            lower = math.sqrt(sum(max(low_a[i]-high_b[i], low_b[i]-high_a[i], 0)**2 for i in range(3)))
            value = cap if lower >= cap else self.repository.shape_distance(a, b, limit=cap)
            exact = value < cap
        else:
            value = box_separation(a, first_half, b, second_half)
            exact = True
        if math.isnan(value):
            raise ValueError('Invalid self-collision distance')
        self.entries[key] = value, exact
        self.entries.move_to_end(key)
        if len(self.entries) > self.max_entries:
            self.entries.popitem(last=False)
            self.stats['evictions'] += 1
        return min(value, cap) if exact else cap


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


def _bounded_radius_gap(query, radius, minimum, *args):
    """Preserve a saturated query's cap instead of subtracting roundoff from it.

    A bounded distance returning its cutoff only certifies that the pair
    cannot improve the current minimum. It is not a measured surface distance.
    Unsaturated distances retain their exact subtraction, including breaches
    arbitrarily close to the acceptance threshold; no epsilon is introduced.
    """
    cutoff = max(0, minimum + radius)
    raw = query(*args, limit=cutoff)
    return minimum if raw >= cutoff else raw - radius


def resolved_world_clearance(values, base, cylinders, fruits, held, config, report_cap=.5,
                             *, reject_on_first_failure=False):
    from .harvest_clearance import _segment_box_distance, _point_box_distance, _point_segment_distance
    shapes, tcp = config.world_shapes(values, base)
    if reject_on_first_failure:
        shapes = sorted(shapes, key=lambda shape: not shape['link'].startswith(('arm_wrist', 'gripper')))
    repository = config.mesh_repository
    fruit_shapes = [({'geometry': fruit['collision_geometry'],
                      'pose': pose_from_center(fruit['center_world_m'])} if 'collision_geometry' in fruit else None, fruit)
                    for fruit in fruits]
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
    pair_cache = getattr(config, 'self_collision_cache', None)
    self_positions = config.positions(values) if pair_cache is not None else None

    def rejected(gap, pair, scope):
        return {'robot_clearance_m': gap, 'limiting_robot_pair': pair, 'first_failure_only': True,
                'scope': scope, 'tcp_world_m': tcp['xyz_m'], 'robot_spec_sha256': config.robot.sha256}

    def self_clearance():
        gap_min, names = report_cap, None
        for index, (first, first_half, _) in enumerate(boxes):
            for second_index in range(index+1, len(boxes)):
                second, second_half, _ = boxes[second_index]
                pair = tuple(sorted((first['link'], second['link'])))
                if first['link'] == second['link'] or pair in exclusions:
                    continue
                uses_mesh = first_half is None or second_half is None
                if uses_mesh:
                    a, b = bounds[index], bounds[second_index]
                    lower_bound = math.sqrt(sum(max(a[0][i]-b[1][i], b[0][i]-a[1][i], 0)**2 for i in range(3)))
                    if lower_bound >= gap_min:
                        continue
                if pair_cache is not None:
                    gap = pair_cache.distance(first['link']+'/'+first['name'], second['link']+'/'+second['name'],
                                              self_positions, gap_min)
                elif uses_mesh:
                    gap = repository.shape_distance(first, second, limit=gap_min)
                else:
                    gap = box_separation(first, first_half, second, second_half)
                if gap < gap_min:
                    gap_min, names = gap, [first['link']+'/'+first['name'], second['link']+'/'+second['name']]
                    if reject_on_first_failure:
                        return gap_min, names
        return gap_min, names

    # Report the environment independently of internal mechanical interfaces.
    # The authoritative total remains their minimum: this adds diagnostics,
    # never an exemption or permission to accept internal contact.
    task = getattr(config, 'task', {})
    matching_blades = set(task.get('demo_fixture', {}).get('ideal_cut_blade_shapes', []))
    crop_excluded = getattr(config, 'crop_collision_excluded_shapes', frozenset())
    active_cut = task.get('active_cut_target')
    detached_id = held['id'] if held is not None else None
    for index, (shape, half, inverse) in enumerate(boxes):
        name = shape['link']+'/'+shape['name']
        ignores_crop = name in crop_excluded
        center = shape['pose']['xyz_m']
        if half is None:
            low, high = bounds[index]
            center = [(a+b)/2 for a,b in zip(low, high)]
            bound = math.dist(low, high)/2
        else:
            bound = math.sqrt(sum(v*v for v in half))
        # A previous penetration must not shrink the spatial query inside the
        # body: deeper intersections still contribute to the reported minimum.
        nearby = (() if ignores_crop else
                  cylinders.near(center, bound+max(0, minimum)) if hasattr(cylinders, 'near') else cylinders)
        for obstacle in nearby:
            if detached_id is not None and obstacle.get('ideal_cut_target') == detached_id:
                # The static world contains only the proximal collider here.
                # The virtual terminal was used before cutting this target.
                continue
            if (active_cut is not None and obstacle.get('ideal_cut_target') == active_cut and name in matching_blades
                    and math.dist(tcp['xyz_m'], obstacle['end']) <= .02):
                continue
            if bounds is not None:
                low_bound, high_bound = bounds[index]
                reach = max(0, minimum) + obstacle['radius']
                if any(min(a,b)-hi >= reach or lo-max(a,b) >= reach for a,b,lo,hi in
                       zip(obstacle['start'], obstacle['end'], low_bound, high_bound)):
                    continue
            gap = (_bounded_radius_gap(repository.segment_distance, obstacle['radius'], minimum,
                                       shape, obstacle['start'], obstacle['end'])
                   if half is None else _segment_box_distance(transform_point(inverse, obstacle['start']),
                   transform_point(inverse, obstacle['end']), half)-obstacle['radius'])
            if gap < minimum:
                minimum, limiting = gap, [name, obstacle['id']]
                if reject_on_first_failure:
                    return rejected(gap, limiting, 'crop')
        for fruit_shape, fruit in (() if ignores_crop else fruit_shapes):
            if held is not None and fruit['id'] == held['id']:
                continue
            fruit_radius = fruit.get('planning_broadphase_radius_m', fruit['radius_m'])
            if bounds is not None:
                low_bound, high_bound = bounds[index]
                reach = max(0, minimum) + fruit_radius
                if any(p-hi >= reach or lo-p >= reach for p,lo,hi in zip(fruit['center_world_m'], low_bound, high_bound)):
                    continue
            gap = (_bounded_radius_gap(repository.point_distance, fruit_radius, minimum,
                                       shape, fruit['center_world_m']) if half is None
                   else _point_box_distance(transform_point(inverse, fruit['center_world_m']), half)-fruit_radius)
            if gap < minimum and 'planning_calyx_recipe' in fruit:
                from .harvest_plants import static_calyx_clearance_shape
                fruit_shape = static_calyx_clearance_shape(fruit, repository)
            if fruit_shape is not None and gap < minimum:
                gap = repository.shape_distance(shape, fruit_shape, limit=max(0, minimum))
            if gap < minimum:
                minimum, limiting = gap, [name, fruit['id']]
                if reject_on_first_failure:
                    return rejected(gap, limiting, 'fruit')
        if shape['link'] not in drive_links:
            if half is None:
                gap = minimum if low[2] >= minimum else repository.world_bounds(shape)[0][2]
            else:
                axes = [rotate_vector(shape['pose']['quaternion_xyzw'], [int(i==j) for i in range(3)]) for j in range(3)]
                gap = center[2]-sum(abs(axis[2])*h for axis, h in zip(axes, half))
            if gap < minimum:
                minimum, limiting = gap, [name, 'ground']
                if reject_on_first_failure:
                    return rejected(gap, limiting, 'ground')
    environment_minimum,environment_limiting=minimum,limiting
    self_minimum, self_limiting = self_clearance()
    if reject_on_first_failure and self_minimum < report_cap:
        return rejected(self_minimum, self_limiting, 'self')
    if self_minimum<=minimum:
        minimum,limiting=self_minimum,self_limiting
    if held is not None:
        # The original offset is expressed in the CUT posture's tool frame,
        # rather than rotating a world-space vector as if wrist roll were zero.
        if 'held_offset_in_tool_m' not in held:
            raise ValueError('Resolved held clearance requires the audited cut-frame attachment offset')
        center = transform_point(tcp, held['held_offset_in_tool_m'])
        radius = held['radius_m']
        held_shape = ({'geometry': held['collision_geometry'],
                       'pose': compose_poses(tcp, held['held_pose_in_tool'])}
                      if 'collision_geometry' in held else None)
        floor_gap = repository.world_bounds(held_shape)[0][2] if held_shape else center[2]-radius
        held_min, limiting_held = min(report_cap, floor_gap), 'ground'
        nearby = cylinders.near(center, radius+max(0, held_min)) if hasattr(cylinders, 'near') else cylinders
        for obstacle in nearby:
            if obstacle.get('ideal_cut_target') == detached_id:
                continue
            gap = _point_segment_distance(center, obstacle['start'], obstacle['end'])-radius-obstacle['radius']
            if held_shape and gap < held_min:
                gap = _bounded_radius_gap(repository.segment_distance, obstacle['radius'], held_min,
                                          held_shape, obstacle['start'], obstacle['end'])
            if gap < held_min:
                held_min, limiting_held = gap, obstacle['id']
        for fruit_shape, fruit in fruit_shapes:
            if fruit['id'] != held['id']:
                fruit_radius = fruit.get('planning_broadphase_radius_m', fruit['radius_m'])
                gap = math.dist(center, fruit['center_world_m'])-radius-fruit_radius
                if gap < held_min and 'planning_calyx_recipe' in fruit:
                    from .harvest_plants import static_calyx_clearance_shape
                    fruit_shape = static_calyx_clearance_shape(fruit, repository)
                if (held_shape or fruit_shape) and gap < held_min:
                    first = held_shape or {'geometry': {'type': 'sphere', 'radius_m': radius}, 'pose': pose_from_center(center)}
                    second = fruit_shape or {'geometry': {'type': 'sphere', 'radius_m': fruit_radius},
                                             'pose': pose_from_center(fruit['center_world_m'])}
                    gap = repository.shape_distance(first, second, limit=max(0, held_min))
                if gap < held_min:
                    held_min, limiting_held = gap, fruit['id']
        for shape, half, inverse in boxes:
            if shape['link']+'/'+shape['name'] in crop_excluded:
                continue
            gap = (_bounded_radius_gap(repository.point_distance, radius, held_robot_min,
                                       shape, center) if half is None
                   else _point_box_distance(transform_point(inverse, center), half)-radius)
            if held_shape and gap < held_robot_min:
                gap = repository.shape_distance(shape, held_shape, limit=max(0, held_robot_min))
            if gap < held_robot_min:
                held_robot_min, limiting_held_robot = gap, shape['link']+'/'+shape['name']
    return {'robot_clearance_m': minimum, 'held_clearance_m': held_min if held else None,
            'self_clearance_m': self_minimum, 'environment_clearance_m': environment_minimum,
            'limiting_self_pair': self_limiting, 'limiting_environment_pair': environment_limiting,
            'held_robot_clearance_m': held_robot_min if held else None,
            'limiting_robot_pair': limiting, 'limiting_held_obstacle': limiting_held,
            'limiting_held_robot_link': limiting_held_robot, 'tcp_world_m': tcp['xyz_m'],
            'robot_spec_sha256': config.robot.sha256}


def pose_from_center(center):
    return {'xyz_m': list(center), 'quaternion_xyzw': [0, 0, 0, 1]}
