"""Pure contracts, paired datasets and active-time accounting for appearance v1.

This module never imports or changes the historical campaign controllers.
"""
from __future__ import annotations

import contextlib
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import statistics
import sys
import threading
import time
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from uchuva_lsystem.execution_budget import awake_seconds

VERSION = "appearance-factorial/1"
BANKS = ("B", "L", "T", "LT")
NEW_BANKS = ("L", "T", "LT")
DOSES = (46, 115, 230)
SEEDS = (20261022, 20261023, 20261024)
NAMES = ("Pintona", "Madura", "Sobremadura")
DEFAULT_ROOT = REPO / "outputs/appearance_factorial_20261026"
BUDGET = dict(version="appearance-active-budget/1", limit_seconds=48 * 3600,
              render_limit_seconds=12 * 3600, evaluation_reserve_seconds=2 * 3600)


def read(path):
    # Windows may briefly deny readers while the heartbeat atomically replaces
    # its ledger. Retry only that transient I/O failure; never skip budget data.
    for attempt in range(20):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(.05)


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for attempt in range(20):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(.05)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def default_protocol():
    return dict(version=VERSION, weights=str(REPO / "yolo26n.pt"),
                weights_sha256="9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef",
                names=list(NAMES), banks=list(BANKS), doses=list(DOSES), seeds=list(SEEDS),
                screen_steps=2000, final_steps=4000, validation_interval=500,
                imgsz=960, batch=2, nbs=2, optimizer="AdamW", lr0=.0002,
                lr_schedule="linear by effective optimizer step from lr0 to 0.01*lr0",
                classical_recipe=dict(hsv_h=0, hsv_s=0, hsv_v=.1, fliplr=.5),
                seed_policy="Paired augmentation substreams keyed by training seed, epoch and slot",
                test_status="development_previously_consulted", selection_used_test=False,
                real_counts=dict(train=461, val=88, test=94), geometry_gate="descriptive_only",
                class_semantics="calyx appearance, not validated internal fruit maturity")


def check_protocol(root):
    protocol = read(Path(root) / "protocol.json")
    expected = default_protocol()
    for key in ("version", "weights_sha256", "names", "banks", "doses", "seeds", "screen_steps",
                "final_steps", "validation_interval", "imgsz", "batch", "nbs", "optimizer",
                "lr0", "lr_schedule", "classical_recipe", "test_status", "real_counts"):
        require(protocol.get(key) == expected[key], f"Unexpected protocol value: {key}")
    require(sha(protocol["weights"]) == protocol["weights_sha256"], "Initialization weights changed")
    return protocol


def initialize_budget(root):
    path = Path(root) / "effective_budget.json"
    if path.exists():
        require(read(path) == BUDGET, "Do not silently replace an existing active budget")
    else:
        write(path, BUDGET)
    return BUDGET.copy()


def process_identity(pid=None):
    """PID plus process creation tick prevents accepting a recycled Windows PID."""
    pid = os.getpid() if pid is None else int(pid)
    if os.name != "nt":
        try:
            return {"pid": pid, "created": Path(f"/proc/{pid}/stat").read_text().split()[21]}
        except (OSError, IndexError):
            return None
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        creation, end, system, user = (ctypes.c_ulonglong() for _ in range(4))
        if not kernel.GetProcessTimes(ctypes.c_void_p(handle), ctypes.byref(creation), ctypes.byref(end),
                                      ctypes.byref(system), ctypes.byref(user)):
            return None
        return {"pid": pid, "created": str(creation.value)}
    finally:
        kernel.CloseHandle(ctypes.c_void_p(handle))


def elapsed_job(record):
    saved = max(0., float(record.get("active_seconds", 0)))
    if record.get("state") == "active" and process_identity(record["identity"]["pid"]) == record["identity"]:
        tick = awake_seconds()
        if tick >= record["awake_started"]:
            return max(saved, tick - record["awake_started"])
    return saved


def budget_usage(root):
    rows = [read(p) for p in (Path(root) / "execution_jobs").glob("*.json")]
    return {"total": sum(elapsed_job(r) for r in rows),
            "render": sum(elapsed_job(r) for r in rows if r["phase"] == "render"),
            "jobs": len(rows)}


def remaining_budget(root, phase="train"):
    budget = read(Path(root) / "effective_budget.json")
    used = budget_usage(root)
    left = budget["limit_seconds"] - used["total"]
    if phase != "evaluation":
        left -= budget["evaluation_reserve_seconds"]
    if phase == "render":
        left = min(left, budget["render_limit_seconds"] - used["render"])
    return max(0., left)


