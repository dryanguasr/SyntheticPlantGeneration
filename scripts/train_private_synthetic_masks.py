"""Run one sealed, slot-matched private segmentation experiment."""

import argparse
from collections import Counter, OrderedDict
from contextlib import closing
from pathlib import Path
import sys
import time

import cv2
import numpy as np
import torch
from torch.nn import functional as F
from torch.utils.checkpoint import checkpoint
from ultralytics import __version__ as ultralytics_version
from ultralytics.utils.loss import E2ELoss
from ultralytics.utils.torch_utils import ModelEMA, init_seeds

from train_private_mask_ladder import (
    BASE_LR, STEPS_PER_EPOCH, SUPPORTED_ULTRALYTICS, EmptyTargetSafeSegmentationLoss,
    atomic_checkpoint, learning_rate, make_model,
)
from uchuva_annotation_audit.prepared_mask_cache import PreparedMaskCache, digest, input_binding
from uchuva_annotation_audit.private_training import (
    PrivateDataset, collate_samples, masked_instance_loss, masked_semantic_loss,
)
from uchuva_annotation_audit.store import SessionLock, atomic_json, read, sha


REPO = Path(__file__).resolve().parents[1]
VERSION = "private-slot-matched-mask-training/1"
REAL_CACHE = REPO / "outputs/private_mask_ladder_20261121"
DENSE_TARGETS = 256
MAX_CACHE_BYTES = 256 * 1024 ** 2
SOURCES = {"real", "synthetic", "frames"}


def bind_projections(root, dataset):
    """Use sealed historical cache hits and build misses in the new campaign."""
    previous = PreparedMaskCache(REAL_CACHE)
    if previous.root.exists():
        previous.check_protocol()
    current = PreparedMaskCache(root)
    entries = []
    current_rows = []
    bindings = []
    for row in dataset.rows:
        binding = input_binding(row, previous.protocol_key)
        if row["source"] == "real" and previous.describe(binding)[1].exists():
            bindings.append((previous, binding))
        else:
            bindings.append((current, binding))
            if not current.describe(binding)[1].exists():
                if row["source"] == "synthetic":
                    raise ValueError(f"Missing audited synthetic projection: {row['id']}")
                current_rows.append(row)
    if current_rows:
        current.build(PrivateDataset(current_rows, [], seed=0, size=dataset.size, ratio=dataset.ratio))
    if any(cache is current for cache, _ in bindings):
        current.check_protocol()
    entries = [(cache, cache._entry(binding)) for cache, binding in bindings]

    local = OrderedDict()
    bytes_used = 0

    def original(index):
        nonlocal bytes_used
        if index in local:
            local.move_to_end(index)
            return local[index][0]
        cache, entry = entries[index]
        value = cache.load(entry)
        weight = sum(array.nbytes for array in value)
        if weight <= MAX_CACHE_BYTES:
            while local and (len(local) >= 24 or bytes_used + weight > MAX_CACHE_BYTES):
                _, (_, evicted_size) = local.popitem(last=False)
                bytes_used -= evicted_size
            local[index] = value, weight
            bytes_used += weight
        return value

    dataset.original = original
    return digest([(entry.binding, entry.sha256) for _, entry in entries])


def assign_without_batch_padding(assign, arguments):
    """Each image has an independent task-aligned assignment."""
    scores, predicted, anchors, labels, boxes, valid = arguments
    if len(scores) == 1 or boxes.shape[1] <= DENSE_TARGETS:
        return None
    results = []
    for index in range(len(scores)):
        item = slice(index, index + 1)
        # Preserve one padded row in a verified negative. The dense batched
        # path also returns label 0 for those background anchors.
        nonzero = valid[item, :, 0].nonzero()
        width = int(nonzero[-1, 1]) + 1 if len(nonzero) else 1
        results.append(assign(scores[item], predicted[item], anchors, labels[item, :width],
                              boxes[item, :width], valid[item, :width]))
    return tuple(torch.cat(parts) for parts in zip(*results))


