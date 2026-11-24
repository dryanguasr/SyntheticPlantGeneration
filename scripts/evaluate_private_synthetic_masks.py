"""Evaluate frozen mixed-data mask models on the two historical real partitions."""

import argparse
from collections import Counter
import gzip
import json
import os
from pathlib import Path
import statistics
import tempfile

from PIL import Image

from evaluate_private_mask_ladder import (
    draw_panel, predict_image, write_examples,
)
from run_private_synthetic_masks import DOSES, SEEDS, completed, private_root, verify
from uchuva_annotation_audit.private_evaluation import (
    AREA_BANDS, CLASS_NAMES, average_precisions, evaluate_images, prepare_image,
)
from uchuva_annotation_audit.store import atomic_json, read, sha


def evaluation_file(root, arm, seed, split):
    return root / 'evaluation' / arm / f'{split}_{seed}.json'


def read_reference(root, plan, run, split):
    if split == 'val':
        return root / 'validation.json'
    lock = read(root / 'weights_lock.json')
    gate = read(root / 'frame_gate_lock.json')
    verify(gate['path'], gate['sha256'])
    arms = [*DOSES, 'frames'] if gate['eligible'] else list(DOSES)
    runs = [completed(root, arm, seed) for arm in arms for seed in plan['seeds']]
    if runs != lock['runs'] or run not in runs or plan['development_sha256'] != lock['development_sha256']:
        raise ValueError('The full set of checkpoints must be sealed before development evaluation')
    reference = Path(plan['development_reference'])
    verify(reference, lock['development_sha256'])
    return reference


def control_threshold(root, arm, seed, split):
    if arm == 'real' and split == 'val':
        return None, None
    path = evaluation_file(root, 'real', seed, 'val')
    metadata = read(path)
    weights = completed(root, 'real', seed)
    if any(metadata[key] != weights[key] for key in ('weights_sha256', 'arm', 'seed')) or metadata['split'] != 'val':
        raise ValueError('Operating threshold must come from the matching real-only validation')
    verify(root / 'validation.json', metadata['reference_sha256'])
    return metadata['operating_threshold'], sha(path)


def evaluate(root, arm, seed, split):
    from ultralytics import YOLO

    plan = read(root / 'plan.json')
    run = completed(root, arm, seed)
    manifest = read_reference(root, plan, run, split)
    rows = read(manifest)['rows']
    if len(rows) != (88 if split == 'val' else 94):
        raise ValueError('Unexpected reference set size')
    threshold, control_sha = control_threshold(root, arm, seed, split)
    destination = evaluation_file(root, arm, seed, split)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(destination)
    prediction_path = destination.with_name(destination.stem + '_predictions.jsonl.gz')
    examples_dir = destination.with_name(destination.stem + '_examples')
    model = YOLO(run['weights'], task='segment')
    images = []
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.jsonl.gz', delete=False) as tmp:
        staging = Path(tmp.name)
    try:
        with gzip.open(staging, 'wt', encoding='utf-8', compresslevel=3) as stream:
            for number, row in enumerate(rows, start=1):
                verify(row['image'], row['image_sha256'])
                verify(row['annotation'], row['annotation_sha256'])
                predictions = predict_image(model, row, plan)
                images.append(prepare_image(row, read(row['annotation']), predictions, plan['size']))
                stream.write(json.dumps(dict(id=row['id'], predictions=predictions), separators=(',', ':'),
                                        allow_nan=False) + '\n')
                if number % 20 == 0 or number == len(rows):
                    print(f'{split} {arm}/{seed}: {number}/{len(rows)}', flush=True)
        threshold, metrics = evaluate_images(images, threshold)
        for band in AREA_BANDS:
            metrics['by_size'][band]['by_class'] = {
                CLASS_NAMES[0]: average_precisions(images, 0, band),
                CLASS_NAMES[1]: average_precisions(images, 1, band),
                CLASS_NAMES[2]: metrics['by_size'][band]['sobremadura'],
            }
        os.replace(staging, prediction_path)
        examples = write_examples(root, examples_dir, rows, metrics, prediction_path, threshold)
    finally:
        staging.unlink(missing_ok=True)
    atomic_json(destination, dict(
        version='private-synthetic-mask-evaluation/1', split=split, arm=arm, seed=seed,
        weights_sha256=run['weights_sha256'], reference_sha256=sha(manifest),
        operating_threshold=threshold, operating_threshold_policy='paired real-only validation macro-F1',
        threshold_reference_sha256=control_sha, metrics=metrics, examples=examples,
        predictions=dict(path=prediction_path.relative_to(root).as_posix(), sha256=sha(prediction_path)),
    ), exclusive=True)


