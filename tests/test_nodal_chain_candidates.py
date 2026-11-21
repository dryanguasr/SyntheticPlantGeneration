import math
import unittest
from types import SimpleNamespace
from uchuva_lsystem.nodal_repulsion import KEY, dot, sub, cross
from uchuva_lsystem.nodal_chain_candidates import four_node_candidates, balanced_proposals


class FourNodeCandidates(unittest.TestCase):
    def make_axis(self):
        parts=[SimpleNamespace(id=str(i),length_cm=10+i,radius_cm=.1,
                              provenance={KEY:{'input_direction':(0,0,1)}}) for i in range(4)]
        frames={};z=0.
        for p in parts:
            frames[p.id]={'start':(0,0,z),'end':(0,0,z+p.length_cm*.08)};z+=p.length_cm*.08
        return SimpleNamespace(internodes=parts),frames

    def test_four_lengths_and_growth_ray_preserved(self):
        axis,frames=self.make_axis();rows=four_node_candidates(axis,0,frames,bearing=(1,0,0))
        self.assertTrue(rows)
        for row in rows:
            previous=frames['0']['start']
            for part,point,direction in zip(axis.internodes,row['anchors'],row['directions']):
                self.assertAlmostEqual(math.sqrt(dot(sub(point,previous),sub(point,previous))),part.length_cm*.08)
                self.assertAlmostEqual(dot(direction,direction),1.)
                self.assertLessEqual(math.degrees(math.acos(dot(direction,(0,0,1)))),35)
                previous=point
            self.assertAlmostEqual(math.sqrt(dot(cross(row['end_anchor'],(0,0,1)),cross(row['end_anchor'],(0,0,1)))),0.)
            self.assertGreaterEqual(row['axial_shortening_bu'],-1e-8)

    def test_opposite_inner_offsets_and_no_organ_creation(self):
        axis,frames=self.make_axis();lengths=[p.length_cm for p in axis.internodes]
        row=four_node_candidates(axis,0,frames,bearing=(1,0,0))[0]
        self.assertAlmostEqual(row['anchors'][0][0],-row['anchors'][2][0])
        self.assertAlmostEqual(row['anchors'][1][0],0.)
        self.assertEqual(lengths,[p.length_cm for p in axis.internodes])
        self.assertEqual(len(axis.internodes),4)

    def test_short_chain_has_no_four_bone_proposal(self):
        axis,frames=self.make_axis()
        self.assertEqual(four_node_candidates(axis,1,frames,bearing=(1,0,0)),[])

    def test_search_budget_covers_modes_and_keeps_lowering_first(self):
        families=[[dict(delta_z=sign,degrees=i,mode=str(mode)) for sign in (-1,1) for i in range(1,25)] for mode in range(3)]
        rows=balanced_proposals(families,32)
        self.assertLessEqual(len(rows),32)
        self.assertEqual({r['mode'] for r in rows},{'0','1','2'})
        self.assertEqual([r['delta_z']>0 for r in rows],sorted(r['delta_z']>0 for r in rows))
        self.assertTrue(any(r['degrees']==24 for r in rows))


if __name__=='__main__':unittest.main()
