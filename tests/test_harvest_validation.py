"""Artificial telemetry fixtures exercise the auditor, never native evidence.

These tests deliberately manufacture JSON-shaped observations. A passing test
proves only that acceptance/rejection logic distinguishes the counterexamples;
it is not a Gazebo run or a claim of a successful physical harvest.
"""
from copy import deepcopy
import math
import unittest

from uchuva_gazebo.harvest_validation import (
    deposited_interval, evaluate_harvest_run, local_point, rotate_vector,
    sphere_in_bin, world_point, yaw_of,
)


def artificial_fixture():
    """A smooth, idealized two-fruit trace with one complete retained harvest."""
    manifest = {
        'fixture_provenance': 'artificial_unit_test_not_gazebo_evidence',
        'fruits': [
            {'id': 'target', 'center_world_m': [.6, 0, .6], 'radius_m': .02},
            {'id': 'untouched', 'center_world_m': [-.6, 0, .65], 'radius_m': .02},
        ],
        'bin': {'inner_min_m': [.25, .05, .4], 'inner_max_m': [.55, .35, .65]},
    }
    samples = []
    for i in range(131):
        t = i * .05
        fruit_position = [.6, 0, .6]
        state, parent, present, pending = 'ATTACHED', 'plant', True, False
        tool = [0, 0, .64]
        ready = True
        residual = .001
        if i <= 41:
            phase = 'baseline'
        else:
            phase = 'mission'
            a = max(0, min(1, (t-2.1)/.4))
            tool = [.6*a, 0, .64]
        if 50 <= i < 65:
            state = 'ARMED'
            if i <= 55:
                a = (i-50)/5
                tool = [.6-.1*a, 0, .64+.1*a]
            elif i <= 60:
                a = (i-55)/5
                tool = [.5+.1*a, 0, .74-.1*a]
            else:
                tool = [.6, 0, .64]
        if i == 65:
            state, parent, present, pending = 'CUT_PENDING', 'none', False, True
        elif 66 <= i <= 92:
            state, parent = 'HELD', 'tool'
            a = (i-66)/(92-66)
            fruit_position = [.6-.2*a, .2*a, .6-.08*a]
            tool = [fruit_position[0], fruit_position[1], fruit_position[2]+.04]
            if i == 66:
                ready, residual = False, None  # new joint, before first physics observation
        elif i >= 93:
            fruit_position = [.4, .2, .52]
            tool = [.4, .2, .56]
            parent, present = 'none', False
            residual = None
            if i == 93:
                state, pending = 'RELEASE_PENDING', True
            else:
                state = 'RELEASED'
                a = min(1, (i-94)/8)
                fruit_position[2] = .52-.07*a
        target = {'id': 'target', 'state': state, 'position': fruit_position,
                  'joint_present': present, 'joint_parent': parent,
                  'removal_pending': pending, 'constraint_error_m': residual}
        untouched = {'id': 'untouched', 'state': 'ATTACHED', 'position': [-.6, 0, .65],
                     'joint_present': True, 'joint_parent': 'plant',
                     'removal_pending': False, 'constraint_error_m': .001}
        displacement = .2*max(0, min(1, (t-2.1)/1.0))
        samples.append({'sim_time': t, 'ready': ready,
                        'status': 'ready' if ready else 'initializing', 'phase': phase,
                        'robot_pose': [displacement, 0, 0, 0, 0, 0, 1],
                        'tool_pose': [*tool, 0, 0, 0, 1], 'fruits': [target, untouched]})
    events = []

    def event(t, identifier, action, accepted, client_phase='', reason='fixture', phase='ack'):
        events.append({'schema_version': 1, 'seq': len(events)+1, 'sim_time': t,
                       'id': identifier, 'action': action, 'accepted': accepted,
                       'client_phase': client_phase, 'reason': reason, 'phase': phase})

    event(2.1, 'unknown_fruit', 'arm', False, reason='unknown_fruit')
    event(2.15, 'target', 'arm', False, 'negative_far', 'cut_point_out_of_range')
    event(2.2, 'target', 'cut', False, 'negative_far', 'state_must_be_ARMED')
    event(2.5, 'target', 'arm', True)
    event(2.75, 'target', 'cut', False, 'negative_armed_far', 'cut_point_out_of_range')
    event(3.25, 'target', 'cut', True)
    event(3.3, 'target', 'cut', True, phase='result')
    event(3.45, 'target', 'cut', False, 'negative_repeat', 'state_must_be_ARMED')
    event(4.65, 'target', 'release', True)
    event(4.7, 'target', 'release', True, phase='result')
    return manifest, samples, events


