import unittest
from uchuva_lsystem.nodal_automation import active_elapsed,remaining,stop_reason,physically_admitted,unique_admissions,candidate_seeds

class NodalAutomationContracts(unittest.TestCase):
    def setUp(self):self.budget=dict(awake_started_seconds=100.,limit_active_seconds=18000,target_new_valid_plants=20,excluded_intervals=[])
    def test_exact_time_boundary(self):
        self.assertEqual(remaining(self.budget,18099),1)
        self.assertIsNone(stop_reason(self.budget,19,18099))
        self.assertEqual(stop_reason(self.budget,19,18100),'active_time_limit_reached')
    def test_target_stops_without_an_extra_plant(self):
        self.assertEqual(stop_reason(self.budget,20,200),'target_valid_plants_reached')
    def test_resource_wait_is_excluded_but_not_double_counted(self):
        self.budget['excluded_intervals']=[dict(start=150,end=250)]
        self.assertEqual(active_elapsed(self.budget,300),100)
        self.budget['excluded_intervals'].append(dict(start=200,end=275))
        self.assertEqual(active_elapsed(self.budget,300),75)
    def test_reboot_does_not_silently_reset_budget(self):
        with self.assertRaisesRegex(RuntimeError,'reset'):active_elapsed(self.budget,10)
    def test_proximity_is_not_a_relaxation_of_actual_intersections(self):
        args=[dict(physical_collision_count=0,clearance_violation_count=300),dict(status='valid'),dict(status='valid'),dict(errors=[]),dict(counts=4),dict(counts=4)]
        self.assertTrue(physically_admitted(*args));args[0]['physical_collision_count']=1
        self.assertFalse(physically_admitted(*args))
    def test_ground_orientation_and_anatomy_are_required(self):
        args=[dict(physical_collision_count=0),dict(status='invalid'),dict(status='valid'),dict(errors=[]),dict(counts=4),dict(counts=4)]
        self.assertFalse(physically_admitted(*args));args[1]['status']='valid';args[-1]['counts']=3
        self.assertFalse(physically_admitted(*args))
    def test_clones_and_repeated_seeds_are_not_counted(self):
        rows=[dict(status='admitted',seed=1,anatomy_sha256='a'),dict(status='admitted',seed=2,anatomy_sha256='a'),dict(status='admitted',seed=1,anatomy_sha256='b'),dict(status='admitted',seed=3,anatomy_sha256='c')]
        self.assertEqual([r['seed'] for r in unique_admissions(rows)],[1,3])
    def test_third_candidate_is_first_then_declared_new_seeds(self):
        seeds=candidate_seeds();self.assertEqual([next(seeds) for _ in range(3)],[2026102602,2026102700,2026102701])
    def test_declared_diversity_queue_keeps_seeds_unique_and_retains_fallback(self):
        seeds=candidate_seeds([2026102708,2026102709,2026102708,2026102602])
        self.assertEqual([next(seeds) for _ in range(6)],[2026102602,2026102708,2026102709,2026102700,2026102701,2026102702])

if __name__=='__main__':unittest.main()
