"""Shared robot semantics and independent observation gates; no Gazebo imports."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from uchuva_gazebo.harvest_pilot import read_config, write_package, load_verified_package
from uchuva_gazebo.robot_kinematics import forward_kinematics, pose_identity, pose_from_rpy
from uchuva_gazebo.robot_motion import ResolvedMotionConfig, resolved_world_clearance, box_separation
from uchuva_gazebo.robot_sdf import resolved_robot_model, resolved_robot_contract, require_native_harvest_adapter, pose_rpy
from uchuva_gazebo.robot_spec import resolve_robot_profile
from uchuva_gazebo.robot_validation import evaluate_robot_telemetry
from test_harvester_robot import evaluate_sdf_arm, pose_matrix


def task():
    return {'orientation_mode': 'position_direction', 'tool_frame': 'cut_point',
            'target_direction_source': 'pedicel_axis', 'target_direction': [1, 0, 0],
            'tool_axis': [1, 0, 0], 'orientation_tolerance_rad': .05,
            'cut_axis_bidirectional': False,
            'acceptance': {'max_telemetry_gap_s': .05, 'joint_position_tolerance_rad': .001,
                           'joint_velocity_tolerance_rad_s': .001, 'effort_tolerance_nm': 1e-8,
                           'orientation_state_max_age_s': .025}}


def minimal_plants():
    return {'models': [], 'fruits': [], 'plants': [], 'meshes': {},
            'provenance': {'limitations': []}}


def write_fixture(path, robot=None, asset_root=None):
    config = read_config()
    config.pop('robot')
    config.update(robot_profile=robot or 'proxy_v1', robot_task=task())
    if asset_root:
        config['robot_asset_root'] = str(asset_root)
    with patch('uchuva_gazebo.harvest_pilot.build_harvest_plants', return_value=minimal_plants()), \
         patch('uchuva_gazebo.harvest_pilot.plan_targets', return_value={'targets': []}), \
         patch('uchuva_gazebo.harvest_pilot.procedural_soil_assets', return_value={
             'meshes': {'meshes/harvest_soil.obj': 'o test_soil\n'}, 'generated_binary_assets': {}}):
        return write_package(path, config)


class RobotIntegrationTests(unittest.TestCase):
    def test_ramped_position_has_exactly_one_force_writer(self):
        data = resolve_robot_profile('proxy_v1').to_dict()
        data['control']['arm']['shoulder_joint']['reference_mode'] = 'ramped_position'
        robot = resolve_robot_profile(data)
        contract = resolved_robot_contract(robot)
        self.assertEqual(contract['schema_version'], 'resolved-harvester-contract/1.2')
        model = resolved_robot_model(robot)
        writers = [p for p in model.findall('plugin')
                   if p.findtext('joint_name') == 'shoulder_joint']
        self.assertEqual(len(writers), 1)
        self.assertEqual(writers[0].get('name'), 'uchuva::JointPositionForceSystem')
        self.assertEqual(writers[0].findtext('state_topic'),
                         contract['topics']['position_force_states']['shoulder_joint'])
        self.assertEqual(float(writers[0].findtext('command_velocity')),
                         data['control']['arm']['shoulder_joint']['command_velocity'])

    def test_collision_detector_is_bound_to_the_profile_and_world(self):
        data = resolve_robot_profile('proxy_v1').to_dict()
        data['physics'] = {'backend': 'DART', 'solver_type': 'pgs',
                           'collision_detector': 'fcl', 'maximum_step_s': .0001}
        with tempfile.TemporaryDirectory() as root:
            package = Path(root)/'package'
            manifest = write_fixture(package, data)
            world_file = package/'harvest.sdf'
            tree = ET.parse(world_file)
            detector = tree.find('world/physics/dart/collision_detector')
            self.assertEqual(detector.text, 'fcl')
            load_verified_package(package)
            detector.text = 'ode'
            tree.write(world_file, encoding='unicode')
            manifest['files_sha256']['harvest.sdf'] = hashlib.sha256(world_file.read_bytes()).hexdigest()
            (package/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'SDF physics'):
                load_verified_package(package)
        data['physics']['collision_detector'] = 'unregistered'
        with self.assertRaises(ValueError):
            resolve_robot_profile(data)

    def test_sdf_joint_transform_matches_shared_fk_with_offsets_and_roll(self):
        robot = resolve_robot_profile('proxy_v1')
        changed = robot.to_dict()
        next(j for j in changed['joints'] if j['name'] == 'shoulder_joint')['zero_offset'] = .17
        for spec in (robot, resolve_robot_profile(changed)):
            model = resolved_robot_model(spec)
            for q in ((0, 0, 0, 0, 0), (.75, 1.1, -1.7, .3, -.8), (-1.9, -.25, .8, -.4, 1.4)):
                actual = evaluate_sdf_arm(model, q)
                expected = pose_matrix(pose_rpy(forward_kinematics(spec, q)['tool_link']))
                for a, b in zip(actual, expected):
                    for left, right in zip(a, b):
                        self.assertAlmostEqual(left, right, places=8)

    def test_dart_policy_requires_explicit_exact_adjacency(self):
        data = resolve_robot_profile('proxy_v1').to_dict()
        data['collision_policy'] = {'mode': 'explicit_pairs', 'excluded_pairs': [
            {'links': [j['parent'], j['child']], 'reason': 'Mechanical adjacent connection; native DART adjacency exclusion'} for j in data['joints']]}
        model = resolved_robot_model(resolve_robot_profile(data))
        self.assertEqual(model.findtext('self_collide'), 'true')
        self.assertTrue(all(c.findtext('surface/contact/collide_bitmask') == '65535' for c in model.findall('.//collision')))
        data['collision_policy']['excluded_pairs'].pop()
        with self.assertRaisesRegex(ValueError, 'explicit adjacency'):
            resolved_robot_model(resolve_robot_profile(data))

    def test_joint_damping_and_friction_reach_sdf_from_schema_fields(self):
        data = resolve_robot_profile('proxy_v1').to_dict()
        joint = next(j for j in data['joints'] if j['name'] == 'shoulder_joint')
        joint['damping'], joint['friction'] = .731, .023
        model = resolved_robot_model(resolve_robot_profile(data))
        dynamics = model.find("joint[@name='shoulder_joint']/axis/dynamics")
        self.assertEqual(float(dynamics.findtext('damping')), .731)
        self.assertEqual(float(dynamics.findtext('friction')), .023)

    def test_sensor_pose_uses_declared_frame_and_disabled_sensors_are_omitted(self):
        data = resolve_robot_profile('proxy_v1').to_dict()
        data['sensors'] = [{'name': 'rgb', 'type': 'camera', 'frame': 'camera_frame', 'enabled': True,
                            'update_rate_hz': 15, 'width': 640, 'height': 480, 'horizontal_fov_rad': 1,
                            'near_m': .03, 'far_m': 10},
                           {'name': 'off', 'type': 'imu', 'frame': 'base_link', 'enabled': False, 'update_rate_hz': 100}]
        robot = resolve_robot_profile(data)
        model = resolved_robot_model(robot)
        sensor = model.find(".//sensor[@name='rgb']")
        self.assertIsNotNone(sensor)
        self.assertEqual(sensor.findtext('camera/image/width'), '640')
        self.assertIsNone(model.find(".//sensor[@name='off']"))
        self.assertEqual(resolved_robot_contract(robot)['sensor_interfaces'][0]['noise_and_latency_validation'], 'pending')

    def test_effective_configuration_survives_relocation_and_semantic_tampering_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            initial, moved = Path(temp)/'initial', Path(temp)/'moved'
            manifest = write_fixture(initial)
            initial.rename(moved)
            self.assertEqual(load_verified_package(moved)['robot_spec_sha256'], manifest['robot_spec_sha256'])
            world = ET.parse(moved/'harvest.sdf')
            world.find(".//model[@name='harvester']/joint[@name='shoulder_joint']/axis/xyz").text = '0 0 1'
            world.write(moved/'harvest.sdf', encoding='unicode')
            manifest['files_sha256']['harvest.sdf'] = hashlib.sha256((moved/'harvest.sdf').read_bytes()).hexdigest()
            (moved/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'SDF robot differs'):
                load_verified_package(moved)

    def test_interaction_frame_tampering_fails_even_when_asset_checksum_is_updated(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'package'
            manifest = write_fixture(path)
            world = ET.parse(path/'harvest.sdf')
            world.find(".//plugin[@name='uchuva::HarvestSystem']/cut_pose").text = '.1 0 0 0 0 0'
            world.write(path/'harvest.sdf', encoding='unicode')
            manifest['files_sha256']['harvest.sdf'] = hashlib.sha256((path/'harvest.sdf').read_bytes()).hexdigest()
            (path/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'different interaction frame'):
                load_verified_package(path)

    def test_effective_derived_fields_cannot_hide_behind_reresolution(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'package'
            manifest = write_fixture(path)
            effective = json.loads((path/'robot_effective.json').read_text())
            next(link for link in effective['links'] if link['name'] == 'upper_arm_link')['inertial']['mass_kg'] = 999
            (path/'robot_effective.json').write_text(json.dumps(effective))
            manifest['robot_config'] = effective
            manifest['files_sha256']['robot_effective.json'] = hashlib.sha256((path/'robot_effective.json').read_bytes()).hexdigest()
            (path/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'configuration/hash differs'):
                load_verified_package(path)

    def test_mesh_bytes_are_admitted_and_packaged_without_rescaling(self):
        robot = resolve_robot_profile('proxy_v1').to_dict()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'meshes').mkdir()
            mesh = root/'meshes/robot_fixture.obj'
            mesh.write_text('o geometry_in_meters\nv 0 0 0\n')
            robot['links'][0]['visuals'].append({'name': 'frozen_mesh', 'pose': pose_identity(),
                'geometry': {'type': 'mesh', 'uri': 'meshes/robot_fixture.obj',
                             'sha256': hashlib.sha256(mesh.read_bytes()).hexdigest(), 'bound_parameters': {'/parameters/upper_arm_m': .34}}})
            manifest = write_fixture(root/'package', robot, root)
            self.assertEqual(load_verified_package(root/'package')['robot_assets_sha256'], manifest['robot_assets_sha256'])
            self.assertEqual(mesh.read_bytes(), (root/'package/meshes/robot_fixture.obj').read_bytes())
            mesh.write_text('changed CAD geometry\n')
            with self.assertRaisesRegex(ValueError, 'differs from admitted SHA'):
                write_fixture(root/'rejected', robot, root)
            self.assertFalse((root/'rejected').exists())

    def test_incomplete_cad_cannot_reach_plant_generation_or_native_execution(self):
        with patch('uchuva_gazebo.harvest_pilot.build_harvest_plants') as plants:
            with tempfile.TemporaryDirectory() as temp:
                config = read_config()
                config.pop('robot')
                config.update(robot_profile='cad_nominal_pending', robot_task=task())
                with self.assertRaises(ValueError):
                    write_package(Path(temp)/'incomplete', config)
            plants.assert_not_called()
        with self.assertRaisesRegex(ValueError, 'native_force_drive'):
            require_native_harvest_adapter(resolve_robot_profile('proxy_v1'), task())

    def test_full_base_tilt_rotates_collision_geometry(self):
        config = ResolvedMotionConfig(resolve_robot_profile('proxy_v1'), task())
        q = [0, .8, -1.2, .4, 1.1]
        base = pose_from_rpy([0, 0, 2], [.5, .2, .4])
        shapes, _ = config.world_shapes(q, [*base['xyz_m'], *base['quaternion_xyzw']])
        body = next(shape for shape in shapes if shape['link'] == 'base_link')
        center = body['pose']['xyz_m']
        obstacle = {'id': 'tilted_body_probe', 'start': center, 'end': [center[0], center[1], center[2]+.01], 'radius': .002}
        state = resolved_world_clearance(q, [*base['xyz_m'], *base['quaternion_xyzw']], [obstacle], [], None, config)
        self.assertLess(state['robot_clearance_m'], 0)
        self.assertEqual(state['limiting_robot_pair'][1], 'tilted_body_probe')
        self.assertEqual(state['robot_spec_sha256'], config.robot.sha256)

    def test_individual_obb_gap_and_self_overlap_are_not_union_box_approximations(self):
        first = {'pose': pose_from_rpy([0, -.2, 1], [0, 0, .1])}
        second = {'pose': pose_from_rpy([0, .2, 1], [0, 0, -.1])}
        self.assertGreater(box_separation(first, [.1,.01,.1], second, [.1,.01,.1]), .3)
        self.assertLess(box_separation(first, [.1,.01,.1], first, [.1,.01,.1]), 0)


def telemetry_fixture():
    robot = resolve_robot_profile('proxy_v1')
    data = robot.to_dict()
    # Synthetic controller declarations for auditor unit tests only. No native
    # capability or CAD measurement is inferred from these fixture gains.
    for joint in data['joints']:
        if joint['group'] == 'drive':
            data['control']['drive']['joints'][joint['name']] = {
                'p_gain': 1, 'i_gain': 0, 'd_gain': 0, 'i_min': 0, 'i_max': 0,
                'cmd_min': -1, 'cmd_max': 1, 'command_velocity': 1}
    robot = resolve_robot_profile(data)
    manifest = {'robot_config': robot.to_dict(), 'robot_task': task(),
                'robot_spec_sha256': robot.sha256,
                'mission': {'targets': [{'id': 'fruit', 'cut_axis_world': [1,0,0]}]}}
    records, samples = [], []
    for i in range(3):
        stamp = .1+i*.01
        records.append({'schema_version': 'robot-telemetry/1.0', 'robot_spec_sha256': robot.sha256,
            'sim_time': stamp, 'iteration': 100+10*i, 'sample_count': 10, 'reset_count': 0,
            'commanded_before_step_time': stamp-.001, 'measured_after_step_time': stamp,
            'wrench_semantics': 'simulated_transmitted_joint_frame_not_motor_torque',
            'joints': [{'name': j['name'], 'position': 0., 'velocity': 0., 'force_command': .1,
                        'position_available': True, 'velocity_available': True, 'force_command_available': True,
                        'wrench_available': True, 'transmitted_wrench': {'force': [0,0,1], 'torque': [0,0,0]},
                        'max_abs_force_command_window': .1, 'max_abs_velocity_window': 0., 'saturated_steps': 0}
                       for j in data['joints'] if j['type'] != 'fixed']})
        samples.append({'schema_version': 2, 'ready': True, 'sim_time': stamp,
                        'orientation_guard_enabled': True, 'cut_pose': [0,0,0,0,0,0,1],
                        'fruits': [{'id': 'fruit', 'pose': [0,0,0,0,0,0,1]}]})
    events = [{'action': 'cut', 'phase': 'ack', 'accepted': True, 'id': 'fruit', 'sim_time': .121}]
    return manifest, records, samples, events


class RobotObservationTests(unittest.TestCase):
    def test_complete_observation_is_required_separately_from_force_commands(self):
        manifest, records, samples, events = telemetry_fixture()
        self.assertTrue(all(c['passed'] for c in evaluate_robot_telemetry(manifest, records, samples, events)))
        records[1]['joints'][0]['wrench_available'] = False
        checks = evaluate_robot_telemetry(manifest, records, samples, events)
        self.assertFalse(checks[0]['passed'])
        self.assertIn('wrench unavailable', checks[0]['errors'][0]['error'])

    def test_unrecorded_peaks_in_window_and_stale_gaps_fail(self):
        manifest, records, samples, events = telemetry_fixture()
        records[1]['joints'][0]['max_abs_force_command_window'] = 999
        self.assertFalse(evaluate_robot_telemetry(manifest, records, samples, events)[0]['passed'])
        manifest, records, samples, events = telemetry_fixture()
        samples[-1]['sim_time'] = .4
        self.assertFalse(evaluate_robot_telemetry(manifest, records, samples, events)[1]['passed'])

    def test_rejected_peaks_remain_visible_without_fabricating_transport_gaps(self):
        manifest, records, samples, events = telemetry_fixture()
        first = records[1]['joints'][0]
        last = records[1]['joints'][-1]
        first['max_abs_velocity_window'] = 999
        last['max_abs_force_command_window'] = 888
        checks = evaluate_robot_telemetry(manifest, records, samples, events)
        self.assertFalse(checks[0]['passed'])
        self.assertFalse(checks[1]['passed'])
        metrics = checks[0]['joint_metrics']
        self.assertEqual(metrics[first['name']]['max_abs_velocity'], 999)
        self.assertEqual(metrics[last['name']]['max_abs_force_command'], 888)
        self.assertEqual(metrics[last['name']]['observed_window_count'], 3)
        self.assertAlmostEqual(checks[1]['maximum_gap_s'], .01)
        self.assertAlmostEqual(checks[1]['maximum_validated_sample_gap_s'], .02)

    def test_orientation_is_recomputed_from_both_observed_poses(self):
        manifest, records, samples, events = telemetry_fixture()
        samples[-1]['fruits'][0]['pose'] = [0,0,0,0,0,1,0]
        checks = evaluate_robot_telemetry(manifest, records, samples, events)
        self.assertFalse(checks[-1]['passed'])
        self.assertAlmostEqual(checks[-1]['maximum_axis_error_rad'], math.pi)

    def test_missing_preregistered_tolerance_and_false_identity_are_rejected(self):
        manifest, records, samples, events = telemetry_fixture()
        del manifest['robot_task']['acceptance']['effort_tolerance_nm']
        with self.assertRaisesRegex(ValueError, 'preregistered'):
            evaluate_robot_telemetry(manifest, records, samples, events)
        manifest, records, samples, events = telemetry_fixture()
        records[1]['robot_spec_sha256'] = '0'*64
        self.assertFalse(evaluate_robot_telemetry(manifest, records, samples, events)[0]['passed'])


if __name__ == '__main__':
    unittest.main()
