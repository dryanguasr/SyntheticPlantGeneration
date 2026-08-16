"""Morphology-first uchuva plant generation package.

The package starts with a JSON-serializable morphology tree and keeps Blender
interpretation in separate modules.
"""

from .grammar import generate_morphology_tree
from .cultivation import (
    adapt_cultivation_morphologies,
    generate_cultivation_morphologies,
)
from .collisions import resolve_global_collisions
from .blender_dataset import DatasetConfig, generate_annotation_dataset
from .morphology import (
    AxillaryBud,
    Axis,
    Calyx,
    Fruit,
    Internode,
    Leaf,
    Node,
    Pedicel,
    Plant,
    ReproductiveUnit,
)
from .parameters import (
    get_initial_parameters,
    get_morphology_parameters,
    get_phenology_profile,
)
from .growth import (
    GrowthProposal,
    ProposalDecision,
    coordinate_synchronous_growth,
)
from .light_competition import (
    CanopyStratum,
    LightCandidateEvaluation,
    StratifiedLightField,
    SunSample,
)
from .spatial import (
    ContactEvaluation,
    ContactPolicy,
    ContactRule,
    SpatialItem,
    SpatialOccupancy,
    classify_contact,
)
from .support import (
    SupportContact,
    SupportLine,
    SupportPost,
    SupportSystem,
    SupportTie,
    SupportZone,
)
from .metrics import (
    SceneMetricsReport,
    compute_morphology_metrics,
    compute_scene_metrics,
)
from .human_validation import (
    HumanValidationCase,
    HumanValidationSuite,
    ProblemRecord,
    RenderQualityProfile,
    build_validation_suite,
    evaluate_human_review,
    fixed_validation_cases,
    problem_registry,
    render_quality_profiles,
    validate_protocol,
)
from .provenance import (
    PROVENANCE_STATUSES,
    ParameterProvenance,
    audit_parameter_provenance,
    normalise_parameter_provenance,
)
from .texture_assets import (
    DEFAULT_TEXTURE_ASSET_DIR,
    generate_texture_asset_library,
    texture_preset,
)
from .scene import (
    CultivationScene,
    CultivationSupport,
    EnvironmentConfig,
    PlantInstance,
    RenderConfig,
    create_cultivation_scene,
    create_scene_stub,
)
from .validation import validate_cultivation_scene, validate_morphology_tree
from .yolo_export import DetectionBox, YOLO_CLASSES

__all__ = [
    "AxillaryBud",
    "Axis",
    "Calyx",
    "Fruit",
    "Internode",
    "Leaf",
    "Node",
    "Pedicel",
    "Plant",
    "PlantInstance",
    "ReproductiveUnit",
    "CultivationScene",
    "CultivationSupport",
    "EnvironmentConfig",
    "RenderConfig",
    "SceneMetricsReport",
    "ProblemRecord",
    "HumanValidationCase",
    "HumanValidationSuite",
    "RenderQualityProfile",
    "ParameterProvenance",
    "GrowthProposal",
    "ProposalDecision",
    "CanopyStratum",
    "LightCandidateEvaluation",
    "StratifiedLightField",
    "SunSample",
    "ContactEvaluation",
    "ContactPolicy",
    "ContactRule",
    "SpatialItem",
    "SpatialOccupancy",
    "SupportContact",
    "SupportLine",
    "SupportPost",
    "SupportSystem",
    "SupportTie",
    "SupportZone",
    "DetectionBox",
    "DatasetConfig",
    "YOLO_CLASSES",
    "DEFAULT_TEXTURE_ASSET_DIR",
    "create_cultivation_scene",
    "create_scene_stub",
    "generate_morphology_tree",
    "adapt_cultivation_morphologies",
    "generate_cultivation_morphologies",
    "coordinate_synchronous_growth",
    "resolve_global_collisions",
    "generate_texture_asset_library",
    "generate_annotation_dataset",
    "get_initial_parameters",
    "get_morphology_parameters",
    "get_phenology_profile",
    "compute_morphology_metrics",
    "compute_scene_metrics",
    "build_validation_suite",
    "evaluate_human_review",
    "fixed_validation_cases",
    "problem_registry",
    "render_quality_profiles",
    "validate_protocol",
    "audit_parameter_provenance",
    "normalise_parameter_provenance",
    "PROVENANCE_STATUSES",
    "classify_contact",
    "texture_preset",
    "validate_cultivation_scene",
    "validate_morphology_tree",
]

__version__ = "0.11.0-stratified-light-standard-render"
