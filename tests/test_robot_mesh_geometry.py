import hashlib
import math
from pathlib import Path
import tempfile
import unittest
import itertools

from uchuva_gazebo.robot_kinematics import pose_identity, axis_quaternion, transform_point
from uchuva_gazebo.robot_mesh_geometry import (
    MeshRepository, TriangleMesh, _primitive_mesh, repair_collision_obj,
    read_collision_obj, point_triangle_distance, segment_triangle_distance,
    triangle_triangle_distance)


def cube(center=(0,0,0), size=2, reverse=False):
    mesh=_primitive_mesh({'type':'box','size_m':[size]*3})
    vertices=[tuple(p[i]+center[i] for i in range(3)) for p in mesh.vertices]
    return vertices,[tuple(reversed(f)) if reverse else f for f in mesh.faces]


def combine(*parts):
    vertices,faces=[],[]
    for vs,fs in parts:
        faces.extend(tuple(i+len(vertices) for i in f) for f in fs)
        vertices.extend(vs)
    return vertices,faces


def write_obj(path, vertices, faces):
    path.write_text(''.join('v '+' '.join(map(str,p))+'\n' for p in vertices)+
                    'vn 1 0 0\n'+''.join('f '+' '.join(f'{i+1}//1' for i in f)+'\n' for f in faces))
    return {'type':'mesh','uri':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'scale':[1,1,1]}


