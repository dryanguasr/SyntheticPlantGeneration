"""Serializable cultivation-support systems and spatial queries."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, fields
from typing import Any, Iterable

from .morphology import SerializableMixin
from .provenance import ParameterProvenance


Vec3 = tuple[float, float, float]


@dataclass
class SupportPost(SerializableMixin):
    id: str
    position: Vec3
    height: float
    section_width: float
    section_depth: float
    row_id: str
    material_key: str = "stake_wood"


@dataclass
class SupportLine(SerializableMixin):
    id: str
    start: Vec3
    end: Vec3
    radius: float
    row_id: str
    material_key: str = "trellis_wire"


@dataclass
class SupportTie(SerializableMixin):
    id: str
    plant_id: str
    start: Vec3
    end: Vec3
    support_line_id: str
    intentional_contact: bool = True


@dataclass
class SupportZone(SerializableMixin):
    id: str
    support_element_id: str
    center: Vec3
    radius: float
    preferred_direction: Vec3
    mode: str = "guided_or_supported"


@dataclass
class SupportContact(SerializableMixin):
    id: str
    plant_id: str
    organ_id: str
    support_element_id: str
    point: Vec3
    contact_type: str = "intentional_support"


@dataclass
class SupportSystem(SerializableMixin):
    """Posts, continuous lines, ties, and intentional support zones."""

    id: str
    mode: str
    posts: list[SupportPost] = field(default_factory=list)
    lines: list[SupportLine] = field(default_factory=list)
    ties: list[SupportTie] = field(default_factory=list)
    zones: list[SupportZone] = field(default_factory=list)
    contacts: list[SupportContact] = field(default_factory=list)
    enabled: bool = True
    provenance: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SupportSystem":
        accepted = {item.name for item in fields(cls)}
        values = {
            key: value
            for key, value in payload.items()
            if key in accepted
            and key not in {"posts", "lines", "ties", "zones", "contacts"}
        }
        values["posts"] = [
            SupportPost(**_filtered(SupportPost, item))
            for item in payload.get("posts", [])
        ]
        values["lines"] = [
            SupportLine(**_filtered(SupportLine, item))
            for item in payload.get("lines", [])
        ]
        values["ties"] = [
            SupportTie(**_filtered(SupportTie, item))
            for item in payload.get("ties", [])
        ]
        values["zones"] = [
            SupportZone(**_filtered(SupportZone, item))
            for item in payload.get("zones", [])
        ]
        values["contacts"] = [
            SupportContact(**_filtered(SupportContact, item))
            for item in payload.get("contacts", [])
        ]
        return cls(**values)

    def nearest_support(
        self,
        point: Vec3,
        *,
        include_posts: bool = True,
        include_lines: bool = True,
    ) -> dict[str, Any] | None:
        """Return the nearest point and direction on an enabled support."""
        if not self.enabled:
            return None
        candidates: list[tuple[float, str, Vec3, str]] = []
        if include_lines:
            for line in self.lines:
                nearest = _closest_point_on_segment(point, line.start, line.end)
                candidates.append(
                    (_distance(point, nearest), line.id, nearest, "line")
                )
        if include_posts:
            for post in self.posts:
                top = (
                    post.position[0],
                    post.position[1],
                    post.position[2] + post.height,
                )
                nearest = _closest_point_on_segment(point, post.position, top)
                candidates.append(
                    (_distance(point, nearest), post.id, nearest, "post")
                )
        if not candidates:
            return None
        distance, element_id, nearest, kind = min(
            candidates, key=lambda item: (item[0], item[1])
        )
        direction = _normalise(_sub(nearest, point))
        return {
            "support_element_id": element_id,
            "kind": kind,
            "point": nearest,
            "distance": distance,
            "direction": direction,
        }


def build_continuous_trellis(
    instances: Iterable[Any],
    *,
    seed: int,
    enabled: bool = True,
) -> SupportSystem:
    """Create a deterministic two-row trellis before plant growth."""
    ordered = sorted(instances, key=lambda item: item.plant_id)
    rng = random.Random(seed + 81_337)
    rows: dict[str, list[Any]] = {}
    for instance in ordered:
        row_id = "row_negative" if instance.position[1] < 0.0 else "row_positive"
        rows.setdefault(row_id, []).append(instance)

    posts: list[SupportPost] = []
    lines: list[SupportLine] = []
    ties: list[SupportTie] = []
    zones: list[SupportZone] = []
    line_heights = (1.05, 1.82, 2.58)
    line_lookup: dict[tuple[str, int], SupportLine] = {}
    for row_id, row_instances in sorted(rows.items()):
        row_x = [item.position[0] for item in row_instances]
        row_y = statistics_median(item.position[1] for item in row_instances)
        start_x = min(row_x) - 0.42
        end_x = max(row_x) + 0.42
        # End posts keep every rigid support outside the planted corridor.
        # Intermediate posts can be added later only from measured row spans;
        # placing one at the arithmetic midpoint can intersect a main axis.
        post_x_values = (start_x, end_x)
        for index, x_value in enumerate(post_x_values):
            posts.append(
                SupportPost(
                    id=f"trellis_{row_id}_post_{index}",
                    position=(round(x_value, 4), round(row_y, 4), 0.0),
                    height=3.15,
                    section_width=0.105,
                    section_depth=0.13,
                    row_id=row_id,
                )
            )
        for height_index, height in enumerate(line_heights):
            line = SupportLine(
                id=f"trellis_{row_id}_line_{height_index}",
                start=(round(start_x, 4), round(row_y, 4), height),
                end=(round(end_x, 4), round(row_y, 4), height),
                radius=0.012,
                row_id=row_id,
            )
            lines.append(line)
            line_lookup[(row_id, height_index)] = line
            zones.append(
                SupportZone(
                    id=f"{line.id}_support_zone",
                    support_element_id=line.id,
                    center=(
                        round((start_x + end_x) * 0.5, 4),
                        round(row_y, 4),
                        height,
                    ),
                    radius=0.24,
                    preferred_direction=(1.0, 0.0, 0.0),
                )
            )

    for instance in ordered:
        row_id = "row_negative" if instance.position[1] < 0.0 else "row_positive"
        tie_count = 3 if instance.scale >= 0.9 else 2
        for tie_index in range(tie_count):
            line = line_lookup[(row_id, tie_index)]
            jitter = rng.uniform(-0.015, 0.015)
            start = (
                instance.position[0],
                instance.position[1],
                line.start[2] + jitter,
            )
            end = (
                instance.position[0],
                line.start[1],
                line.start[2] + jitter,
            )
            ties.append(
                SupportTie(
                    id=f"{instance.plant_id}_trellis_tie_{tie_index}",
                    plant_id=instance.plant_id,
                    start=tuple(round(value, 4) for value in start),
                    end=tuple(round(value, 4) for value in end),
                    support_line_id=line.id,
                )
            )

    provenance = ParameterProvenance(
        status="engineering_heuristic",
        method="continuous_two_row_trellis_initial_model",
        source_ids=[],
        uncertainty="high",
        pending_validation=True,
    )
    return SupportSystem(
        id=f"continuous_trellis_seed_{seed}",
        mode="continuous_row_trellis",
        posts=posts,
        lines=lines,
        ties=ties,
        zones=zones,
        enabled=enabled,
        provenance=provenance.to_dict(),
    )


def _filtered(cls: type[Any], payload: dict[str, Any]) -> dict[str, Any]:
    accepted = {item.name for item in fields(cls)}
    return {key: value for key, value in payload.items() if key in accepted}


def _closest_point_on_segment(point: Vec3, start: Vec3, end: Vec3) -> Vec3:
    segment = _sub(end, start)
    denominator = sum(value * value for value in segment)
    if denominator <= 1e-12:
        return start
    amount = max(
        0.0,
        min(
            1.0,
            sum((point[index] - start[index]) * segment[index] for index in range(3))
            / denominator,
        ),
    )
    return tuple(
        start[index] + segment[index] * amount for index in range(3)
    )


def _distance(left: Vec3, right: Vec3) -> float:
    return math.sqrt(sum((left[index] - right[index]) ** 2 for index in range(3)))


def _sub(left: Vec3, right: Vec3) -> Vec3:
    return tuple(left[index] - right[index] for index in range(3))


def _normalise(value: Vec3) -> Vec3:
    length = math.sqrt(sum(item * item for item in value))
    if length <= 1e-12:
        return (0.0, 0.0, 0.0)
    return tuple(item / length for item in value)


def statistics_median(values: Iterable[float]) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) * 0.5
