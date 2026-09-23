"""Export selected originals and resized copies with asymmetric mirror padding."""
import argparse
from collections import Counter
from pathlib import Path
import shutil
import sys

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from uchuva_dataset_curation import digest, read_rows, write_json, write_rows


def letterbox(image, size):
    height, width = image.shape[:2]
    scale = min(size / width, size / height)
    rw, rh = max(1, round(width * scale)), max(1, round(height * scale))
    left, top = (size - rw) // 2, (size - rh) // 2
    right, bottom = size - rw - left, size - rh - top
    resized = cv2.resize(image, (rw, rh), interpolation=cv2.INTER_LINEAR)
    result = cv2.copyMakeBorder(resized, 0, bottom, left, right, cv2.BORDER_REFLECT_101)
    result = cv2.copyMakeBorder(result, top, 0, 0, 0, cv2.BORDER_CONSTANT, value=(114, 114, 114))
    assert result.shape[:2] == (size, size)
    assert np.array_equal(result[top:top + rh, left:left + rw], resized)
    assert not top or np.all(result[:top] == 114)
    return result, dict(scale=scale, resized_width=rw, resized_height=rh,
                        pad_left=left, pad_right=right, pad_top=top, pad_bottom=bottom)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", type=int, required=True)
    args = parser.parse_args()
    if args.size < 2 or args.output.exists():
        parser.error("Use a new output directory and a size of at least two pixels")
    rows = read_rows(args.parent / "export_manifest.jsonl")
    records = {r["image_id"]: r for r in read_rows(args.parent / "manifest.jsonl")}
    args.output.mkdir(parents=True)
    manifest = []
    for row in rows:
        source = args.parent / row["path"]
        assert digest(source) == row["sha256"]
        original = args.output / "originals" / row["split"] / source.name
        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, original)
        image = cv2.imread(str(source))
        if image is None:
            raise ValueError(f"Unreadable: {source}")
        rendered, geometry = letterbox(image, args.size)
        target = args.output / f"images_{args.size}x{args.size}" / row["split"] / (source.stem + ".png")
        target.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(target), rendered):
            raise ValueError(f"Failed export: {target}")
        assert np.array_equal(cv2.imread(str(target)), rendered)
        assert digest(original) == row["sha256"]
        manifest.append(dict(image_id=row["image_id"], split=row["split"], group_id=row["group_id"],
                             source=records[row["image_id"]]["source"],
                             original_path=original.relative_to(args.output).as_posix(),
                             output_path=target.relative_to(args.output).as_posix(),
                             original_sha256=row["sha256"], output_sha256=digest(target), **geometry))
    write_rows(args.output / "manifest.csv", manifest)
    write_rows(args.output / "manifest.jsonl", manifest)
    write_json(args.output / "preprocessing.json", dict(
        parent=str(args.parent.resolve()), parent_manifest_sha256=digest(args.parent / "export_manifest.jsonl"),
        script_sha256=digest(Path(__file__)), images=len(rows), size_px=[args.size, args.size],
        splits=dict(Counter(r["split"] for r in rows)), seed=None,
        preset="mirror_left_right_bottom_gray_top", interpolation="OpenCV INTER_LINEAR",
        mirror="OpenCV BORDER_REFLECT_101 (edge pixel not repeated)", top_gray=114,
        padding="Centered; left/right/bottom reflected when padding is needed; top constant gray",
        originals="Byte-identical copies of oriented v6 exports", validation="passed: hashes, dimensions, pixel roundtrip, content rectangle, gray top",
        status="provisional; human group and scale review pending"))
    (args.output / "LEEME.md").write_text(
        "# Copias originales y relleno en espejo\n\n"
        f"{len(rows)} imágenes en cada formato, conservando nombres, grupos y splits.\n\n"
        f"`originals/`: copias exactas de los originales orientados de la entrega. "
        f"`images_{args.size}x{args.size}/`: PNG con proporción conservada, "
        "relleno lateral e inferior en espejo y superior gris (114). "
        "El relleno se aplica solo donde falta espacio; no se recorta la imagen.\n\n"
        "El espejo puede repetir objetos: es contenido artificial. Para etiquetar, "
        "usar los originales; el manifiesto registra escala y márgenes para transformar coordenadas. "
        "No se crearon etiquetas. La revisión de escalas y grupos sigue pendiente.\n",
        encoding="utf-8")
    print(f"Exported and verified {len(rows)} originals and {len(rows)} resized images")


if __name__ == "__main__":
    main()
