"""Run and summarize the fixed A--F pure-Python ablation matrix."""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
VARIANTS = (
    "A_baseline_independent",
    "B_morphology_calibrated",
    "C_plus_structural_support",
    "D_plus_synchronous_multi_plant",
    "E_plus_contact_policy_clearance",
    "F_plus_space_colonization_optional",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--seed-count", type=int, default=30)
    parser.add_argument(
        "--variants",
        nargs="+",
        choices=VARIANTS,
        default=list(VARIANTS),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "outputs" / "ablations",
    )
    parser.add_argument("--skip-existing", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_root = (
        args.output_dir
        if args.output_dir.is_absolute()
        else REPO_ROOT / args.output_dir
    ).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    reports: dict[str, list[dict[str, Any]]] = {}
    for variant in args.variants:
        variant_dir = output_root / variant
        metrics_path = variant_dir / "scene_metrics.json"
        if not (args.skip_existing and metrics_path.exists()):
            command = [
                sys.executable,
                str(
                    REPO_ROOT
                    / "scripts"
                    / "generate_morphology_diagnostics.py"
                ),
                "--seed-start",
                str(args.seed_start),
                "--seed-count",
                str(args.seed_count),
                "--model-variant",
                variant,
                "--output-dir",
                str(variant_dir),
            ]
            subprocess.run(command, cwd=REPO_ROOT, check=True)
        reports[variant] = json.loads(metrics_path.read_text(encoding="utf-8"))
    summary = _summarize(reports)
    json_path = output_root / "ablation_summary.json"
    markdown_path = output_root / "ablation_summary.md"
    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    markdown_path.write_text(
        _markdown(summary),
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")


def _summarize(
    reports: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    variants: dict[str, Any] = {}
    for variant, items in reports.items():
        variants[variant] = {
            "seed_count": len(items),
            "axes_per_plant": _summary(
                item["morphology"]["axes_per_plant"] for item in items
            ),
            "long_axes_without_children_fraction": _summary(
                item["morphology"]["long_axes_without_children_fraction"]
                for item in items
            ),
            "leaf_length_cm_median": _summary(
                item["morphology"]["leaf_length_cm"]["median"]
                for item in items
            ),
            "normalized_posthoc_adjustments": _summary(
                item["adjustments"].get("count", 0)
                / max(
                    sum(
                        item["morphology"]["organ_counts"].get(key, 0)
                        for key in ("axes", "leaves", "reproductive_units")
                    ),
                    1,
                )
                for item in items
            ),
            "coverage_fraction": _summary(
                item.get("projected_2d", {}).get("coverage_fraction", 0.0)
                for item in items
            ),
            "mixed_cell_fraction": _summary(
                item.get("projected_2d", {}).get("mixed_cell_fraction", 0.0)
                for item in items
            ),
            "elapsed_seconds": _summary(
                item.get("performance", {}).get("elapsed_seconds", 0.0)
                for item in items
            ),
        }
    acceptance: dict[str, Any] = {
        "baseline_available": "A_baseline_independent" in reports,
        "final_available": "E_plus_contact_policy_clearance" in reports,
        "projective_reference_acceptance": (
            "pending_camera_matched_Blender_measurements"
        ),
        "mesh_acceptance": "pending_BVH_runs_for_10_fixed_seeds",
    }
    if (
        "E_plus_contact_policy_clearance" in variants
        and "A_baseline_independent" in variants
    ):
        baseline_time = variants["A_baseline_independent"]["elapsed_seconds"][
            "median"
        ]
        final_time = variants[
            "E_plus_contact_policy_clearance"
        ]["elapsed_seconds"]["median"]
        ratio = (
            final_time / baseline_time
            if baseline_time not in {None, 0.0}
            else None
        )
        acceptance["E_to_A_runtime_ratio"] = (
            round(ratio, 4) if ratio is not None else None
        )
        acceptance["E_runtime_over_2x_risk"] = (
            ratio is not None and ratio > 2.0
        )
    if (
        "F_plus_space_colonization_optional" in variants
        and "E_plus_contact_policy_clearance" in variants
    ):
        e_time = variants[
            "E_plus_contact_policy_clearance"
        ]["elapsed_seconds"]["median"]
        f_time = variants[
            "F_plus_space_colonization_optional"
        ]["elapsed_seconds"]["median"]
        ratio = f_time / e_time if e_time not in {None, 0.0} else None
        acceptance["F_to_E_runtime_ratio"] = (
            round(ratio, 4) if ratio is not None else None
        )
        acceptance["retain_F_runtime_gate"] = (
            ratio is not None and ratio <= 2.0
        )
    if acceptance["baseline_available"] and acceptance["final_available"]:
        baseline = {
            item["seed"]: item
            for item in reports["A_baseline_independent"]
        }
        final = {
            item["seed"]: item
            for item in reports["E_plus_contact_policy_clearance"]
        }
        common = sorted(set(baseline) & set(final))
        correction_wins = 0
        architecture_wins = 0
        leaf_not_increased = 0
        for seed in common:
            before = baseline[seed]
            after = final[seed]
            before_organs = max(
                sum(
                    before["morphology"]["organ_counts"].get(key, 0)
                    for key in ("axes", "leaves", "reproductive_units")
                ),
                1,
            )
            after_organs = max(
                sum(
                    after["morphology"]["organ_counts"].get(key, 0)
                    for key in ("axes", "leaves", "reproductive_units")
                ),
                1,
            )
            before_rate = before["adjustments"].get("count", 0) / before_organs
            after_rate = after["adjustments"].get("count", 0) / after_organs
            correction_wins += after_rate <= before_rate * 0.5
            architecture_wins += (
                after["morphology"]["axes_per_plant"]
                > before["morphology"]["axes_per_plant"]
                and after["morphology"]["long_axes_without_children_fraction"]
                < before["morphology"]["long_axes_without_children_fraction"]
            )
            leaf_not_increased += (
                after["morphology"]["leaf_length_cm"]["median"]
                <= before["morphology"]["leaf_length_cm"]["median"]
            )
        acceptance.update(
            {
                "common_seed_count": len(common),
                "correction_reduction_seed_count": correction_wins,
                "architecture_improvement_seed_count": architecture_wins,
                "leaf_not_increased_seed_count": leaf_not_increased,
                "correction_target_met": (
                    correction_wins >= min(7, len(common))
                ),
                "architecture_target_met": (
                    architecture_wins >= min(7, len(common))
                ),
            }
        )
    return {
        "schema_version": "1.0",
        "variants": variants,
        "acceptance": acceptance,
        "notes": [
            "No se combinan las métricas en una única puntuación.",
            "Las métricas proyectivas proxy no sustituyen la evaluación de cámara.",
            "La aceptación de malla requiere la auditoría Blender separada.",
        ],
    }


def _summary(values) -> dict[str, float | int | None]:
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return {"count": 0, "median": None, "mean": None, "min": None, "max": None}
    return {
        "count": len(numbers),
        "median": round(statistics.median(numbers), 6),
        "mean": round(statistics.fmean(numbers), 6),
        "min": round(min(numbers), 6),
        "max": round(max(numbers), 6),
    }


def _markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Resumen de ablaciones A–F",
        "",
        "| Variante | Semillas | Ejes/planta | Ejes largos sin hijas | Ajustes normalizados | Cobertura proxy | Tiempo (s) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, values in summary["variants"].items():
        lines.append(
            "| {name} | {count} | {axes} | {long_axes} | {adjustments} | {coverage} | {time} |".format(
                name=name,
                count=values["seed_count"],
                axes=values["axes_per_plant"]["median"],
                long_axes=values["long_axes_without_children_fraction"]["median"],
                adjustments=values["normalized_posthoc_adjustments"]["median"],
                coverage=values["coverage_fraction"]["median"],
                time=values["elapsed_seconds"]["median"],
            )
        )
    lines.extend(
        [
            "",
            "## Aceptación",
            "",
            "```json",
            json.dumps(
                summary["acceptance"],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