class GPUJobLock:
    """Workspace-wide OS lock; remains held by its live owner, not a PID text file."""
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else REPO / "outputs/.appearance_gpu_job.lock"

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("a+b")
        self.stream.seek(0)
        if self.stream.read(1) == b"":
            self.stream.write(b"0")
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise RuntimeError("Another appearance GPU job owns the workspace lock") from None
        return self

    def __exit__(self, *_):
        self.stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        self.stream.close()


@contextlib.contextmanager
def charged_job(root, phase="render", job_id=None):
    """Charge only this active job. Never nest around a charged child/controller."""
    root = Path(root)
    initialize_budget(root)
    require(phase in {"render", "train", "evaluation"}, "Unknown budget phase")
    with GPUJobLock():
        require(remaining_budget(root, phase) > 0, f"Active {phase} budget exhausted")
        for path in (root / "execution_jobs").glob("*.json"):
            previous = read(path)
            if previous["state"] == "active":
                require(process_identity(previous["identity"]["pid"]) != previous["identity"],
                        "A live accounting owner still exists")
                previous.update(state="interrupted", recovery="Charged through last verified heartbeat only")
                write(path, previous)
        identifier = f"{job_id or phase}_{uuid.uuid4().hex[:12]}"
        path = root / "execution_jobs" / (identifier + ".json")
        record = dict(job_id=identifier, phase=phase, state="active", identity=process_identity(),
                      started_utc=time.time(), awake_started=awake_seconds(), active_seconds=0.)
        require(record["identity"] is not None, "Cannot verify accounting process identity")
        stopped = threading.Event()
        errors = []
        def heartbeat():
            while not stopped.wait(2):
                try:
                    record.update(active_seconds=max(0., awake_seconds() - record["awake_started"]),
                                  heartbeat_utc=time.time())
                    write(path, record)
                except Exception as error:
                    errors.append(repr(error))
                    return
        write(path, record)
        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        if os.name == "nt":
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
        try:
            yield record
            if errors:
                raise RuntimeError("Active budget heartbeat failed: " + errors[-1])
            record["state"] = "complete"
        except BaseException as error:
            record.update(state="failed", error=repr(error))
            raise
        finally:
            stopped.set()
            thread.join()
            record.update(active_seconds=max(0., awake_seconds() - record["awake_started"]), ended_utc=time.time())
            write(path, record)
            if os.name == "nt":
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


def verify_review(root):
    root = Path(root)
    review = read(root / "review_lock.json")
    require(review.get("approved") is True and review.get("human_review") == "approved",
            "Human class review is required before material freeze and training")
    profile = Path(review.get("profiles_file", root / "profiles.json"))
    require(sha(profile) == review["profiles_sha256"], "Reviewed appearance profiles changed")
    return review


def checked_labels(path):
    rows = []
    for line in Path(path).read_text().splitlines():
        values = list(map(float, line.split()))
        require(len(values) == 5 and all(math.isfinite(v) for v in values), f"Malformed label: {path}")
        c, x, y, w, h = values
        require(c in (0, 1, 2) and w > 0 and h > 0 and min(x-w/2, y-h/2) >= -1e-6
                and max(x+w/2, y+h/2) <= 1+1e-6, f"Invalid box: {path}")
        rows.append(values)
    return rows


def real_rows(root):
    manifest = read(Path(root) / "real_manifest.json")
    rows = manifest.get("records", manifest.get("rows"))
    require(isinstance(rows, list), "Expected real manifest records")
    result = []
    for row in rows:
        if row.get("status", "included") != "included":
            continue
        value = dict(row, source_id=f"row_{int(row['source_row']):04d}", domain="real")
        value["image_sha256"] = row.get("image_sha256", row.get("sha256"))
        result.append(value)
    return sorted(result, key=lambda r: r["source_id"])


def verify_real(root, expected_counts=None):
    rows = real_rows(root)
    require(len({r["source_id"] for r in rows}) == len(rows), "Duplicate real row")
    expected_counts = expected_counts or dict(train=461, val=88, test=94)
    for split, count in expected_counts.items():
        require(sum(r["split"] == split for r in rows) == count, f"Unexpected real {split} size")
    for field in ("group_id", "image_sha256"):
        sets = [{r[field] for r in rows if r["split"] == s} for s in ("train", "val", "test")]
        require(all(not sets[a] & sets[b] for a, b in ((0, 1), (0, 2), (1, 2))), f"Split leakage: {field}")
    for row in rows:
        for kind in ("image", "label"):
            require(Path(row[kind]).is_absolute(), "Dataset source paths must be absolute")
            require(sha(row[kind]) == row[kind + "_sha256"], f"Changed {kind}: {row['source_id']}")
        checked_labels(row["label"])
    return rows


