import unittest
import numpy as np
import sys
from pathlib import Path
from uchuva_gazebo.continuous_evaluation import one_to_one_masks,target_scope,mask_iou_matrix
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from diagnose_continuous_geometry import true_marker_pose


class EvaluationTests(unittest.TestCase):
    def test_privileged_camera_transform_has_expected_optical_axes(self):
        half=np.sqrt(.5)
        pose=true_marker_pose(dict(position=[0,-2,.7],quaternion_xyzw=[0,0,half,half]),
            dict(normal_world=[0,-1,0],center_world_m=[0,0,.12]))
        np.testing.assert_allclose(pose['R'],np.diag([1,-1,-1]),atol=1e-12)
        np.testing.assert_allclose(pose['t'],[0,.585,1.932],atol=1e-12)

    def test_one_to_one_augmenting_match(self):
        matches=one_to_one_masks(np.array([[.9,.8],[.85,.1]]))
        self.assertEqual(matches,{0:1,1:0})

    def test_background_not_denominator_but_unmatched_prediction_retained(self):
        instances=[dict(code=2),dict(code=1)]
        objects={'1':dict(role='target'),'2':dict(role='background')}
        indices,ignore=target_scope(np.array([[.9,0],[0,.8],[0,0]]),instances,objects)
        self.assertEqual(indices,[1]);self.assertEqual(ignore.tolist(),[True,False,False])

    def test_single_visible_pixel_remains_in_denominator(self):
        codes=np.array([[1,0],[0,2]])
        instances=[dict(code=1,bbox=[0,0,1,1],pixels=1),dict(code=2,bbox=[1,1,2,2],pixels=1)]
        result=mask_iou_matrix([codes==1],codes,instances)
        self.assertEqual(result.tolist(),[[1.,0.]])


if __name__=='__main__':unittest.main()