class MeshGeometryTests(unittest.TestCase):
    def test_disconnected_shell_pruning_preserves_material_and_cavities(self):
        # Analytic union: a hollow cube and a separate solid cube. The long
        # empty span is inside the combined AABB but outside every body.
        mesh=TriangleMesh(*combine(cube(size=4),cube(size=2,reverse=True),cube((10,0,0))))
        for point in itertools.product((-2.1,-1.5,-.5,.5,1.5,2.1,5.,9.5,10.5,11.1), repeat=3):
            hollow=1 < max(map(abs,point)) < 2
            separate=max(abs(point[i]-(10 if i==0 else 0)) for i in range(3)) < 1
            self.assertEqual(mesh.contains(point),hollow or separate,point)

    def test_support_bounds_match_all_transformed_vertices_without_eager_transform(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'part.obj';g=write_obj(path,*combine(cube(),cube((5,1,2),size=.8)))
            repo=MeshRepository(tmp,[g])
            for angle in (0,.3,-1.7,math.pi):
                shape={'geometry':g,'pose':{'xyz_m':[.4,-.5,1.2],'quaternion_xyzw':axis_quaternion([v/math.sqrt(14) for v in (1,2,3)],angle)}}
                posed=repo.prepare(shape);actual=repo.world_bounds(shape)
                self.assertFalse(posed.vertex_cache)
                points=[transform_point(shape['pose'],p) for p in posed.mesh.vertices]
                for axis in range(3):
                    self.assertAlmostEqual(actual[0][axis],min(p[axis] for p in points),places=12)
                    self.assertAlmostEqual(actual[1][axis],max(p[axis] for p in points),places=12)
                    enclosing=repo.conservative_world_bounds(shape)
                    self.assertLessEqual(enclosing[0][axis],actual[0][axis]+1e-12)
                    self.assertGreaterEqual(enclosing[1][axis],actual[1][axis]-1e-12)
    def test_triangle_distance_handles_piercing_and_coplanar_overlap(self):
        tri=((0,0,0),(2,0,0),(0,2,0))
        self.assertEqual(segment_triangle_distance((.5,.5,-1),(.5,.5,1),*tri),0)
        self.assertEqual(segment_triangle_distance((-.2,.5,0),(1,.5,0),*tri),0)
        self.assertAlmostEqual(point_triangle_distance((.5,.5,3),*tri),3)
        self.assertEqual(triangle_triangle_distance(tri,((.1,.1,-1),(.1,.1,1),(.5,.5,1))),0)
        self.assertAlmostEqual(triangle_triangle_distance(tri,tuple((x,y,z+2) for x,y,z in tri)),2)
        # A nonzero native CAD facet must not silently become three edges merely
        # because its absolute area is small (the restored Tapa facet case).
        tiny=((0,0,0),(1e-8,0,0),(0,1e-8,0))
        self.assertAlmostEqual(point_triangle_distance((2e-9,2e-9,1e-8),*tiny),1e-8,places=20)
        self.assertEqual(segment_triangle_distance((2e-9,2e-9,-1e-8),(2e-9,2e-9,1e-8),*tiny),0)

    def test_solid_contains_overlap_and_cavity_without_winding_cancellation(self):
        v,f=combine(cube(),cube((.5,0,0)))
        self.assertTrue(TriangleMesh(v,f).contains((.25,0,0)))
        v,f=combine(cube(),cube((.5,0,0),reverse=True))
        with self.assertRaisesRegex(ValueError,'inside-out'):
            TriangleMesh(v,f)
        v,f=combine(cube(size=4),cube(size=2,reverse=True))
        cavity=TriangleMesh(v,f)
        self.assertFalse(cavity.contains((0,0,0)))
        self.assertTrue(cavity.contains((1.5,0,0)))
        # Nested positive solids are a union, not a subtractive cavity.
        v,f=combine(cube(size=4),cube(size=2))
        self.assertTrue(TriangleMesh(v,f).contains((0,0,0)))
        with self.assertRaisesRegex(ValueError,'inside-out'):
            TriangleMesh(*cube(reverse=True))

    def test_nonmanifold_touching_edge_does_not_hide_an_inside_out_body(self):
        first=_primitive_mesh({'type':'box','size_m':[2,2,4]})
        second=_primitive_mesh({'type':'box','size_m':[1,1,4]})
        shifted=[(p[0]+1.5,p[1]+1.5,p[2]) for p in second.vertices]
        v,f=combine((first.vertices,first.faces),(shifted,[tuple(reversed(face)) for face in second.faces]))
        with self.assertRaisesRegex(ValueError,'inside-out'):
            TriangleMesh(v,f)
        v,f=combine((first.vertices,first.faces),(shifted,second.faces))
        valid=TriangleMesh(v,f)
        self.assertTrue(valid.contains((1.5,1.5,0)))
        self.assertTrue(valid.contains((0,0,0)))

    def test_distances_share_transformed_geometry_and_detect_disconnected_containment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'part.obj'; g=write_obj(path,*combine(cube(),cube((5,0,0))))
            repo=MeshRepository(tmp,[g]); shape={'geometry':g,'pose':pose_identity()}
            sphere={'geometry':{'type':'sphere','radius_m':.1},'pose':{'xyz_m':[5,0,0],'quaternion_xyzw':[0,0,0,1]}}
            self.assertEqual(repo.shape_distance(shape,sphere),0)
            self.assertAlmostEqual(repo.point_distance(shape,(2,0,0)),1)
            self.assertEqual(repo.segment_distance(shape,(2,0,0),(6,0,0)),0)
            other={'geometry':{'type':'box','size_m':[.1]*3},'pose':{'xyz_m':[5,0,0],'quaternion_xyzw':[0,0,0,1]}}
            self.assertEqual(repo.shape_distance(shape,other),0)
            moved={'geometry':g,'pose':{'xyz_m':[0,3,0],'quaternion_xyzw':axis_quaternion([0,0,1],math.pi/2)}}
            lo,hi=repo.world_bounds(moved)
            self.assertAlmostEqual(lo[0],-1);self.assertAlmostEqual(hi[1],9)
            self.assertAlmostEqual(repo.point_distance(moved,(0,0,0)),2)

    def test_cavity_opening_and_mesh_clearance_are_not_the_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'u.obj'
            g=write_obj(path,*combine(cube((-2,0,0)),cube((2,0,0)),cube((0,0,-2))))
            repo=MeshRepository(tmp,[g]); shape={'geometry':g,'pose':pose_identity()}
            self.assertAlmostEqual(repo.point_distance(shape,(0,0,0)),1)
            self.assertAlmostEqual(repo.segment_distance(shape,(0,0,0),(0,0,3)),1)
            ball={'geometry':{'type':'sphere','radius_m':.5},'pose':pose_identity()}
            self.assertAlmostEqual(repo.shape_distance(shape,ball),.5)
            self.assertAlmostEqual(repo.shape_distance(shape,ball,limit=.2),.2)

    def test_hash_normal_winding_and_open_boundary_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'cube.obj';v,f=cube();g=write_obj(path,v,f)
            for bad in ({**g,'sha256':'0'*64},{**g,'uri':'../cube.obj'}):
                with self.assertRaises(ValueError):MeshRepository(tmp,[bad])
            path.write_text(path.read_text().replace('//1',''))
            g['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'normal indices'):MeshRepository(tmp,[g])
            g=write_obj(path,v,f[:-1])
            with self.assertRaisesRegex(ValueError,'closed'):MeshRepository(tmp,[g])
            f[0]=tuple(reversed(f[0]));g=write_obj(path,v,f)
            with self.assertRaisesRegex(ValueError,'closed'):MeshRepository(tmp,[g])
            repaired=Path(tmp)/'fixed.obj';report=repair_collision_obj(path,repaired)
            self.assertEqual(report['flipped_triangles'],1)
            self.assertTrue(report['vertices_unchanged']);self.assertTrue(report['unoriented_triangles_unchanged'])
            fixed={**g,'uri':repaired.name,'sha256':report['collision_sha256']}
            self.assertTrue(MeshRepository(tmp,[fixed])._load(fixed).contains((0,0,0)))
            self.assertEqual(read_collision_obj(path)[0],read_collision_obj(repaired)[0])


if __name__=='__main__':unittest.main()
