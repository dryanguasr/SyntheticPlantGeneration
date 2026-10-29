import copy
import unittest
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.nodal_repulsion import axes,protected_anatomy
from uchuva_lsystem.spatial_admission import (strict_five_percent_budget,make_plan,apply_plan,validate_plan,eligible_organs,solve_cover,KEY)


class SpatialAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=generate_morphology_tree(2026102602,preset_name='trained_trellis_nodal_repulsion_v8',phenology_model='literature_cohort_v1',resolve_growth=False)
    def setUp(self):self.plant=copy.deepcopy(self.source)
    def test_strict_integer_boundary(self):
        self.assertEqual([strict_five_percent_budget(n) for n in [0,1,19,20,21,40,100,408]],[0,0,0,0,1,1,4,20])
        for n in range(1,1000):self.assertLess(strict_five_percent_budget(n)/n,.05)
    def test_separate_budgets_choose_other_kind(self):
        selected,_=solve_cover([['f','l']],dict(f='fruit',l='leaf'),dict(fruit=0,leaf=1))
        self.assertEqual(selected,['l'])
    def test_fixed_contact_and_forced_overflow_reject(self):
        for edges in [[[]],[['a'],['b']]]:
            with self.assertRaises(ValueError):solve_cover(edges,dict(a='leaf',b='leaf'),dict(fruit=0,leaf=1))
    def test_mixed_omissions_restore_all_other_anatomy(self):
        organs=eligible_organs(self.plant);f=next(x for x in organs if x.startswith('fruit:'));l=next(x for x in organs if x.startswith('leaf:'))
        p=make_plan(self.plant,[[f],[l]],evidence_sha256='a'*64);apply_plan(self.plant,p)
        r=validate_plan(self.plant);self.assertEqual(r['losses'],dict(fruit=1,leaf=1));self.assertTrue(r['original_anatomy_recovered'])
        self.assertEqual(validate_plan(Plant.from_dict(self.plant.to_dict())),r)
        with self.assertRaises(ValueError):make_plan(self.plant,[],evidence_sha256='a'*64)
    def test_cumulative_boundary_cannot_reset(self):
        organs=eligible_organs(self.plant);fs=[x for x in organs if x.startswith('fruit:')]
        limit=strict_five_percent_budget(protected_anatomy(self.plant)['counts']['fruits'])
        with self.assertRaises(ValueError):make_plan(self.plant,[[x] for x in fs[:limit+1]],evidence_sha256='a'*64)
    def test_explicit_grammar_path_and_unchanged_default(self):
        organs=eligible_organs(self.plant);f=next(x for x in organs if x.startswith('fruit:'));p=make_plan(self.plant,[[f]],evidence_sha256='a'*64)
        kwargs=dict(params=self.plant.metadata['effective_parameters'],phenology_profile=self.plant.metadata['phenology_profile'],phenology_model='literature_cohort_v1',resolve_growth=False)
        regenerated=generate_morphology_tree(self.plant.seed,**kwargs,spatial_admission_plan=p)
        self.assertEqual(validate_plan(regenerated)['losses']['fruit'],1)
        self.assertEqual(protected_anatomy(generate_morphology_tree(self.plant.seed,**kwargs)),protected_anatomy(self.plant))
    def test_tampered_retained_organ_rejected(self):
        p=make_plan(self.plant,[],evidence_sha256='a'*64);apply_plan(self.plant,p)
        next(n.leaf for a in axes(self.plant.axes) for n in a.nodes if n.leaf).length_cm+=1
        with self.assertRaises(ValueError):validate_plan(self.plant)
    def test_large_leaf_area_is_guarded_even_with_small_count(self):
        leaf=next(n.leaf for a in axes(self.plant.axes) for n in a.nodes if n.leaf)
        leaf.length_cm=1e6;leaf.width_cm=1e6
        with self.assertRaises(ValueError):make_plan(self.plant,[['leaf:'+leaf.id]],evidence_sha256='a'*64)


if __name__=='__main__':unittest.main()
