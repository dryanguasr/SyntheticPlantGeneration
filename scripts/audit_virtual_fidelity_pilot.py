"""Evaluate the fixed acceptance criteria for the virtual-fidelity v2 pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


VISUAL_STATES = ("pass", "fail", "pending")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _criterion(value: Any, threshold: str, passed: bool | None) -> dict[str, Any]:
    return {"value": value, "threshold": threshold, "passed": passed}


def build_audit(
    *,
    dataset_root: Path,
    integrity_path: Path,
    domain_path: Path,
    baseline_v1_domain_path: Path,
    visual_macro_waves: str,
    visual_new_plastic: str,
) -> dict[str, Any]:
    dataset_report_path = dataset_root / "dataset_report.json"
    dataset_report = _read_json(dataset_report_path)
    integrity = _read_json(integrity_path)
    domain = _read_json(domain_path)
    baseline_v1 = _read_json(baseline_v1_domain_path)

    morphology = integrity["morphology_and_visibility"]
    alignment = dataset_report["reference_alignment"]
    area_gap = float(alignment["metrics"]["box_area"]["maximum_gap_pct_points"])
    composition_gap = float(
        domain["distance"]["composition_mean_absolute_gap_pct_points"]
    )
    candidate = domain["candidate"]["overall"]
    context = candidate["non_calyx_scene_context"]
    edge_energy = float(context["edge_energy"]["p50"])
    luma_spread = float(context["luminance_spread"]["p50"])
    pilot_luma = float(candidate["mean_luminance_quantiles"]["p50"])
    v1_luma = float(baseline_v1["candidate"]["overall"]["mean_luminance_quantiles"]["p50"])
    luma_delta = pilot_luma - v1_luma

    invariant_counts = {
        "physical_collision_count": int(morphology["physical_collision_count"]),
        "open_calyx_count": int(morphology["open_calyx_count"]),
        "visible_hidden_fruit_count": int(morphology["visible_hidden_fruit_count"]),
        "unknown_visible_reproductive_instance_count": int(
            morphology["unknown_visible_reproductive_instance_count"]
        ),
    }
    visual_macro_pass = None if visual_macro_waves == "pending" else visual_macro_waves == "pass"
    visual_plastic_pass = None if visual_new_plastic == "pending" else visual_new_plastic == "pass"
    criteria = {
        "dataset_integrity": _criterion(
            integrity["status"], "valid", integrity["status"] == "valid"
        ),
        "morphology_and_visibility": _criterion(
            invariant_counts,
            "all counts equal zero",
            all(value == 0 for value in invariant_counts.values()),
        ),
        "box_area_maximum_gap_pct_points": _criterion(
            area_gap, "<= 7.0", area_gap <= 7.0
        ),
        "composition_mean_absolute_gap_pct_points": _criterion(
            composition_gap, "<= 3.0", composition_gap <= 3.0
        ),
        "context_edge_energy_median": _criterion(
            edge_energy, ">= 30.0", edge_energy >= 30.0
        ),
        "context_luminance_spread_median": _criterion(
            luma_spread, ">= 38.0", luma_spread >= 38.0
        ),
        "global_luminance_vs_v1": _criterion(
            {"pilot_p50": pilot_luma, "v1_p50": v1_luma, "delta": round(luma_delta, 3)},
            "pilot delta >= -2.0 levels",
            luma_delta >= -2.0,
        ),
        "visual_macro_waves_absent": _criterion(
            visual_macro_waves, "pass", visual_macro_pass
        ),
        "visual_new_plastic_gloss_absent": _criterion(
            visual_new_plastic, "pass", visual_plastic_pass
        ),
    }
    passed_values = [item["passed"] for item in criteria.values()]
    status = (
        "accepted"
        if all(value is True for value in passed_values)
        else "rejected"
        if any(value is False for value in passed_values)
        else "pending_visual_review"
    )
    return {
        "audit_version": "1.0.0",
        "status": status,
        "dataset_root": str(dataset_root.resolve()),
        "reference_split": alignment.get("reference_split"),
        "real_test_consulted": False,
        "render_engine": "BLENDER_EEVEE_NEXT",
        "cycles_qa_count": int(dataset_report["summary"]["qa_cycles_count"]),
        "criteria": criteria,
        "input_hashes": {
            "dataset_report_sha256": _sha256(dataset_report_path),
            "integrity_audit_sha256": _sha256(integrity_path),
            "domain_comparison_sha256": _sha256(domain_path),
            "baseline_v1_domain_comparison_sha256": _sha256(
                baseline_v1_domain_path
            ),
        },
        "interpretation": (
            "Acceptance requires every automated and visual criterion to pass. "
            "Failure blocks the 640-image dataset and new training runs."
        ),
    }


def _markdown(report: dict[str, Any]) -> str:
    labels = {
        "dataset_integrity": "Integridad",
        "morphology_and_visibility": "Colisiones, capachos y fruto oculto",
        "box_area_maximum_gap_pct_points": "Brecha máxima de bandas de área",
        "composition_mean_absolute_gap_pct_points": "Brecha media de composición",
        "context_edge_energy_median": "Energía de borde contextual mediana",
        "context_luminance_spread_median": "Dispersión contextual de luminancia",
        "global_luminance_vs_v1": "Luminancia global frente a v1",
        "visual_macro_waves_absent": "Macroondulaciones nuevas ausentes",
        "visual_new_plastic_gloss_absent": "Brillo plástico nuevo ausente",
    }
    rows = []
    for key, item in report["criteria"].items():
        passed = "pendiente" if item["passed"] is None else "sí" if item["passed"] else "no"
        rows.append(
            f"| {labels[key]} | `{json.dumps(item['value'], ensure_ascii=False)}` | "
            f"`{item['threshold']}` | {passed} |"
        )
    return "\n".join(
        [
            "# Auditoría del piloto de fidelidad virtual v2",
            "",
            f"Estado: **{report['status']}**.",
            "",
            f"Split real de referencia: `{report['reference_split']}`. Test real consultado: **no**.",
            "",
            "| Criterio | Valor | Umbral | Cumple |",
            "|---|---:|---:|:---:|",
            *rows,
            "",
            report["interpretation"],
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--integrity-audit", type=Path, required=True)
    parser.add_argument("--domain-comparison", type=Path, required=True)
    parser.add_argument("--baseline-v1-domain-comparison", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--visual-macro-waves", choices=VISUAL_STATES, default="pending")
    parser.add_argument("--visual-new-plastic", choices=VISUAL_STATES, default="pending")
    args = parser.parse_args()
    report = build_audit(
        dataset_root=args.dataset_root,
        integrity_path=args.integrity_audit,
        domain_path=args.domain_comparison,
        baseline_v1_domain_path=args.baseline_v1_domain_comparison,
        visual_macro_waves=args.visual_macro_waves,
        visual_new_plastic=args.visual_new_plastic,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "pilot_audit.json"
    markdown_path = args.output_dir / "pilot_audit.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    markdown_path.write_text(_markdown(report), encoding="utf-8", newline="\n")
    print(json_path)
    print(markdown_path)
    raise SystemExit(0 if report["status"] == "accepted" else 2)


if __name__ == "__main__":
    main()
