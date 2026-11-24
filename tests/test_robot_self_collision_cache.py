"""Self-distance reuse depends on relative articulation, never lucky base poses."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from test_robot_mesh_geometry import cube, write_obj
from uchuva_gazebo.robot_kinematics import (pose_identity, pose_from_rpy, forward_kinematics,
    collision_shapes)
from uchuva_gazebo.robot_mesh_geometry import MeshRepository
from uchuva_gazebo.robot_motion import (_RigidPairDistanceCache, ResolvedMotionConfig,
    resolved_world_clearance, box_separation, shape_box)
from uchuva_gazebo.robot_spec import resolve_robot_profile


def tree_fixture(geometry=None):
    geometry = geometry or {'type': 'box', 'size_m': [.1]*3}
    links = [{'name': name, 'collisions': ([] if name in ('root', 'trunk', 'unrelated') else
             [{'name': 'solid', 'geometry': deepcopy(geometry), 'pose': pose_identity()}])}
             for name in ('root', 'trunk', 'left', 'right', 'unrelated')]
    joints = []
    for name, parent, child, kind, origin, axis, offset in (
            ('common', 'root', 'trunk', 'revolute', [1, 2, 3], [0, 0, 1], .1),
            ('slide', 'trunk', 'left', 'prismatic', [0, 0, 0], [1, 0, 0], .02),
            ('fixed', 'trunk', 'right', 'fixed', [.3, 0, 0], [0, 0, 1], 0),
            ('other', 'root', 'unrelated', 'revolute', [0, 0, 1], [0, 1, 0], 0)):
        joints.append({'name': name, 'parent': parent, 'child': child, 'type': kind,
            'origin': pose_from_rpy(origin, [0, 0, 0]), 'child_pose': pose_identity(),
            'axis': axis, 'zero_offset': offset, 'limits': {'lower': -2, 'upper': 2}})
    data = {'root_link': 'root', 'links': links, 'joints': joints, 'frames': [],
            'arm_home_positions': {'common': 0, 'slide': 0, 'other': 0},
            'collision_policy': {'excluded_pairs': []}}
    return SimpleNamespace(sha256='tree', data=data, links=links, joints=joints,
        frames=[], joint_names=('common', 'slide', 'other'),
        to_dict=lambda: deepcopy(data), require_capability=lambda capability: None)


class SelfCollisionCacheTests(unittest.TestCase):
    def test_common_ancestors_unrelated_joints_and_pair_order_share_exact_result(self):
        robot = tree_fixture()
        cache = _RigidPairDistanceCache(robot, None)
        q = {'common': 0, 'slide': 0, 'other': 0}
        first = cache.distance('left/solid', 'right/solid', q, .5)
        moved = {'common': 1.3, 'slide': 0, 'other': -.6}
        repeated = cache.distance('right/solid', 'left/solid', moved, .5)
        fresh = _RigidPairDistanceCache(robot, None).distance('left/solid', 'right/solid', moved, .5)
        self.assertEqual(first, repeated)
        self.assertEqual(first, fresh)
        self.assertEqual(cache.stats['hits'], 1)
        self.assertAlmostEqual(first, .18, places=14)
        # An independent full-chain FK evaluation agrees under both a base
        # rotation/translation and a common ancestor rotation.
        fk = forward_kinematics(robot, moved, pose_from_rpy([7, -4, 2], [.2, -.4, 1]))
        a, b = collision_shapes(robot, fk)
        expected = box_separation(a, shape_box(a), b, shape_box(b))
        self.assertAlmostEqual(first, expected, places=13)
        moved['slide'] = .179
        breach = cache.distance('left/solid', 'right/solid', moved, .004)
        self.assertLess(breach, .004)
        self.assertAlmostEqual(breach, .001, places=14)
        self.assertEqual(cache.stats['misses'], 2)

    def test_saturated_mesh_entries_require_recheck_for_larger_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            geometry = write_obj(Path(tmp)/'cube.obj', *cube(size=.1))
            robot = tree_fixture(geometry)
            repo = MeshRepository(tmp, [geometry])
            cache = _RigidPairDistanceCache(robot, repo)
            q = {'common': 0, 'slide': 0, 'other': 0}
            self.assertEqual(cache.distance('left/solid', 'right/solid', q, .004), .004)
            self.assertEqual(cache.distance('left/solid', 'right/solid', q, .003), .003)
            self.assertEqual(cache.stats['lower_bound_hits'], 1)
            gap = cache.distance('left/solid', 'right/solid', q, .5)
            self.assertAlmostEqual(gap, .18, places=14)
            self.assertEqual(cache.stats['cap_rechecks'], 1)
            self.assertEqual(cache.distance('left/solid', 'right/solid', q, .7), gap)
            self.assertEqual(cache.distance('left/solid', 'right/solid', q, .004), .004)
            self.assertEqual(cache.stats['exact_hits'], 2)
            q['slide'] = .179
            self.assertLess(cache.distance('left/solid', 'right/solid', q, .004), .004)

    def test_lru_is_bounded_and_changed_coordinates_are_not_quantized(self):
        cache = _RigidPairDistanceCache(tree_fixture(), None, max_entries=2)
        for slide in (0, .01, .02):
            cache.distance('left/solid', 'right/solid', {'slide': slide}, .5)
        self.assertEqual(len(cache.entries), 2)
        self.assertEqual(cache.stats['evictions'], 1)
        cache.distance('left/solid', 'right/solid', {'slide': .020000000000001}, .5)
        self.assertEqual(cache.stats['misses'], 4)
        self.assertEqual(len(cache.entries), 2)

    def test_resolved_clones_share_cache_but_different_robot_is_rejected(self):
        robot = resolve_robot_profile('proxy_v1')
        task = {'orientation_mode': 'position_direction', 'target_direction': [1, 0, 0],
                'tool_axis': [1, 0, 0], 'orientation_tolerance_rad': .03, 'tool_frame': 'cut_point'}
        config = ResolvedMotionConfig(robot, task)
        for clone in (config.for_direction([0, 1, 0]), config.for_target_cut('fruit'),
                      config.for_observed_joints({})):
            self.assertIs(clone.self_collision_cache, config.self_collision_cache)
        changed = robot.to_dict(); changed['model_name'] = 'different'
        with self.assertRaises(ValueError):
            ResolvedMotionConfig(resolve_robot_profile(changed), task,
                self_collision_cache=config.self_collision_cache)

    def test_world_base_changes_reuse_self_cache_without_changing_ground_checks(self):
        robot = tree_fixture()
        cache = _RigidPairDistanceCache(robot, None)
        def positions(values): return dict(zip(robot.joint_names, values))
        def world_shapes(values, base):
            fk = forward_kinematics(robot, positions(values), pose_from_rpy(base[:3], [0, 0, base[3]]))
            return collision_shapes(robot, fk), fk['root']
        config = SimpleNamespace(robot=robot, mesh_repository=None, task={},
            self_collision_cache=cache, positions=positions, world_shapes=world_shapes)
        first = resolved_world_clearance([0, 0, 0], [0, 0, 0, 0], [], [], None, config)
        second = resolved_world_clearance([1.1, 0, .5], [4, 5, 2, .7], [], [], None, config)
        self.assertEqual(first['self_clearance_m'], second['self_clearance_m'])
        self.assertEqual(cache.stats['hits'], 1)
        ground = resolved_world_clearance([0, 0, 0], [0, 0, -3, 0], [], [], None, config)
        self.assertLess(ground['environment_clearance_m'], .004)
        self.assertEqual(ground['limiting_environment_pair'][1], 'ground')


if __name__ == '__main__':
    unittest.main()
