"""Measure polygon overlap under an explicit raster convention, not occlusion."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.root / 'download_manifest.json').read_text(encoding='utf-8'))
    rows = [json.loads(x) for x in (args.root / manifest['source_file']).read_text(encoding='utf-8').splitlines()]
    result = []
    for number, row in enumerate(rows[1:], 2):
        w, h = row['width'], row['height']
        cover = np.zeros((h, w), np.uint16)
        for segment in row['annotations']['segments']:
            points = np.rint(np.asarray(segment[1:]).reshape(-1, 2) * (w, h)).astype(np.int32)
            points[:, 0] = np.clip(points[:, 0], 0, w - 1)
            points[:, 1] = np.clip(points[:, 1], 0, h - 1)
            x, y, width, height = cv2.boundingRect(points)
            mask = np.zeros((height, width), np.uint8)
            cv2.fillPoly(mask, [points - (x, y)], 1)
            cover[y:y+height, x:x+width] += mask
        overlap = int(np.count_nonzero(cover > 1))
        if overlap:
            result.append({'source_row': number, 'split': row['split'], 'overlap_pixels': overlap,
                           'union_pixels': int(np.count_nonzero(cover)), 'max_instance_coverage': int(cover.max())})
    report = {'convention': 'engineering check: round normalized*dimension, clip to image, OpenCV fillPoly; source raster semantics unverified',
              'source_sha256': manifest['source_sha256'], 'not_occlusion': True, 'images_with_overlap': result}
    out = args.root / 'audit' / 'raster_overlap.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'Images with inter-instance polygon overlap: {len(result)}')


if __name__ == '__main__':
    main()
