"""Train one restartable run from a sealed private mask-ladder phase."""

import argparse
from collections import Counter
from copy import deepcopy
from pathlib import Path
import os
import sys
import tempfile
import time

import cv2
import torch
from ultralytics import __version__ as ultralytics_version
from ultralytics.cfg import get_cfg
from ultralytics.nn.tasks import SegmentationModel, load_checkpoint
from ultralytics.utils.loss import E2ELoss
from ultralytics.utils.torch_utils import ModelEMA, init_seeds

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from uchuva_annotation_audit.private_training import (
    PrivateDataset, PrivateSegmentationLoss, collate_samples, pair_supervision, sampling_order,
)
from uchuva_annotation_audit.prepared_mask_revision import compatible_protocol, load_revision
from uchuva_annotation_audit.store import CLASSES, SessionLock, atomic_json, read, sha


STEPS_PER_EPOCH = 500
BASE_LR = .0002
VERSION = "private-native-mask-training/1"
SUPPORTED_ULTRALYTICS = "8.4.114"


def boolean_empty_assignment(_assigner, arguments, result):
    foreground = result[3]
    if foreground.dtype == torch.bool:
        return result
    if arguments[3].shape[1] != 0:
        raise RuntimeError("Unexpected foreground dtype for a batch containing positive targets")
    return (*result[:3], foreground.bool(), result[4])


class EmptyTargetSafeSegmentationLoss(PrivateSegmentationLoss):
    """Keep the assignment-mask type stable when all supervised pixels are background."""

    def __init__(self, model, tal_topk=10, tal_topk2=None):
        super().__init__(model, tal_topk=tal_topk, tal_topk2=tal_topk2)
        self.assigner.register_forward_hook(boolean_empty_assignment)


def freeze_run(root, phase, seed, output, requested_device, revision=None):
    plan_path = root / "plan.json"
    plan = read(plan_path)
    if phase not in plan["phases"] or seed not in plan["seeds"]:
        raise ValueError("Run is not in the frozen plan")
    if (plan["steps"], plan["size"], plan["batch"]) != (4000, 960, 2):
        raise ValueError("Run does not match the fixed ladder budget")
    if ultralytics_version != SUPPORTED_ULTRALYTICS:
        raise RuntimeError("The private loss adapter expects Ultralytics 8.4.114")
    manifest_path = root / "phases" / f"{phase:03d}" / "manifest.json"
    manifest = read(manifest_path)
    if len(manifest["train"]) != phase or len(manifest["val"]) != 88 or "test" in manifest:
        raise ValueError("Wrong phase cohort or forbidden test split in training input")
    seen_ids = set()
    for row in manifest["train"] + manifest["val"]:
        if row["id"] in seen_ids:
            raise ValueError(f"Duplicate sample ID: {row['id']}")
        seen_ids.add(row["id"])
        for kind in ("image", "annotation"):
            path = Path(row[kind])
            if not path.is_absolute() or not path.is_file():
                raise ValueError(f"Missing sealed {kind}: {row['id']}")
            if kind + "_sha256" in row and sha(path) != row[kind + "_sha256"]:
                raise ValueError(f"Changed sealed {kind}: {row['id']}")
    weight = Path(plan["initial_weights"])
    if not weight.is_absolute():
        weight = root / weight
    weight_sha256 = sha(weight)
    if "initial_weights_sha256" in plan and weight_sha256 != plan["initial_weights_sha256"]:
        raise ValueError("Initial weights differ from the plan")
    raw_device = requested_device if requested_device is not None else plan.get("training_device", "0")
    if str(raw_device).isdigit():
        raw_device = f"cuda:{raw_device}"
    device = torch.device(raw_device)
    if device.type not in ("cuda", "cpu"):
        raise ValueError("Expected a CUDA device or an explicit CPU test device")
    if device.type == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable; cannot silently change the frozen recipe")
        torch.cuda.set_device(device)
    precision = "bf16" if device.type == "cuda" and torch.cuda.is_bf16_supported() else "fp32"
    frozen = {
        "version": VERSION, "plan_sha256": sha(plan_path), "manifest_sha256": sha(manifest_path),
        "initial_weights_sha256": weight_sha256, "phase": phase, "seed": seed,
        "steps": plan["steps"], "batch": plan["batch"], "size": plan["size"],
        "device": str(device), "precision": precision, "ultralytics": ultralytics_version,
        "torch": str(torch.__version__), "opencv": cv2.__version__, "worker_sha256": sha(__file__),
        "adapter_sha256": sha(REPO / "src/uchuva_annotation_audit/private_training.py"),
        "recipe": {
            "geometry": "per-instance any-coverage grid/4; RGB letterbox",
            "augment": "seeded-slot horizontal flip and brightness gain 0.9-1.1",
            "precision": precision, "optimizer": "AdamW", "weight_decay": .0005,
            "learning_rate": "linear from 0.0002 to 0.000002 per optimizer call",
            "ema": True, "virtual_epoch_steps": STEPS_PER_EPOCH,
        },
    }
    lock = output / "protocol_lock.json"
    if lock.exists():
        frozen = compatible_protocol(root, lock, frozen, revision)
    else:
        atomic_json(lock, frozen, exclusive=True)
    return manifest["train"], weight, device, frozen


