"""Frozen control composition cannot replace revised CAD or admit extra changes."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from compose_cad_robot_candidate import compose, verify_drive_delta, DRIVE_PARAMETERS
from uchuva_gazebo.robot_spec import resolve_robot_profile
from uchuva_gazebo.robot_kinematics import pose_identity


def evidence(source='revision.json', revision='a'*64):
    return {'status': 'estimado', 'source': source, 'revision': revision, 'method': 'fixture'}


def fixture():
    data = resolve_robot_profile('proxy_v1').to_dict()
    parameters = {**DRIVE_PARAMETERS, 'wheel_effort_limit_nm': 4.,
                  'wheel_velocity_p_gain': 12., 'wheel_integral_effort_limit_nm': 1.}
    for name, value in parameters.items():
        data['parameters'][name] = value
        data['parameter_metadata']['/parameters/'+name] = {**evidence(), 'update_class': 'model_regeneration'}
    for index, joint in enumerate(data['joints']):
        if joint['group'] != 'drive':
            continue
        name = joint['name']
        data['control']['drive']['joints'][name] = dict(p_gain=12., i_gain=4., d_gain=0.,
            i_min=-1., i_max=1., cmd_min=-4., cmd_max=4., command_velocity=1.)
        actuator_index = next(i for i, a in enumerate(data['actuators']) if a['joint'] == name)
        data['actuators'][actuator_index].update(continuous_effort=4., peak_effort=4.)
        mappings = [(f'/joints/{index}/limits/effort', 'wheel_effort_limit_nm', 1),
                    (f'/actuators/{actuator_index}/continuous_effort', 'wheel_effort_limit_nm', 1),
                    (f'/actuators/{actuator_index}/peak_effort', 'wheel_effort_limit_nm', 1)]
        for key, parameter, sign in (('p_gain', 'wheel_velocity_p_gain', 1),
                ('i_gain', 'wheel_velocity_i_gain', 1), ('i_min', 'wheel_integral_effort_limit_nm', -1),
                ('i_max', 'wheel_integral_effort_limit_nm', 1), ('cmd_min', 'wheel_effort_limit_nm', -1),
                ('cmd_max', 'wheel_effort_limit_nm', 1)):
            mappings.append((f'/control/drive/joints/{name}/{key}', parameter, sign))
        for path, parameter, sign in mappings:
            data['derived_values'].append({'path': path, 'expression':
                {'parameter': parameter} if sign == 1 else {'op': 'mul', 'args': [-1, {'parameter': parameter}]}})
    for name, group in (('driver', 'gripper'), ('follower', 'passive')):
        data['links'].append(dict(name=name, inertial=dict(mass_kg=.01, com_m=[0, 0, 0],
            tensor_kg_m2=[.00001, .00001, .00001, 0, 0, 0]), visuals=[], collisions=[]))
        data['joints'].append(dict(name=name, parent=data['root_link'], child=name, type='revolute', group=group,
            origin=pose_identity(), child_pose=pose_identity(), axis=[0, 1, 0], zero_offset=0,
            limits=dict(lower=-.2, upper=.2, velocity=1, effort=.02)))
    data['actuators'].append(dict(name='driver_actuator', joint='driver', continuous_effort=.02,
        peak_effort=.02, transmission_ratio=1., efficiency=1., status='estimado', effort_reference='joint_output'))
    data['control']['gripper'] = {'driver': dict(p_gain=.2, i_gain=0, d_gain=.01,
        i_min=0, i_max=0, cmd_min=-.02, cmd_max=.02, command_velocity=1.)}
    data['gear_couplings'] = [dict(name='gears', driver='driver', follower='follower',
        ratio=-1, offset=0, stiffness_nm_rad=100, damping_nms_rad=.03, maximum_step_s=.0001)]
    data['physics'] = dict(backend='DART', solver_type='pgs', maximum_step_s=.0001)
    base = resolve_robot_profile(data)
    revisions, current = [], base
    for values, source, digest in (({'wheel_effort_limit_nm': 6.5}, 'r1.json', '1'*64),
            ({'wheel_velocity_p_gain': 30., 'wheel_integral_effort_limit_nm': 5.5}, 'r2.json', '2'*64)):
        revision = {'base_robot_spec_sha256': current.sha256, 'candidate_parameters': values}
        revisions.append((revision, source, digest))
        current = resolve_robot_profile(current, {'/parameters/'+p: {
            'value': value, 'provenance': evidence(source, digest)} for p, value in values.items()})
    return base, current, revisions


def settings():
    return {'collision_detector': 'bullet', 'position_control': {'groups': ['arm', 'gripper'],
        'reference_mode': 'ramped_position', 'gripper_command_velocity_rad_s': .2},
        'gear_coupling': {'name': 'gears', 'stiffness_nm_rad': 100, 'damping_nms_rad': .012,
                          'selection_status': 'selected_for_full_validation'}}


class CadCandidateCompositionTests(unittest.TestCase):
    def test_exact_replay_covers_efforts_actuators_and_gains(self):
        base, reference, revisions = fixture()
        events = verify_drive_delta(base, reference, revisions)
        self.assertEqual(len(events), 3)
        for joint in reference.joints:
            if joint['group'] == 'drive':
                self.assertEqual(joint['limits']['effort'], 6.5)
                gains = reference.data['control']['drive']['joints'][joint['name']]
                self.assertEqual((gains['p_gain'], gains['i_gain'], gains['i_min'], gains['cmd_max']),
                                 (30., 4., -5.5, 6.5))

    def test_unrelated_drive_reference_change_is_rejected(self):
        base, reference, revisions = fixture()
        altered = reference.to_dict()
        altered['physics']['solver_type'] = 'dantzig'
        with self.assertRaisesRegex(ValueError, 'outside the exact override'):
            verify_drive_delta(base, resolve_robot_profile(altered), revisions)

    def test_composition_preserves_revised_geometry_and_inertia(self):
        base, reference, revisions = fixture()
        events = verify_drive_delta(base, reference, revisions)
        cad = resolve_robot_profile(base, {'/parameters/upper_arm_m': {
            'value': .4, 'provenance': evidence('CAD fixture')}})
        final = compose(cad, base, events, settings(), evidence()).to_dict()
        self.assertEqual(final['links'], cad.to_dict()['links'])
        self.assertEqual(final['collision_policy'], cad.to_dict()['collision_policy'])
        self.assertEqual(final['physics']['collision_detector'], 'bullet')
        self.assertEqual(final['control']['gripper']['driver']['command_velocity'], .2)
        self.assertEqual(final['gear_couplings'][0]['damping_nms_rad'], .012)
        self.assertTrue(all(g['reference_mode'] == 'ramped_position' for g in final['control']['arm'].values()))

    def test_pending_damping_cannot_produce_profile(self):
        base, reference, revisions = fixture()
        pending = settings()
        pending['gear_coupling']['damping_nms_rad'] = None
        pending['gear_coupling']['selection_status'] = 'PENDING'
        with self.assertRaisesRegex(ValueError, 'not been explicitly selected'):
            compose(base, base, verify_drive_delta(base, reference, revisions), pending, evidence())

    def test_ramped_initial_zero_must_be_inside_arm_and_gripper_limits(self):
        base, reference, revisions = fixture()
        events = verify_drive_delta(base, reference, revisions)
        for group, name in (('arm', 'shoulder_joint'), ('gripper', 'driver')):
            changed = base.to_dict()
            joint = next(j for j in changed['joints'] if j['name'] == name)
            joint['limits']['lower'] = .01
            if group == 'arm':
                changed['arm_home_positions'][name] = .1
            cad = resolve_robot_profile(changed)
            with self.subTest(group=group), self.assertRaisesRegex(ValueError, 'initial zero'):
                compose(cad, base, events, settings(), evidence())


if __name__ == '__main__':
    unittest.main()
