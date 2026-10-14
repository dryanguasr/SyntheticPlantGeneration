import unittest
from uchuva_gazebo.motion_observations import RelativeMotion


class MotionTests(unittest.TestCase):
    def test_contract_rejects_truth_and_invalid_covariance(self):
        cov=tuple(tuple(.01 if i==j else 0 for j in range(6)) for i in range(6))
        data=RelativeMotion(1,2,(.1,0,0),(0,0,.01),cov).to_dict()
        self.assertEqual(RelativeMotion.from_dict(data).to_dict(),data)
        with self.assertRaises(ValueError):RelativeMotion.from_dict(dict(data,world_pose=[1,2,3]))
        bad=dict(data);bad['end_stamp_ns']=0
        with self.assertRaises(ValueError):RelativeMotion.from_dict(bad)
        bad=dict(data);bad['covariance_6x6']=[[-1 if i==j else 0 for j in range(6)] for i in range(6)]
        with self.assertRaises(ValueError):RelativeMotion.from_dict(bad)


if __name__=='__main__':unittest.main()
