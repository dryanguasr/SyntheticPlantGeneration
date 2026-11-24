import copy
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from preflight_cad_v8_reach import orientation_enclosure,axis_quaternion


class CadV8PreflightTests(unittest.TestCase):
    def fixture(self):
        axes=[[0.,0.,1.],[0.,1.,0.],[0.,1.,0.],[0.,1.,0.],[1.,0.,0.]]
        return SimpleNamespace(joints=[{'axis':axis,'origin':{'quaternion_xyzw':[0,0,0,1]},
            'child_pose':{'quaternion_xyzw':[0,0,0,1]},'zero_offset':0} for axis in axes],
            mount={'quaternion_xyzw':[0,0,0,1]},bounds=[(-.1,.1)]*5,
            frame={'pose':{'quaternion_xyzw':axis_quaternion([1,0,0],math.pi/2)}})
    def test_enclosure_contains_known_parallel_pitch_roll_extremum(self):
        result=orientation_enclosure(self.fixture(),8)
        self.assertEqual(result['status'],'ENCLOSED')
        lo,hi=result['theta_from_vertical_interval_rad']
        exact_max=math.acos(math.cos(.3)*math.cos(.1))
        self.assertLessEqual(lo,0)
        self.assertGreaterEqual(hi,exact_max)
        self.assertLess(hi-exact_max,.1)
    def test_nonparallel_or_tilted_mount_is_not_given_the_same_certificate(self):
        chain=self.fixture();chain.joints[2]['axis']=[1.,0.,0.]
        self.assertEqual(orientation_enclosure(chain)['status'],'NOT_APPLICABLE')
        chain=self.fixture();chain.mount['quaternion_xyzw']=axis_quaternion([1,0,0],.01)
        self.assertEqual(orientation_enclosure(chain)['status'],'NOT_APPLICABLE')


if __name__=='__main__':unittest.main()
