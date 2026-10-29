import unittest
from uchuva_lsystem.scaffold_budget import allocate_scaffold_budget


class ScaffoldBudgetTests(unittest.TestCase):
    def test_conservation_and_no_dominant_axis_over_counts_and_seeds(self):
        for count in range(2,6):
            for seed in range(30):
                plan=allocate_scaffold_budget(709,seed,count)
                self.assertEqual(sum(plan.node_budgets),709)
                self.assertEqual(len(plan.node_budgets),count)
                self.assertLess(max(plan.node_budgets)/min(plan.node_budgets),1.4)
                self.assertEqual(plan,allocate_scaffold_budget(709,seed,count))
                self.assertFalse(plan.geometry_generated)

    def test_count_is_randomized_and_limits_fail(self):
        self.assertEqual({allocate_scaffold_budget(100,s).scaffold_count for s in range(100)},{2,3,4,5})
        for count in (0,1,6,3.5):
            with self.assertRaises(ValueError):allocate_scaffold_budget(100,1,count)

if __name__=='__main__':unittest.main()
