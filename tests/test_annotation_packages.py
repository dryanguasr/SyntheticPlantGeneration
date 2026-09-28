"""Traceability and annotation-return contracts, with small generated images."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from uchuva_annotation_packages import (CLASSES, diagnose, distribute, generate,
    import_returns, letterbox, partition_audit, sample_bank, validate_geometry, verify, verify_portability)
from uchuva_dataset_curation import digest, read_json, read_rows, write_json, write_rows


class AnnotationPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def fixture(self):
        parent, source = self.root / 'parent', self.root / 'sources'
        (parent / 'candidates').mkdir(parents=True)
        source.mkdir()
        rows, files = [], []
        for i in range(15):
            rgb = np.full((21 + i, 45, 3), (10 + i, 30, 120), dtype=np.uint8)
            ident = f's{i:03}_photo'
            p = source / f'{i}.jpg'
            Image.fromarray(rgb).save(p)
            cache = parent / 'candidates' / f'{ident}.jpg'
            cache.write_bytes(p.read_bytes())
            split = ('train', 'val', 'test')[i % 3]
            r = dict(image_id=ident, source_id=f's{i:03}', source=p.name, kind='photo', source_sha256=digest(p),
                     sha256=digest(cache), candidate_path=f'candidates/{ident}.jpg', pixel_sha256=f'pixels{i}',
                     frame_index=None, timestamp_seconds=None, group_id=f'g{i:03}', group_review='pending', split=split,
                     rotation_cw=270 if i == 3 else 0, selection='exclude' if i == 0 else 'reserve', device='test')
            rows.append(r)
            files.append(dict(source_id=r['source_id'], source=p.name, sha256=digest(p), orientation=1, kind='photo'))
        write_rows(parent / 'manifest.jsonl', rows)
        write_json(parent / 'inventory.json', dict(files=files))
        write_rows(parent / 'pair_review.csv', [dict(left_source='s000', right_source='s000', verdict='same_source')])
        return parent, source, rows

    def test_letterbox_rounding_padding_inverse(self):
        rgb = np.full((103, 271, 3), 7, dtype=np.uint8)
        box, t = letterbox(rgb)
        self.assertTrue(np.all(box[:t['top']] == 114))
        self.assertEqual(box.shape, (640, 640, 3))
        for x, y in [(0, 0), (17.3, 21.9), (271, 103)]:
            self.assertAlmostEqual(((x*t['scale_x']+t['left'])-t['left'])/t['scale_x'], x)
            self.assertAlmostEqual(((y*t['scale_y']+t['top'])-t['top'])/t['scale_y'], y)

    def test_temporal_bank_not_historical_representatives(self):
        rows = [dict(image_id=f'v{n}', source_id='v', source='v.mp4', group_id='g', kind='video',
                     frame_index=n*2, timestamp_seconds=n*.43, selection='reserve') for n in range(100)]
        a = sample_bank(rows, 20, 7)
        self.assertEqual(a, sample_bank(list(reversed(rows)), 20, 7))
        self.assertEqual(len({r['image_id'] for r in a}), 20)
        self.assertIn('v0', {r['image_id'] for r in a})
        self.assertIn('v99', {r['image_id'] for r in a})

    def test_owners_do_not_change_large_group_split(self):
        rows = [dict(image_id=str(i), group_id='same', source='v.mp4', frame_index=i, split='train') for i in range(100)]
        original = copy.deepcopy(rows)
        assigned = distribute(rows)
        self.assertEqual(len(assigned), 100)
        self.assertEqual(len({a[0] for a in assigned.values()}), 5)
        self.assertEqual(rows, original)

    def test_cross_device_relation_and_duplicate_block_release(self):
        rows = [dict(group_id='g1', split='train', group_review='reviewed', source_id='a', source_sha256='x', pixel_sha256='pix'),
                dict(group_id='g2', split='val', group_review='reviewed', source_id='b', source_sha256='x', pixel_sha256='pix')]
        audit = partition_audit(rows, [dict(left_source='a', right_source='b', verdict='pending')])
        self.assertFalse(audit['release_allowed'])
        self.assertEqual({c['kind'] for c in audit['conflicts']}, {'source_sha256', 'pixel_sha256', 'related_sources'})

    def test_diagnose_no_writes(self):
        parent, source, _ = self.fixture()
        before = sorted(str(p) for p in self.root.rglob('*'))
        result = diagnose(parent, source, 15, 9)[0]
        self.assertEqual(result['bank'], 15)
        self.assertEqual(before, sorted(str(p) for p in self.root.rglob('*')))

    def test_small_delivery_zip_calibration_and_exclusion(self):
        parent, source, rows = self.fixture()
        out = self.root / 'delivery'
        result = generate(parent, source, out, 15, 42)
        self.assertTrue(result['ok'])
        self.assertEqual(len(list((out / 'zips').glob('*.zip'))), 5)
        self.assertTrue(verify_portability(out)['ok'])
        manifest = read_rows(out / 'manifest.jsonl')
        self.assertEqual({r['image_id'] for r in manifest}, {r['image_id'] for r in rows})
        self.assertEqual(next(r for r in manifest if r['image_id'] == 's000_photo')['initial_decision'], 'NO USAR')
        for row in manifest:
            self.assertEqual(row['split'], next(r for r in rows if r['image_id'] == row['image_id'])['split'])
        with self.assertRaises(ValueError):
            generate(parent, source, out, 15)
        preview = out / 'paquetes' / manifest[0]['package_id'] / manifest[0]['preview_path']
        preview.write_bytes(b'corruption')
        with self.assertRaises(ValueError):
            verify(out)

    def import_fixture(self):
        campaign = self.root / 'campaign'
        campaign.mkdir()
        row = dict(image_id='image', filename='image.jpg', preview_path='vistas_640/image.png',
                   width=100, height=50, delivered_sha256='originalhash', preview_sha256='previewhash',
                   group_id='g', split='train', group_review='pending', source_id='source', source_sha256='sourcehash',
                   pixel_sha256='pixel', scale_x=6.4, scale_y=6.4, left=0, top=160)
        write_rows(campaign / 'manifest.jsonl', [row])
        write_rows(campaign / 'relations.csv', [])
        incoming = self.root / 'incoming'
        incoming.mkdir()
        item = dict(image_id='image', filename='image.jpg', dimensions=[100, 50], image_sha256='originalhash',
                    representation='original', decision='DUDOSA', annotation_complete=True,
                    instances=[dict(class_id=None, segmentation=[[1, 2, 30, 2, 30, 40]])])
        return campaign, incoming, item

    def test_doubt_unknown_maturity_preserved_and_no_duplicate_sample(self):
        campaign, incoming, item = self.import_fixture()
        for reviewer in ['P01', 'P02']:
            write_json(incoming / f'{reviewer}.json', dict(classes=CLASSES, images=[item]))
        result = import_returns(campaign, incoming, self.root/'result')
        self.assertEqual(result['unique_images'], 1)
        self.assertEqual(result['adjudication_required'], ['image'])
        kept = read_json(self.root/'result/preserved_returns.json')
        self.assertEqual(kept[0]['instances'], item['instances'])
        self.assertTrue(kept[0]['review_pending'])
        self.assertFalse(kept[0]['negative_confirmed'])
        self.assertFalse(result['training_release_allowed'])

    def test_renamed_and_wrong_classes_rejected_raw_preserved(self):
        campaign, incoming, item = self.import_fixture()
        item['filename'] = 'renamed.jpg'
        write_json(incoming/'rename.json', dict(classes=CLASSES, images=[item]))
        write_json(incoming/'mono.json', dict(classes={'0':'capacho'}, images=[item]))
        result = import_returns(campaign, incoming, self.root/'result')
        self.assertEqual(len(result['errors']), 2)
        self.assertEqual(digest(incoming/'mono.json'), digest(self.root/'result/raw/mono.json'))

    def test_selection_csv_and_empty_annotation_never_negative(self):
        campaign, incoming, item = self.import_fixture()
        item.pop('decision')
        item['instances'] = []
        item['split'] = 'test'
        write_rows(incoming/'seleccion.csv', [dict(image_id='image', decision='USAR')])
        write_json(incoming/'return.json', dict(classes=CLASSES, images=[item]))
        import_returns(campaign, incoming, self.root/'result')
        kept = read_json(self.root/'result/preserved_returns.json')[0]
        self.assertEqual(kept['decision'], 'USAR')
        self.assertEqual(kept['split'], 'train')
        self.assertFalse(kept['negative_confirmed'])
        self.assertTrue(kept['review_pending'])

    def test_640_geometry_retains_representation_and_inverse(self):
        campaign, incoming, item = self.import_fixture()
        item.update(filename='image.png', dimensions=[640,640], representation='640', image_sha256='previewhash')
        write_json(incoming/'return.json', dict(classes=CLASSES, images=[item]))
        import_returns(campaign, incoming, self.root/'result')
        kept = read_json(self.root/'result/preserved_returns.json')[0]
        self.assertEqual(kept['geometry_coordinates'], '640')
        self.assertEqual(kept['instances'], item['instances'])
        self.assertEqual(kept['inverse_letterbox']['top'], 160)

    def test_lossless_rle_and_disconnected_geometry(self):
        validate_geometry({'size':[3,4], 'counts':[0,1,2,3,6]}, [4,3])
        validate_geometry([[0,0,1,0,1,1], [2,2,3,2,3,3]], [4,3])
        with self.assertRaises(ValueError):
            validate_geometry({'size':[3,4], 'counts':[13]}, [4,3])
        with self.assertRaises(ValueError):
            validate_geometry([[0,0,float('nan'),0,1,1]], [4,3])

    def test_import_rejects_recursive_output_and_missing_representation(self):
        campaign, incoming, item = self.import_fixture()
        with self.assertRaises(ValueError):
            import_returns(campaign, incoming, incoming/'recursive')
        self.assertFalse((incoming/'recursive').exists())
        item.pop('representation')
        write_json(incoming/'return.json', dict(classes=CLASSES, images=[item]))
        result = import_returns(campaign, incoming, self.root/'result')
        self.assertEqual(len(result['errors']), 1)
        self.assertEqual(result['raw_files_preserved'], 1)


if __name__ == '__main__':
    unittest.main()