def mask_chunk(coefficients, proto, targets, selected, ignored, boxes):
    logits = torch.einsum("in,nhw->ihw", coefficients, proto)
    return masked_instance_loss(logits, targets[selected], ignored, boxes)


class DensitySafeLoss(EmptyTargetSafeSegmentationLoss):
    """Match the private loss while bounding allocations for dense views."""

    def __init__(self, model, tal_topk=10, tal_topk2=None):
        super().__init__(model, tal_topk=tal_topk, tal_topk2=tal_topk2)
        self._assigner_forward = self.assigner.forward
        self.assigner.forward = self._assign

    def _assign(self, *arguments):
        return assign_without_batch_padding(self._assigner_forward, arguments) or self._assigner_forward(*arguments)

    def loss(self, preds, batch):
        indices = batch["batch_idx"]
        if len(indices) <= DENSE_TARGETS or int(torch.bincount(indices).max()) <= DENSE_TARGETS:
            return super().loss(preds, batch)
        foreground, indices, boxes, size, detection = self.get_assigned_targets_and_loss(preds, batch)
        coefficients = preds["mask_coefficient"].permute(0, 2, 1)
        features = preds["proto"]
        proto, semantic = features if isinstance(features, tuple) else (features, None)
        masks, ignored = batch["masks"], batch["ignored"]
        if tuple(proto.shape[-2:]) != tuple(ignored.shape[-2:]):
            proto = F.interpolate(proto, ignored.shape[-2:], mode="bilinear", align_corners=False)
        grid_y, grid_x = ignored.shape[-2:]
        scale = size.new_tensor([grid_x, grid_y, grid_x, grid_y]) / size[[1, 0, 1, 0]]
        instance = proto.float().sum() * 0 + coefficients.float().sum() * 0
        targets = None if semantic is None else torch.zeros(
            (len(foreground), self.nc, grid_y, grid_x), dtype=torch.bool, device=ignored.device
        )
        for index, active in enumerate(foreground):
            local = batch["batch_idx"] == index
            local_masks = masks[local]
            for group in active.nonzero().flatten().split(24):
                if len(group):
                    instance = instance + checkpoint(
                        mask_chunk, coefficients[index, group], proto[index], local_masks, indices[index, group],
                        ignored[index], boxes[index, group] * scale, use_reentrant=False, preserve_rng_state=False,
                    )
            if targets is not None and len(local_masks):
                classes = batch["cls"][local, 0]
                for cls in range(self.nc):
                    targets[index, cls] = (local_masks & (classes == cls)[:, None, None]).any(dim=0)
        instance = instance / foreground.sum().clamp(min=1)
        semantic_loss = masked_semantic_loss(semantic, targets, ignored) if targets is not None else instance * 0
        components = torch.stack([
            detection[0], instance * self.hyp.box, detection[1], detection[2], semantic_loss * self.hyp.box,
        ])
        return components * len(foreground), dict(zip(self.loss_names, components.detach()))


