"""Audit a closed private mask ladder and compute size metrics from saved predictions."""

import argparse
from collections import Counter
import gzip
import json
import math
from pathlib import Path
import statistics
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))

from run_private_mask_ladder import (DEFAULT_ROOT, PHASES, SEEDS, TRAINER, completed,
                                     private_root, snapshot_sources, validate_inputs, verify)
from uchuva_annotation_audit.prepared_mask_revision import REVISION_NAME, load_revision, verified_record
from uchuva_annotation_audit.store import atomic_json, read, sha


TRAINING_ADAPTER = REPO / 'src/uchuva_annotation_audit/private_training.py'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def private_path(root, path):
    path = Path(path)
    path = (path if path.is_absolute() else root / path).resolve()
    require(path != root and path.is_relative_to(root), f'Artefacto fuera de la raíz privada: {path}')
    return path


def check_partition(root, rows, expected, split, image_ids, image_hashes, groups):
    require(len(rows) == expected, f'Cantidad incorrecta en {split}')
    for row in rows:
        ident = row['id']
        image_hash = row['image_sha256']
        group = row['group_id']
        require(ident not in image_ids and image_hash not in image_hashes,
                f'Foto duplicada entre inventarios: {ident}')
        require(group and groups.setdefault(group, split) == split, f'Grupo cruzado: {group}')
        image_ids.add(ident)
        image_hashes.add(image_hash)
        verify(row['image'], image_hash)
        if split != 'train':
            ann = private_path(root, row['annotation'])
            verify(ann, row['annotation_sha256'])
            require(read(ann)['image_sha256'] == image_hash, f'Referencia ligada a otra foto: {ident}')


def check_phase(root, inputs, phase, annotations):
    path = root / 'phases' / f'{phase:03d}' / 'manifest.json'
    manifest = read(path)
    require(manifest['phase'] == phase and manifest['val'] == inputs['val'] and 'test' not in manifest,
            f'Referencias de validación o partición incorrecta en {path}')
    expected_rows = inputs['train'][:phase]
    require(len(manifest['train']) == len(expected_rows), f'Dosis inesperada en {path}')
    for actual, row in zip(manifest['train'], expected_rows, strict=True):
        ident = row['id']
        expected = root / 'annotations' / f'{ident}.json'
        require(private_path(root, actual['annotation']) == expected,
                f'Ruta de máscara no canónica para {ident}')
        if ident not in annotations:
            doc = read(expected)
            require(doc['review_state'] == 'assistant_visual_reviewed' and doc['id'] == ident
                    and doc['image_sha256'] == row['image_sha256']
                    and doc['size'] == [row['width'], row['height']],
                    f'Máscara privada ligada a otra foto o pendiente de revisión: {ident}')
            annotations[ident] = sha(expected)
        require(actual == dict(row, annotation=str(expected), annotation_sha256=annotations[ident]),
                f'La fase {phase} cambió el orden, los datos o el sello de {ident}')
    groups = dict(Counter(row['group_id'] for row in expected_rows))
    require(manifest['groups'] == groups and manifest['coverage']['processed'] == phase,
            f'Cobertura incompatible con el inventario de {phase}')
    return path, expected_rows


