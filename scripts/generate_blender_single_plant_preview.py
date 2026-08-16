"""Generate a Blender .blend preview from the uchuva morphology tree."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_lsystem.blender_geometry import build_geometry_from_morphology
from uchuva_lsystem.blender_scene import (
    cleanup_scene,
    create_project_materials,
    save_blend_file,
    setup_camera_and_lights,
    setup_render_settings,
)
from uchuva_lsystem.exporters import export_json, export_morphology_tree
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.validation import validate_morphology_tree


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an uchuva L-System morphology preview as .blend."
    )
    parser.add_argument("--seed", type=int, default=0, help="Reproducible seed.")
    parser.add_argument(
        "--condition",
        choices=("healthy", "drying"),
        default="healthy",
        help="Whole-plant stem/health condition.",
    )
    parser.add_argument(
        "--output-blend",
        type=Path,
        default=None,
        help="Output .blend path.",
    )
    parser.add_argument(
        "--morphology-output",
        type=Path,
        default=None,
        help="Output morphology JSON path.",
    )
    parser.add_argument(
        "--validation-output",
        type=Path,
        default=None,
        help="Output validation JSON path.",
    )
    return parser.parse_args(_argv_after_blender_separator())


def main() -> None:
    args = parse_args()
    output_blend = args.output_blend or (
        REPO_ROOT / "outputs" / "blends" / f"uchuva_lsystem_seed_{args.seed}.blend"
    )
    morphology_output = args.morphology_output or (
        REPO_ROOT / "outputs" / "specs" / f"morphology_tree_seed_{args.seed}.json"
    )
    validation_output = args.validation_output or (
        REPO_ROOT / "outputs" / "specs" / f"validation_report_seed_{args.seed}.json"
    )

    plant = generate_morphology_tree(seed=args.seed, condition=args.condition)
    validation_report = validate_morphology_tree(plant)
    export_morphology_tree(plant, morphology_output)
    export_json(validation_report, validation_output)

    cleanup_scene()
    materials = create_project_materials(seed=args.seed + 2000)
    geometry_report = build_geometry_from_morphology(plant, materials)
    setup_camera_and_lights(
        plant_height=geometry_report["height"],
        target=geometry_report["target"],
    )
    setup_render_settings()
    save_blend_file(output_blend)

    print(f"Wrote morphology tree: {morphology_output}")
    print(f"Wrote validation report: {validation_output}")
    print(f"Wrote Blender file: {output_blend}")
    print(f"Geometry report: {geometry_report}")
    print(f"Validation status: {validation_report['status']}")


def _argv_after_blender_separator() -> list[str]:
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1 :]


if __name__ == "__main__":
    main()
