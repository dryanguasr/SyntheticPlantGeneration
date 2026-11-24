"""Cover losses and native mask contracts without touching campaign data."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw
import torch
from ultralytics.nn.tasks import SegmentationModel
from ultralytics.cfg import get_cfg
from ultralytics.utils.loss import E2ELoss

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from uchuva_annotation_audit.masks import encode_mask, mask_bbox
from uchuva_annotation_audit.private_training import (
    PrivateDataset, PrivateSegmentationLoss, anchor_negative_exclusions, collate_samples,
    masked_instance_loss, masked_semantic_loss, sampling_order,
)


def obj(canvas, cls):
    mask = encode_mask(canvas)
    return {"id": str(cls), "class_id": cls, "segmentation": mask, "bbox": mask_bbox(mask)}


class PrivateTrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(2)

    def test_nested_dose_sampler_does_not_miss_a_photo(self):
        for count in [20, 40, 80, 160, 320, 461]:
            order = sampling_order(count, 20261022, 8000)
            self.assertEqual(order, sampling_order(count, 20261022, 8000))
            self.assertNotEqual(order, sampling_order(count, 20261023, 8000))
            self.assertEqual(len(order), 8000)
            for start in range(0, len(order) - count + 1, count):
                self.assertEqual(set(order[start:start + count]), set(range(count)))

    def test_native_masks_keep_overlap_fragment_and_hole(self):
        canvas = Image.new("L", (64, 64))
        drawing = ImageDraw.Draw(canvas)
        drawing.rectangle((4, 4, 35, 35), fill=255)
        drawing.rectangle((12, 12, 23, 23), fill=0)
        drawing.rectangle((48, 48, 53, 53), fill=255)
        other = Image.new("L", (64, 64))
        ImageDraw.Draw(other).rectangle((25, 25, 37, 37), fill=255)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            rgb = path / "photo.jpg"
            annotation = path / "masks.json"
            Image.new("RGB", (64, 64)).save(rgb)
            objects = [obj(canvas, 0), obj(other, 2)]
            annotation.write_text(json.dumps({"objects": objects}), encoding="utf-8")
            row = {"id": "demo", "image": rgb, "annotation": annotation, "width": 64, "height": 64}
            dataset = PrivateDataset([row], [0], 20261022, size=64)
            _, masks, classes, _, ignored = dataset.original(0)
            self.assertEqual(classes.tolist(), [0, 2])
            self.assertEqual(masks.shape, (2, 16, 16))
            self.assertTrue(np.any(masks[0] & masks[1]))
            self.assertTrue(masks[0, 12, 12])
            self.assertFalse(masks[0, 4, 4])
            self.assertFalse(ignored.any())
            self.assertEqual(row["annotation"].read_text(encoding="utf-8"), json.dumps({"objects": objects}))

    def test_empty_verified_negative_differs_from_abstention(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            rgb = path / "photo.jpg"
            annotation = path / "masks.json"
            Image.new("RGB", (64, 64)).save(rgb)
            row = {"id": "demo", "image": rgb, "annotation": annotation, "width": 64, "height": 64}
            annotation.write_text('{"objects": []}', encoding="utf-8")
            unknown = PrivateDataset([row], [0], 20261022, size=64)[0]
            self.assertTrue(unknown["ignored"].all())
            self.assertIsNone(collate_samples([unknown]))
            annotation.write_text('{"objects": [], "empty_confirmed": true}', encoding="utf-8")
            known = PrivateDataset([row], [0], 20261022, size=64)[0]
            self.assertFalse(known["ignored"].any())
            result = collate_samples([unknown, known])
            self.assertEqual(tuple(result["img"].shape), (1, 3, 64, 64))
            self.assertEqual(tuple(result["masks"].shape), (0, 16, 16))
            self.assertEqual(tuple(result["batch_idx"].shape), (0,))

    def test_uncertainty_excludes_negatives_and_preserves_positive(self):
        ignored = torch.tensor([[[True, True], [False, False]]])
        foreground = torch.tensor([[True, False, False, False]])
        missing = anchor_negative_exclusions(ignored, [torch.zeros((1, 3, 2, 2))], foreground)
        self.assertEqual(missing.tolist(), [[False, True, False, False]])

        truth = torch.tensor([[[True, False], [False, False]]])
        box = torch.tensor([[0, 0, 2, 2]])
        instance = torch.zeros((1, 2, 2), requires_grad=True)
        value = masked_instance_loss(instance, truth, ignored[0], box)
        value.backward()
        self.assertLess(float(instance.grad[0, 0, 0]), 0)
        self.assertEqual(float(instance.grad[0, 0, 1]), 0)
        self.assertGreater(float(instance.grad[0, 1, 0]), 0)

        semantic = torch.zeros((1, 3, 2, 2), requires_grad=True)
        target = torch.zeros_like(semantic, dtype=torch.bool)
        target[0, 2, 0, 0] = True
        loss = masked_semantic_loss(semantic, target, ignored)
        loss.backward()
        self.assertTrue((semantic.grad[0, :, 0, 1] == 0).all())
        self.assertEqual(float(semantic.grad[0, 0, 0, 0]), 0)
        self.assertLess(float(semantic.grad[0, 2, 0, 0]), 0)

    def test_cpu_native_two_heads_backprop(self):
        model = SegmentationModel("yolo26n-seg.yaml", nc=3, verbose=False)
        model.args = get_cfg(overrides={"overlap_mask": False, "epochs": 8})
        model.train()
        criterion = E2ELoss(model, PrivateSegmentationLoss)
        images = torch.rand((2, 3, 64, 64))
        ignored = torch.zeros((2, 16, 16), dtype=torch.bool)
        ignored[0, 6:9, 6:9] = True
        truth = torch.zeros((1, 16, 16), dtype=torch.bool)
        truth[0, 4:12, 4:12] = True
        batch = dict(ignored=ignored, masks=truth, cls=torch.tensor([[1]]),
                     batch_idx=torch.tensor([0]), bboxes=torch.tensor([[.5, .5, .5, .5]]))
        predictions = model(images)
        for head in ("one2one", "one2many"):
            predictions[head]["scores"].retain_grad()
        components, _ = criterion(predictions, batch)
        self.assertTrue(torch.isfinite(components).all())
        components.sum().backward()
        for head in ("one2one", "one2many"):
            gradients = predictions[head]["scores"].grad
            self.assertIsNotNone(gradients)
            self.assertTrue(torch.isfinite(gradients).all())


if __name__ == "__main__":
    unittest.main()