def check_training_revision(root, plan, sources):
    revision = load_revision(root)
    if revision is None:
        return None, {}

    anchor = root / REVISION_NAME
    verify(anchor, sources.get(str(anchor)))
    for key in ('previous_sources', 'cache_manifest'):
        require(not Path(revision[key]).is_absolute(), f'Ruta absoluta en la revisión: {key}')
    cache = private_path(root, revision['cache_manifest'])
    require(sources.get(str(cache)) == revision['cache_manifest_sha256'],
            'El sello vigente no incorpora el manifiesto de caché')
    previous = read(private_path(root, revision['previous_sources']))['files']
    require(previous.get(str(TRAINING_ADAPTER)) == sources[str(TRAINING_ADAPTER)],
            'La revisión de caché cambió el adaptador de entrenamiento')

    valid_runs = {(phase, seed) for phase in PHASES for seed in SEEDS}
    historical = {(run['phase'], run['seed']): run for run in revision['historical_runs']}
    require(len(historical) == len(revision['historical_runs']) and historical.keys() <= valid_runs,
            'La revisión contiene corridas históricas repetidas o ajenas al plan')
    continued = revision['continued_run']
    if continued is not None:
        key = continued['phase'], continued['seed']
        interval = plan['virtual_epoch_images'] // plan['batch']
        steps = continued['steps']
        require(key in valid_runs and key not in historical and type(steps) is int
                and 0 < steps < plan['steps'] and steps % interval == 0,
                'Reanudación de caché incompatible con el plan o con las corridas cerradas')
        require(not Path(continued['checkpoint']).is_absolute(),
                'El checkpoint anterior debe tener una ruta privada relativa')
        archived = verified_record(root, continued['checkpoint'], continued['checkpoint_sha256'])
        phase, seed = key
        active = root / 'phases' / f'{phase:03d}' / 'runs' / str(seed) / 'checkpoint.pt'
        require(archived != active.resolve(), 'La reanudación debe conservar un checkpoint archivado independiente')
    assignment_fix = root / 'training_empty_targets_revision.json'
    if assignment_fix.is_file():
        verify(assignment_fix, sources.get(str(assignment_fix)))
        change = read(assignment_fix)
        require(change['version'] == 'empty-assignment-dtype/1', 'Corrección de asignación desconocida')
        previous_lock = verified_record(root, change['previous_sources'], change['previous_sources_sha256'])
        require(sources.get(str(previous_lock)) == change['previous_sources_sha256'],
                'La corrección de asignación debe ligar el sello de fuentes anterior')
        prior_sources = read(previous_lock)['files']
        worker = change['prior_cached_worker_sha256']
        require(prior_sources[str(TRAINING_ADAPTER)] == sources[str(TRAINING_ADAPTER)]
                and prior_sources[str(REPO / 'src/uchuva_annotation_audit/prepared_mask_cache.py')]
                == sources[str(REPO / 'src/uchuva_annotation_audit/prepared_mask_cache.py')]
                and prior_sources[str(TRAINER)] == worker, 'Cambió la procedencia de la preparación congelada')
        cached = {(item['phase'], item['seed']): item for item in change['historical_cached_runs']}
        occupied = set(historical)
        if continued:
            occupied.add((continued['phase'], continued['seed']))
        require(len(cached) == len(change['historical_cached_runs']) and cached.keys() <= valid_runs
                and not (cached.keys() & occupied), 'Corridas de la primera revisión de caché incompatibles')
        revision = dict(revision, historical_cached=cached, prior_cached_worker_sha256=worker)
    return revision, historical


def verify_historical_run(run, seed, record, previous):
    verify(run / 'protocol_lock.json', previous['protocol_sha256'])
    verify(run / 'completion.json', previous['completion_sha256'])
    verify(run.parent.parent / 'evaluation' / f'val_{seed}.json', previous['validation_sha256'])
    require(record['weights_sha256'] == previous['weights_sha256'], f'Cambiaron los pesos históricos: {run}')


def check_run_source(run, phase, seed, protocol, record, sources, revision, historical):
    worker = sources[str(TRAINER)]
    metadata = {}
    if revision is not None:
        key = phase, seed
        previous = historical.get(key)
        continued = revision['continued_run']
        cache_stamp = record.get('input_cache_manifest_sha256')
        cache_digest = revision['cache_manifest_sha256']
        protocol_path = run / 'protocol_lock.json'
        if previous is not None:
            verify_historical_run(run, seed, record, previous)
            require(cache_stamp is None, f'Cambió el uso de caché de la corrida histórica: {run}')
            worker = revision['historical_worker_sha256']
            metadata['training_source_revision'] = 'historical'
        elif continued is not None and key == (continued['phase'], continued['seed']):
            verify(protocol_path, continued['protocol_sha256'])
            require(cache_stamp is None or cache_stamp == cache_digest,
                    f'La corrida continuada declara otro manifiesto de caché: {run}')
            worker = revision['historical_worker_sha256']
            metadata.update(training_source_revision='continued', resumed_from_steps=continued['steps'])
            if cache_stamp is not None:
                metadata['resumed_with_worker_sha256'] = revision.get('prior_cached_worker_sha256',
                                                                    sources[str(TRAINER)])
        elif key in revision.get('historical_cached', {}):
            verify_historical_run(run, seed, record, revision['historical_cached'][key])
            require(cache_stamp == cache_digest, f'Cambió el manifiesto de caché anterior: {run}')
            worker = revision['prior_cached_worker_sha256']
            metadata['training_source_revision'] = 'historical_cache'
        else:
            require(cache_stamp == cache_digest, f'Falta el sello de caché vigente en la corrida: {run}')
            metadata['training_source_revision'] = 'cache'
        metadata.update(training_worker_sha256=worker, training_adapter_sha256=sources[str(TRAINING_ADAPTER)],
                        input_cache_manifest_sha256=cache_stamp)

    require(protocol['worker_sha256'] == worker
            and protocol['adapter_sha256'] == sources[str(TRAINING_ADAPTER)],
            f'Fuentes del protocolo de entrenamiento incompatibles: {run}')
    return metadata


