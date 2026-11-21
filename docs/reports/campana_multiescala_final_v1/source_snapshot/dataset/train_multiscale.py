"""Gated ten-epoch synthetic multiscale pilot using native raster augmentation.

Adapted from frozen_field_pilot_20261019/train_pilot.py. Never renders, generates
plants, modifies truth, or selects hyperparameters using development test data.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

import psutil
import torch
from ultralytics import YOLO

CAMPAIGN = Path(__file__).resolve().parent
sys.path.insert(0, str(CAMPAIGN))
from native_raster_trainer import CoverageRasterTrainer, RasterValidator
from multiscale_native_augmentation import NativeAugmentationConfig, augmentation_contract


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def preflight(root):
    protocol = read(root / "protocol.json")
    readiness = read(root / "training_readiness.json")
    if readiness.get("passed") is not True:
        raise ValueError("New dataset training_readiness.json has not passed")
    data = root / "patches/dataset"
    files = {
        "protocol_sha256": root / "protocol.json",
        "raster_manifest_sha256": root / "dataset/raster_manifest.json",
        "patch_manifest_sha256": data / "raster_manifest.json",
        "native_augmentation_check_sha256": root / "native_augmentation_integration_check.json",
        "initialization_sha256": Path(protocol["initialization"]),
    }
    for key, path in files.items():
        if readiness.get(key) != sha(path):
            raise ValueError(f"Training gate hash mismatch: {key}")
    for folder in (root / "dataset", data):
        if read(folder / "dataset_contract.json").get("training_eligible") is not True:
            raise ValueError(f"Dataset quality gate has not passed: {folder}")
    native_check = read(files["native_augmentation_check_sha256"])
    if native_check.get("passed") is not True:
        raise ValueError("Native augmentation integration check has not passed")
    for path, expected in native_check["file_hashes"].items():
        if sha(path) != expected:
            raise ValueError(f"Integration-tested code changed: {path}")
    if sha(files["initialization_sha256"]) != protocol["initialization_sha256"]:
        raise ValueError("Frozen initialization mismatch")
    if protocol["primary_patch_size"] != 640 or protocol["training_input_size"] != 960:
        raise ValueError("Expected current 640-native-crop / 960-network plan")
    rows = read(data / "raster_manifest.json")["images"]
    train = [row for row in rows if row["split"] == "train"]
    val = [row for row in rows if row["split"] == "val"]
    if not train or not val or len(train) > protocol["training_patch_cap"]:
        raise ValueError("Invalid train/validation size")
    if any(row["image_size"] != [640, 640] for row in train + val):
        raise ValueError("Unexpected native patch dimensions")
    native = NativeAugmentationConfig(**protocol["native_augmentation"])
    return protocol, data, native, {key: sha(path) for key, path in files.items()}


class MemoryBoundTrainer(CoverageRasterTrainer):
    def get_dataloader(self, dataset_path, batch_size=16, rank=0, mode="train"):
        return super().get_dataloader(dataset_path, 1 if mode == "val" else batch_size, rank, mode)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=CAMPAIGN)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--run-name", default="training")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    protocol, data, native, gate_hashes = preflight(root)
    if args.preflight_only:
        print(json.dumps(dict(passed=True, hashes=gate_hashes, augmentation=augmentation_contract(native))))
        return
    free = psutil.virtual_memory().available / 2**30
    if free < 6.5:
        raise RuntimeError(f"Admission needs 6.5 GiB available, found {free:.2f}")
    torch.set_num_threads(args.threads)
    output = root / "training_runs"
    output.mkdir(exist_ok=True)
    run = output / ("safe_validation" if args.validate_only else args.run_name)
    if run.exists():
        raise FileExistsError(run)
    validation_records = []

    def validation_batch_end(validator):
        torch.cuda.synchronize()
        torch.cuda.empty_cache()
        record = dict(batch=validator.batch_i,
                      free_host_gib=psutil.virtual_memory().available / 2**30,
                      allocated_gib=torch.cuda.memory_allocated() / 2**30,
                      reserved_after_gib=torch.cuda.memory_reserved() / 2**30)
        validation_records.append(record)
        if run.exists():
            with (run / "validation_memory_trace.jsonl").open("a") as stream:
                stream.write(json.dumps(record) + "\n")
        if record["free_host_gib"] < 3:
            raise RuntimeError("Validation below 3 GiB early-stop margin")

    if args.validate_only:
        model = YOLO(output / args.run_name / "weights/last.pt")
        model.add_callback("on_val_batch_end", validation_batch_end)
        result = model.val(validator=RasterValidator, data=str(data / "dataset.yaml"),
                           imgsz=960, batch=1, workers=0, device=0, half=True, plots=False,
                           mask_ratio=2, overlap_mask=False, project=str(output),
                           name="safe_validation", exist_ok=False)
        write(run / "summary.json", dict(batch=1, weights_changed=False,
              min_free_host_gib=min(row["free_host_gib"] for row in validation_records),
              metrics=result.results_dict))
        return

    counts = {"batches": 0, "steps": 0}
    epoch_start = {}
    model = YOLO(protocol["initialization"])
    started_time = time.perf_counter()

    def step(optimizer, a, k):
        counts["steps"] += 1

    def started(trainer):
        trainer.optimizer.register_step_post_hook(step)
        write(run / "startup_audit.json", dict(
            timestamp=datetime.now(timezone.utc).isoformat(), gate_hashes=gate_hashes,
            initialization=protocol["initialization"], augmentation=augmentation_contract(native),
            native_patch_size=640, input_size=960, worker_count=0,
            train_images=len(trainer.train_loader.dataset),
            validation_images=len(trainer.test_loader.dataset)))

    def epoch_begin(trainer):
        epoch_start["steps"] = counts["steps"]
        epoch_start["parameters"] = {
            name: parameter.detach().cpu().clone()
            for name, parameter in trainer.model.named_parameters() if parameter.requires_grad}

    def epoch_end(trainer):
        changes = [float((parameter.detach().cpu().float() - epoch_start["parameters"][name].float()).abs().max())
                   for name, parameter in trainer.model.named_parameters() if name in epoch_start["parameters"]]
        with (run / "parameter_updates.jsonl").open("a") as stream:
            stream.write(json.dumps(dict(epoch=trainer.epoch + 1, steps=counts["steps"],
                         epoch_steps=counts["steps"] - epoch_start["steps"],
                         changed_tensors=sum(value > 0 for value in changes), max_update=max(changes),
                         native_transform_calls=trainer.train_loader.dataset.native_call_counts)) + "\n")
        epoch_start.pop("parameters")
        if counts["steps"] == epoch_start["steps"] or not any(value > 0 for value in changes):
            raise RuntimeError("No real optimizer/parameter update in this epoch")

    def batch_end(trainer):
        counts["batches"] += 1
        torch.cuda.synchronize()
        allocated, reserved = torch.cuda.memory_allocated(), torch.cuda.memory_reserved()
        torch.cuda.empty_cache()
        free = psutil.virtual_memory().available / 2**30
        record = dict(batch=counts["batches"], epoch=trainer.epoch + 1, optimizer_steps=counts["steps"],
                      allocated_gib=allocated / 2**30, reserved_before_gib=reserved / 2**30,
                      reserved_after_gib=torch.cuda.memory_reserved() / 2**30,
                      peak_allocated_gib=torch.cuda.max_memory_allocated() / 2**30, free_host_gib=free)
        with (run / "memory_trace.jsonl").open("a") as stream:
            stream.write(json.dumps(record) + "\n")
        if free < 3:
            raise RuntimeError("Training below 3 GiB early-stop margin")

    model.add_callback("on_val_batch_end", validation_batch_end)
    model.add_callback("on_train_start", started)
    model.add_callback("on_train_epoch_start", epoch_begin)
    model.add_callback("on_train_epoch_end", epoch_end)
    model.add_callback("on_train_batch_end", batch_end)
    result = model.train(
        trainer=MemoryBoundTrainer, data=str(data / "dataset.yaml"),
        epochs=protocol["training_epochs"], imgsz=960, batch=1, nbs=1, warmup_epochs=0,
        device=0, workers=0, amp=True, optimizer="AdamW", lr0=.0002,
        seed=20261002, deterministic=True, patience=0, project=str(output), name=run.name,
        exist_ok=False, plots=False, overlap_mask=False, mask_ratio=2, cache=False,
        close_mosaic=0, save=True, **asdict(native))
    records = [json.loads(line) for line in (run / "memory_trace.jsonl").read_text().splitlines()]
    write(run / "execution_summary.json", dict(
        elapsed_seconds=time.perf_counter() - started_time, threads=args.threads, workers=0,
        batches=counts["batches"], optimizer_steps=counts["steps"],
        min_free_host_gib=min(row["free_host_gib"] for row in records),
        min_validation_free_host_gib=min((row["free_host_gib"] for row in validation_records), default=None),
        max_allocated_gib=max(row["peak_allocated_gib"] for row in records),
        geometry_changed=False, canonical_truth_changed=False,
        native_augmentation=augmentation_contract(native), gate_hashes=gate_hashes,
        scientific_status="pilot training complete; full original-raster evaluation pending"))


if __name__ == "__main__":
    main()
