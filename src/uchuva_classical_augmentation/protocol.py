"""Pure metadata contract for the student classical-augmentation baseline.

The contract records what is actually available in the delivered materials.
It must not be mistaken for an implementation of E1/E2: only their resulting
datasets and the multi-seed training launcher were supplied.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


STUDENT_YOLO11N_PROTOCOL_VERSION = "diego_amaya_yolo11n_multiseed_v1"
RECIPE_STATUS_PRECOMPUTED_ONLY = "precomputed_dataset_only"


@dataclass(frozen=True)
class ClassicalAugmentationCondition:
    """One explicitly documented conventional-augmentation condition."""

    code: str
    dataset_id: str
    description: str
    transform_families: tuple[str, ...]
    recipe_status: str
    expected_split_counts: tuple[int, int, int]
    source_protocol: str = STUDENT_YOLO11N_PROTOCOL_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation without hiding provenance."""
        return asdict(self)


def student_yolo11n_conditions() -> tuple[ClassicalAugmentationCondition, ...]:
    """Return the three conditions documented in the student delivery.

    E1 and E2 are usable as fixed datasets, but their transformation recipes
    are not reproducible from source code currently present in the repository.
    """
    return (
        ClassicalAugmentationCondition(
            code="E0",
            dataset_id="semifield_v1",
            description="Datos reales sin aumentacion offline.",
            transform_families=(),
            recipe_status="natural_only",
            expected_split_counts=(1062, 109, 109),
        ),
        ClassicalAugmentationCondition(
            code="E1",
            dataset_id="dataset_E1_occ_light_strong",
            description="Oclusion y cambios fuertes de iluminacion.",
            transform_families=("occlusion", "photometric"),
            recipe_status=RECIPE_STATUS_PRECOMPUTED_ONLY,
            expected_split_counts=(2124, 109, 109),
        ),
        ClassicalAugmentationCondition(
            code="E2",
            dataset_id="dataset_E2_occ_light_soft",
            description="Oclusion e iluminacion moderadas.",
            transform_families=("occlusion", "photometric"),
            recipe_status=RECIPE_STATUS_PRECOMPUTED_ONLY,
            expected_split_counts=(2124, 109, 109),
        ),
    )
