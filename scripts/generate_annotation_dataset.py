"""Generate the deterministic real-matched uchuva YOLO/MakeSense pilot."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_lsystem.blender_dataset import DatasetConfig, generate_annotation_dataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate paired RGB and MakeSense-compatible YOLO annotations."
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--image-count", type=int, default=100)
    parser.add_argument("--captures-per-scene", type=int, default=1)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=960)
    parser.add_argument(
        "--cycles-qa-count",
        type=int,
        default=0,
        help="Optional Cycles QA renders; disabled by default.",
    )
    parser.add_argument("--cycles-samples", type=int, default=64)
    parser.add_argument("--neighbor-count-min", type=int, default=0)
    parser.add_argument("--neighbor-count-max", type=int, default=2)
    parser.add_argument("--max-seed-candidates", type=int, default=1000)
    parser.add_argument("--capture-pose-retries", type=int, default=8)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--output-blend",
        type=Path,
        default=None,
        help="Optional inspection Blend saved from the last accepted scene.",
    )
    parser.add_argument("--asset-dir", type=Path, default=None)
    parser.add_argument("--reference-profile", type=Path, default=None)
    parser.add_argument(
        "--reference-split",
        choices=("train", "val", "test", "overall"),
        default="train",
    )
    parser.add_argument("--composition-calibration", type=Path, default=None)
    parser.add_argument(
        "--phenology-model",
        choices=("literature_cohort_v1", "legacy_independent"),
        default="literature_cohort_v1",
    )
    parser.add_argument(
        "--background-style",
        choices=("layered_understory_v2", "legacy_green_carpet"),
        default="layered_understory_v2",
    )
    parser.add_argument(
        "--composition-profile",
        choices=("real_matched", "legacy_pilot"),
        default="real_matched",
    )
    parser.add_argument("--image-format", choices=("JPEG", "PNG"), default="JPEG")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--keep-masks", action="store_true")
    return parser.parse_args(_argv_after_blender_separator())


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir or (
        REPO_ROOT
        / "outputs"
        / "datasets"
        / f"uchuva_real_matched_pilot_seed_{args.seed}"
    )
    asset_dir = args.asset_dir or (
        REPO_ROOT / "outputs" / "assets_cache" / "polyhaven"
    )
    default_reference = (
        REPO_ROOT
        / "outputs"
        / "domain_analysis"
        / "real_vs_synthetic"
        / "domain_comparison.json"
    )
    reference_profile = args.reference_profile or (
        default_reference if default_reference.is_file() else None
    )
    config = DatasetConfig(
        output_dir=_resolve_repo_path(output_dir),
        seed=args.seed,
        image_count=args.image_count,
        captures_per_scene=args.captures_per_scene,
        width=args.width,
        height=args.height,
        cycles_qa_count=args.cycles_qa_count,
        cycles_samples=args.cycles_samples,
        neighbor_count_min=args.neighbor_count_min,
        neighbor_count_max=args.neighbor_count_max,
        max_seed_candidates=args.max_seed_candidates,
        capture_pose_retries=args.capture_pose_retries,
        asset_dir=_resolve_repo_path(asset_dir),
        reference_profile_path=(
            _resolve_repo_path(reference_profile) if reference_profile is not None else None
        ),
        reference_split=args.reference_split,
        composition_calibration_path=(
            _resolve_repo_path(args.composition_calibration)
            if args.composition_calibration is not None
            else None
        ),
        phenology_model=args.phenology_model,
        background_style=args.background_style,
        label_mode="calyx_single_class",
        composition_profile=args.composition_profile,
        image_format=args.image_format,
        resume=args.resume,
        keep_masks=args.keep_masks,
        inspection_blend_path=(
            _resolve_repo_path(args.output_blend)
            if args.output_blend is not None
            else None
        ),
    )
    report = generate_annotation_dataset(config)
    print(f"Dataset: {config.output_dir}")
    print(f"Status: {report['status']}")
    print(f"Images: {report['summary']['image_count']}")
    print(f"QA Cycles: {report['summary']['qa_cycles_count']}")


def _resolve_repo_path(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def _argv_after_blender_separator() -> list[str]:
    if "--" in sys.argv:
        return sys.argv[sys.argv.index("--") + 1 :]
    return sys.argv[1:]


if __name__ == "__main__":
    main()
