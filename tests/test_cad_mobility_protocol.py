"""Guard the physical acceptance contract across isolated commissioning runs."""
import importlib.util
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
from uchuva_gazebo.robot_spec import resolve_robot_profile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cad_mobility_protocol',ROOT/'scripts/probe_cad_mobility.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


class MobilityProtocolTests(unittest.TestCase):
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
