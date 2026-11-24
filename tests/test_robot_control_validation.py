"""Negative observation cases, independent from the native controller code."""
import copy
import unittest

from uchuva_gazebo.robot_control_validation import evaluate_position_force_control


class PositionForceEvidenceTests(unittest.TestCase):
    def fixture(self):
        control = {'reference_mode': 'ramped_position', 'command_velocity': .2,
                   'cmd_min': -.02, 'cmd_max': .02}
        manifest = {'robot_spec_sha256': 'robot', 'robot_config': {
            'control': {'gripper': {'jaw': control}},
            'joints': [{'name': 'jaw', 'limits': {'lower': -.4, 'upper': .4, 'velocity': 1}}]},
            'robot_task': {'acceptance': {'max_telemetry_gap_s': .05,
                'joint_position_tolerance_rad': .01, 'joint_velocity_tolerance_rad_s': .03,
                'effort_tolerance_nm': 1e-6, 'orientation_state_max_age_s': .025}}}
        records, native = [], []
        for index in range(21):
            stamp = index/100
            records.append({'schema_version': 'joint-position-force/1.0',
                'robot_spec_sha256': 'robot', 'joint_name': 'jaw', 'sim_time': stamp,
                'sample_phase': 'pre_physics', 'requested_target_position_rad': .04,
                'limited_reference_rad': .2*stamp, 'measured_position_rad': .2*stamp,
                'measured_velocity_rad_s': .2, 'unsaturated_force_nm': .03,
                'force_command_nm': .02, 'saturated': True, 'command_velocity_rad_s': .2,
                'status': 'active', 'window_steps': 100, 'invalid_state_steps_window': 0,
                'saturated_steps_window': 100, 'saturated_steps_total': (index+1)*100,
                'command_sequence': 1, 'rejected_commands': 0,
                'max_abs_velocity_window': .2, 'max_abs_force_command_window': .02,
                'max_abs_unsaturated_force_window': .03, 'max_abs_reference_rate_window': .2})
            native.append({'commanded_before_step_time': stamp,
                'joints': [{'name': 'jaw', 'force_command_available': True, 'force_command': .02}]})
        samples = [{'ready': True, 'sim_time': 0}, {'ready': True, 'sim_time': .2}]
        return manifest, records, native, samples

    def test_reference_and_separate_native_command_agree(self):
        self.assertTrue(evaluate_position_force_control(*self.fixture())[0]['passed'])

    def test_bad_reference_identity_saturation_or_native_command_fails(self):
        for change in ('slew', 'identity', 'saturation', 'nan', 'force', 'missing', 'coverage',
                       'velocity_peak', 'slew_peak', 'force_peak', 'state_loss', 'window_loss'):
            with self.subTest(change=change):
                manifest, records, native, samples = copy.deepcopy(self.fixture())
                if change == 'slew': records[5]['limited_reference_rad'] += .01
                elif change == 'identity': records[5]['robot_spec_sha256'] = 'another'
                elif change == 'saturation': records[5]['saturated'] = False
                elif change == 'nan': records[5]['limited_reference_rad'] = float('nan')
                elif change == 'force': native[5]['joints'][0]['force_command'] = -.02
                elif change == 'missing': native.pop(5)
                elif change == 'coverage': records = records[:4]
                elif change == 'velocity_peak': records[5]['max_abs_velocity_window'] = 1.04
                elif change == 'slew_peak': records[5]['max_abs_reference_rate_window'] = .201
                elif change == 'force_peak': records[5]['max_abs_force_command_window'] = .0201
                elif change == 'state_loss': records[5]['status'] = 'waiting_for_native_state'
                elif change == 'window_loss': records[5]['invalid_state_steps_window'] = 1
                result = evaluate_position_force_control(manifest, records, native, samples)[0]
                self.assertFalse(result['passed'])

    def test_initial_missing_native_state_is_explicit_and_never_ready(self):
        manifest, records, native, samples = self.fixture()
        initial = {**records[0], 'sim_time': 0, 'status': 'waiting_for_native_state',
                   'measured_position_rad': None, 'measured_velocity_rad_s': None,
                   'force_command_nm': 0}
        records = records[1:]
        samples[0]['sim_time'] = .01
        result = evaluate_position_force_control(manifest, [initial]+records, native, samples)[0]
        self.assertTrue(result['passed'])
        self.assertEqual(result['initialization_samples'], 1)
        initial['sim_time'] = .01
        self.assertFalse(evaluate_position_force_control(manifest, [initial]+records, native, samples)[0]['passed'])

    def test_isolated_gripper_scope_cannot_approve_missing_arm_observations(self):
        manifest, records, native, samples = self.fixture()
        manifest['robot_config']['control']['arm'] = {
            'elbow': copy.deepcopy(manifest['robot_config']['control']['gripper']['jaw'])}
        manifest['robot_config']['joints'].append({'name': 'elbow',
            'limits': {'lower': -.4, 'upper': .4, 'velocity': 1}})
        self.assertFalse(evaluate_position_force_control(manifest, records, native, samples)[0]['passed'])
        result = evaluate_position_force_control(manifest, records, native, samples,
                                                 control_groups=('gripper',))[0]
        self.assertTrue(result['passed'])
        self.assertFalse(result['full_robot_controller_scope'])
        self.assertEqual(result['required_control_groups'], ['gripper'])
        for groups in ((), ('all',), ('gripper', 'gripper')):
            with self.assertRaises(ValueError):
                evaluate_position_force_control(manifest, records, native, samples, control_groups=groups)


if __name__ == '__main__':
    unittest.main()
