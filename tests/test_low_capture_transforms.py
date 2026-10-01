"""Evaluator transforms and conservative executed-route certificates."""
import importlib.util
from pathlib import Path
import unittest
import tempfile
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('low_capture',ROOT/'scripts/validate_low_capture.py')
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
material_spec=importlib.util.spec_from_file_location('prepare_low',ROOT/'scripts/prepare_low_flight.py')
prepare=importlib.util.module_from_spec(material_spec);material_spec.loader.exec_module(prepare)


class CaptureTests(unittest.TestCase):
    def test_each_calyx_loads_only_its_own_material(self):
        inventory=[{'model_name':f'calyx_{i:05d}','color':[.1*i,.2,.3,1]} for i in range(3)]
        with tempfile.TemporaryDirectory() as temp:
            prepare.write_calyx_materials(Path(temp),inventory)
            for obj in inventory:
                text=(Path(temp)/f'{obj["model_name"]}.mtl').read_text()
                self.assertEqual(text.count('newmtl '),1)
                self.assertEqual([float(v) for v in next(l for l in text.splitlines() if l.startswith('Kd ')).split()[1:]],obj['color'][:3])

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
