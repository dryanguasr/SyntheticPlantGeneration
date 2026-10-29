import unittest
from uchuva_lsystem.nodal_constraint_search import solve_ordered_domains


class OrderedConstraintSearch(unittest.TestCase):
    def test_compatible_assignment_and_input_order_preserved(self):
        domains = [[0, 1], [0, 1], [0, 1]]
        result = solve_ordered_domains(domains, lambda a,i,b,j: i==j, expired=lambda:False)
        self.assertEqual(result.status, 'compatible')
        self.assertEqual(result.selected, (0,0,0))
        self.assertEqual(domains, [[0,1],[0,1],[0,1]])

    def test_exhausted_domains_are_distinct_from_timeout(self):
        result = solve_ordered_domains([[0],[0]], lambda *args:False, expired=lambda:False)
        self.assertEqual(result.status, 'discrete_domains_exhausted')
        self.assertIsNone(result.selected)

    def test_wide_forward_filter_is_interruptible_before_recursion(self):
        calls = []
        def compatible(*args):
            calls.append(args)
            return True
        result = solve_ordered_domains([[0],range(1000000)], compatible, expired=lambda:len(calls)>=7)
        self.assertEqual(result.status, 'time_budget_exhausted')
        self.assertIsNone(result.selected)
        self.assertEqual(len(calls), 7)

    def test_expired_search_never_returns_an_unchecked_assignment(self):
        result = solve_ordered_domains([], lambda *args:True, expired=lambda:True)
        self.assertEqual(result.status, 'time_budget_exhausted')
        self.assertIsNone(result.selected)


if __name__ == '__main__':
    unittest.main()
