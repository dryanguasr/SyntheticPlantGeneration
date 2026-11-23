"""Native observation joins must not turn missing or rejected evidence into PASS."""
import copy
import unittest
from unittest.mock import patch

from uchuva_gazebo.robot_validation import evaluate_native_mechanisms


class ObservedRobot:
    sha256 = 'native-fixture-hash'
    data = {
        'model_name': 'native_fixture',
        'links': [{'name': name} for name in
                  ('carrier_left', 'carrier_aux', 'gripper_short', 'gripper_aux')],
        'closures': [
            {'name': 'suspension', 'body': 'carrier_left', 'auxiliary': 'carrier_aux'},
            {'name': 'gripper', 'body': 'gripper_short', 'auxiliary': 'gripper_aux'}],
        'gear_couplings': [{'name': 'gears', 'driver': 'driver', 'follower': 'follower',
                            'ratio': -1, 'offset': 0}]}
    links = data['links']

    def to_dict(self):
        return copy.deepcopy(self.data)


class NativeMechanismObservationTests(unittest.TestCase):
    def setUp(self):
        self.robot = ObservedRobot()
        self.manifest = {'robot_config': {'fixture': True}, 'robot_task': {'acceptance': {
            'max_telemetry_gap_s': .05, 'joint_position_tolerance_rad': .01,
            'joint_velocity_tolerance_rad_s': .01, 'effort_tolerance_nm': .001,
            'orientation_state_max_age_s': .02}}}
        self.samples = [{'ready': True, 'sim_time': 1.}, {'ready': True, 'sim_time': 1.30}]
        self.records, self.poses = [], []
        for index in range(31):
            stamp = round(1 + index * .01, 8)
            self.records.append({'schema_version': 'robot-telemetry/1.0',
                'robot_spec_sha256': self.robot.sha256, 'sim_time': round(stamp+.0001, 8),
                'commanded_before_step_time': stamp,
                'measured_after_step_time': round(stamp+.0001, 8), 'joints': [
                    {'name': 'driver', 'position': .04, 'position_available': True,
                     'force_command_available': True, 'force_command': .002,
                     'max_abs_force_command_window': .002},
                    {'name': 'follower', 'position': -.04, 'position_available': True,
                     'force_command_available': False, 'force_command': None,
                     'max_abs_force_command_window': 0}]})
            self.poses.append({'schema_version': 'native-robot-link-poses/1.0',
                'robot_spec_sha256': self.robot.sha256, 'frame_id': 'native_fixture',
                'sim_time': stamp, 'links': {link['name']: {
                    'xyz_m': [.1, .2, .3], 'quaternion_xyzw': [0, 0, 0, 1]}
                    for link in self.robot.links}})

    def evaluate(self):
        # Only the configuration loader is replaced. The observation audit is
        # real; these inputs contain no FK prediction or command-as-position.
        with patch('uchuva_gazebo.robot_validation.resolve_robot_profile', return_value=self.robot):
            return evaluate_native_mechanisms(self.manifest, self.records, self.poses, self.samples)[0]

    def test_complete_native_observations_pass_without_fk_substitution(self):
        result = self.evaluate()
        self.assertTrue(result['passed'])
        self.assertTrue(result['complete_coverage'])
        self.assertEqual(result['sample_count'], 31)
        self.assertEqual(result['metrics']['gears']['maximum_coordinate_error_rad'], 0)

    def test_missing_native_pose_stream_or_missing_link_fails_closed(self):
        original = self.poses
        self.poses = []
        self.assertFalse(self.evaluate()['passed'])
        self.poses = copy.deepcopy(original)
        del self.poses[15]['links']['gripper_aux']
        self.assertFalse(self.evaluate()['passed'])

    def test_stale_or_future_joint_coordinates_fail_join(self):
        original = copy.deepcopy(self.records)
        self.records = [copy.deepcopy(original[0])]
        self.records[0].update(sim_time=.9001, commanded_before_step_time=.9, measured_after_step_time=.9001)
        self.assertFalse(self.evaluate()['passed'])
        self.records = original
        for row in self.records:
            for key in ('sim_time', 'commanded_before_step_time', 'measured_after_step_time'):
                row[key] += 1
        self.assertFalse(self.evaluate()['passed'])

    def test_nearby_iteration_cannot_replace_exact_native_physics_step(self):
        for row in self.records:
            for key in ('sim_time', 'commanded_before_step_time', 'measured_after_step_time'):
                row[key] += .0001
        result = self.evaluate()
        self.assertFalse(result['passed'])
        self.assertTrue(any('exact physics step' in error for error in result['errors']))

    def test_inconsistent_native_after_step_timestamp_fails_closed(self):
        self.records[15]['measured_after_step_time'] += .0001
        self.assertFalse(self.evaluate()['passed'])

    def test_profile_and_frame_identity_are_required(self):
        original_poses, original_records = copy.deepcopy(self.poses), copy.deepcopy(self.records)
        for field in ('robot_spec_sha256', 'frame_id'):
            self.poses = copy.deepcopy(original_poses)
            self.poses[15][field] = 'another-robot'
            self.assertFalse(self.evaluate()['passed'])
        self.poses = original_poses
        self.records = original_records
        self.records[15]['robot_spec_sha256'] = 'another-robot'
        self.assertFalse(self.evaluate()['passed'])

    def test_any_follower_motor_window_rejects_even_with_zero_final_command(self):
        self.records[15]['joints'][1]['max_abs_force_command_window'] = .001
        self.assertFalse(self.evaluate()['passed'])

    def test_rejected_gear_peak_remains_visible(self):
        self.records[15]['joints'][1]['position'] += .0011
        result = self.evaluate()
        self.assertFalse(result['passed'])
        self.assertAlmostEqual(result['metrics']['gears']['maximum_coordinate_error_rad'], .0011)

    def test_rejected_closure_peak_remains_visible(self):
        self.poses[15]['links']['gripper_aux']['xyz_m'][0] += .0006
        result = self.evaluate()
        self.assertFalse(result['passed'])
        self.assertAlmostEqual(result['metrics']['gripper']['maximum_position_error_m'], .0006)

    def test_nonfinite_timestamp_cannot_be_discarded_as_outside_interval(self):
        self.poses[15]['sim_time'] = float('nan')
        self.assertFalse(self.evaluate()['passed'])

    def test_duplicate_pose_time_and_missing_interior_coverage_fail(self):
        original = copy.deepcopy(self.poses)
        self.poses[15]['sim_time'] = self.poses[14]['sim_time']
        self.assertFalse(self.evaluate()['passed'])
        self.poses = original[:12] + original[20:]
        result = self.evaluate()
        self.assertFalse(result['passed'])
        self.assertFalse(result['complete_coverage'])


if __name__ == '__main__':
    unittest.main()
