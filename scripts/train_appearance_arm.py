"""Exact-step YOLO adapter with paired per-slot augmentation and active budget.

Historical training files remain unchanged. Every arm in this campaign uses
this adapter, including the freshly trained real-only controls.
"""
from __future__ import annotations

import argparse
from collections import Counter
import contextlib
from pathlib import Path
import random
import time

import numpy as np
import torch
from torch.utils.data import DataLoader, Sampler
from ultralytics import YOLO, __version__
from ultralytics.models.yolo.detect import DetectionTrainer

from appearance_campaign import (charged_job, check_protocol, learning_rate, read, remaining_budget,
    require, schedule_indices, sha, slot_seed, verify_review, verify_sources, write, process_identity)


class RecordedTransform:
    """Native HSV/flip implementation with independent, auditable slot RNG."""
    def __init__(self, transform, trainer, component):
        self.transform, self.trainer, self.component = transform, trainer, component

    def __repr__(self):
        return f"Paired({self.transform!r}, component={self.component!r})"

    def __call__(self, labels):
        epoch, slot = self.trainer.current_slot
        seed = slot_seed(self.trainer.args.seed, epoch, slot, self.component)
        py_state, np_state = random.getstate(), np.random.get_state()
        record = self.trainer.augmentation.setdefault((epoch, slot), dict(epoch=epoch, slot=slot))
        if self.component == "hsv":
            gains = np.random.RandomState(seed).uniform(-1, 1, 3) * [self.transform.hgain, self.transform.sgain, self.transform.vgain]
            record.update(value_factor=float(1 + gains[2]), hue_delta=float(gains[0]), saturation_delta=float(gains[1]), hsv_seed=seed)
        else:
            record[self.component] = random.Random(seed).random() < self.transform.p
            record[self.component + "_seed"] = seed
        try:
            random.seed(seed)
            np.random.seed(seed)
            return self.transform(labels)
        finally:
            random.setstate(py_state)
            np.random.set_state(np_state)


class SlotDataset:
    def __init__(self, dataset, trainer):
        self.dataset, self.trainer = dataset, trainer

    def __getattr__(self, name):
        return getattr(self.dataset, name)

    def __len__(self):
        return len(self.dataset)

    def __getitem__(self, key):
        index, epoch, slot = key
        self.trainer.current_slot = (epoch, slot)
        seed = slot_seed(self.trainer.args.seed, epoch, slot, "other_disabled_transforms")
        py_state, np_state = random.getstate(), np.random.get_state()
        try:
            random.seed(seed)
            np.random.seed(seed)
            return self.dataset[index]
        finally:
            random.setstate(py_state)
            np.random.set_state(np_state)


class PairedSampler(Sampler):
    def __init__(self, trainer, dataset):
        self.trainer, self.dataset = trainer, dataset

    def __len__(self):
        return 1000

    def __iter__(self):
        t = self.trainer
        indices = schedule_indices(len(self.dataset), t.args.seed, t.epoch)
        planned = [Path(self.dataset.im_files[i]).stem for i in indices]
        if t.control:
            real = [i for i, path in enumerate(self.dataset.im_files) if Path(path).stem.startswith("row_")]
            rng = random.Random(t.args.seed + 900000 + t.epoch)
            indices = [rng.choice(real) if name.startswith("view_") else i for i, name in zip(indices, planned)]
        actual = [Path(self.dataset.im_files[i]).stem for i in indices]
        t.sequences.append(dict(epoch=t.epoch, indices=indices, planned_source_ids=planned, actual_source_ids=actual))
        return iter((index, t.epoch, slot) for slot, index in enumerate(indices))


