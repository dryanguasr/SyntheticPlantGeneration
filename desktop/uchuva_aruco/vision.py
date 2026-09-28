"""Same FP32, RGB letterbox, end2end and planar conventions as Android."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time

import cv2
import numpy as np

from . import APP_VERSION


@dataclass(frozen=True)
class Settings:
    side_cm: float | None = None
    confidence: float = 0.25
    dictionary: str = "DICT_4X4_50"

    def __post_init__(self):
        if self.dictionary not in {"DICT_4X4_50", "DICT_4X4_100"}:
            raise ValueError("Diccionario ArUco no compatible")
        if self.side_cm is not None and not (math.isfinite(self.side_cm) and 0.1 <= self.side_cm <= 1000):
            raise ValueError("Introduce el lado negro real entre 0.1 y 1000 cm")
        if not 0.05 <= self.confidence <= 0.95:
            raise ValueError("La confianza debe estar entre 0.05 y 0.95")


def letterbox(image):
    height, width = image.shape[:2]
    scale = min(640 / width, 640 / height)
    rw, rh = round(width * scale), round(height * scale)
    left, top = (640 - rw) // 2, (640 - rh) // 2
    padded = np.full((640, 640, 3), 114, np.uint8)
    padded[top:top + rh, left:left + rw] = cv2.resize(image, (rw, rh), interpolation=cv2.INTER_LINEAR)
    tensor = np.ascontiguousarray(padded[:, :, ::-1].transpose(2, 0, 1)[None], dtype=np.float32) / 255
    return tensor, scale, left, top


def mapping(corners, side):
    """Reject small, nonconvex and nearly collinear quads (engineering heuristics)."""
    p = np.asarray(corners, np.float64)
    if p.shape != (4, 2) or not np.isfinite(p).all():
        return None
    edges = np.roll(p, -1, axis=0) - p
    cross = edges[:, 0] * np.roll(edges[:, 1], -1) - edges[:, 1] * np.roll(edges[:, 0], -1)
    span = np.ptp(p, axis=0).max()
    area = abs(cv2.contourArea(p.astype(np.float32)))
    if (np.linalg.norm(edges, axis=1).min() < 24 or area < 576 or
            area / max(span * span, 1e-9) < .04 or not ((cross > 1).all() or (cross < -1).all())):
        return None
    half = side / 2
    target = np.array([[-half, half], [half, half], [half, -half], [-half, -half]], np.float32)
    h = cv2.getPerspectiveTransform(p.astype(np.float32), target)
    center_denominator = float(h[2] @ np.r_[p.mean(axis=0), 1])
    if not np.isfinite(h).all() or abs(center_denominator) < 1e-10 or abs(np.linalg.det(h)) < 1e-12:
        return None
    return h / center_denominator


def project(h, point):
    if h is None:
        return None
    p = h @ np.r_[point, 1.0]
    if not np.isfinite(p).all() or p[2] < 1e-8:
        return None
    x, y = p[:2] / p[2]
    return {"x": float(x), "y": float(y), "distance": float(math.hypot(x, y))}


def grid_lines(h, side, width, height):
    """Infinite metric coordinate lines clipped to the image, capped at 80 per axis."""
    boundary = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], float)
    samples = [project(h, a + (b-a)*t) for a, b in zip(boundary, np.roll(boundary, -1, axis=0))
               for t in np.linspace(0, 1, 33)]
    samples = [p for p in samples if p]
    if not samples:
        return []
    lines = []
    for axis, name in enumerate(("x", "y")):
        low, high = min(0, min(p[name] for p in samples)), max(0, max(p[name] for p in samples))
        step = side / 2
        while (high - low) / step > 80:
            step *= 2
        for i in range(math.floor(low / step), math.ceil(high / step) + 1):
            line = h[axis] - (i * step) * h[2]
            points = []
            for a, b in zip(boundary, np.roll(boundary, -1, axis=0)):
                va, vb = line @ np.r_[a, 1], line @ np.r_[b, 1]
                if abs(va - vb) < 1e-12:
                    continue
                t = va / (va - vb)
                if 0 <= t <= 1:
                    p = a + t*(b-a)
                    if not any(np.linalg.norm(p-q) < 1e-5 for q in points):
                        points.append(p)
            if len(points) >= 2 and project(h, points[0]) and project(h, points[-1]):
                lines.append((points[0], points[-1], i == 0))
    return lines


def resolve(markers, side_cm, selected):
    counts = Counter(m["id"] for m in markers)
    refs, transforms = [], {}
    for index, marker in enumerate(markers):
        h = mapping(marker["corners_px"], side_cm or 10)
        state = ("ambiguous" if counts[marker["id"]] > 1 else "degenerate" if h is None else
                 "size_unconfirmed" if side_cm is None else "valid")
        refs.append(dict(observation_index=index, marker_id=marker["id"], corners_px=marker["corners_px"],
                         state=state, side_cm=side_cm, selected=selected == marker["id"],
                         origin="marker_center", axes="x_marker_right_y_marker_up"))
        transforms[index] = h
    return sorted(refs, key=lambda r: (r["marker_id"], r["observation_index"])), transforms


class VisionEngine:
    def __init__(self, assets: Path):
        import onnxruntime as ort
        self.manifest = json.loads((assets / "model_manifest.json").read_text(encoding="utf-8"))
        model = assets / "detector.onnx"
        with model.open("rb") as f:
            self.model_hash = hashlib.file_digest(f, "sha256").hexdigest()
        if self.model_hash != self.manifest["model_sha256"]:
            raise ValueError("Modelo distinto del manifiesto")
        if not self.manifest["end2end"] or self.manifest["additional_nms"] or self.manifest["classes"] != {"0": "calyx"}:
            raise ValueError("Contrato del detector incompatible")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(model), options, providers=["CPUExecutionProvider"])
        self.input_name = self.manifest["input_name"]
        if self.session.get_inputs()[0].shape != [1, 3, 640, 640]:
            raise ValueError("Se requiere entrada FP32 1x3x640x640")
        params = cv2.aruco.DetectorParameters()
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        self.arucos = {name: cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, name)), params)
                       for name in ("DICT_4X4_50", "DICT_4X4_100")}

    def analyze(self, image, settings: Settings, frame_id=0, source_kind="file", selected=None,
                received_at=None, media_time_ms=None):
        start = time.perf_counter()
        height, width = image.shape[:2]
        tensor, scale, left, top = letterbox(image)
        rows = self.session.run(None, {self.input_name: tensor})[0]
        if rows.ndim != 3 or rows.shape[0] != 1 or rows.shape[2] != 6:
            raise ValueError("Salida end2end incompatible")
        corners, ids, _ = self.arucos[settings.dictionary].detectMarkers(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
        markers = [] if ids is None else [{"id": int(i), "corners_px": p.reshape(4, 2).tolist()} for p, i in zip(corners, ids.ravel())]
        if selected is None and len(markers) == 1:
            selected = markers[0]["id"]
        refs, transforms = resolve(markers, settings.side_cm, selected)
        matching = [r for r in refs if r["marker_id"] == selected]
        ref_state = ("no_selection" if selected is None else "missing" if not matching else
                     "ambiguous" if len(matching) > 1 else matching[0]["state"])
        detections = []
        for row in rows[0]:
            if not np.isfinite(row).all() or row[4] < settings.confidence or row[5] != 0:
                continue
            box = (row[:4].astype(float) - [left, top, left, top]) / scale
            box = np.clip(box, [0, 0, 0, 0], [width, height, width, height])
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            center = (box[:2] + box[2:]) / 2
            positions = []
            for ref in refs:
                pos = project(transforms[ref["observation_index"]], center) if ref["state"] == "valid" else None
                positions.append(dict(observation_index=ref["observation_index"], marker_id=ref["marker_id"],
                                      state=ref["state"], reference_state=ref["state"], position_cm=pos,
                                      position_status="estimated" if pos else "unavailable"))
            selected_positions = [p["position_cm"] for p in positions if p["marker_id"] == selected]
            pos = selected_positions[0] if len(selected_positions) == 1 else None
            detections.append(dict(class_id=0, class_name="calyx", confidence=float(row[4]), box_xyxy_px=box.tolist(),
                                   center_px=center.tolist(), positions_by_marker=positions, position_cm=pos,
                                   position_status="estimated" if pos else "unavailable"))
        received_at = received_at or datetime.now(timezone.utc).isoformat()
        result = dict(schema_version="1.4", app_version=APP_VERSION, model_sha256=self.model_hash,
                      model_version=self.manifest["model_version"], frame_id=frame_id, captured_at=received_at,
                      camera_timestamp_ns=None,
                      source=dict(kind=source_kind, received_at=received_at, media_time_ms=media_time_ms,
                                  drone_capture_time_known=False, timestamp_basis="receiver_clock"),
                      image=dict(width=width, height=height, rotation_applied_degrees=0, coordinates="upright_analysis_pixels"),
                      confidence_threshold=settings.confidence, markers=markers, references=refs, detections=detections,
                      reference=dict(dictionary=settings.dictionary, selected_id=selected, side_cm=settings.side_cm,
                                     size_confirmed=settings.side_cm is not None, state=ref_state,
                                     origin="marker_center", axes="x_marker_right_y_marker_up"),
                      estimation=dict(method="marker_plane_homography", status="estimated", label="Estimación sobre el plano del ArUco",
                                      lens_distortion_corrected=False, object_depth_measured=False, point="bounding_box_center",
                                      geometric_threshold_provenance="engineering_heuristic"),
                      analysis_ms=(time.perf_counter()-start)*1000)
        return annotate(image, result, transforms), result


def marker_color(marker_id):
    hsv = np.uint8([[[int(marker_id * 67 % 360 / 2), 180, 255]]])
    return tuple(int(v) for v in cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0])


def annotate(image, result, transforms):
    output = image.copy()
    height, width = output.shape[:2]
    grid = output.copy()
    def pixel(p):
        return tuple(np.rint(p).astype(int))
    for ref in result["references"]:
        h = transforms[ref["observation_index"]]
        color = marker_color(ref["marker_id"])
        if h is not None:
            for a, b, axis in grid_lines(h, ref["side_cm"] or 10, width, height):
                cv2.line(grid, pixel(a), pixel(b), color, 2 if axis else 1, cv2.LINE_AA)
    cv2.addWeighted(grid, .30, output, .70, 0, output)
    for ref in result["references"]:
        color = marker_color(ref["marker_id"])
        points = np.array(ref["corners_px"], np.int32)
        cv2.polylines(output, [points], True, color, 3 if ref["selected"] else 2, cv2.LINE_AA)
        p = points[0].copy(); p[1] = max(16, p[1]-6)
        cv2.putText(output, f'ArUco {ref["marker_id"]}', pixel(p), cv2.FONT_HERSHEY_SIMPLEX, .5, color, 1, cv2.LINE_AA)
        h = transforms[ref["observation_index"]]
        if h is not None:
            inv = np.linalg.inv(h)
            pts = cv2.perspectiveTransform(np.array([[[0., 0.], [(ref["side_cm"] or 10)/2, 0.], [0., (ref["side_cm"] or 10)/2]]]), inv)[0]
            if np.isfinite(pts).all() and np.abs(pts).max() < 1e6:
                for end, label in zip(pts[1:], ("X+", "Y+")):
                    cv2.arrowedLine(output, pixel(pts[0]), pixel(end), color, 2, tipLength=.15)
                    cv2.putText(output, label, pixel(end), cv2.FONT_HERSHEY_SIMPLEX, .5, color, 1, cv2.LINE_AA)
    for index, det in enumerate(result["detections"]):
        x1, y1, x2, y2 = np.rint(det["box_xyxy_px"]).astype(int)
        cv2.rectangle(output, (x1, y1), (x2, y2), (140, 240, 180), 2)
        lines = [(f'Capacho {index+1} | {det["confidence"]:.0%}', (255, 255, 255))]
        for pos in det["positions_by_marker"]:
            p = pos["position_cm"]
            label = (f'X {p["x"]:+.1f} Y {p["y"]:+.1f} d {p["distance"]:.1f} cm' if p else
                     "confirma lado en cm" if pos["state"] == "size_unconfirmed" else "no disponible")
            color = (236, 218, 99) if pos["marker_id"] == result["reference"]["selected_id"] else marker_color(pos["marker_id"])
            lines.append((f'ArUco {pos["marker_id"]} | {label}', color))
        if len(lines) == 1:
            lines.append(("Sin marcador de referencia", (255, 255, 255)))
        font = min(.5, (height-12) / (max(1, len(lines)) * 32))
        longest = max(cv2.getTextSize(s, cv2.FONT_HERSHEY_SIMPLEX, font, 1)[0][0] for s, _ in lines)
        if longest + 12 > width:
            font *= (width-12) / (longest+1)
        line_height = max(8, round(font*32))
        card_width = min(width, 12 + max(cv2.getTextSize(s, cv2.FONT_HERSHEY_SIMPLEX, font, 1)[0][0] for s, _ in lines))
        card_height = min(height, line_height * len(lines) + 8)
        x = x2 + 6 if x2 + 6 + card_width <= width else x1 - 6 - card_width
        x, y = max(0, min(x, width-card_width)), max(0, min(y1, height-card_height))
        cv2.rectangle(output, (x, y), (x+card_width, y+card_height), (20, 28, 24), -1)
        for n, (label, color) in enumerate(lines):
            cv2.putText(output, label, (x+5, y+line_height*(n+1)), cv2.FONT_HERSHEY_SIMPLEX, font, color, 1, cv2.LINE_AA)
    cv2.rectangle(output, (0, height-24), (width, height), (20, 28, 24), -1)
    cv2.putText(output, "Estimacion sobre el plano ArUco | Sin profundidad ni correccion de lente", (5, height-8),
                cv2.FONT_HERSHEY_SIMPLEX, min(.45, width/1800), (255, 255, 255), 1, cv2.LINE_AA)
    return output
