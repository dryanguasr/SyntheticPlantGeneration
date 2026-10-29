"""Regression evidence for parameter-aware validation and shared geometry."""
from copy import deepcopy
import hashlib
import json
import math
from types import SimpleNamespace
import unittest

from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.parameters import get_initial_parameters
from uchuva_lsystem.validation import validate_morphology_tree
from uchuva_lsystem.geometry_contracts import (
    axis_sag_factor, stem_centerline_points, bounds_from_points,
    compare_fruit_calyx_bounds, summarize_geometry_envelopes,
)
from uchuva_lsystem.collisions import _append_axis_proxies, _append_leaf_proxies
from uchuva_lsystem.organ_frames import local_cone_leaf_direction, orthogonal_leaf_direction
from uchuva_lsystem.scene import PlantInstance


def attach_snapshot(plant, params):
    plant.metadata['effective_parameters'] = deepcopy(params)
    plant.metadata['effective_parameters_sha256'] = hashlib.sha256(json.dumps(
        params, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
        allow_nan=False).encode()).hexdigest()


class ParameterValidationTests(unittest.TestCase):
    def setUp(self):
        self.params = get_initial_parameters()
        self.plant = generate_morphology_tree(11, self.params)

    def test_missing_historical_snapshot_is_reported_not_invented(self):
        report = validate_morphology_tree(self.plant)
        self.assertFalse(report['parameter_contract']['contract_available'])
        self.assertEqual(report['parameter_contract']['source'], 'legacy_snapshot_missing')

    def test_effective_leaf_ranges_replace_old_near_planar_constants(self):
        attach_snapshot(self.plant, self.params)
        leaf = self.plant.axes[0].nodes[0].leaf
        leaf.curl, leaf.twist_deg = .15, 7.5
        report = validate_morphology_tree(self.plant)
        self.assertFalse(any(leaf.id in w['message'] and ('curl=' in w['message']
                             or 'twist_deg=' in w['message']) for w in report['warnings']))
        leaf.curl = .5
        report = validate_morphology_tree(self.plant)
        self.assertTrue(any(leaf.id in w['message'] and 'curl=' in w['message']
                            for w in report['warnings']))

    def test_snapshot_corruption_and_conflicting_override_are_detected(self):
        attach_snapshot(self.plant, self.params)
        conflicting = deepcopy(self.params)
        conflicting['leaf']['curl_range']['max'] = .7
        report = validate_morphology_tree(self.plant, params=conflicting)
        self.assertEqual(report['status'], 'invalid')
        self.assertTrue(any('Explicit parameters' in e['message'] for e in report['errors']))
        self.plant.metadata['effective_parameters']['leaf']['curl_range']['max'] = .7
        report = validate_morphology_tree(self.plant)
        self.assertFalse(report['parameter_contract']['snapshot_verified'])
        self.assertTrue(any('snapshot hash' in e['message'] for e in report['errors']))

    def test_light_proxies_only_required_after_adaptation(self):
        self.plant.metadata['light_competition'] = {'enabled': True}
        generated = validate_morphology_tree(self.plant, stage='generated')
        adapted = validate_morphology_tree(self.plant, stage='adapted')
        self.assertEqual(generated['checks']['stratified_light_response'],
                         'not_required_before_scene_adaptation')
        self.assertFalse(any('missing daily_light' in w['message'] for w in generated['warnings']))
        self.assertTrue(any('missing daily_light' in w['message'] for w in adapted['warnings']))

    def test_radius_uses_parent_insertion_not_parent_maximum(self):
        axis = next(a for a in self.plant.axes if a.child_axes)
        child = axis.child_axes[0]
        index = next(i for i, node in enumerate(axis.nodes) if node.id == child.parent_node_id)
        axis.internodes[index].radius_cm = .01
        child.internodes[0].radius_cm = .02
        report = validate_morphology_tree(self.plant, params=self.params)
        self.assertTrue(any('exceeds the parent at insertion' in e['message'] for e in report['errors']))

    def test_nonfinite_geometry_and_stale_counts_fail_integrity(self):
        self.plant.axes[0].internodes[0].radius_cm = math.nan
        self.plant.metadata['reproductive_counts_by_stage'] = {'generated': {
            'reproductive_units': -1, 'flowers': 0, 'fruits': 0, 'fruits_with_calyx': 0}}
        report = validate_morphology_tree(self.plant)
        self.assertEqual(report['status'], 'invalid')
        self.assertTrue(any(e['category'] == 'integrity' for e in report['errors']))
        self.assertTrue(any('counts differ' in e['message'] for e in report['errors']))

    def test_new_generator_snapshot_has_no_false_taper_or_leaf_contract_warnings(self):
        for seed in (0, 2, 6):
            plant = generate_morphology_tree(seed, preset_name='trained_trellis_audit_v2',
                                            phenology_model='literature_cohort_v1')
            report = validate_morphology_tree(plant)
            self.assertTrue(report['parameter_contract']['snapshot_verified'])
            self.assertFalse(report['errors'])
            self.assertFalse([w for w in report['warnings'] if w['category'] == 'parameter_contract'])
        self.assertGreater(report['summary']['fruiting_reproductive_unit_count'], 10)

    def test_wrong_leaf_attachment_is_an_integrity_error(self):
        self.plant.axes[0].nodes[0].leaf.node_id = 'unrelated_node'
        report = validate_morphology_tree(self.plant)
        self.assertEqual(report['status'], 'invalid')
        self.assertTrue(any('associated with the wrong node' in e['message'] for e in report['errors']))


