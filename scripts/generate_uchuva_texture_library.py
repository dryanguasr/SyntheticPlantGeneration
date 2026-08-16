"""Generate the auditable uchuva leaf/calyx texture asset library."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_lsystem.texture_assets import (
    DEFAULT_TEXTURE_ASSET_DIR,
    generate_texture_asset_library,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate synthetic uchuva leaf and calyx texture maps."
    )
    parser.add_argument("--seed", type=int, default=1701, help="Reproducible seed.")
    parser.add_argument(
        "--resolution",
        type=int,
        default=512,
        help="Square map resolution in pixels (32 to 4096).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / DEFAULT_TEXTURE_ASSET_DIR,
        help="Destination directory for PNG maps and manifest.json.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = generate_texture_asset_library(
        args.output_dir,
        seed=args.seed,
        resolution=args.resolution,
    )
    print(f"Wrote {len(manifest['texture_sets'])} texture sets: {args.output_dir}")
    print(f"Preview: {args.output_dir / manifest['preview']}")


if __name__ == "__main__":
    main()
