"""Bindings for the lossless input-cache revision of a sealed mask campaign."""

from pathlib import Path

from .store import read, sha


REVISION_NAME = "training_input_cache_revision.json"
VERSION = "sealed-mask-cache-transition/1"
WORKER = Path(__file__).resolve().parents[2] / "scripts/train_private_mask_ladder.py"


def campaign_file(root, value):
    path = (root / value).resolve(strict=True)
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Training revision evidence outside the private campaign: {path}")
    return path


def verified_record(root, path, digest):
    path = campaign_file(root, path)
    if sha(path) != digest:
        raise ValueError(f"Training revision evidence changed: {path}")
    return path


def load_revision(root):
    anchor = root / REVISION_NAME
    if not anchor.is_file():
        return None
    revision = read(anchor)
    if revision["version"] != VERSION:
        raise ValueError("Unknown training input cache revision")
    previous = verified_record(root, revision["previous_sources"], revision["previous_sources_sha256"])
    if read(previous)["files"].get(str(WORKER)) != revision["historical_worker_sha256"]:
        raise ValueError("The archived worker does not match the previous source lock")
    verified_record(root, revision["cache_manifest"], revision["cache_manifest_sha256"])
    return revision


def compatible_protocol(root, path, expected, revision):
    previous = read(path)
    if previous == expected:
        return expected
    resumed = revision["continued_run"] if revision else None
    if (not resumed or (resumed["phase"], resumed["seed"]) != (expected["phase"], expected["seed"])
            or sha(path) != resumed["protocol_sha256"]):
        raise RuntimeError("Training attempt already locked with different data or recipe")

    original_worker = revision["historical_worker_sha256"]
    if previous != dict(expected, worker_sha256=original_worker):
        raise RuntimeError("A cache transition cannot change the sealed scientific protocol")
    verified_record(root, resumed["checkpoint"], resumed["checkpoint_sha256"])
    return previous
