"""Regression checks for negative-only training batches in the private mask ladder."""

from pathlib import Path
import sys
import unittest

import torch
from ultralytics.cfg import get_cfg
from ultralytics.nn.tasks import SegmentationModel
from ultralytics.utils.loss import E2ELoss

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "scripts")]

from train_private_mask_ladder import EmptyTargetSafeSegmentationLoss
from uchuva_annotation_audit.private_training import PrivateSegmentationLoss, collate_samples


def ignored_quadrants(height, width):
    ignored = torch.zeros((2, height, width), dtype=torch.bool)
    ignored[0, :height // 2, :width // 2] = True
    ignored[1, height // 2:, width // 2:] = True
    return ignored


class EmptyTargetLossTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        previous_threads = torch.get_num_threads()
        cls.addClassCleanup(torch.set_num_threads, previous_threads)
        torch.set_num_threads(2)
        cls.model = SegmentationModel("yolo26n-seg.yaml", nc=3, verbose=False).cpu().train()
        cls.model.args = get_cfg(overrides={"overlap_mask": False, "epochs": 8})

    def test_known_background_without_targets_masks_both_classification_heads(self):
        samples = [dict(img=torch.rand(3, 64, 64), ignored=ignored, supervised=True,
                        masks=torch.empty((0, 16, 16), dtype=torch.bool),
                        cls=torch.empty((0, 1), dtype=torch.long), bboxes=torch.empty((0, 4)))
                   for ignored in ignored_quadrants(16, 16)]
        batch = collate_samples(samples)
        self.assertIsNotNone(batch)
        self.assertEqual(batch["batch_idx"].numel(), 0)

        predictions = self.model(batch["img"])
        for head in predictions.values():
            head["scores"].retain_grad()
        semantic = predictions["one2many"]["proto"][1]
        semantic.retain_grad()

        criterion = E2ELoss(self.model, EmptyTargetSafeSegmentationLoss)
        components, _ = criterion(predictions, batch)
        self.assertTrue(torch.isfinite(components).all())
        self.assertGreater(float(components[2].detach()), 0)
        torch.testing.assert_close(components[[0, 1, 3]], torch.zeros(3), rtol=0, atol=0)
        components.sum().backward()

        for name, head in predictions.items():
            with self.subTest(head=name):
                scores = head["scores"].grad
                ignored = torch.cat([ignored_quadrants(*feature.shape[-2:]).flatten(1)
                                     for feature in head["feats"]], dim=1)
                self.assert_background_gradient(scores, ignored)
        semantic_ignored = ignored_quadrants(*semantic.shape[-2:]).flatten(1)
        self.assert_background_gradient(semantic.grad.flatten(2), semantic_ignored)

    def assert_background_gradient(self, gradient, ignored):
        self.assertIsNotNone(gradient)
        self.assertTrue(torch.isfinite(gradient).all())
        excluded = ignored[:, None].expand_as(gradient)
        self.assertTrue((gradient[excluded] == 0).all())
        self.assertTrue((gradient[~excluded] > 0).all())

    def test_assignment_with_objects_matches_original_loss(self):
        before = E2ELoss(self.model, PrivateSegmentationLoss)
        after = E2ELoss(self.model, EmptyTargetSafeSegmentationLoss)
        anchors = torch.cartesian_prod(torch.arange(1.0, 5.0), torch.arange(1.0, 5.0))
        target = torch.tensor([[[0.0, 0.0, 6.0, 6.0]]])
        args = (torch.full((1, 16, 3), 0.5), target.expand(-1, 16, -1).contiguous(),
                anchors, torch.ones((1, 1, 1)), target, torch.ones((1, 1, 1), dtype=torch.bool))
        for name in ("one2many", "one2one"):
            with self.subTest(head=name):
                expected = getattr(before, name).assigner(*args)
                actual = getattr(after, name).assigner(*args)
                self.assertEqual(expected[3].dtype, torch.bool)
                self.assertTrue(expected[3].any())
                torch.testing.assert_close(actual, expected, rtol=0, atol=0)


if __name__ == "__main__":
    unittest.main()