def check_run(plan_path, plan, phase, seed, manifest, rows, sources, revision=None, historical=None):
    run = manifest.parent / 'runs' / str(seed)
    seal = completed(run, phase, seed, manifest, plan_path)
    record = read(run / 'completion.json')
    protocol = read(run / 'protocol_lock.json')
    keys = ('steps', 'batch', 'size', 'initial_weights_sha256')
    require({k: protocol[k] for k in keys} == {k: plan[k] for k in keys}
            and (protocol['phase'], protocol['seed']) == (phase, seed)
            and protocol['plan_sha256'] == record['plan_sha256'] == sha(plan_path)
            and protocol['manifest_sha256'] == record['manifest_sha256'] == sha(manifest)
            and record['initial_weights_sha256'] == plan['initial_weights_sha256'],
            f'Protocolo o procedencia de pesos inconsistente: {run}')
    source_metadata = check_run_source(run, phase, seed, protocol, record, sources, revision, historical)
    ids = {row['id'] for row in rows}
    exposures = record['image_exposures']
    supervised = record['supervised_image_exposures']
    require(record['completed'] is True and record['distinct_images'] == phase and set(exposures) == ids
            and all(type(value) is int and value > 0 for value in exposures.values())
            and sum(exposures.values()) == record['exposures'] == 8000,
            f'El entrenamiento comprometido no cubre la dosis de {run}')
    require(record['distinct_supervised_images'] == len(supervised) and set(supervised) <= ids
            and all(type(value) is int and 0 < value <= exposures[ident] for ident, value in supervised.items())
            and record['batches_without_supervision'] == 0
            and set(record['instance_exposures_by_class']) <= {'0', '1', '2'},
            f'Registro de supervisión inconsistente: {run}')
    progress = read(run / 'progress.json')
    require(progress['steps'] == progress['target'] == record['steps'] == 4000
            and progress['exposures'] == 8000 and progress['supervised_exposures'] == sum(supervised.values())
            and math.isclose(progress['lr'], .000002, rel_tol=1e-9),
            f'El último registro de pasos no coincide con el cierre de {run}')
    recipe = {key: protocol[key] for key in ('version', 'device', 'precision', 'ultralytics', 'torch', 'opencv', 'recipe')}
    summary = dict(phase=phase, seed=seed, manifest_sha256=record['manifest_sha256'],
                   steps=record['steps'], exposures=record['exposures'],
                   supervised_exposures=sum(supervised.values()), seconds=record['seconds'], **source_metadata)
    return seal, recipe, summary


def check_evaluation(root, phase, seed, split, path, reference, rows, run, validation=None):
    from uchuva_annotation_audit.private_evaluation import CLASS_NAMES

    report = read(path)
    expect = (phase, seed, split, run['weights_sha256'], sha(reference))
    actual = (report['phase'], report['seed'], report['split'], report['weights_sha256'], report['reference_sha256'])
    require(actual == expect, f'Evaluación ligada a otra corrida o referencia: {path}')
    if validation is None:
        require(report['validation_sha256'] is None, f'Validación con procedencia inesperada: {path}')
    else:
        require(report['validation_sha256'] == sha(validation)
                and report['operating_threshold'] == read(validation)['operating_threshold'],
                f'Umbral de desarrollo distinto de su validación: {path}')
    metrics = report['metrics']
    require(metrics['image_count'] == len(rows) and tuple(metrics['by_class']) == CLASS_NAMES
            and {group: item['image_count'] for group, item in metrics['by_group'].items()}
            == dict(Counter(row['group_id'] for row in rows)), f'Cobertura de evaluación inesperada: {path}')
    stamp = report['predictions']
    prediction_path = private_path(root, stamp['path'])
    require(prediction_path == path.with_name(path.stem + '_predictions.jsonl.gz'),
            f'Ruta de predicciones incorrecta: {path}')
    verify(prediction_path, stamp['sha256'])
    examples = []
    ids = {row['id'] for row in rows}
    files = set()
    for item in report['examples']:
        example = private_path(root, item['path'])
        require(item['id'] in ids and example.parent == path.with_name(path.stem + '_examples')
                and example not in files and example.is_file() and example.stat().st_size > 0,
                f'Ejemplo ausente, repetido o ajeno a la corrida: {item}')
        files.add(example)
        examples.append(dict(id=item['id'], kind=item['kind'], path=item['path'], sha256=sha(example)))
    require(examples, f'Evaluación sin ejemplos privados: {path}')
    return dict(phase=phase, seed=seed, split=split, report=path.relative_to(root).as_posix(),
                report_sha256=sha(path), reference_sha256=actual[-1], reference_rows=len(rows),
                predictions=stamp, examples=examples)


