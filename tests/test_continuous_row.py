import json
import math
from pathlib import Path
import tempfile
import unittest

from uchuva_gazebo.capture_pairs import select_pairs
from uchuva_gazebo.continuous_row import terminal_arc, orientation_speed_scale, obstacle_distance
from uchuva_lsystem.execution_budget import remaining_seconds


class ContinuousRowTests(unittest.TestCase):
    def test_no_hidden_downsampling_and_missing_pair_reported(self):
        stamps=[str(round(i*1e9/30)) for i in range(300)]
        index={k:{s:f'{k}/{s}.png' for s in stamps} for k in ('rgb','mask')}
        all_pairs,missing=select_pairs(index,None)
        self.assertEqual(len(all_pairs),300)
        self.assertFalse(missing)
        legacy,_=select_pairs(index,5)
        self.assertLess(len(legacy),60)
        del index['mask'][stamps[100]]
        pairs,missing=select_pairs(index,None)
        self.assertEqual(len(pairs),299)
        self.assertEqual(missing,[dict(stamp_ns=int(stamps[100]),missing='mask')])

    def test_turn_always_faces_terminal_plant_and_wrap_is_continuous(self):
        center=[3,0,1]
        points=terminal_arc(center,3,1,'plant_05')
        for p in points:
            delta=[center[d]-p['position'][d] for d in range(2)]
            self.assertAlmostEqual((math.cos(p['yaw'])*delta[0]+math.sin(p['yaw'])*delta[1])/3,1)
        for a,b in zip(points,points[1:]):
            error=math.atan2(math.sin(b['yaw']-a['yaw']),math.cos(b['yaw']-a['yaw']))
            self.assertLessEqual(abs(error),math.radians(5)+1e-10)
        self.assertEqual(orientation_speed_scale(math.radians(21)),0)
        self.assertAlmostEqual(orientation_speed_scale(math.radians(15)),.5)

    def test_corridor_is_not_solid_field_envelope(self):
        boxes=[[[-2,-1,0],[2,1,2]],[[-2,5,0],[2,7,2]]]
        self.assertEqual(obstacle_distance([0,3,1],boxes,[]),1)
        self.assertEqual(obstacle_distance([0,0,1],boxes,[]),0)
        capsule=dict(start_m=[-2,3,1],end_m=[2,3,1],radius_m=.1)
        self.assertEqual(obstacle_distance([0,3,1],boxes,[capsule]),0)

    def test_unlimited_authorization_preserves_accounting(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'effective_budget.json').write_text(json.dumps(dict(limit_seconds=None,historical_execution_seconds=100000)))
            self.assertTrue(math.isinf(remaining_seconds(root)))
            (root/'effective_budget.json').write_text(json.dumps(dict(limit_seconds=None,historical_execution_seconds=100000,hard_deadline_unix=0)))
            self.assertEqual(remaining_seconds(root),0)


if __name__=='__main__':unittest.main()