def freeze_inputs(root, arm, seed):
    plan_path, manifest_path = root / "plan.json", root / "manifests" / f"{arm}.json"
    schedule_path = root / "schedules" / f"{arm}_{seed}.json"
    plan, manifest, schedule = read(plan_path), read(manifest_path), read(schedule_path)
    if seed not in plan["seeds"] or (plan["steps"], plan["size"], plan["batch"]) != (4000, 960, 2):
        raise ValueError("Run does not match the sealed step, seed, batch and image-size contract")
    if ultralytics_version != SUPPORTED_ULTRALYTICS or "test" in manifest:
        raise ValueError("Training requires the pinned Ultralytics and a manifest without development data")
    rows = manifest["train"]
    by_id = {row["id"]: index for index, row in enumerate(rows)}
    slots = schedule["slots"]
    if len(by_id) != len(rows) or set(slots) != set(by_id) or len(slots) != 8000:
        raise ValueError("Schedule must cover all sealed IDs in exactly 8,000 exposures")
    expected = Counter()
    fully_uncertain = set()
    counts = {}
    for row in rows:
        if row["source"] not in SOURCES:
            raise ValueError(f"Unexpected source for {row['id']}")
        for key in ("image", "annotation"):
            path = Path(row[key])
            if not path.is_absolute() or not path.is_file() or sha(path) != row[f"{key}_sha256"]:
                raise ValueError(f"Changed sealed {key}: {row['id']}")
        annotation = read(row["annotation"])
        if (annotation.get("id"), annotation.get("image_sha256"), annotation.get("size")) != (
                row["id"], row["image_sha256"], [row["width"], row["height"]]):
            raise ValueError(f"Annotation binding differs from the frozen RGB: {row['id']}")
        objects = annotation["objects"]
        counts[row["id"]] = sum(obj["class_id"] is not None for obj in objects)
        if annotation.get("full_image_uncertain") or (
                not objects and not annotation.get("ignore_regions") and not (
                    annotation.get("verified_empty") is True or annotation.get("empty_confirmed") is True)):
            fully_uncertain.add(row["id"])
    for first, second in zip(slots[::2], slots[1::2]):
        pair = [rows[by_id[ident]]["source"] for ident in (first, second)]
        if "real" not in pair or (first in fully_uncertain and second in fully_uncertain):
            raise ValueError("All batches must retain a real photo and some supervision")
        expected.update(pair)
    weight = Path(plan["initial_weights"])
    if not weight.is_absolute():
        weight = root / weight
    if sha(weight) != plan["initial_weights_sha256"]:
        raise ValueError("Initial weights differ from the sealed plan")
    device_name = str(plan.get("training_device", "0"))
    device = torch.device(f"cuda:{device_name}" if device_name.isdigit() else device_name)
    if device.type != "cuda" or not torch.cuda.is_available():
        raise RuntimeError("The campaign awaits its planned CUDA device")
    torch.cuda.set_device(device)
    frozen = {
        "version": VERSION, "arm": arm, "seed": seed, "steps": 4000, "batch": 2, "size": 960,
        "manifest_sha256": sha(manifest_path), "plan_sha256": sha(plan_path), "schedule_sha256": sha(schedule_path),
        "initial_weights_sha256": sha(weight), "worker_sha256": sha(__file__),
        "historical_worker_sha256": sha(REPO / "scripts/train_private_mask_ladder.py"),
        "adapter_sha256": sha(REPO / "src/uchuva_annotation_audit/private_training.py"),
        "device": str(device), "precision": "bf16" if torch.cuda.is_bf16_supported() else "fp32",
        "ultralytics": ultralytics_version, "torch": str(torch.__version__),
        "expected_exposures_by_source": dict(expected),
    }
    return rows, [by_id[ident] for ident in slots], counts, weight, device, frozen


def make_training(weight, device):
    model = make_model(weight, device)
    criterion = E2ELoss(model, DensitySafeLoss)
    ema = ModelEMA(model)
    optimizer = torch.optim.AdamW(model.parameters(), lr=BASE_LR, weight_decay=.0005)
    return model, criterion, ema, optimizer


def optimize(samples, model, criterion, ema, optimizer, device, frozen, step):
    batch = collate_samples(samples)
    if batch is None:
        raise ValueError(f"Batch without supervision at update {step + 1}")
    optimizer.zero_grad(set_to_none=True)
    batch = {key: value.to(device) for key, value in batch.items()}
    with torch.autocast(device.type, dtype=torch.bfloat16, enabled=frozen["precision"] == "bf16"):
        predictions = model(batch["img"].float() / 255)
        components, _ = criterion(predictions, batch)
        loss = components.sum()
    if not bool(torch.isfinite(loss)):
        raise FloatingPointError(f"Nonfinite loss in optimizer step {step + 1}")
    loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(), 10., error_if_nonfinite=True)
    lr = learning_rate(step, frozen["steps"])
    for group in optimizer.param_groups:
        group["lr"] = lr
    optimizer.step()
    ema.update(model)
    return lr, float(loss.detach())


