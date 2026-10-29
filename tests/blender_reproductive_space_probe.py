"""Verify exact geometric comparison tolerates only mesh reindexing."""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'))
from audit_third_candidate_space_review import canonical_mesh_hash
import bmesh


class MeshIdentityTests(unittest.TestCase):
    def test_reindexing_and_polygon_cycle_but_not_move_or_winding(self):
        p=[(0.,0.,0.),(1.,0.,0.),(0.,1.,0.)]
        original=canonical_mesh_hash(p,[(0,1,2)])
        self.assertEqual(original,canonical_mesh_hash([p[2],p[0],p[1]],[(1,2,0)]))
        self.assertEqual(original,canonical_mesh_hash(p,[(1,2,0)]))
        self.assertNotEqual(original,canonical_mesh_hash(p,[(0,2,1)]))
        self.assertNotEqual(original,canonical_mesh_hash([(0.,0.,1e-10),*p[1:]],[(0,1,2)]))

    def test_bmesh_rebuild_exact_points_and_oriented_faces(self):
        hashes=[]
        for _ in range(5):
            bm=bmesh.new();bmesh.ops.create_uvsphere(bm,u_segments=32,v_segments=16,radius=.07)
            bm.verts.ensure_lookup_table();bm.verts.index_update()
            hashes.append(canonical_mesh_hash([tuple(v.co) for v in bm.verts],
                                              [tuple(v.index for v in f.verts) for f in bm.faces]))
            bm.free()
        self.assertEqual(len(set(hashes)),1)


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(MeshIdentityTests)
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():raise RuntimeError('Fixture failed')
