"""Create an unlabelled review sidecar from a synthetic manifest; never change YOLO."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uchuva_lsystem.annotation_contract import instance_observation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "outputs").resolve()):
        parser.error("Output must be a derivative under outputs/.")
    if output.exists():
        parser.error("Output exists; use a new path to preserve review decisions.")
    content = args.manifest.read_bytes()
    fingerprint = hashlib.sha256(content).hexdigest()
    records = []
    for line in content.decode("utf-8-sig").splitlines():
        row = json.loads(line)
        if "scene_seed" not in row or not row.get("dataset_version"):
            raise ValueError("Expected a generated synthetic dataset manifest.")
        for detection in row["detections"]:
            record = instance_observation(detection, source_domain="synthetic")
            record.update(image_path=row["image_path"], scene_seed=row["scene_seed"],
                          split=row["split"], source_manifest_sha256=fingerprint)
            records.append(record)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"Prepared {len(records)} pending instance observations: {output}")


if __name__ == "__main__":
    main()