class AppearanceTrainer(DetectionTrainer):
    campaign_root = None
    target_steps = 2000
    control = False

    def __init__(self, *args, **kwargs):
        self.steps = 0
        self.sequences = []
        self.augmentation = {}
        self.current_slot = None
        self.exposure, self.instance_exposure = Counter(), Counter()
        self.started_wall = time.time()
        self.lr_history = []
        super().__init__(*args, **kwargs)

    def get_dataloader(self, dataset_path, batch_size=16, rank=0, mode="train"):
        if mode != "train":
            return super().get_dataloader(dataset_path, batch_size, rank, mode)
        require(batch_size == 2, "Reject automatic batch changes")
        dataset = self.build_dataset(dataset_path, mode, batch_size)
        manifest = read(Path(self.args.data).parent / "manifest.json")
        require([Path(p).stem for p in dataset.im_files] == manifest["train_source_ids"],
                "Native file order differs from the frozen paired slot order")
        def instrument(compose):
            children = getattr(compose, "transforms", [])
            for index, transform in enumerate(children):
                name = transform.__class__.__name__
                if name == "Albumentations":
                    transform.p = 0
                elif name == "RandomHSV":
                    children[index] = RecordedTransform(transform, self, "hsv")
                elif name == "RandomFlip":
                    children[index] = RecordedTransform(transform, self, "flip_" + transform.direction)
                else:
                    instrument(transform)
        instrument(dataset.transforms)
        wrapped = SlotDataset(dataset, self)
        return DataLoader(wrapped, batch_size=2, sampler=PairedSampler(self, wrapped), num_workers=0,
                          pin_memory=True, collate_fn=dataset.collate_fn)

    def _setup_train(self):
        super()._setup_train()
        self.scaler = torch.amp.GradScaler("cuda", init_scale=1., growth_interval=1000000, enabled=self.amp)
        self.optimizer.register_step_post_hook(lambda *_: setattr(self, "steps", self.steps + 1))
        require(self.accumulate == 1, "Gradient accumulation changed")
        require(self.test_loader.dataset.augment is False, "Evaluation augmentation enabled")
        write(self.save_dir / "augmentation_evidence.json", dict(train=repr(self.train_loader.dataset.transforms),
              val=repr(self.test_loader.dataset.transforms), args=vars(self.args),
              optional_albumentations_disabled=True, evaluation_augmentation=False,
              pairing="Native HSV and flip, seeded independently by epoch and slot; same recipe in every arm"))

    def preprocess_batch(self, batch):
        if remaining_budget(self.campaign_root, "train") <= 0:
            raise TimeoutError("Active training budget exhausted")
        for index, path in enumerate(batch["im_file"]):
            domain = "real" if Path(path).stem.startswith("row_") else "synthetic"
            self.exposure[domain] += 1
            self.instance_exposure[domain] += int((batch["batch_idx"] == index).sum())
        return super().preprocess_batch(batch)

    def optimizer_step(self):
        lr = learning_rate(self.steps, self.target_steps, self.args.lr0)
        for group in self.optimizer.param_groups:
            group["lr"] = lr
        before = self.steps
        super().optimizer_step()
        require(self.steps == before + 1, "AMP skipped an optimizer update; reject run")
        self.lr_history.append(lr)
        if self.steps % 100 == 0:
            write(self.save_dir / "progress.json", dict(steps=self.steps, target=self.target_steps,
                  wall_seconds=time.time() - self.started_wall, exposure=dict(self.exposure),
                  instance_exposure=dict(self.instance_exposure)))

    def validate(self):
        previous = self.best_fitness
        metrics, _ = super().validate()
        require(self.steps % 500 == 0, "Validation is not at a 500-step boundary")
        fitness = metrics["metrics/mAP50-95(B)"]
        self.best_fitness = max(previous if previous is not None else -1, fitness)
        return metrics, fitness


