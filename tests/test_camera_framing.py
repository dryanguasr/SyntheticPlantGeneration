import math
import random
import unittest
from uchuva_lsystem.camera_framing import fit_level_camera


class CameraFramingTests(unittest.TestCase):
    def test_exact_perspective_margins_and_filled_dimension(self):
        rng=random.Random(19)
        points=[(rng.uniform(-.6,.6),rng.uniform(-.4,.4),rng.uniform(0,1.3)) for _ in range(200)]
        points += [(-.05,-.18,.07),(.05,.18,.17)]
        for side in (-1,1):
            for azimuth in (-.2,0,.2):
                fit=fit_level_camera(points,side=side,azimuth=azimuth)
                eye=fit['position'];radial=(math.sin(azimuth),side*math.cos(azimuth));right=(-radial[1],radial[0])
                uv=[]
                for point in points:
                    dx,dy,dz=[point[i]-eye[i] for i in range(3)]
                    depth=-(dx*radial[0]+dy*radial[1])
                    uv.append((.5+(dx*right[0]+dy*right[1])/(2*depth*math.tan(math.pi/6)),
                               .5+dz/(2*depth*math.tan(math.pi/6)*720/1280)))
                self.assertGreaterEqual(min(min(v) for v in uv),.07-1e-9)
                self.assertLessEqual(max(max(v) for v in uv),.93+1e-9)
                occupancy=max(max(v[d] for v in uv)-min(v[d] for v in uv) for d in (0,1))
                self.assertAlmostEqual(occupancy,.86,places=7)

    def test_empty_target_rejected(self):
        with self.assertRaises(ValueError):fit_level_camera([])


if __name__=='__main__':unittest.main()
