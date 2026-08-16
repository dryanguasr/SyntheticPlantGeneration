"""Traceable baseline definitions for conventional image augmentation.

This package intentionally does not implement undocumented transformations.
The student delivery currently provides pre-materialized E1/E2 datasets and a
reproducible multi-seed trainer; its missing image-generation recipes remain
explicitly marked as unavailable until they are recovered or reimplemented.
"""

from .protocol import (
    ClassicalAugmentationCondition,
    STUDENT_YOLO11N_PROTOCOL_VERSION,
    student_yolo11n_conditions,
)

__all__ = [
    "ClassicalAugmentationCondition",
    "STUDENT_YOLO11N_PROTOCOL_VERSION",
    "student_yolo11n_conditions",
]
