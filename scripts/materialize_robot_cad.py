"""Download authenticated CAD copies from a private, ephemeral download manifest.

No Drive credentials or signed URLs belong in Git. The input is generated from
the connected Drive tool; the output inventory deliberately excludes URLs.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path, PurePosixPath
import urllib.request


def materialize(entry: dict, root: Path) -> dict:
    relative = PurePosixPath(entry["path"])
    if relative.is_absolute() or any(p in ("..", ".") or ":" in p or "\\" in p for p in relative.parts):
        raise ValueError("Unsafe relative CAD path")
    target = root.joinpath(*relative.parts).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"CAD path escapes output directory: {target!s} (root {root!s})")
    record = {k: v for k, v in entry.items() if k not in ("download_url", "file_uri")}
    expected = int(entry["size"])
    if target.exists():
        # Equal byte length does not prove either content or Drive revision.
        # Preserve the file and require a fresh destination for materializing.
        record.update(status="existing_unverified")
        return record
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".download")
        try:
            with urllib.request.urlopen(entry["download_url"], timeout=120) as response, temporary.open("xb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            if temporary.stat().st_size != expected:
                raise ValueError("Downloaded size differs from Drive metadata")
            temporary.replace(target)
        except Exception as error:
            record.update(status="download_failed", error_type=type(error).__name__)
            # Exception strings can include signed URLs, so do not persist them.
            return record
    if target.stat().st_size != expected:
        record.update(status="existing_size_conflict")
        return record
    with target.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    record.update(status="downloaded", sha256=digest)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    entries = json.loads(args.manifest.read_text(encoding="utf-8"))["files"]
    if len({entry["path"].casefold() for entry in entries}) != len(entries):
        raise ValueError("Duplicate target paths in CAD download manifest")
    if args.report.exists():
        raise ValueError("Use a new report path; preserve earlier download evidence")
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 8))) as pool:
        records = list(pool.map(lambda item: materialize(item, root), entries))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"schema_version": "cad-download/1.0", "files": records}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = sum(r["status"] != "downloaded" for r in records)
    print(json.dumps({"downloaded": len(records) - failed, "failed": failed, "report": str(args.report)}))
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
