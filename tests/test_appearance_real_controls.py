from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from appearance_campaign import screen_matrix,SEEDS
from complete_appearance_real_controls import control_plan,freeze_evaluation


class RealControlCompletion(unittest.TestCase):
    def test_exact_original_control_budgets_and_three_paired_seeds(self):
        screen,blocks=control_plan(dict(available_doses=[],matrix=screen_matrix([])))
        self.assertEqual(len(screen),2)
        self.assertTrue(all(c['steps']==2000 and c['seed']==SEEDS[0] for c in screen))
        self.assertEqual(len(blocks),2)
        self.assertTrue(all(len(b)==3 and {c['seed'] for c in b}==set(SEEDS) for b in blocks))
        self.assertTrue(blocks[0][0]['classical'])
        self.assertTrue(all(c['steps']==4000 and c['bank']=='real' and c['synthetic_images']==0
                            and not c['repeat_control'] for b in blocks for c in b))
        self.assertEqual(sum(c['steps'] for c in screen+[c for b in blocks for c in b]),28000)

    def test_no_synthetic_or_incomplete_recipe_fallback(self):
        for m in (dict(available_doses=[46],matrix=screen_matrix([46])),
                  dict(available_doses=[],matrix=screen_matrix([])[:1])):
            with self.assertRaises(ValueError):control_plan(m)

    def test_no_development_test_lock_until_all_six_runs_are_complete(self):
        _,blocks=control_plan(dict(available_doses=[],matrix=screen_matrix([])))
        configs=[c for b in blocks for c in b]
        workspace=Path(__file__).resolve().parents[1]/'outputs'
        workspace.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=workspace) as folder:
            self.assertTrue(Path(folder).resolve().is_relative_to(workspace.resolve()))
            with patch('complete_appearance_real_controls.completed',return_value=None):
                with self.assertRaisesRegex(ValueError,'all six complete'):freeze_evaluation(Path(folder),configs)
            self.assertFalse((Path(folder)/'evaluation_lock.json').exists())


if __name__=='__main__':unittest.main()
