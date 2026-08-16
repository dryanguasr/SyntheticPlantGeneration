#!/usr/bin/env python3
"""Export a dependency-free Gazebo interpretation plan from morphology JSON.

This is an interface spike, not an SDF or physics exporter.  It produces a
semantic plan that a future Robot-Cosechador Gazebo repository can consume.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from uchuva_gazebo import (  # noqa: E402
    GazeboExportConfig,
    build_gazebo_export_plan,
    write_gazebo_export_plan,
)
from uchuva_lsystem.morphology import Plant  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--morphology-json", type=Path, required=True)
    parser.add_argument("--lod", type=int, choices=(0, 1, 2), default=1)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "exports" / "gazebo",
        help="Ignored generated-artifact directory.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = json.loads(args.morphology_json.read_text(encoding="utf-8"))
    plant = Plant.from_dict(payload)
    plan = build_gazebo_export_plan(plant, GazeboExportConfig(lod=args.lod))
    destination = args.output_dir / f"seed_{plant.seed:04d}" / "gazebo_export_plan.json"
    output_path = write_gazebo_export_plan(plan, destination)
    print(f"Gazebo export plan: {output_path}")
    print("This plan contains no SDF, Gazebo runtime dependency, or measured physics.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
