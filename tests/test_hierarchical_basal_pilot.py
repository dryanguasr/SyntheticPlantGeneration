import unittest
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.sparse_pilot import prepare_plant,sparse_morphology_parameters
from uchuva_lsystem.hierarchical_basal_pilot import hierarchical_basal_pilot
class HierarchyTest(unittest.TestCase):
 def test_connections_taper_and_reproducibility(self):
  base=prepare_plant(generate_morphology_tree(814141,sparse_morphology_parameters('individual_dense_crown_v3')))
  for count in (2,3,4,5):
   p=hierarchical_basal_pilot(base,count)
   self.assertEqual(p.to_dict(),hierarchical_basal_pilot(base,count).to_dict())
   self.assertEqual(len(p.axes[0].child_axes),count)
   ids=set()
   def check(a):
    self.assertNotIn(a.id,ids);ids.add(a.id)
    bynode={n.id:s for n,s in zip(a.nodes,a.internodes)}
    for n in a.nodes:
     if n.leaf:self.assertEqual(n.leaf.node_id,n.id)
     if n.reproductive_unit:self.assertEqual(n.reproductive_unit.node_id,n.id)
    for c in a.child_axes:
     self.assertIn(c.parent_node_id,bynode)
     self.assertEqual(c.order,a.order+1)
     self.assertLess(c.internodes[0].radius_cm,bynode[c.parent_node_id].radius_cm)
     check(c)
    if 1<=a.order<=3:
     self.assertEqual(sum(c.parent_node_id==a.nodes[-1].id for c in a.child_axes),2)
   check(p.axes[0])
if __name__=='__main__':unittest.main()
