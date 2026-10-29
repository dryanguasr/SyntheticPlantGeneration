import unittest
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.sparse_pilot import prepare_plant,sparse_morphology_parameters
from uchuva_lsystem.balanced_basal_pilot import balanced_basal_pilot


class BalancedPilotTests(unittest.TestCase):
    def test_organs_and_parent_connections_preserved(self):
        base=prepare_plant(generate_morphology_tree(814140,sparse_morphology_parameters('individual_dense_crown_v3')))
        original=base.to_dict()
        def walk(axis):
            yield axis
            for child in axis.child_axes:yield from walk(child)
        original_nodes={n.id for a in walk(base.axes[0]) for n in a.nodes}
        for count in (2,3,5):
            plant=balanced_basal_pilot(base,count)
            self.assertEqual(plant.node_count(),base.node_count()+count)
            self.assertEqual(plant.reproductive_unit_count(),base.reproductive_unit_count())
            self.assertEqual(len(plant.axes[0].child_axes),count)
            nodes=[n.id for a in walk(plant.axes[0]) for n in a.nodes]
            self.assertEqual(len(nodes),len(set(nodes)))
            self.assertTrue(original_nodes.issubset(nodes))
            for a in walk(plant.axes[0]):
                for child in a.child_axes:
                    self.assertIn(child.parent_node_id,{n.id for n in a.nodes})
                    self.assertEqual(child.order,a.order+1)
            self.assertEqual(base.to_dict(),original)

if __name__=='__main__':unittest.main()
