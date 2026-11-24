"""Complete the authorized repetition controls without rerunning frozen finals.

This orchestration layer does not alter the trainer, data, sampling or evaluator.
Prepare archives the previous closure and incomplete repetition before any run.
"""
from __future__ import annotations

import argparse
import collections
import ctypes
import json
import importlib.metadata
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO / "outputs/augmentation_pilot_20261022/synthetic_exploratory_extension"
REVISION = "03_authorized_completion_20261026"


def configure(root):
    os.environ["UCHUVA_AUGMENTATION_ROOT"] = str(root)
    from augmentation_pilot import read, write, sha
    return read, write, sha


def verify(root):
    """Verify persisted evidence before reusing any completed run."""
    read, write, sha = configure(root)
    for path, digest in read(root / "training_source_lock.json")["files"].items():
        assert sha(path) == digest, f"Frozen source changed: {path}"
    protocol = read(root / "protocol.json")
    assert sha(protocol["weights"]) == protocol["weights_sha256"]
    matrix = read(root / "matrix.json")
    lock = read(root / "finalists_lock.json")
    assert lock["test_read"] is False
    rows = {}
    for path in sorted((root / "training").glob("*/completion.json")):
        row = read(path)
        config = row["config"]
        expected = 2000 if path.parent.name.startswith("screen_") else 4000
        assert row["completed"] and row["steps"] == expected
        assert sum(row["exposure"].values()) == 2 * expected
        assert sha(path.parent / "weights/best.pt") == row["best_sha256"]
        assert sha(path.parent / "weights/last.pt") == row["last_sha256"]
        assert sha(root / "protocol.json") == config["protocol_sha256"]
        assert sha(Path(config["dataset"]).parent / "manifest.json") == config["dataset_sha256"]
        assert config["code_sha256"] == sha(REPO / "scripts/train_augmentation_arm.py")
        for package in ["torch", "ultralytics"]:
            assert importlib.metadata.version(package) == config[package], f"Environment changed: {package}"
        sequences = read(path.parent / "sampling_sequences.json")
        assert len(sequences) == expected // 500
        assert all(len(s["actual_source_ids"]) == 1000 for s in sequences)
        rows[path.parent.name] = row
    counts = dict(screening=sum(n.startswith("screen_") for n in rows),
                  synthetic_finals=sum(n.startswith("final_") and r["config"]["synthetic_ratio"] > 0 for n, r in rows.items()),
                  real_finals=sum(n.startswith("final_") and r["config"]["synthetic_ratio"] == 0 for n, r in rows.items()),
                  repetitions=sum(n.startswith("repeat_") for n in rows))
    assert (counts["screening"], counts["synthetic_finals"], counts["real_finals"]) == (24, 18, 18)
    for arm in lock["finalists"]:
        if arm["synthetic_ratio"]:
            same = [a for a in matrix if a["real_fraction"] == arm["real_fraction"]
                    and a["classical"] == arm["classical"] and a["synthetic_ratio"] > 0]
            chosen = max(same, key=lambda a: (rows["screen_" + a["arm"]]["best_validation_ap"], -a["synthetic_ratio"]))
            assert chosen["arm"] == arm["arm"]
        for seed in protocol["seeds"]:
            assert f"final_{arm['arm']}_{seed}" in rows
    groups = collections.defaultdict(list)
    for name, row in rows.items():
        if name.startswith("final_") and row["config"]["synthetic_ratio"] > 0:
            groups[row["config"]["arm"]].append(row)
    assert all(len(group) == 3 for group in groups.values())
    winner = max(groups, key=lambda arm: statistics.mean(r["best_validation_ap"] for r in groups[arm]))
    assert winner == "r100_s25_c1", "Unexpected change to frozen validation winner"
    seen, real_sets, synthetic_sets = {}, {}, {}
    for arm in matrix:
        entries = read(Path(arm["dataset"]).parent / "manifest.json")["entries"]
        for a, b in [("train", "val"), ("train", "test"), ("val", "test")]:
            for key in ["image_sha256", "group"]:
                x = {e[key] for e in entries if e["split"] == a and e.get(key)}
                y = {e[key] for e in entries if e["split"] == b and e.get(key)}
                assert not x & y, (a, b, key)
        real_sets[arm["real_fraction"]] = {e["source_id"] for e in entries if e["split"] == "train" and e["domain"] == "real"}
        synthetic_sets[(arm["real_fraction"], arm["synthetic_images"])] = {e["source_id"] for e in entries if e["split"] == "train" and e["domain"] == "synthetic"}
        for entry in entries:
            for key in ["image", "label"]:
                path, digest = entry[key], entry[key + "_sha256"]
                if path not in seen:
                    assert sha(path) == digest, path
                    seen[path] = digest
                else:
                    assert seen[path] == digest
    assert real_sets[25] <= real_sets[50] <= real_sets[100]
    for fraction in [25, 50, 100]:
        banks = [v for (f, _), v in sorted(synthetic_sets.items()) if f == fraction]
        assert all(a <= b for a, b in zip(banks, banks[1:]))
    audit = dict(verified_at=time.time(), counts=counts, data_files=len(seen),
                 frozen_sources=True, steps_weights_exposure=True, split_group_isolation=True,
                 nested_subsets=True, winner=winner, winner_selection="mean validation AP only",
                 finalists_sha256=sha(root / "finalists_lock.json"), test_metrics_used=False,
                 completions={n: sha(root / "training" / n / "completion.json") for n in rows})
    return audit, rows, groups[winner]