def preflight(root, rows, counts, weight, device, frozen):
    """Exercise a full optimizer update using the largest real and synthetic targets."""
    receipt_path = root / "preflight.json"
    if receipt_path.exists():
        previous = read(receipt_path)
        if previous["protocol"] != frozen or not previous["passed"]:
            raise ValueError("The preflight receipt belongs to a different sealed run")
        return
    selected = [max((row for row in rows if row["source"] == source), key=lambda row: counts[row["id"]])
                for source in ("real", "synthetic")]
    dataset = PrivateDataset(selected, [0, 1], frozen["seed"], frozen["size"])
    receipt = bind_projections(root, dataset)
    exact = dataset.original(1)
    # Run the historical mask implementation on the most demanding RGB once.
    historical = dataset._prepare(1)
    if not all(np.array_equal(current, previous) for current, previous in zip(exact, historical)):
        raise ValueError("Fast dense projection does not equal the historical model inputs")
    del historical
    samples = [dataset[0], dataset[1]]
    torch.cuda.reset_peak_memory_stats(device)
    training = make_training(weight, device)
    torch.cuda.synchronize(device)
    started = time.monotonic()
    lr, loss = optimize(samples, *training, device, frozen, 0)
    torch.cuda.synchronize(device)
    atomic_json(receipt_path, {
        "passed": True, "protocol": frozen, "updates": 1,
        "images": [{"id": row["id"], "source": row["source"], "instances": counts[row["id"]]} for row in selected],
        "projection_exact": True, "input_cache_receipt": receipt,
        "lr": lr, "loss": loss, "seconds": time.monotonic() - started,
        "peak_allocated_bytes": torch.cuda.max_memory_allocated(device),
        "peak_reserved_bytes": torch.cuda.max_memory_reserved(device),
    }, exclusive=True)


