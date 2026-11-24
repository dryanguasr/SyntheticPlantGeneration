"""Compare two segmentation checkpoints on complete views and native instance masks.

Reports fixed-threshold precision/recall, not AP. Historical preprocessing is
explicit; ground-truth rasters are never resized or filtered by visible area.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
import torch
from ultralytics import YOLO
from ultralytics.models.yolo.segment import SegmentationPredictor
from raster_segmentation_inference import AreaRasterSegmentationPredictor

COLORS = [(255, 180, 40), (40, 210, 255), (240, 90, 200)]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(counts):
    tp, fp, fn = (counts[k] for k in ('tp', 'fp', 'fn'))
    return dict(**counts, precision=tp / max(1, tp + fp),
                recall=tp / max(1, tp + fn), f1=2 * tp / max(1, 2 * tp + fp + fn))


def match(native, labels, masks, predictions):
    """Confidence-ordered one-to-one matching using exact native intersections."""
    remaining = set(range(len(labels)))
    counts = [dict(tp=0, fp=0, fn=0) for _ in COLORS]
    matches = []
    for j in sorted(range(len(predictions)), key=lambda i: -predictions[i]['confidence']):
        cl = predictions[j]['class_id']
        # Histogram measures intersections without allocating one full mask per GT.
        intersections = np.bincount(native[masks[j]].astype(np.int64),
                                   minlength=len(labels) + 1)
        area = int(masks[j].sum())
        candidates = []
        for k in remaining:
            item = labels[k]
            if item['class_id'] != cl:
                continue
            inter = int(intersections[item['mask_id']])
            iou = inter / max(1, area + item['pixels'] - inter)
            candidates.append((iou, k))
        if candidates and max(candidates)[0] >= .5:
            iou, k = max(candidates)
            remaining.remove(k)
            counts[cl]['tp'] += 1
            matches.append(dict(prediction=j, truth=k, iou=iou))
        else:
            counts[cl]['fp'] += 1
    for k in remaining:
        counts[labels[k]['class_id']]['fn'] += 1
    return counts, matches, sorted(remaining)


def overlay(rgb, masks, labels):
    array = np.array(rgb).copy()
    locations = []
    for mask, label in zip(masks, labels):
        color = np.array(COLORS[label['class_id']])
        array[mask] = (array[mask] * .5 + color * .5).astype(np.uint8)
        y, x = np.where(mask)
        if len(x):
            locations.append((int(x.min()), int(y.min()), label))
    image = Image.fromarray(array)
    draw = ImageDraw.Draw(image)
    for x, y, label in locations:
        if 'confidence' in label:
            draw.text((x, y), f"{label['class_id']}:{label['confidence']:.2f}",
                      fill='white', stroke_width=1, stroke_fill='black')
    return image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--version', default='182')
    args = parser.parse_args()
    root = args.root.resolve()
    output = root / f'field_training_v{args.version}'
    data = root / 'field_pilot_v181/dataset'
    vis = output / 'comparison'
    vis.mkdir(exist_ok=False)
    torch.set_num_threads(2)
    rows = [r for r in json.loads((data / 'raster_manifest.json').read_text())['images']
            if r['split'] in ('val', 'test')]
    assert len(rows) == 16
    models = {
        'previous_v177': (root / 'crop_combined_v177/training/weights/last.pt',
                          AreaRasterSegmentationPredictor, 'INTER_AREA'),
        f'new_v{args.version}': (output / 'training/weights/last.pt',
                     SegmentationPredictor, 'INTER_LINEAR'),
    }
    report = {}
    for tag, (path, predictor, interpolation) in models.items():
        model = YOLO(path)
        assert list(model.names.values()) == ['pintona', 'madura', 'sobremadura']
        frames = []
        for row in rows:
            assert sha(data / row['image']) == row['rgb_sha256']
            assert sha(data / row['mask']) == row['raster_sha256']
            name = Path(row['image']).stem
            rgb = Image.open(data / row['image']).convert('RGB')
            native = np.array(Image.open(data / row['mask']))
            result = model.predict(str(data / row['image']), predictor=predictor,
                                   rect=False, imgsz=960, conf=.25, retina_masks=True,
                                   max_det=300, device=0, verbose=False)[0]
            masks = (np.zeros((0, rgb.height, rgb.width), dtype=bool) if result.masks is None
                     else result.masks.data.cpu().numpy().astype(bool))
            labels = [dict(class_id=int(c), confidence=float(s)) for c, s in
                      zip(result.boxes.cls.cpu().tolist(), result.boxes.conf.cpu().tolist())]
            assert len(masks) == len(labels)
            assert masks.shape[1:] == native.shape
            counts, matches, missed = match(native, row['instances'], masks, labels)
            overlay(rgb, masks, labels).save(vis / f'{name}_{tag}.jpg', quality=95)
            np.savez_compressed(vis / f'{name}_{tag}.npz', masks=masks)
            if tag == 'previous_v177':
                overlay(rgb, (native == x['mask_id'] for x in row['instances']),
                        row['instances']).save(vis / f'{name}_truth.jpg', quality=95)
            frames.append(dict(image=name, split=row['split'], rgb_sha256=row['rgb_sha256'],
                               mask_sha256=row['raster_sha256'], truth_count=len(row['instances']),
                               predictions=labels, classes=counts, matches=matches, missed=missed))
            print(tag, name, len(labels), 'predictions', len(matches), 'TP', flush=True)
        splits = {}
        for split in ('val', 'test'):
            selected = [f for f in frames if f['split'] == split]
            classes = [metrics({k: sum(f['classes'][cl][k] for f in selected)
                                for k in ('tp', 'fp', 'fn')}) for cl in range(3)]
            total = metrics({k: sum(c[k] for c in classes) for k in ('tp', 'fp', 'fn')})
            splits[split] = dict(total=total, classes=classes)
        report[tag] = dict(weights=str(path), sha256=sha(path), preprocessing=interpolation,
                           splits=splits, frames=frames)
        (output / 'evaluation_progress.json').write_text(json.dumps(report, indent=2))
        del model
        torch.cuda.empty_cache()
    final = dict(protocol='confidence .25, native class-aware mask IoU .50, all visible instances',
                 metric_type='fixed-threshold P/R/F1, not AP', images=16, results=report,
                 development_test=True, dataset_sha256=sha(data / 'raster_manifest.json'))
    (output / 'evaluation.json').write_text(json.dumps(final, indent=2))
    html = ['<meta charset="utf-8"><title>Piloto V182 frente a V177</title>',
            '<style>body{background:#192228;color:white;font:16px system-ui}img{width:100%}',
            'td{width:33%;padding:5px}a{color:#8de}table{width:100%}</style>',
            '<h1>Mismas vistas completas: referencia, V177 y V182</h1>',
            '<p>Naranja: pintona · cian: madura · magenta: sobremadura. Apariencia del capacho.',
            ' Confianza 0,25; IoU de máscara nativa 0,50. Etiquetas: clase:confianza.</p>',
            '<p>V177 usa su INTER_AREA histórico; V182 usa INTER_LINEAR. Sin recortes ni filtro de tamaño.</p>',
            '<pre>' + json.dumps({k: v['splits'] for k, v in report.items()}, indent=2) + '</pre>',
            '<table><tr><th>Máscaras originales</th><th>Anterior V177</th><th>Nuevo V182</th></tr>']
    for row in rows:
        name = Path(row['image']).stem
        html.append(f'<tr><td colspan="3">{row["split"]}: {name}</td></tr><tr>')
        for tag in ('truth', 'previous_v177', f'new_v{args.version}'):
            file = f'comparison/{name}_{tag}.jpg'
            html.append(f'<td><a href="{file}"><img src="{file}"></a></td>')
        html.append('</tr>')
    html.append('</table>')
    (output / 'comparison.html').write_text(''.join(html).replace('V182', 'V'+args.version), encoding='utf-8')
    # Predeclared views, independent of prediction quality.
    for scene in ('validation', 'test'):
        name = scene + '_view_003'
        sheet = Image.new('RGB', (1280, 1140), '#192228')
        draw = ImageDraw.Draw(sheet)
        for i, (tag, title) in enumerate([('truth', 'Mascaras originales'),
                                         ('previous_v177', 'Anterior V177'), (f'new_v{args.version}', 'Nuevo V182')]):
            draw.text((10, i * 380 + 5), title.replace('V182', 'V'+args.version), fill='white')
            im = Image.open(vis / f'{name}_{tag}.jpg').resize((640, 360))
            rgb = Image.open(data / next(r['image'] for r in rows if Path(r['image']).stem == name)).resize((640, 360))
            sheet.paste(rgb, (0, i * 380 + 20)); sheet.paste(im, (640, i * 380 + 20))
        sheet.save(output / f'{scene}_comparison.jpg', quality=95)
    print(json.dumps({k: v['splits'] for k, v in report.items()}), flush=True)


if __name__ == '__main__':
    main()
