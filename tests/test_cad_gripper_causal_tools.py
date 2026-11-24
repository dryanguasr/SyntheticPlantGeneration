"""Controls preserve physical data and distinguish model omissions from fixes."""
import copy
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from analyze_cad_gripper_coupling import coupled_screen,polynomial_roots
from probe_cad_gripper_contacts import diagnostic_profile,instrument_contacts,native_collision_detectors
from analyze_cad_gripper_tree import identity,inverse,multiply,projected_poles,observed_mode
from probe_cad_gripper_contact import fruit_fixture,verify_opening_clearance,nonseparating_pedicel_contact,native_contact_time


class CausalGripperToolsTests(unittest.TestCase):
    def test_bullet_proximity_points_do_not_trigger_pedicel_contact(self):
        pad='harvester::gripper_left_jaw::part_113_bounds'
        contact={'collision1':{'name':pad},'collision2':{'name':'fruit_fixture::fruit_link::distal_pedicel'},
                 'depth':[-.000187,-.000055]}
        self.assertFalse(nonseparating_pedicel_contact(contact,pad))
        for depths in ([],[float('nan')],[float('inf')],[True]):
            self.assertFalse(nonseparating_pedicel_contact({**contact,'depth':depths},pad))
        self.assertTrue(nonseparating_pedicel_contact({**contact,'depth':[-.0001,0]},pad))
        self.assertTrue(nonseparating_pedicel_contact({**contact,'depth':[1e-6]},pad))
        self.assertFalse(nonseparating_pedicel_contact({**contact,'depth':[1e-6],
            'collision2':{'name':'fruit_fixture::fruit_link::berry'}},pad))

    def test_contact_time_requires_native_stamp_and_does_not_use_arrival(self):
        self.assertEqual(native_contact_time({'header':{'stamp':{'sec':'1','nsec':270200000}}}),1.2702)
        self.assertIsNone(native_contact_time({'observation_sim_time':1.2701}))
        self.assertIsNone(native_contact_time({'header':{'stamp':{'sec':'NaN'}}}))
        self.assertIsNone(native_contact_time({'header':{'stamp':{'sec':1,'nsec':1000000000}}}))

    def test_final_witness_uses_v8_pedicel_diameter_without_changing_body_offset(self):
        pose={'xyz_m':[0,0,0],'quaternion_xyzw':[0,0,0,1]}
        root=ET.fromstring(fruit_fixture(pose))
        radius=float(root.findtext("model/link/collision[@name='distal_pedicel']/geometry/cylinder/radius"))
        self.assertAlmostEqual(radius*2,.0036)
        self.assertAlmostEqual(float(root.findtext('model/pose').split()[1]),-.03)

    def test_extended_opening_requires_matching_admitted_mesh_and_covered_interval(self):
        from admit_cad_gripper_envelope import kinematic_visual_fingerprint
        data={'links':[{'name':'jaw','visuals':[{'name':'L1','pose':{'xyz_m':[0,0,0],'quaternion_xyzw':[0,0,0,1]},
            'geometry':{'type':'mesh','sha256':'a'*64}}]}],'joints':[],'frames':[]}
        evidence={'status':'PASS','interval_rad':[0,.085],'cad_part_sha256':'b'*64,'visual_obj_sha256':'a'*64}
        evidence['kinematic_visual_fingerprint']=kinematic_visual_fingerprint(data)
        verify_opening_clearance(data,.08481092765,evidence)
        for invalid in ({**evidence,'status':'FAIL'},{**evidence,'interval_rad':[0,.08]},
                        {**evidence,'visual_obj_sha256':'c'*64},{**evidence,'kinematic_visual_fingerprint':'d'*64}):
            with self.assertRaises(ValueError):verify_opening_clearance(data,.08481092765,invalid)
    def test_native_detector_identity_ignores_terminal_color_only(self):
        self.assertEqual(native_collision_detectors('[Msg] Using [\x1b[0m\x1b[1;32mfcl\x1b[0m] collision detector'),['fcl'])
        self.assertEqual(native_collision_detectors('Requested fcl collision detector'),[])
    def test_contact_instrumentation_changes_only_sensor_elements(self):
        root=ET.fromstring('<sdf><world><model><link name="gripper_a"><inertial><mass>2</mass></inertial>'
            '<collision name="one"><geometry><sphere><radius>.02</radius></sphere></geometry></collision>'
            '<collision name="two"><geometry><box><size>1 2 3</size></box></geometry></collision>'
            '</link><link name="gripper_b"/></model></world></sdf>')
        before=ET.tostring(root);sensors=instrument_contacts(root)
        self.assertEqual(len(sensors),2)
        self.assertEqual({row['collision'] for row in sensors},{'one','two'})
        for link in root.findall('world/model/link'):
            for sensor in list(link.findall('sensor')):link.remove(sensor)
        self.assertEqual(ET.tostring(root),before)

    def test_no_contact_control_has_separate_hash_and_preserves_mass_joints_gains(self):
        from uchuva_gazebo.robot_spec import canonical_hash
        source={'profile_id':'fixture','capabilities':['native_harvest','fk'],
            'links':[{'name':name,'collisions':[{'name':'c'}],'inertial':{'mass_kg':.2},'visuals':[1]}
                     for name in ('arm_wrist_roll','gripper_jaw','base_link')],
            'joints':[{'name':'driver','axis':[0,1,0]}],'control':{'gripper':{'driver':{'p_gain':.2}}},
            'provenance':{},'physics':{'solver_type':'pgs'}}
        original=copy.deepcopy(source);derived,removed=diagnostic_profile(source,True)
        self.assertEqual(source,original)
        self.assertNotEqual(canonical_hash(source),canonical_hash(derived))
        self.assertEqual(len(removed),2)
        self.assertNotIn('native_harvest',derived['capabilities'])
        self.assertEqual(derived['joints'],source['joints'])
        self.assertEqual(derived['control'],source['control'])
        self.assertEqual(derived['links'][2],source['links'][2])
        for before,after in zip(source['links'],derived['links']):
            self.assertEqual(before['inertial'],after['inertial'])
            self.assertEqual(before['visuals'],after['visuals'])

    def test_detector_revision_is_canonical_and_retains_all_geometry(self):
        source={'profile_id':'fixture','capabilities':['fk'],'links':[],'provenance':{},'physics':{'solver_type':'pgs'}}
        derived,removed=diagnostic_profile(source,False,'fcl')
        self.assertEqual(derived['physics']['collision_detector'],'fcl')
        self.assertEqual(derived['links'],source['links'])
        self.assertEqual(removed,[])
        self.assertNotIn('collision_detector',source['physics'])

    def test_ramped_controller_revision_preserves_gains_rate_and_physical_inputs(self):
        source={'profile_id':'fixture','links':[{'name':'jaw','collisions':[1],'inertial':2}],
            'joints':[3],'control':{'gripper':{'driver':{'p_gain':.2,'d_gain':.01,'command_velocity':1}},
            'arm':{'joint':{'p_gain':7}}},'provenance':{}}
        derived,removed=diagnostic_profile(source,reference_mode='ramped_position')
        self.assertEqual(derived['links'],source['links'])
        self.assertEqual(derived['joints'],source['joints'])
        self.assertEqual(derived['control']['arm'],source['control']['arm'])
        control=derived['control']['gripper']['driver']
        self.assertEqual(control.pop('reference_mode'),'ramped_position')
        self.assertEqual(control,source['control']['gripper']['driver'])
        self.assertEqual(removed,[])

    def test_poles_are_checked_against_known_distinct_roots(self):
        # Product (x-.2)(x+.4)(x-.8)(x-.9).
        roots=polynomial_roots([1,-1.5,.3,.28,-.0576])
        self.assertLess(max(abs(root.imag) for root in roots),1e-9)
        for actual,expected in zip(roots,(-.4,.2,.8,.9)):self.assertAlmostEqual(actual.real,expected,places=8)

    def test_tree_projection_reduces_to_closed_model_without_extra_coordinates(self):
        inertia=[3e-6,4e-6];di=[.001,.002];step=.0001
        mass=[[inertia[0],0],[0,inertia[1]]];damping=[[di[0],0],[0,di[1]]]
        stiffness=[[100.2,100],[100,100]];explicit=[[.022,.012],[.012,.012]]
        tree=projected_poles(mass,damping,stiffness,explicit,identity(2),step,mass)
        reduced=coupled_screen(inertia,di,100,.012,.2,.01,step)
        self.assertAlmostEqual(tree['spectral_radius'],reduced['spectral_radius'],places=10)
        product=multiply(mass,inverse(mass))
        for i in range(2):
            for j in range(2):self.assertAlmostEqual(product[i][j],float(i==j),places=12)

    def test_native_mode_analysis_detects_alternation_and_refuses_dropped_step(self):
        rows=[{'sim_time':i*.0001,'status':'active','measured_velocity_rad_s':(-1.)**i*.1,
               'requested_target_position_rad':0} for i in range(800)]
        result=observed_mode(rows)
        for window in result['windows']:
            self.assertAlmostEqual(window['velocity_lag_one_slope'],-1)
            self.assertEqual(window['sign_changes'],window['samples']-1)
        del rows[4]
        with self.assertRaises(ValueError):observed_mode(rows)

    def test_motor_damping_omission_cannot_be_mistaken_for_native_instability(self):
        inertia=[3.348944713986979e-6,3.801686757081188e-6]
        implicit=[.002*(2.8828351550687343**2+(.1814412764885399-1)**2),
                  .002*(2.80359215694512**2+(.3718142887178245-1)**2)]
        incomplete=coupled_screen(inertia,[0,0],100,.03,.2,.01,.0001)
        complete=coupled_screen(inertia,implicit,100,.03,.2,.01,.0001)
        self.assertAlmostEqual(incomplete['spectral_radius'],1.1560323948589777,places=10)
        self.assertFalse(incomplete['linearly_stable_in_this_reduced_model'])
        self.assertTrue(complete['linearly_stable_in_this_reduced_model'])
        self.assertGreater(complete['minus_one_margin_eigenvalues'][0],0)
        with self.assertRaises(ValueError):coupled_screen([0,1],implicit,100,.03,.2,.01,.0001)


if __name__=='__main__':unittest.main()
