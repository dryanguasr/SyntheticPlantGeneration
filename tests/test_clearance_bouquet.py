"""Axis clearance may change poses, never organ identity or nodal architecture."""
import copy
import unittest
from uchuva_lsystem.bouquet import train_bouquet
from uchuva_lsystem.clearance_bouquet import clear_branch_axes
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.sparse_pilot import prepare_plant,sparse_morphology_parameters,walk_axes


class ClearanceBouquetTests(unittest.TestCase):
    def test_repeatable_pose_change_preserves_all_nodes_and_dimensions(self):
        source=train_bouquet(prepare_plant(generate_morphology_tree(420100,
            sparse_morphology_parameters('individual_dense_crown_v3'))))
        first=copy.deepcopy(source);second=copy.deepcopy(source)
        clear_branch_axes(first);clear_branch_axes(second)
        self.assertEqual(first.to_dict(),second.to_dict())
        for before,after in zip(walk_axes(source.axes),walk_axes(first.axes)):
            self.assertEqual((before.id,before.parent_node_id,before.order),
                             (after.id,after.parent_node_id,after.order))
            self.assertEqual([n.to_dict() for n in before.nodes],[n.to_dict() for n in after.nodes])
            self.assertEqual([n.to_dict() for n in before.internodes],[n.to_dict() for n in after.internodes])


if __name__=='__main__':unittest.main()
