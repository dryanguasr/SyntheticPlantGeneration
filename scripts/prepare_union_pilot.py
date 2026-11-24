"""Prepare an immutable-source, grouped detection pilot and human review queue."""
from __future__ import annotations
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import random
import re
import shutil

import numpy as np
from PIL import Image, ImageDraw, ImageOps

SOURCE = Path('outputs/datasets/union_anotadas_20261021_v1')
ROOT = Path('outputs/union_real_pilot_20261022')
SEED = 20261022


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def bbox(segment):
    points = np.asarray(segment[1:], dtype=float).reshape(-1, 2)
    low, high = points.min(0), points.max(0)
    center, size = (low + high) / 2, high - low
    if not np.isfinite(points).all() or low.min() < 0 or high.max() > 1 or size.min() <= 0:
        raise ValueError('Invalid bounding box')
    return [int(segment[0]), *map(float, center), *map(float, size)]


def prepare():
    if ROOT.exists():
        raise FileExistsError('Choose a new run directory; never overwrite a prepared run')
    ROOT.mkdir(parents=True)
    rows = [json.loads(line) for line in (SOURCE / 'source_latest.ndjson').read_text(encoding='utf-8').splitlines()]
    audit = json.loads((SOURCE / 'audit/audit_report.json').read_text(encoding='utf-8'))
    source_manifest = json.loads((SOURCE / 'download_manifest.json').read_text(encoding='utf-8'))
    assert sha(SOURCE / 'source_latest.ndjson') == source_manifest['source_sha256']
    images = {r['source_row']: dict(r) for r in source_manifest['images']}
    parent = {i: i for i in images}
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def join(a, b):
        parent[find(max(a, b))] = find(min(a, b))
    groups = defaultdict(list)
    unknown = []
    for i, image in images.items():
        match = re.match(r'(.+)_f\d+\.[^.]+$', image['file'])
        if match:
            groups['sequence:' + match[1]].append(i)
        else:
            unknown.append(i)
    groups['unresolved_photos_train_only'] = unknown
    for members in groups.values():
        for i in members[1:]:
            join(members[0], i)
    for group in audit['byte_duplicate_groups']:
        for item in group[1:]:
            join(group[0]['source_row'], item['source_row'])
    # Conservative co-location is not a claim that dHash proves identity.
    for pair in audit['near_duplicate_candidates']:
        join(pair['a']['source_row'], pair['b']['source_row'])
    bad = {x['source_row'] for x in audit['issues']}
    duplicates, conflicts = {}, set()
    for group in audit['byte_duplicate_groups']:
        ids = sorted(x['source_row'] for x in group)
        labels = [rows[i-1]['annotations'] for i in ids]
        if any(label != labels[0] for label in labels[1:]):
            conflicts.update(ids)
        else:
            duplicates.update({i: ids[0] for i in ids[1:]})
    eligible = sorted(set(images) - bad - set(duplicates) - conflicts)
    components = defaultdict(list)
    for i in eligible:
        components[find(i)].append(i)
    anchored = {find(i) for i in unknown}
    vectors = {}
    for group, ids in components.items():
        c = Counter(int(s[0]) for i in ids for s in rows[i-1]['annotations']['segments'])
        vectors[group] = np.array([len(ids), c[0], c[1], c[2]], float)
    total = sum(vectors.values())
    targets = np.array([.70, .15, .15])[:, None] * total
    available = sorted(set(components) - anchored)
    rng = random.Random(SEED)
    best = None
    for _ in range(20000):
        assignment = {g: 0 for g in components}
        for g in available:
            assignment[g] = rng.choices([0, 1, 2], [.45, .275, .275])[0]
        totals = np.zeros((3, 4))
        for g, split in assignment.items():
            totals[split] += vectors[g]
        if np.any(totals[:, 1:] == 0):
            continue
        score = float(np.sum(((totals-targets)/np.maximum(targets, 1))**2))
        if best is None or score < best[0]:
            best = score, assignment, totals
    if best is None:
        raise ValueError('No grouped split retaining all classes')
    assignment = best[1]
    split_names = ('train', 'val', 'test')
    manifest = []
    for i, record in sorted(images.items()):
        path = SOURCE / record['path']
        assert sha(path) == record['sha256'], path
        item = {**record, 'source_path': str(path.resolve()), 'original_split': record['split'],
                'group_id': f'component_{find(i)}', 'source_annotations_sha256': hashlib.sha256(json.dumps(rows[i-1]['annotations'], sort_keys=True).encode()).hexdigest()}
        if i in bad or i in conflicts:
            item.update(status='quarantined_image', split=None, reason='polygon_issue' if i in bad else 'conflicting_labels')
        elif i in duplicates:
            item.update(status='duplicate_separated', split=None, canonical_source_row=duplicates[i])
        else:
            split = split_names[assignment[find(i)]]
            name = f'row_{i:04d}'
            destination = ROOT / 'dataset' / 'images' / split / (name + path.suffix.lower())
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            boxes = [bbox(s) for s in rows[i-1]['annotations']['segments']]
            label = ROOT / 'dataset' / 'labels' / split / (name + '.txt')
            label.parent.mkdir(parents=True, exist_ok=True)
            label.write_text('\n'.join(str(b[0]) + ' ' + ' '.join(f'{v:.9f}' for v in b[1:]) for b in boxes) + '\n', encoding='utf-8')
            item.update(status='included', split=split, image=str(destination.relative_to(ROOT)),
                        label=str(label.relative_to(ROOT)), label_sha256=sha(label), annotations=len(boxes))
            assert sha(destination) == record['sha256']
        manifest.append(item)
    included = [r for r in manifest if r['status'] == 'included']
    for key in ['sha256', 'group_id']:
        isolation = defaultdict(set)
        for r in included:
            isolation[r[key]].add(r['split'])
        assert all(len(x) == 1 for x in isolation.values()), key
    data = ROOT / 'dataset/data.yaml'
    data.write_text('path: ' + (ROOT/'dataset').resolve().as_posix() + '\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: Pintona\n  1: Madura\n  2: Sobremadura\n', encoding='utf-8')
    review = ROOT / 'review'
    review.mkdir()
    review_rows, cards = [], []
    for issue in audit['issues']:
        i, j = issue['source_row'], issue['instance']
        segment = rows[i-1]['annotations']['segments'][j]
        with Image.open(SOURCE / images[i]['path']) as im:
            im = im.convert('RGB')
            pts = [(segment[k]*im.width, segment[k+1]*im.height) for k in range(1, len(segment), 2)]
            ImageDraw.Draw(im).line(pts+pts[:1], fill=(255,0,180), width=3)
            x, y = zip(*pts)
            crop = im.crop((max(0,int(min(x))-30), max(0,int(min(y))-30), min(im.width,int(max(x))+31), min(im.height,int(max(y))+31)))
            crop = ImageOps.contain(crop, (800,800))
            name = f'row_{i}_instance_{j}.jpg'
            crop.save(review / name)
        review_rows.append({'source_row': i, 'instance_zero_based': j, 'class_id': segment[0], 'file': images[i]['file'],
                            'reason': issue['kind'], 'crop': name, 'reviewer': '', 'decision': '', 'notes': ''})
        cards.append(f'<article><h2>Fila {i}, instancia {j}, clase {segment[0]}</h2><img src="{name}"><p>{html.escape(issue["kind"])}</p></article>')
    with (review/'karen_caroline_review.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(review_rows[0])); writer.writeheader(); writer.writerows(review_rows)
    (review/'index.html').write_text('<meta charset="utf-8"><title>Revisión Karen y Caroline</title><style>body{font-family:sans-serif}article{display:inline-block;vertical-align:top;width:45%;margin:2%}img{max-width:100%}</style><h1>Polígonos pendientes de adjudicación</h1><p>Originales intactos. Imágenes excluidas completas del piloto. No se han enviado mensajes.</p>'+''.join(cards), encoding='utf-8')
    write(ROOT/'manifest.json', {'schema_version':'union-detection-revision/1.0','seed':SEED,'source_sha256':source_manifest['source_sha256'],
          'group_policy':'filename sequence + exact duplicate + conservative dHash <=5 linkage; unresolved photos train only',
          'session_independence_verified':False,'records':manifest})
    counts = {split: {'images':int(best[2][j,0]),'classes':[int(x) for x in best[2][j,1:]]} for j,split in enumerate(split_names)}
    write(ROOT/'readiness.json', {'training_allowed':True,'counts':counts,'status_counts':dict(Counter(r['status'] for r in manifest)),
          'cross_split_hash_groups':0,'cross_split_capture_components':0,'source_hashes_verified':True,'export_hashes_verified':True,
          'manifest_sha256':sha(ROOT/'manifest.json'),'created_at_utc':datetime.now(timezone.utc).isoformat()})
    write(ROOT/'protocol.json', {'seed':SEED,'deadline_utc':'2026-10-22T12:30:00+00:00','training_stop_utc':'2026-10-22T10:30:00+00:00',
          'synthetic_admission_deadline_utc':'2026-10-22T09:30:00+00:00','weights':'yolo26n.pt','weights_sha256':sha('yolo26n.pt'),
          'class_names':['Pintona','Madura','Sobremadura'],'task':'detect','epochs':20,'max_training_seconds':5400,
          'imgsz':960,'batch':2,'optimizer':'AdamW','lr0':0.0002,'nbs':2,'warmup_epochs':0,
          'hsv_h':0,'hsv_s':0,'hsv_v':0.1,'fliplr':0.5,'flipud':0,'mosaic':0,'mixup':0,'copy_paste':0,
          'degrees':0,'perspective':0,'shear':0,'translate':0,'scale':0,
          'video_fps':5,'coordinates':'X right, Y up, Z inward; origin unconfirmed',
          'marker_side_m':None,'camera_intrinsics':None,'metric_localization_validated':False})
    print(json.dumps(counts)); print(Counter(r['status'] for r in manifest))


if __name__ == '__main__':
    prepare()
