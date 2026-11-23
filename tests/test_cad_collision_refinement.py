import hashlib
import tempfile
import unittest
from pathlib import Path

from uchuva_gazebo.cad_collision_refinement import conservative_boxes, apply_refinements
from uchuva_gazebo.robot_kinematics import pose_identity
from uchuva_gazebo.robot_spec import resolve_robot_profile


def box_obj(bounds):
    vertices, faces = [], []
    for lower, upper in bounds:
        offset=len(vertices)
        vertices += [(lower[0],lower[1],lower[2]),(upper[0],lower[1],lower[2]),
                     (upper[0],upper[1],lower[2]),(lower[0],upper[1],lower[2]),
                     (lower[0],lower[1],upper[2]),(upper[0],lower[1],upper[2]),
                     (upper[0],upper[1],upper[2]),(lower[0],upper[1],upper[2])]
        for quad in ((0,3,2,1),(4,5,6,7),(0,1,5,4),(3,7,6,2),(0,4,7,3),(1,2,6,5)):
            faces += [(offset+quad[0]+1,offset+quad[i]+1,offset+quad[i+1]+1) for i in (1,2)]
    return ''.join('v '+' '.join(map(str,p))+'\n' for p in vertices)+''.join('f '+' '.join(map(str,p))+'\n' for p in faces)


def covered(point, boxes):
    return any(all(abs(point[i]-b['center_m'][i])<=b['size_m'][i]/2+1e-12 for i in range(3)) for b in boxes)


class CadCollisionRefinementTests(unittest.TestCase):
    def test_open_cavity_and_material_are_distinct_and_source_volume_is_covered(self):
        parts=[([-.03,-.01,0],[-.02,.01,.05]),([.02,-.01,0],[.03,.01,.05]),([-.03,-.01,-.01],[.03,.01,0])]
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'u.obj';path.write_text(box_obj(parts))
            boxes,report=conservative_boxes(path,.002,.0002)
            self.assertFalse(covered([0,0,.03],boxes))
            self.assertTrue(covered([.025,0,.03],boxes))
            for lo,hi in parts:
                for i in range(5):
                    for j in range(5):
                        for k in range(5):
                            p=[lo[n]+(hi[n]-lo[n])*v/4 for n,v in enumerate((i,j,k))]
                            self.assertTrue(covered(p,boxes),p)
            self.assertTrue(report['compression_cell_coverage_exact'])
            self.assertGreater(report['interior_cells'],0)

    def test_triangle_sat_does_not_fill_the_tetrahedron_bounds(self):
        text='v 0 0 0\nv .04 0 0\nv 0 .04 0\nv 0 0 .04\nf 1 3 2\nf 1 2 4\nf 1 4 3\nf 2 3 4\n'
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'tetra.obj';path.write_text(text)
            boxes,_=conservative_boxes(path,.002,0)
            self.assertFalse(covered([.03,.03,.03],boxes))
            self.assertTrue(covered([.005,.005,.005],boxes))
            self.assertTrue(covered([.01,.01,.02],boxes))

    def test_open_mesh_and_changed_source_are_rejected_and_visual_mass_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'part.obj';path.write_text('v 0 0 0\nv .01 0 0\nv 0 .01 0\nf 1 2 3\n')
            with self.assertRaisesRegex(ValueError,'open/odd'):
                conservative_boxes(path,.002,0)
            path.write_text(box_obj([([0,0,0],[.01,.01,.01])]))
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            data=resolve_robot_profile('proxy_v1').to_dict()
            link=data['links'][0]
            original=link['collisions'][0]['name']
            link['visuals'].append({'name':'part','pose':pose_identity(),
                'geometry':{'type':'mesh','uri':'part.obj','sha256':digest,'bound_parameters':{}}})
            config={'refinements':[{'collision_name':original,'visual_name':'part','mesh_sha256':digest,
                                   'cell_m':.002,'chord_tolerance_m':0,'source_document':'synthetic closed cube'}]}
            result,report=apply_refinements(data,temporary,config)
            self.assertEqual(result['links'][0]['visuals'],link['visuals'])
            self.assertEqual(result['links'][0]['inertial'],link['inertial'])
            self.assertEqual(data['links'][0]['collisions'][0]['name'],original)
            self.assertTrue(report['visuals_and_inertias_unchanged'])
            path.write_text(path.read_text()+'# changed\n')
            with self.assertRaisesRegex(ValueError,'path/hash'):
                apply_refinements(data,temporary,config)


if __name__=='__main__':unittest.main()
