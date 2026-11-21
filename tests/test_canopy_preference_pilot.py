import unittest
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.sparse_pilot import prepare_plant,sparse_morphology_parameters
from uchuva_lsystem.canopy_preference_pilot import canopy_preference_pilot,node_positions
class CanopyPreferenceTest(unittest.TestCase):
 def test_determinism_limits_and_leaf_bias(self):
  base=prepare_plant(generate_morphology_tree(814141,sparse_morphology_parameters('individual_dense_crown_v3')))
  for probability,expected in ((0,3),(1,4)):
   p=canopy_preference_pilot(base,probability)
   self.assertEqual(p.to_dict(),canopy_preference_pilot(base,probability).to_dict())
   m=p.metadata['canopy_preference_pilot'];self.assertIn(m['basal_axes'],(3,4,5));self.assertEqual(m['levels'],expected)
   pos,axes=node_positions(p);self.assertTrue(m['trained_axes'])
   for a in axes.values():
    for s in a.internodes:self.assertLessEqual(abs(s.bend_angle_deg),12)
    for n in a.nodes:
     if n.leaf:
      q=n.leaf.provenance;self.assertAlmostEqual(q['retention_probability'],.25+.70*q['exterior_exposure_proxy']**2)
      self.assertEqual(n.leaf.node_id,n.id)
   self.assertGreater(m['leaf_count_removed'],0)
if __name__=='__main__':unittest.main()
