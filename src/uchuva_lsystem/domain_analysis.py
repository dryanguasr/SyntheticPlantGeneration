"""Read-only comparison helpers for real and synthetic YOLO datasets."""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
SPLITS = ("train", "val", "test")


def analyze_yolo_domain(
    name: str,
    images_root: str | Path,
    labels_root: str | Path,
    *,
    sample_luminance: bool = True,
    sample_context: bool = True,
    splits: Iterable[str] = SPLITS,
) -> dict[str, Any]:
    """Summarize image, label, box, and split properties without changing files."""
    image_root = Path(images_root)
    label_root = Path(labels_root)
    split_reports: dict[str, dict[str, Any]] = {}
    warnings: list[dict[str, Any]] = []
    all_image_ids: dict[str, list[str]] = {}

    selected_splits = tuple(splits)
    unknown_splits = sorted(set(selected_splits) - set(SPLITS))
    if not selected_splits or unknown_splits:
        raise ValueError(
            "splits must contain one or more of train, val, test; "
            f"unknown={unknown_splits}"
        )
    for split in selected_splits:
        report = _analyze_split(
            image_root / split,
            label_root / split,
            sample_luminance=sample_luminance,
            sample_context=sample_context,
        )
        split_reports[split] = report
        all_image_ids[split] = list(report.pop("image_ids"))
        for stem in report["missing_label_ids"]:
            warnings.append(
                {
                    "code": "missing_label",
                    "split": split,
                    "image_id": stem,
                    "message": f"Image {stem} has no YOLO label file.",
                }
            )
        for stem in report["orphan_label_ids"]:
            warnings.append(
                {
                    "code": "orphan_label",
                    "split": split,
                    "image_id": stem,
                    "message": f"Label {stem} has no matching image.",
                }
            )

    if {"val", "test"} <= set(selected_splits) and _numeric_ranges_overlap(
        all_image_ids["val"], all_image_ids["test"]
    ):
        warnings.append(
            {
                "code": "val_test_capture_correlation_risk",
                "split": "val,test",
                "message": (
                    "Validation and test numeric IDs occupy the same capture range; "
                    "audit consecutive images for correlated scenes before treating "
                    "the test score as independent."
                ),
            }
        )

    overall = _combine_split_reports(split_reports.values())
    for split_report in split_reports.values():
        split_report.pop("_raw", None)
    return {
        "name": name,
        "images_root": str(image_root.resolve()),
        "labels_root": str(label_root.resolve()),
        "selected_splits": list(selected_splits),
        "overall": overall,
        "splits": split_reports,
        "warnings": warnings,
    }


