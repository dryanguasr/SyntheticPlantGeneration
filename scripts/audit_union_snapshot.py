"""Audit a materialized Ultralytics segmentation snapshot without changing labels.

Uses Pillow and NumPy already present in the training environment. Similarity
thresholds are engineering review filters, never proof of capture independence.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np
from PIL import Image, ImageDraw, ImageOps


def groups(mapping):
    return [items for items in mapping.values() if len(items) > 1]


def proper_crossings(points):
    """Count strict crossings of nonadjacent edges; collinear contacts excluded."""
    p = np.asarray(points, dtype=float)
    q = np.roll(p, -1, axis=0)
    a, b = p[:, None, :], q[:, None, :]
    c, d = p[None, :, :], q[None, :, :]
    def cross(u, v):
        return u[..., 0] * v[..., 1] - u[..., 1] * v[..., 0]
    one = cross(b-a, c-a) * cross(b-a, d-a)
    two = cross(d-c, a-c) * cross(d-c, b-c)
    return int(np.count_nonzero(np.triu((one < -1e-20) & (two < -1e-20), 1)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    root = args.root
    manifest = json.loads((root / 'download_manifest.json').read_text(encoding='utf-8'))
    rows = [json.loads(x) for x in (root / manifest['source_file']).read_text(encoding='utf-8').splitlines()]
    downloads = {x['source_row']: x for x in manifest['images']}
    out = root / 'audit'
    out.mkdir(exist_ok=True)
    classes = rows[0]['class_names']
    counts, image_classes, dimensions = defaultdict(Counter), defaultdict(Counter), Counter()
    byte_groups, pixel_groups, name_groups, sequence_groups = (defaultdict(list) for _ in range(4))
    issues, records, instances, features = [], [], [], []
    for source_row, row in enumerate(rows[1:], 2):
        rec = {'source_row': source_row, 'file': row['file'], 'split': row['split']}
        entry = downloads[source_row]
        name_groups[row['file']].append(rec)
        match = re.match(r'(.+)_f(\d+)\.[^.]+$', row['file'])
        if match:
            sequence_groups[match[1]].append({**rec, 'frame': int(match[2])})
        segments = row.get('annotations', {}).get('segments', [])
        counts[row['split']]['images'] += 1
        counts[row['split']]['annotations'] += len(segments)
        dimensions[f"{row['width']}x{row['height']}"] += 1
        if not segments:
            issues.append({**rec, 'kind': 'empty_annotation'})
        seen, present = set(), set()
        for index, segment in enumerate(segments):
            inst = {**rec, 'instance': index}
            if len(segment) < 7 or len(segment) % 2 != 1:
                issues.append({**inst, 'kind': 'invalid_segment_length'})
                continue
            cid, values = segment[0], segment[1:]
            if type(cid) is not int or str(cid) not in classes:
                issues.append({**inst, 'kind': 'invalid_class'})
                continue
            present.add(cid)
            counts[row['split']][f'class_{cid}'] += 1
            if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
                issues.append({**inst, 'kind': 'nonfinite_coordinate'})
                continue
            if min(values) < 0 or max(values) > 1:
                issues.append({**inst, 'kind': 'coordinate_out_of_range'})
            pts = np.asarray(values).reshape(-1, 2)
            area = abs(float(np.sum(pts[:, 0] * np.roll(pts[:, 1], -1) - pts[:, 1] * np.roll(pts[:, 0], -1)))) / 2
            span = np.ptp(pts, axis=0)
            if area <= 1e-12 or min(span) <= 0 or len(set(map(tuple, pts))) < 3:
                issues.append({**inst, 'kind': 'degenerate_polygon'})
            crossings = proper_crossings(pts)
            if crossings:
                issues.append({**inst, 'kind': 'proper_self_intersection', 'crossings': crossings})
            key = tuple(segment)
            if key in seen:
                issues.append({**inst, 'kind': 'duplicate_annotation_row'})
            seen.add(key)
            instances.append({**inst, 'class_id': cid, 'vertices': len(pts),
                              'area_fraction_shoelace': area,
                              'bbox_width_at_640': float(span[0] * row['width'] * 640 / max(row['width'], row['height'])),
                              'bbox_height_at_640': float(span[1] * row['height'] * 640 / max(row['width'], row['height'])),
                              'touches_image_border': bool(np.any((pts == 0) | (pts == 1)))})
        for cid in present:
            image_classes[row['split']][str(cid)] += 1
        if 'error' in entry:
            issues.append({**rec, 'kind': 'missing_download'})
            continue
        path = root / entry['path']
        byte_groups[entry['sha256']].append(rec)
        try:
            with Image.open(path) as source:
                source.load()
                rgb = source.convert('RGB')
                if rgb.size != (row['width'], row['height']):
                    issues.append({**rec, 'kind': 'dimension_mismatch', 'actual': list(rgb.size)})
                orientation = source.getexif().get(274, 1)
                if orientation != 1:
                    issues.append({**rec, 'kind': 'exif_orientation', 'orientation': orientation})
                digest = hashlib.sha256(str(rgb.size).encode() + rgb.tobytes()).hexdigest()
                pixel_groups[digest].append(rec)
                tiny = np.asarray(rgb.convert('L').resize((9, 8), Image.Resampling.LANCZOS))
                bits = np.packbits(tiny[:, 1:] > tiny[:, :-1]).tobytes()
                features.append((rec, int.from_bytes(bits, 'big')))
                records.append({**rec, 'path': entry['path'], 'sha256': entry['sha256'], 'pixel_sha256': digest,
                                'annotations': len(segments), 'classes': sorted(present), 'dhash64': bits.hex()})
        except Exception as exc:
            issues.append({**rec, 'kind': 'image_decode_error', 'error_type': type(exc).__name__})
        if source_row % 100 == 0:
            print(f'Audited {source_row-1}/{len(rows)-1}', flush=True)
    near = []
    for i, (a, ah) in enumerate(features):
        for b, bh in features[i+1:]:
            distance = (ah ^ bh).bit_count()
            if distance <= 5:
                near.append({'a': a, 'b': b, 'dhash_distance': distance, 'cross_split': a['split'] != b['split']})
    def cross_count(items):
        return sum(len({x['split'] for x in group}) > 1 for group in items)
    byte_dups, pixel_dups, names = groups(byte_groups), groups(pixel_groups), groups(name_groups)
    seq = [{'filename_prefix': key, 'splits': dict(Counter(x['split'] for x in value)), 'records': value}
           for key, value in sequence_groups.items()]
    report = {'schema_version': 'union-audit/1.0', 'source_sha256': manifest['source_sha256'],
              'source_version': rows[0].get('version'), 'class_names': classes,
              'counts_by_split': dict(counts), 'images_per_class_by_split': dict(image_classes),
              'dimensions': dict(dimensions), 'issue_counts': dict(Counter(x['kind'] for x in issues)),
              'issues': issues, 'duplicate_filenames': names, 'byte_duplicate_groups': byte_dups,
              'pixel_duplicate_groups': pixel_dups, 'cross_split_byte_duplicate_groups': cross_count(byte_dups),
              'cross_split_pixel_duplicate_groups': cross_count(pixel_dups),
              'near_duplicate_candidates': near, 'cross_split_near_candidate_pairs': sum(x['cross_split'] for x in near),
              'filename_sequence_candidates': seq,
              'limitations': ['dHash <=5 is an engineering review filter, not identity proof',
                             'Filename prefixes are capture-group candidates, not validated session IDs',
                             'No human agreement or agronomic maturity validation',
                             'Strict crossings exclude collinear contacts; no exhaustive topology certification',
                             'Test inspected for integrity/similarity only; never used for model selection']}
    for name, value in [('audit_report.json', report), ('images.json', records), ('instances.json', instances)]:
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    # Development-only visual sample, deterministic and balanced by class coverage.
    selected = []
    for cid in (0, 1, 2):
        candidates = sorted((r for r in records if r['split'] == 'train' and cid in r['classes']),
                            key=lambda r: hashlib.sha256(f"union-review-20261021:{cid}:{r['source_row']}".encode()).hexdigest())
        selected.extend([r for r in candidates if r not in selected][:4])
    colors = [(40, 220, 80), (255, 180, 30), (240, 70, 160)]
    sheet = Image.new('RGB', (1200, math.ceil(len(selected)/3)*340), 'white')
    for index, rec in enumerate(selected):
        row = rows[rec['source_row']-1]
        with Image.open(root / rec['path']) as source:
            thumb = ImageOps.contain(source.convert('RGB'), (390, 295))
        draw = ImageDraw.Draw(thumb)
        for seg in row['annotations']['segments']:
            pts = [(seg[j]*thumb.width, seg[j+1]*thumb.height) for j in range(1, len(seg), 2)]
            draw.line(pts + pts[:1], fill=colors[seg[0]], width=2)
            draw.text(pts[0], str(seg[0]), fill=colors[seg[0]], stroke_width=1, stroke_fill='black')
        x, y = (index%3)*400, (index//3)*340
        sheet.paste(thumb, (x, y+25))
        ImageDraw.Draw(sheet).text((x+4, y+4), f"row {rec['source_row']} train | {rec['annotations']} instances", fill='black')
    sheet.save(out / 'development_review.jpg')
    (out / 'visual_sample.json').write_text(json.dumps(selected, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['counts_by_split', 'issue_counts', 'cross_split_byte_duplicate_groups', 'cross_split_pixel_duplicate_groups', 'cross_split_near_candidate_pairs']}))


if __name__ == '__main__':
    main()
