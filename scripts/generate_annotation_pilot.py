"""Generate the small contextual uchuva annotation pilot in Blender."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_lsystem.blender_pilot import generate_annotation_pilot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate one contextual, annotation-ready uchuva pilot scene."
    )
    parser.add_argument("--seed", type=int, default=0, help="First seed in the deterministic 20-seed search.")
    parser.add_argument("--plant-count", type=int, default=20, choices=range(1, 21))
    parser.add_argument(
        "--neighbor-count",
        type=int,
        default=None,
        choices=range(0, 20),
        help="Compatibility alias; when provided it overrides --plant-count.",
    )
    parser.add_argument("--asset-dir", type=Path, default=REPO_ROOT / "outputs" / "assets_cache" / "polyhaven")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--output-blend", type=Path, default=None)
    parser.add_argument(
        "--profiles",
        nargs="+",
        default=["robot_close_oblique", "human_oblique_mid", "context_wide"],
        choices=[
            "robot_close_oblique",
            "human_oblique_mid",
            "context_wide",
            "real_close",
            "real_mid",
            "real_context",
        ],
    )
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=960)
    parser.add_argument("--cycles-samples", type=int, default=64)
    parser.add_argument("--skip-rgb", action="store_true")
    cycles = parser.add_mutually_exclusive_group()
    cycles.add_argument(
        "--render-cycles",
        action="store_true",
        dest="render_cycles",
        help="Opt in to the costly Cycles comparison render.",
    )
    cycles.add_argument(
        "--skip-cycles",
        action="store_false",
        dest="render_cycles",
        help="Backward-compatible no-op; Cycles is already disabled by default.",
    )
    parser.set_defaults(render_cycles=False)
    parser.add_argument("--allow-physical-collision", action="store_true")
    return parser.parse_args(_argv_after_blender_separator())


def main() -> None:
    args = parse_args()
    output_dir = _repo_path(args.output_dir) if args.output_dir else (
        REPO_ROOT / "outputs" / "pilots" / f"uchuva_annotation_seed_{args.seed}"
    )
    output_blend = _repo_path(args.output_blend) if args.output_blend else (
        REPO_ROOT / "outputs" / "blends" / f"uchuva_annotation_pilot_seed_{args.seed}.blend"
    )
    asset_dir = _repo_path(args.asset_dir)
    report = generate_annotation_pilot(
        seed_start=args.seed,
        plant_count=args.plant_count,
        neighbor_count=args.neighbor_count,
        output_dir=output_dir,
        output_blend=output_blend,
        asset_dir=asset_dir,
        camera_profiles=args.profiles,
        width=args.width,
        height=args.height,
        cycles_samples=args.cycles_samples,
        render_rgb=not args.skip_rgb,
        render_cycles=args.render_cycles,
        fail_on_physical_collision=not args.allow_physical_collision,
    )
    print(f"Selected seed: {report['selected_seed']}")
    print(f"Annotation validation: {report['annotation_validation']['status']}")
    print(f"Wrote pilot directory: {output_dir}")
    print(f"Wrote portable Blender scene: {output_blend}")


def _argv_after_blender_separator() -> list[str]:
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1 :]


def _repo_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


if __name__ == "__main__":
    main()
