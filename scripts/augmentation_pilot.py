"""Reproducible geometry-first augmentation campaign; originals are read-only."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import time

import numpy as np
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get('UCHUVA_AUGMENTATION_ROOT',str(REPO / 'outputs/augmentation_pilot_20261022'))).resolve()
SOURCE = REPO / 'outputs/union_real_pilot_20261022'
NAMES = ['Pintona', 'Madura', 'Sobremadura']


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def link(source, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        try:
            os.link(source, dest)
        except OSError:
            shutil.copy2(source, dest)


def boxes(path):
    rows = [list(map(float, line.split())) for line in Path(path).read_text().splitlines() if line.strip()]
    for c, x, y, w, h in rows:
        assert c in (0, 1, 2) and w > 0 and h > 0
        assert min(x-w/2, y-h/2) >= -1e-6 and max(x+w/2, y+h/2) <= 1+1e-6
    return rows


def image_geometry(image, labels):
    with Image.open(image) as im:
        width, height = im.size
    output = []
    for i, (c, x, y, w, h) in enumerate(labels):
        nearest = min((math.hypot(x-b[1], y-b[2]) for j, b in enumerate(labels) if i != j), default=None)
        overlaps = []
        for j, (_, xx, yy, ww, hh) in enumerate(labels):
            if i == j:
                continue
            inter = max(0, min(x+w/2, xx+ww/2)-max(x-w/2, xx-ww/2))*max(0, min(y+h/2, yy+hh/2)-max(y-h/2, yy-hh/2))
            overlaps.append(inter / max(1e-12, w*h+ww*hh-inter))
        output.append(dict(class_id=int(c), x=x, y=y, width=w, height=h, area=w*h,
                           aspect=w*width/(h*height), min_side_960=min(w*width, h*height)*960/max(width, height),
                           nearest_center=nearest, max_box_iou=max(overlaps, default=0),
                           touches_border=min(x-w/2, y-h/2, 1-x-w/2, 1-y-h/2) <= 1/max(width, height)))
    return dict(width=width, height=height, count=len(labels), boxes=output)


def quantiles(values):
    return dict(zip(['p10', 'p50', 'p90'], map(float, np.quantile(values, [.1, .5, .9])))) if values else None


def summary(rows):
    flat = [b for r in rows for b in r['geometry']['boxes']]
    sizes = [b['min_side_960'] for b in flat]
    hist = np.histogram(sizes, [0, 16, 32, 64, np.inf])[0]
    return dict(images=len(rows), instances=len(flat), density=quantiles([r['geometry']['count'] for r in rows]),
                min_side_960=quantiles(sizes), size_fractions=(hist/max(1, sum(hist))).tolist(),
                classes=dict(Counter(str(b['class_id']) for b in flat)),
                metrics={k:quantiles([float(b[k]) for b in flat if b[k] is not None]) for k in
                         ['x','y','width','height','area','aspect','nearest_center','max_box_iou','touches_border']},
                by_class={str(c):dict(count=sum(b['class_id']==c for b in flat),
                    size=quantiles([b['min_side_960'] for b in flat if b['class_id']==c])) for c in range(3)})


def gate(real, synthetic):
    if not synthetic or not any(r['geometry']['count'] for r in synthetic):
        return dict(passed=False, reason='No nonempty synthetic bank')
    a, b = summary(real), summary(synthetic)
    errors = {k:abs(b[k]['p50']/a[k]['p50']-1) for k in ['density','min_side_960']}
    fractions = np.abs(np.array(a['size_fractions'])-np.array(b['size_fractions'])).tolist()
    return dict(passed=errors['min_side_960'] <= .2 and max(fractions) <= .05,
                density_is_admission_criterion=False, admission_version='size-only/2',
                median_relative_errors=errors, size_fraction_errors=fractions, real=a, synthetic=b)


def prepare():
    ROOT.mkdir(exist_ok=False)
    # The clock begins at the first execution inspection, not after preparation.
    start = datetime.fromisoformat('2026-10-22T09:54:59-05:00').timestamp()
    write(ROOT/'budget.json', dict(start=start, deadline=start+86400, training_deadline=start+79200,
                                  render_deadline=start+14400, timezone='America/Bogota'))
    manifest = read(SOURCE/'manifest.json')
    assert sha(SOURCE/'manifest.json') == read(SOURCE/'readiness.json')['manifest_sha256']
    groups, hashes = defaultdict(set), defaultdict(set)
    rows = []
    for r in manifest['records']:
        if r['status'] != 'included':
            continue
        assert sha(SOURCE/r['image']) == r['sha256']
        assert sha(SOURCE/r['label']) == r['label_sha256']
        groups[r['group_id']].add(r['split']); hashes[r['sha256']].add(r['split'])
        row = dict(r, image=str((SOURCE/r['image']).resolve()), label=str((SOURCE/r['label']).resolve()))
        # No validation/test geometry is used for calibration.
        if r['split'] == 'train':
            row['geometry'] = image_geometry(row['image'], boxes(row['label']))
        rows.append(row)
    assert all(len(x)==1 for x in groups.values()) and all(len(x)==1 for x in hashes.values())
    assert Counter(r['split'] for r in rows) == dict(train=461, val=88, test=94)
    write(ROOT/'real_manifest.json', dict(source_manifest_sha256=sha(SOURCE/'manifest.json'), rows=rows))
    train = [r for r in rows if r['split']=='train']
    write(ROOT/'geometry/real_train.json', dict(summary=summary(train), rows=train,
          overlap_is_not_occlusion=True, calibration_split='train'))
    grouped = defaultdict(list)
    for row in train:
        grouped[row['group_id']].append(row)
    # Deterministic search for a nested group ordering near both requested sizes.
    rng=random.Random(20261022); keys=sorted(grouped); best=None
    for _ in range(3000):
        rng.shuffle(keys); cumulative=np.cumsum([len(grouped[k]) for k in keys])
        stops=[int(np.argmin(abs(cumulative-len(train)*f)))+1 for f in (.25,.5)]
        selected=[[r for k in keys[:n] for r in grouped[k]] for n in stops]
        if any(len({b['class_id'] for r in sub for b in r['geometry']['boxes']})<3 for sub in selected):continue
        score=sum(abs(len(sub)-len(train)*f) for sub,f in zip(selected,(.25,.5)))
        if best is None or score<best[0]:best=(score,selected)
    subsets={'25':best[1][0], '50':best[1][1], '100':train}
    write(ROOT/'subsets.json', {k:[r['source_row'] for r in v] for k,v in subsets.items()})
    protocol=dict(version='augmentation-pilot/1', weights=str((REPO/'yolo26n.pt').resolve()),
        weights_sha256=sha(REPO/'yolo26n.pt'), names=NAMES, primary='macro AP50:95',
        real_fractions=[100,50,25], synthetic_ratios=[0,.25,.5,1], classical=[False,True],
        seeds=[20261022,20261023,20261024], screen_steps=2000, final_steps=4000,
        validation_interval=500, batch=2, imgsz=960, optimizer='AdamW', lr0=.0002,
        lr_schedule='linear by effective optimizer step from lr0 to 0.01*lr0',
        classical_recipe=dict(hsv_h=0,hsv_s=0,hsv_v=.1,fliplr=.5),
        geometry_gate=dict(median_relative_tolerance=.2,bin_absolute_tolerance=.05,density_is_admission_criterion=False,version='size-only/2'),
        test_status='historically consulted development test', source_class_semantics='calyx appearance, not validated fruit maturity')
    assert protocol['weights_sha256']==read(SOURCE/'protocol.json')['weights_sha256']
    write(ROOT/'protocol.json', protocol)
    write(ROOT/'integrity.json', dict(groups_disjoint=True, hashes_verified=True, exclusions_preserved=True,
                                    counts=dict(Counter(r['split'] for r in rows)),subset_counts={k:len(v) for k,v in subsets.items()}))
    print(json.dumps(read(ROOT/'integrity.json')))
    print(json.dumps(summary(train)))


def make_dataset(name, real_rows, synthetic_rows=()):
    folder=ROOT/'datasets'/name
    if (folder/'manifest.json').exists():return folder/'data.yaml'
    evaluation=[r for r in read(ROOT/'real_manifest.json')['rows'] if r['split']!='train']
    entries=[]
    for row in list(real_rows)+list(synthetic_rows)+evaluation:
        split=row.get('split','train'); domain='synthetic' if 'synthetic_id' in row else 'real'
        ident=row.get('synthetic_id', 'row_'+str(row.get('source_row')))
        image=folder/'images'/split/(ident+Path(row['image']).suffix)
        label=folder/'labels'/split/(ident+'.txt')
        link(row['image'],image); link(row['label'],label)
        entries.append(dict(image=str(image.resolve()),label=str(label.resolve()),domain=domain,
                            split=split,group=row.get('group_id',row.get('scene')),source_id=ident,
                            image_sha256=sha(image),label_sha256=sha(label),instances=len(boxes(label))))
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'data.yaml').write_text('path: '+folder.as_posix()+'\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n'+''.join(f'  {i}: {n}\n' for i,n in enumerate(NAMES)),encoding='utf-8')
    write(folder/'manifest.json',dict(entries=entries))
    return folder/'data.yaml'


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare']);a=p.parse_args()
    if a.action=='prepare':prepare()
