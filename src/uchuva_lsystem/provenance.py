"""Canonical provenance helpers for scientific and engineering parameters.

The project historically stored free-form ``status`` strings.  Those strings
remain available for compatibility, while this module adds a canonical,
machine-readable provenance record using the taxonomy agreed for the current
research iteration.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


PROVENANCE_STATUSES: tuple[str, ...] = (
    "literature_reported",
    "real_dataset_measured",
    "real_dataset_inferred",
    "manual_initial_guess",
    "engineering_heuristic",
    "implementation_constraint",
    "to_be_measured",
)


@dataclass
class ParameterProvenance:
    """Canonical provenance attached to a parameter or modeling decision."""

    status: str
    method: str = ""
    source_ids: list[str] = field(default_factory=list)
    uncertainty: str = "high"
    pending_validation: bool = True
    legacy_status: str = ""

    def __post_init__(self) -> None:
        if self.status not in PROVENANCE_STATUSES:
            raise ValueError(f"Unknown provenance status: {self.status}")
        if self.uncertainty not in {"low", "medium", "high"}:
            raise ValueError("uncertainty must be low, medium, or high")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "method": self.method,
            "source_ids": list(self.source_ids),
            "uncertainty": self.uncertainty,
            "pending_validation": self.pending_validation,
            "legacy_status": self.legacy_status,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ParameterProvenance":
        return cls(
            status=str(payload["status"]),
            method=str(payload.get("method", "")),
            source_ids=[str(item) for item in payload.get("source_ids", [])],
            uncertainty=str(payload.get("uncertainty", "high")),
            pending_validation=bool(payload.get("pending_validation", True)),
            legacy_status=str(payload.get("legacy_status", "")),
        )


def canonical_status(status: str) -> str:
    """Map a historical compound status to one canonical category."""
    lowered = status.strip().lower()
    if lowered in PROVENANCE_STATUSES:
        return lowered
    if "literature" in lowered:
        return "literature_reported"
    if "dataset" in lowered and "measured" in lowered:
        return "real_dataset_measured"
    if "dataset" in lowered or "inferred" in lowered:
        return "real_dataset_inferred"
    if "constraint" in lowered:
        return "implementation_constraint"
    if "heuristic" in lowered or "collision" in lowered:
        return "engineering_heuristic"
    if "manual" in lowered or "guess" in lowered or "estimated" in lowered:
        return "manual_initial_guess"
    return "to_be_measured"


def provenance_for_status(
    status: str,
    *,
    method: str = "",
    source_ids: list[str] | None = None,
) -> ParameterProvenance:
    """Create a conservative canonical provenance record."""
    canonical = canonical_status(status)
    uncertainty = {
        "literature_reported": "medium",
        "real_dataset_measured": "medium",
        "real_dataset_inferred": "high",
        "implementation_constraint": "low",
    }.get(canonical, "high")
    pending = canonical not in {"implementation_constraint"}
    return ParameterProvenance(
        status=canonical,
        method=method or "legacy_status_mapping",
        source_ids=list(source_ids or []),
        uncertainty=uncertainty,
        pending_validation=pending,
        legacy_status=status if status != canonical else "",
    )


def normalise_parameter_provenance(parameters: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with additive canonical ``provenance`` records.

    Existing keys and free-form status strings are deliberately preserved.
    """
    result = deepcopy(parameters)

    def visit(value: Any, path: tuple[str, ...]) -> None:
        if isinstance(value, dict):
            status = value.get("status")
            if isinstance(status, str) and "provenance" not in value:
                value["provenance"] = provenance_for_status(
                    status,
                    method=".".join(path) or "root_parameter",
                ).to_dict()
            for key, item in list(value.items()):
                if key != "provenance":
                    visit(item, (*path, str(key)))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, (*path, str(index)))

    visit(result, ())
    return result


def audit_parameter_provenance(parameters: dict[str, Any]) -> dict[str, Any]:
    """Report missing or invalid provenance without mutating parameters."""
    inspected = 0
    missing: list[str] = []
    invalid: list[dict[str, str]] = []
    counts = {status: 0 for status in PROVENANCE_STATUSES}

    def visit(value: Any, path: tuple[str, ...]) -> None:
        nonlocal inspected
        if isinstance(value, dict):
            status = value.get("status")
            if isinstance(status, str):
                inspected += 1
                provenance = value.get("provenance")
                location = ".".join(path) or "<root>"
                if not isinstance(provenance, dict):
                    missing.append(location)
                else:
                    canonical = str(provenance.get("status", ""))
                    if canonical not in PROVENANCE_STATUSES:
                        invalid.append({"path": location, "status": canonical})
                    else:
                        counts[canonical] += 1
            for key, item in value.items():
                if key != "provenance":
                    visit(item, (*path, str(key)))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, (*path, str(index)))

    visit(parameters, ())
    return {
        "status": "valid" if not missing and not invalid else "invalid",
        "inspected_parameter_records": inspected,
        "canonical_status_counts": counts,
        "missing_provenance": missing,
        "invalid_provenance": invalid,
        "taxonomy": list(PROVENANCE_STATUSES),
    }
