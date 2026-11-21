import unittest
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.sparse_pilot import prepare_plant,sparse_morphology_parameters
from uchuva_lsystem.ascending_basal_pilot import ascending_basal_pilot,VARIANTS


class AscendingBasalTest(unittest.TestCase):
    def test_conservation_connections_and_matched_variants(self):
        base=prepare_plant(generate_morphology_tree(814140,sparse_morphology_parameters('individual_dense_crown_v3')))
        original=base.to_dict()
        def walk(a):
            yield a
            for c in a.child_axes:yield from walk(c)
        for count in range(2,6):
            alternatives=[ascending_basal_pilot(base,count,v) for v in VARIANTS]
            reference=alternatives[0]
            for plant in alternatives:
                self.assertEqual(plant.node_count(),base.node_count()+count)
                self.assertEqual(plant.reproductive_unit_count(),base.reproductive_unit_count())
                axes=list(walk(plant.axes[0]));nodes=[n.id for a in axes for n in a.nodes]
                self.assertEqual(len(nodes),len(set(nodes)))
                for axis in axes:
                    for child in axis.child_axes:
                        self.assertIn(child.parent_node_id,{n.id for n in axis.nodes})
                        self.assertEqual(child.order,axis.order+1)
                lengths=plant.metadata['ascending_basal_pilot']['scaffold_lengths_cm']
                self.assertLess(max(lengths)/min(lengths),1.2)
                self.assertEqual(lengths,reference.metadata['ascending_basal_pilot']['scaffold_lengths_cm'])
                self.assertTrue(all(a.resolved_direction[2]>.65 for a in plant.axes[0].child_axes))
            self.assertEqual(reference.to_dict(),ascending_basal_pilot(base,count,'A_vertical').to_dict())
        self.assertEqual(base.to_dict(),original)


if __name__=='__main__':unittest.main()
