"""Canonical inputs reject stale geometry, topology errors and hidden overrides."""
import copy
import json
import hashlib
from pathlib import Path
import tempfile
import unittest

from uchuva_gazebo.robot_spec import (
    PROFILE_DIRECTORY, ResolvedRobot, RobotSpec, canonical_hash,
    resolve_robot_profile, validate_robot_spec, load_robot_json, verify_robot_assets,
)


def raw_profile():
    return json.loads((PROFILE_DIRECTORY / 'proxy_v1.json').read_text(encoding='utf-8'))


def evidence():
    return {'status': 'estimado', 'source': 'unit-test engineering fixture',
            'revision': 'test-v1', 'method': 'controlled parameter perturbation'}


class RobotSpecTests(unittest.TestCase):
    def test_resolved_is_deeply_immutable_and_hash_covers_effective_inputs(self):
        robot = resolve_robot_profile('proxy_v1')
        with self.assertRaises(TypeError):
            robot.data['links'][0]['inertial']['mass_kg'] = 999
        copied = robot.to_dict()
        copied['links'][0]['inertial']['mass_kg'] = 999
        self.assertEqual(robot.data['links'][0]['inertial']['mass_kg'], 12)
        self.assertEqual(robot.sha256, canonical_hash(robot.to_dict()))
        with self.assertRaises(ValueError):
            ResolvedRobot(copied, robot.sha256)
        parsed = RobotSpec.from_dict(raw_profile())
        with self.assertRaises(TypeError):
            parsed.data['parameters']['upper_arm_m'] = 9

    def test_dimension_override_propagates_to_joint_collision_inertia_and_adapter(self):
        source = raw_profile()
        original = copy.deepcopy(source)
        robot = resolve_robot_profile(source, {'/parameters/upper_arm_m': {'value': .40, 'provenance': evidence()}})
        data = robot.to_dict()
        upper = next(row for row in data['links'] if row['name'] == 'upper_arm_link')
        elbow = next(row for row in data['joints'] if row['name'] == 'elbow_joint')
        self.assertEqual(elbow['origin']['xyz_m'][0], .40)
        self.assertEqual(upper['collisions'][0]['geometry']['size_m'][0], .40)
        self.assertEqual(upper['inertial']['com_m'][0], .20)
        self.assertAlmostEqual(upper['inertial']['tensor_kg_m2'][1], (.40**2+.055**2)/12)
        self.assertEqual(data['legacy_proxy_config']['upper_arm_m'], .40)
        self.assertEqual(data['override_history'][0]['provenance']['status'], 'estimado')
        self.assertEqual(source, original)
        self.assertNotEqual(robot.sha256, resolve_robot_profile(source).sha256)

    def test_mass_override_changes_inertia_without_geometry_edit(self):
        a = resolve_robot_profile('proxy_v1').to_dict()
        b = resolve_robot_profile('proxy_v1', {'/parameters/upper_arm_mass_kg': {'value': 2., 'provenance': evidence()}}).to_dict()
        la = next(row for row in a['links'] if row['name'] == 'upper_arm_link')
        lb = next(row for row in b['links'] if row['name'] == 'upper_arm_link')
        self.assertEqual(la['collisions'], lb['collisions'])
        self.assertEqual(lb['inertial']['mass_kg'], 2.)
        for left, right in zip(la['inertial']['tensor_kg_m2'], lb['inertial']['tensor_kg_m2']):
            self.assertAlmostEqual(right, 2*left)

    def test_limits_and_controller_must_change_consistently(self):
        data = raw_profile()
        index = next(i for i, row in enumerate(data['joints']) if row['name'] == 'shoulder_joint')
        limits = {f'/joints/{index}/limits/effort': {'value': 30., 'provenance': evidence()}}
        with self.assertRaisesRegex(ValueError, 'capacity'):
            resolve_robot_profile(data, limits)
        for field, value in [('cmd_min', -30.), ('cmd_max', 30.)]:
            limits[f'/control/arm/shoulder_joint/{field}'] = {'value': value, 'provenance': evidence()}
        robot = resolve_robot_profile(data, limits)
        self.assertEqual(robot.to_dict()['control']['arm']['shoulder_joint']['cmd_max'], 30)

    def test_mesh_binding_rejects_changed_dimensions_and_scaling(self):
        data = raw_profile()
        mesh = {'name': 'fixture_mesh', 'pose': {'xyz_m': [0,0,0], 'quaternion_xyzw': [0,0,0,1]},
                'geometry': {'type': 'mesh', 'uri': 'meshes/fixture.obj', 'sha256': 'a'*64,
                             'bound_parameters': {'/parameters/upper_arm_m': .34}, 'scale': [1,1,1]}}
        data['links'][0]['visuals'].append(mesh)
        resolve_robot_profile(data)
        with self.assertRaisesRegex(ValueError, 'Stale mesh'):
            resolve_robot_profile(data, {'/parameters/upper_arm_m': {'value': .40, 'provenance': evidence()}})
        mesh['geometry']['scale'] = [2,1,1]
        with self.assertRaisesRegex(ValueError, 'unit scale'):
            resolve_robot_profile(data)

    def test_incomplete_cad_is_inspectable_but_cannot_resolve(self):
        data = json.loads((PROFILE_DIRECTORY/'cad_nominal_pending.json').read_text(encoding='utf-8'))
        spec = RobotSpec.from_dict(data)
        self.assertTrue(spec.to_dict()['missing_evidence'])
        self.assertEqual(spec.to_dict()['links'], [])
        with self.assertRaisesRegex(ValueError, 'Incomplete robot profile'):
            resolve_robot_profile(spec)

    def test_invalid_physics_axes_references_cycles_and_typo_fail_closed(self):
        def reject(edit):
            data = resolve_robot_profile('proxy_v1').to_dict()
            data['derived_values'] = []
            edit(data)
            with self.assertRaises(ValueError):
                resolve_robot_profile(data)
        reject(lambda d: d['links'][0]['inertial'].update(mass_kg=-1))
        reject(lambda d: d['links'][0]['inertial'].update(tensor_kg_m2=[1,1,9,0,0,0]))
        reject(lambda d: d['joints'][4].update(axis=[0,0,2]))
        reject(lambda d: d['joints'][4].update(parent='missing'))
        reject(lambda d: d['joints'][4].update(parent='tool_link'))
        reject(lambda d: d['frames'][0].update(parent='arm_mount'))
        reject(lambda d: d['joints'][4]['limits'].update(lower=5,upper=-5))
        reject(lambda d: d['control']['arm']['shoulder_joint'].update(command_velocity=10))
        reject(lambda d: d['links'][0]['inertial'].update(mass_kg=float('nan')))
        reject(lambda d: d['parameters'].update(upper_arm_m=True))
        reject(lambda d: d['links'][0].update(inertiall={}))
        reject(lambda d: d['units'].update(length='mm'))
        reject(lambda d: d['collision_policy']['excluded_pairs'].append(d['collision_policy']['excluded_pairs'][0]))
        reject(lambda d: d['actuators'][0].update(effort_reference='motor_shaft'))
        reject(lambda d: d['actuators'][0].update(continuous_effort=1,peak_effort=2))

    def test_overrides_require_evidence_and_never_silently_overwrite_derived_fields(self):
        with self.assertRaisesRegex(ValueError, 'value and provenance'):
            resolve_robot_profile('proxy_v1', {'/parameters/upper_arm_m': .4})
        with self.assertRaisesRegex(ValueError, 'canonical parameter'):
            resolve_robot_profile('proxy_v1', {'/links/0/inertial/mass_kg': {'value': 5., 'provenance': evidence()}})
        data = raw_profile()
        data['parameter_metadata']['/parameters/upper_arm_m']['update_class'] = 'cad_reexport'
        with self.assertRaisesRegex(ValueError, 'CAD reexport required'):
            resolve_robot_profile(data, {'/parameters/upper_arm_m': {'value': .4, 'provenance': evidence()}})
        with self.assertRaisesRegex(ValueError, 'capability'):
            resolve_robot_profile('proxy_v1').require_capability('confirmed_real_hardware')

    def test_intermediate_negative_indices_and_duplicate_json_are_rejected(self):
        for pointer in ['/links/-1/inertial/mass_kg','/links/01/inertial/mass_kg','/links/999/inertial/mass_kg','/links/~2/inertial/mass_kg']:
            data=raw_profile()
            data['parameter_metadata'][pointer]={**evidence(),'update_class':'model_regeneration'}
            with self.assertRaises(ValueError):
                resolve_robot_profile(data,{pointer:{'value':1.,'provenance':evidence()}})
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'duplicate.json'
            path.write_text('{"mass": 1, "mass": 2}',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Duplicate JSON'):
                load_robot_json(path)

    def test_mesh_content_is_verified_independently_from_its_parameter_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'meshes').mkdir()
            path=root/'meshes/fixture.obj';path.write_bytes(b'# geometric fixture\n')
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            data=raw_profile()
            data['links'][0]['visuals'].append({'name':'mesh_fixture',
                'pose':{'xyz_m':[0,0,0],'quaternion_xyzw':[0,0,0,1]},
                'geometry':{'type':'mesh','uri':'meshes/fixture.obj','sha256':digest,
                            'bound_parameters':{'/parameters/upper_arm_m':.34}}})
            robot=resolve_robot_profile(data)
            self.assertEqual(verify_robot_assets(robot,root),{'meshes/fixture.obj':digest})
            path.write_bytes(b'# changed\n')
            with self.assertRaisesRegex(ValueError,'content differs'):
                verify_robot_assets(robot,root)

    def test_three_overrides_reach_exported_sdf_and_kinematics(self):
        from uchuva_gazebo.robot_sdf import resolved_robot_model
        from uchuva_gazebo.robot_kinematics import forward_kinematics,collision_shapes
        baseline=resolve_robot_profile('proxy_v1')
        longer=resolve_robot_profile('proxy_v1',{'/parameters/upper_arm_m':{'value':.40,'provenance':evidence()}})
        heavier=resolve_robot_profile('proxy_v1',{'/parameters/upper_arm_mass_kg':{'value':2.,'provenance':evidence()}})
        changes={'/joints/5/limits/effort':{'value':30.,'provenance':evidence()},
                 '/control/arm/shoulder_joint/cmd_min':{'value':-30.,'provenance':evidence()},
                 '/control/arm/shoulder_joint/cmd_max':{'value':30.,'provenance':evidence()}}
        weaker=resolve_robot_profile('proxy_v1',changes)
        model=resolved_robot_model(longer)
        self.assertEqual(float(model.findtext("link[@name='upper_arm_link']/collision/geometry/box/size").split()[0]),.40)
        before=forward_kinematics(baseline,[0]*5);after=forward_kinematics(longer,[0]*5)
        self.assertAlmostEqual(after['tcp']['xyz_m'][0]-before['tcp']['xyz_m'][0],.06)
        shape=next(s for s in collision_shapes(longer,after) if s['name']=='upper_arm_collision')
        self.assertEqual(shape['geometry']['size_m'][0],.40)
        heavy_model=resolved_robot_model(heavier)
        self.assertEqual(float(heavy_model.findtext("link[@name='upper_arm_link']/inertial/mass")),2.)
        self.assertEqual(forward_kinematics(heavier,[0]*5),before)
        weak_model=resolved_robot_model(weaker)
        self.assertEqual(float(weak_model.findtext("joint[@name='shoulder_joint']/axis/limit/effort")),30.)
        pid=next(p for p in weak_model.findall('plugin') if p.findtext('joint_name')=='shoulder_joint')
        self.assertEqual(float(pid.findtext('cmd_max')),30.)


if __name__ == '__main__':
    unittest.main()
