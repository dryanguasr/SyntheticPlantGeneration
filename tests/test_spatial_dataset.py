import unittest
import tempfile,json
import random
from pathlib import Path
from unittest.mock import patch
from uchuva_lsystem.spatial_dataset import depth_stratum,admitted_pool,committed_views,select_scene_plants


class DatasetPhaseTests(unittest.TestCase):
    def test_three_depths_are_balanced_and_repeatable(self):
        self.assertEqual([depth_stratum(i) for i in range(6)],['near','middle','far']*2)
    def test_insufficient_or_duplicate_plants_never_start_dataset(self):
        rows=[dict(status='admitted',seed=1,anatomy_sha256='one',folder='unused')]*20
        with patch('uchuva_lsystem.spatial_dataset.read',side_effect=AssertionError('No audit reads expected')):
            self.assertEqual(admitted_pool('.',rows),[])
    def test_raw_inventory_cannot_count_as_admission(self):
        self.assertEqual(admitted_pool('.',[dict(status='inventory',seed=i) for i in range(30)]),[])
    def test_palette_capacity_includes_flowers_without_thinning_trees(self):
        pool=[dict(seed=i,counts=dict(calyces=300,flowers=50 if i<6 else 20)) for i in range(20)]
        selected=select_scene_plants(pool,12,random.Random(12))
        self.assertEqual(len(selected),12)
        self.assertTrue(all(p in pool for p in selected))
        self.assertLessEqual(sum(p['counts']['calyces']+p['counts']['flowers'] for p in selected),4095)
        with self.assertRaises(ValueError):select_scene_plants(pool,12,random.Random(12),capacity=100)
    def test_discarded_views_are_preserved_but_never_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);view=root/'views'/'old';view.mkdir(parents=True)
            (view/'view.json').write_text(json.dumps(dict(status='complete',view_id='old')))
            (root/'excluded_views.json').write_text(json.dumps(dict(view_ids=['old'])))
            self.assertEqual(committed_views(root),[])
            self.assertTrue((view/'view.json').exists())


if __name__=='__main__':unittest.main()
