"""Generate reproducible pure-Python baseline and ablation diagnostics."""

from __future__ import annotations

import argparse
import json
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_lsystem.cultivation import adapt_cultivation_morphologies
from uchuva_lsystem.exporters import export_json
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.metrics import (
    SceneMetricsReport,
    compute_scene_metrics,
    source_tree_fingerprint,
    write_metrics_bundle,
)
from uchuva_lsystem.parameters import (
    get_initial_parameters,
    get_morphology_parameters,
)
from uchuva_lsystem.provenance import (
    audit_parameter_provenance,
    normalise_parameter_provenance,
)
from uchuva_lsystem.scene import create_cultivation_scene


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate morphology-first baseline diagnostics without Blender."
    )
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--seed-count", type=int, default=10)
    parser.add_argument("--plant-count", type=int, default=20)
    parser.add_argument(
        "--preset",
        default=None,
        choices=(
            "single_plant_study",
            "foreground_plant_with_neighbors",
            "annotation_foreground_pilot",
            "row_canopy",
            "dense_staked_crop",
            "dense_trellis_synchronous",
        ),
    )
    parser.add_argument(
        "--model-variant",
        default="A_baseline_independent",
        choices=(
            "A_baseline_independent",
            "B_morphology_calibrated",
            "C_plus_structural_support",
            "D_plus_synchronous_multi_plant",
            "E_plus_contact_policy_clearance",
            "F_plus_space_colonization_optional",
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.seed_count < 1:
        raise ValueError("--seed-count must be at least 1")
    active_preset = args.preset or (
        "dense_staked_crop"
        if args.model_variant == "A_baseline_independent"
        else "dense_trellis_synchronous"
    )
    output_dir = args.output_dir or (
        REPO_ROOT
        / "outputs"
        / "diagnostics"
        / f"{args.model_variant}_seeds_{args.seed_start}_{args.seed_start + args.seed_count - 1}"
    )
    output_dir = output_dir if output_dir.is_absolute() else REPO_ROOT / output_dir
    fingerprint = source_tree_fingerprint(REPO_ROOT)
    parameters = normalise_parameter_provenance(
        get_initial_parameters()
        if args.model_variant == "A_baseline_independent"
        else get_morphology_parameters("trained_trellis")
    )
    provenance_report = audit_parameter_provenance(parameters)
    reports: list[SceneMetricsReport] = []
    failures: list[dict[str, Any]] = []

    for seed in range(args.seed_start, args.seed_start + args.seed_count):
        try:
            report, scene_payload = _generate_seed_report(
                seed=seed,
                plant_count=args.plant_count,
                preset=active_preset,
                model_variant=args.model_variant,
                parameters=parameters,
                fingerprint=fingerprint,
            )
        except Exception as error:
            failures.append(
                {
                    "seed": seed,
                    "type": type(error).__name__,
                    "message": str(error),
                }
            )
            continue
        reports.append(report)
        seed_dir = output_dir / f"seed_{seed}"
        export_json(report, seed_dir / "metrics.json")
        export_json(scene_payload, seed_dir / "scene_summary.json")

    paths = write_metrics_bundle(reports, output_dir)
    experiment = {
        "schema_version": "1.0",
        "model_variant": args.model_variant,
        "preset": active_preset,
        "seed_start": args.seed_start,
        "seed_count_requested": args.seed_count,
        "seed_count_completed": len(reports),
        "plant_count_requested": args.plant_count,
        "source_fingerprint": fingerprint,
        "parameter_provenance": provenance_report,
        "failures": failures,
        "artifacts": {key: str(path) for key, path in paths.items()},
    }
    export_json(experiment, output_dir / "experiment.json")
    print(json.dumps(experiment, ensure_ascii=False, indent=2))
    if failures:
        raise RuntimeError(f"{len(failures)} diagnostic seeds failed")


def _generate_seed_report(
    *,
    seed: int,
    plant_count: int,
    preset: str,
    model_variant: str,
    parameters: dict[str, Any],
    fingerprint: str,
) -> tuple[SceneMetricsReport, dict[str, Any]]:
    tracemalloc.start()
    started = time.perf_counter()
    scene = create_cultivation_scene(
        seed=seed,
        preset_name=preset,
        plant_count=plant_count,
        collision_policy="canopy_permissive",
    )
    plants = {
        instance.plant_id: generate_morphology_tree(
            seed=instance.seed,
            params=parameters,
            condition=instance.condition,
        )
        for instance in scene.plant_instances
    }
    if model_variant == "A_baseline_independent":
        scene, plants, adaptation = adapt_cultivation_morphologies(scene, plants)
    else:
        from uchuva_lsystem.cultivation import generate_cultivation_morphologies

        scene, plants, adaptation = generate_cultivation_morphologies(
            scene,
            parameters,
            model_variant=model_variant,
            potential_plants=plants,
        )
    elapsed = time.perf_counter() - started
    _, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    scene.metadata["cultivation_adaptation"] = adaptation
    performance = {
        "elapsed_seconds": round(elapsed, 6),
        "peak_memory_bytes": int(peak_memory),
    }
    report = compute_scene_metrics(
        scene,
        plants,
        model_variant=model_variant,
        performance=performance,
        source_fingerprint=fingerprint,
    )
    summary = {
        "scene_id": scene.scene_id,
        "seed": seed,
        "preset": preset,
        "model_variant": model_variant,
        "plant_ids": sorted(plants),
        "performance": performance,
        "cultivation_adaptation": adaptation,
    }
    return report, summary


if __name__ == "__main__":
    main()
