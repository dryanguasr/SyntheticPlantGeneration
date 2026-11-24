"""Explicit, part-scoped crop-contact omission for the authorized CAD video.

This is an approximation, not collision-free physical harvesting. Original
robot masks remain present. Extra bits are strict subsets of their original
cliques, so they cannot introduce a previously forbidden internal contact.
Only plant/fruit models use the extra bits; ground and other external bodies
continue to expose all bits. No geometry, inertia or clearance threshold moves.
"""
from __future__ import annotations

import hashlib
import itertools
import json

from .robot_collision_filters import collision_masks


OPTION = 'ignore_finger_blade_crop_contacts'
POLICY_SCHEMA = 'cad-finger-blade-crop-omission/1.0'
# Dedicated CAD fingers, blades and pads. The rigid pad supports 111/112,
# housing 98, cover 99, wrist and every other part are deliberately absent.
_CAD_PARTS = {
    'gripper_right_jaw/part_104_bounds': ('Eslabon L:1', 'd4d02dd949c76c5dd0773913418447685b310703c820beb9f719cdd4699f9125'),
    'gripper_left_jaw/part_106_bounds': ('Eslabon L:2', '5af9f4af1ee725912b1387866a2003b31201d0f34aa0497bf45d38a354430a8f'),
    'gripper_left_jaw/part_109_bounds': ('Cuchilla:1', '93f62cf50b4c7933d12f31b02c014162c6030310cf667b73d6539ef404f94c0a'),
    'gripper_right_jaw/part_110_bounds': ('Cuchilla:2', '93f62cf50b4c7933d12f31b02c014162c6030310cf667b73d6539ef404f94c0a'),
    'gripper_left_jaw/part_113_bounds': ('Goma:1', 'e7197c337019297e9347acf1424a35fcce3b2ffbbb7313fc90457d72fdebe358'),
    'gripper_right_jaw/part_114_bounds': ('Goma:2', 'e7197c337019297e9347acf1424a35fcce3b2ffbbb7313fc90457d72fdebe358'),
}
FINGER_BLADE_CROP_SHAPES = frozenset(_CAD_PARTS)


def _shape_inventory(robot):
    rows = [(link['name']+'/'+shape['name'], shape)
            for link in robot.links for shape in link['collisions']]
    if len({name for name, _ in rows}) != len(rows):
        raise ValueError('Duplicate qualified robot collision name')
    return dict(rows)


def finger_blade_crop_exclusions(robot, task):
    """Validate the boolean opt-in and exact CAD assets; return six names or none."""
    fixture = task.get('demo_fixture', {})
    enabled = fixture.get(OPTION, False)
    if type(enabled) is not bool:
        raise ValueError(f'demo_fixture.{OPTION} must be a boolean')
    if not enabled:
        return frozenset()
    from .harvest_basket import DEMO_FIXTURE_SCHEMA
    if (fixture.get('schema_version') != DEMO_FIXTURE_SCHEMA or
            fixture.get('robot_spec_sha256') != robot.sha256):
        raise ValueError('Crop-contact omission requires the matching versioned CAD demonstration')
    inventory = _shape_inventory(robot)
    for name, (_, digest) in _CAD_PARTS.items():
        geometry = inventory.get(name, {}).get('geometry', {})
        if (geometry.get('type') != 'mesh' or geometry.get('sha256') != digest or
                tuple(geometry.get('scale', (1, 1, 1))) != (1, 1, 1)):
            raise ValueError(f'Crop-contact omission requires the exact dedicated CAD shape: {name}')
    return FINGER_BLADE_CROP_SHAPES


def _subset_masks(original, omitted):
    """Split clique memberships at shape granularity, with exhaustive proof."""
    if not original or not omitted <= original.keys() or any(
            type(v) is not int or not 0 < v <= 65535 for v in original.values()):
        raise ValueError('Crop mask splitting requires nonzero original 16-bit shape masks')
    used = [bit for bit in range(16) if any(mask & (1 << bit) for mask in original.values())]
    free = [bit for bit in range(16) if bit not in used]
    revised = dict(original)
    crop_mask = 0
    for bit in used:
        members = {name for name, mask in original.items() if mask & (1 << bit)}
        retained = members-omitted
        if not retained:
            continue
        if not members & omitted:
            # Reusing a clique containing no omitted shape is already safe.
            crop_mask |= 1 << bit
            continue
        if not free:
            raise ValueError('No free 16-bit collision bit for exact crop-only shape exclusions')
        extra = 1 << free.pop(0)
        crop_mask |= extra
        for name in retained:
            revised[name] |= extra
    if not crop_mask:
        raise ValueError('Crop mask must preserve contacts with the remaining robot')
    for a, b in itertools.combinations(original, 2):
        if bool(original[a] & original[b]) != bool(revised[a] & revised[b]):
            raise ValueError('Crop split changed an internal robot mask pair')
    if any(bool(mask & crop_mask) != (name not in omitted) for name, mask in revised.items()):
        raise ValueError('Crop split changed an unauthorized shape-to-crop pair')
    return revised, crop_mask


