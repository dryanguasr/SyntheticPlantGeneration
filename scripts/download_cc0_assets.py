"""Download and verify the small CC0 asset set used by the pilot."""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_lsystem.blender_environment import ASSET_MANIFEST


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download the Poly Haven CC0 pilot assets.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "outputs" / "assets_cache" / "polyhaven",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for key, spec in ASSET_MANIFEST.items():
        destination = args.output_dir / spec["filename"]
        if destination.exists() and _md5(destination) == spec["md5"]:
            print(f"Verified existing {key}: {destination}")
            continue
        temporary = destination.with_suffix(destination.suffix + ".part")
        print(f"Downloading {key} from {spec['source_page']}")
        urllib.request.urlretrieve(spec["url"], temporary)
        digest = _md5(temporary)
        if digest != spec["md5"]:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(
                f"Checksum mismatch for {key}: expected {spec['md5']}, got {digest}."
            )
        temporary.replace(destination)
        print(f"Wrote {destination}")


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
