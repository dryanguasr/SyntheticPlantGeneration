"""Export and validate the existing calyx checkpoint for the offline Android app.

No training or test data are accessed. Only an explicitly named val directory is
accepted. Outputs are prepared atomically after equivalence checks pass.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DEPS = ROOT / "outputs/mobile/python-deps"
if DEPS.exists():
    sys.path.insert(0, str(DEPS))
os.environ["YOLO_AUTOINSTALL"] = "false"
os.environ.setdefault("YOLO_CONFIG_DIR", str(ROOT / "outputs/mobile/ultralytics-config"))
Path(os.environ["YOLO_CONFIG_DIR"]).mkdir(parents=True, exist_ok=True)
DEFAULT_CHECKPOINT = ROOT / "outputs/experiments/checkpoint_interpolation_scale80_seed_1000_v1/interpolated_checkpoints/natural_hybrid_alpha_045.pt"
EXPORT_VERSION = "1.0"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def letterbox_rgb(image):
    import cv2
    import numpy as np
    height, width = image.shape[:2]
    ratio = min(640 / width, 640 / height)
    resized = cv2.resize(image, (round(width * ratio), round(height * ratio)), interpolation=cv2.INTER_LINEAR)
    top = (640 - resized.shape[0]) // 2
    left = (640 - resized.shape[1]) // 2
    padded = np.full((640, 640, 3), 114, dtype=np.uint8)
    padded[top:top + resized.shape[0], left:left + resized.shape[1]] = resized
    return np.ascontiguousarray(padded[:, :, ::-1].transpose(2, 0, 1)[None], dtype=np.float32) / 255


def match_predictions(reference, candidate, threshold=0.25):
    """Greedy score-independent matching, accounting for TopK order permutations."""
    import numpy as np
    ref = reference[reference[:, 4] >= threshold]
    out = candidate[candidate[:, 4] >= threshold]
    if len(ref) != len(out):
        raise ValueError(f"Detection count differs: {len(ref)} vs {len(out)}")
    unmatched = set(range(len(out)))
    min_iou, max_delta = 1.0, 0.0
    for row in ref:
        best = None
        for j in unmatched:
            other = out[j]
            if row[5] != other[5]:
                continue
            low = np.maximum(row[:2], other[:2]); high = np.minimum(row[2:4], other[2:4])
            intersection = float(np.prod(np.maximum(high - low, 0)))
            area = float(np.prod(row[2:4] - row[:2]) + np.prod(other[2:4] - other[:2]))
            iou = intersection / max(area - intersection, 1e-9)
            if best is None or iou > best[0]:
                best = (iou, j)
        if best is None:
            raise ValueError("Missing class match")
        iou, j = best
        delta = abs(float(row[4] - out[j, 4]))
        if iou < 0.99 or delta > 0.001:
            raise ValueError(f"Equivalence failed: IoU={iou}, confidence delta={delta}")
        unmatched.remove(j)
        min_iou = min(min_iou, iou); max_delta = max(max_delta, delta)
    return {"count": len(ref), "min_iou": min_iou, "max_confidence_delta": max_delta}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--validation-dir", type=Path, default=ROOT / "Dataset Original/IMAGENES/val")
    parser.add_argument("--sample-count", type=int, default=20)
    args = parser.parse_args()
    validation_dir = args.validation_dir.resolve()
    if validation_dir.name != "val" or "test" in {p.lower() for p in validation_dir.parts}:
        raise SystemExit("Use an explicit val directory; test is forbidden.")
    if args.sample_count < 1:
        raise SystemExit("sample-count must be positive")
    images = sorted(p for p in validation_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})[:args.sample_count]
    if len(images) != args.sample_count:
        raise SystemExit("Not enough validation images")

    import cv2
    import numpy as np
    import onnx
    import onnxruntime as ort
    import torch
    from ultralytics import YOLO

    torch.set_num_threads(4)
    output = ROOT / "outputs/mobile/model"
    output.mkdir(parents=True, exist_ok=True)
    staged = output / "detector.pt"
    shutil.copy2(args.checkpoint, staged)
    detector = YOLO(str(staged))
    if detector.names != {0: "calyx"} or not detector.model.model[-1].end2end:
        raise SystemExit("Expected single-class calyx end2end checkpoint")
    exported = Path(detector.export(format="onnx", imgsz=640, batch=1, dynamic=False, simplify=False, opset=17, nms=False, device="cpu"))
    onnx.checker.check_model(str(exported))
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    session = ort.InferenceSession(str(exported), options, providers=["CPUExecutionProvider"])
    input_meta = session.get_inputs()[0]
    output_meta = session.get_outputs()[0]
    if input_meta.shape != [1, 3, 640, 640] or output_meta.shape[0] != 1 or output_meta.shape[-1] != 6:
        raise ValueError(f"Unexpected ONNX contract: {input_meta.shape}, {output_meta.shape}")
    model = YOLO(str(staged)).model.float().eval()
    records = []
    for image in images:
        pixels = cv2.imread(str(image))
        if pixels is None:
            raise ValueError(f"Unreadable image: {image}")
        tensor = letterbox_rgb(pixels)
        with torch.inference_mode():
            raw = model(torch.from_numpy(tensor))
            reference = (raw[0] if isinstance(raw, tuple) else raw).cpu().numpy()[0]
        start = time.perf_counter()
        candidate = session.run(None, {input_meta.name: tensor})[0][0]
        elapsed_ms = (time.perf_counter() - start) * 1000
        record = {"image": image.name, "sha256": sha256(image), "onnx_cpu_ms": elapsed_ms, **match_predictions(reference, candidate)}
        records.append(record)
        print(f"Validated {image.name}: {record['count']} detections", flush=True)
    versions = {name: importlib.metadata.version(name) for name in ("ultralytics", "torch", "onnx", "onnxruntime", "opencv-python")}
    manifest = {
        "schema_version": "1.0", "exporter_version": EXPORT_VERSION,
        "model_version": args.checkpoint.stem, "source_checkpoint_sha256": sha256(args.checkpoint),
        "model_sha256": sha256(exported), "created_at": datetime.now(timezone.utc).isoformat(),
        "classes": {"0": "calyx"}, "input_name": input_meta.name, "input_shape": input_meta.shape,
        "input_dtype": "float32", "input_color": "RGB", "input_layout": "NCHW",
        "normalization": "pixel / 255", "letterbox_padding": 114,
        "output_shape": output_meta.shape, "output_columns": ["x1", "y1", "x2", "y2", "confidence", "class_id"],
        "end2end": True, "additional_nms": False, "opset": 17, "versions": versions,
    }
    report = {"status": "passed", "split": "val", "selection": "filename_sorted_first_n", "threshold": 0.25,
              "acceptance": {"min_iou": 0.99, "max_confidence_delta": 0.001}, "records": records,
              "mean_onnx_cpu_ms": float(np.mean([r["onnx_cpu_ms"] for r in records])),
              "physical_phone_tests": "pending_device", "model_sha256": manifest["model_sha256"]}
    (output / "validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assets = ROOT / "mobile/android/app/src/main/assets"
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exported, assets / "detector.onnx.tmp")
    (assets / "model_manifest.json.tmp").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (assets / "detector.onnx.tmp").replace(assets / "detector.onnx")
    (assets / "model_manifest.json.tmp").replace(assets / "model_manifest.json")
    (output / "model_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    # A lossless, ignored fixture checks the Android decoder/preprocessor/runtime together.
    fixture_image = cv2.imread(str(images[0]))
    fixture_rows = session.run(None, {input_meta.name: letterbox_rgb(fixture_image)})[0][0]
    height, width = fixture_image.shape[:2]
    ratio = min(640 / width, 640 / height)
    left, top = (640 - round(width * ratio)) // 2, (640 - round(height * ratio)) // 2
    fixture_detections = []
    for row in fixture_rows[fixture_rows[:, 4] >= 0.25]:
        box = (row[:4] - np.array([left, top, left, top])) / ratio
        box = np.clip(box, 0, [width, height, width, height])
        fixture_detections.append({"box": box.tolist(), "confidence": float(row[4]), "class_id": int(row[5])})
    fixture_assets = ROOT / "mobile/android/app/src/androidTest/assets"
    fixture_assets.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(fixture_assets / "mobile_validation_fixture.png"), fixture_image)
    (fixture_assets / "mobile_validation_fixture.json").write_text(json.dumps({
        "source": images[0].name, "source_sha256": sha256(images[0]), "split": "val",
        "model_sha256": manifest["model_sha256"], "detections": fixture_detections,
    }, indent=2), encoding="utf-8")
    print(json.dumps({"assets": str(assets), "report": str(output / "validation_report.json")}, indent=2))


if __name__ == "__main__":
    main()