def _seal(report):
    report['policy_sha256'] = hashlib.sha256(json.dumps(report, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return report


def compile_crop_collision_policy(robot, task):
    omitted = finger_blade_crop_exclusions(robot, task)
    if not omitted:
        return None
    inventory = _shape_inventory(robot)
    masks = collision_masks(robot.to_dict())
    original = {name: masks[name.split('/')[0]] for name in inventory}
    revised, crop_mask = _subset_masks(original, omitted)
    return _seal({
        'schema_version': POLICY_SCHEMA, 'robot_spec_sha256': robot.sha256,
        'scope': 'only_crop_against_named_fingers_blades_and_pads',
        'status': 'explicit_video_approximation_not_physical_harvest_validation',
        'excluded_shapes': [{'name': name, 'cad_occurrence': _CAD_PARTS[name][0],
                             'collision_sha256': _CAD_PARTS[name][1]} for name in sorted(omitted)],
        'original_robot_masks': original, 'robot_masks': revised, 'crop_mask': crop_mask,
        'other_external_mask': 65535,
        'internal_shape_pairs_verified': len(original)*(len(original)-1)//2,
        'preserved': ['all_internal_mask_pairs', 'native_adjacency', 'all_geometry_and_inertias',
                      'ground', 'basket', 'supports_111_112', 'all_other_robot_crop_pairs',
                      'crop_crop_contacts', 'clearance_thresholds'],
    })


def apply_robot_crop_collision_masks(model, policy):
    """Alter only contact masks on an otherwise canonical robot model."""
    from .harvester_robot import set_collision_bitmask
    found = {link.get('name')+'/'+shape.get('name'): shape
             for link in model.findall('link') for shape in link.findall('collision')}
    if set(found) != set(policy['robot_masks']):
        raise ValueError('Robot SDF collision inventory differs from crop policy')
    for name, node in found.items():
        old = int(node.findtext('surface/contact/collide_bitmask', '-1'))
        if old != policy['original_robot_masks'][name]:
            raise ValueError('Robot SDF masks differ from the canonical internal policy')
        set_collision_bitmask(node, policy['robot_masks'][name])


def scene_crop_collision_policy(robot, task, crop_model_names):
    policy = compile_crop_collision_policy(robot, task)
    if policy is None:
        return None
    names = sorted(set(crop_model_names))
    if not names or robot.data['model_name'] in names or 'ground' in names:
        raise ValueError('Crop-only filtering requires an explicit nonempty plant/fruit inventory')
    policy.pop('policy_sha256')
    policy['crop_model_names'] = names
    return _seal(policy)


def verify_scene_crop_collision_masks(world, robot_model_name, policy):
    """Read-only check, including ground/external masks; used by package loader."""
    found_crop = set()
    for model in world.findall('model'):
        name = model.get('name')
        if name in policy['crop_model_names']:
            found_crop.add(name)
        for link in model.findall('link'):
            for shape in link.findall('collision'):
                if name == robot_model_name:
                    expected = policy['robot_masks'].get(link.get('name')+'/'+shape.get('name'))
                else:
                    expected = policy['crop_mask'] if name in policy['crop_model_names'] else 65535
                masks = shape.findall('surface/contact/collide_bitmask')
                categories = shape.findall('surface/contact/category_bitmask')
                if (len(masks) != 1 or int(masks[0].text) != expected or len(categories) > 1 or
                        (categories and int(categories[0].text) != expected)):
                    raise ValueError('Native crop-contact masks differ from the explicit scene policy')
    if found_crop != set(policy['crop_model_names']):
        raise ValueError('Missing plant/fruit model in crop-contact policy')