def prepare(root):
    read, write, sha = configure(root)
    revision = root / "revisions" / REVISION
    if revision.exists():
        raise FileExistsError(f"Do not overwrite revision: {revision}")
    audit, rows, winner = verify(root)
    assert not (root / "evaluation_lock.json").exists(), "Preserve/review existing evaluation lock before continuing"
    revision.mkdir(parents=True)
    artifacts = [root / "state.json", root / "budget.json", root / "controller_failure.json",
                 root / "finalists_lock.json", root / "training_source_lock.json",
                 REPO / "docs/reports/piloto_aumentacion_sintetica_exploratoria_2026-10-22.md"]
    preserved = {}
    for path in artifacts:
        if path.exists():
            shutil.copy2(path, revision / path.name)
            preserved[str(path)] = sha(path)
    for result in winner:
        name = "repeat_" + result["config"]["name"]
        output = root / "training" / name
        if output.exists() and not (output / "completion.json").exists():
            # Both resolved targets must remain inside the authorized campaign.
            source = output.resolve()
            destination = (revision / "incomplete_attempts" / name).resolve()
            assert source.is_relative_to(root) and destination.is_relative_to(revision.resolve())
            inventory = {str(p.relative_to(source)): sha(p) for p in source.rglob("*") if p.is_file()}
            destination.parent.mkdir(exist_ok=True)
            shutil.move(str(source), str(destination))
            write(destination.parent / (name + "_hashes.json"), inventory)
        for path in [root / "logs" / (name + ".log"), root / "configs" / (name + ".json"),
                     root / "configs" / (name + "_frozen.json")]:
            if path.exists():
                destination = revision / path.parent.name / path.name
                destination.parent.mkdir(exist_ok=True)
                shutil.copy2(path, destination)
                preserved[str(path)] = sha(path)
    now = time.time()
    budget = read(root / "budget.json")
    budget.update(deadline=now + 7 * 86400, training_deadline=now + 7 * 86400 - 7200,
                  continuation_authorized_at=now, continuation_days=7,
                  continuation_revision=REVISION,
                  continuation_policy="User authorized time necessary to finish; no sleep-inflated admission estimate")
    write(revision / "authorization.json", dict(authorized_at=now, user_instruction=
        "Continúa hasta completar los tres controles de repetición y la evaluación final. Amplía el tiempo necesario y conserva los resultados ya obtenidos para confirmar si las mejoras se mantienen.",
        scope="Three 4000-step repetitions, frozen final evaluation and paired group bootstrap; no new selection/trainer/data/renders",
        winner=audit["winner"], initial_wall_time_guard_days=7, preserved_sha256=preserved))
    write(revision / "verification.json", audit)
    write(root / "budget.json", budget)
    write(revision / "new_budget.json", budget)
    write(root / "state.json", dict(stage="continuation_prepared", complete=False, closed=False,
                                    revision=REVISION, updated=now, winner=audit["winner"]))
    print(json.dumps(audit, indent=2))


