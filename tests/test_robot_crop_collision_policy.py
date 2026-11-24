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
    OPTION, WRIST_OPTION, FINGER_BLADE_CROP_SHAPES, WRIST_HOUSING_CROP_SHAPES,
    WRIST_EXTENSION_JAW_SHAPES, _CAD_PARTS, _WRIST_CAD_PARTS, _ADDITIONAL_JAW_PARTS, _subset_masks,
    finger_blade_crop_exclusions, crop_collision_exclusions, compile_crop_collision_policy,
    apply_robot_crop_collision_masks, scene_crop_collision_policy,
    verify_scene_crop_collision_masks)
from uchuva_gazebo.robot_motion import resolved_world_clearance, pose_from_center


def fixture(include_wrist=False):
    links = {name: {'name': name, 'collisions': []} for name in
             ('base_link', 'arm_wrist_roll', 'gripper_left_jaw', 'gripper_right_jaw')}
    if include_wrist:
        links['arm_wrist_pitch'] = {'name': 'arm_wrist_pitch', 'collisions': []}
    parts = {**_CAD_PARTS, **(_WRIST_CAD_PARTS if include_wrist else {}),
             **(_ADDITIONAL_JAW_PARTS if include_wrist else {})}
    for name, (_, digest) in parts.items():
        link, shape = name.split('/')
        links[link]['collisions'].append({'name': shape, 'geometry': {
            'type': 'mesh', 'sha256': digest, 'scale': [1, 1, 1]}})
    for link, name in (('base_link', 'basket_floor'), ('arm_wrist_roll', 'part_99_bounds'),
                       ('gripper_left_jaw', 'part_111_bounds'), ('gripper_right_jaw', 'part_112_bounds')):
        if link+'/'+name in parts:
            continue
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
    def test_wrist_extension_is_separate_requires_fingers_and_exact_full_inventory(self):
        robot, task = fixture(include_wrist=True)
        baseline = compile_crop_collision_policy(robot, task)
        task['demo_fixture'][WRIST_OPTION] = False
        self.assertEqual(compile_crop_collision_policy(robot, task), baseline)
        task['demo_fixture'][WRIST_OPTION] = True
        self.assertEqual(finger_blade_crop_exclusions(robot, task), FINGER_BLADE_CROP_SHAPES)
        self.assertEqual(crop_collision_exclusions(robot, task),
                         FINGER_BLADE_CROP_SHAPES | WRIST_HOUSING_CROP_SHAPES | WRIST_EXTENSION_JAW_SHAPES)
        for invalid in ('true', 1, None):
            changed = deepcopy(task); changed['demo_fixture'][WRIST_OPTION] = invalid
            with self.assertRaises(ValueError): crop_collision_exclusions(robot, changed)
        changed = deepcopy(task); changed['demo_fixture'][OPTION] = False
        with self.assertRaises(ValueError): crop_collision_exclusions(robot, changed)
        wrist = next(link for link in robot.links if link['name'] == 'arm_wrist_roll')
        saved = wrist['collisions'][0]['geometry']['sha256']
        wrist['collisions'][0]['geometry']['sha256'] = '0'*64
        with self.assertRaises(ValueError): crop_collision_exclusions(robot, task)
        wrist['collisions'][0]['geometry']['sha256'] = saved
        # New, unreviewed wrist geometry is not silently covered by a prefix.
        wrist['collisions'].append({'name': 'unreviewed', 'geometry': {'type': 'box', 'size_m': [.1]*3}})
        with self.assertRaises(ValueError): crop_collision_exclusions(robot, task)

    def test_wrist_extension_preserves_internal_pairs_and_omits_only_the_reclassified_jaw_parts(self):
        robot, task = fixture(include_wrist=True)
        task['demo_fixture'][WRIST_OPTION] = True
        policy = compile_crop_collision_policy(robot, task)
        self.assertEqual(len(policy['excluded_shapes']), 19)
        self.assertIn('wrist_housing_extension', policy)
        old, new = policy['original_robot_masks'], policy['robot_masks']
        omitted = FINGER_BLADE_CROP_SHAPES | WRIST_HOUSING_CROP_SHAPES | WRIST_EXTENSION_JAW_SHAPES
        for a, b in itertools.combinations(old, 2):
            self.assertEqual(bool(old[a]&old[b]), bool(new[a]&new[b]), (a, b))
        for name, mask in new.items():
            self.assertEqual(bool(mask&policy['crop_mask']), name not in omitted, name)
            self.assertTrue(mask&65535)
        self.assertTrue(new['base_link/basket_floor']&policy['crop_mask'])
        for name in WRIST_EXTENSION_JAW_SHAPES:
            self.assertFalse(new[name]&policy['crop_mask'])
            self.assertTrue(new[name]&65535)
        self.assertEqual(policy['wrist_housing_extension']['additional_jaw_shapes'], sorted(WRIST_EXTENSION_JAW_SHAPES))
        model = model_with_masks(robot)
        apply_robot_crop_collision_masks(model, policy)
        for row in policy['excluded_shapes']:
            link, name = row['name'].split('/')
            node = model.find(f"link[@name='{link}']/collision[@name='{name}']")
            self.assertEqual(int(node.findtext('surface/contact/collide_bitmask')) & policy['crop_mask'], 0)

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

    def test_only_the_matching_virtual_terminal_leaves_the_crop_after_cut(self):
        config = self.config(name='part_112_bounds')
        terminal = {'id': 'virtual-cut-span', 'ideal_cut_target': 'fruit',
                    'start': [0, 0, .8], 'end': [0, 0, 1.2], 'radius': .01}
        fruit = {'id': 'fruit', 'center_world_m': [0, 0, 1], 'radius_m': .02,
                 'held_offset_in_tool_m': [0, 0, 0]}
        self.assertLess(resolved_world_clearance([], [], [terminal], [], None, config)['robot_clearance_m'], 0)
        result = resolved_world_clearance([], [], [terminal], [], fruit, config)
        self.assertEqual(result['robot_clearance_m'], .5)
        self.assertEqual(result['held_clearance_m'], .5)
        neighbor = {**terminal, 'ideal_cut_target': 'different-fruit'}
        self.assertLess(resolved_world_clearance([], [], [neighbor], [], fruit, config)['held_clearance_m'], 0)

    def test_wrist_extension_omits_crop_but_retains_arm_ground_and_self(self):
        crop = {'id': 'crop', 'start': [0, 0, .8], 'end': [0, 0, 1.2], 'radius': .01}
        wrist = self.config(link='arm_wrist_roll', name='part_98_bounds')
        self.assertLess(resolved_world_clearance([], [], [crop], [], None, wrist)['robot_clearance_m'], 0)
        wrist.crop_collision_excluded_shapes |= WRIST_HOUSING_CROP_SHAPES
        self.assertEqual(resolved_world_clearance([], [], [crop], [], None, wrist)['robot_clearance_m'], .5)
        arm = self.config(link='arm_forearm', name='body')
        arm.crop_collision_excluded_shapes |= WRIST_HOUSING_CROP_SHAPES
        self.assertLess(resolved_world_clearance([], [], [crop], [], None, arm)['robot_clearance_m'], 0)
        for config, scope in ((self.config(link='arm_wrist_roll', name='part_98_bounds', center=(0, 0, .02)), 'ground'),
                              (self.config(link='arm_wrist_roll', name='part_98_bounds', other=(.04, 0, 1)), 'self')):
            config.crop_collision_excluded_shapes |= WRIST_HOUSING_CROP_SHAPES
            result = resolved_world_clearance([], [], [], [], None, config,
                report_cap=.004, reject_on_first_failure=True)
            self.assertLess(result['robot_clearance_m'], .004)
            self.assertEqual(result['scope'], scope)


if __name__ == '__main__':
    unittest.main()
