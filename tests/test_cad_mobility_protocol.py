"""Guard the physical acceptance contract across isolated commissioning runs."""
import importlib.util
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest
import xml.etree.ElementTree as ET
from uchuva_gazebo.robot_spec import resolve_robot_profile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cad_mobility_protocol',ROOT/'scripts/probe_cad_mobility.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


class MobilityProtocolTests(unittest.TestCase):
    def test_sequential_payload_only_changes_order_and_never_moves_jaw_with_arm(self):
        concurrent=probe.protocol(.296218,.0001,'payload_arm')
        sequential=probe.protocol(.296218,.0001,'payload_sequential')
        for key in ('acceptance','jaw_acceptance','ground_contact','start_xyzyaw','dt_s'):
            self.assertEqual(concurrent[key],sequential[key])
        self.assertEqual(sequential['duration_s'],16)
        self.assertTrue(all(p['end_s']-p['start_s']==2 for p in sequential['phases']))
        for key,value in concurrent['criteria'].items():
            if key!='minimum_observed_span_s':self.assertEqual(value,sequential['criteria'][key])
        arms=[p for p in sequential['phases'] if 'arm_offset_rad' in p]
        self.assertEqual([p['arm_offset_rad'] for p in arms],[.08,-.08,0.])
        self.assertTrue(all(not p['jaw_open'] for p in arms))
        self.assertTrue(sequential['phases'][2]['jaw_open'])
        self.assertFalse(sequential['phases'][3]['jaw_open'])
        self.assertTrue(sequential['phases'][-1]['jaw_open'])

    def test_payload_startup_keeps_limits_and_only_observes_impact(self):
        full=probe.protocol(.298218,.0001,'payload_arm');short=probe.protocol(.298218,.0001,'payload_startup')
        for key in ('acceptance','jaw_acceptance','ground_contact','start_xyzyaw','dt_s'):
            self.assertEqual(full[key],short[key])
        self.assertEqual(short['duration_s'],.1)
        self.assertEqual(short['robot_telemetry_publish_rate_hz'],10000)
        self.assertTrue(all(p['linear_m_s']==p['angular_rad_s']==0 and not p['jaw_open'] for p in short['phases']))
        self.assertTrue(all('arm_offset_rad' not in p for p in short['phases']))

    def test_payload_arm_reuses_strict_arm_and_physics_contract_without_drive_claim(self):
        integrated=probe.protocol(.298218,.0001,'integrated_arm')
        short=probe.protocol(.298218,.0001,'payload_arm')
        self.assertEqual(short['duration_s'],10)
        self.assertEqual([{k:v for k,v in p.items() if k!='jaw_open'} for p in short['phases']],integrated['phases'][:5])
        self.assertEqual(short['acceptance'],integrated['acceptance'])
        self.assertEqual(short['ground_contact'],integrated['ground_contact'])
        self.assertEqual(short['criteria']['arm_target_error_rad'],.01)
        self.assertEqual(short['criteria']['arm_settled_velocity_rad_s'],.01)
        self.assertEqual(short['acceptance']['joint_velocity_tolerance_rad_s'],.03)
        self.assertTrue(all(p['linear_m_s']==p['angular_rad_s']==0 for p in short['phases']))
        self.assertIn('cannot validate drive',short['schedule_revision'])
        robot=resolve_robot_profile('proxy_v1')
        self.assertTrue(probe.arm_sequence_checks(robot,short,[],[]))
        self.assertTrue(all(not row['passed'] for row in probe.arm_sequence_checks(robot,short,[],[])))

    def test_payload_jaw_has_si_limits_and_requires_open_closed_native_excursions(self):
        config=probe.protocol(.3,.0001,'payload_arm')
        robot=SimpleNamespace(joints=[{'name':'jaw','type':'prismatic','limits':{'lower':0.,'upper':.006,'velocity':.005,'effort':2.}}],
            data={'control':{'gripper':{'jaw':{}}},'parameters':{'demo_jaw_open_position_m':.006}})
        targets=probe.jaw_phase_targets(robot,config);rows=[]
        for phase in config['phases']:
            for i in range(20):
                rows.append({'sim_time':phase['end_s']-.2+i*.01,'joints':[{'name':'jaw','position':targets[phase['name']]['jaw'],
                    'velocity':0.,'max_abs_velocity_window':0.,'force_command':.1,'max_abs_force_command_window':.1,
                    'position_available':True,'velocity_available':True,'force_command_available':True}]})
        force=[{'joint_name':'jaw','joint_type':'prismatic','position_unit':'m','velocity_unit':'m/s','force_unit':'N'}]
        self.assertTrue(all(c['passed'] for c in probe.jaw_sequence_checks(robot,config,rows,force)))
        for field,value in (('position',0.),('max_abs_velocity_window',.005501),('force_command',2.01)):
            altered=deepcopy(rows);altered[30]['joints'][0][field]=value
            self.assertFalse(all(c['passed'] for c in probe.jaw_sequence_checks(robot,config,altered,force)))
        force[0]['position_unit']='rad'
        self.assertFalse(all(c['passed'] for c in probe.jaw_sequence_checks(robot,config,rows,force)))

    def test_fixed_gripper_guard_includes_passive_descendants_but_not_suspension(self):
        # Structural fixture deliberately avoids a gripper naming prefix.
        joints=[{'name':'arm','parent':'base','child':'wrist','group':'arm','type':'revolute'},
            {'name':'driver','parent':'wrist','child':'gear','group':'fixed','type':'fixed'},
            {'name':'jaw','parent':'wrist','child':'jaw_link','group':'passive','type':'fixed'},
            {'name':'closure_pin','parent':'jaw_link','child':'tip','group':'passive','type':'fixed'},
            {'name':'suspension','parent':'base','child':'carrier','group':'passive','type':'revolute'}]
        probe.require_fixed_gripper_diagnostic(SimpleNamespace(joints=joints))
        for index in (1,2,3):
            moving=deepcopy(joints);moving[index]['type']='revolute'
            with self.assertRaisesRegex(ValueError,'every tool-subtree joint fixed'):
                probe.require_fixed_gripper_diagnostic(SimpleNamespace(joints=moving))
        outside=deepcopy(joints);outside[1].update(parent='base',group='gripper')
        with self.assertRaisesRegex(ValueError,'inside the terminal-arm'):
            probe.require_fixed_gripper_diagnostic(SimpleNamespace(joints=outside))

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