def run(root):
    read, write, sha = configure(root)
    revision = root / "revisions" / REVISION
    assert (revision / "authorization.json").exists()
    # OS-held lock survives pauses and is released on process termination.
    import msvcrt
    with (revision / "controller.lock").open("a+b") as controller_lock:
        controller_lock.seek(0)
        if not controller_lock.read(1):
            controller_lock.write(b"0")
            controller_lock.flush()
        controller_lock.seek(0)
        msvcrt.locking(controller_lock.fileno(), msvcrt.LK_NBLCK, 1)
        keep_awake = ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
        write(revision / "controller_identity.json", dict(pid=os.getpid(), started=time.time(),
            executable=sys.executable, command=sys.argv, prevent_automatic_sleep=bool(keep_awake),
            limitation="Transient system wake request only; manual suspension/lid closure can still pause work"))
        try:
            for path, digest in read(revision / "continuation_source_lock.json")["files"].items():
                assert sha(path) == digest, path
            audit, rows, winner = verify(root)
            assert audit["finalists_sha256"] == read(revision / "verification.json")["finalists_sha256"]
            for name, digest in read(revision / "verification.json")["completions"].items():
                assert sha(root / "training" / name / "completion.json") == digest
            write(revision / "run_verification.json", audit)
            from run_augmentation_campaign import run_arm, job
            repeats = []
            for result in sorted(winner, key=lambda r: r["config"]["seed"]):
                config = dict(result["config"], name="repeat_" + result["config"]["name"], repeat_control=True)
                output = root / "training" / config["name"]
                if output.exists() and not (output / "completion.json").exists():
                    raise RuntimeError(f"Incomplete attempt requires preserved recovery: {output}")
                repeated = run_arm(config)
                original_sequences = read(root / "training" / result["config"]["name"] / "sampling_sequences.json")
                repeated_sequences = read(output / "sampling_sequences.json")
                assert len(original_sequences) == len(repeated_sequences) == 8
                for a, b in zip(original_sequences, repeated_sequences):
                    assert a["planned_source_ids"] == b["planned_source_ids"]
                    assert all(x == y for x, y in zip(a["actual_source_ids"], b["actual_source_ids"]) if x.startswith("row_"))
                    assert all(x.startswith("row_") for x in b["actual_source_ids"])
                assert repeated["steps"] == 4000 and repeated["exposure"] == {"real": 8000}
                write(output / "repetition_pair_check.json", dict(passed=True, original=result["config"]["name"],
                    planned_slots=8000, original_real_slots_preserved=True, synthetic_slots_replaced_by_real=True))
                repeats.append(repeated)
            finals = [r for n, r in rows.items() if n.startswith("final_")]
            assert len(finals) == 36 and len(repeats) == 3
            runs = finals + repeats
            payload = dict(created=time.time(), finalists_sha256=sha(root / "finalists_lock.json"),
                runs=[r["config"]["name"] for r in runs], weights={r["config"]["name"]: r["best_sha256"] for r in runs},
                test_status=read(root / "protocol.json")["test_status"], selection_used_test=False,
                revision=REVISION, repetition_winner=audit["winner"])
            lock = root / "evaluation_lock.json"
            if lock.exists():
                previous = read(lock)
                assert {k: v for k, v in previous.items() if k != "created"} == {k: v for k, v in payload.items() if k != "created"}
            else:
                write(lock, payload)
                write(revision / "evaluation_lock.json", payload)
            deadline = read(root / "budget.json")["deadline"]
            job("evaluate_synthetic_extension.py", [], "evaluation", deadline)
            job("complete_augmentation_evaluation.py", ["--root", root], "paired_confirmation", deadline)
            write(root / "state.json", dict(stage="evaluation_complete_pending_review", complete=False,
                updated=time.time(), runs=39, repetitions_completed=3, revision=REVISION,
                review="Inspect curves, direct contrasts, sample predictions and graph before final delivery"))
        except Exception as error:
            failure = dict(error=repr(error), when=time.time(), pid=os.getpid(), revision=REVISION)
            write(revision / f"failure_{int(time.time())}.json", failure)
            write(root / "state.json", dict(stage="needs_attention", complete=False, **failure))
            raise
        finally:
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "verify", "run"])
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    campaign_root = args.root.resolve()
    if args.action == "prepare":
        prepare(campaign_root)
    elif args.action == "verify":
        print(json.dumps(verify(campaign_root)[0], indent=2))
    else:
        run(campaign_root)
