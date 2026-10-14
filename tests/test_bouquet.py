"""Training must preserve organs, node attachments, scale and old presets."""
import copy
import math
import unittest

from uchuva_lsystem.bouquet import train_bouquet
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.sparse_pilot import prepare_plant, sparse_morphology_parameters, walk_axes


class BouquetTests(unittest.TestCase):
    def test_determinism_and_organ_conservation(self):
        original = prepare_plant(generate_morphology_tree(23092613,
            sparse_morphology_parameters('individual_dense_crown_v3')))
        result = train_bouquet(copy.deepcopy(original))
        self.assertEqual(result.to_dict(), train_bouquet(copy.deepcopy(original)).to_dict())
        self.assertEqual(result.to_dict(), Plant.from_dict(result.to_dict()).to_dict())
        for before, after in zip(walk_axes(original.axes), walk_axes(result.axes)):
            self.assertEqual(before.id, after.id)
            self.assertEqual(before.parent_node_id, after.parent_node_id)
            self.assertEqual([n.to_dict() for n in before.nodes], [n.to_dict() for n in after.nodes])
            self.assertEqual([i.radius_cm for i in before.internodes], [i.radius_cm for i in after.internodes])
            self.assertAlmostEqual(sum(v*v for v in after.resolved_direction), 1)
            self.assertGreater(after.resolved_direction[2], .5)
        with self.assertRaises(ValueError): train_bouquet(result)
        self.assertEqual(original.parameter_preset, 'individual_dense_crown_v3')

    def test_upper_primary_arms_open_more(self):
        plant = prepare_plant(generate_morphology_tree(23092603,
            sparse_morphology_parameters('individual_dense_crown_v3')))
        train_bouquet(plant)
        root = plant.axes[0]
        positions = {n.id:i for i,n in enumerate(root.nodes)}
        arms = sorted(root.child_axes, key=lambda a:positions[a.parent_node_id])
        angles = [math.acos(a.resolved_direction[2]) for a in arms]
        self.assertEqual(angles, sorted(angles))


if __name__ == '__main__': unittest.main()
