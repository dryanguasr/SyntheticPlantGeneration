import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cad_drive_revision',ROOT/'scripts/prepare_cad_drive_revision.py')
revision=importlib.util.module_from_spec(spec);spec.loader.exec_module(revision)


def fixture(p_gain=30):
    data={'physics':{'maximum_step_s':.0001},
          'links':[{'name':'wheel','inertial':{'mass_kg':1.,'com_m':[.01,.02,.03],
                    'tensor_kg_m2':[.003,.005,.003,0,0,0]}}],
          'joints':[{'name':'drive','group':'drive','child':'wheel','axis':[0,1,0],
                     'child_pose':{'xyz_m':[0,0,0],'quaternion_xyzw':[0,0,0,1]}}],
          'control':{'drive':{'joints':{'drive':{'p_gain':p_gain,'i_gain':4}}}}}
    return SimpleNamespace(to_dict=lambda:copy.deepcopy(data)),data


class DriveRevisionTests(unittest.TestCase):
    def test_axis_inertia_includes_only_perpendicular_com_distance(self):
        robot,_=fixture()
        analysis=revision.wheel_pi_analysis(robot)
        self.assertAlmostEqual(analysis['rows'][0]['axis_inertia_kg_m2'],.006)
        self.assertAlmostEqual(analysis['rows'][0]['dt_p_over_inertia'],.5)
        self.assertTrue(analysis['all_local_checks_passed'])
        self.assertIn('not proof',analysis['scope'])

    def test_unstable_discretization_and_unverified_frame_are_not_accepted(self):
        robot,data=fixture(200)
        self.assertFalse(revision.wheel_pi_analysis(robot)['all_local_checks_passed'])
        data['joints'][0]['child_pose']['xyz_m'][0]=.01
        with self.assertRaisesRegex(ValueError,'joint frame'):
            revision.wheel_pi_analysis(robot)


if __name__=='__main__':unittest.main()