def checks(report):
    return {entry['name']: entry for entry in report['checks']}


class HarvestValidationTests(unittest.TestCase):
    def test_artificial_complete_trace_passes_but_is_not_native_evidence(self):
        manifest, samples, events = artificial_fixture()
        report = evaluate_harvest_run(manifest, samples, events, ['target'])
        self.assertTrue(report['passed'], [c for c in report['checks'] if not c['passed']])
        self.assertEqual(manifest['fixture_provenance'], 'artificial_unit_test_not_gazebo_evidence')
        self.assertTrue(checks(report)['target:settled_in_bin']['passed'])

    def test_command_acknowledgements_without_retained_motion_cannot_pass(self):
        manifest, samples, events = artificial_fixture()
        for sample in samples:
            target = sample['fruits'][0]
            if target['state'] == 'HELD':
                target['position'] = [.6, 0, .6]
                sample['tool_pose'] = [.6, 0, .64, 0, 0, 0, 1]
        report = evaluate_harvest_run(manifest, samples, events, ['target'])
        self.assertFalse(report['passed'])
        self.assertFalse(checks(report)['target:physical_retention']['passed'])
        self.assertTrue(checks(report)['target:one_cut']['passed'])

    def test_released_label_outside_bin_is_not_a_deposit(self):
        manifest, samples, events = artificial_fixture()
        for sample in samples:
            if sample['fruits'][0]['state'] == 'RELEASED':
                sample['fruits'][0]['position'] = [.65, .2, .45]
        report = evaluate_harvest_run(manifest, samples, events, ['target'])
        self.assertFalse(report['passed'])
        self.assertFalse(checks(report)['target:settled_in_bin']['passed'])

    def test_center_inside_bin_does_not_substitute_for_whole_fruit_containment(self):
        manifest, _, _ = artificial_fixture()
        self.assertTrue(sphere_in_bin([.4, .2, .45], .02, manifest['bin']))
        self.assertFalse(sphere_in_bin([.26, .2, .45], .02, manifest['bin']))
        self.assertFalse(sphere_in_bin([.4, .2, .405], .02, manifest['bin']))

    def test_deposit_needs_consecutive_low_speed_duration(self):
        manifest, samples, _ = artificial_fixture()
        settled = [s for s in samples if s['sim_time'] >= 5.15]
        self.assertTrue(deposited_interval(settled, 'target', .02, manifest['bin'])['passed'])
        self.assertFalse(deposited_interval(settled[:10], 'target', .02, manifest['bin'])['passed'])
        oscillating = deepcopy(settled)
        for i, sample in enumerate(oscillating):
            sample['fruits'][0]['position'][0] += .004*(-1)**i
        self.assertFalse(deposited_interval(oscillating, 'target', .02, manifest['bin'])['passed'])
        interrupted = deepcopy(settled)
        for i in range(7, len(interrupted), 7):
            interrupted[i]['fruits'][0]['position'][0] = .7
        self.assertFalse(deposited_interval(interrupted, 'target', .02, manifest['bin'])['passed'])

    def test_teleport_reset_gap_and_extra_fruit_each_fail(self):
        for fault in ('fruit_teleport', 'robot_teleport', 'tool_teleport', 'reset', 'gap', 'extra_fruit'):
            with self.subTest(fault=fault):
                manifest, samples, events = artificial_fixture()
                if fault == 'fruit_teleport':
                    samples[80]['fruits'][0]['position'][0] += .5
                elif fault == 'robot_teleport':
                    samples[80]['robot_pose'][0] += 2
                elif fault == 'tool_teleport':
                    samples[80]['tool_pose'][0] += 2
                elif fault == 'reset':
                    samples[80]['sim_time'] = .1
                elif fault == 'gap':
                    del samples[60:70]
                else:
                    extra = deepcopy(samples[80]['fruits'][1])
                    extra['id'] = 'unexpected_new_fruit'
                    samples[80]['fruits'].append(extra)
                report = evaluate_harvest_run(manifest, samples, events, ['target'])
                self.assertFalse(report['passed'])
                expected = 'no_large_pose_jumps' if fault.endswith('teleport') else 'telemetry_integrity'
                self.assertFalse(checks(report)[expected]['passed'])

    def test_unrequested_fruit_detachment_is_rejected(self):
        manifest, samples, events = artificial_fixture()
        for sample in samples[85:]:
            sample['fruits'][1].update(state='RELEASED', joint_present=False,
                joint_parent='none', removal_pending=False, constraint_error_m=None)
        report = evaluate_harvest_run(manifest, samples, events, ['target'])
        self.assertFalse(report['passed'])
        self.assertEqual(checks(report)['no_unrequested_detachments']['unexpected_ids'], ['untouched'])

    def test_latch_residual_and_tool_relative_slip_are_independent_gates(self):
        for fault in ('residual', 'slip'):
            with self.subTest(fault=fault):
                manifest, samples, events = artificial_fixture()
                for i in range(75, 85):
                    if fault == 'residual':
                        samples[i]['fruits'][0]['constraint_error_m'] = .04
                    else:
                        samples[i]['tool_pose'][1] += .04
                report = evaluate_harvest_run(manifest, samples, events, ['target'])
                self.assertFalse(report['passed'])
                self.assertFalse(checks(report)['target:physical_retention']['passed'])

    def test_malformed_shapes_quaternions_and_constraint_evidence_fail_as_reports(self):
        faults = ('short_position', 'short_pose', 'zero_quaternion', 'nan_position',
                  'null_held_residual', 'nan_held_residual', 'negative_residual',
                  'string_joint_flag', 'wrong_joint_parent', 'missing_fruit', 'duplicate_fruit',
                  'released_still_attached', 'runtime_error')
        for fault in faults:
            with self.subTest(fault=fault):
                manifest, samples, events = artificial_fixture()
                sample, fruit = samples[80], samples[80]['fruits'][0]
                if fault == 'short_position': fruit['position'] = []
                elif fault == 'short_pose': sample['tool_pose'] = [0, 0, 0, 1]
                elif fault == 'zero_quaternion': sample['robot_pose'][3:7] = [0]*4
                elif fault == 'nan_position': fruit['position'][0] = float('nan')
                elif fault == 'null_held_residual': fruit['constraint_error_m'] = None
                elif fault == 'nan_held_residual': fruit['constraint_error_m'] = float('nan')
                elif fault == 'negative_residual': fruit['constraint_error_m'] = -.01
                elif fault == 'string_joint_flag': fruit['joint_present'] = 'true'
                elif fault == 'wrong_joint_parent': fruit['joint_parent'] = 'plant'
                elif fault == 'missing_fruit': sample['fruits'].pop()
                elif fault == 'duplicate_fruit': sample['fruits'].append(deepcopy(fruit))
                elif fault == 'released_still_attached': samples[120]['fruits'][0]['joint_present'] = True
                elif fault == 'runtime_error': sample['status'] = 'error'
                report = evaluate_harvest_run(manifest, samples, events, ['target'])
                self.assertFalse(report['passed'])
                self.assertFalse(checks(report)['telemetry_integrity']['passed'])

    def test_transition_before_physics_is_preserved_but_not_retention_evidence(self):
        manifest, samples, events = artificial_fixture()
        self.assertIsNone(samples[66]['fruits'][0]['constraint_error_m'])
        self.assertFalse(samples[66]['ready'])
        report = evaluate_harvest_run(manifest, samples, events, ['target'])
        self.assertTrue(report['passed'])
        # Claiming HELD forever without a measured constraint cannot pass.
        for sample in samples:
            if sample['fruits'][0]['state'] == 'HELD':
                sample['ready'] = False
                sample['status'] = 'initializing'
                sample['fruits'][0]['constraint_error_m'] = None
        report = evaluate_harvest_run(manifest, samples, events, ['target'])
        self.assertFalse(report['passed'])
        self.assertFalse(checks(report)['target:physical_retention']['passed'])

    def test_disconnected_held_episodes_cannot_manufacture_duration(self):
        manifest, samples, events = artificial_fixture()
        samples[80]['fruits'][0].update(state='RELEASED', joint_present=False,
            joint_parent='none', removal_pending=False, constraint_error_m=None)
        report = evaluate_harvest_run(manifest, samples, events, ['target'])
        self.assertFalse(report['passed'])
        self.assertFalse(checks(report)['telemetry_integrity']['passed'])

    def test_transforms_include_translation_roll_pitch_and_quaternion_normalization(self):
        # 90 degrees about X: local +Y becomes world +Z, then translate.
        h = math.sqrt(.5)
        base = [1, 2, 3, 3*h, 0, 0, 3*h]
        point = [.2, .3, .4]
        transformed = world_point(point, base)
        for a, b in zip(transformed, [1.2, 1.6, 3.3]): self.assertAlmostEqual(a, b)
        for a, b in zip(local_point(transformed, base), point): self.assertAlmostEqual(a, b)
        # A nontrivial quaternion is tested with its equivalent negative scale.
        q = [.3, -.4, .2, .7]
        rotated = rotate_vector(q, point)
        for a, b in zip(rotate_vector([-5*x for x in q], point), rotated): self.assertAlmostEqual(a, b)
        for a, b in zip(rotate_vector(q, rotated, inverse=True), point): self.assertAlmostEqual(a, b)
        self.assertAlmostEqual(yaw_of([0, 0, 0, 0, 0, 3*h, 3*h]), math.pi/2)

    def test_retention_accepts_rigid_offset_during_tool_rotation(self):
        manifest, samples, events = artificial_fixture()
        offset = [.02, .03, -.04]
        for i, sample in enumerate(samples):
            if sample['fruits'][0]['state'] == 'HELD':
                angle = (i-66)*.025
                quaternion = [0, math.sin(angle/2), 0, math.cos(angle/2)]
                rotated_offset = rotate_vector(quaternion, offset)
                position = [a-b for a, b in zip(sample['fruits'][0]['position'], rotated_offset)]
                sample['tool_pose'] = position + quaternion
        report = evaluate_harvest_run(manifest, samples, events, ['target'])
        self.assertTrue(report['passed'], [c for c in report['checks'] if not c['passed']])

    def test_negative_armed_cut_must_fail_for_distance_not_wrong_state(self):
        manifest, samples, events = artificial_fixture()
        event = next(e for e in events if e['client_phase'] == 'negative_armed_far')
        event['reason'] = 'state_must_be_ARMED'
        report = evaluate_harvest_run(manifest, samples, events, ['target'])
        self.assertFalse(report['passed'])
        self.assertFalse(checks(report)['target:armed_distant_cut_rejected']['passed'])

    def test_out_of_order_commands_failed_result_and_runtime_abort_fail(self):
        for fault in ('order', 'failed_result', 'abort'):
            with self.subTest(fault=fault):
                manifest, samples, events = artificial_fixture()
                kwargs = {}
                if fault == 'order':
                    next(e for e in events if e['action'] == 'arm' and e['accepted'])['sim_time'] = 4
                elif fault == 'failed_result':
                    next(e for e in events if e['phase'] == 'result')['accepted'] = False
                else:
                    kwargs['execution_error'] = 'simulator exited early'
                report = evaluate_harvest_run(manifest, samples, events, ['target'], **kwargs)
                self.assertFalse(report['passed'])

    def test_vertical_base_bounce_is_not_four_wheel_driving(self):
        manifest, samples, events = artificial_fixture()
        for sample in samples:
            sample['robot_pose'][2] = sample['robot_pose'][0]
            sample['robot_pose'][0] = 0
        report = evaluate_harvest_run(manifest, samples, events, ['target'])
        self.assertFalse(report['passed'])
        self.assertFalse(checks(report)['base_really_moved']['passed'])

    def test_smoke_passes_only_without_detachment_and_no_samples_fail_closed(self):
        manifest, samples, events = artificial_fixture()
        smoke = samples[:49]
        report = evaluate_harvest_run(manifest, smoke, events[:3], ['target'], mode='smoke')
        self.assertTrue(report['passed'], [c for c in report['checks'] if not c['passed']])
        self.assertFalse(evaluate_harvest_run(manifest, samples, events, ['target'], mode='smoke')['passed'])
        self.assertFalse(evaluate_harvest_run(manifest, [], [], ['target'])['passed'])
        self.assertFalse(evaluate_harvest_run(manifest, samples, events, ['target', 'target'])['passed'])

    def test_initializing_only_cannot_satisfy_smoke_physics_readiness(self):
        manifest, samples, events = artificial_fixture()
        smoke = samples[:49]
        for sample in smoke:
            sample['ready'] = False
            sample['status'] = 'initializing'
            for fruit in sample['fruits']:
                fruit['constraint_error_m'] = None
        report = evaluate_harvest_run(manifest, smoke, events[:3], ['target'], mode='smoke')
        self.assertFalse(report['passed'])
        self.assertFalse(checks(report)['attached_without_commands']['passed'])
        self.assertFalse(checks(report)['runtime_ready_at_end']['passed'])


if __name__ == '__main__':
    unittest.main()