def verify_bank(root):
    root = Path(root)
    manifest = read(root / "banks/manifest.json")
    require(isinstance(manifest, dict), "Expected versioned bank manifest")
    for name in ("source", "selection"):
        require(manifest.get(name + "_lock_sha256") == sha(root / "banks" / (name + "_lock.json")),
                f"Bank {name} lock changed")
    source_lock = read(root / "banks/source_lock.json")
    for path, expected in source_lock["files"].items():
        require(sha(path) == expected, "Frozen rendering source or asset changed: " + path)
    selection = read(root / "banks/selection_lock.json")
    require(selection["used_validation"] is False and selection["used_test"] is False,
            "Camera selection must use real training references only")
    views = manifest.get("views", manifest.get("rows")) if isinstance(manifest, dict) else manifest
    require(isinstance(views, list), "Expected ordered bank views")
    require(len({v["view_id"] for v in views}) == len(views), "Duplicated view IDs")
    require([v["view_id"] for v in views] == selection["selected_view_ids"][:len(views)],
            "Bank is not the complete prefix of the frozen nested selection")
    for index, view in enumerate(views):
        require(view.get("scene_id") and view.get("plant_ids"), "Missing plant/scene provenance")
        require(set(view["variants"]) == set(BANKS), "Every view must contain the complete visual factorial")
        require(all(view.get(key) for key in ("geometry_sha256", "camera_sha256", "assignments_sha256")),
                "Missing paired geometry/camera/assignment hashes")
        # The renderer's canonical JSON uses UTF-8 rather than ASCII escaping.
        camera_hash = hashlib.sha256(json.dumps(view["camera"], sort_keys=True, separators=(",", ":"),
                                               ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        require(camera_hash == view["camera_sha256"], "Camera snapshot changed")
        label_hashes, mask_hashes = set(), set()
        for bank in BANKS:
            row = view["variants"][bank]
            require(all(row.get(key) == view[key] for key in ("geometry_sha256", "camera_sha256", "assignments_sha256")),
                    f"Unpaired geometry/camera/assignments: {view['view_id']}/{bank}")
            for kind in ("image", "label", "mask"):
                require(sha(row[kind]) == row[kind + "_sha256"], f"Changed bank artifact: {view['view_id']}/{bank}")
            label_hashes.add(row["label_sha256"])
            mask_hashes.add(row["mask_sha256"])
            checked_labels(row["label"])
        require(len(label_hashes) == 1, f"Unpaired labels: {view['view_id']}")
        require(len(mask_hashes) == 1, f"Unpaired masks: {view['view_id']}")
        view["source_id"] = f"view_{index:04d}"
    return views


def arm_id(bank, dose, classical):
    return f"{bank}_n{dose:03d}_c{int(classical)}"


def screen_matrix(doses=DOSES):
    result = []
    for classical in (True, False):
        result.append(dict(arm=arm_id("real", 0, classical), bank="real", synthetic_images=0, classical=classical))
    for dose in sorted(doses, key=lambda n: (n != 115, n)):
        for classical in (True, False):
            for bank in BANKS:
                result.append(dict(arm=arm_id(bank, dose, classical), bank=bank,
                                   synthetic_images=dose, classical=classical))
    return result


def choose_dose(screenings, classical):
    available = [r for r in screenings if r["config"]["classical"] == classical and r["config"]["bank"] in NEW_BANKS]
    require(bool(available), "No completed new-appearance screening candidates")
    winner = min(available, key=lambda r: (-r["best_validation_ap"], r["config"]["synthetic_images"],
                                         NEW_BANKS.index(r["config"]["bank"])))
    return winner["config"]["synthetic_images"]


def choose_variant(completions, classical, seeds=SEEDS):
    grouped = {bank: [r for r in completions if r["config"]["classical"] == classical
                     and r["config"]["bank"] == bank and not r["config"].get("repeat_control")]
               for bank in NEW_BANKS}
    for bank, rows in grouped.items():
        require(len(rows) == len(seeds) and {r["config"]["seed"] for r in rows} == set(seeds),
                f"Incomplete paired seeds: {bank}")
    return min(NEW_BANKS, key=lambda b: (-statistics.mean(r["best_validation_ap"] for r in grouped[b]), NEW_BANKS.index(b)))


def schedule_indices(count, seed, epoch, length=1000):
    require(count > 0 and epoch >= 0, "Invalid sampler dimensions")
    rng = random.Random(seed)
    stream = []
    while len(stream) < (epoch + 1) * length:
        cycle = list(range(count))
        rng.shuffle(cycle)
        stream.extend(cycle)
    return stream[epoch * length:(epoch + 1) * length]


def slot_seed(seed, epoch, slot, component):
    return int(digest([seed, epoch, slot, component])[:8], 16)


def learning_rate(step, target, lr0=.0002):
    require(0 <= step < target, "Optimizer step outside frozen budget")
    return lr0 * (1 - .99 * step / max(1, target - 1))


def copy_link(source, target):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        require(sha(source) == sha(target), f"Existing dataset file differs: {target}")
        return
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def build_dataset(root, arm, real, views):
    folder = Path(root) / "datasets" / arm["arm"]
    entries = []
    for row in real:
        entries.append(dict(row))
    for view in views[:arm["synthetic_images"]]:
        entry = dict(view["variants"][arm["bank"]], source_id=view["source_id"], split="train",
                     domain="synthetic", group_id=view["scene_id"], view_id=view["view_id"], plant_ids=view["plant_ids"])
        entries.append(entry)
    entries.sort(key=lambda r: (r["split"], r["source_id"]))
    for entry in entries:
        extension = Path(entry["image"]).suffix.lower()
        entry["source_image"], entry["source_label"] = entry["image"], entry["label"]
        image = folder / "images" / entry["split"] / (entry["source_id"] + extension)
        label = folder / "labels" / entry["split"] / (entry["source_id"] + ".txt")
        copy_link(entry["image"], image)
        copy_link(entry["label"], label)
        entry.update(image=str(image.resolve()), label=str(label.resolve()))
    payload = dict(version=VERSION, arm=arm, entries=entries,
                   train_source_ids=sorted(r["source_id"] for r in entries if r["split"] == "train"))
    manifest = folder / "manifest.json"
    if manifest.exists():
        require(read(manifest) == payload, "Prepared dataset changed")
    else:
        write(manifest, payload)
    descriptor = dict(path=str(folder.resolve()), train="images/train", val="images/val", test="images/test", names=list(NAMES))
    descriptor_path = folder / "dataset.yaml"
    if descriptor_path.exists():
        require(read(descriptor_path) == descriptor, "Existing dataset descriptor changed")
    else:
        write(descriptor_path, descriptor)
    return str((folder / "dataset.yaml").resolve())


def source_files():
    return [REPO / "scripts" / p for p in ("appearance_campaign.py", "train_appearance_arm.py",
            "run_appearance_campaign.py", "evaluate_appearance_campaign.py", "evaluate_augmentation_campaign.py",
            "evaluate_union_detector.py", "augmentation_pilot.py")] + [REPO / "src/uchuva_lsystem/execution_budget.py"]


def verify_sources(root):
    lock = read(Path(root) / "training_source_lock.json")
    for path, value in lock["files"].items():
        require(sha(path) == value, f"Frozen appearance campaign source changed: {path}")
    import importlib.metadata
    for package, version in lock["packages"].items():
        require(importlib.metadata.version(package) == version, f"Training environment changed: {package}")
    return lock


def prepare_matrix(root):
    root = Path(root).resolve()
    protocol = check_protocol(root)
    verify_review(root)
    initialize_budget(root)
    real, views = verify_real(root), verify_bank(root)
    doses = [n for n in DOSES if len(views) >= n]
    matrix = screen_matrix(doses)
    for arm in matrix:
        arm["dataset"] = build_dataset(root, arm, real, views)
    lock = dict(version=VERSION, protocol_sha256=sha(root / "protocol.json"),
                review_sha256=sha(root / "review_lock.json"), bank_sha256=sha(root / "banks/manifest.json"),
                real_sha256=sha(root / "real_manifest.json"), available_doses=doses,
                unavailable_doses=[n for n in DOSES if n not in doses], matrix=matrix,
                selection_used_test=False)
    path = root / "matrix_lock.json"
    if path.exists():
        require(read(path) == lock, "Matrix inputs changed; create a new campaign revision")
        verify_sources(root)
    else:
        import importlib.metadata
        # The matrix itself is part of the immutable training contract, including
        # each canonical arm and dataset path. Freeze it before the source lock.
        write(path, lock)
        files = source_files() + [Path(protocol["weights"]), path, root / "protocol.json", root / "review_lock.json", root / "banks/manifest.json",
                                  root / "banks/source_lock.json", root / "banks/selection_lock.json",
                                  root / "real_manifest.json", Path(read(root / "review_lock.json").get("profiles_file", root / "profiles.json"))]
        files += [Path(p) for p in protocol.get("source_files", [])]
        for arm in matrix:
            files.extend([Path(arm["dataset"]), Path(arm["dataset"]).parent / "manifest.json"])
        write(root / "training_source_lock.json", dict(files={str(p): sha(p) for p in files},
              packages={p: importlib.metadata.version(p) for p in ("torch", "ultralytics", "numpy", "opencv-python")}))
    return lock