def audit(root):
    state = read(root / 'state.json')
    require(state['stage'] == 'complete_private_review' and state['runs'] == 18
            and state['phases'] == list(PHASES) and state['development_photos'] == 94,
            'El controlador debe cerrar las seis fases antes de auditar el lanzamiento privado')
    child = read(root / 'active_child.json')
    child_exit = child.get('exit_code')
    natural_exit = 'finished' in child and child_exit == 0
    recovered_exit = 'disappeared' in child and 'exit_code' in child and child_exit is None
    require(natural_exit or recovered_exit, 'El último trabajador carece de un cierre o una recuperación registrados')
    plan_path = root / 'plan.json'
    plan = read(plan_path)
    require((plan['phases'], plan['seeds'], plan['steps'], plan['batch'], plan['size'])
            == (list(PHASES), list(SEEDS), 4000, 2, 960), 'El plan no corresponde a la campaña autorizada')
    inputs_path = root / 'private_inputs.json'
    input_lock = read(root / 'inputs_lock.json')
    verify(plan_path, input_lock['plan_sha256'])
    verify(inputs_path, input_lock['inventory_sha256'])
    verify(plan['initial_weights'], plan['initial_weights_sha256'])
    snapshot_sources(root)
    sources = read(root / 'source_lock.json')['files']
    revision, historical = check_training_revision(root, plan, sources)
    inputs = read(inputs_path)
    validate_inputs(inputs)
    require(len({row['student_round_id'] for row in inputs['train'] if row.get('student_round_id')}) == 50,
            'La línea de 461 debe contener las 50 fotos distintas del lote estudiantil')
    image_ids, image_hashes, groups = set(), set(), {}
    check_partition(root, inputs['train'], 461, 'train', image_ids, image_hashes, groups)
    check_partition(root, inputs['val'], 88, 'val', image_ids, image_hashes, groups)
    annotations, manifests, runs, briefs, recipe = {}, {}, [], [], None
    for phase in PHASES:
        manifest, train = check_phase(root, inputs, phase, annotations)
        manifests[phase] = manifest
        for seed in SEEDS:
            run, configuration, brief = check_run(plan_path, plan, phase, seed, manifest, train, sources,
                                                  revision, historical)
            if recipe is None:
                recipe = configuration
            require(recipe == configuration, 'Las corridas difieren en la receta o versión de entrenamiento')
            runs.append(run)
            briefs.append(brief)
    lock = read(root / 'weights_lock.json')
    require(lock['runs'] == runs and len(runs) == len({run['weights'] for run in runs}) == 18,
            'Falta el sello de los 18 pesos exactos antes de acceder a desarrollo')

    development = root / 'development.json'
    development_index = inputs['development_index']
    require(development_index['sha256'] == lock['development_sha256'], 'Sello incompatible con el índice de desarrollo')
    verify(private_path(root, development_index['path']), lock['development_sha256'])
    verify(development, lock['development_sha256'])
    reference = read(development)['rows']
    check_partition(root, reference, 94, 'test', image_ids, image_hashes, groups)
    evaluations = []
    for run in runs:
        phase, seed = run['phase'], run['seed']
        manifest = manifests[phase]
        val = manifest.parent / 'evaluation' / f'val_{seed}.json'
        test = val.with_name(f'test_{seed}.json')
        evaluations.extend((check_evaluation(root, phase, seed, 'val', val, manifest, inputs['val'], run),
                            check_evaluation(root, phase, seed, 'test', test, development, reference, run, val)))
    payload = dict(version=1, private=True, exploratory=True, phases=list(PHASES), seeds=list(SEEDS),
                   inventory=dict(train=461, val=88, historical_development=94), recipe=recipe,
                   plan_sha256=input_lock['plan_sha256'], inventory_sha256=input_lock['inventory_sha256'],
                   weights_lock_sha256=sha(root / 'weights_lock.json'), source_lock_sha256=sha(root / 'source_lock.json'),
                   initial_weights_sha256=plan['initial_weights_sha256'],
                   recovered_last_worker_exit=recovered_exit, runs=briefs, evaluations=evaluations)
    if revision is not None:
        cache_revision = root / REVISION_NAME
        payload['training_input_cache_revision'] = dict(read(cache_revision), sha256=sha(cache_revision))
    assignment_fix = root / 'training_empty_targets_revision.json'
    if assignment_fix.is_file():
        payload['training_empty_targets_revision'] = dict(read(assignment_fix), sha256=sha(assignment_fix))
    return payload, {'val': inputs['val'], 'test': reference}, plan['size']