def compare_domain_reports(
    reference: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    """Return the two reports plus compact distribution-gap measurements."""
    reference_stats = reference["overall"]
    candidate_stats = candidate["overall"]
    percentage_pairs = [
        (reference_stats["orientation_rates_pct"], candidate_stats["orientation_rates_pct"]),
        (reference_stats["objects_per_image_band_rates_pct"], candidate_stats["objects_per_image_band_rates_pct"]),
        (reference_stats["box_area_band_rates_pct"], candidate_stats["box_area_band_rates_pct"]),
    ]
    gaps: list[float] = []
    for left, right in percentage_pairs:
        for key in sorted(set(left) | set(right)):
            gaps.append(abs(float(left.get(key, 0.0)) - float(right.get(key, 0.0))))
    gaps.append(
        abs(
            float(reference_stats["boundary_box_rate_pct"])
            - float(candidate_stats["boundary_box_rate_pct"])
        )
    )
    reference_luma = reference_stats.get("mean_luminance_quantiles", {}).get("p50")
    candidate_luma = candidate_stats.get("mean_luminance_quantiles", {}).get("p50")
    context_gaps: dict[str, float | None] = {}
    for metric in (
        "mean_luminance",
        "mean_saturation",
        "luminance_spread",
        "edge_energy",
    ):
        left = reference_stats.get("non_calyx_scene_context", {}).get(metric, {}).get("p50")
        right = candidate_stats.get("non_calyx_scene_context", {}).get(metric, {}).get("p50")
        context_gaps[metric] = (
            round(abs(float(left) - float(right)), 3)
            if left is not None and right is not None
            else None
        )
    return {
        "reference": reference,
        "candidate": candidate,
        "distance": {
            "composition_mean_absolute_gap_pct_points": round(statistics.mean(gaps), 3),
            "mean_luminance_median_gap": (
                round(abs(float(reference_luma) - float(candidate_luma)), 3)
                if reference_luma is not None and candidate_luma is not None
                else None
            ),
            "non_calyx_scene_context_median_gaps": context_gaps,
        },
    }


def write_domain_comparison(
    report: dict[str, Any], output_dir: str | Path
) -> tuple[Path, Path]:
    """Write deterministic JSON and Spanish Markdown summaries."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "domain_comparison.json"
    markdown_path = root / "domain_comparison.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    markdown_path.write_text(_comparison_markdown(report), encoding="utf-8", newline="\n")
    return json_path, markdown_path


def load_reference_profile(path: str | Path | None) -> dict[str, Any] | None:
    """Load either a domain report or a full comparison report."""
    if path is None:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if "reference" in payload:
        return payload["reference"]
    return payload


def _analyze_split(
    image_dir: Path,
    label_dir: Path,
    *,
    sample_luminance: bool,
    sample_context: bool,
) -> dict[str, Any]:
    images = sorted(
        path for path in image_dir.glob("*") if path.suffix.lower() in IMAGE_SUFFIXES
    ) if image_dir.exists() else []
    labels = sorted(label_dir.glob("*.txt")) if label_dir.exists() else []
    image_by_stem = {path.stem: path for path in images}
    label_by_stem = {path.stem: path for path in labels}
    object_counts: list[int] = []
    box_areas: list[float] = []
    pixel_aspects: list[float] = []
    luminance: list[float] = []
    orientations: Counter[str] = Counter()
    classes: Counter[str] = Counter()
    boundary_count = 0
    invalid_rows: list[str] = []
    context_metrics: list[dict[str, float]] = []

    for stem, image_path in image_by_stem.items():
        width, height, mean_luma = _image_metadata(
            image_path, sample_luminance=sample_luminance
        )
        orientations[_orientation(width, height)] += 1
        if mean_luma is not None:
            luminance.append(mean_luma)
        rows = []
        label_path = label_by_stem.get(stem)
        if label_path is not None:
            rows = [line for line in label_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        accepted = 0
        normalized_boxes: list[tuple[float, float, float, float]] = []
        for line_number, line in enumerate(rows, start=1):
            fields = line.split()
            if len(fields) != 5:
                invalid_rows.append(f"{label_path}:{line_number}:{line}")
                continue
            try:
                class_id = str(int(float(fields[0])))
                x, y, box_width, box_height = (float(value) for value in fields[1:])
            except ValueError:
                invalid_rows.append(f"{label_path}:{line_number}:{line}")
                continue
            accepted += 1
            normalized_boxes.append((x, y, box_width, box_height))
            classes[class_id] += 1
            box_areas.append(box_width * box_height)
            if box_height > 0.0:
                pixel_aspects.append((box_width * width) / (box_height * height))
            epsilon = 1e-7
            if (
                x - box_width / 2.0 <= epsilon
                or y - box_height / 2.0 <= epsilon
                or x + box_width / 2.0 >= 1.0 - epsilon
                or y + box_height / 2.0 >= 1.0 - epsilon
            ):
                boundary_count += 1
        object_counts.append(accepted)
        if sample_context:
            context_metrics.append(
                _non_calyx_scene_context_metrics(image_path, normalized_boxes)
            )

    orphan_stems = sorted(set(label_by_stem) - set(image_by_stem))
    return _statistics_payload(
        image_count=len(images),
        label_count=len(labels),
        object_counts=object_counts,
        box_areas=box_areas,
        pixel_aspects=pixel_aspects,
        orientations=orientations,
        classes=classes,
        boundary_count=boundary_count,
        luminance=luminance,
        missing_label_ids=sorted(set(image_by_stem) - set(label_by_stem)),
        orphan_label_ids=orphan_stems,
        invalid_rows=invalid_rows,
        image_ids=sorted(image_by_stem),
        context_metrics=context_metrics,
    )


def _combine_split_reports(reports: Iterable[dict[str, Any]]) -> dict[str, Any]:
    reports = list(reports)
    return _statistics_payload(
        image_count=sum(item["image_count"] for item in reports),
        label_count=sum(item["label_count"] for item in reports),
        object_counts=[value for item in reports for value in item["_raw"]["object_counts"]],
        box_areas=[value for item in reports for value in item["_raw"]["box_areas"]],
        pixel_aspects=[value for item in reports for value in item["_raw"]["pixel_aspects"]],
        orientations=Counter(
            {key: sum(item["orientation_counts"].get(key, 0) for item in reports) for key in ("portrait", "landscape", "square")}
        ),
        classes=Counter(
            {key: sum(item["class_counts"].get(key, 0) for item in reports) for key in set().union(*(item["class_counts"] for item in reports))}
        ),
        boundary_count=sum(item["boundary_box_count"] for item in reports),
        luminance=[value for item in reports for value in item["_raw"]["luminance"]],
        missing_label_ids=[value for item in reports for value in item["missing_label_ids"]],
        orphan_label_ids=[value for item in reports for value in item["orphan_label_ids"]],
        invalid_rows=[value for item in reports for value in item["invalid_rows"]],
        image_ids=[],
        context_metrics=[
            value
            for item in reports
            for value in item["_raw"]["context_metrics"]
        ],
        include_raw=False,
    )


def _statistics_payload(
    *,
    image_count: int,
    label_count: int,
    object_counts: list[int],
    box_areas: list[float],
    pixel_aspects: list[float],
    orientations: Counter[str],
    classes: Counter[str],
    boundary_count: int,
    luminance: list[float],
    missing_label_ids: list[str],
    orphan_label_ids: list[str],
    invalid_rows: list[str],
    image_ids: list[str],
    context_metrics: list[dict[str, float]],
    include_raw: bool = True,
) -> dict[str, Any]:
    object_bands = {
        "zero": sum(value == 0 for value in object_counts),
        "one_to_five": sum(1 <= value <= 5 for value in object_counts),
        "six_to_ten": sum(6 <= value <= 10 for value in object_counts),
        "more_than_ten": sum(value > 10 for value in object_counts),
    }
    area_bands = {
        "under_one_percent": sum(value < 0.01 for value in box_areas),
        "one_to_five_percent": sum(0.01 <= value < 0.05 for value in box_areas),
        "at_least_five_percent": sum(value >= 0.05 for value in box_areas),
    }
    result: dict[str, Any] = {
        "image_count": image_count,
        "label_count": label_count,
        "object_count": sum(object_counts),
        "objects_per_image_mean": _mean(object_counts),
        "objects_per_image_quantiles": _quantiles(object_counts),
        "objects_per_image_bands": object_bands,
        "objects_per_image_band_rates_pct": _rates(object_bands, image_count),
        "box_area_quantiles": _quantiles(box_areas),
        "box_area_bands": area_bands,
        "box_area_band_rates_pct": _rates(area_bands, len(box_areas)),
        "pixel_aspect_quantiles": _quantiles(pixel_aspects),
        "boundary_box_count": boundary_count,
        "boundary_box_rate_pct": _percentage(boundary_count, len(box_areas)),
        "orientation_counts": dict(sorted(orientations.items())),
        "orientation_rates_pct": _rates(orientations, image_count),
        "class_counts": dict(sorted(classes.items())),
        "mean_luminance_quantiles": _quantiles(luminance),
        "non_calyx_scene_context": {
            "proxy": "pixels_outside_yolo_boxes_expanded_by_10_percent",
            "excluded_box_expansion_fraction": 0.10,
            "sample_count": len(context_metrics),
            "mean_luminance": _quantiles(
                item["mean_luminance"] for item in context_metrics
            ),
            "mean_saturation": _quantiles(
                item["mean_saturation"] for item in context_metrics
            ),
            "luminance_spread": _quantiles(
                item["luminance_spread"] for item in context_metrics
            ),
            "edge_energy": _quantiles(
                item["edge_energy"] for item in context_metrics
            ),
            "interpretation_limit": (
                "Scene-context proxy only; unlabeled calyx pixels may remain outside boxes."
            ),
        },
        "missing_label_ids": missing_label_ids,
        "orphan_label_ids": orphan_label_ids,
        "invalid_rows": invalid_rows,
        "image_ids": image_ids,
    }
    if include_raw:
        result["_raw"] = {
            "object_counts": object_counts,
            "box_areas": box_areas,
            "pixel_aspects": pixel_aspects,
            "luminance": luminance,
            "context_metrics": context_metrics,
        }
    return result


def _image_metadata(path: Path, *, sample_luminance: bool) -> tuple[int, int, float | None]:
    try:
        from PIL import Image, ImageStat
    except ImportError as error:
        raise RuntimeError("Pillow is required to analyze image dimensions and luminance.") from error
    with Image.open(path) as image:
        width, height = image.size
        mean_luma = None
        if sample_luminance:
            preview = image.convert("L")
            preview.thumbnail((32, 32))
            mean_luma = round(float(ImageStat.Stat(preview).mean[0]), 3)
    return int(width), int(height), mean_luma


def _non_calyx_scene_context_metrics(
    path: Path,
    boxes: list[tuple[float, float, float, float]],
) -> dict[str, float]:
    """Measure aggregate context outside expanded annotation boxes."""
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageStat
    except ImportError as error:
        raise RuntimeError("Pillow is required for scene-context analysis.") from error
    with Image.open(path) as source:
        image = source.convert("RGB")
        image.thumbnail((256, 256))
    width, height = image.size
    mask = Image.new("L", image.size, 255)
    draw = ImageDraw.Draw(mask)
    for center_x, center_y, box_width, box_height in boxes:
        expanded_width = box_width * 1.10
        expanded_height = box_height * 1.10
        x0 = max(0, round((center_x - expanded_width / 2.0) * width))
        y0 = max(0, round((center_y - expanded_height / 2.0) * height))
        x1 = min(width - 1, round((center_x + expanded_width / 2.0) * width))
        y1 = min(height - 1, round((center_y + expanded_height / 2.0) * height))
        draw.rectangle((x0, y0, x1, y1), fill=0)
    luma = image.convert("L")
    saturation = image.convert("HSV").getchannel("S")
    edges = luma.filter(ImageFilter.FIND_EDGES)
    luma_stat = ImageStat.Stat(luma, mask=mask)
    saturation_stat = ImageStat.Stat(saturation, mask=mask)
    edge_stat = ImageStat.Stat(edges, mask=mask)
    return {
        "mean_luminance": round(float(luma_stat.mean[0]), 3),
        "mean_saturation": round(float(saturation_stat.mean[0]), 3),
        "luminance_spread": round(float(luma_stat.stddev[0]), 3),
        "edge_energy": round(float(edge_stat.mean[0]), 3),
    }


def _orientation(width: int, height: int) -> str:
    if height > width:
        return "portrait"
    if width > height:
        return "landscape"
    return "square"


def _quantiles(values: Iterable[float | int]) -> dict[str, float | int | None]:
    ordered = sorted(values)
    if not ordered:
        return {key: None for key in ("min", "p10", "p25", "p50", "p75", "p90", "max")}
    positions = {"min": 0.0, "p10": 0.1, "p25": 0.25, "p50": 0.5, "p75": 0.75, "p90": 0.9, "max": 1.0}
    return {key: ordered[round((len(ordered) - 1) * position)] for key, position in positions.items()}


def _mean(values: list[int]) -> float:
    return round(statistics.mean(values), 3) if values else 0.0


def _percentage(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 3) if denominator else 0.0


def _rates(counts: dict[str, int] | Counter[str], denominator: int) -> dict[str, float]:
    return {key: _percentage(int(value), denominator) for key, value in sorted(counts.items())}


def _numeric_ranges_overlap(left: list[str], right: list[str]) -> bool:
    try:
        left_numbers = [int(value) for value in left]
        right_numbers = [int(value) for value in right]
    except ValueError:
        return False
    return bool(left_numbers and right_numbers and max(min(left_numbers), min(right_numbers)) <= min(max(left_numbers), max(right_numbers)))


def _comparison_markdown(report: dict[str, Any]) -> str:
    reference = report["reference"]
    candidate = report["candidate"]
    left = reference["overall"]
    right = candidate["overall"]
    left_context = left.get("non_calyx_scene_context", {})
    right_context = right.get("non_calyx_scene_context", {})
    lines = [
        "# Comparación de dominio real y sintético",
        "",
        f"Referencia: **{reference['name']}**. Candidato: **{candidate['name']}**.",
        "",
        "| Métrica | Real | Sintético |",
        "|---|---:|---:|",
        f"| Imágenes | {left['image_count']} | {right['image_count']} |",
        f"| Objetos por imagen, mediana | {left['objects_per_image_quantiles']['p50']} | {right['objects_per_image_quantiles']['p50']} |",
        f"| Orientación vertical | {left['orientation_rates_pct'].get('portrait', 0):.1f}% | {right['orientation_rates_pct'].get('portrait', 0):.1f}% |",
        f"| Cajas truncadas | {left['boundary_box_rate_pct']:.1f}% | {right['boundary_box_rate_pct']:.1f}% |",
        f"| Luminancia mediana | {left['mean_luminance_quantiles']['p50']} | {right['mean_luminance_quantiles']['p50']} |",
        f"| Contexto: energía de borde mediana | {left_context.get('edge_energy', {}).get('p50')} | {right_context.get('edge_energy', {}).get('p50')} |",
        f"| Contexto: dispersión de luminancia mediana | {left_context.get('luminance_spread', {}).get('p50')} | {right_context.get('luminance_spread', {}).get('p50')} |",
        f"| Contexto: saturación mediana | {left_context.get('mean_saturation', {}).get('p50')} | {right_context.get('mean_saturation', {}).get('p50')} |",
        "",
        f"Brecha media de composición: **{report['distance']['composition_mean_absolute_gap_pct_points']:.2f} puntos porcentuales**.",
        "",
        "El contexto se estima fuera de cajas YOLO expandidas 10%; es un proxy de escena, no segmentación semántica.",
        "",
        "## Advertencias de la referencia",
        "",
    ]
    lines.extend(
        f"- `{item['code']}`: {item['message']}" for item in reference["warnings"]
    )
    if not reference["warnings"]:
        lines.append("- Sin advertencias.")
    return "\n".join(lines) + "\n"
