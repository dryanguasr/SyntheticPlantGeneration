"""Verify the attributed upstream snapshot without Git or external libraries."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath

ROOT = Path(__file__).resolve().parents[1]


def verify_snapshot(root: Path) -> dict:
    provenance = json.loads((root / "contributions/physalisharvest.provenance.json").read_text(encoding="utf-8"))
    snapshot = root / "contributions/physalisharvest"
    failures = []
    for entry in provenance["files"]:
        relative = PurePosixPath(entry["path"])
        if (relative.is_absolute() or PureWindowsPath(entry["path"]).drive
                or ".." in relative.parts or "\\" in entry["path"]):
            raise ValueError("Snapshot manifest contains an unsafe path")
        path = snapshot / relative
        if not path.is_file() or path.is_symlink():
            failures.append({"path": entry["path"], "reason": "missing_or_not_regular_file"})
            continue
        payload = path.read_bytes()
        if entry["comparison"] == "utf8_lf":
            payload = payload.replace(b"\r\n", b"\n")
        if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            failures.append({"path": entry["path"], "reason": "content_mismatch"})
    return {"schema_version": "physalisharvest-snapshot-verification/1.0",
            "upstream_commit": provenance["upstream_commit"],
            "expected_files": len(provenance["files"]),
            "status": "FAIL" if failures else "PASS", "failures": failures,
            "scope": "Preserved upstream files only; no ROS, firmware or hardware execution."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = verify_snapshot(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
