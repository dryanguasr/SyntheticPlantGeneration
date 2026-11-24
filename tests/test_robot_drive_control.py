"""Native yaw feedback cannot evade force-control reference limits or validity."""
import copy
import math
import unittest

from uchuva_gazebo.robot_drive_control import DriveReferenceController
from uchuva_gazebo.robot_spec import resolve_robot_profile
from uchuva_gazebo.robot_control_validation import evaluate_base_drive_control


def feedback():
    return dict(enabled=True, mode='yaw_rate_proportional', observation_source='native_model_pose_ideal',
                p_gain=1.5, window_s=.1, max_observation_age_s=.05,
                zero_twist_policy='ramp_to_zero_without_feedback')


def drive(enabled=True):
    result=dict(left_joints=['left'], right_joints=['right'], joint_signs={'left':1,'right':1},
        joints={n:{'command_velocity':8} for n in ('left','right')}, wheel_radius_m=.11,
        wheel_separation_m=.61655, max_linear_velocity=.15, max_angular_velocity=.3,
        max_linear_acceleration=.2, max_angular_acceleration=.4)
    if enabled:result['base_feedback']=feedback()
    return result


def pose(yaw):
    return [0.,0.,.3,0.,0.,math.sin(yaw/2),math.cos(yaw/2)]


def observe(controller, stop=.2, rate=.08, offset=0):
    for i in range(round(stop/.01)+1):
        t=i*.01;controller.observe_pose(t,pose(offset+rate*t))


