"""Crop-only shape filters must preserve internal and other external contacts."""
from copy import deepcopy
import hashlib
import itertools
import json
from types import MappingProxyType, SimpleNamespace
import unittest
import xml.etree.ElementTree as ET

from uchuva_gazebo.harvest_basket import DEMO_FIXTURE_SCHEMA
from uchuva_gazebo.harvester_robot import set_collision_bitmask
from uchuva_gazebo.robot_collision_filters import collision_masks
from uchuva_gazebo.robot_crop_collision_policy import (
    OPTION, FINGER_BLADE_CROP_SHAPES, _CAD_PARTS, _subset_masks,
    finger_blade_crop_exclusions, compile_crop_collision_policy,
    apply_robot_crop_collision_masks, scene_crop_collision_policy,
    verify_scene_crop_collision_masks)
from uchuva_gazebo.robot_motion import resolved_world_clearance, pose_from_center


def fixture():
    links = {name: {'name': name, 'collisions': []} for name in
             ('base_link', 'arm_wrist_roll', 'gripper_left_jaw', 'gripper_right_jaw')}
    for name, (_, digest) in _CAD_PARTS.items():
        link, shape = name.split('/')
        links[link]['collisions'].append({'name': shape, 'geometry': {
            'type': 'mesh', 'sha256': digest, 'scale': [1, 1, 1]}})
    for link, name in (('base_link', 'basket_floor'), ('arm_wrist_roll', 'part_99_bounds'),
                       ('gripper_left_jaw', 'part_111_bounds'), ('gripper_right_jaw', 'part_112_bounds')):
        links[link]['collisions'].append({'name': name, 'geometry': {'type': 'box', 'size_m': [.1]*3}})
    data = {'model_name': 'robot', 'links': list(links.values()), 'joints': [],
            'collision_policy': {'excluded_pairs': [{'links': ['gripper_left_jaw', 'gripper_right_jaw']}]}}
    robot = SimpleNamespace(data=data, links=data['links'], sha256='fixture', to_dict=lambda: deepcopy(data))
    task = {'demo_fixture': {'schema_version': DEMO_FIXTURE_SCHEMA, 'robot_spec_sha256': robot.sha256, OPTION: True}}
    return robot, task


def model_with_masks(robot):
    model = ET.Element('model', name='robot')
    masks = collision_masks(robot.data)
    for row in robot.links:
        link = ET.SubElement(model, 'link', name=row['name'])
        for shape in row['collisions']:
            node = ET.SubElement(link, 'collision', name=shape['name'])
            ET.SubElement(ET.SubElement(ET.SubElement(node, 'geometry'), 'box'), 'size').text = '.1 .1 .1'
            ET.SubElement(ET.SubElement(node, 'surface'), 'friction').text = 'preserved'
            set_collision_bitmask(node, masks[row['name']])
    return model


