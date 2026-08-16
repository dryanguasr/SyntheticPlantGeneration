"""Create a deterministic annotated contact sheet from a generated dataset."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _records(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _even_indices(length: int, count: int) -> list[int]:
    if count >= length:
        return list(range(length))
    if count == 1:
        return [length // 2]
    return [round(index * (length - 1) / (count - 1)) for index in range(count)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--columns", type=int, default=4)
    args = parser.parse_args()
    records = _records(args.dataset_root / "manifest.jsonl")
    selected = [records[index] for index in _even_indices(len(records), args.count)]
    tile_width, tile_height, label_height = 360, 270, 34
    rows = math.ceil(len(selected) / args.columns)
    sheet = Image.new(
        "RGB", (args.columns * tile_width, rows * (tile_height + label_height)), "#202020"
    )
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for position, record in enumerate(selected):
        source_path = args.dataset_root / record["image_path"]
        with Image.open(source_path) as source:
            image = source.convert("RGB")
        original_width, original_height = image.size
        image.thumbnail((tile_width, tile_height), Image.Resampling.LANCZOS)
        x0 = (position % args.columns) * tile_width
        y0 = (position // args.columns) * (tile_height + label_height)
        offset_x = x0 + (tile_width - image.width) // 2
        offset_y = y0 + (tile_height - image.height) // 2
        sheet.paste(image, (offset_x, offset_y))
        scale_x = image.width / original_width
        scale_y = image.height / original_height
        for detection in record.get("detections", []):
            box_x, box_y, box_width, box_height = detection["bbox_xywh"]
            draw.rectangle(
                (
                    offset_x + box_x * scale_x,
                    offset_y + box_y * scale_y,
                    offset_x + (box_x + box_width) * scale_x,
                    offset_y + (box_y + box_height) * scale_y,
                ),
                outline="#ff4f45",
                width=2,
            )
        caption = (
            f"{record['scene_id']} | {record.get('camera_profile')} | "
            f"n={record.get('accepted_detection_count', len(record.get('detections', [])))}"
        )
        draw.text((x0 + 5, y0 + tile_height + 8), caption, fill="white", font=font)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
