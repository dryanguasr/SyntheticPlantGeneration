"""Audit 100 pure-Python v2 morphology seeds without importing Blender."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.blender_dataset import _morphology_params_for_target
from uchuva_lsystem.validation import validate_morphology_tree


PROFILES = ("mixed_early", "mixed_balanced", "mixed_late")
AREA_BANDS = (
    "under_one_percent",
    "one_to_five_percent",
    "at_least_five_percent",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-start", type=int, default=14000)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "outputs" / "audits" / "literature_cohort_v1_100_seeds",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = args.output_dir.resolve()
    morphology_dir = output / "morphologies"
    validation_dir = output / "validations"
    morphology_dir.mkdir(parents=True, exist_ok=True)
    validation_dir.mkdir(parents=True, exist_ok=True)
    records = []
    critical_totals: Counter[str] = Counter()
    for offset in range(args.count):
        seed = args.seed_start + offset
        profile = PROFILES[offset % len(PROFILES)]
        area_band = AREA_BANDS[offset % len(AREA_BANDS)]
        params = _morphology_params_for_target(
            {
                "object_count_band": "one_to_five",
                "box_area_band": area_band,
            }
        )
        plant = generate_morphology_tree(
            seed,
            params=params,
            phenology_profile=profile,
            phenology_model="literature_cohort_v1",
        )
        validation = validate_morphology_tree(plant)
        critical = _critical_failures(plant, validation)
        critical_totals.update(critical)
        morphology_path = morphology_dir / f"morphology_seed_{seed}.json"
        validation_path = validation_dir / f"validation_seed_{seed}.json"
        _write_json(morphology_path, plant.to_dict())
        _write_json(validation_path, validation)
        records.append(
            {
                "seed": seed,
                "phenology_profile": profile,
                "box_area_band": area_band,
                "morphology_path": str(morphology_path.relative_to(output)),
                "validation_path": str(validation_path.relative_to(output)),
                "critical_failures": critical,
                "phenology": validation["summary"]["phenology"],
                "general_warning_count": len(validation["warnings"]),
            }
        )
    report = {
        "version": "1.0.0-literature-cohort-pure-audit",
        "status": "valid" if not critical_totals else "invalid",
        "seed_start": args.seed_start,
        "seed_count": args.count,
        "phenology_model": "literature_cohort_v1",
        "critical_failure_totals": dict(sorted(critical_totals.items())),
        "critical_contract": [
            "leaf_attached_to_own_node",
            "reproductive_unit_attached_to_own_node",
            "pedicel_connects_axil_to_unit",
            "fruit_requires_closed_calyx",
            "fruit_remains_hidden",
            "major_phenology_inversion_count_zero",
            "first_bifurcation_within_8_to_12_nodes",
        ],
        "general_warning_policy": (
            "Noncritical light/cultivation warnings are retained but do not fail this pure morphology audit."
        ),
        "records": records,
    }
    _write_json(output / "audit_report.json", report)
    print(output / "audit_report.json")
    if report["status"] != "valid":
        raise RuntimeError(f"Critical morphology failures: {dict(critical_totals)}")


def _critical_failures(plant: Any, validation: dict[str, Any]) -> dict[str, int]:
    failures: Counter[str] = Counter()
    snapshot = plant.metadata.get("phenology_snapshot", {})
    threshold = int(snapshot.get("first_bifurcation_node", 0))
    if threshold < 8 or threshold > 12:
        failures["first_bifurcation_threshold_out_of_range"] += 1

    def visit(axis: Any, *, main_axis: bool = False) -> None:
        node_positions = {node.id: node.position_index + 1 for node in axis.nodes}
        for node in axis.nodes:
            if node.leaf is not None and node.leaf.node_id != node.id:
                failures["leaf_without_own_node"] += 1
            unit = node.reproductive_unit
            if unit is None:
                continue
            if unit.node_id != node.id:
                failures["reproductive_unit_without_own_node"] += 1
            if unit.pedicel.node_id != node.id:
                failures["pedicel_wrong_axil"] += 1
            if unit.pedicel.connects_to != unit.id:
                failures["pedicel_broken_destination"] += 1
            if unit.fruit is not None and unit.calyx is None:
                failures["fruit_without_calyx"] += 1
            if unit.calyx is not None and unit.calyx.openness > 0.001:
                failures["open_calyx"] += 1
            if unit.fruit is not None and unit.fruit.visibility != "hidden":
                failures["visible_hidden_fruit"] += 1
        if main_axis:
            for child in axis.child_axes:
                position = node_positions.get(child.parent_node_id)
                if position is not None and position < threshold:
                    failures["branch_before_first_bifurcation"] += 1
        for child in axis.child_axes:
            visit(child)

    for root_axis in plant.axes:
        visit(root_axis, main_axis=True)
    inversions = int(validation["summary"]["phenology"]["severe_inversion_count"])
    if inversions:
        failures["major_phenology_inversion"] += inversions
    return dict(sorted(failures.items()))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
