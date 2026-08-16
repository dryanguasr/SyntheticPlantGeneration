"""Pure-Python shared occupancy and organ-contact policy.

The broad-phase shapes in this module are deliberately conservative.  They
guide growth proposals; evaluated Blender meshes remain the final authority
for physical intersection.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields
from typing import Any, Iterable

from .morphology import SerializableMixin
from .provenance import provenance_for_status


Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class ContactRule(SerializableMixin):
    organ_a: str
    organ_b: str
    policy: str
    clearance: float
    near_contact_distance: float
    intentional_contact_allowed: bool = False
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str]:
        return tuple(sorted((self.organ_a, self.organ_b)))


@dataclass
class ContactPolicy(SerializableMixin):
    """Pair-specific hard, soft, visual, and intentional contact rules."""

    rules: list[ContactRule]
    default_policy: str = "soft_occupancy"
    default_clearance: float = 0.018
    default_near_contact_distance: float = 0.055
    schema_version: str = "1.0"

    @classmethod
    def default(cls) -> "ContactPolicy":
        provenance = provenance_for_status(
            "engineering_heuristic",
            method="pair_clearance_proxy_initialisation",
        ).to_dict()
        definitions = (
            ("stem", "stem", "hard_occupancy", 0.024, 0.065, False),
            ("stem", "calyx", "hard_occupancy", 0.022, 0.060, False),
            ("calyx", "calyx", "hard_occupancy", 0.022, 0.060, False),
            ("stem", "support_post", "hard_occupancy", 0.020, 0.055, False),
            ("calyx", "support_post", "hard_occupancy", 0.018, 0.050, False),
            ("leaf", "support_post", "soft_occupancy", 0.008, 0.045, False),
            ("leaf", "stem", "soft_occupancy", 0.006, 0.040, False),
            ("leaf", "calyx", "soft_occupancy", 0.006, 0.040, False),
            ("leaf", "leaf", "visual_occlusion", 0.000, 0.030, False),
            ("stem", "support_line", "intentional_support", 0.000, 0.045, True),
            ("stem", "support_tie", "intentional_support", 0.000, 0.045, True),
        )
        return cls(
            rules=[
                ContactRule(
                    organ_a=organ_a,
                    organ_b=organ_b,
                    policy=policy,
                    clearance=clearance,
                    near_contact_distance=near_distance,
                    intentional_contact_allowed=intentional,
                    provenance=provenance,
                )
                for (
                    organ_a,
                    organ_b,
                    policy,
                    clearance,
                    near_distance,
                    intentional,
                ) in definitions
            ]
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ContactPolicy":
        accepted = {item.name for item in fields(cls)}
        values = {
            key: value
            for key, value in payload.items()
            if key in accepted and key != "rules"
        }
        values["rules"] = [
            ContactRule(
                **{
                    key: value
                    for key, value in item.items()
                    if key in {field_.name for field_ in fields(ContactRule)}
                }
            )
            for item in payload.get("rules", [])
        ]
        return cls(**values)

    def rule_for(self, organ_a: str, organ_b: str) -> ContactRule:
        key = tuple(sorted((organ_a, organ_b)))
        for rule in self.rules:
            if rule.key == key:
                return rule
        return ContactRule(
            organ_a=key[0],
            organ_b=key[1],
            policy=self.default_policy,
            clearance=self.default_clearance,
            near_contact_distance=self.default_near_contact_distance,
            provenance=provenance_for_status(
                "engineering_heuristic",
                method="default_pair_contact_policy",
            ).to_dict(),
        )


@dataclass(frozen=True)
class SpatialItem(SerializableMixin):
    id: str
    plant_id: str
    organ_type: str
    start: Vec3
    end: Vec3
    radius: float
    intentional_contact: bool = False
    source_id: str | None = None

    def aabb(self, padding: float = 0.0) -> tuple[Vec3, Vec3]:
        amount = self.radius + padding
        return (
            tuple(min(self.start[index], self.end[index]) - amount for index in range(3)),
            tuple(max(self.start[index], self.end[index]) + amount for index in range(3)),
        )


@dataclass(frozen=True)
class ContactEvaluation(SerializableMixin):
    item_a: str
    item_b: str
    organ_a: str
    organ_b: str
    clearance: float
    required_clearance: float
    classification: str
    policy: str


class SpatialOccupancy:
    """Deterministic spatial hash over capsule-like growth proxies."""

    def __init__(
        self,
        contact_policy: ContactPolicy | None = None,
        *,
        cell_size: float = 0.32,
    ) -> None:
        self.contact_policy = contact_policy or ContactPolicy.default()
        self.cell_size = float(cell_size)
        self._items: dict[str, SpatialItem] = {}
        self._cells: dict[tuple[int, int, int], set[str]] = {}

    @property
    def items(self) -> list[SpatialItem]:
        return [self._items[key] for key in sorted(self._items)]

    def add(self, item: SpatialItem) -> None:
        if item.id in self._items:
            raise ValueError(f"Spatial item already exists: {item.id}")
        self._items[item.id] = item
        for cell in self._cells_for_aabb(item.aabb(self.contact_policy.default_near_contact_distance)):
            self._cells.setdefault(cell, set()).add(item.id)

    def query(self, item: SpatialItem) -> list[ContactEvaluation]:
        candidate_ids: set[str] = set()
        padding = max(
            self.contact_policy.default_near_contact_distance,
            self.contact_policy.default_clearance,
        )
        for cell in self._cells_for_aabb(item.aabb(padding)):
            candidate_ids.update(self._cells.get(cell, set()))
        evaluations: list[ContactEvaluation] = []
        for other_id in sorted(candidate_ids):
            other = self._items[other_id]
            if other.id == item.id:
                continue
            rule = self.contact_policy.rule_for(item.organ_type, other.organ_type)
            clearance = capsule_clearance(item, other)
            classification = classify_contact(
                clearance,
                rule,
                intentional=(
                    item.intentional_contact
                    or other.intentional_contact
                    or (
                        rule.intentional_contact_allowed
                        and item.plant_id == other.plant_id
                    )
                ),
            )
            if classification != "separate":
                evaluations.append(
                    ContactEvaluation(
                        item_a=item.id,
                        item_b=other.id,
                        organ_a=item.organ_type,
                        organ_b=other.organ_type,
                        clearance=round(clearance, 6),
                        required_clearance=rule.clearance,
                        classification=classification,
                        policy=rule.policy,
                    )
                )
        return evaluations

    def hard_conflicts(self, item: SpatialItem) -> list[ContactEvaluation]:
        return [
            result
            for result in self.query(item)
            if result.classification in {"proxy_conflict", "clearance_violation"}
            and result.policy == "hard_occupancy"
        ]

    def _cells_for_aabb(
        self,
        aabb: tuple[Vec3, Vec3],
    ) -> Iterable[tuple[int, int, int]]:
        minimum = tuple(math.floor(value / self.cell_size) for value in aabb[0])
        maximum = tuple(math.floor(value / self.cell_size) for value in aabb[1])
        for x_index in range(minimum[0], maximum[0] + 1):
            for y_index in range(minimum[1], maximum[1] + 1):
                for z_index in range(minimum[2], maximum[2] + 1):
                    yield (x_index, y_index, z_index)


def classify_contact(
    clearance: float,
    rule: ContactRule,
    *,
    intentional: bool = False,
) -> str:
    if (
        intentional
        and rule.intentional_contact_allowed
        and clearance < rule.near_contact_distance
    ):
        return "intentional_contact"
    if clearance < 0.0:
        if rule.policy == "visual_occlusion":
            return "visual_occlusion"
        return "proxy_conflict"
    if clearance < rule.clearance:
        if rule.policy == "visual_occlusion":
            return "visual_occlusion"
        return "clearance_violation"
    if clearance < rule.near_contact_distance:
        return "near_contact"
    return "separate"


def capsule_clearance(left: SpatialItem, right: SpatialItem) -> float:
    return (
        _segment_segment_distance(left.start, left.end, right.start, right.end)
        - left.radius
        - right.radius
    )


def _segment_segment_distance(
    p1: Vec3,
    q1: Vec3,
    p2: Vec3,
    q2: Vec3,
) -> float:
    """Shortest distance between two finite segments."""
    d1 = _sub(q1, p1)
    d2 = _sub(q2, p2)
    r = _sub(p1, p2)
    a = _dot(d1, d1)
    e = _dot(d2, d2)
    epsilon = 1e-12
    if a <= epsilon and e <= epsilon:
        return _length(r)
    if a <= epsilon:
        s = 0.0
        t = _clamp(_dot(d2, r) / e)
    else:
        c = _dot(d1, r)
        if e <= epsilon:
            t = 0.0
            s = _clamp(-c / a)
        else:
            b = _dot(d1, d2)
            denominator = a * e - b * b
            s = _clamp((b * _dot(d2, r) - c * e) / denominator) if denominator else 0.0
            t = (b * s + _dot(d2, r)) / e
            if t < 0.0:
                t = 0.0
                s = _clamp(-c / a)
            elif t > 1.0:
                t = 1.0
                s = _clamp((b - c) / a)
    closest = _sub(_add(p1, _mul(d1, s)), _add(p2, _mul(d2, t)))
    return _length(closest)


def _dot(left: Vec3, right: Vec3) -> float:
    return sum(left[index] * right[index] for index in range(3))


def _add(left: Vec3, right: Vec3) -> Vec3:
    return tuple(left[index] + right[index] for index in range(3))


def _sub(left: Vec3, right: Vec3) -> Vec3:
    return tuple(left[index] - right[index] for index in range(3))


def _mul(value: Vec3, amount: float) -> Vec3:
    return tuple(item * amount for item in value)


def _length(value: Vec3) -> float:
    return math.sqrt(_dot(value, value))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
