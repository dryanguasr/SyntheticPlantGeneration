"""Evaluate one sealed private-ladder checkpoint on native reference masks."""

import argparse
import gzip
import json
import math
import os
from pathlib import Path
import sys
import tempfile

import cv2
import numpy as np
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))
from uchuva_annotation_audit.masks import decode_mask, mask_bbox
from uchuva_annotation_audit.private_evaluation import (
    CLASS_NAMES, MASK_IOUS, evaluate_images, native_prediction_rle, prepare_image,
)
from uchuva_annotation_audit.store import atomic_json, read, sha

VERSION = 'private-mask-ladder-evaluation/1'
PREDICTION_FLOOR = .001
MAX_DETECTIONS = 300
PALETTE = ('#58bd68', '#ffc457', '#ee7376', '#b7b3c4')


def private_path(root, path):
    path = Path(path).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError('La evaluación y sus resultados deben quedar dentro de la raíz privada')
    return path


def verify_training(root, run, plan, phase, seed):
    if phase not in plan['phases'] or seed not in plan['seeds']:
        raise ValueError('Fase o semilla fuera del plan sellado')
    weights = private_path(root, run / 'weights/last.pt')
    complete = read(private_path(root, run / 'completion.json'))
    digest = sha(weights)
    expected = dict(phase=phase, seed=seed, steps=plan['steps'], exposures=plan['steps'] * plan['batch'], weights_sha256=digest)
    for key, value in expected.items():
        if complete.get(key) != value:
            raise ValueError(f'Entrenamiento incompleto o incompatible: {key}')
    return weights, digest


def unlock_development(root, plan, phase, seed, weights, digest):
    lock = read(private_path(root, root / 'weights_lock.json'))
    expected = {(n, s) for n in plan['phases'] for s in plan['seeds']}
    found = {}
    for item in lock['runs']:
        key = item['phase'], item['seed']
        if key in found or key not in expected:
            raise ValueError('Peso repetido o fuera del plan en el sello')
        found[key] = (private_path(root, item['weights']), item['weights_sha256'])
    if found.keys() != expected or len({path for path, _ in found.values()}) != len(expected):
        raise ValueError('Desarrollo permanece cerrado hasta sellar todas las corridas')
    if found[(phase, seed)] != (weights, digest):
        raise ValueError('El peso evaluado no coincide con el peso sellado')
    for path, expected_hash in found.values():
        if sha(path) != expected_hash:
            raise ValueError('El sello de pesos fue alterado')
    development = private_path(root, root / 'development.json')
    if sha(development) != lock['development_sha256']:
        raise ValueError('La referencia de desarrollo fue alterada')
    return development


def read_threshold(root, validation, phase, seed, digest):
    if validation is None:
        raise ValueError('Desarrollo requiere el informe validación de esa corrida')
    metadata = read(private_path(root, validation))
    expected = dict(version=VERSION, split='val', phase=phase, seed=seed, weights_sha256=digest)
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError('El umbral no corresponde al informe de validación de esa corrida')
    value = float(metadata['operating_threshold'])
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('Umbral de validación fuera de rango')
    return value, sha(validation)


def read_rows(root, manifest, key):
    rows = read(manifest)[key]
    if not rows:
        raise ValueError(f'El conjunto {key} está vacío')
    ids = set()
    for row in rows:
        ident = row['id']
        if not isinstance(ident, str) or ident in ids or not isinstance(row['group_id'], str) or not row['group_id']:
            raise ValueError('ID duplicado o procedencia de captura ausente')
        ids.add(ident)
        private_path(root, row['annotation'])
        for filename, digest_key in (('image', 'image_sha256'), ('annotation', 'annotation_sha256')):
            if digest_key in row and sha(row[filename]) != row[digest_key]:
                raise ValueError(f'Archivo alterado para {ident}: {filename}')
        if not all(type(row[k]) is int and row[k] > 0 for k in ('width', 'height')):
            raise ValueError(f'Dimensiones inválidas: {ident}')
    return rows


