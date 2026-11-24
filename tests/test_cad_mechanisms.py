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
import admit_cad_gripper_envelope as admission


class MechanismTests(unittest.TestCase):
    def test_envelope_fingerprint_allows_pid_but_rejects_changed_joint_axis(self):
        data={'links':[{'name':'jaw','visuals':[{'name':'part_104','pose':{},'geometry':{'type':'mesh','uri':'a.obj','sha256':'same','scale':[1,1,1]}}]}],
              'joints':[{'name':'pivot','type':'revolute','parent':'base','child':'jaw','origin':{},'child_pose':{},'axis':[0,1,0],'zero_offset':0,'damping':.002}],
              'control':{'gain':1},'frames':[]}
        expected=admission.kinematic_visual_fingerprint(data)
        moved=copy.deepcopy(data);moved['control']['gain']=2;moved['joints'][0]['damping']=.004
        moved['links'][0]['visuals'][0]['geometry']['uri']='portable/new.obj'
        self.assertEqual(expected,admission.kinematic_visual_fingerprint(moved))
        moved['joints'][0]['axis']=[1,0,0]
        self.assertNotEqual(expected,admission.kinematic_visual_fingerprint(moved))

    def test_cover_tangency_cannot_hide_penetration_or_out_of_plane_motion(self):
        identity=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
        names=['Gripper 1:1','Eslabon L:1','Eslabon L:2']
        motion={'assembly_sha256':'a','samples':[{'driver_rad':q,'occurrence_transforms_m':{n:identity.copy() for n in names}} for q in (0,.1)]}
        geometry={'status':'COMPLETED','source_files_unchanged':True,'assembly_sha256':'a','pairs':[]}
        for name in names[1:]:
            geometry['pairs'].append({'occurrences':[names[0],name],'driver_rad':0,'interference_count':0,
                'interference_volumes_m3':[],'minimum_distance_m':0,'visualization_parts':[
                    {'occurrence':names[0],'native_body_range_bounds_m':{'min':[0,.0035,0],'max':[1,.005,1]}},
                    {'occurrence':name,'native_body_range_bounds_m':{'min':[0,.0005,0],'max':[1,.0035,1]}}]})
        self.assertFalse(admission.prove_cover_tangencies(geometry,motion)['positive_clearance_claimed'])
        bad=copy.deepcopy(geometry);bad['pairs'][0]['interference_volumes_m3']=[1e-15]
        with self.assertRaises(ValueError):admission.prove_cover_tangencies(bad,motion)
        bad=copy.deepcopy(motion);bad['samples'][1]['occurrence_transforms_m']['Eslabon L:1'][7]=.0001
        with self.assertRaises(ValueError):admission.prove_cover_tangencies(geometry,bad)

    def test_operational_admission_keeps_reserve_and_ligament_independent(self):
        revision={'original_sources_unchanged':True,'full_arm_reference':{'status':'PRIVATE_CHAIN_VERIFIED'},
            'maximum_saved_assembly_transform_change':0,'feature':{'pin_hole_preserved':True},
            'final_L2_copy_sha256':'same','native_matching_planes':[{}],
            'plan':{'original_part_sha256':'same','pin_hole_radius_m':.0015,'target_driver_rad':.08},
            'actual_cut_planes':[{'offset_local_m':.003405}]}
        pairs=[{'occurrences':p.copy(),'continuous_lower_gap_m':.001} for p in admission.EXPECTED_PAIRS]
        critical=admission.EXPECTED_PAIRS.index(['Gripper y engranaje:1','Eslabon L:1'])
        pairs[critical]['continuous_lower_gap_m']=.000201
        summary={'pairs':pairs,'driver_interval_rad':[0,.08]}
        observed={'source_files_unchanged':True,'pairs':[{'interference_count':0,'interference_volumes_m3':[]}]}
        self.assertEqual(admission.evaluate(revision,{},observed,summary)['status'],'PASS')
        bad=copy.deepcopy(summary);bad['pairs'][critical]['continuous_lower_gap_m']=.000199
        self.assertEqual(admission.evaluate(revision,{},observed,bad)['status'],'FAIL')
        bad=copy.deepcopy(revision);bad['actual_cut_planes'][0]['offset_local_m']=.003399
        self.assertEqual(admission.evaluate(bad,{},observed,summary)['status'],'FAIL')

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
