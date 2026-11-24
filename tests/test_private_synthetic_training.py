"""The density guard must preserve the historical assignment and mask gradients."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import torch
from ultralytics.cfg import get_cfg
from ultralytics.nn.tasks import SegmentationModel
from ultralytics.utils.loss import E2ELoss
from ultralytics.utils.tal import TaskAlignedAssigner

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import train_private_synthetic_masks as mixed


class PrivateSyntheticTrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(2)

    def test_split_assignment_matches_dense_and_verified_negative(self):
        generator = torch.Generator().manual_seed(921)
        anchors = torch.rand((60, 2), generator=generator) * 60
        scores = torch.rand((2, 60, 3), generator=generator)
        centers = torch.rand((2, 60, 2), generator=generator) * 60
        predicted = torch.cat([centers - 6, centers + 6], dim=-1)
        gt = torch.rand((2, 10, 2), generator=generator) * 48 + 6
        boxes = torch.cat([gt - 5, gt + 5], dim=-1)
        labels = torch.randint(3, (2, 10, 1), generator=generator).float()
        valid = torch.ones((2, 10, 1), dtype=torch.bool)
        cut = 2
        for count in (cut, 0):
            valid[1, count:] = False
            boxes[1, count:] = 0
            labels[1, count:] = 0
            assign = TaskAlignedAssigner(topk=7, num_classes=3, topk2=1)
            inputs = (scores, predicted, anchors, labels, boxes, valid)
            expected = assign(*inputs)
            with patch.object(mixed, "DENSE_TARGETS", cut):
                actual = mixed.assign_without_batch_padding(assign.forward, inputs)
            for result, reference in zip(actual, expected):
                torch.testing.assert_close(result, reference, atol=0, rtol=0)

    def test_dense_path_preserves_end_to_end_components_and_gradients(self):
        torch.manual_seed(733)
        model = SegmentationModel("yolo26n-seg.yaml", nc=3, verbose=False)
        model.args = get_cfg(overrides={"task": "segment", "overlap_mask": False, "epochs": 8})
        model.train()
        images = torch.rand(2, 3, 64, 64)
        masks = torch.zeros(3, 16, 16, dtype=torch.bool)
        masks[0, 3:11, 3:11] = True
        masks[0, 5:7, 5:7] = False
        masks[0, 12, 12] = True
        masks[1, 8:15, 8:15] = True
        masks[2, 5:9, 5:9] = True
        ignored = torch.zeros((2, 16, 16), dtype=torch.bool)
        ignored[0, :6, :6] = True
        batch = {
            "batch_idx": torch.tensor([0, 0, 1]), "cls": torch.tensor([[0.], [1.], [2.]]),
            "bboxes": torch.tensor([[.5, .5, .625, .625], [.71875, .71875, .4375, .4375], [.4375, .4375, .25, .25]]),
            "masks": masks, "ignored": ignored,
        }
        historical = E2ELoss(model, mixed.EmptyTargetSafeSegmentationLoss)
        dense_safe = E2ELoss(model, mixed.DensitySafeLoss)
        pred = model(images)
        expected, _ = historical(pred, batch)
        grads = torch.autograd.grad(expected.sum(), tuple(model.parameters()), retain_graph=True, allow_unused=True)
        with patch.object(mixed, "DENSE_TARGETS", 1):
            actual, _ = dense_safe(pred, batch)
            dense_grads = torch.autograd.grad(actual.sum(), tuple(model.parameters()), allow_unused=True)
        torch.testing.assert_close(actual, expected, atol=0, rtol=0)
        for left, right in zip(dense_grads, grads):
            if left is None:
                self.assertIsNone(right)
            else:
                torch.testing.assert_close(left, right, atol=0, rtol=0)


if __name__ == "__main__":
    unittest.main()
