import unittest
from uchuva_lsystem.basal_architecture import basal_scaffolds
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.sparse_pilot import sparse_morphology_parameters, prepare_plant, walk_axes
from uchuva_lsystem.morphology import Plant


class BasalTests(unittest.TestCase):
    def test_conserves_every_organ_and_attachment(self):
        original=prepare_plant(generate_morphology_tree(23092613,sparse_morphology_parameters('individual_dense_crown_v3')))
        before=original.to_dict()
        for count in range(2,min(5,len(original.axes[0].child_axes)+1)+1):
            result=basal_scaffolds(original,count)
            self.assertEqual(original.to_dict(),before)
            self.assertEqual(result.to_dict(),Plant.from_dict(result.to_dict()).to_dict())
            self.assertEqual(original.reproductive_unit_count(),result.reproductive_unit_count())
            old={a.id:a for a in walk_axes(original.axes)}
            new={a.id:a for a in walk_axes(result.axes)}
            self.assertEqual(old.keys(),new.keys())
            for key in old:
                self.assertEqual(old[key].parent_node_id,new[key].parent_node_id)
                def organs(axis):
                    return {n.id:(n.leaf.to_dict() if n.leaf else None,n.reproductive_unit.to_dict() if n.reproductive_unit else None) for n in axis.nodes}
                self.assertEqual(organs(old[key]),organs(new[key]))
            basal=result.axes[0].nodes[:count-1]
            self.assertEqual({a.parent_node_id for a in result.axes[0].child_axes if a.id in result.metadata['basal_architecture']['selected_axes']},{n.id for n in basal})
            self.assertAlmostEqual(sum(s.length_cm for s in result.axes[0].internodes[:count-1])/8,.15)
        with self.assertRaises(ValueError):basal_scaffolds(original,6)


if __name__=='__main__':unittest.main()