def measure(metrics):
    return {'macro': metrics['macro_ap50_95'], 'agnostic': metrics['class_agnostic']['ap50_95'],
            **{name: metrics['by_class'][name]['ap50_95'] for name in CLASS_NAMES}}


def descriptive_summary(values):
    if any(value is None for value in values):
        return dict(mean=None, sd=None)
    return dict(mean=statistics.mean(values), sd=statistics.stdev(values))


def check_report(root, split, run):
    path = evaluation_file(root, run['arm'], run['seed'], split)
    report = read(path)
    if (report['weights_sha256'], report['arm'], report['seed'], report['split']) != (
            run['weights_sha256'], run['arm'], run['seed'], split):
        raise ValueError(f'Incompatible evaluation: {path}')
    threshold, control_sha = control_threshold(root, run['arm'], run['seed'], split)
    if threshold is not None and (report['operating_threshold'], report['threshold_reference_sha256']) != (
            threshold, control_sha):
        raise ValueError(f'Mismatched operating threshold: {path}')
    plan = read(root / 'plan.json')
    verify(read_reference(root, plan, run, split), report['reference_sha256'])
    verify(root / report['predictions']['path'], report['predictions']['sha256'])
    return report


def compare(root, runs, split):
    by_arm = {}
    for run in runs:
        arm, seed = run['arm'], run['seed']
        rpt = check_report(root, split, run)
        by_arm.setdefault(arm, {})[seed] = dict(
            scores=measure(rpt['metrics']),
            by_size=rpt['metrics']['by_size'], by_group=rpt['metrics']['by_group'],
            operating_point=rpt['metrics']['operating_point'], threshold=rpt['operating_threshold'],
            examples=rpt['examples'],
        )
    for arm, seeds in by_arm.items():
        for seed, row in seeds.items():
            row['deltas'] = {}
            comparators = ['real', 'synth_middle'] if arm == 'synth_framing' else ['real']
            for control in comparators:
                row['deltas'][control] = {}
                for key, value in row['scores'].items():
                    base = by_arm[control][seed]['scores'][key]
                    row['deltas'][control][key] = value - base if value is not None and base is not None else None
        if set(seeds) != set(SEEDS):
            raise ValueError('The three matched seeds are required')
    return {
        arm: dict(seeds=seeds, scores={key: descriptive_summary([seeds[seed]['scores'][key] for seed in SEEDS])
                                      for key in seeds[SEEDS[0]]['scores']},
                  deltas={
                      control: {key: descriptive_summary([seeds[seed]['deltas'][control][key] for seed in SEEDS])
                                for key in seeds[SEEDS[0]]['scores']}
                      for control in seeds[SEEDS[0]]['deltas']
                  }) for arm, seeds in by_arm.items()
    }


def predictions_by_id(root, arm, seed, selected):
    predictions = read(evaluation_file(root, arm, seed, 'test'))['predictions']
    with gzip.open(root / predictions['path'], 'rt', encoding='utf-8') as stream:
        return {row['id']: row['predictions'] for row in map(json.loads, stream) if row['id'] in selected}


def comparison_gallery(root, development, val):
    reference = read(read(root / 'plan.json')['development_reference'])['rows']
    rows = {row['id']: row for row in reference}
    seed = SEEDS[0]
    treated = max((arm for arm in DOSES if arm != 'real'), key=lambda arm: val[arm]['scores']['macro']['mean'])
    gallery = root / 'gallery'
    gallery.mkdir(exist_ok=True)
    base_events = development['real']['seeds'][seed]['operating_point']['sobremadura']
    other_events = development[treated]['seeds'][seed]['operating_point']['sobremadura']
    cases = {}
    for side, source in (('real', base_events), ('mixed', other_events)):
        for kind in ('omission', 'confusion', 'correct', 'background_fp'):
            for event in source:
                if event['kind'] == kind and event['id'] not in cases:
                    cases[event['id']] = f'{side}_{kind}'
                    break
    threshold = development['real']['seeds'][seed]['threshold']
    base = predictions_by_id(root, 'real', seed, cases)
    mixed = predictions_by_id(root, treated, seed, cases)
    files = []
    for image_id, kind in cases.items():
        row = rows[image_id]
        with Image.open(row['image']) as image:
            rgb = image.convert('RGB')
        rgb.thumbnail((570, 480), Image.Resampling.LANCZOS)
        panels = [
            draw_panel(rgb, read(row['annotation'])['objects'], f'{image_id} | Referencia histórica'),
            draw_panel(rgb, [p for p in base[image_id] if p['score'] >= threshold], 'Sólo real'),
            draw_panel(rgb, [p for p in mixed[image_id] if p['score'] >= threshold], treated),
        ]
        combined = Image.new('RGB', (panels[0].width * 3 + 12, panels[0].height), '#f7f8f7')
        for index, panel in enumerate(panels):
            combined.paste(panel, (index * (panel.width + 6), 0))
        path = gallery / f'{image_id}_{kind}.jpg'
        combined.save(path, quality=90)
        files.append(dict(image=image_id, kind=kind, file=path.relative_to(root).as_posix()))
    return dict(arm=treated, seed=seed, threshold=threshold, cases=files)


