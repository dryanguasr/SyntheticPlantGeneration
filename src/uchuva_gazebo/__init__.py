"""Gazebo-facing, dependency-free interpretation contracts for morphology.

This package is a new output boundary of the morphology model.  It neither
imports Blender nor requires a local Gazebo installation.
"""

from .interfaces import (
    GAZEBO_EXPORT_SCHEMA_VERSION,
    GazeboExportConfig,
    GazeboExportPlan,
    GazeboPhysicsItem,
    GazeboVisualItem,
    build_gazebo_export_plan,
    write_gazebo_export_plan,
)
from .admitted_plants import build_admitted_plant_bundle

__all__ = [
    "GAZEBO_EXPORT_SCHEMA_VERSION",
    "GazeboExportConfig",
    "GazeboExportPlan",
    "GazeboPhysicsItem",
    "GazeboVisualItem",
    "build_gazebo_export_plan",
    "write_gazebo_export_plan",
    "build_admitted_plant_bundle",
]
