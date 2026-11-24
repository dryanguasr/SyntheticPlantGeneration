"""Guard the physical acceptance contract across isolated commissioning runs."""
import importlib.util
from copy import deepcopy
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
from uchuva_gazebo.robot_spec import resolve_robot_profile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cad_mobility_protocol',ROOT/'scripts/probe_cad_mobility.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


class MobilityProtocolTests(unittest.TestCase):
    def test_integrated_arm_preserves_mobility_and_uses_strict_observed_targets(self):
        original=probe.protocol(.298218,.0001)
        combined=probe.protocol(.298218,.0001,'integrated_arm')
        self.assertEqual(combined['duration_s'],21)
        self.assertEqual(combined['acceptance'],original['acceptance'])
        self.assertEqual(combined['ground_contact'],original['ground_contact'])
        for key,value in original['criteria'].items():
            if key!='minimum_observed_span_s':self.assertEqual(combined['criteria'][key],value)
        for old in original['phases'][2:]:
            new=next(p for p in combined['phases'] if p['name']==old['name'])
            self.assertEqual({**old,'start_s':old['start_s']+6,'end_s':old['end_s']+6},new)
        self.assertEqual(combined['criteria']['arm_target_error_rad'],.01)
        self.assertEqual(combined['criteria']['arm_settled_velocity_rad_s'],.01)
        robot=resolve_robot_profile('proxy_v1')
        targets=probe.arm_phase_targets(robot,combined)
        for name,home in robot.data['arm_home_positions'].items():
            self.assertAlmostEqual(targets['arm_positive'][name],home+.08)
            self.assertAlmostEqual(targets['arm_negative'][name],home-.08)
            self.assertEqual(targets['arm_return'][name],home)
        combined['phases'][2]['arm_offset_rad']=100
        with self.assertRaisesRegex(ValueError,'travel'):probe.arm_phase_targets(robot,combined)

    def test_arm_excursion_cannot_pass_with_static_missing_or_unsettled_observations(self):
        robot=resolve_robot_profile('proxy_v1');config=probe.protocol(.3,.0001,'integrated_arm')
        targets=probe.arm_phase_targets(robot,config);joints=[];poses=[]
        for phase in config['phases']:
            if 'arm_offset_rad' not in phase:continue
            for i in range(50):
                stamp=phase['end_s']-.5+i*.01
                joints.append({'sim_time':stamp,'joints':[{'name':name,'position':q,'velocity':0.,
                    'max_abs_velocity_window':0.,'position_available':True,'velocity_available':True}
                    for name,q in targets[phase['name']].items()]})
                poses.append({'sim_time':stamp,'pose':[0,0,.3,0,0,0,1]})
        self.assertTrue(all(row['passed'] for row in probe.arm_sequence_checks(robot,config,joints,poses)))
        for field,value in (('position',0.),('max_abs_velocity_window',.011),('position_available',False)):
            altered=deepcopy(joints);altered[0]['joints'][0][field]=value
            self.assertFalse(all(row['passed'] for row in probe.arm_sequence_checks(robot,config,altered,poses)))
        self.assertFalse(all(row['passed'] for row in probe.arm_sequence_checks(robot,config,joints[20:],poses)))
        self.assertFalse(all(row['passed'] for row in probe.arm_sequence_checks(robot,config,joints,poses[20:])))

    def test_isolation_keeps_physical_thresholds_and_three_second_turn(self):
        full=probe.protocol(.298218,.0001)
        short=probe.protocol(.298218,.0001,'turn_only')
        self.assertEqual(full['duration_s'],15)
        self.assertEqual(short['duration_s'],6)
        # PoseV at the phase endpoint requires the next step's native observer
        # response. Guard collection adds no extra motion phase or tolerance.
        self.assertEqual(full['observation_tail_s'],full['dt_s'])
        self.assertEqual(short['observation_tail_s'],short['dt_s'])
        self.assertEqual(full['acceptance'],short['acceptance'])
        self.assertEqual(full['ground_contact'],short['ground_contact'])
        for name,value in full['criteria'].items():
            if name!='minimum_observed_span_s':self.assertEqual(value,short['criteria'][name],name)
        for config in (full,short):
            turn=next(p for p in config['phases'] if p['name']=='turn')
            self.assertEqual(turn['end_s']-turn['start_s'],3)
            self.assertEqual(turn['angular_rad_s'],.2)
            self.assertFalse(config['pose_commands_used'])
        self.assertIn('never substitutes',short['scope'])

    def test_unknown_experiment_cannot_silently_become_full_admission(self):
        with self.assertRaisesRegex(ValueError,'Unknown'):
            probe.protocol(.298218,.0001,'unknown')

    def test_native_collision_detector_is_explicit_and_historical_default_is_ode(self):
        robot=resolve_robot_profile('proxy_v1')
        config=probe.protocol(.3,.0001)
        config['physics']={'backend':'DART','solver_type':'pgs','maximum_step_s':.0001,'collision_detector':'fcl'}
        sdf=ET.fromstring(probe.world(robot,config))
        self.assertEqual(sdf.findtext('world/physics/dart/collision_detector'),'fcl')
        self.assertEqual(sdf.findtext('world/physics/dart/solver/solver_type'),'pgs')
        del config['physics']['collision_detector']
        sdf=ET.fromstring(probe.world(robot,config))
        self.assertEqual(sdf.findtext('world/physics/dart/collision_detector'),'ode')


if __name__=='__main__':unittest.main()
