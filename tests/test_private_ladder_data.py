"""Contracts for the private mask ladder inputs and reference preparation."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from uchuva_annotation_audit.masks import area, mask_iou
from uchuva_annotation_audit.private_ladder_data import _historical_objects, _nested_order, _split_records, prepare


class PrivateLadderDataTests(unittest.TestCase):
    def test_nested_order_is_stable_across_input_order_and_visits_all_groups(self):
        rows = [{'id': f'image{i}', 'group_id': f'group{i % 9}'} for i in range(60)]
        density = {row['id']: i % 10 for i, row in enumerate(rows)}
        ordered = _nested_order(rows, density)
        self.assertEqual(ordered, _nested_order(list(reversed(rows)), density))
        self.assertEqual(len({row['group_id'] for row in ordered[:9]}), 9)
        self.assertEqual(len({row['id'] for row in ordered}), len(rows))
        self.assertTrue(all('density' not in row for row in ordered))

    def test_group_and_exact_duplicate_cannot_cross_splits(self):
        train = {'domain': 'real', 'split': 'train', 'source_row': 2, 'image_sha256': 'image-a', 'group_id': 'group-a'}
        val = {'domain': 'real', 'split': 'val', 'source_row': 3, 'image_sha256': 'image-b', 'group_id': 'group-a'}
        with self.assertRaisesRegex(ValueError, 'Group crosses splits'):
            _split_records([train, val])
        with self.assertRaisesRegex(ValueError, 'Duplicate image hash'):
            _split_records([train, {**val, 'image_sha256': 'image-a', 'group_id': 'group-b'}])

    def test_original_polygon_masks_retain_overlapping_instances(self):
        triangle = [0, .1, .1, .1, .7, .7, .7]
        first, second = _historical_objects([triangle, [2, *triangle[1:]]], 40, 30, 'fixture')
        self.assertEqual((first['class_id'], second['class_id']), (0, 2))
        self.assertEqual(first['bbox'], second['bbox'])
        self.assertEqual(mask_iou(first['segmentation'], second['segmentation']), 1)
        x1, y1, x2, y2 = first['bbox']
        self.assertLess(area(first['segmentation']), (x2 - x1) * (y2 - y1))
        with self.assertRaisesRegex(ValueError, 'unmapped historical class'):
            _historical_objects([[True, *triangle[1:]]], 40, 30, 'fixture')

    def test_preparation_refuses_historical_or_distributable_locations(self):
        for directory in (ROOT, ROOT / 'outputs', ROOT / 'outputs' / 'datasets',
                          ROOT / 'outputs' / 'revision_cruzada_uchuva_20261119',
                          ROOT / 'outputs' / 'revision_cruzada_uchuva_20261119' / 'aplicacion'):
            with self.subTest(directory=directory), self.assertRaises(ValueError):
                prepare(directory)


if __name__ == '__main__':
    unittest.main()