def atomic_checkpoint(value, path):
    """Commit a complete tensor checkpoint before replacing a prior checkpoint."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".training-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            torch.save(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def make_model(weight, device):
    pretrained, _ = load_checkpoint(weight, device="cpu")
    if not isinstance(pretrained, SegmentationModel) or not pretrained.end2end:
        raise ValueError("Expected YOLO26 end-to-end segmentation weights")
    model = SegmentationModel(deepcopy(pretrained.yaml), nc=3, verbose=False)
    model.names = {index: CLASSES[index] for index in range(3)}
    model.load(pretrained, verbose=False)
    model.args = get_cfg(overrides={"task": "segment", "overlap_mask": False, "epochs": 8})
    model.task = "segment"
    model.to(device).train()
    return model


def learning_rate(step, target):
    return BASE_LR * (1 - .99 * step / (target - 1))


def train(root, phase, seed, output, requested_device=None):
    revision = load_revision(root)
    rows, weight, device, frozen = freeze_run(root, phase, seed, output, requested_device, revision)
    published = output / "completion.json"
    weights = output / "weights" / "last.pt"
    if published.exists():
        record = read(published)
        if (record["steps"] != frozen["steps"] or record["exposures"] != frozen["steps"] * frozen["batch"]
                or record["seed"] != seed or record["phase"] != phase
                or record["manifest_sha256"] != frozen["manifest_sha256"]
                or record["weights_sha256"] != sha(weights)):
            raise RuntimeError("Previously published run no longer matches the frozen contract")
        return
    started = time.monotonic()
    torch.set_num_threads(2)
    cv2.setNumThreads(1)
    init_seeds(seed, deterministic=True)
    target, batch_size = frozen["steps"], frozen["batch"]
    fully_uncertain = {index for index,row in enumerate(rows)
                       if read(row['annotation']).get('full_image_uncertain') is True}
    order = pair_supervision(sampling_order(phase, seed, target * batch_size), fully_uncertain)
    dataset = PrivateDataset(rows, order, seed, frozen["size"])
    cache_receipt = None
    if revision:
        from uchuva_annotation_audit.prepared_mask_cache import PreparedMaskCache

        cache = PreparedMaskCache(root, size=dataset.size, ratio=dataset.ratio)
        cache_receipt = cache.bind(dataset)
        expected = read(root / revision["cache_manifest"])["phase_receipts"][str(phase)]
        if cache_receipt != expected:
            raise ValueError("Prepared model inputs differ from the sealed phase receipt")
    model = make_model(weight, device)
    criterion = E2ELoss(model, EmptyTargetSafeSegmentationLoss)
    ema = ModelEMA(model)
    optimizer = torch.optim.AdamW(model.parameters(), lr=BASE_LR, weight_decay=.0005)
    images = Counter()
    supervised = Counter()
    instances = Counter()
    seconds_completed = 0
    steps = batches_without_supervision = 0
    recovery = output / "checkpoint.pt"
    continued = revision["continued_run"] if revision else None
    if continued and (continued["phase"], continued["seed"]) != (phase, seed):
        continued = None
    if continued and not recovery.is_file():
        raise RuntimeError("Committed checkpoint missing after the prepared-cache transition")
    if recovery.exists():
        checkpoint = torch.load(recovery, map_location="cpu", weights_only=True)
        if checkpoint["frozen"] != frozen or checkpoint["steps"] % STEPS_PER_EPOCH:
            raise RuntimeError("Checkpoint is incompatible with the frozen attempt")
        steps = checkpoint["steps"]
        if continued and (steps < continued["steps"] or (
            steps == continued["steps"] and sha(recovery) != continued["checkpoint_sha256"]
        )):
            raise RuntimeError("Restored checkpoint differs from the sealed cache transition")
        images.update(checkpoint["images"])
        supervised.update(checkpoint["supervised"])
        instances.update(checkpoint["instances"])
        if not 0 < steps <= target or sum(images.values()) != steps * batch_size:
            raise RuntimeError("Checkpoint does not match the exact-step budgets")
        seconds_completed = checkpoint["seconds"]
        batches_without_supervision = checkpoint["batches_without_supervision"]
        model.load_state_dict(checkpoint["model"])
        ema.ema.load_state_dict(checkpoint["ema"])
        ema.updates = steps
        optimizer.load_state_dict(checkpoint["optimizer"])
        for _ in range(steps // STEPS_PER_EPOCH):
            criterion.update()
        torch.set_rng_state(checkpoint["rng_cpu"])
        if device.type == "cuda":
            torch.cuda.set_rng_state(checkpoint["rng_cuda"], device=device)
        del checkpoint

    def after_update(*_):
        nonlocal steps
        steps += 1

    optimizer.register_step_post_hook(after_update)
    while steps < target:
        previous = steps
        samples = [dataset[slot] for slot in range(steps * batch_size, (steps + 1) * batch_size)]
        batch = collate_samples(samples)
        if batch is None:
            raise RuntimeError(f'Unsupervised batch at slot {steps * batch_size}; update budget not advanced')
        optimizer.zero_grad(set_to_none=True)
        batch = {key: value.to(device) for key, value in batch.items()}
        with torch.autocast(device.type, dtype=torch.bfloat16, enabled=frozen["precision"] == "bf16"):
            predictions = model(batch["img"].float() / 255)
            components, _ = criterion(predictions, batch)
            loss = components.sum()
        if not bool(torch.isfinite(loss)):
            raise FloatingPointError(f"Nonfinite loss in optimizer step {previous + 1}")
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 10., error_if_nonfinite=True)
        lr = learning_rate(steps, target)
        for group in optimizer.param_groups:
            group["lr"] = lr
        optimizer.step()
        if steps != previous + 1:
            raise RuntimeError("Optimizer did not perform exactly one step")
        ema.update(model)
        for sample in samples:
            images[sample["image_id"]] += 1
            if sample["supervised"]:
                supervised[sample["image_id"]] += 1
                instances.update(str(value) for value in sample["cls"].flatten().tolist())
        if steps % 100 == 0:
            atomic_json(output / "progress.json", {
                "steps": steps, "target": target, "exposures": sum(images.values()),
                "supervised_exposures": sum(supervised.values()),
                "batches_without_supervision": batches_without_supervision, "lr": lr,
                "elapsed_seconds": seconds_completed + time.monotonic() - started,
            })
            print(f"phase={phase} seed={seed} updates={steps}/{target}", flush=True)
        if steps % STEPS_PER_EPOCH == 0:
            criterion.update()
            atomic_checkpoint({
                "frozen": frozen, "steps": steps, "images": dict(images), "supervised": dict(supervised),
                "instances": dict(instances), "model": model.state_dict(), "ema": ema.ema.state_dict(),
                "optimizer": optimizer.state_dict(), "batches_without_supervision": batches_without_supervision,
                "seconds": seconds_completed + time.monotonic() - started,
                "rng_cpu": torch.get_rng_state(),
                "rng_cuda": torch.cuda.get_rng_state(device) if device.type == "cuda" else None,
            }, recovery)
    optimizer.zero_grad(set_to_none=True)
    if len(images) != phase or sum(images.values()) != target * batch_size:
        raise RuntimeError("Image coverage or optimizer exposure budget did not close")
    # The inference file contains a native Ultralytics SegmentationModel, not
    # this worker or its custom training criterion.
    inference_model = ema.ema.cpu().half().eval()
    inference_model.args = {"imgsz": frozen["size"], "task": "segment", "seed": seed}
    atomic_checkpoint({"model": inference_model, "train_args": inference_model.args}, weights)
    atomic_json(published, {
        "completed": True, "steps": steps, "exposures": sum(images.values()), "phase": phase, "seed": seed,
        "weights_sha256": sha(weights), "plan_sha256": frozen["plan_sha256"],
        "manifest_sha256": frozen["manifest_sha256"], "initial_weights_sha256": frozen["initial_weights_sha256"],
        "image_exposures": dict(images), "supervised_image_exposures": dict(supervised),
        "instance_exposures_by_class": dict(instances), "distinct_images": len(images),
        "distinct_supervised_images": len(supervised), "batches_without_supervision": batches_without_supervision,
        "seconds": seconds_completed + time.monotonic() - started,
        "input_cache_receipt": cache_receipt,
        "input_cache_manifest_sha256": revision["cache_manifest_sha256"] if revision else None,
    }, exclusive=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--phase", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device")
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    if output == root or not output.is_relative_to(root):
        raise ValueError("The run output must remain inside the private campaign")
    lock = SessionLock(output / "worker.lock")
    try:
        train(root, args.phase, args.seed, output, args.device)
    finally:
        lock.close()


if __name__ == "__main__":
    main()
