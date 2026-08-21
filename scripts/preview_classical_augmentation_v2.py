"""Create original | augmented | bbox-overlay contact sheets for v2 datasets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_classical_augmentation.v2.labels import read_yolo_labels
from uchuva_classical_augmentation.v2.manifest import read_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=REPO_ROOT / "Dataset Original")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--samples", type=int, default=12)
    return parser.parse_args()


def main() -> None:
    import cv2
    import numpy as np

    args = parse_args()
    dataset_dir = args.dataset_dir.resolve()
    records = read_jsonl(dataset_dir / "manifests" / "derived_samples.jsonl")[: args.samples]
    rows = []
    for record in records:
        source = cv2.imread(str(args.source_root / "IMAGENES" / "train" / record.source_image_id))
        derived_path = dataset_dir / "images" / "train" / record.derived_image_id
        derived = cv2.imread(str(derived_path))
        if source is None or derived is None:
            continue
        overlay = derived.copy()
        labels = read_yolo_labels(dataset_dir / "labels" / "train" / f"{derived_path.stem}.txt")
        for box in labels:
            x1, y1, x2, y2 = box.to_xyxy_pixels(overlay.shape[1], overlay.shape[0])
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 255), 2)
        source = _fit(source, 420, 300)
        derived = _fit(derived, 420, 300)
        overlay = _fit(overlay, 420, 300)
        rows.append(np.hstack([source, derived, overlay]))
    if not rows:
        raise RuntimeError("No derived samples available for preview")
    sheet = np.vstack(rows)
    output = args.output or dataset_dir / "preview_contact_sheet.jpg"
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), sheet, [cv2.IMWRITE_JPEG_QUALITY, 92]):
        raise RuntimeError(f"Could not write {output}")
    print(output.resolve())


def _fit(image, width: int, height: int):
    import cv2
    import numpy as np

    source_height, source_width = image.shape[:2]
    scale = min(width / source_width, height / source_height)
    resized = cv2.resize(image, (round(source_width * scale), round(source_height * scale)), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    y = (height - resized.shape[0]) // 2
    x = (width - resized.shape[1]) // 2
    canvas[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    return canvas


if __name__ == "__main__":
    main()