def train(root, rows, order, weight, device, frozen):
    arm, seed, target, batch_size = (frozen[key] for key in ("arm", "seed", "steps", "batch"))
    output = root / "runs" / arm / str(seed)
    published, weights = output / "completion.json", output / "weights/last.pt"
    checkpoint_path = output / "checkpoint.pt"
    cache_fields = ("manifest_sha256", "plan_sha256", "schedule_sha256", "initial_weights_sha256")
    with closing(SessionLock(output / "worker.lock")):
        protocol_path = output / "protocol_lock.json"
        if protocol_path.exists():
            if read(protocol_path) != frozen:
                raise ValueError("Run protocol changed after its first attempt")
        else:
            atomic_json(protocol_path, frozen, exclusive=True)
        if published.exists():
            record = read(published)
            if (record["weights_sha256"] != sha(weights) or record["steps"] != target
                    or record["exposures"] != target * batch_size
                    or any(record[key] != frozen[key] for key in cache_fields)):
                raise ValueError("Published run no longer matches its sealed contract")
            return
        started = time.monotonic()
        dataset = PrivateDataset(rows, order, seed, frozen["size"])
        cache_receipt = bind_projections(root, dataset)
        model, criterion, ema, optimizer = make_training(weight, device)
        images, supervised = Counter(), Counter()
        instances = {source: Counter() for source in SOURCES}
        sources = {row["id"]: row["source"] for row in rows}
        elapsed = steps = 0
        if checkpoint_path.exists():
            saved = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
            steps = saved["steps"]
            if (saved["protocol"] != frozen or saved["cache_receipt"] != cache_receipt
                    or not 0 < steps <= target or steps % STEPS_PER_EPOCH
                    or Counter(saved["images"]) != Counter(rows[index]["id"] for index in order[:steps * batch_size])):
                raise ValueError("Checkpoint differs from the sealed run or its actual exposure prefix")
            images.update(saved["images"])
            supervised.update(saved["supervised"])
            for source, values in saved["instances"].items():
                instances[source].update(values)
            elapsed = saved["seconds"]
            model.load_state_dict(saved["model"])
            ema.ema.load_state_dict(saved["ema"])
            ema.updates = steps
            optimizer.load_state_dict(saved["optimizer"])
            for _ in range(steps // STEPS_PER_EPOCH):
                criterion.update()
            torch.set_rng_state(saved["rng_cpu"])
            torch.cuda.set_rng_state(saved["rng_cuda"], device=device)
            del saved

        def record_update(*_):
            nonlocal steps
            steps += 1

        optimizer.register_step_post_hook(record_update)
        while steps < target:
            previous = steps
            samples = [dataset[slot] for slot in range(steps * batch_size, (steps + 1) * batch_size)]
            lr, loss = optimize(samples, model, criterion, ema, optimizer, device, frozen, steps)
            if steps != previous + 1:
                raise RuntimeError("Optimizer did not perform exactly one update")
            for sample in samples:
                ident = sample["image_id"]
                images[ident] += 1
                if sample["supervised"]:
                    supervised[ident] += 1
                    instances[sources[ident]].update(str(cls) for cls in sample["cls"].flatten().tolist())
            if steps % 100 == 0:
                atomic_json(output / "progress.json", {
                    "arm": arm, "seed": seed, "steps": steps, "target": target, "exposures": sum(images.values()),
                    "lr": lr, "loss": loss, "elapsed_seconds": elapsed + time.monotonic() - started,
                })
                print(f"arm={arm} seed={seed} updates={steps}/{target}", flush=True)
            if steps % STEPS_PER_EPOCH == 0:
                criterion.update()
                atomic_checkpoint({
                    "protocol": frozen, "cache_receipt": cache_receipt, "steps": steps,
                    "images": dict(images), "supervised": dict(supervised),
                    "instances": {source: dict(counts) for source, counts in instances.items()},
                    "model": model.state_dict(), "ema": ema.ema.state_dict(), "optimizer": optimizer.state_dict(),
                    "seconds": elapsed + time.monotonic() - started,
                    "rng_cpu": torch.get_rng_state(), "rng_cuda": torch.cuda.get_rng_state(device),
                }, checkpoint_path)

        if images != Counter(rows[index]["id"] for index in order):
            raise ValueError("Actual exposures differ from the training schedule")
        exposures_by_source = Counter()
        for ident, count in images.items():
            exposures_by_source[sources[ident]] += count
        if dict(exposures_by_source) != frozen["expected_exposures_by_source"]:
            raise ValueError("Actual source exposure differs from the sealed plan")
        model.zero_grad(set_to_none=True)
        inference_model = ema.ema.cpu().half().eval()
        inference_model.args = {"imgsz": frozen["size"], "task": "segment", "seed": seed}
        atomic_checkpoint({"model": inference_model, "train_args": inference_model.args}, weights)
        atomic_json(published, {
            "completed": True, "arm": arm, "seed": seed, "steps": steps, "exposures": sum(images.values()),
            "weights_sha256": sha(weights), "checkpoint_sha256": sha(checkpoint_path),
            **{key: frozen[key] for key in cache_fields},
            "image_exposures": dict(images), "supervised_image_exposures": dict(supervised),
            "exposures_by_source": dict(exposures_by_source),
            "instance_exposures_by_source_and_class": {
                source: {str(cls): instances[source][str(cls)] for cls in range(3)} for source in sorted(SOURCES)
            },
            "elapsed_seconds": elapsed + time.monotonic() - started,
        }, exclusive=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("arm")
    parser.add_argument("seed", type=int)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    if not args.arm.isidentifier():
        parser.error("Arm must be an identifier")
    root = args.root.resolve()
    torch.set_num_threads(2)
    cv2.setNumThreads(1)
    rows, order, counts, weight, device, frozen = freeze_inputs(root, args.arm, args.seed)
    init_seeds(args.seed, deterministic=True)
    if args.preflight:
        with closing(SessionLock(root / "preflight.lock")):
            preflight(root, rows, counts, weight, device, frozen)
    else:
        train(root, rows, order, weight, device, frozen)


if __name__ == "__main__":
    main()
