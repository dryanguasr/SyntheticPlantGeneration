"""JSON export helpers for morphology trees and validation reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def export_json(data: Any, output_path: str | Path) -> Path:
    """Export JSON-ready data or an object exposing to_dict()."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if hasattr(data, "to_dict"):
        payload = data.to_dict()
    else:
        payload = data

    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")

    return path


def export_morphology_tree(plant: Any, output_path: str | Path) -> Path:
    """Export a Plant morphology tree to JSON."""
    return export_json(plant, output_path)
