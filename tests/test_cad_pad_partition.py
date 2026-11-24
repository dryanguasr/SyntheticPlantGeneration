"""Exact convex partitions retain concave material boundaries and fail closed."""
from collections import Counter
from fractions import Fraction
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from partition_cad_pad_mesh import star_partition
from uchuva_gazebo.robot_mesh_geometry import TriangleMesh


def star_prism(polygon):
    # Independent fixture: planar cap fans around a visible center, plus walls.
    n=len(polygon);vertices=[(x,y,z) for z in (-1.,1.) for x,y in polygon]
    vertices.extend([(0.,0.,-1.),(0.,0.,1.)]);faces=[]
    for i in range(n):
        j=(i+1)%n
        faces.extend([(2*n,j,i),(2*n+1,n+i,n+j),(i,j,n+j),(i,n+j,n+i)])
    return vertices,faces


class ExactCadPadPartitionTests(unittest.TestCase):
    def test_box_merges_and_exact_volume_is_preserved(self):
        vertices,faces=star_prism([(-1.,-1.),(1.,-1.),(1.,1.),(-1.,1.)])
        cells,report=star_partition(vertices,faces)
        self.assertEqual(report['convex_cells'],1)
        self.assertEqual(Fraction(report['exact_volume_fraction']),8)
        self.assertFalse(report['native_acceptance'])
        self.assertTrue(TriangleMesh(*cells[0]).contains((0,0,0)))

    def test_concave_plus_keeps_empty_corners_and_original_boundary(self):
        polygon=[(-.5,-2),(.5,-2),(.5,-.5),(2,-.5),(2,.5),(.5,.5),(.5,2),
                 (-.5,2),(-.5,.5),(-2,.5),(-2,-.5),(-.5,-.5)]
        vertices,faces=star_prism(polygon);cells,report=star_partition(vertices,faces)
        self.assertEqual(Fraction(report['exact_volume_fraction']),14)
        self.assertGreater(len(cells),1)
        for point in ((1,1,0),(-1,1,0),(1,-1,0),(-1,-1,0)):
            self.assertFalse(any(TriangleMesh(*cell).contains(point) for cell in cells))
        boundary=Counter(tuple(sorted(points[i] for i in face)) for points,triangles in cells for face in triangles)
        source={tuple(sorted(vertices[i] for i in face)) for face in faces}
        self.assertEqual({face for face,count in boundary.items() if count==1},source)
        self.assertTrue(all(count in (1,2) for count in boundary.values()))

    def test_disconnected_solids_are_not_filled_by_a_global_hull(self):
        vertices,faces=star_prism([(-1.,-1.),(1.,-1.),(1.,1.),(-1.,1.)])
        second=[(x+5,y,z) for x,y,z in vertices];offset=len(vertices)
        with self.assertRaisesRegex(ValueError,'One closed material component'):
            star_partition(vertices+second,faces+[tuple(i+offset for i in face) for face in faces])


if __name__=='__main__':unittest.main()
