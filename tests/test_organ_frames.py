import math
import unittest
from uchuva_lsystem.organ_frames import orthogonal_leaf_direction


class OrganFrameTest(unittest.TestCase):
    def test_requested_angle_for_tilted_and_singular_axes(self):
        for axis in ((0,0,1),(1,0,0),(.7,.2,.5),(0,0,-1)):
            length=math.sqrt(sum(x*x for x in axis))
            for az in (0,45,90,180,270):
                for angle in (0,35,90,130,180):
                    direction=orthogonal_leaf_direction(axis,az,angle)
                    self.assertAlmostEqual(sum(x*x for x in direction),1)
                    self.assertAlmostEqual(sum(x*y for x,y in zip(axis,direction))/length,math.cos(math.radians(angle)))

    def test_zero_axis_rejected(self):
        with self.assertRaises(ValueError):orthogonal_leaf_direction((0,0,0),0,30)