class SharedGeometryTests(unittest.TestCase):
    def test_trained_phases_remove_sag_in_proxies_and_renderer_contract(self):
        axis = SimpleNamespace(order=1, reproductive_load=.6, training_phase='normal')
        normal = stem_centerline_points((0, 0, 1), (2, 0, 1), axis_sag_factor(axis))
        self.assertLess(normal[2][2], 1)
        for phase in ('overhead_strings_manual_initial_guess', 'bouquet_open_and_lift_v4'):
            axis.training_phase = phase
            trained = stem_centerline_points((0, 0, 1), (2, 0, 1), axis_sag_factor(axis))
            self.assertEqual([p[2] for p in trained], [1] * 6)

    def test_tangent_curve_retains_endpoints_and_does_not_double_apply_sag(self):
        args = ((0, 0, 0), (2, 0, 1))
        tangents = ((1, 0, 0), (0, 0, 1))
        first = stem_centerline_points(*args, 0, endpoint_tangents=tangents, points_count=13)
        second = stem_centerline_points(*args, 1, endpoint_tangents=tangents, points_count=13)
        self.assertEqual(first, second)
        self.assertEqual(first[0], args[0])
        self.assertEqual(first[-1], args[1])
        self.assertLess(first[1][2], .01)
        self.assertLess(abs(first[-2][0] - 2), .03)

    def test_axis_proxy_honours_trained_sag_and_continuous_tangents(self):
        plant = generate_morphology_tree(5)
        axis = plant.axes[0]
        axis.child_axes = []
        axis.nodes = []
        axis.internodes = axis.internodes[:1]
        axis.internodes[0].bend_angle_deg = 0
        axis.training_phase = 'overhead_strings_manual_initial_guess'
        axis.mechanical_deflection_deg = 0
        axis.resolved_direction = (1, 0, 0)
        instance = PlantInstance('fixture', 5)
        proxies = []
        _append_axis_proxies(proxies, axis, instance=instance, start=(0,0,1),
                            parent_direction=(0,0,1), node_frames={})
        self.assertEqual(len(proxies), 5)
        self.assertTrue(all(p.start[2] == p.end[2] == 1 for p in proxies))
        axis.provenance['continuous_tangent_v140'] = True
        proxies = []
        _append_axis_proxies(proxies, axis, instance=instance, start=(0,0,1),
                            parent_direction=(0,0,1), node_frames={})
        self.assertEqual(len(proxies), 12)

    def test_bounds_do_not_claim_solid_containment_or_occlusion(self):
        calyx = bounds_from_points([(-1,-1,-2),(1,1,2)])
        fruit = bounds_from_points([(-.5,-.5,-.5),(.5,.5,.5)])
        inside = compare_fruit_calyx_bounds(fruit, calyx)
        self.assertFalse(inside['fruit_outside_calyx_aabb'])
        self.assertEqual(inside['solid_containment'], 'not_established')
        self.assertEqual(inside['visual_occlusion'], 'not_measured')
        outside = compare_fruit_calyx_bounds(bounds_from_points([(0,0,0),(3,0,0)]), calyx)
        self.assertTrue(outside['fruit_outside_calyx_aabb'])

    def test_canopy_envelope_uses_union_not_sum_of_branches(self):
        bounds = bounds_from_points([(-1,-1,0),(1,1,4)])
        rows = [dict(name=f'leaf{i}', plant_id='p', semantic='leaf',
                     reproductive_instance_id='', bounds=bounds) for i in range(100)]
        report = summarize_geometry_envelopes(rows)
        self.assertEqual(report['plants']['p']['extent'], [2,2,4])
        self.assertEqual(report['plants']['p']['width_to_height'], .5)
        with self.assertRaises(ValueError):
            bounds_from_points([(0,0,math.nan)])