class CropPolicyTests(unittest.TestCase):
    def test_six_exact_parts_opt_in_and_changed_assets_fail_closed(self):
        robot, task = fixture()
        self.assertEqual(len(finger_blade_crop_exclusions(robot, task)), 6)
        self.assertFalse(finger_blade_crop_exclusions(robot, {}))
        self.assertIsNone(compile_crop_collision_policy(robot, {}))
        # ResolvedRobot exposes immutable mapping proxies and tuple scales.
        # Exercise that public view, not only its JSON-serializable to_dict().
        frozen = SimpleNamespace(sha256=robot.sha256, links=tuple(
            MappingProxyType({**link, 'collisions': tuple(MappingProxyType({**shape,
                'geometry': MappingProxyType({**shape['geometry'], **(
                    {'scale': tuple(shape['geometry']['scale'])} if 'scale' in shape['geometry'] else {})})})
                for shape in link['collisions'])}) for link in robot.links))
        self.assertEqual(finger_blade_crop_exclusions(frozen, task), FINGER_BLADE_CROP_SHAPES)
        for invalid in ('true', 1, None):
            changed = deepcopy(task); changed['demo_fixture'][OPTION] = invalid
            with self.assertRaises(ValueError): finger_blade_crop_exclusions(robot, changed)
        changed = deepcopy(task); changed['demo_fixture']['robot_spec_sha256'] = 'other'
        with self.assertRaises(ValueError): finger_blade_crop_exclusions(robot, changed)
        shape = robot.links[2]['collisions'][0]
        shape['geometry']['sha256'] = '0'*64
        with self.assertRaises(ValueError): finger_blade_crop_exclusions(robot, task)

    def test_split_preserves_every_internal_pair_support_and_basket(self):
        robot, task = fixture()
        policy = compile_crop_collision_policy(robot, task)
        before, after = policy['original_robot_masks'], policy['robot_masks']
        for a, b in itertools.combinations(before, 2):
            self.assertEqual(bool(before[a]&before[b]), bool(after[a]&after[b]), (a, b))
        for name, mask in after.items():
            self.assertEqual(bool(mask&policy['crop_mask']), name not in FINGER_BLADE_CROP_SHAPES)
            self.assertTrue(mask&65535, 'Ground and ordinary obstacles must still contact every shape')
        self.assertTrue(after['gripper_left_jaw/part_111_bounds']&policy['crop_mask'])
        self.assertTrue(after['gripper_right_jaw/part_112_bounds']&policy['crop_mask'])
        self.assertTrue(after['base_link/basket_floor']&policy['crop_mask'])
        report = deepcopy(policy); digest = report.pop('policy_sha256')
        self.assertEqual(digest, hashlib.sha256(json.dumps(report, sort_keys=True,
            separators=(',', ':'), allow_nan=False).encode()).hexdigest())

    def test_reuse_safe_bits_and_refuse_unrepresentable_sixteen_bits(self):
        masks, crop = _subset_masks({'finger': 1, 'support': 3, 'other': 2}, {'finger'})
        self.assertFalse(masks['finger']&crop)
        self.assertTrue(crop&2)
        self.assertEqual(bool(masks['finger']&masks['support']), True)
        with self.assertRaises(ValueError):
            _subset_masks({'finger': 65535, 'support': 65535}, {'finger'})

    def test_only_xml_masks_change_and_native_scope_is_verified(self):
        robot, task = fixture()
        world = ET.Element('world')
        model = model_with_masks(robot); original = deepcopy(model); world.append(model)
        for name in ('plant_000', 'fruit_000', 'ground', 'ordinary_obstacle'):
            ext = ET.SubElement(world, 'model', name=name)
            ET.SubElement(ET.SubElement(ext, 'link', name='body'), 'collision', name='surface')
        policy = scene_crop_collision_policy(robot, task, ['plant_000', 'fruit_000'])
        apply_robot_crop_collision_masks(model, policy)
        for node in world.findall('model')[1:]:
            set_collision_bitmask(node, policy['crop_mask'] if node.get('name') in policy['crop_model_names'] else 65535)
        verify_scene_crop_collision_masks(world, 'robot', policy)
        # Canonical data, geometry and friction stay byte-identical when masks
        # are removed, including same-link support vs finger distinction.
        for node in (original, model):
            for contact in node.findall('.//surface/contact'):
                for child in list(contact): contact.remove(child)
        self.assertEqual(ET.tostring(original), ET.tostring(model))
        # Rebuild because stripping masks above was only a comparison fixture.
        world.remove(model); model = model_with_masks(robot)
        apply_robot_crop_collision_masks(model, policy); world.append(model)
        for name, bad_mask in (('plant_000', 65535), ('ground', policy['crop_mask'])):
            node = world.find(f"model[@name='{name}']")
            good = policy['crop_mask'] if name == 'plant_000' else 65535
            set_collision_bitmask(node, bad_mask)
            with self.assertRaises(ValueError): verify_scene_crop_collision_masks(world, 'robot', policy)
            set_collision_bitmask(node, good)


class PlannerScopeTests(unittest.TestCase):
    def config(self, *, name='part_104_bounds', link='gripper_right_jaw', center=(0, 0, 1), other=None):
        shapes = [{'name': name, 'link': link, 'pose': pose_from_center(center),
                   'geometry': {'type': 'box', 'size_m': [.1]*3}}]
        if other is not None:
            shapes.append({'name': 'body', 'link': 'other', 'pose': pose_from_center(other),
                           'geometry': {'type': 'box', 'size_m': [.1]*3}})
        robot = SimpleNamespace(joints=[], sha256='fixture', data={'collision_policy': {'excluded_pairs': []}})
        return SimpleNamespace(robot=robot, task={}, mesh_repository=None,
            crop_collision_excluded_shapes=FINGER_BLADE_CROP_SHAPES,
            world_shapes=lambda q, base: (shapes, pose_from_center(center)))

    def test_cylinder_fruit_and_held_crop_omit_only_authorized_shapes(self):
        cylinder = {'id': 'crop', 'start': [0, 0, .8], 'end': [0, 0, 1.2], 'radius': .01}
        fruit = {'id': 'fruit', 'center_world_m': [0, 0, 1], 'radius_m': .02,
                 'held_offset_in_tool_m': [0, 0, 0]}
        config = self.config()
        for cylinders, fruits, held in (([cylinder], [], None), ([], [fruit], None), ([], [], fruit)):
            result = resolved_world_clearance([], [], cylinders, fruits, held, config)
            self.assertEqual(result['robot_clearance_m'], .5)
            if held: self.assertEqual(result['held_robot_clearance_m'], .5)
        # An authorized finger does not exempt its same-link support.
        support = self.config(name='part_112_bounds')
        self.assertLess(resolved_world_clearance([], [], [cylinder], [], None, support)['robot_clearance_m'], 0)
        self.assertLess(resolved_world_clearance([], [], [], [fruit], None, support)['robot_clearance_m'], 0)
        self.assertLess(resolved_world_clearance([], [], [], [], fruit, support)['held_robot_clearance_m'], 0)
        # Held crop still checks other crop; it is not globally collisionless.
        self.assertLess(resolved_world_clearance([], [], [cylinder], [], fruit, config)['held_clearance_m'], 0)

    def test_ground_and_self_contacts_remain_failures_with_same_threshold(self):
        for config, scope in ((self.config(center=(0, 0, .02)), 'ground'),
                              (self.config(other=(.04, 0, 1)), 'self')):
            result = resolved_world_clearance([], [], [], [], None, config,
                report_cap=.004, reject_on_first_failure=True)
            self.assertLess(result['robot_clearance_m'], .004)
            self.assertEqual(result['scope'], scope)


if __name__ == '__main__':
    unittest.main()
