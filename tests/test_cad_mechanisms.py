"""Independent conservation and virtual-work checks for mechanism preparation."""
import importlib.util
import copy
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
spec = importlib.util.spec_from_file_location('cad_mechanisms', ROOT/'scripts/cad_mechanisms.py')
cad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cad)
import analyze_cad_gripper_range as gripper_range
import summarize_gripper_brep_envelope as envelope


class MechanismTests(unittest.TestCase):
    def test_collision_derivatives_cannot_modify_visuals_or_physics(self):
        data=cad.resolve_robot_profile(ROOT/'configs/robots/proxy_v1.json').to_dict()
        data['capabilities'].append('collision_meshes')
        data['physics']={'backend':'DART','solver_type':'pgs','maximum_step_s':.0001}
        geometry={'type':'mesh','uri':'meshes/source.obj','sha256':'1'*64,
                  'bound_parameters':{'/parameters/body_length_m':data['parameters']['body_length_m']},'scale':[1,1,1]}
        data['links'][0]['collisions'][0]['geometry']=geometry
        data['derived_values']=[row for row in data['derived_values']
                                if not row['path'].startswith('/links/0/collisions/0/geometry/')]
        original=cad.resolve_robot_profile(data)
        manifest={'entries':{'1'*64:{'collision_uri':'collision_meshes/derived.obj',
            'collision_sha256':'2'*64,'positions_unchanged':True,
            'unoriented_triangles_unchanged':True,'report':{}}}}
        changed,report=cad.apply_collision_derivatives(original,manifest,'3'*64)
        actual=changed.to_dict()
        actual['links'][0]['collisions'][0]['geometry']=copy.deepcopy(geometry)
        actual['provenance']=copy.deepcopy(data['provenance'])
        self.assertEqual(actual,original.to_dict())
        self.assertEqual(report['changed_colliders'],1)
        manifest['entries']['1'*64]['positions_unchanged']=False
        with self.assertRaisesRegex(ValueError,'Undocumented'):
            cad.apply_collision_derivatives(original,manifest,'3'*64)

    def test_continuous_clearance_does_not_promote_sub_four_mm_gap(self):
        motion={'assembly_sha256':'a','samples':[{'driver_rad':q} for q in (0,.1)],
                'point_speed_bounds_m_per_driver_rad':{'a':.01,'b':.01}}
        observations={'status':'COMPLETED','source_files_unchanged':True,'assembly_sha256':'a',
            'pairs':[{'driver_rad':q,'occurrences':['a','b'],'status':'NATIVE_BREP_OBSERVED',
                'minimum_distance_m':.002,'interference_count':0,'interference_volumes_m3':[]}
                for q in (0,.1)]}
        result=envelope.summarize(motion,observations)
        self.assertEqual(result['status'],'NOMINAL_GEOMETRY_SEPARATED')
        self.assertAlmostEqual(result['pairs'][0]['continuous_lower_gap_m'],.001)
        self.assertFalse(result['pairs'][0]['passes_unchanged_four_mm_self_margin'])
        self.assertFalse(result['collision_exclusions_authorized'])
        observations['pairs'].pop()
        with self.assertRaisesRegex(ValueError,'Missing'):
            envelope.summarize(motion,observations)

    def test_four_bar_parallelogram_has_exact_known_angular_relations(self):
        points={'A':[0,0,0],'B':[1,0,0],'C':[1,0,-1],'D':[0,0,-1]}
        result=gripper_range.trace_four_bar(points,[0,1,0],.35,100)
        self.assertEqual(result['status'],'KINEMATIC_BRANCH_TRACED')
        for row in result['records']:
            self.assertAlmostEqual(row['short_rad'],row['driver_rad'],places=12)
            self.assertAlmostEqual(row['jaw_absolute_rad'],0,places=12)
            self.assertAlmostEqual(math.dist(row['point_d_m'],points['A']),1,places=12)

    def test_auxiliary_partition_conserves_full_tensor_at_arbitrary_pose(self):
        inertia = {'mass_kg': 3, 'com_m': [.2, -.1, .15],
                   'tensor_kg_m2': [.4, .5, .6, .01, -.02, .03]}
        pose = {'xyz_m': [-.2, .7, .3], 'quaternion_xyzw': [0, 0, math.sin(.3), math.cos(.3)]}
        full = cad.body_total([{'name': 'full', 'inertial': inertia}], {'full': pose})
        split = cad.body_total([{'name': name, 'inertial': cad.scaled_inertia(inertia, fraction)}
                                for name, fraction in (('a', .5), ('b', .5))], {'a': pose, 'b': pose})
        self.assertAlmostEqual(full['mass_kg'], split['mass_kg'])
        for key in ('com_m', 'tensor_kg_m2'):
            for a, b in zip(full[key], split[key]):
                self.assertAlmostEqual(a, b, places=13)

    def test_virtual_work_preload_balances_symmetric_fixture(self):
        # Four corners: carrier axis Y at origin of each corner; its wheel is
        # .2 m forward, lower shock .3 m forward, vertical shock length .2 m.
        # All moving masses sit on their pivots, so preload derives only from
        # ground reaction: Fspring = Nwheel * .2/.3.
        links, poses, suspension, wheels = [], {}, [], []
        def body(name, point, mass):
            links.append({'name': name, 'inertial': {'mass_kg': mass, 'com_m': [0,0,0],
                          'tensor_kg_m2': [.01, .01, .01, 0,0,0]}})
            poses[name] = cad.pose(point)
        body('base', [0,0,0], 10)
        for index, (x,y) in enumerate(((1,1),(-1,1),(-1,-1),(1,-1))):
            suffix = str(index)
            a, b, c = [x-.2,y,0], [x+.1,y,.2], [x+.1,y,0]
            carrier, shock, wheel = 'carrier_'+suffix, 'shock_'+suffix, 'wheel_'+suffix
            # Very small positive physical masses keep the fixture tensor
            # valid; their exact gravitational derivative is checked below.
            body(carrier, a, .01)
            body(shock+'_upper', b, .01)
            body(shock+'_lower', c, .01)
            body(wheel, [x,y,0], .01)
            suspension.append({'name': suffix, 'carrier_group': carrier, 'shock_group': shock,
                'chassis_biela_hinge_axis_evidence': {'axis_line_point_base_m': a},
                'chassis_shock_eye_axis_evidence': {'axis_line_point_base_m': b},
                'biela_shock_eye_axis_evidence': {'axis_line_point_base_m': c}})
            wheels.append({'name': suffix, 'group': wheel, 'center_base_m': [x,y,0]})
        report = cad.suspension_preload_estimates(links, poses, {'suspension': suspension, 'wheels': wheels})
        normals = sum(row['wheel_normal_force_n'] for row in report.values())
        self.assertAlmostEqual(normals, 10.16*9.81, places=10)
        for row in report.values():
            self.assertAlmostEqual(row['spring_length_derivative_m_rad'], .3)
            # lower shock .01 kg at x=.3 and wheel .01 kg at x=.2
            potential_derivative = -.01*9.81*(.3+.2)
            expected = (row['wheel_normal_force_n']*.2+potential_derivative)/.3
            self.assertAlmostEqual(row['spring_extension_force_n'], expected, places=10)


if __name__ == '__main__':
    unittest.main()
