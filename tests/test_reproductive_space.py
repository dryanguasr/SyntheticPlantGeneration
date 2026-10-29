"""Sparse generation admission must be explicit, bounded and reversible."""
import copy
import unittest

from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.nodal_repulsion import axes, protected_anatomy
from uchuva_lsystem.reproductive_space import (KEY, apply_admission_plan,
    make_admission_plan, validate_admission)
from uchuva_lsystem.validation import validate_morphology_tree


class ReproductiveSpaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = generate_morphology_tree(11,
            preset_name='trained_trellis_nodal_repulsion_v8',
            phenology_model='literature_cohort_v1', resolve_growth=False)

    def setUp(self):
        self.plant = copy.deepcopy(self.original)
        self.ids = sorted(n.reproductive_unit.id for a in axes(self.plant.axes)
                          for n in a.nodes if n.reproductive_unit and n.reproductive_unit.calyx)
        self.edges = [[self.ids[0]], self.ids[1:3], self.ids[3:5]]

    def plan(self):
        return make_admission_plan(self.plant, self.edges, evidence_sha256='a'*64,
                                   max_fruit_fraction=.05)

    def test_minimum_cover_and_order_independent(self):
        p = self.plan()
        other = make_admission_plan(self.plant, list(reversed(self.edges)),
                                    evidence_sha256='a'*64, max_fruit_fraction=.05)
        self.assertEqual(p, other)
        self.assertEqual(len(p['selected_units']), 3)
        self.assertIn(self.ids[0], p['selected_units'])

    def test_shared_contacts_use_two_units_not_one_per_edge(self):
        a, b, c = self.ids[:3]
        p = make_admission_plan(self.plant, [[a,b],[b,c],[a,c]],
                                evidence_sha256='a'*64, max_fruit_fraction=.05)
        self.assertEqual(len(p['selected_units']), 2)

    def test_complete_omissions_and_retained_anatomy_recover(self):
        before = protected_anatomy(self.plant)
        r = apply_admission_plan(self.plant, self.plan())
        self.assertEqual(r['output_anatomy']['counts']['leaves'], before['counts']['leaves'])
        self.assertEqual(r['output_anatomy']['counts']['fruits'], before['counts']['fruits']-3)
        self.assertTrue(validate_admission(self.plant)['original_anatomy_recovered'])
        self.assertFalse(validate_morphology_tree(self.plant, stage='generated')['errors'])

    def test_zero_budget_fails_without_mutation(self):
        before = self.plant.to_dict()
        with self.assertRaises(ValueError):
            make_admission_plan(self.plant, self.edges, evidence_sha256='a'*64,
                                max_fruit_fraction=0.)
        self.assertEqual(before, self.plant.to_dict())

    def test_unknown_unit_or_missing_evidence_rejected(self):
        for edges, evidence in [([['unknown']], 'a'*64), (self.edges, '')]:
            with self.assertRaises(ValueError):
                make_admission_plan(self.plant, edges, evidence_sha256=evidence)

    def test_tampered_plan_rejected_before_mutation(self):
        p = self.plan(); p['selected_units'] = []
        before = self.plant.to_dict()
        with self.assertRaises(ValueError): apply_admission_plan(self.plant, p)
        self.assertEqual(before, self.plant.to_dict())

    def test_serialization_and_retained_leaf_tampering(self):
        apply_admission_plan(self.plant, self.plan())
        restored = Plant.from_dict(self.plant.to_dict())
        self.assertEqual(validate_admission(restored), validate_admission(self.plant))
        next(n.leaf for a in axes(restored.axes) for n in a.nodes if n.leaf).length_cm += .1
        with self.assertRaises(ValueError): validate_admission(restored)
        self.assertTrue(validate_morphology_tree(restored, stage='generated')['errors'])

    def test_omission_snapshot_tampering_rejected(self):
        apply_admission_plan(self.plant, self.plan())
        self.plant.metadata[KEY]['omitted_units'][0]['reproductive_unit']['calyx']['radius_cm'] *= .9
        with self.assertRaises(ValueError): validate_admission(self.plant)

    def test_grammar_explicit_plan_and_default_reproducibility(self):
        p = self.plan()
        kwargs = dict(preset_name='trained_trellis_nodal_repulsion_v8',
                      phenology_model='literature_cohort_v1', resolve_growth=False)
        plain = generate_morphology_tree(11, **kwargs)
        self.assertEqual(plain.to_dict(), self.original.to_dict())
        constrained = generate_morphology_tree(11, **kwargs, reproductive_space_plan=p)
        self.assertTrue(validate_admission(constrained)['original_anatomy_recovered'])
        self.assertEqual(constrained.metadata[KEY]['input_anatomy'], protected_anatomy(plain))


if __name__ == '__main__': unittest.main()
