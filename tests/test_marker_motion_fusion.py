import unittest
import numpy as np
from uchuva_gazebo.marker_motion_fusion import MarkerMotionFusion,exp,canonical_visual_measurements,marker_projection_covariance
from uchuva_gazebo.motion_observations import RelativeMotion


class FusionTests(unittest.TestCase):
    def test_projection_covariance_noise_and_scale(self):
        K=np.array([[900.,0,640],[0,900,360],[0,0,1]])
        R=exp([.2,.1,.05]);t=np.array([.1,.2,2.])
        Q=marker_projection_covariance(R,t,K,.15,.5)
        self.assertGreater(np.linalg.eigvalsh(Q).min(),0)
        self.assertGreater(np.linalg.norm(Q[:3,3:]),1e-6)
        np.testing.assert_allclose(marker_projection_covariance(R,t,K,.15,1.),4*Q)
        scaled=marker_projection_covariance(R,2*t,K,.30,.5)
        units=np.diag([2,2,2,1,1,1])
        np.testing.assert_allclose(scaled,units@Q@units,rtol=2e-5,atol=1e-9)

    def test_projection_covariance_rejects_invalid_geometry(self):
        K=np.array([[900.,0,640],[0,900,360],[0,0,1]])
        for rotation,translation,side,sigma in [
                (np.eye(3),[0,0,-1],.15,.5),
                (np.eye(3),[0,0,1],0,.5),
                (np.eye(3),[0,0,1],.15,0),
                (np.eye(3)*2,[0,0,1],.15,.5)]:
            with self.assertRaises(ValueError):
                marker_projection_covariance(rotation,translation,K,side,sigma)

    def test_decoded_keys_do_not_retransform_canonical_poses(self):
        pose={'R':np.eye(3).tolist(),'t':[1,2,3]}
        rows=canonical_visual_measurements({'9':pose},{'8':8,'9':8})
        self.assertEqual(rows[0][0],8)
        self.assertIs(rows[0][1],pose)
        with self.assertRaises(KeyError):canonical_visual_measurements({'99':pose},{'9':8})

    def test_rotated_camera_motion_and_reanchoring(self):
        f=MarkerMotionFusion(8);R=exp([0,0,np.pi/2]);Q=np.eye(6)*.001
        f.correct(0,8,R.T,[0,0,0],Q)
        m=RelativeMotion(0,1,(1,0,0),(0,0,0),tuple(map(tuple,Q)))
        f.predict(m.to_dict())
        np.testing.assert_allclose(f.t,[0,1,0],atol=1e-8)
        self.assertTrue(f.correct(1,8,R.T,(-R.T@np.array([0,1.01,0])).tolist(),Q))
        self.assertGreater(f.t[1],1)
        self.assertLess(np.linalg.eigvalsh(f.P).min(),.003)
        self.assertFalse(f.correct(1,8,R.T,[100,0,0],Q))
        with self.assertRaises(ValueError):f.predict(m.to_dict())
        with self.assertRaises(ValueError):f.correct(1,9,R.T,[0,0,0],Q)

    def test_no_anchor_no_world_origin(self):
        f=MarkerMotionFusion(0)
        self.assertIsNone(f.camera_from_marker())
        with self.assertRaises(ValueError):f.predict(RelativeMotion(0,1,(0,0,0),(0,0,0),tuple(map(tuple,np.eye(6)))).to_dict())


if __name__=='__main__':unittest.main()
