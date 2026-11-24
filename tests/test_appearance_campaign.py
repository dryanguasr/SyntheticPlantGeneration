"""Meaningful CPU checks for the new campaign, including native box transforms."""
import copy
from collections import Counter
import contextlib
import json
from pathlib import Path
import random
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import appearance_campaign as campaign
import run_appearance_campaign as controller
from run_appearance_campaign import make_config, verify_pair


class AppearanceCampaignTests(unittest.TestCase):
    def test_ledger_read_retries_transient_lock_but_never_skips_budget(self):
        with patch.object(Path, "read_text", side_effect=[PermissionError(13,"busy"), '{"active_seconds":12}']), patch.object(campaign.time,"sleep"):
            self.assertEqual(campaign.read("unused"), {"active_seconds":12})
        with patch.object(Path,"read_text",side_effect=PermissionError(13,"busy")) as read, patch.object(campaign.time,"sleep"):
            with self.assertRaises(PermissionError):
                campaign.read("unused")
            self.assertEqual(read.call_count,20)

    def temp(self):
        return tempfile.TemporaryDirectory(dir=REPO / "outputs")

    def test_matrix_and_selection_are_validation_only_and_complete(self):
        matrix = campaign.screen_matrix()
        self.assertEqual(len(matrix), 26)
        self.assertEqual(len({r["arm"] for r in matrix}), 26)
        scores = [dict(config=dict(row, seed=20261022), best_validation_ap=.2) for row in matrix]
        # Huge test scores cannot influence selection; equal val favors smaller dose, then L.
        for row in scores:
            row["test_ap"] = 100 if row["config"]["synthetic_images"] == 230 else -100
        for classic in (False, True):
            self.assertEqual(campaign.choose_dose(scores, classic), 46)
            finals = [dict(config=dict(bank=bank, classical=classic, seed=seed), best_validation_ap=.2)
                      for bank in ("L", "T", "LT") for seed in campaign.SEEDS]
            self.assertEqual(campaign.choose_variant(finals, classic), "L")
            with self.assertRaisesRegex(ValueError, "Incomplete paired seeds"):
                campaign.choose_variant(finals[:-1], classic)
        main_finals = [make_config(row, seed, 4000) for row in matrix if row["synthetic_images"] in (0, 115) for seed in campaign.SEEDS]
        repeats = [make_config(row, seed, 4000, repeat=True) for row in matrix if row["synthetic_images"] == 115 and row["bank"] == "LT" for seed in campaign.SEEDS]
        self.assertEqual((len(main_finals), len(repeats)), (30, 6))

    def test_sampler_lr_and_budget_steps_match_frozen_numerical_recipe(self):
        from train_augmentation_arm import schedule_indices as historical
        for n in (461, 507, 576, 691):
            for epoch in (0, 1, 7):
                self.assertEqual(campaign.schedule_indices(n, 20261022, epoch), historical(n, 20261022, epoch))
        self.assertEqual(campaign.learning_rate(0, 4000), .0002)
        self.assertAlmostEqual(campaign.learning_rate(3999, 4000), .000002)
        with self.assertRaises(ValueError):
            campaign.learning_rate(4000, 4000)

    def test_optimizer_rejects_extra_and_skipped_updates(self):
        from train_appearance_arm import AppearanceTrainer, DetectionTrainer
        trainer = AppearanceTrainer.__new__(AppearanceTrainer)
        trainer.steps, trainer.target_steps = 0, 2
        trainer.args = SimpleNamespace(lr0=.0002)
        trainer.optimizer = SimpleNamespace(param_groups=[dict(lr=0.)])
        trainer.lr_history = []
        def update(_self):
            trainer.steps += 1
        with patch.object(DetectionTrainer, "optimizer_step", update):
            trainer.optimizer_step()
            trainer.optimizer_step()
            with self.assertRaisesRegex(ValueError, "outside frozen budget"):
                trainer.optimizer_step()
        self.assertEqual(trainer.steps, 2)
        trainer.steps = 0
        with patch.object(DetectionTrainer, "optimizer_step", lambda *_: None):
            with self.assertRaisesRegex(ValueError, "AMP skipped"):
                trainer.optimizer_step()

    def test_native_augmentation_is_slot_paired_and_flips_boxes_correctly(self):
        from ultralytics.data.augment import RandomHSV, RandomFlip
        from ultralytics.utils.instance import Instances
        from train_appearance_arm import RecordedTransform
        trainer = SimpleNamespace(args=SimpleNamespace(seed=20261022), current_slot=(0, 11), augmentation={})
        hsv = RecordedTransform(RandomHSV(0, 0, .1), trainer, "hsv")
        flip = RecordedTransform(RandomFlip(1., "horizontal"), trainer, "flip_horizontal")
        image = np.full((8, 10, 3), [30, 70, 120], dtype=np.uint8)
        labels = dict(img=image.copy(), instances=Instances(np.array([[.2, .3, .1, .2]], dtype=np.float32),
                      segments=np.zeros((0, 0, 2), dtype=np.float32), bbox_format="xywh", normalized=True))
        state_py, state_np = random.getstate(), np.random.get_state()
        first = flip(hsv(copy.deepcopy(labels)))
        first_decisions = copy.deepcopy(trainer.augmentation)
        # Different ambient RNG state and a different number of labels cannot alter the slot decisions.
        random.seed(999)
        np.random.seed(999)
        second = flip(hsv(copy.deepcopy(labels)))
        self.assertEqual(first_decisions, trainer.augmentation)
        np.testing.assert_array_equal(first["img"], second["img"])
        np.testing.assert_allclose(first["instances"].bboxes[0], [.8, .3, .1, .2], atol=1e-7)
        self.assertEqual(first_decisions[(0, 11)]["hue_delta"], 0)
        self.assertEqual(first_decisions[(0, 11)]["saturation_delta"], 0)
        self.assertTrue(.9 <= first_decisions[(0, 11)]["value_factor"] <= 1.1)
        random.setstate(state_py)
        np.random.set_state(state_np)

    def test_native_dataloader_pairs_visual_and_repetition_slots_without_training(self):
        import torch
        from PIL import Image
        from ultralytics.cfg import get_cfg
        from train_appearance_arm import AppearanceTrainer
        with self.temp() as folder:
            root = Path(folder)
            ids = ["row_0001", "row_0002", "view_0000"]
            for index, name in enumerate(ids):
                image = root / "images/train" / (name + ".png")
                label = root / "labels/train" / (name + ".txt")
                image.parent.mkdir(parents=True, exist_ok=True)
                label.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (96, 64), (30 + 40*index, 80, 120)).save(image)
                label.write_text(f"{index} 0.2 0.3 0.1 0.2\n")
            campaign.write(root / "manifest.json", dict(train_source_ids=ids))
            campaign.write(root / "dataset.yaml", {})
            def make_trainer(repeat):
                trainer = AppearanceTrainer.__new__(AppearanceTrainer)
                trainer.args = get_cfg(overrides=dict(data=str(root / "dataset.yaml"), imgsz=96, batch=2,
                    workers=0, cache=False, seed=20261022, hsv_h=0., hsv_s=0., hsv_v=.1, fliplr=.5,
                    flipud=0., mosaic=0., mixup=0., copy_paste=0., degrees=0., perspective=0.,
                    shear=0., translate=0., scale=0., erasing=0., bgr=0., multi_scale=0.))
                trainer.model = SimpleNamespace(stride=torch.tensor([32]))
                trainer.data = dict(names=dict(enumerate(campaign.NAMES)), channels=3)
                trainer.device = torch.device("cpu")
                trainer.epoch = 0
                trainer.control = repeat
                trainer.sequences, trainer.augmentation = [], {}
                trainer.current_slot = None
                return trainer
            first, second = make_trainer(False), make_trainer(True)
            for trainer in (first, second):
                loader = trainer.get_dataloader(str(root / "images/train"), batch_size=2)
                iterator = iter(loader)
                for _ in range(2):
                    batch = next(iterator)
                    self.assertEqual(tuple(batch["img"].shape), (2, 3, 96, 96))
            self.assertEqual(first.sequences[0]["planned_source_ids"], second.sequences[0]["planned_source_ids"])
            self.assertEqual(first.augmentation, second.augmentation)
            self.assertEqual(len(first.augmentation), 4)
            self.assertTrue(all(name.startswith("row_") for name in second.sequences[0]["actual_source_ids"]))
            val = first.get_dataloader(str(root / "images/train"), batch_size=2, mode="val")
            self.assertFalse(val.dataset.augment)

    def test_human_review_cannot_be_bypassed_or_reused_for_changed_profiles(self):
        with self.temp() as folder:
            root = Path(folder)
            profile = root / "profiles.json"
            campaign.write(profile, {"candidate": 1})
            review = dict(approved=False, human_review="pending", profiles_file=str(profile), profiles_sha256=campaign.sha(profile))
            campaign.write(root / "review_lock.json", review)
            with self.assertRaisesRegex(ValueError, "Human class review"):
                campaign.verify_review(root)
            review.update(approved=True, human_review="approved")
            campaign.write(root / "review_lock.json", review)
            campaign.verify_review(root)
            campaign.write(profile, {"candidate": 2})
            with self.assertRaisesRegex(ValueError, "profiles changed"):
                campaign.verify_review(root)

    def test_active_budget_ignores_wall_clock_and_orphan_wait(self):
        with self.temp() as folder:
            root = Path(folder)
            campaign.initialize_budget(root)
            identity = dict(pid=7, created="instance1")
            record = dict(job_id="test", phase="render", state="active", identity=identity,
                          awake_started=100., active_seconds=8., started_utc=0.)
            campaign.write(root / "execution_jobs/test.json", record)
            with patch.object(campaign, "process_identity", return_value=identity), patch.object(campaign, "awake_seconds", return_value=112.):
                self.assertEqual(campaign.budget_usage(root)["total"], 12.)
                self.assertEqual(campaign.remaining_budget(root, "render"), 43200 - 12.)
            with patch.object(campaign, "process_identity", return_value=None), patch.object(campaign, "awake_seconds", return_value=100000.):
                self.assertEqual(campaign.budget_usage(root)["total"], 8.)
            with patch.object(campaign, "process_identity", return_value=dict(pid=7, created="recycled")):
                self.assertEqual(campaign.budget_usage(root)["total"], 8.)

    def test_bank_requires_all_pairs_identical_labels_geometry_and_camera(self):
        with self.temp() as folder:
            root = Path(folder)
            image, label, mask = root / "image.png", root / "label.txt", root / "mask.png"
            image.write_bytes(b"fixture-image")
            mask.write_bytes(b"fixture-mask")
            label.write_text("0 0.5 0.5 0.2 0.2\n")
            camera = dict(lens_mm=45., width=960, height=540)
            campaign.write(root / "banks/source_lock.json", dict(files={}))
            campaign.write(root / "banks/selection_lock.json", dict(used_validation=False, used_test=False, selected_view_ids=["v001"]))
            variant = dict(image=str(image), label=str(label), image_sha256=campaign.sha(image),
                           label_sha256=campaign.sha(label), mask=str(mask), mask_sha256=campaign.sha(mask),
                           geometry_sha256="geometry", camera_sha256=campaign.digest(camera), assignments_sha256="classes")
            view = dict(view_id="v001", scene_id="scene1", plant_ids=["plant1"], geometry_sha256="geometry",
                        camera=camera, camera_sha256=campaign.digest(camera), assignments_sha256="classes",
                        variants={b: copy.deepcopy(variant) for b in campaign.BANKS})
            manifest = dict(views=[view], source_lock_sha256=campaign.sha(root / "banks/source_lock.json"),
                            selection_lock_sha256=campaign.sha(root / "banks/selection_lock.json"))
            campaign.write(root / "banks/manifest.json", manifest)
            self.assertEqual(campaign.verify_bank(root)[0]["source_id"], "view_0000")
            view["variants"]["T"]["geometry_sha256"] = "changed"
            campaign.write(root / "banks/manifest.json", manifest)
            with self.assertRaisesRegex(ValueError, "Unpaired geometry"):
                campaign.verify_bank(root)
            view["variants"]["T"]["geometry_sha256"] = "geometry"
            campaign.write(root / "banks/manifest.json", manifest)
            mask.write_bytes(b"changed mask")
            with self.assertRaisesRegex(ValueError, "Changed bank artifact"):
                campaign.verify_bank(root)

    def test_eight_sequences_reconstruct_exact_slots_and_exposure(self):
        from train_appearance_arm import PairedSampler
        class Dataset:
            im_files = ["row_0001.png", "row_0002.png", "view_0000.png"]
            def __len__(self):
                return len(self.im_files)
        ids = [Path(p).stem for p in Dataset.im_files]
        for repeat in (False, True):
            trainer = SimpleNamespace(control=repeat, args=SimpleNamespace(seed=20261022), epoch=0, sequences=[])
            for epoch in range(8):
                trainer.epoch = epoch
                self.assertEqual(len(list(PairedSampler(trainer, Dataset()))), 1000)
            exposure = dict(Counter("real" if name.startswith("row_") else "synthetic"
                            for sequence in trainer.sequences for name in sequence["actual_source_ids"]))
            config = dict(seed=20261022, steps=4000, repeat_control=repeat)
            controller.verify_sequences(config, ids, trainer.sequences, exposure)
            self.assertEqual(sum(exposure.values()), 8000)
            trainer.sequences[-1]["actual_source_ids"][-1] = "invented"
            with self.assertRaisesRegex(ValueError, "sequence changed"):
                controller.verify_sequences(config, ids, trainer.sequences, exposure)

    def test_frozen_dose_is_reconstructed_from_validation_scores(self):
        with self.temp() as folder:
            root = Path(folder)
            matrix = dict(matrix=campaign.screen_matrix(), available_doses=list(campaign.DOSES))
            campaign.write(root / "matrix_lock.json", matrix)
            results = [dict(config=make_config(arm, campaign.SEEDS[0], 2000, "screen"), best_validation_ap=.2)
                       for arm in matrix["matrix"]]
            lookup = {r["config"]["name"]: r for r in results}
            lock = dict(selection_used_test=False, matrix_lock_sha256=campaign.sha(root / "matrix_lock.json"),
                        seeds=list(campaign.SEEDS), steps=4000, complete_screening_doses=list(campaign.DOSES),
                        doses={"0":46, "1":46}, screening={n:r["best_validation_ap"] for n,r in lookup.items()})
            campaign.write(root / "finalists_lock.json", lock)
            with patch.object(controller, "completed", side_effect=lambda _root, c: lookup[c["name"]]):
                controller.audit_finalists(root)
                lock["doses"]["1"] = 230
                campaign.write(root / "finalists_lock.json", lock)
                with self.assertRaisesRegex(ValueError, "Dose decision"):
                    controller.audit_finalists(root)

    def test_evaluation_lock_resume_never_returns_to_training(self):
        with self.temp() as folder:
            root = Path(folder)
            campaign.write(root / "evaluation_lock.json", {})
            frozen = dict(runs=["already_frozen"], pending_runs=["unavailable"])
            with patch.object(controller, "verify_review"), patch.object(controller, "GPUJobLock", return_value=contextlib.nullcontext()), \
                 patch.object(controller, "assert_no_orphans"), patch.object(controller, "prepare_matrix", return_value=dict(matrix=[])), \
                 patch.object(controller, "audit_confirmation", return_value=(frozen, {})), \
                 patch.object(controller, "run_subprocess") as launch, patch.object(controller, "run_arm") as train:
                controller.run(root)
            train.assert_not_called()
            self.assertEqual(launch.call_args.args[-1], "evaluation")
            self.assertEqual(campaign.read(root / "state.json")["stage"], "evaluation_complete_pending_review")

    def test_before_test_requires_all_36_runs_and_reconstructs_winners(self):
        with self.temp() as folder:
            root = Path(folder)
            matrix = campaign.screen_matrix([115])
            campaign.write(root / "matrix_lock.json", dict(matrix=matrix))
            finalists = dict(doses={"0":115, "1":115})
            campaign.write(root / "finalists_lock.json", finalists)
            def completion(_root, config):
                return dict(config=config, best_validation_ap=.3 if config["bank"] == "T" else .2,
                            best_sha256=config["name"])
            names, winners = [], {}
            for classic in (True, False):
                selected = [next(a for a in matrix if a["bank"] == b and a["classical"] == classic)
                            for b in (*campaign.BANKS, "real")]
                configs = [make_config(a, seed, 4000) for seed in campaign.SEEDS for a in selected]
                record = controller.winner_record([completion(root, c) for c in configs], 115, classic)
                winners[str(int(classic))] = record
                campaign.write(root / f"repetition_selection_c{int(classic)}.json", record)
                chosen = next(a for a in selected if a["bank"] == "T")
                configs += [make_config(chosen, seed, 4000, repeat=True) for seed in campaign.SEEDS]
                names.extend(c["name"] for c in configs)
            lock = dict(selection_used_test=False, test_status="development_previously_consulted",
                        finalists_sha256=campaign.sha(root / "finalists_lock.json"), winners=winners,
                        runs=names, weights={name:name for name in names})
            campaign.write(root / "evaluation_lock.json", lock)
            with patch.object(controller, "audit_finalists", return_value=(finalists, [])), \
                 patch.object(controller, "completed", side_effect=completion):
                _, values = controller.audit_confirmation(root)
                self.assertEqual(len(values), 36)
                lock["runs"] = names[:-1]
                campaign.write(root / "evaluation_lock.json", lock)
                with self.assertRaisesRegex(ValueError, "exact complete"):
                    controller.audit_confirmation(root)
                lock["runs"] = names
                lock["winners"]["1"]["bank"] = "LT"
                campaign.write(root / "evaluation_lock.json", lock)
                campaign.write(root / "repetition_selection_c1.json", lock["winners"]["1"])
                with self.assertRaisesRegex(ValueError, "mean validation"):
                    controller.audit_confirmation(root)

    def test_repetition_keeps_every_original_real_slot_and_augmentation(self):
        with self.temp() as folder:
            root = Path(folder)
            first = dict(epoch=0, planned_source_ids=["row_0001", "view_0000", "row_0002"],
                         actual_source_ids=["row_0001", "view_0000", "row_0002"])
            second = dict(first, actual_source_ids=["row_0001", "row_0002", "row_0002"])
            for name, sequence in (("original", first), ("repeat", second)):
                campaign.write(root / "training" / name / "sampling_sequences.json", [sequence])
                campaign.write(root / "training" / name / "augmentation_decisions.json", [dict(flip_horizontal=True)])
                campaign.write(root / "training" / name / "learning_rates.json", [.0002])
            self.assertTrue(verify_pair(root, "original", "repeat", True)["passed"])
            second["actual_source_ids"][0] = "row_0002"
            campaign.write(root / "training/repeat/sampling_sequences.json", [second])
            with self.assertRaisesRegex(ValueError, "original real slot"):
                verify_pair(root, "original", "repeat", True)

    def test_bootstrap_keeps_three_class_denominator_and_common_draws(self):
        from evaluate_appearance_campaign import checked_groups, three_class_ap
        records = [dict(group=f"g{c}", stats=dict(target_cls=[c])) for c in range(3)]
        design = checked_groups(records, 12, 5)
        self.assertEqual(design, checked_groups(records, 12, 5))
        self.assertTrue(design["rejected"])
        self.assertTrue(all(set(draw) == {"g0", "g1", "g2"} for draw in design["draws"]))
        from evaluate_augmentation_campaign import stats
        row = dict(stats=stats([dict(class_id=0, bbox=[0., 0., 10., 10.])], []))
        with self.assertRaisesRegex(ValueError, "three classes"):
            three_class_ap([row])


if __name__ == "__main__":
    unittest.main()
