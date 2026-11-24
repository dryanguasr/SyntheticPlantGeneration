"""Regression checks for exact-mask metrics and the development seal."""

import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uchuva_annotation_audit.masks import decode_mask, encode_mask
from uchuva_annotation_audit.private_evaluation import (
    evaluate_images, intersection_pixels, interval_prefix, native_prediction_rle,
    prepare_image, union_intervals,
)
from uchuva_annotation_audit.store import atomic_json, read, sha

spec = importlib.util.spec_from_file_location('evaluate_private_mask_ladder', ROOT / 'scripts/evaluate_private_mask_ladder.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def mask_at(left, top=1, size=12):
    mask = np.zeros((size, size), dtype=np.uint8)
    mask[top:top + 3, left:left + 3] = 255
    return encode_mask(Image.fromarray(mask))


def obj(label, rle, score=None):
    result = dict(id=f'target-{label}', class_id=label, segmentation=rle)
    if score is not None:
        result['score'] = score
    return result


class EvaluationTests(unittest.TestCase):
    def test_native_projection_keeps_fragment_and_hole(self):
        width, height = 17, 9
        model_mask = np.zeros((8, 8), np.uint8)
        # The top and bottom rows are outside the centered 8 x 4 content.
        model_mask[0] = 1
        model_mask[2:6, 0:4] = 1
        model_mask[3:5, 1:3] = 0
        model_mask[4, 6] = 1
        expected = cv2.resize(model_mask[2:6], (width, height), interpolation=cv2.INTER_NEAREST)
        actual = decode_mask(native_prediction_rle(model_mask, width, height))
        np.testing.assert_array_equal(np.asarray(actual) > 0, expected > 0)
        self.assertIsNone(native_prediction_rle(np.zeros_like(model_mask), width, height))

    def test_intervals_count_unique_ignore_coverage(self):
        regions = union_intervals([(0, 4), (3, 6), (8, 10), (10, 13)])
        other = np.array([(1, 2), (4, 9), (10, 16)])
        np.testing.assert_array_equal(regions, [(0, 6), (8, 13)])
        self.assertEqual(intersection_pixels(regions, interval_prefix(regions), other), 7)

    def test_class_confusion_and_ignore_behave_independently(self):
        row = dict(id='I01', group_id='G1', width=12, height=12)
        # The last ignore also covers the resolved Sobremadura. A real error
        # touching that target must still appear in the confusion matrix.
        reference = dict(objects=[obj(0, mask_at(0)), obj(2, mask_at(4)), obj(None, mask_at(8))],
                         ignore_regions=[mask_at(4)])
        predictions = [obj(2, mask_at(8), .98), obj(0, mask_at(0), .91), obj(1, mask_at(4), .73),
                       obj(2, mask_at(1, top=7), .52)]
        image = prepare_image(row, reference, predictions, 960)
        threshold, metrics = evaluate_images([image], threshold=.5)
        self.assertEqual(threshold, .5)
        self.assertAlmostEqual(metrics['class_agnostic']['ap50_95'], 1.)
        self.assertAlmostEqual(metrics['macro_ap50_95'], .5)
        self.assertIsNone(metrics['by_class']['Madura']['ap50_95'])
        self.assertEqual(metrics['operating_point']['matrix'][2][1], 1)
        self.assertEqual([event['kind'] for event in metrics['operating_point']['sobremadura']], ['confusion', 'background_fp'])
        self.assertEqual(metrics['by_group']['G1']['image_count'], 1)

    def test_threshold_from_validation_counts_omission_and_rejects_spurious(self):
        row = dict(id='I01', group_id='G1', width=12, height=12)
        reference = dict(objects=[obj(0, mask_at(0)), obj(1, mask_at(4)), obj(2, mask_at(8))])
        predictions = [obj(0, mask_at(0), .9), obj(1, mask_at(4), .7), obj(2, mask_at(0, top=7), .4)]
        threshold, metrics = evaluate_images([prepare_image(row, reference, predictions, 960)])
        self.assertEqual(threshold, .7)
        self.assertEqual(metrics['operating_point']['sobremadura'][0]['kind'], 'omission')
        self.assertEqual(metrics['operating_point']['matrix'][3][2], 0)

    def test_development_gate_and_weight_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            run = root / 'weights.pt'
            run.write_bytes(b'weights')
            other_run = root / 'other_weights.pt'
            other_run.write_bytes(b'other weights')
            development = root / 'development.json'
            development.write_bytes(b'{"rows":[]}')
            plan = dict(phases=[20], seeds=[1, 2])
            runs = [dict(phase=20, seed=seed, weights=str(path), weights_sha256=sha(path))
                    for seed, path in enumerate((run, other_run), 1)]
            lock = root / 'weights_lock.json'
            atomic_json(lock, dict(development_sha256=sha(development), runs=runs[:1]))
            with self.assertRaisesRegex(ValueError, 'hasta sellar'):
                worker.unlock_development(root, plan, 20, 1, run, sha(run))
            atomic_json(lock, dict(development_sha256=sha(development), runs=runs))
            self.assertEqual(worker.unlock_development(root, plan, 20, 1, run, sha(run)), development)
            development.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'referencia'):
                worker.unlock_development(root, plan, 20, 1, run, sha(run))

    def test_worker_writes_native_prediction_gallery_for_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            phase = root / 'phases/020'
            run = phase / 'run'
            weights = run / 'weights/last.pt'
            weights.parent.mkdir(parents=True)
            weights.write_bytes(b'artificial checkpoint')
            image = root / 'photo.jpg'
            Image.new('RGB', (12, 12), '#776633').save(image)
            annotation = root / 'reference.json'
            rle = mask_at(0)
            atomic_json(annotation, dict(objects=[obj(0, rle)], ignore_regions=[]))
            atomic_json(root / 'plan.json', dict(phases=[20], seeds=[1], steps=4, batch=2, size=12))
            atomic_json(run / 'completion.json', dict(phase=20, seed=1, steps=4, exposures=8, weights_sha256=sha(weights)))
            row = dict(id='I01', group_id='G1', width=12, height=12, image=str(image), annotation=str(annotation),
                       image_sha256=sha(image), annotation_sha256=sha(annotation))
            atomic_json(phase / 'manifest.json', dict(val=[row]))

            def tensor(data):
                return SimpleNamespace(cpu=lambda: SimpleNamespace(numpy=lambda: np.asarray(data)))

            mask = np.asarray(decode_mask(rle))[None] > 0
            fixture = SimpleNamespace(orig_shape=(12, 12), masks=SimpleNamespace(data=tensor(mask)),
                                      boxes=SimpleNamespace(cls=tensor([0]), conf=tensor([.8])))
            fake_library = SimpleNamespace(YOLO=lambda *_, **__: SimpleNamespace(predict=lambda *_, **__: [fixture]))
            output = phase / 'validation.json'
            with patch.dict(sys.modules, {'ultralytics': fake_library}):
                worker.evaluate(SimpleNamespace(root=root, phase=20, seed=1, split='val', run=run, output=output, validation=None))
            report = read(output)
            self.assertEqual(report['operating_threshold'], .8)
            self.assertEqual(report['metrics']['macro_ap50_95'], 1.)
            self.assertEqual(sha(root / report['predictions']['path']), report['predictions']['sha256'])
            self.assertTrue((root / report['examples'][0]['path']).is_file())


if __name__ == '__main__':
    unittest.main()