class LeafPoseValidationTests(unittest.TestCase):
    def setUp(self):
        self.plant = generate_morphology_tree(2026102600,
            preset_name='trained_trellis_bush_pose_audit_v4',
            phenology_model='literature_cohort_v1')
        self.leaf = self.plant.axes[0].nodes[0].leaf

    def test_generated_pose_matches_effective_frame_and_range(self):
        report = validate_morphology_tree(self.plant, stage='generated')
        self.assertFalse(report['errors'])
        self.assertFalse([w for w in report['warnings'] if w['category'] == 'parameter_contract'])

    def test_frame_or_sampling_provenance_mismatch_is_rejected(self):
        self.leaf.provenance['insertion_frame'] = 'global_legacy'
        self.leaf.provenance['pose_sampling']['range_min_deg'] = 55
        report = validate_morphology_tree(self.plant)
        self.assertTrue(any('insertion_frame differs' in e['message'] for e in report['errors']))
        self.assertTrue(any('pose_sampling differs' in e['message'] for e in report['errors']))

    def test_generated_angles_must_be_valid_samples_not_just_finite(self):
        self.leaf.insertion_angle_deg = 95
        self.leaf.preferred_insertion_angle_deg = 20
        report = validate_morphology_tree(self.plant)
        self.assertTrue(any('insertion_angle_deg=95' in e['message'] for e in report['errors']))
        self.assertTrue(any('preferred_insertion_angle_deg=20' in e['message'] for e in report['errors']))
        self.leaf.insertion_angle_deg = math.nan
        self.assertTrue(any('nonfinite' in e['message'] for e in validate_morphology_tree(self.plant)['errors']))

    def test_adapted_pose_may_leave_sampled_range_with_original_preserved(self):
        self.leaf.insertion_angle_deg = 120
        self.leaf.orientation_adjustment_deg = abs(120-self.leaf.preferred_insertion_angle_deg)
        self.leaf.orientation_cost_terms = {'collision': 0.0}
        report = validate_morphology_tree(self.plant, stage='adapted')
        self.assertFalse(report['errors'])
        self.assertFalse([w for w in report['warnings'] if 'insertion angle' in w['message']])
        self.leaf.preferred_insertion_angle_deg = 120
        self.assertTrue(any('preferred_insertion_angle_deg' in e['message']
                            for e in validate_morphology_tree(self.plant, stage='adapted')['errors']))

    def test_undocumented_adapted_pose_warns_but_does_not_redefine_range(self):
        self.leaf.insertion_angle_deg = 120
        report = validate_morphology_tree(self.plant, stage='adapted')
        self.assertFalse(report['errors'])
        self.assertTrue(any('pose-adjustment record' in w['message'] for w in report['warnings']))

    def test_historical_presets_do_not_invent_pose_sampling_contract(self):
        plant = generate_morphology_tree(1, preset_name='trained_trellis_audit_v2')
        leaf = plant.axes[0].nodes[0].leaf
        leaf.preferred_insertion_angle_deg = None
        report = validate_morphology_tree(plant)
        self.assertFalse([e for e in report['errors'] if 'insertion' in e['message'] or 'pose_sampling' in e['message']])


class LocalConeLeafTests(unittest.TestCase):
    def test_horizontal_stem_retains_vertical_radial_variation(self):
        historical = [orthogonal_leaf_direction((1,0,0), az, 55) for az in (45,90,225,270)]
        self.assertTrue(all(abs(direction[2]) < 1e-10 for direction in historical))
        upward = local_cone_leaf_direction((1,0,0), 90, 55)
        downward = local_cone_leaf_direction((1,0,0), 270, 55)
        self.assertGreater(upward[2], .8)
        self.assertLess(downward[2], -.8)

    def test_local_cone_preserves_requested_angle_and_unit_length(self):
        for axis in ((0,0,1),(1,0,0),(.8,.2,.4)):
            norm = math.sqrt(sum(v*v for v in axis))
            for azimuth in (0,45,90,230):
                for angle in (30,55,80):
                    direction = local_cone_leaf_direction(axis, azimuth, angle)
                    self.assertAlmostEqual(sum(v*v for v in direction), 1, places=10)
                    self.assertAlmostEqual(sum(v*a/norm for v,a in zip(direction,axis)),
                                           math.cos(math.radians(angle)), places=10)

    def test_proxy_petiole_uses_same_local_cone_without_a_camera(self):
        plant = generate_morphology_tree(2026102600, preset_name='trained_trellis_bush_pose_audit_v4')
        leaf = plant.axes[0].nodes[0].leaf
        leaf.provenance['insertion_frame'] = 'local_cone_v2'
        leaf.azimuth_deg, leaf.insertion_angle_deg = 90,55
        proxies = []
        _append_leaf_proxies(proxies, leaf, (0,0,0), (1,0,0), PlantInstance('fixture',1))
        petiole = next(p for p in proxies if p.kind == 'petiole')
        expected = local_cone_leaf_direction((1,0,0),90,55)
        for actual, desired in zip(petiole.end, expected):
            self.assertAlmostEqual(actual, desired*leaf.petiole_length_cm*.08, places=10)

    def test_invalid_new_frame_inputs_fail_explicitly(self):
        for axis,azimuth,angle in (((0,0,0),30,55),((math.nan,0,1),30,55),
                                  ((1,0,0),math.nan,55),((1,0,0),30,181)):
            with self.assertRaises(ValueError):
                local_cone_leaf_direction(axis,azimuth,angle)

    def test_adult_v5_leaf_range_is_validated_without_legacy_vigor_penalty(self):
        for seed in range(2026102600,2026102604):
            plant = generate_morphology_tree(seed, preset_name='trained_trellis_broad_crown_audit_v5',
                                            phenology_model='literature_cohort_v1')
            report = validate_morphology_tree(plant)
            self.assertFalse(report['errors'])
            self.assertFalse([w for w in report['warnings'] if w['category'] == 'parameter_contract'])


if __name__ == '__main__':
    unittest.main()
