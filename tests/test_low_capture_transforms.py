"""Evaluator transforms and conservative executed-route certificates."""
import importlib.util
from pathlib import Path
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('low_capture',ROOT/'scripts/validate_low_capture.py')
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)


class CaptureTests(unittest.TestCase):
    def test_optical_axes_and_metric_offset(self):
        samples=[{'t':t,'position':[1,2,3],'quaternion_xyzw':[0,0,0,1]} for t in (0,1)]
        R,C,dt=capture.camera_pose(samples,500_000_000,pitch=0)
        np.testing.assert_allclose(C,[1.068,2,3.005])
        np.testing.assert_allclose(R@[0,0,1],[1,0,0])
        np.testing.assert_allclose(R@[1,0,0],[0,-1,0])
        np.testing.assert_allclose(R@[0,1,0],[0,0,-1])
        self.assertEqual(dt,1)

    def test_pose_quaternion_sign_does_not_flip_interpolation(self):
        samples=[{'t':0,'position':[0,0,0],'quaternion_xyzw':[0,0,0,1]},
                 {'t':1,'position':[1,0,0],'quaternion_xyzw':[0,0,0,-1]}]
        _,C,_=capture.camera_pose(samples,500_000_000,pitch=0)
        np.testing.assert_allclose(C,[.568,0,.005])
        with self.assertRaises(ValueError):capture.camera_pose(samples,2_000_000_000)

    def test_executed_clearance_loses_bound_when_route_deviates(self):
        preflight={'minimum_clearance_lower_bound_m':.25,
                   'segments':[{'from_m':[0,0,0],'to_m':[1,0,0]}],
                   'samples':[{'center_m':[0,0,0],'envelope_clearance_lower_bound_m':.25},
                              {'center_m':[1,0,0],'envelope_clearance_lower_bound_m':.25}]}
        samples=[{'t':0,'position':[0,.2,0]},{'t':1,'position':[0,.2,0]}]
        self.assertFalse(capture.audit_executed(samples,preflight)['passed'])


if __name__=='__main__':unittest.main()