class DriveReferenceTests(unittest.TestCase):
    def test_independent_auditor_checks_native_rate_and_actual_wheel_references(self):
        data=drive();control=DriveReferenceController(data);poses=[];commands=[]
        for i in range(31):
            stamp=i*.01;p=pose(.08*stamp)
            poses.append({'sim_time':stamp,'pose':p});control.observe_pose(stamp,p)
            row=control.step(0,.2 if i>=15 else 0,stamp)
            commands.append({'sim_time':stamp,'linear_m_s':row['linear_m_s'],
                'angular_rad_s':row['angular_rad_s'],'wheel_velocity_references_rad_s':copy.deepcopy(row['wheel_velocity_references_rad_s']),
                'drive_reference':row})
        manifest={'robot_config':{'control':{'drive':data}}}
        self.assertTrue(evaluate_base_drive_control(manifest,commands,poses)[0]['passed'])
        for field in ('observed_yaw_rate_rad_s','feedback_correction_rad_s','angular_rad_s'):
            altered=copy.deepcopy(commands);altered[20]['drive_reference'][field]+=.1
            self.assertFalse(evaluate_base_drive_control(manifest,altered,poses)[0]['passed'])
        altered=copy.deepcopy(commands);altered[20]['wheel_velocity_references_rad_s']['left']+=.1
        self.assertFalse(evaluate_base_drive_control(manifest,altered,poses)[0]['passed'])
        self.assertFalse(evaluate_base_drive_control(manifest,commands,poses[:5])[0]['passed'])

    def test_disabled_preserves_legacy_mapping_and_ramps(self):
        control=DriveReferenceController(drive(False))
        first=control.step(.1,.2,.1)
        self.assertAlmostEqual(first['linear_m_s'],.02)
        self.assertAlmostEqual(first['angular_rad_s'],.04)
        self.assertAlmostEqual(first['wheel_velocity_references_rad_s']['left'],(.02-.04*.61655/2)/.11)
        self.assertFalse(first['feedback_enabled'])
        self.assertEqual(control.step(.1,.2,.1)['angular_rad_s'],first['angular_rad_s'])

    def test_proportional_feedback_is_bounded_and_has_no_integral(self):
        control=DriveReferenceController(drive());observe(control)
        value=control.step(0,.2,.2)
        self.assertAlmostEqual(value['observed_yaw_rate_rad_s'],.08)
        self.assertAlmostEqual(value['feedback_correction_rad_s'],.18)
        self.assertAlmostEqual(value['compensated_angular_before_limit_rad_s'],.38)
        self.assertEqual(value['compensated_angular_rad_s'],.3)
        self.assertAlmostEqual(value['angular_rad_s'],.08)
        self.assertTrue(value['angular_feedback_clipped'])
        self.assertEqual(value['observation_source'],'native_model_pose_ideal')

    def test_zero_twist_brakes_with_ramp_and_cannot_reverse_from_feedback(self):
        control=DriveReferenceController(drive());observe(control)
        before=control.step(0,.2,.2)
        stopped=control.step(0,0,.21)
        self.assertAlmostEqual(stopped['angular_rad_s'],before['angular_rad_s']-.004)
        self.assertEqual(stopped['feedback_correction_rad_s'],0)
        self.assertTrue(stopped['zero_twist_feedback_bypass'])
        self.assertEqual(control.step(0,0,1.)['angular_rad_s'],0)

    def test_invalid_or_regressing_pose_does_not_enter_history(self):
        control=DriveReferenceController(drive());control.observe_pose(.1,pose(0))
        for bad in ([0]*7,[math.nan,0,0,0,0,0,1],[0,0,0,0,0,0,2]):
            with self.assertRaises(ValueError):control.observe_pose(.2,bad)
        with self.assertRaisesRegex(ValueError,'regressed'):control.observe_pose(.09,pose(0))
        with self.assertRaisesRegex(ValueError,'Conflicting'):control.observe_pose(.1,pose(.1))
        control.observe_pose(.1,pose(0))
        self.assertEqual(len(control.observations),1)

    def test_stale_missing_and_future_observations_reject_motion_without_mutating_ramp(self):
        control=DriveReferenceController(drive())
        self.assertEqual(control.step(0,0,.0001)['angular_rad_s'],0)
        with self.assertRaisesRegex(ValueError,'not available'):control.step(0,.2,.1)
        observe(control)
        for stamp,pattern in ((.19,'future'),(.26,'stale')):
            previous=control.previous
            with self.assertRaisesRegex(ValueError,pattern):control.step(0,.2,stamp)
            self.assertEqual(control.previous,previous)
        self.assertEqual(control.step(0,0,.26)['angular_rad_s'],0)

    def test_full_window_required_and_yaw_wrap_is_continuous(self):
        control=DriveReferenceController(drive())
        control.observe_pose(0,pose(0));control.observe_pose(.05,pose(.01))
        with self.assertRaisesRegex(ValueError,'incomplete'):control.step(0,.2,.05)
        wrapped=DriveReferenceController(drive());observe(wrapped,.3,.2,math.pi-.03)
        value=wrapped.step(0,.2,.3)
        self.assertAlmostEqual(value['observed_yaw_rate_rad_s'],.2)
        self.assertAlmostEqual(value['feedback_correction_rad_s'],0,places=12)

    def test_nonfinite_commands_and_time_regression_rejected(self):
        control=DriveReferenceController(drive(False));control.step(0,0,.1)
        for args in ((math.nan,0,.2),(0,math.inf,.2),(0,0,.09),(0,0,True)):
            with self.assertRaises(ValueError):control.step(*args)

    def test_proxy_stays_disabled_and_enabled_feedback_requires_native_drive_and_provenance(self):
        original=resolve_robot_profile('proxy_v1')
        self.assertNotIn('base_feedback',original.data['control']['drive'])
        data=original.to_dict();data['control']['drive']['base_feedback']=feedback()
        with self.assertRaisesRegex(ValueError,'finite-force'):resolve_robot_profile(data)
        data['control']['drive']['base_feedback']['enabled']=False
        with self.assertRaisesRegex(ValueError,'provenance'):resolve_robot_profile(data)
        for key in feedback():
            data['parameter_metadata']['/control/drive/base_feedback/'+key]={
                'status':'estimado','source':'test','revision':'test','method':'fixture','update_class':'runtime'}
        resolved=resolve_robot_profile(data)
        self.assertFalse(resolved.data['control']['drive']['base_feedback']['enabled'])
        malformed=copy.deepcopy(data);malformed['control']['drive']['base_feedback']['window_s']=0
        with self.assertRaises(ValueError):resolve_robot_profile(malformed)


if __name__=='__main__':unittest.main()
