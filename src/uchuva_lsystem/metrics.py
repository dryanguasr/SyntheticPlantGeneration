"""Pure-Python morphology, canopy, and reproducibility metrics.

Metrics in this module are diagnostic engineering measures.  They are not
presented as validated botanical indicators unless their provenance explicitly
says otherwise.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .morphology import Axis, Plant
from .scene import CultivationScene


METRICS_VERSION = "0.1.0"


@dataclass
class SceneMetricsReport:
    """Serializable report shared by baseline and ablation commands."""

    scene_id: str
    seed: int
    model_variant: str
    morphology: dict[str, Any]
    canopy_3d: dict[str, Any]
    projected_2d: dict[str, Any] = field(default_factory=dict)
    contacts: dict[str, Any] = field(default_factory=dict)
    adjustments: dict[str, Any] = field(default_factory=dict)
    performance: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    source_fingerprint: str = ""
    version: str = METRICS_VERSION
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "seed": self.seed,
            "model_variant": self.model_variant,
            "morphology": self.morphology,
            "canopy_3d": self.canopy_3d,
            "projected_2d": self.projected_2d,
            "contacts": self.contacts,
            "adjustments": self.adjustments,
            "performance": self.performance,
            "provenance": self.provenance,
            "source_fingerprint": self.source_fingerprint,
            "version": self.version,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SceneMetricsReport":
        accepted = {
            "scene_id",
            "seed",
            "model_variant",
            "morphology",
            "canopy_3d",
            "projected_2d",
            "contacts",
            "adjustments",
            "performance",
            "provenance",
            "source_fingerprint",
            "version",
            "schema_version",
        }
        return cls(**{key: value for key, value in payload.items() if key in accepted})


def compute_morphology_metrics(plants_by_id: dict[str, Plant]) -> dict[str, Any]:
    """Compute structural measures for a set of plant morphology trees."""
    axis_lengths: dict[int, list[float]] = {}
    internode_lengths: dict[int, list[float]] = {}
    branch_angles: dict[int, list[float]] = {}
    child_counts: dict[int, list[int]] = {}
    node_density: dict[int, list[float]] = {}
    reproductive_fractions: dict[int, list[float]] = {}
    curvatures: dict[int, list[float]] = {}
    leaf_lengths: list[float] = []
    leaf_widths: list[float] = []
    petiole_lengths: list[float] = []
    leaf_insertions: list[float] = []
    leaf_to_internode: list[float] = []
    leaf_area_to_spacing_sq: list[float] = []
    leaf_light_interception: list[float] = []
    leaf_projected_coverage_gain: list[float] = []
    leaf_intraspecific_shading: list[float] = []
    leaf_interspecific_shading: list[float] = []
    leaves_by_stratum: dict[str, int] = {}
    calyx_to_leaf: list[float] = []
    branch_length_per_child: list[float] = []
    bud_states: dict[str, int] = {}
    long_axes_without_children = 0
    axes_with_children = 0
    organ_counts = {
        "plants": len(plants_by_id),
        "axes": 0,
        "internodes": 0,
        "nodes": 0,
        "leaves": 0,
        "axillary_buds": 0,
        "reproductive_units": 0,
        "flowers": 0,
        "fruits": 0,
        "calyxes": 0,
    }

    def visit_axis(axis: Axis) -> None:
        nonlocal long_axes_without_children, axes_with_children
        order = axis.order
        lengths = [item.length_cm for item in axis.internodes]
        total_length = sum(lengths)
        axis_lengths.setdefault(order, []).append(total_length)
        internode_lengths.setdefault(order, []).extend(lengths)
        branch_angles.setdefault(order, []).append(axis.branch_angle_deg)
        child_counts.setdefault(order, []).append(len(axis.child_axes))
        curvatures.setdefault(order, []).append(
            sum(abs(item.bend_angle_deg) for item in axis.internodes)
            / max(total_length, 1e-9)
        )
        node_density.setdefault(order, []).append(len(axis.nodes) / max(total_length, 1e-9))
        reproductive_count = sum(
            1 for node in axis.nodes if node.reproductive_unit is not None
        )
        reproductive_fractions.setdefault(order, []).append(
            reproductive_count / max(len(axis.nodes), 1)
        )
        branch_length_per_child.append(total_length / max(len(axis.child_axes), 1))
        if axis.child_axes:
            axes_with_children += 1
        if total_length >= 20.0 and not axis.child_axes:
            long_axes_without_children += 1
        organ_counts["axes"] += 1
        organ_counts["internodes"] += len(axis.internodes)
        organ_counts["nodes"] += len(axis.nodes)

        local_spacing = statistics.fmean(lengths) if lengths else 0.0
        for index, node in enumerate(axis.nodes):
            leaf = node.leaf
            if leaf is not None:
                organ_counts["leaves"] += 1
                leaf_lengths.append(leaf.length_cm)
                leaf_widths.append(leaf.width_cm)
                petiole_lengths.append(leaf.petiole_length_cm)
                leaf_insertions.append(leaf.insertion_angle_deg)
                leaves_by_stratum[leaf.canopy_stratum] = (
                    leaves_by_stratum.get(leaf.canopy_stratum, 0) + 1
                )
                if leaf.daily_light_interception_proxy is not None:
                    leaf_light_interception.append(
                        leaf.daily_light_interception_proxy
                    )
                if leaf.projected_coverage_gain is not None:
                    leaf_projected_coverage_gain.append(
                        leaf.projected_coverage_gain
                    )
                leaf_intraspecific_shading.append(
                    leaf.intraspecific_shading_fraction
                )
                leaf_interspecific_shading.append(
                    leaf.interspecific_shading_fraction
                )
                local_internode = lengths[index] if index < len(lengths) else local_spacing
                if local_internode > 0.0:
                    leaf_to_internode.append(leaf.length_cm / local_internode)
                if local_spacing > 0.0:
                    approximate_area = math.pi * leaf.length_cm * leaf.width_cm * 0.25
                    leaf_area_to_spacing_sq.append(
                        approximate_area / (local_spacing**2)
                    )
            bud = node.axillary_bud
            if bud is not None:
                organ_counts["axillary_buds"] += 1
                bud_states[bud.state] = bud_states.get(bud.state, 0) + 1
            unit = node.reproductive_unit
            if unit is not None:
                organ_counts["reproductive_units"] += 1
                if unit.stage == "flower":
                    organ_counts["flowers"] += 1
                if unit.fruit is not None:
                    organ_counts["fruits"] += 1
                if unit.calyx is not None:
                    organ_counts["calyxes"] += 1
                    if leaf is not None and leaf.length_cm > 0.0:
                        calyx_to_leaf.append(
                            (unit.calyx.radius_cm * 2.0) / leaf.length_cm
                        )
        for child in axis.child_axes:
            visit_axis(child)

    for plant_id in sorted(plants_by_id):
        for root_axis in plants_by_id[plant_id].axes:
            visit_axis(root_axis)

    total_buds = sum(bud_states.values())
    active_buds = sum(
        count for state, count in bud_states.items() if state != "dormant"
    )
    return {
        "organ_counts": organ_counts,
        "axes_by_order": _count_by_order(axis_lengths),
        "axis_length_cm_by_order": _summaries_by_order(axis_lengths),
        "internode_length_cm_by_order": _summaries_by_order(internode_lengths),
        "branch_angle_deg_by_order": _summaries_by_order(branch_angles),
        "child_branches_by_order": _summaries_by_order(child_counts),
        "node_density_per_cm_by_order": _summaries_by_order(node_density),
        "reproductive_node_fraction_by_order": _summaries_by_order(
            reproductive_fractions
        ),
        "curvature_deg_per_cm_by_order": _summaries_by_order(curvatures),
        "leaf_length_cm": _summary(leaf_lengths),
        "leaf_width_cm": _summary(leaf_widths),
        "petiole_length_cm": _summary(petiole_lengths),
        "leaf_insertion_angle_deg": _summary(leaf_insertions),
        "leaf_length_to_internode_length": _summary(leaf_to_internode),
        "leaf_area_to_local_branch_spacing_sq": _summary(
            leaf_area_to_spacing_sq
        ),
        "leaves_by_canopy_stratum": dict(sorted(leaves_by_stratum.items())),
        "daily_light_interception_proxy": _summary(
            leaf_light_interception
        ),
        "leaf_projected_coverage_gain": _summary(
            leaf_projected_coverage_gain
        ),
        "leaf_intraspecific_shading_fraction": _summary(
            leaf_intraspecific_shading
        ),
        "leaf_interspecific_shading_fraction": _summary(
            leaf_interspecific_shading
        ),
        "calyx_diameter_to_leaf_length": _summary(calyx_to_leaf),
        "branch_length_per_child_branch_cm": _summary(branch_length_per_child),
        "axes_per_plant": (
            organ_counts["axes"] / max(organ_counts["plants"], 1)
        ),
        "nodes_per_axis": (
            organ_counts["nodes"] / max(organ_counts["axes"], 1)
        ),
        "axes_with_children_fraction": (
            axes_with_children / max(organ_counts["axes"], 1)
        ),
        "long_axes_without_children_count": long_axes_without_children,
        "long_axes_without_children_fraction": (
            long_axes_without_children / max(organ_counts["axes"], 1)
        ),
        "long_axis_threshold_cm": 20.0,
        "bud_states": dict(sorted(bud_states.items())),
        "active_bud_fraction": active_buds / total_buds if total_buds else 0.0,
        "parameter_status": "engineering_heuristic",
    }


def compute_scene_metrics(
    scene: CultivationScene,
    plants_by_id: dict[str, Plant],
    *,
    model_variant: str,
    performance: dict[str, Any] | None = None,
    source_fingerprint: str = "",
    projected_2d: dict[str, Any] | None = None,
) -> SceneMetricsReport:
    """Compute morphology, coarse occupancy, contact, and adjustment metrics."""
    morphology = compute_morphology_metrics(plants_by_id)
    canopy = _compute_canopy_metrics(scene, plants_by_id)
    adaptation = scene.metadata.get("cultivation_adaptation", {})
    collision_report = adaptation.get("collision_resolution", {})
    if "proxy_conflicts" in collision_report:
        contact_audit = {
            "version": collision_report.get("version"),
            "counts": {
                "proxy_conflicts": len(
                    collision_report.get("proxy_conflicts", [])
                ),
                "clearance_violations": len(
                    collision_report.get("clearance_violations", [])
                ),
                "soft_occupancy_overlaps": len(
                    collision_report.get("soft_occupancy_overlaps", [])
                ),
                "intentional_contacts": len(
                    collision_report.get("intentional_contacts", [])
                ),
                "near_contacts": len(
                    collision_report.get("near_contacts", [])
                ),
                "visual_occlusions": len(
                    collision_report.get("visual_occlusions", [])
                ),
            },
            "strict_minimum_clearance": collision_report.get(
                "strict_minimum_clearance"
            ),
        }
    elif model_variant == "A_baseline_independent":
        contact_audit = {
            "version": collision_report.get("version"),
            "counts": {
                "proxy_conflicts": int(
                    collision_report.get("unresolved_pair_count", 0)
                ),
                "clearance_violations": 0,
                "soft_occupancy_overlaps": 0,
                "intentional_contacts": 0,
                "near_contacts": 0,
                "visual_occlusions": 0,
            },
            "strict_minimum_clearance": collision_report.get(
                "minimum_clearance"
            ),
            "mode": "legacy_report_compatibility",
        }
    else:
        try:
            from .collisions import audit_proxy_contacts

            contact_audit = audit_proxy_contacts(scene, plants_by_id)
        except (KeyError, ValueError):
            contact_audit = {
                "counts": {},
                "strict_minimum_clearance": None,
            }
    contact_counts = contact_audit.get("counts", {})
    contacts = {
        "proxy_conflicts": int(
            contact_counts.get(
                "proxy_conflicts",
                collision_report.get("unresolved_pair_count", 0),
            )
        ),
        "mesh_intersections": int(
            scene.metadata.get("mesh_collision_audit", {}).get(
                "physical_collision_count", 0
            )
        ),
        "clearance_violations": int(
            contact_counts.get(
                "clearance_violations",
                collision_report.get("clearance_violation_count", 0),
            )
        ),
        "soft_occupancy_overlaps": int(
            contact_counts.get("soft_occupancy_overlaps", 0)
        ),
        "intentional_contacts": max(
            int(contact_counts.get("intentional_contacts", 0)),
            (
                len(scene.support_system.contacts)
                if scene.support_system is not None
                else len(
                    scene.metadata.get("support_geometry", {}).get(
                        "intentional_contacts", []
                    )
                )
            ),
        ),
        "near_contacts": int(
            contact_counts.get(
                "near_contacts",
                collision_report.get("near_contact_count", 0),
            )
        ),
        "visual_occlusions": int(
            contact_counts.get("visual_occlusions", 0)
        ),
        "minimum_clearance": (
            contact_audit.get("strict_minimum_clearance")
            if contact_audit.get("strict_minimum_clearance") is not None
            else collision_report.get("minimum_clearance")
        ),
        "contact_policy_version": contact_audit.get("version"),
    }
    adjustments = compute_adjustment_metrics(
        collision_report.get("adjustments", [])
    )
    decisions = adaptation.get("decisions", [])
    if decisions:
        angular_changes = [
            float(item.get("angular_deviation_deg", 0.0))
            for item in decisions
        ]
        shortening = [
            1.0 - float(item.get("shortening_fraction", 1.0))
            for item in decisions
        ]
        adjustments["growth_decisions"] = {
            "count": len(decisions),
            "decision_counts": dict(adaptation.get("decision_counts", {})),
            "angular_deviation_deg": _summary(angular_changes),
            "shortening_fraction": _summary(shortening),
        }
        adjustments["posthoc_adjustment_count"] = adjustments["count"]
    active_projected = (
        dict(projected_2d)
        if projected_2d is not None
        else _compute_projected_proxy_metrics(scene, plants_by_id)
    )
    return SceneMetricsReport(
        scene_id=scene.scene_id,
        seed=scene.seed,
        model_variant=model_variant,
        morphology=morphology,
        canopy_3d=canopy,
        projected_2d=active_projected,
        contacts=contacts,
        adjustments=adjustments,
        performance=dict(performance or {}),
        provenance={
            "status": "engineering_heuristic",
            "note": (
                "Metrics diagnose morphology and scene composition; they are "
                "not validated botanical traits unless separately cited."
            ),
        },
        source_fingerprint=source_fingerprint,
    )


def compute_adjustment_metrics(
    adjustments: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    angular: dict[str, list[float]] = {}
    positional: dict[str, list[float]] = {}
    for item in adjustments:
        kind = str(item.get("control_kind", "unknown"))
        counts[kind] = counts.get(kind, 0) + 1
        before = item.get("before")
        after = item.get("after")
        if not (
            isinstance(before, (list, tuple))
            and isinstance(after, (list, tuple))
            and len(before) == len(after)
        ):
            continue
        if len(before) == 2:
            delta = abs(
                (float(after[0]) - float(before[0]) + 180.0) % 360.0 - 180.0
            )
            angular.setdefault(kind, []).append(delta)
        elif len(before) == 3:
            distance = math.sqrt(
                sum(
                    (float(after[index]) - float(before[index])) ** 2
                    for index in range(3)
                )
            )
            positional.setdefault(kind, []).append(distance)
    return {
        "count": sum(counts.values()),
        "count_by_control_kind": dict(sorted(counts.items())),
        "angular_change_deg_by_control_kind": {
            key: _summary(values) for key, values in sorted(angular.items())
        },
        "position_change_by_control_kind": {
            key: _summary(values) for key, values in sorted(positional.items())
        },
    }


def source_tree_fingerprint(repository_root: str | Path) -> str:
    """Hash source/configuration files without relying on Git history."""
    root = Path(repository_root)
    digest = hashlib.sha256()
    patterns = (
        "src/**/*.py",
        "scripts/*.py",
        "scripts/*.ps1",
        "tests/*.py",
        "AGENTS.md",
        "README.md",
        "docs/**/*.md",
        "docs/**/*.bib",
    )
    paths: set[Path] = set()
    for pattern in patterns:
        paths.update(path for path in root.glob(pattern) if path.is_file())
    for path in sorted(paths, key=lambda item: item.as_posix().lower()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def write_metrics_bundle(
    reports: list[SceneMetricsReport],
    output_directory: str | Path,
) -> dict[str, Path]:
    """Write JSON, CSV, and Markdown summaries for an experiment."""
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    payloads = [report.to_dict() for report in reports]
    json_path = output / "scene_metrics.json"
    json_path.write_text(
        json.dumps(payloads, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    rows = [_flatten_report(report) for report in reports]
    fieldnames = sorted({key for row in rows for key in row})
    csv_path = output / "scene_metrics.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    markdown_path = output / "scene_metrics.md"
    lines = [
        "# Métricas diagnósticas de escena",
        "",
        "Estas métricas son diagnósticas y no constituyen validación botánica.",
        "",
        "| Semilla | Variante | Plantas | Ejes | Hojas | Reproductivas | Ajustes | Clearance mínimo |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for report in reports:
        counts = report.morphology["organ_counts"]
        lines.append(
            "| {seed} | {variant} | {plants} | {axes} | {leaves} | {repro} | {adjustments} | {clearance} |".format(
                seed=report.seed,
                variant=report.model_variant,
                plants=counts["plants"],
                axes=counts["axes"],
                leaves=counts["leaves"],
                repro=counts["reproductive_units"],
                adjustments=report.adjustments.get("count", 0),
                clearance=report.contacts.get("minimum_clearance"),
            )
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "json": json_path,
        "csv": csv_path,
        "markdown": markdown_path,
    }


def _compute_canopy_metrics(
    scene: CultivationScene,
    plants_by_id: dict[str, Plant],
) -> dict[str, Any]:
    try:
        from .collisions import build_scene_proxies

        proxies = build_scene_proxies(scene, plants_by_id)
    except (KeyError, ValueError):
        proxies = []
    boxes_by_plant: dict[str, list[tuple[tuple[float, float, float], tuple[float, float, float]]]] = {}
    for proxy in proxies:
        if proxy.kind == "stake":
            continue
        boxes_by_plant.setdefault(proxy.plant_id, []).append(proxy.aabb())

    plant_boxes: dict[
        str, tuple[tuple[float, float, float], tuple[float, float, float]]
    ] = {}
    for plant_id, boxes in boxes_by_plant.items():
        minimum = tuple(min(box[0][axis] for box in boxes) for axis in range(3))
        maximum = tuple(max(box[1][axis] for box in boxes) for axis in range(3))
        plant_boxes[plant_id] = (minimum, maximum)

    volumes = {
        plant_id: _box_volume(box)
        for plant_id, box in plant_boxes.items()
    }
    overlap_volumes: list[float] = []
    ordered = sorted(plant_boxes)
    for left_index, left_id in enumerate(ordered):
        for right_id in ordered[left_index + 1 :]:
            overlap_volumes.append(
                _box_intersection_volume(plant_boxes[left_id], plant_boxes[right_id])
            )
    crop_box = None
    if plant_boxes:
        crop_box = (
            tuple(min(box[0][axis] for box in plant_boxes.values()) for axis in range(3)),
            tuple(max(box[1][axis] for box in plant_boxes.values()) for axis in range(3)),
        )
    return {
        "plant_aabb_volume": _summary(volumes.values()),
        "crop_aabb_volume": _box_volume(crop_box) if crop_box is not None else 0.0,
        "pairwise_aabb_overlap_volume": _summary(overlap_volumes),
        "mixed_pair_fraction": (
            sum(value > 0.0 for value in overlap_volumes) / len(overlap_volumes)
            if overlap_volumes
            else 0.0
        ),
        "proxy_count": len(proxies),
        "parameter_status": "engineering_heuristic",
    }


def _compute_projected_proxy_metrics(
    scene: CultivationScene,
    plants_by_id: dict[str, Plant],
    *,
    grid_size: int = 96,
) -> dict[str, Any]:
    """Cheap fixed X/Z projection used before Blender camera measurements."""
    try:
        from .collisions import build_scene_proxies

        proxies = [
            item
            for item in build_scene_proxies(scene, plants_by_id)
            if item.kind
            not in {"stake", "support_post", "support_line", "support_tie"}
        ]
    except (KeyError, ValueError):
        proxies = []
    if not proxies:
        return {
            "projection": "orthographic_xz_proxy",
            "coverage_fraction": 0.0,
            "visible_gap_fraction": 1.0,
            "mixed_cell_fraction": 0.0,
            "parameter_status": "engineering_heuristic",
        }
    boxes = [(item, item.aabb()) for item in proxies]
    min_x = min(box[0][0] for _, box in boxes)
    max_x = max(box[1][0] for _, box in boxes)
    min_z = min(box[0][2] for _, box in boxes)
    max_z = max(box[1][2] for _, box in boxes)
    extent_x = max(max_x - min_x, 1e-6)
    extent_z = max(max_z - min_z, 1e-6)
    cells: dict[tuple[int, int], set[str]] = {}
    apparent_widths: dict[str, list[float]] = {}
    apparent_heights: dict[str, list[float]] = {}
    for proxy, box in boxes:
        x0 = max(0, min(grid_size - 1, int((box[0][0] - min_x) / extent_x * grid_size)))
        x1 = max(0, min(grid_size - 1, int((box[1][0] - min_x) / extent_x * grid_size)))
        z0 = max(0, min(grid_size - 1, int((box[0][2] - min_z) / extent_z * grid_size)))
        z1 = max(0, min(grid_size - 1, int((box[1][2] - min_z) / extent_z * grid_size)))
        for x_index in range(min(x0, x1), max(x0, x1) + 1):
            for z_index in range(min(z0, z1), max(z0, z1) + 1):
                cells.setdefault((x_index, z_index), set()).add(proxy.plant_id)
        apparent_widths.setdefault(proxy.kind, []).append(
            (box[1][0] - box[0][0]) / extent_x
        )
        apparent_heights.setdefault(proxy.kind, []).append(
            (box[1][2] - box[0][2]) / extent_z
        )
    total_cells = grid_size * grid_size
    mixed_cells = sum(len(plant_ids) > 1 for plant_ids in cells.values())
    return {
        "projection": "orthographic_xz_proxy",
        "grid_size": grid_size,
        "coverage_fraction": round(len(cells) / total_cells, 6),
        "visible_gap_fraction": round(1.0 - len(cells) / total_cells, 6),
        "mixed_cell_fraction": round(mixed_cells / max(len(cells), 1), 6),
        "apparent_width_fraction_by_organ": {
            key: _summary(values)
            for key, values in sorted(apparent_widths.items())
        },
        "apparent_height_fraction_by_organ": {
            key: _summary(values)
            for key, values in sorted(apparent_heights.items())
        },
        "crop_bounds_xz": [
            round(min_x, 6),
            round(min_z, 6),
            round(max_x, 6),
            round(max_z, 6),
        ],
        "parameter_status": "engineering_heuristic",
    }


def _summary(values: Iterable[float | int]) -> dict[str, Any]:
    numbers = [float(value) for value in values]
    if not numbers:
        return {
            "count": 0,
            "min": None,
            "median": None,
            "mean": None,
            "p95": None,
            "max": None,
        }
    ordered = sorted(numbers)
    p95_index = min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)
    return {
        "count": len(ordered),
        "min": round(ordered[0], 6),
        "median": round(statistics.median(ordered), 6),
        "mean": round(statistics.fmean(ordered), 6),
        "p95": round(ordered[p95_index], 6),
        "max": round(ordered[-1], 6),
    }


def _summaries_by_order(
    values: dict[int, list[float | int]],
) -> dict[str, dict[str, Any]]:
    return {
        str(order): _summary(items)
        for order, items in sorted(values.items())
    }


def _count_by_order(values: dict[int, list[Any]]) -> dict[str, int]:
    return {str(order): len(items) for order, items in sorted(values.items())}


def _box_volume(
    box: tuple[tuple[float, float, float], tuple[float, float, float]] | None,
) -> float:
    if box is None:
        return 0.0
    return math.prod(max(0.0, box[1][axis] - box[0][axis]) for axis in range(3))


def _box_intersection_volume(
    left: tuple[tuple[float, float, float], tuple[float, float, float]],
    right: tuple[tuple[float, float, float], tuple[float, float, float]],
) -> float:
    return math.prod(
        max(0.0, min(left[1][axis], right[1][axis]) - max(left[0][axis], right[0][axis]))
        for axis in range(3)
    )


def _flatten_report(report: SceneMetricsReport) -> dict[str, Any]:
    counts = report.morphology.get("organ_counts", {})
    return {
        "seed": report.seed,
        "model_variant": report.model_variant,
        "scene_id": report.scene_id,
        "source_fingerprint": report.source_fingerprint,
        "plant_count": counts.get("plants", 0),
        "axis_count": counts.get("axes", 0),
        "node_count": counts.get("nodes", 0),
        "leaf_count": counts.get("leaves", 0),
        "reproductive_unit_count": counts.get("reproductive_units", 0),
        "adjustment_count": report.adjustments.get("count", 0),
        "proxy_conflicts": report.contacts.get("proxy_conflicts", 0),
        "mesh_intersections": report.contacts.get("mesh_intersections", 0),
        "clearance_violations": report.contacts.get("clearance_violations", 0),
        "minimum_clearance": report.contacts.get("minimum_clearance"),
        "elapsed_seconds": report.performance.get("elapsed_seconds"),
        "peak_memory_bytes": report.performance.get("peak_memory_bytes"),
    }
