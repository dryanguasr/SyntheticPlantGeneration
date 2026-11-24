"""Serial, resumable appearance factorial controller; human review is mandatory."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import random
import shutil
import statistics
import subprocess
import sys
import time
import uuid

from appearance_campaign import (BANKS, DEFAULT_ROOT, SEEDS, GPUJobLock, arm_id, budget_usage,
    charged_job, check_protocol, choose_dose, choose_variant, learning_rate, prepare_matrix,
    process_identity, read, remaining_budget, require, schedule_indices, sha, verify_review, verify_sources, write)


def make_config(arm, seed, steps, phase="final", repeat=False):
    name = f"{phase}_{arm['arm']}_{seed}"
    if repeat:
        name = "repeat_" + name
    return dict(arm, name=name, seed=seed, steps=steps, repeat_control=repeat)


def verify_sequences(config, source_ids, sequences, exposure):
    """Reconstruct all four/eight 1000-slot epochs, including repetition RNG."""
    require(len(sequences) == config["steps"] // 500, "Invalid epoch count")
    observed = Counter()
    for epoch, row in enumerate(sequences):
        indices = schedule_indices(len(source_ids), config["seed"], epoch)
        planned = [source_ids[i] for i in indices]
        if config["repeat_control"]:
            real = [i for i, name in enumerate(source_ids) if name.startswith("row_")]
            rng = random.Random(config["seed"] + 900000 + epoch)
            indices = [rng.choice(real) if name.startswith("view_") else i for i, name in zip(indices, planned)]
        actual = [source_ids[i] for i in indices]
        require(row == dict(epoch=epoch, indices=indices, planned_source_ids=planned, actual_source_ids=actual),
                f"Frozen sample sequence changed at epoch {epoch}")
        observed.update("real" if name.startswith("row_") else "synthetic" for name in actual)
    require(dict(observed) == exposure, "Reported image exposure differs from sample slots")


def completed(root, config):
    directory = Path(root) / "training" / config["name"]
    path = directory / "completion.json"
    if not path.exists():
        return None
    value = read(path)
    require(value["completed"] and value["steps"] == config["steps"], "Truncated run is not a completed arm")
    for key, expected in config.items():
        require(value["config"].get(key) == expected, f"Completed configuration changed: {key}")
    require(value["config"]["protocol_sha256"] == sha(Path(root) / "protocol.json"), "Protocol mismatch")
    require(value["config"]["training_source_lock_sha256"] == sha(Path(root) / "training_source_lock.json"), "Source lock mismatch")
    require(value["config"]["dataset_sha256"] == sha(Path(config["dataset"]).parent / "manifest.json"), "Dataset mismatch")
    require(value["config"]["dataset_descriptor_sha256"] == sha(config["dataset"]), "Dataset descriptor mismatch")
    require(sum(value["exposure"].values()) == 2 * config["steps"], "Unexpected exposure")
    for filename, key in (("weights/best.pt", "best_sha256"), ("weights/last.pt", "last_sha256"),
                          ("sampling_sequences.json", "sequence_sha256"),
                          ("augmentation_decisions.json", "augmentation_sha256"),
                          ("learning_rates.json", "learning_rates_sha256")):
        require(sha(directory / filename) == value[key], f"Changed training artifact: {filename}")
    require(read(directory / "learning_rates.json") == [learning_rate(i, config["steps"]) for i in range(config["steps"])],
            "Effective LR schedule differs")
    sequences = read(directory / "sampling_sequences.json")
    manifest = read(Path(config["dataset"]).parent / "manifest.json")
    verify_sequences(config, manifest["train_source_ids"], sequences, value["exposure"])
    decisions = read(directory / "augmentation_decisions.json")
    require([(r["epoch"], r["slot"]) for r in decisions] == [(e, s) for e in range(config["steps"] // 500) for s in range(1000)],
            "Missing paired augmentation slots")
    return value


def verify_pair(root, first, second, repeat=False):
    a = Path(root) / "training" / first
    b = Path(root) / "training" / second
    aa, bb = read(a / "sampling_sequences.json"), read(b / "sampling_sequences.json")
    require(len(aa) == len(bb), "Different sequence lengths")
    for x, y in zip(aa, bb):
        require(x["planned_source_ids"] == y["planned_source_ids"], "Planned slots changed between pairs")
        if repeat:
            require(all(left == right for left, right in zip(x["actual_source_ids"], y["actual_source_ids"])
                        if left.startswith("row_")), "Repetition changed an original real slot")
            require(all(name.startswith("row_") for name in y["actual_source_ids"]), "Synthetic content in repetition control")
        else:
            require(x["actual_source_ids"] == y["actual_source_ids"], "Unpaired actual source IDs")
    require(read(a / "augmentation_decisions.json") == read(b / "augmentation_decisions.json"), "Unpaired augmentation decisions")
    require(read(a / "learning_rates.json") == read(b / "learning_rates.json"), "Unpaired LR schedule")
    payload = dict(passed=True, original=first, paired=second, repetition=repeat,
                   sequences=len(aa), slots=sum(len(s["actual_source_ids"]) for s in aa))
    write(b / ("repetition_pair_check.json" if repeat else "visual_pair_check.json"), payload)
    return payload


def assert_no_orphans(root):
    for path in (Path(root) / "children").glob("*.json"):
        record = read(path)
        if record.get("identity") and process_identity(record["identity"]["pid"]) == record["identity"]:
            raise RuntimeError(f"Prior child is still alive: {record['name']} / {record['identity']}")


def preserve_partial(root, name):
    root = Path(root)
    source = root / "training" / name
    if not source.exists():
        return
    require(not (source / "completion.json").exists(), "Never archive a completed run as partial")
    assert_no_orphans(root)
    verify_sources(root)
    target = root / "recovery" / f"{name}_{uuid.uuid4().hex[:10]}"
    target.mkdir(parents=True, exist_ok=False)
    hashes = {str(p.relative_to(source)): sha(p) for p in source.rglob("*") if p.is_file()}
    write(target / "preserved_hashes.json", dict(reason="Interrupted attempt; restart from common original weights", files=hashes))
    # Both paths are resolved and verified inside this campaign before moving.
    require(source.resolve().is_relative_to(root.resolve()) and target.resolve().is_relative_to(root.resolve()), "Unsafe recovery path")
    shutil.move(str(source), str(target / "attempt"))
    for config in (root / "configs").glob(name + "*.json"):
        shutil.copy2(config, target / config.name)


def run_subprocess(root, name, script, arguments, phase):
    root = Path(root)
    assert_no_orphans(root)
    attempt = uuid.uuid4().hex[:10]
    log = root / "logs" / f"{name}_{attempt}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with charged_job(root, phase, name) as accounting:
        command = [sys.executable, str(Path(__file__).with_name(script)), "--root", str(root),
                   *map(str, arguments), "--accounting-job", accounting["job_id"]]
        with log.open("x", encoding="utf-8") as stream:
            child = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1], stdout=stream, stderr=subprocess.STDOUT)
            identity = process_identity(child.pid)
            record = dict(name=name, identity=identity, command=command, log=str(log), accounting_job=accounting["job_id"])
            child_path = root / "children" / (attempt + ".json")
            write(child_path, record)
            try:
                while child.poll() is None:
                    if remaining_budget(root, phase) <= 0:
                        child.terminate()
                        child.wait(timeout=60)
                        raise TimeoutError(f"Active {phase} budget exhausted during {name}")
                    time.sleep(2)
                require(child.returncode == 0, f"{name} failed ({child.returncode}); preserve {log}")
            except BaseException:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=60)
                raise
            finally:
                record.update(returncode=child.poll(), finished_utc=time.time())
                write(child_path, record)


def run_arm(root, config):
    value = completed(root, config)
    if value:
        return value
    preserve_partial(root, config["name"])
    path = Path(root) / "configs" / (config["name"] + ".json")
    write(path, config)
    write(Path(root) / "state.json", dict(stage="training", run=config["name"], complete=False,
                                          human_review="approved", updated_utc=time.time()))
    run_subprocess(root, config["name"], "train_appearance_arm.py", ["--config", path], "train")
    return completed(root, config)


def estimated_seconds(root, steps):
    rates = []
    for path in (Path(root) / "execution_jobs").glob("*.json"):
        row = read(path)
        if row["phase"] != "train" or row["state"] != "complete":
            continue
        name = row["job_id"].rsplit("_", 1)[0]
        completion = Path(root) / "training" / name / "completion.json"
        if completion.exists():
            rates.append(row["active_seconds"] / read(completion)["steps"])
    return steps * (max(statistics.median(rates[-8:]), .15) * 1.25 if rates else .30)


def block_fits(root, configs):
    missing = [c for c in configs if not completed(root, c)]
    return remaining_budget(root, "train") >= sum(estimated_seconds(root, c["steps"]) for c in missing)


def freeze_json(path, payload):
    if Path(path).exists():
        require(read(path) == payload, f"Frozen selection changed: {path}")
    else:
        write(path, payload)


def audit_finalists(root, matrix=None):
    """Reconstruct the frozen validation-only dose decision on every resume."""
    root = Path(root)
    matrix = matrix or read(root / "matrix_lock.json")
    lock = read(root / "finalists_lock.json")
    require(lock["selection_used_test"] is False and lock["matrix_lock_sha256"] == sha(root / "matrix_lock.json"),
            "Finalist selection inputs changed")
    require(lock["seeds"] == list(SEEDS) and lock["steps"] == 4000, "Finalist protocol changed")
    doses = lock["complete_screening_doses"]
    require(bool(doses) and len(set(doses)) == len(doses) and set(doses) <= set(matrix["available_doses"]),
            "Invalid frozen screening blocks")
    selected = [arm for arm in matrix["matrix"] if arm["bank"] == "real" or arm["synthetic_images"] in doses]
    screenings = [completed(root, make_config(arm, SEEDS[0], 2000, "screen")) for arm in selected]
    require(all(screenings), "Frozen dose selection includes incomplete screening")
    require(lock["screening"] == {r["config"]["name"]: r["best_validation_ap"] for r in screenings},
            "Frozen validation scores changed")
    expected = {str(int(c)): choose_dose(screenings, c) for c in (True, False)}
    require(lock["doses"] == expected, "Dose decision does not follow frozen validation/tie rule")
    return lock, screenings


def winner_record(results, dose, classical):
    return dict(bank=choose_variant(results, classical), dose=dose, classical=classical, selection_used_test=False,
                validation_means={b: statistics.mean(r["best_validation_ap"] for r in results
                                                    if r["config"]["bank"] == b) for b in BANKS})


def audit_confirmation(root):
    """Verify exact final arms, seeds, winners and weights before opening test."""
    root = Path(root)
    finalists, _ = audit_finalists(root)
    lock = read(root / "evaluation_lock.json")
    require(lock["selection_used_test"] is False and lock["test_status"] == "development_previously_consulted",
            "Evaluation is not a locked development comparison")
    require(lock["finalists_sha256"] == sha(root / "finalists_lock.json"), "Finalist lock changed")
    require(bool(lock["winners"]) and set(lock["winners"]) <= {"0", "1"}, "Invalid confirmation recipes")
    arms = {a["arm"]: a for a in read(root / "matrix_lock.json")["matrix"]}
    configs, results = [], []
    for classic in (True, False):
        key = str(int(classic))
        if key not in lock["winners"]:
            continue
        dose = finalists["doses"][key]
        selected = [arms[arm_id(b, dose, classic)] for b in BANKS] + [arms[arm_id("real", 0, classic)]]
        main = [make_config(arm, seed, 4000) for seed in SEEDS for arm in selected]
        values = [completed(root, config) for config in main]
        require(all(values), "Incomplete three-seed factorial before test")
        expected_winner = winner_record(values, dose, classic)
        require(lock["winners"][key] == expected_winner
                and read(root / f"repetition_selection_c{key}.json") == expected_winner,
                "Repetition winner does not follow mean validation/tie rule")
        repeats = [make_config(arms[arm_id(expected_winner["bank"], dose, classic)], seed, 4000, repeat=True) for seed in SEEDS]
        repeated = [completed(root, config) for config in repeats]
        require(all(repeated), "Incomplete three-seed repetition block before test")
        configs.extend(main + repeats)
        results.extend(values + repeated)
    require(lock["runs"] == [c["name"] for c in configs], "Evaluation run list is not the exact complete confirmation blocks")
    require(lock["weights"] == {r["config"]["name"]: r["best_sha256"] for r in results}, "Frozen evaluation weights changed")
    return lock, {r["config"]["name"]: r for r in results}


def run(root):
    root = Path(root).resolve()
    verify_review(root)
    with GPUJobLock(root / "controller.lock"):
        assert_no_orphans(root)
        lock = prepare_matrix(root)
        arms = {a["arm"]: a for a in lock["matrix"]}
        skipped = []
        try:
            # Once test was unlocked, a resume can only finish that frozen
            # evaluation. Extra time must not expand the selected run set.
            if (root / "evaluation_lock.json").exists():
                evaluation, _ = audit_confirmation(root)
                run_subprocess(root, "development_evaluation", "evaluate_appearance_campaign.py", [], "evaluation")
                write(root / "state.json", dict(stage="evaluation_complete_pending_review", complete=False,
                    evaluated_runs=len(evaluation["runs"]), pending_runs=evaluation["pending_runs"],
                    budget_usage=budget_usage(root), review="Inspect persisted curves, samples and report before closing"))
                return
            if (root / "finalists_lock.json").exists():
                finalist_payload, screenings = audit_finalists(root, lock)
                skipped = list(finalist_payload["pending_screening_runs"])
            else:
                controls = [make_config(a, SEEDS[0], 2000, "screen") for a in lock["matrix"] if a["bank"] == "real"]
                if not block_fits(root, controls):
                    raise TimeoutError("Insufficient active time for the real screening block")
                screenings = [run_arm(root, c) for c in controls]
                complete_doses = []
                for dose in sorted(lock["available_doses"], key=lambda n: (n != 115, n)):
                    configs = [make_config(a, SEEDS[0], 2000, "screen") for a in lock["matrix"] if a["synthetic_images"] == dose]
                    if not block_fits(root, configs):
                        skipped.extend(c["name"] for c in configs if not completed(root, c))
                        continue
                    results = [run_arm(root, c) for c in configs]
                    for classical in (True, False):
                        baseline = f"screen_{arm_id('B', dose, classical)}_{SEEDS[0]}"
                        for bank in ("L", "T", "LT"):
                            verify_pair(root, baseline, f"screen_{arm_id(bank, dose, classical)}_{SEEDS[0]}")
                    screenings.extend(results)
                    complete_doses.append(dose)
                require(complete_doses, "No complete synthetic screening dose; preserve controls and report pending")
                finalist_payload = dict(selection_used_test=False,
                    doses={str(int(c)): choose_dose(screenings, c) for c in (True, False)}, complete_screening_doses=complete_doses,
                    screening={r["config"]["name"]: r["best_validation_ap"] for r in screenings},
                    matrix_lock_sha256=sha(root / "matrix_lock.json"), seeds=list(SEEDS), steps=4000,
                    pending_screening_runs=skipped.copy())
                freeze_json(root / "finalists_lock.json", finalist_payload)
            dose_choices = finalist_payload["doses"]
            finals = []
            winners = {}
            for classical in (True, False):
                dose = dose_choices[str(int(classical))]
                selections = [arms[arm_id(b, dose, classical)] for b in BANKS] + [arms[arm_id("real", 0, classical)]]
                configs = [make_config(arm, seed, 4000) for seed in SEEDS for arm in selections]
                # Reserve all three repetition runs before starting this comparable block.
                repetition_path = root / f"repetition_selection_c{int(classical)}.json"
                missing_repeats = 3
                if repetition_path.exists():
                    previous_winner = read(repetition_path)["bank"]
                    repeat_arm = arms[arm_id(previous_winner, dose, classical)]
                    missing_repeats = sum(completed(root, make_config(repeat_arm, seed, 4000, repeat=True)) is None for seed in SEEDS)
                if not block_fits(root, configs) or remaining_budget(root, "train") < sum(
                        estimated_seconds(root, c["steps"]) for c in configs if not completed(root, c)) + missing_repeats * estimated_seconds(root, 4000):
                    skipped.extend(c["name"] for c in configs if not completed(root, c))
                    continue
                results = [run_arm(root, config) for config in configs]
                for seed in SEEDS:
                    first = f"final_{arm_id('B', dose, classical)}_{seed}"
                    for bank in ("L", "T", "LT"):
                        verify_pair(root, first, f"final_{arm_id(bank, dose, classical)}_{seed}")
                selection = winner_record(results, dose, classical)
                winner = selection["bank"]
                freeze_json(root / f"repetition_selection_c{int(classical)}.json", selection)
                repetitions = []
                for seed in SEEDS:
                    config = make_config(arms[arm_id(winner, dose, classical)], seed, 4000, repeat=True)
                    value = run_arm(root, config)
                    verify_pair(root, config["name"].removeprefix("repeat_"), config["name"], repeat=True)
                    repetitions.append(value)
                finals.extend(results + repetitions)
                winners[str(int(classical))] = selection
            require(finals, "No complete three-seed confirmation block; evaluation remains pending")
            evaluation = dict(selection_used_test=False, test_status="development_previously_consulted",
                              finalists_sha256=sha(root / "finalists_lock.json"), winners=winners,
                              runs=[r["config"]["name"] for r in finals],
                              weights={r["config"]["name"]: r["best_sha256"] for r in finals},
                              unavailable_doses=lock["unavailable_doses"], pending_runs=skipped)
            freeze_json(root / "evaluation_lock.json", evaluation)
            run_subprocess(root, "development_evaluation", "evaluate_appearance_campaign.py", [], "evaluation")
            write(root / "state.json", dict(stage="evaluation_complete_pending_review", complete=False,
                  evaluated_runs=len(finals), screening_runs=len(screenings), pending_runs=skipped,
                  budget_usage=budget_usage(root), review="Inspect curves, prediction samples and final report before closing"))
        except BaseException as error:
            failure = dict(error=repr(error), when_utc=time.time(), identity=process_identity(), pending_runs=skipped)
            write(root / "failures" / (uuid.uuid4().hex + ".json"), failure)
            write(root / "state.json", dict(stage="needs_attention", complete=False, **failure))
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "verify"))
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    if args.action == "run":
        run(args.root)
    elif args.action == "prepare":
        prepare_matrix(args.root)
    else:
        verify_review(args.root)
        verify_sources(args.root)
        check_protocol(args.root)
        print("Frozen review, sources, environment and protocol verified")
