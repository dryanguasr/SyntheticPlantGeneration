"""Validation-only confirmatory decisions and immutable selection locks.

This module deliberately contains no inference code.  Its purpose is to make
the boundary before the final test explicit and machine-verifiable.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .manifest import file_sha256


SELECTION_PROTOCOL_VERSION = "classical_augmentation_v2_selection_v1.0.0"
GLOBAL_SIGN_FRACTION = 0.8
MAX_OPERATIONAL_RECALL_DROP = 0.02
MAP_STABILITY_TOLERANCE = 0.005


def paired_interval(values: list[float], confidence: float = 0.95) -> dict[str, Any]:
    """Return descriptive paired statistics and a Student-t interval.

    The campaign uses at most ten seeds, so fixed two-sided 95% critical
    values avoid a new SciPy dependency.  For other confidence levels the
    interval is intentionally unavailable rather than silently approximated.
    """
    if not values:
        return {"n": 0, "mean": None, "sd": None, "ci95": None}
    mean = statistics.mean(values)
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    interval = None
    critical = {
        1: 12.706,
        2: 4.303,
        3: 3.182,
        4: 2.776,
        5: 2.571,
        6: 2.447,
        7: 2.365,
        8: 2.306,
        9: 2.262,
        10: 2.228,
        11: 2.201,
        12: 2.179,
        13: 2.160,
        14: 2.145,
        15: 2.131,
        16: 2.120,
        17: 2.110,
        18: 2.101,
        19: 2.093,
        20: 2.086,
        21: 2.080,
        22: 2.074,
        23: 2.069,
        24: 2.064,
        25: 2.060,
        26: 2.056,
        27: 2.052,
        28: 2.048,
        29: 2.045,
        30: 2.042,
    }
    if confidence == 0.95 and len(values) > 1:
        t_value = critical.get(len(values) - 1)
        if t_value is not None:
            margin = t_value * sd / math.sqrt(len(values))
            interval = [mean - margin, mean + margin]
    return {"n": len(values), "mean": mean, "sd": sd, "ci95": interval}


def confirmation_decisions(report: dict[str, Any]) -> dict[str, Any]:
    """Apply the predeclared strong-candidate and extension rules on val only."""
    if report.get("test_consulted") is not False or report.get("selection_split") != "val":
        raise ValueError("Confirmatory decisions require validation-only evidence.")
    runs = report.get("runs", [])
    if any(int(run.get("epochs_completed", 0)) != 50 for run in runs):
        raise ValueError("Every confirmatory run must contain exactly 50 epochs.")
    scenarios = {run["scenario"] for run in runs}
    if not {"V2-E0", "V2-E0R"}.issubset(scenarios):
        raise ValueError("Both V2-E0 and V2-E0R controls are required.")
    observed_pairs = {(run["scenario"], int(run["seed"])) for run in runs}
    if len(observed_pairs) != len(runs):
        raise ValueError("Confirmatory evidence contains duplicate scenario/seed runs.")
    seeds_by_scenario = {
        scenario: sorted(
            int(run["seed"]) for run in runs if run["scenario"] == scenario
        )
        for scenario in scenarios
    }
    control_seeds = seeds_by_scenario["V2-E0"]
    if seeds_by_scenario["V2-E0R"] != control_seeds or len(control_seeds) not in {5, 10}:
        raise ValueError("Controls must share an exact five- or ten-seed cohort.")
    for scenario in scenarios - {"V2-E0", "V2-E0R"}:
        cohort = seeds_by_scenario[scenario]
        if len(cohort) not in {5, 10} or not set(cohort).issubset(control_seeds):
            raise ValueError(
                f"{scenario}: recipe cohort must contain exactly 5 or 10 seeds paired with both controls."
            )

    decisions: dict[str, Any] = {}
    for scenario in sorted(scenarios - {"V2-E0", "V2-E0R"}):
        seeds = seeds_by_scenario[scenario]
        required_positive = math.ceil(GLOBAL_SIGN_FRACTION * len(seeds))
        versus_e0r = report["paired"][scenario]["V2-E0R"]
        versus_e0 = report["paired"][scenario]["V2-E0"]
        map_deltas = [float(value) for value in versus_e0r["differences"]]
        operational_deltas = [
            float(value) for value in versus_e0r["operational_recall_differences"]
        ]
        if len(map_deltas) != len(seeds) or len(operational_deltas) != len(seeds):
            raise ValueError(f"{scenario}: incomplete paired operational evidence.")
        mean_map = statistics.mean(map_deltas)
        mean_operational = statistics.mean(operational_deltas)
        positive_map = sum(value > 0 for value in map_deltas)
        positive_operational = sum(value > 0 for value in operational_deltas)
        difficulty = versus_e0r.get("mean_delta_difficulty_recall", {})
        key_difficulty = {
            label: difficulty.get(label)
            for label in ("size:small", "clustered:True", "border_contact:True")
        }
        if any(value is None for value in key_difficulty.values()):
            raise ValueError(f"{scenario}: incomplete key difficulty evidence.")
        no_operational_degradation = (
            mean_operational >= -MAX_OPERATIONAL_RECALL_DROP
            and min(float(value) for value in key_difficulty.values())
            >= -MAX_OPERATIONAL_RECALL_DROP
        )
        global_case = (
            mean_map > 0
            and positive_map >= required_positive
            and no_operational_degradation
        )
        operational_case = (
            mean_map >= -MAP_STABILITY_TOLERANCE
            and mean_operational > 0
            and positive_operational >= required_positive
            and max(float(value) for value in key_difficulty.values()) > 0
            and no_operational_degradation
        )
        comparison_extension = any(
            float(comparison["mean_delta_map5095"]) > 0
            and int(comparison["positive_seeds"]) >= required_positive
            for comparison in (versus_e0, versus_e0r)
        )
        decisions[scenario] = {
            "case_a_global_improvement": global_case,
            "case_b_operational_improvement": operational_case,
            "strong_candidate": global_case or operational_case,
            "extend_to_ten_seeds": len(seeds) == 5
            and comparison_extension
            and no_operational_degradation,
            "paired_map5095_vs_e0r": paired_interval(map_deltas),
            "paired_operational_recall_vs_e0r": paired_interval(operational_deltas),
            "positive_map_seeds_vs_e0r": positive_map,
            "positive_operational_seeds_vs_e0r": positive_operational,
            "required_positive_seed_count": required_positive,
            "seed_count": len(seeds),
            "seeds": seeds,
            "mean_delta_key_difficulty_recall_vs_e0r": key_difficulty,
        }
    return {
        "protocol_version": SELECTION_PROTOCOL_VERSION,
        "selection_split": "val",
        "test_consulted": False,
        "seed_count": len(control_seeds),
        "seeds": control_seeds,
        "scenario_cohorts": {
            scenario: seeds_by_scenario[scenario]
            for scenario in sorted(scenarios)
        },
        "fixed_engineering_thresholds": {
            "majority_sign_fraction": GLOBAL_SIGN_FRACTION,
            "maximum_operational_recall_drop": MAX_OPERATIONAL_RECALL_DROP,
            "map_stability_tolerance": MAP_STABILITY_TOLERANCE,
        },
        "decisions": decisions,
    }


def create_selection_lock(
    *,
    confirmatory_summary_path: str | Path,
    project: str | Path,
    campaign_config_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Freeze recipes, datasets, protocol, checkpoints and val thresholds."""
    summary_path = Path(confirmatory_summary_path).resolve()
    project = Path(project).resolve()
    config_path = Path(campaign_config_path).resolve()
    output_path = Path(output_path).resolve()
    if output_path.exists():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        if existing.get("status") != "locked":
            raise ValueError("Existing selection lock is not sealed.")
        if existing.get("confirmatory_summary_sha256") != file_sha256(summary_path):
            raise FileExistsError("Selection lock belongs to different confirmatory evidence.")
        if existing.get("campaign_config_sha256") != file_sha256(config_path):
            raise FileExistsError("Selection lock belongs to a different campaign configuration.")
        return existing
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    decision = confirmation_decisions(summary)
    if any(item["extend_to_ten_seeds"] for item in decision["decisions"].values()):
        raise ValueError("A qualifying five-seed cohort must be extended before locking.")
    selected_scenarios = [
        scenario
        for scenario in summary["ranking"]
        if decision["decisions"].get(scenario, {}).get("strong_candidate")
    ][:3]
    environment_path = project / "execution_environment.json"
    environment = json.loads(environment_path.read_text(encoding="utf-8"))
    locked_runs = []
    for run in summary["runs"]:
        if run["scenario"] not in {"V2-E0", "V2-E0R", *selected_scenarios}:
            continue
        checkpoint = Path(run["checkpoint"]).resolve()
        if file_sha256(checkpoint) != run["checkpoint_sha256"]:
            raise ValueError(f"Checkpoint hash changed: {checkpoint}")
        data_yaml = Path(run["data_yaml"]).resolve()
        dataset_dir = data_yaml.parent
        build_config = dataset_dir / "build_config.json"
        audit_report = dataset_dir / "audit_report.json"
        if json.loads(audit_report.read_text(encoding="utf-8")).get("status") != "valid":
            raise ValueError(f"Dataset audit is not valid: {dataset_dir}")
        operational = run.get("operational", {})
        sweep = operational.get("confidence_sweep", {})
        selected_threshold = sweep.get("selected")
        if not selected_threshold:
            raise ValueError(f"Missing validation-selected threshold: {run['scenario']} seed {run['seed']}")
        locked_runs.append(
            {
                "role": "control" if run["scenario"] in {"V2-E0", "V2-E0R"} else "candidate",
                "scenario": run["scenario"],
                "seed": int(run["seed"]),
                "checkpoint": str(checkpoint),
                "checkpoint_sha256": run["checkpoint_sha256"],
                "checkpoint_rule": "maximum_validation_map50_95",
                "best_epoch": int(run["best_epoch"]),
                "data_yaml": str(data_yaml),
                "data_yaml_sha256": file_sha256(data_yaml),
                "dataset_build_config": str(build_config.resolve()),
                "dataset_build_config_sha256": file_sha256(build_config),
                "dataset_audit_sha256": file_sha256(audit_report),
                "confidence_threshold_rule": sweep["selection_rule"],
                "validation_selected_confidence": float(selected_threshold["confidence"]),
            }
        )
    payload = {
        "protocol_version": SELECTION_PROTOCOL_VERSION,
        "status": "locked",
        "locked_at_utc": datetime.now(timezone.utc).isoformat(),
        "selection_split": "val",
        "test_consulted": False,
        "test_policy": "single_evaluation_of_locked_controls_and_candidates_only",
        "historical_test_caveat": (
            "Test was excluded from selection in this campaign but had been consulted "
            "in historical work, so it is not a virgin holdout."
        ),
        "confirmatory_summary": str(summary_path),
        "confirmatory_summary_sha256": file_sha256(summary_path),
        "decision": decision,
        "selected_scenarios": selected_scenarios,
        "campaign_config": str(config_path),
        "campaign_config_sha256": file_sha256(config_path),
        "training_environment": environment,
        "training_environment_sha256": file_sha256(environment_path),
        "locked_runs": sorted(locked_runs, key=lambda item: (item["scenario"], item["seed"])),
    }
    payload["lock_content_sha256"] = _canonical_hash(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return payload


def verify_selection_lock(lock_path: str | Path) -> dict[str, Any]:
    """Verify the immutable lock and every file it authorizes."""
    lock_path = Path(lock_path).resolve()
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    if payload.get("status") != "locked":
        raise ValueError("Selection lock is not sealed.")
    expected_hash = payload.get("lock_content_sha256")
    content = dict(payload)
    content.pop("lock_content_sha256", None)
    if not expected_hash or _canonical_hash(content) != expected_hash:
        raise ValueError("Selection lock content hash mismatch.")
    protected_files = (
        (payload["confirmatory_summary"], payload["confirmatory_summary_sha256"]),
        (payload["campaign_config"], payload["campaign_config_sha256"]),
    )
    for path, expected in protected_files:
        if file_sha256(Path(path)) != expected:
            raise ValueError(f"Protected selection input changed: {path}")
    for run in payload["locked_runs"]:
        checks = (
            (run["checkpoint"], run["checkpoint_sha256"]),
            (run["data_yaml"], run["data_yaml_sha256"]),
            (run["dataset_build_config"], run["dataset_build_config_sha256"]),
            (str(Path(run["dataset_build_config"]).with_name("audit_report.json")), run["dataset_audit_sha256"]),
        )
        for path, expected in checks:
            if file_sha256(Path(path)) != expected:
                raise ValueError(f"Locked run input changed: {path}")
    return payload


def _canonical_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
