"""Contract and geometry checks for the CAD demonstration's onboard basket."""
from __future__ import annotations

import math

from .harvest_validation import _vector


DEMO_FIXTURE_SCHEMA = 'cad-v8-short-stroke-harvest/1.0'
BASKET_PARTS = {'basket_floor', 'basket_front', 'basket_rear', 'basket_left', 'basket_right'}


def load_fruit_vertices(manifest, asset_root):
    from pathlib import Path
    from .robot_mesh_geometry import read_collision_obj

    return {fruit['id']: read_collision_obj(Path(asset_root) / fruit['collision_geometry']['uri'])[0]
            for fruit in manifest['fruits'] if 'collision_geometry' in fruit}


def validated_demonstration(robot, task):
    if not isinstance(task, dict) or task.get('demo_fixture', {}).get('schema_version') != DEMO_FIXTURE_SCHEMA:
        raise ValueError('Expected the versioned CAD short-stroke fixture')
    fixture = task['demo_fixture']
    if fixture.get('robot_spec_sha256') != robot.sha256:
        raise ValueError('The CAD demonstration refers to a different resolved robot')
    if fixture.get('motion_clearance_m', .004) != .004 or fixture.get('minimum_joint_margin_rad', .025) != .025:
        raise ValueError('The demonstration must retain the frozen V8 motion margins')
    data = robot.to_dict()
    jaw = fixture['gripper']
    name = jaw['joint']
    joints = {row['name']: row for row in data['joints']}
    joint = joints.get(name, {})
    if (joint.get('group') != 'gripper' or joint.get('type') != 'prismatic' or
            set(data['control'].get('gripper', {})) != {name} or data.get('gear_couplings') or
            {j['name'] for j in joints.values() if j['group'] == 'gripper'} != {name}):
        raise ValueError('The demonstration requires a single native prismatic jaw driver')
    controls = set(data['control']['arm']) | set(data['control']['drive']['joints']) | {name}
    if controls & {j['name'] for j in joints.values() if j['group'] == 'passive'}:
        raise ValueError('Passive mechanisms must be observed without a position controller')
    limits = joint['limits']
    closed, opened, tol, speed, stable = _vector([jaw[key] for key in (
        'closed_position_m', 'open_position_m', 'position_tolerance_m', 'maximum_speed_m_s',
        'stable_time_s')], 5, 'short-stroke jaw')
    if not (limits['lower'] <= closed < opened <= limits['upper'] and
            0 < opened-closed <= .008 and 0 < tol < (opened-closed)/2 and
            0 < speed <= limits['velocity'] and stable > 0):
        raise ValueError('The specified jaw coordinates or guard are inconsistent with the robot')
    basket = fixture['bin']
    if basket.get('frame') != 'robot_base':
        raise ValueError('An onboard basket must be expressed in the measured robot base frame')
    lo = _vector(basket['inner_min_m'], 3, 'basket lower bounds')
    hi = _vector(basket['inner_max_m'], 3, 'basket upper bounds')
    if any(a >= b for a, b in zip(lo, hi)):
        raise ValueError('Basket interior has an empty axis')
    base = next(link for link in data['links'] if link['name'] == data['root_link'])
    parts = {s['name']: s for s in base['collisions'] if s['name'].startswith('basket_')}
    if set(parts) != BASKET_PARTS:
        raise ValueError('The base must carry a basket with a floor and four separate collision walls')
    boxes = []
    for part in parts.values():
        pose = part['pose']
        if pose['quaternion_xyzw'] != [0, 0, 0, 1] or part['geometry']['type'] != 'box':
            raise ValueError('The basket bounds require base-aligned collision boxes')
        extent = [v / 2 for v in part['geometry']['size_m']]
        boxes.append(([c-d for c,d in zip(pose['xyz_m'], extent)],
                      [c+d for c,d in zip(pose['xyz_m'], extent)]))

    # Every face must be a real native support surface. The opening itself
    # deliberately has no collider. Dimensions are checked without inflating
    # the acceptance allowance used for the released fruit.
    def matches(axis, lower_face):
        face = lo[axis] if lower_face else hi[axis]
        return any(math.isclose((b if lower_face else a)[axis], face, abs_tol=1e-9)
                   and all(a[i] <= lo[i]+1e-9 and b[i] >= hi[i]-1e-9
                           for i in range(3) if i != axis) for a,b in boxes)

    if not all(matches(axis, low) for axis, low in ((2, True), (0, True), (0, False), (1, True), (1, False))):
        raise ValueError('Basket interior disagrees with native floor and wall locations')
    if any(all(min(b[i], hi[i]) - max(a[i], lo[i]) > 1e-9 for i in range(3)) for a,b in boxes):
        raise ValueError('A native basket collider obstructs the declared interior')
    return fixture