def predict_image(model, row, plan):
    image = cv2.imdecode(np.fromfile(row['image'], dtype=np.uint8), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
    pixels = row['height'], row['width']
    if image is None or image.shape[:2] != pixels:
        raise ValueError(f'El RGB no coincide con las dimensiones selladas: {row["id"]}')
    results = model.predict(image, task='segment', imgsz=plan['size'], conf=PREDICTION_FLOOR,
                            iou=.7, max_det=MAX_DETECTIONS, rect=False, retina_masks=False,
                            device=plan.get('training_device', 0), verbose=False, save=False)
    if len(results) != 1 or results[0].orig_shape != pixels:
        raise ValueError('La salida del predictor no coincide con su imagen')
    result = results[0]
    if result.masks is None:
        if len(result.boxes):
            raise ValueError('El checkpoint devolvió cajas sin máscaras')
        return []

    masks = result.masks.data.cpu().numpy()
    classes = result.boxes.cls.cpu().numpy()
    confidences = result.boxes.conf.cpu().numpy()
    output = []
    for mask, label, score in zip(masks, classes, confidences, strict=True):
        if label not in (0, 1, 2) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError('Predicción no compatible con las tres clases selladas')
        rle = native_prediction_rle(mask, row['width'], row['height'])
        if rle is not None:
            output.append(dict(class_id=int(label), score=float(score), segmentation=rle, bbox=mask_bbox(rle)))
    return output


def draw_panel(base, rows, title):
    panel = base.copy()
    for annotation in rows:
        label = annotation['class_id']
        color = PALETTE[3 if label is None else label]
        mask = decode_mask(annotation['segmentation']).resize(base.size, Image.Resampling.NEAREST)
        panel.paste(color, (0, 0, *base.size), mask.point(lambda value: round(.43 * value)))
    canvas = Image.new('RGB', (base.width, base.height + 32), '#173d2f')
    canvas.paste(panel, (0, 32))
    ImageDraw.Draw(canvas).text((10, 9), title, fill='white')
    return canvas


def write_examples(root, destination, rows, metrics, predictions_path, threshold):
    chosen = {}
    for kind in ('omission', 'confusion', 'background_fp', 'correct'):
        picked = 0
        for event in metrics['operating_point']['sobremadura']:
            if event['kind'] == kind and event['id'] not in chosen:
                chosen[event['id']] = kind
                picked += 1
            if picked == 2:
                break
    if not chosen:
        chosen = {row['id']: 'inventory' for row in rows[:2]}
    destination.mkdir(parents=True, exist_ok=True)
    by_id = {row['id']: row for row in rows}
    published = []
    with gzip.open(predictions_path, 'rt', encoding='utf-8') as stream:
        for line in stream:
            item = json.loads(line)
            ident = item['id']
            if ident not in chosen:
                continue
            row = by_id[ident]
            reference = read(row['annotation'])['objects']
            visible_predictions = [p for p in item['predictions'] if p['score'] >= threshold]
            with Image.open(row['image']) as rgb:
                base = rgb.convert('RGB')
                base.thumbnail((700, 540), Image.Resampling.LANCZOS)
            left = draw_panel(base, reference, f'{ident}  |  Referencia histórica')
            right = draw_panel(base, visible_predictions, f'Predicción  |  umbral {threshold:.4f}')
            composite = Image.new('RGB', (left.width + right.width + 6, left.height + 34), '#f7f8f7')
            composite.paste(left, (0, 0))
            composite.paste(right, (left.width + 6, 0))
            legend = ImageDraw.Draw(composite)
            for index, label in enumerate((*CLASS_NAMES, 'No resoluble')):
                x = 10 + index * 128
                legend.rectangle((x, left.height + 9, x + 13, left.height + 22), fill=PALETTE[index])
                legend.text((x + 19, left.height + 8), label, fill='#173d2f')
            path = destination / f'{len(published):02d}_{chosen[ident]}.jpg'
            composite.save(path, quality=88)
            published.append(dict(id=ident, kind=chosen[ident], path=path.relative_to(root).as_posix()))
    return published


def evaluate(args):
    root = args.root.resolve()
    run = private_path(root, args.run)
    destination = private_path(root, args.output)
    if destination.exists():
        raise FileExistsError(destination)
    plan = read(root / 'plan.json')
    weights, digest = verify_training(root, run, plan, args.phase, args.seed)
    threshold, validation_sha = None, None
    if args.split == 'test':
        manifest = unlock_development(root, plan, args.phase, args.seed, weights, digest)
        threshold, validation_sha = read_threshold(root, args.validation, args.phase, args.seed, digest)
        rows = read_rows(root, manifest, 'rows')
    else:
        manifest = private_path(root, root / 'phases' / f'{args.phase:03d}' / 'manifest.json')
        rows = read_rows(root, manifest, 'val')

    from ultralytics import YOLO

    model = YOLO(str(weights), task='segment')
    destination.parent.mkdir(parents=True, exist_ok=True)
    prediction_path = private_path(root, destination.with_name(destination.stem + '_predictions.jsonl.gz'))
    files = []
    examples = []
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.jsonl.gz', delete=False) as tmp:
        staging = Path(tmp.name)
    try:
        with gzip.open(staging, 'wt', encoding='utf-8', compresslevel=3) as stream:
            for index, row in enumerate(rows, start=1):
                annotation = read(row['annotation'])
                predictions = predict_image(model, row, plan)
                files.append(prepare_image(row, annotation, predictions, plan['size']))
                stream.write(json.dumps(dict(id=row['id'], predictions=predictions), separators=(',', ':'), allow_nan=False) + '\n')
                if index % 20 == 0 or index == len(rows):
                    print(f'{args.split} {args.phase} / {args.seed}   {index} de {len(rows)}', flush=True)
        threshold, metrics = evaluate_images(files, threshold)
        os.replace(staging, prediction_path)
        examples = write_examples(root, private_path(root, destination.with_name(destination.stem + '_examples')),
                                  rows, metrics, prediction_path, threshold)
    finally:
        staging.unlink(missing_ok=True)

    atomic_json(destination, dict(
        version=VERSION, split=args.split, phase=args.phase, seed=args.seed, weights_sha256=digest,
        reference_sha256=sha(manifest), validation_sha256=validation_sha,
        operating_threshold=threshold, operating_threshold_policy='validation macro-F1 after geometry pairing at mask IoU >= .50',
        ap_protocol=dict(iou=list(MASK_IOUS), precision_recall_points=101, confidence_floor=PREDICTION_FLOOR,
                         max_predictions_per_image=MAX_DETECTIONS, ignore_min_prediction_cover=.5,
                         size_bands_at_model_input=[32, 96], macro='mean over classes with positive reference support'),
        metrics=metrics, examples=examples,
        predictions=dict(path=prediction_path.relative_to(root).as_posix(), sha256=sha(prediction_path)),
    ), exclusive=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--phase', required=True, type=int)
    parser.add_argument('--seed', required=True, type=int)
    parser.add_argument('--split', required=True, choices=('val', 'test'))
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--validation', type=Path)
    evaluate(parser.parse_args())


if __name__ == '__main__':
    main()