def images_from_predictions(root, asset, rows, size, references):
    from uchuva_annotation_audit.private_evaluation import prepare_image

    path = private_path(root, asset['path'])
    verify(path, asset['sha256'])
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        for row, line in zip(rows, stream, strict=True):
            item = json.loads(line)
            require(item['id'] == row['id'], f'Inventario de predicción alterado: {path}')
            ident = row['id']
            if ident not in references:
                references[ident] = read(private_path(root, row['annotation']))
            yield prepare_image(row, references[ident], item['predictions'], size)


def size_metrics(images):
    from uchuva_annotation_audit.private_evaluation import AREA_BANDS, CLASS_NAMES, average_precisions

    bands = {}
    for band in AREA_BANDS:
        classes = {name: average_precisions(images, label, band) for label, name in enumerate(CLASS_NAMES)}
        resolved = [item['ap50_95'] for item in classes.values() if item['support']]
        bands[band] = dict(by_class=classes, supported_classes=len(resolved),
                           macro_ap50_95=statistics.mean(resolved) if resolved else None,
                           class_agnostic=average_precisions(images, band=band))
    return bands


def supplement(root, audit_payload, split, rows, size):
    from uchuva_annotation_audit.private_evaluation import AREA_BANDS, CLASS_NAMES

    reference = {}
    reports = []
    for evaluation in audit_payload['evaluations']:
        if evaluation['split'] == split:
            images = list(images_from_predictions(root, evaluation['predictions'], rows, size, reference))
            reports.append(dict(phase=evaluation['phase'], seed=evaluation['seed'],
                                predictions=evaluation['predictions'], by_size=size_metrics(images)))

    def distribution(measures):
        return dict(mean=statistics.mean(measures), sd=statistics.stdev(measures)) if all(
            value is not None for value in measures) else dict(mean=None, sd=None)

    aggregate = []
    for phase in PHASES:
        seeds = [item for item in reports if item['phase'] == phase]
        require(tuple(item['seed'] for item in seeds) == SEEDS, f'Tres semillas requeridas para {split}/{phase}')
        bands = {}
        for band in AREA_BANDS:
            values = [item['by_size'][band] for item in seeds]
            bands[band] = dict(macro=distribution([item['macro_ap50_95'] for item in values]),
                               by_class={name: distribution([item['by_class'][name]['ap50_95'] for item in values])
                                         for name in CLASS_NAMES},
                               class_agnostic=distribution([item['class_agnostic']['ap50_95'] for item in values]))
        aggregate.append(dict(phase=phase, by_size=bands))
    return dict(version=1, split=split, exploratory=True, size_side_thresholds_at_model_input=[32, 96],
                macro_policy='mean over supported classes for each size band and seed',
                weights_lock_sha256=audit_payload['weights_lock_sha256'], runs=reports, aggregate=aggregate)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('audit', 'supplement'))
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--split', choices=('val', 'test', 'both'), default='both')
    args = parser.parse_args()
    root = private_root(args.root)
    payload, rows, size = audit(root)
    atomic_json(root / 'release_audit.json', payload)
    print(f'18 corridas, 36 informes y artefactos verificados en {root / "release_audit.json"}', flush=True)
    if args.action == 'supplement':
        for split in rows if args.split == 'both' else [args.split]:
            target = root / f'supplement_mask_size_{split}.json'
            atomic_json(target, supplement(root, payload, split, rows[split], size))
            print(target, flush=True)


if __name__ == '__main__':
    main()
