import math
import unittest
from uchuva_lsystem.leaf_surface import broad_leaf_surface
from uchuva_lsystem.morphology import Leaf

class LeafSurfaceTests(unittest.TestCase):
    def edges(self):
        return [(0,0,0),(-2,1,-.02),(3,1,-.02),(-1,3,-.18),(1.5,3,-.18),(0,5,-.5),(0,5,-.5)]
    def test_asymmetric_midrib_root_tip_and_topology(self):
        points,faces=broad_leaf_surface(self.edges(),5,5,.5,.06)
        self.assertEqual(points[0],(0,0,0));self.assertEqual(points[-1],(0,5,-.5))
        for row,y in enumerate((1,3)):
            c=points[1+row*9+4]
            self.assertEqual(c[:2],(0,y));self.assertAlmostEqual(c[2],-.5*(y/5)**2)
        self.assertTrue(all(len(set(f))==len(f) for f in faces))
        self.assertEqual(set(i for f in faces for i in f),set(range(len(points))))
    def test_invalid_control_rejected(self):
        for r in (-.01,.21,float('nan'),float('inf')):
            with self.assertRaises(ValueError):broad_leaf_surface(self.edges(),5,5,.5,r)
    def test_root_fan_and_body_have_consistent_winding(self):
        points,faces=broad_leaf_surface(self.edges(),5,5,.5,.06)
        for face in faces:
            a,b,c=(points[i] for i in face[:3])
            signed_area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            self.assertGreater(signed_area,0)
        # Every shared edge must be traversed in opposite directions.
        edges={}
        for face in faces:
            for a,b in zip(face,face[1:]+face[:1]):
                edges.setdefault(tuple(sorted((a,b))),[]).append((a,b))
        for directions in edges.values():
            if len(directions)==2:
                self.assertEqual(directions[0],directions[1][::-1])
    def test_default_and_serialized_control(self):
        leaf=Leaf('l','n',5,4,1)
        self.assertEqual(leaf.transverse_arch_ratio,0)
        leaf.transverse_arch_ratio=.06
        self.assertEqual(Leaf(**leaf.to_dict()).transverse_arch_ratio,.06)
