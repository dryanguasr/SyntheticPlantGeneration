"""Pure-Python proxy for stratified, daily canopy light competition.

The model deliberately estimates projected gap capture rather than physical
photosynthesis or radiative transfer.  It samples several sun directions,
projects candidate leaf footprints into lower, middle, and upper canopy
strata, and records whether a leaf covers a previously open projected cell or
shares it with leaves from the same or another plant.

All numeric defaults are engineering heuristics pending local measurement and
agronomic validation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable


Vec3 = tuple[float, float, float]
CellKey = tuple[str, int, int, int]


@dataclass(frozen=True)
class SunSample:
    """One weighted direction in a coarse daily solar path."""

    azimuth_deg: float
    elevation_deg: float
    weight: float = 1.0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SunSample":
        return cls(
            azimuth_deg=float(payload["azimuth_deg"]),
            elevation_deg=float(payload["elevation_deg"]),
            weight=float(payload.get("weight", 1.0)),
        )


@dataclass(frozen=True)
class CanopyStratum:
    """Vertical interval used to form one foliage umbrella."""

    name: str
    minimum_height: float
    maximum_height: float

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CanopyStratum":
        return cls(
            name=str(payload["name"]),
            minimum_height=float(payload["min_height"]),
            maximum_height=float(payload["max_height"]),
        )


@dataclass
class LightCandidateEvaluation:
    """Serializable summary plus internal projected cells for one leaf pose."""

    stratum: str
    projected_cell_count: int
    new_cell_count: int
    new_coverage_fraction: float
    same_plant_overlap_fraction: float
    other_plant_overlap_fraction: float
    daily_light_interception_proxy: float
    cells: frozenset[CellKey] = field(default_factory=frozenset, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stratum": self.stratum,
            "projected_cell_count": self.projected_cell_count,
            "new_cell_count": self.new_cell_count,
            "new_coverage_fraction": self.new_coverage_fraction,
            "same_plant_overlap_fraction": self.same_plant_overlap_fraction,
            "other_plant_overlap_fraction": self.other_plant_overlap_fraction,
            "daily_light_interception_proxy": (
                self.daily_light_interception_proxy
            ),
        }


class StratifiedLightField:
    """Track projected leaf occupancy for several daylight directions."""

    def __init__(
        self,
        *,
        strata: Iterable[CanopyStratum],
        sun_samples: Iterable[SunSample],
        cell_size: float,
        parameter_status: str = "engineering_heuristic",
    ) -> None:
        self.strata = tuple(strata)
        self.sun_samples = tuple(sun_samples)
        self.cell_size = float(cell_size)
        self.parameter_status = parameter_status
        if not self.strata:
            raise ValueError("At least one canopy stratum is required.")
        if not self.sun_samples:
            raise ValueError("At least one sun sample is required.")
        if self.cell_size <= 0.0:
            raise ValueError("Light-field cell_size must be positive.")
        for stratum in self.strata:
            if stratum.maximum_height <= stratum.minimum_height:
                raise ValueError(
                    f"Invalid canopy stratum bounds for {stratum.name!r}."
                )
        for sample in self.sun_samples:
            if not 1.0 <= sample.elevation_deg <= 89.0:
                raise ValueError("Sun-sample elevation must be within 1..89 degrees.")
            if sample.weight <= 0.0:
                raise ValueError("Sun-sample weight must be positive.")

        self._claims: dict[CellKey, list[tuple[str, str]]] = {}
        self._registered: list[dict[str, Any]] = []

    @classmethod
    def from_parameters(cls, parameters: dict[str, Any]) -> "StratifiedLightField":
        """Build the field from a normalized ``light_competition`` section."""
        strata_payload = parameters.get("strata", [])
        sun_payload = parameters.get("daily_sun_samples", [])
        return cls(
            strata=[
                CanopyStratum.from_dict(item)
                for item in strata_payload
                if isinstance(item, dict)
            ],
            sun_samples=[
                SunSample.from_dict(item)
                for item in sun_payload
                if isinstance(item, dict)
            ],
            cell_size=float(
                parameters.get("projected_cell_size", {}).get("value", 0.18)
            ),
            parameter_status=str(
                parameters.get("status", "engineering_heuristic")
            ),
        )

    def stratum_for_height(self, height: float) -> CanopyStratum:
        """Return the configured interval containing a world-space height."""
        for stratum in self.strata:
            if stratum.minimum_height <= height < stratum.maximum_height:
                return stratum
        if height < self.strata[0].minimum_height:
            return self.strata[0]
        return self.strata[-1]

    def evaluate_leaf(
        self,
        *,
        plant_id: str,
        start: Vec3,
        end: Vec3,
        width: float,
        include_other_plants: bool = True,
    ) -> LightCandidateEvaluation:
        """Estimate marginal daily projected coverage for a candidate leaf."""
        stratum = self.stratum_for_height((start[2] + end[2]) * 0.5)
        cells = self._projected_cells(
            start=start,
            end=end,
            width=max(float(width), self.cell_size * 0.25),
            stratum=stratum,
        )
        new_count = 0
        same_count = 0
        other_count = 0
        weighted_total = 0.0
        weighted_new = 0.0
        incidence_by_sample = self._incidence_by_sample(start, end)
        for cell in cells:
            sample_weight = self.sun_samples[cell[1]].weight
            weighted_total += sample_weight
            claims = self._claims.get(cell, [])
            relevant_claims = (
                claims
                if include_other_plants
                else [
                    claim
                    for claim in claims
                    if claim[0] == plant_id
                ]
            )
            if not relevant_claims:
                new_count += 1
                weighted_new += (
                    sample_weight * incidence_by_sample[cell[1]]
                )
                continue
            owners = {owner for owner, _leaf_id in relevant_claims}
            if plant_id in owners:
                same_count += 1
            if any(owner != plant_id for owner in owners):
                other_count += 1
        denominator = max(len(cells), 1)
        interception = weighted_new / max(weighted_total, 1e-9)
        return LightCandidateEvaluation(
            stratum=stratum.name,
            projected_cell_count=len(cells),
            new_cell_count=new_count,
            new_coverage_fraction=round(new_count / denominator, 6),
            same_plant_overlap_fraction=round(same_count / denominator, 6),
            other_plant_overlap_fraction=round(other_count / denominator, 6),
            daily_light_interception_proxy=round(interception, 6),
            cells=frozenset(cells),
        )

    def register_leaf(
        self,
        *,
        plant_id: str,
        leaf_id: str,
        evaluation: LightCandidateEvaluation,
    ) -> None:
        """Commit the selected leaf pose to the shared canopy field."""
        for cell in evaluation.cells:
            self._claims.setdefault(cell, []).append((plant_id, leaf_id))
        self._registered.append(
            {
                "plant_id": plant_id,
                "leaf_id": leaf_id,
                **evaluation.to_dict(),
            }
        )

    def summary(self) -> dict[str, Any]:
        """Return auditable stratum coverage and competition proxy metrics."""
        summaries: dict[str, dict[str, Any]] = {}
        for stratum in self.strata:
            records = [
                item
                for item in self._registered
                if item["stratum"] == stratum.name
            ]
            cells = {
                key: claims
                for key, claims in self._claims.items()
                if key[0] == stratum.name
            }
            interspecific_cells = 0
            intraspecific_cells = 0
            for claims in cells.values():
                plant_ids = [plant_id for plant_id, _leaf_id in claims]
                if len(set(plant_ids)) > 1:
                    interspecific_cells += 1
                if len(plant_ids) > len(set(plant_ids)):
                    intraspecific_cells += 1
            summaries[stratum.name] = {
                "leaf_count": len(records),
                "unique_projected_cell_count": len(cells),
                "observed_projected_fill_fraction": (
                    self._observed_fill_fraction(stratum.name)
                ),
                "mean_marginal_coverage_gain": _mean(
                    item["new_coverage_fraction"] for item in records
                ),
                "mean_daily_light_interception_proxy": _mean(
                    item["daily_light_interception_proxy"]
                    for item in records
                ),
                "intraspecific_shared_cell_fraction": round(
                    intraspecific_cells / max(len(cells), 1),
                    6,
                ),
                "interspecific_shared_cell_fraction": round(
                    interspecific_cells / max(len(cells), 1),
                    6,
                ),
            }
        return {
            "model": "stratified_daily_projected_gap_capture",
            "interpretation": (
                "Engineering proxy for projected light interception; not a "
                "photosynthesis or radiative-transfer estimate."
            ),
            "strata": summaries,
            "sun_sample_count": len(self.sun_samples),
            "projected_cell_size": self.cell_size,
            "registered_leaf_count": len(self._registered),
            "parameter_status": self.parameter_status,
        }

    def _projected_cells(
        self,
        *,
        start: Vec3,
        end: Vec3,
        width: float,
        stratum: CanopyStratum,
    ) -> set[CellKey]:
        direction_x = end[0] - start[0]
        direction_y = end[1] - start[1]
        horizontal_length = math.hypot(direction_x, direction_y)
        if horizontal_length <= 1e-9:
            direction_x, direction_y = 1.0, 0.0
        else:
            direction_x /= horizontal_length
            direction_y /= horizontal_length
        side_x, side_y = -direction_y, direction_x
        footprint_points: list[Vec3] = []
        for along in (0.28, 0.50, 0.72, 0.94):
            center = tuple(
                start[index] + (end[index] - start[index]) * along
                for index in range(3)
            )
            blade_profile = math.sin(math.pi * min(along / 0.94, 1.0))
            half_width = width * 0.5 * max(0.28, blade_profile)
            for across in (-1.0, 0.0, 1.0):
                footprint_points.append(
                    (
                        center[0] + side_x * half_width * across,
                        center[1] + side_y * half_width * across,
                        center[2],
                    )
                )

        cells: set[CellKey] = set()
        reference_height = stratum.minimum_height
        for sample_index, sample in enumerate(self.sun_samples):
            azimuth = math.radians(sample.azimuth_deg)
            tan_elevation = math.tan(math.radians(sample.elevation_deg))
            sun_x = math.cos(azimuth)
            sun_y = math.sin(azimuth)
            for point in footprint_points:
                projection_distance = max(
                    0.0,
                    (point[2] - reference_height) / max(tan_elevation, 1e-6),
                )
                projected_x = point[0] - sun_x * projection_distance
                projected_y = point[1] - sun_y * projection_distance
                cells.add(
                    (
                        stratum.name,
                        sample_index,
                        math.floor(projected_x / self.cell_size),
                        math.floor(projected_y / self.cell_size),
                    )
                )
        return cells

    def _incidence_by_sample(self, start: Vec3, end: Vec3) -> list[float]:
        """Approximate cosine interception from the candidate leaf plane."""
        blade = _normalise(
            tuple(end[index] - start[index] for index in range(3))
        )
        horizontal = math.hypot(blade[0], blade[1])
        if horizontal <= 1e-9:
            width_axis = (1.0, 0.0, 0.0)
        else:
            width_axis = (
                -blade[1] / horizontal,
                blade[0] / horizontal,
                0.0,
            )
        normal = _normalise(_cross(blade, width_axis))
        values: list[float] = []
        for sample in self.sun_samples:
            azimuth = math.radians(sample.azimuth_deg)
            elevation = math.radians(sample.elevation_deg)
            sun_direction = (
                math.cos(azimuth) * math.cos(elevation),
                math.sin(azimuth) * math.cos(elevation),
                math.sin(elevation),
            )
            values.append(
                max(
                    0.05,
                    min(1.0, abs(_dot(normal, sun_direction))),
                )
            )
        return values

    def _observed_fill_fraction(self, stratum_name: str) -> float:
        values: list[float] = []
        for sample_index in range(len(self.sun_samples)):
            coordinates = [
                (key[2], key[3])
                for key in self._claims
                if key[0] == stratum_name and key[1] == sample_index
            ]
            if not coordinates:
                continue
            minimum_x = min(item[0] for item in coordinates)
            maximum_x = max(item[0] for item in coordinates)
            minimum_y = min(item[1] for item in coordinates)
            maximum_y = max(item[1] for item in coordinates)
            area = (maximum_x - minimum_x + 1) * (maximum_y - minimum_y + 1)
            values.append(len(set(coordinates)) / max(area, 1))
        return round(_mean(values), 6)


def _mean(values: Iterable[float]) -> float:
    numbers = [float(value) for value in values]
    if not numbers:
        return 0.0
    return round(sum(numbers) / len(numbers), 6)


def _cross(left: Vec3, right: Vec3) -> Vec3:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _dot(left: Vec3, right: Vec3) -> float:
    return sum(left[index] * right[index] for index in range(3))


def _normalise(value: Vec3) -> Vec3:
    length = math.sqrt(_dot(value, value))
    if length <= 1e-12:
        return (0.0, 0.0, 1.0)
    return tuple(item / length for item in value)