def report(root):
    runs = read(root / 'weights_lock.json')['runs']
    val, development = (compare(root, runs, split) for split in ('val', 'test'))
    gallery = comparison_gallery(root, development, val)
    exposure = []
    for run in runs:
        arm, seed = run['arm'], run['seed']
        receipt = read(root / 'runs' / arm / str(seed) / 'completion.json')
        slots = read(root / 'schedules' / f'{arm}_{seed}.json')['slots']
        rows = read(root / 'manifests' / f'{arm}.json')['train']
        sources = {row['id']: row['source'] for row in rows}
        counts = Counter(sources[image_id] for image_id in slots)
        exposure.append(dict(arm=arm, seed=seed, exposures_by_source=dict(counts),
                             distinct_by_source=dict(Counter(sources[image_id] for image_id in set(slots))),
                             receipt=receipt))
    recommended = [
        arm for arm in DOSES if arm != 'real'
        and val[arm]['deltas']['real']['macro']['mean'] > 0
        and val[arm]['deltas']['real']['Sobremadura']['mean'] >= 0
    ]
    atomic_json(root / 'summary.json', dict(validation=val, development=development, exposures=exposure,
                                          examples=gallery, eligible_for_expansion=recommended,
                                          development_is_exploratory=True))
    lines = [
        '# Piloto privado de segmentación', '',
        f'Se verificaron {len(runs)} corridas de 4.000 actualizaciones y 8.000 exposiciones.',
        'Las etiquetas privadas de las 461 fotos fueron la referencia provisional de entrenamiento.',
        'Las 94 fotos de desarrollo ya se consultaron en estudios anteriores. Los resultados son exploratorios.',
    ]
    for title, split in (('Validación, 88 fotos', val), ('Desarrollo histórico, 94 fotos', development)):
        lines += ['', f'## {title}', '', 'AP50–95 de máscaras en %. Δ frente a sólo real en puntos porcentuales.', '',
                  '| Brazo | Macro ± DE | Δ macro | Pintona | Madura | Sobremadura | Δ Sobremadura | Sin clase |',
                  '|---|---:|---:|---:|---:|---:|---:|---:|']
        for arm, values in split.items():
            scores, delta = values['scores'], values['deltas']['real']
            means = [scores[key]['mean'] * 100 for key in CLASS_NAMES]
            macro = scores['macro']
            lines.append(
                f'| {arm} | {macro["mean"]*100:.2f} ± {macro["sd"]*100:.2f} | {delta["macro"]["mean"]*100:+.2f} |'
                f' {means[0]:.2f} | {means[1]:.2f} | {means[2]:.2f} |'
                f' {delta["Sobremadura"]["mean"]*100:+.2f} | {scores["agnostic"]["mean"]*100:.2f} |')
    gate = read(root / 'frame_gate_lock.json')
    lines += ['', '## Lectura y evidencia', '',
              f'Brazo de fotogramas evaluado: {"sí" if gate["eligible"] else "no"}.',
              'Cumplen el criterio descriptivo de ampliación en validación: '
              + (', '.join(recommended) if recommended else 'ningún brazo sintético') + '.',
              'El criterio exige una mejora media de AP macro sin una caída media de Sobremadura.',
              'Las dosis sustituyen repeticiones reales. Comparar exposiciones de instancias además de imágenes.',
              'Consultar [resumen técnico](summary.json) para semillas, tamaños, grupos y errores de Sobremadura.',
              '', '### Ejemplos con un umbral común', '']
    lines.extend(f'- [{case["image"]} · {case["kind"]}]({case["file"]})' for case in gallery['cases'])
    pending = root / 'report.tmp'
    pending.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    pending.replace(root / 'report.md')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('arm')
    parser.add_argument('seed', type=int, nargs='?')
    parser.add_argument('split', choices=('val', 'test'), nargs='?')
    args = parser.parse_args()
    root = private_root(args.root)
    if args.arm == 'report':
        report(root)
    else:
        evaluate(root, args.arm, args.seed, args.split)


if __name__ == '__main__':
    main()
