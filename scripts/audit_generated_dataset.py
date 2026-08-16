"""Audit integrity, split isolation, and annotation invariants of a generated dataset."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path
from typing import Any


PATH_HASH_FIELDS = {
    "image_path": "image_sha256",
    "label_path": "label_sha256",
    "preview_path": "preview_sha256",
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_dataset(root: Path) -> dict[str, Any]:
    records = _read_jsonl(root / "manifest.jsonl")
    report = json.loads((root / "dataset_report.json").read_text(encoding="utf-8"))
    rejected = _read_jsonl(root / "rejected_scenes.jsonl")

    errors: list[str] = []
    missing_files: list[dict[str, Any]] = []
    hash_mismatches: list[dict[str, Any]] = []
    invalid_yolo_lines: list[dict[str, Any]] = []
    label_detection_mismatches: list[dict[str, Any]] = []
    manifest_paths = {field: set() for field in PATH_HASH_FIELDS}
    hashes: dict[str, dict[str, list[dict[str, str]]]] = {
        hash_field: collections.defaultdict(list)
        for hash_field in PATH_HASH_FIELDS.values()
    }
    split_counts: collections.Counter[str] = collections.Counter()
    split_image_hashes: dict[str, set[str]] = collections.defaultdict(set)
    yolo_class_ids: set[int] = set()
    yolo_label_lines = 0

    for row_index, record in enumerate(records):
        split = str(record.get("split", ""))
        split_counts[split] += 1
        for path_field, hash_field in PATH_HASH_FIELDS.items():
            relative_path = str(record.get(path_field, ""))
            manifest_paths[path_field].add(relative_path)
            path = root / relative_path
            if not path.is_file():
                missing_files.append(
                    {"row": row_index, "field": path_field, "path": relative_path}
                )
                continue
            actual_hash = _sha256(path)
            expected_hash = str(record.get("checksums", {}).get(hash_field, ""))
            hashes[hash_field][actual_hash].append(
                {"split": split, "path": relative_path}
            )
            if hash_field == "image_sha256":
                split_image_hashes[split].add(actual_hash)
            if actual_hash != expected_hash:
                hash_mismatches.append(
                    {
                        "row": row_index,
                        "field": path_field,
                        "actual": actual_hash,
                        "expected": expected_hash,
                    }
                )

        label_path = root / str(record.get("label_path", ""))
        if label_path.is_file():
            label_lines = [
                line.strip()
                for line in label_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            yolo_label_lines += len(label_lines)
            detections = record.get("detections", [])
            if len(label_lines) != len(detections):
                label_detection_mismatches.append(
                    {
                        "row": row_index,
                        "labels": len(label_lines),
                        "detections": len(detections),
                    }
                )
            for line_number, line in enumerate(label_lines, start=1):
                parts = line.split()
                reason = ""
                if len(parts) != 5:
                    reason = "token_count"
                else:
                    try:
                        class_id = int(parts[0])
                        values = [float(value) for value in parts[1:]]
                        yolo_class_ids.add(class_id)
                        _, _, width, height = values
                        if (
                            class_id != 0
                            or not all(0.0 <= value <= 1.0 for value in values)
                            or width <= 0.0
                            or height <= 0.0
                        ):
                            reason = "range_or_class"
                    except ValueError:
                        reason = "parse"
                if reason:
                    invalid_yolo_lines.append(
                        {
                            "path": str(label_path.relative_to(root)),
                            "line": line_number,
                            "reason": reason,
                            "value": line,
                        }
                    )

        for detection in record.get("detections", []):
            if detection.get("class_id") != 0 or detection.get("class_name") != "calyx":
                errors.append(f"Manifest class mismatch at row {row_index}.")
            values = detection.get("yolo_xywh", [])
            if (
                len(values) != 4
                or not all(0.0 <= float(value) <= 1.0 for value in values)
                or float(values[2]) <= 0.0
                or float(values[3]) <= 0.0
            ):
                errors.append(f"Manifest bounding box invalid at row {row_index}.")

    actual_paths = {
        "image_path": {
            str(path.relative_to(root)).replace("\\", "/")
            for path in (root / "images").rglob("*")
            if path.is_file()
        },
        "label_path": {
            str(path.relative_to(root)).replace("\\", "/")
            for path in (root / "labels").rglob("*")
            if path.is_file()
        },
        "preview_path": {
            str(path.relative_to(root)).replace("\\", "/")
            for path in (root / "previews").rglob("*")
            if path.is_file()
        },
    }
    duplicate_hashes = {
        hash_field: [entries for entries in groups.values() if len(entries) > 1]
        for hash_field, groups in hashes.items()
    }
    indices = [int(record.get("scene_index", -1)) for record in records]
    capture_seeds = [record.get("capture_seed") for record in records]
    scene_seeds = [record.get("scene_seed") for record in records]
    scene_ids = [record.get("scene_id") for record in records]
    expected_indices = list(range(len(records)))
    split_pairs = (("train", "val"), ("train", "test"), ("val", "test"))
    cross_split_hash_overlap = {
        f"{left}-{right}": len(split_image_hashes[left] & split_image_hashes[right])
        for left, right in split_pairs
    }
    rejected_reasons = collections.Counter(
        str(item.get("reason", "unknown")) for item in rejected
    )
    rejected_camera_reasons: collections.Counter[str] = collections.Counter()
    for item in rejected:
        for diagnostic in item.get("details", {}).get("capture_diagnostics", []):
            rejected_camera_reasons.update(
                str(reason) for reason in diagnostic.get("reasons", [])
            )

    audit_errors = errors.copy()
    if missing_files:
        audit_errors.append(f"Found {len(missing_files)} missing files.")
    if hash_mismatches:
        audit_errors.append(f"Found {len(hash_mismatches)} checksum mismatches.")
    if invalid_yolo_lines:
        audit_errors.append(f"Found {len(invalid_yolo_lines)} invalid YOLO lines.")
    if label_detection_mismatches:
        audit_errors.append(
            f"Found {len(label_detection_mismatches)} label/detection count mismatches."
        )
    if sorted(indices) != expected_indices or len(set(indices)) != len(records):
        audit_errors.append("Scene indices are not an exact unique contiguous sequence.")
    if len(set(capture_seeds)) != len(records):
        audit_errors.append("Capture seeds are not unique.")
    if len(set(scene_seeds)) != len(records):
        audit_errors.append("Accepted scene seeds are not unique.")
    if any(cross_split_hash_overlap.values()):
        audit_errors.append("Image hashes overlap across splits.")
    for field in PATH_HASH_FIELDS:
        if actual_paths[field] != manifest_paths[field]:
            audit_errors.append(f"Manifest and filesystem paths differ for {field}.")

    return {
        "audit_version": "1.0.0",
        "status": "valid" if not audit_errors else "invalid",
        "errors": audit_errors,
        "manifest_rows": len(records),
        "split_counts": dict(split_counts),
        "actual_file_counts": {
            field: len(paths) for field, paths in actual_paths.items()
        },
        "path_unique_counts": {
            field: len(paths) for field, paths in manifest_paths.items()
        },
        "scene_index_min_max": [min(indices), max(indices)] if indices else [],
        "scene_index_unique": len(set(indices)),
        "scene_index_sequence_exact": sorted(indices) == expected_indices,
        "capture_seed_unique": len(set(capture_seeds)),
        "accepted_scene_seed_unique": len(set(scene_seeds)),
        "scene_id_unique": len(set(scene_ids)),
        "missing_file_count": len(missing_files),
        "checksum_mismatch_count": len(hash_mismatches),
        "duplicate_hash_groups": {
            field: len(groups) for field, groups in duplicate_hashes.items()
        },
        "duplicate_files_in_hash_groups": {
            field: sum(len(group) for group in groups)
            for field, groups in duplicate_hashes.items()
        },
        "cross_split_image_hash_overlap": cross_split_hash_overlap,
        "yolo": {
            "label_lines": yolo_label_lines,
            "class_ids": sorted(yolo_class_ids),
            "invalid_line_count": len(invalid_yolo_lines),
            "label_detection_count_mismatch_count": len(label_detection_mismatches),
            "manifest_class_or_bbox_error_count": len(errors),
        },
        "morphology_and_visibility": {
            "physical_collision_count": sum(
                int(record.get("physical_collision_count", 0)) for record in records
            ),
            "open_calyx_count": sum(
                int(record.get("open_calyx_count", 0)) for record in records
            ),
            "visible_hidden_fruit_count": sum(
                int(record.get("visible_hidden_fruit_count", 0)) for record in records
            ),
            "unknown_visible_reproductive_instance_count": sum(
                int(record.get("unknown_visible_reproductive_instance_count", 0))
                for record in records
            ),
        },
        "accepted_detection_count": sum(
            int(record.get("accepted_detection_count", 0)) for record in records
        ),
        "qa_cycles_path_count": sum(
            bool(record.get("qa_cycles_path")) for record in records
        ),
        "generator_report": {
            "status": report.get("status"),
            "errors": report.get("errors"),
            "warnings": report.get("warnings"),
        },
        "rejections": {
            "candidate_count": len(rejected),
            "scene_reasons": dict(rejected_reasons),
            "camera_retry_reasons": dict(rejected_camera_reasons),
        },
        "descriptors": {
            "data_yaml": (root / "data.yaml").read_text(encoding="utf-8"),
            "labels_txt": (root / "labels.txt").read_text(encoding="utf-8"),
        },
        "diagnostic_samples": {
            "missing_files": missing_files[:5],
            "hash_mismatches": hash_mismatches[:5],
            "invalid_yolo_lines": invalid_yolo_lines[:5],
            "label_detection_mismatches": label_detection_mismatches[:5],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit_dataset(args.dataset_root.resolve())
    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    raise SystemExit(0 if result["status"] == "valid" else 1)


if __name__ == "__main__":
    main()