def train(root, config):
    root = Path(root).resolve()
    protocol = check_protocol(root)
    verify_review(root)
    source_lock = verify_sources(root)
    matrix = read(root / "matrix_lock.json")
    expected_arm = next((arm for arm in matrix["matrix"] if arm["arm"] == config["arm"]), None)
    require(expected_arm is not None and all(config.get(k) == v for k, v in expected_arm.items()),
            "Training arm does not match the frozen matrix")
    phase = "screen" if config["steps"] == 2000 else "final"
    expected_name = f"{phase}_{config['arm']}_{config['seed']}"
    if config.get("repeat_control", False):
        require(phase == "final", "Only final winners have repetition controls")
        winner = read(root / f"repetition_selection_c{int(config['classical'])}.json")
        require(winner["selection_used_test"] is False and winner["bank"] == config["bank"]
                and winner["dose"] == config["synthetic_images"], "Repetition does not match validation winner")
        expected_name = "repeat_" + expected_name
    require(config["name"] == expected_name, "Noncanonical run name or phase")
    output = root / "training" / config["name"]
    require(not output.exists(), f"Preserve existing training attempt: {output}")
    manifest_path = Path(config["dataset"]).parent / "manifest.json"
    manifest = read(manifest_path)
    descriptor = read(config["dataset"])
    require(descriptor == dict(path=str(manifest_path.parent.resolve()), train="images/train", val="images/val",
                               test="images/test", names=protocol["names"]), "Dataset descriptor changed")
    for entry in manifest["entries"]:
        for kind in ("image", "label"):
            require(sha(entry[kind]) == entry[kind + "_sha256"], f"Data changed: {entry[kind]}")
    require(config["steps"] in (2000, 4000) and config["seed"] in protocol["seeds"], "Unsupported training budget or seed")
    frozen = dict(config, protocol_sha256=sha(root / "protocol.json"), dataset_sha256=sha(manifest_path),
                  dataset_descriptor_sha256=sha(config["dataset"]),
                  code_sha256=sha(__file__), training_source_lock_sha256=sha(root / "training_source_lock.json"),
                  ultralytics=__version__, torch=torch.__version__)
    write(root / "configs" / (config["name"] + "_frozen.json"), frozen)
    AppearanceTrainer.campaign_root = root
    AppearanceTrainer.target_steps = config["steps"]
    AppearanceTrainer.control = config.get("repeat_control", False)
    torch.set_num_threads(4)
    model = YOLO(protocol["weights"])
    classic = config["classical"]
    started = time.time()
    try:
        model.train(trainer=AppearanceTrainer, data=config["dataset"], epochs=config["steps"] // 500,
            imgsz=960, batch=2, nbs=2, optimizer="AdamW", lr0=.0002, lrf=.01, warmup_epochs=0,
            hsv_h=0, hsv_s=0, hsv_v=.1 if classic else 0, fliplr=.5 if classic else 0, flipud=0,
            mosaic=0, mixup=0, copy_paste=0, degrees=0, perspective=0, shear=0, translate=0, scale=0,
            erasing=0, bgr=0, multi_scale=0, seed=config["seed"], device=0, workers=0, cache=False,
            amp=True, deterministic=True, patience=0, project=str(root / "training"), name=config["name"],
            exist_ok=False, plots=False, close_mosaic=0, save=True, save_period=1, val=True)
        t = model.trainer
        require(t.steps == config["steps"] and sum(t.exposure.values()) == 2 * t.steps, "Incomplete effective updates/exposure")
        require(len(t.augmentation) == 2 * t.steps, "Missing augmentation decisions")
        write(output / "sampling_sequences.json", t.sequences)
        write(output / "augmentation_decisions.json", [t.augmentation[key] for key in sorted(t.augmentation)])
        write(output / "learning_rates.json", t.lr_history)
        write(output / "completion.json", dict(completed=True, steps=t.steps, wall_seconds=time.time() - started,
              exposure=dict(t.exposure), instance_exposure=dict(t.instance_exposure),
              best_sha256=sha(output / "weights/best.pt"), last_sha256=sha(output / "weights/last.pt"),
              best_validation_ap=float(t.best_fitness), config=frozen,
              sequence_sha256=sha(output / "sampling_sequences.json"),
              augmentation_sha256=sha(output / "augmentation_decisions.json"),
              learning_rates_sha256=sha(output / "learning_rates.json")))
    except BaseException as error:
        write(output / "failure.json", dict(error=repr(error), wall_seconds=time.time() - started,
              config=frozen, steps=getattr(getattr(model, "trainer", None), "steps", None)))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--accounting-job", default=None)
    args = parser.parse_args()
    config = read(args.config)
    if args.accounting_job:
        job = read(args.root / "execution_jobs" / (args.accounting_job + ".json"))
        require(job["state"] == "active" and job["phase"] == "train"
                and process_identity(job["identity"]["pid"]) == job["identity"], "Accounting owner is not alive")
        manager = contextlib.nullcontext()
    else:
        manager = charged_job(args.root, "train", config["name"])
    with manager:
        train(args.root, config)


if __name__ == "__main__":
    main()
