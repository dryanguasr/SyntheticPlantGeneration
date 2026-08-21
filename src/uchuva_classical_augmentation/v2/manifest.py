"""Per-sample provenance manifests for reproducible derived images."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class DerivedSampleRecord:
    derived_image_id: str
    source_image_id: str
    source_sha256: str
    recipe_id: str
    recipe_version: str
    augmentation_seed: int
    transform_sequence: tuple[str, ...]
    transform_parameters: tuple[dict[str, Any], ...]
    source_labels: tuple[dict[str, Any], ...]
    output_labels: tuple[dict[str, Any], ...]
    bbox_visibility_changes: tuple[dict[str, Any], ...]
    source_domain_if_known: str | None
    output_sha256: str
    source_split: str = "train"
    status: str = "accepted"
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.source_domain_if_known is None:
            payload["source_domain_if_known"] = "unknown_not_available"
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DerivedSampleRecord":
        converted = dict(payload)
        if converted.get("source_domain_if_known") == "unknown_not_available":
            converted["source_domain_if_known"] = None
        for key in ("transform_sequence", "transform_parameters", "source_labels", "output_labels", "bbox_visibility_changes"):
            converted[key] = tuple(converted[key])
        return cls(**converted)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_jsonl(path: Path, records: Iterable[DerivedSampleRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[DerivedSampleRecord]:
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(DerivedSampleRecord.from_dict(json.loads(line)))
        except (TypeError, KeyError, json.JSONDecodeError) as error:
            raise ValueError(f"Invalid manifest record at {path}:{line_number}") from error
    return records


def verify_record_hashes(record: DerivedSampleRecord, *, source_path: Path, output_path: Path) -> None:
    if file_sha256(source_path) != record.source_sha256:
        raise ValueError(f"Source hash mismatch: {source_path}")
    if file_sha256(output_path) != record.output_sha256:
        raise ValueError(f"Output hash mismatch: {output_path}")
    if record.source_split != "train":
        raise ValueError(f"Derived sample has forbidden provenance split: {record.source_split}")
