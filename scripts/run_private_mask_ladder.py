"""Run an isolated, resumable six-size real RGB segmentation experiment."""
import argparse
from collections import Counter
from contextlib import closing
from importlib.metadata import version
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))

from uchuva_annotation_audit.masks import checked_runs, mask_bbox
from uchuva_annotation_audit.prepared_mask_revision import REVISION_NAME, load_revision, verified_record
from uchuva_annotation_audit.store import SessionLock, atomic_json, now, read, sha, window_process_identity


PHASES = (20, 40, 80, 160, 320, 461)
SEEDS = (20261022, 20261023, 20261024)
PRIVATE_PARENT = REPO / 'outputs'
DEFAULT_ROOT = PRIVATE_PARENT / 'private_mask_ladder_20261121'
TRAINER = REPO/'scripts/train_private_mask_ladder.py'
EVALUATOR = REPO/'scripts/evaluate_private_mask_ladder.py'
ANNOTATOR = REPO/'scripts/annotate_private_mask_ladder.py'
VERSION = 'private-real-mask-ladder/1'


def verify(path, expected):
    if sha(path) != expected:
        raise ValueError(f'Frozen artifact changed: {path}')


def write_or_check(path, payload):
    if path.exists():
        if read(path) != payload:
            raise ValueError(f'Incompatible existing artifact: {path}')
    else:
        atomic_json(path, payload, exclusive=True)


def private_root(argument):
    root = argument.resolve()
    if root.parent != PRIVATE_PARENT.resolve() or not root.name.startswith('private_mask_ladder_'):
        raise ValueError('Use a distinct private_mask_ladder_* directory directly under outputs')
    return root


def initialize(root):
    from uchuva_annotation_audit.assistance import default_model
    from uchuva_annotation_audit.private_ladder_data import prepare

    root.mkdir(parents=True, exist_ok=True)
    with closing(SessionLock(root/'initialization.lock')):
        packed = REPO/'outputs/daylight_augmentation_115_20261112/pilot'
        run = 'final_real_classical_20261022'
        detector = packed/'training'/run/'weights/best.pt'
        detector_sha = read(packed/'evaluation_lock.json')['weights'][run]
        mobile, mobile_sha = default_model()
        weights = REPO/'outputs/segmentation_cycles_20261002/yolo26n-seg.pt'
        verify(detector, detector_sha)
        verify(mobile, mobile_sha)
        plan = dict(schema_version=VERSION, phases=list(PHASES), seeds=list(SEEDS),
                    steps=4000, size=960, batch=2, virtual_epoch_images=1000, training_device='0',
                    initial_weights=str(weights), initial_weights_sha256=sha(weights),
                    annotation_assets=dict(detector=dict(path=str(detector), sha256=detector_sha),
                                           mobile_sam=dict(path=str(mobile), sha256=mobile_sha)),
                    exposure_policy='fixed_steps_nested_track_image_repeat_counts',
                    review_policy='assistant_visual_only_then_seal_each_extension',
                    evaluation_policy='fixed_val_each_stage_then_locked_development_only',
                    dependencies={name: version(name) for name in ('ultralytics','torch','numpy','Pillow')})
        write_or_check(root/'plan.json', plan)
        inputs = prepare(root)
        validate_inputs(inputs)
        write_or_check(root/'inputs_lock.json', dict(plan_sha256=sha(root/'plan.json'),
                                                     inventory_sha256=sha(root/'private_inputs.json')))
    print(f'{root}: {len(inputs["train"])} train / {len(inputs["val"])} val, development reference isolated', flush=True)


def validate_inputs(inputs):
    train, val = inputs['train'], inputs['val']
    if (len(train), len(val)) != (461, 88):
        raise ValueError('Training or validation counts differ from frozen study scope')
    if sum(bool(row.get('student_round_id')) for row in train) != 50:
        raise ValueError('Training must include exactly the original 50 classroom photos')
    for field in ('id', 'image_sha256'):
        if len({row[field] for row in train+val}) != len(train)+len(val):
            raise ValueError(f'Repeated image binding: {field}')
    if {row['group_id'] for row in train} & {row['group_id'] for row in val}:
        raise ValueError('Train/val group leakage')


def check_partition_reference(rows):
    for row in rows:
        verify(row['image'], row['image_sha256'])
        verify(row['annotation'], row['annotation_sha256'])


def prepare_phase(root, inputs, count):
    rows = inputs['train'][:count]
    missing = [row['id'] for row in rows if not (root/'annotations'/f"{row['id']}.json").is_file()]
    if missing:
        return None, missing
    assembled = []
    coverage = Counter()
    groups = Counter()
    for row in rows:
        ann = root/'annotations'/f"{row['id']}.json"
        doc = read(ann)
        size = row['width'], row['height']
        if doc['review_state'] != 'assistant_visual_reviewed' or doc['image_sha256'] != row['image_sha256'] or doc['id'] != row['id']:
            raise ValueError('Missing exact reviewed annotation binding')
        verify(row['image'], row['image_sha256'])
        for obj in doc['objects']:
            checked_runs(obj['segmentation'], *size)
            if obj['bbox'] != mask_bbox(obj['segmentation']):
                raise ValueError('Annotation box is not derived from the mask')
            name = ('pintona', 'madura', 'sobremadura')[obj['class_id']] if obj['class_id'] is not None else 'uncertain_masks'
            coverage[name] += 1
        for region in doc['ignore_regions']:
            checked_runs(region, *size)
        coverage['processed'] += 1
        coverage['fully_uncertain'] += int(doc['full_image_uncertain'])
        has_foreground = any(obj['class_id'] is not None for obj in doc['objects'])
        coverage['supervised_images'] += int(not doc['full_image_uncertain'])
        coverage['supervised_foreground_images'] += int(has_foreground)
        coverage['verified_empty'] += int(doc['empty_confirmed'])
        coverage['ignored_regions'] += len(doc['ignore_regions'])
        groups[row['group_id']] += 1
        assembled.append(dict(row, annotation=str(ann), annotation_sha256=sha(ann)))
    if not sum(coverage[name] for name in ('pintona','madura','sobremadura')):
        raise ValueError('A sealed phase requires some resolved foreground supervision')
    coverage['supervised_masks'] = sum(coverage[name] for name in ('pintona','madura','sobremadura'))
    phase = root/'phases'/f'{count:03d}'
    write_or_check(phase/'manifest.json', dict(schema_version=VERSION, phase=count, train=assembled,
                                               val=inputs['val'], coverage=dict(coverage), groups=dict(groups)))
    return phase, []


def ready_gpu():
    result = subprocess.run(['nvidia-smi','--query-gpu=index,memory.free,utilization.gpu',
                             '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True)
    lines = [list(map(int, line.split(','))) for line in result.stdout.splitlines() if line.strip()]
    gpu = next((row for row in lines if row[0] == 0), None)
    if gpu is None:
        raise RuntimeError('CUDA GPU 0 not available')
    return gpu[1] >= 5000 and gpu[2] < 35, {'free_mib': gpu[1], 'utilization_percent': gpu[2]}


def update(root, stage, **values):
    previous = read(root/'state.json') if (root/'state.json').is_file() else {}
    record = dict(values, stage=stage)
    if {key: value for key, value in previous.items() if key != 'updated'} != record:
        atomic_json(root/'state.json', dict(record, updated=now()))
        print(stage, json.dumps(values, ensure_ascii=False), flush=True)


def wait_gpu(root, *, phase, seed, job):
    consecutive = 0
    while consecutive < 2:
        ready, info = ready_gpu()
        consecutive = consecutive+1 if ready else 0
        if consecutive < 2:
            update(root, 'waiting_for_gpu', phase=phase, seed=seed, job=job, gpu=info)
            time.sleep(8 if ready else 45)


def invoke(root, script, args, *, tag):
    folder = root/'logs'
    folder.mkdir(exist_ok=True)
    sequence = 1
    while (folder/f'{tag}_{sequence:03d}.log').exists():
        sequence += 1
    log = folder/f'{tag}_{sequence:03d}.log'
    with log.open('xb') as stream:
        process = subprocess.Popen([sys.executable, str(script), *map(str,args)],
                                   cwd=REPO, stdout=stream, stderr=subprocess.STDOUT)
        identity = {'pid': process.pid}
        if os.name == 'nt':
            from uchuva_lsystem.dataset_completion import process_identity
            identity = process_identity(process.pid, int(process._handle))
        atomic_json(root/'active_child.json', dict(identity, script=script.name, log=str(log), started=now()))
        code = process.wait()
    atomic_json(root/'active_child.json', dict(identity, script=script.name, log=str(log),
                                               finished=now(), exit_code=code))
    if code:
        raise RuntimeError(f'{tag} exited with {code}. See {log}')


def completed(run, phase, seed, manifest=None, plan=None):
    record = read(run/'completion.json')
    weights = run/'weights/last.pt'
    if (record['steps'], record['exposures'], record['phase'], record['seed']) != (4000, 8000, phase, seed):
        raise ValueError(f'Unexpected dose or steps in {run}')
    if manifest is not None and record['manifest_sha256'] != sha(manifest):
        raise ValueError('Completed run belongs to a different phase manifest')
    if plan is not None and record['plan_sha256'] != sha(plan):
        raise ValueError('Completed run belongs to a different study plan')
    verify(weights, record['weights_sha256'])
    return dict(phase=phase, seed=seed, weights=str(weights), weights_sha256=record['weights_sha256'])


def check_evaluation(path, weights_sha, split):
    report = read(path)
    if (report['weights_sha256'], report['split']) != (weights_sha, split):
        raise ValueError(f'Evaluation does not belong to frozen weight and split: {path}')
    return report


def snapshot_sources(root, *, create=False):
    files = [Path(__file__), TRAINER, EVALUATOR, ANNOTATOR]
    files.extend((REPO/'src/uchuva_annotation_audit').glob('private_*.py'))
    files.extend(REPO/'src/uchuva_annotation_audit'/name for name in ('masks.py','store.py','assistance.py'))
    if os.name == 'nt':
        files.append(REPO/'src/uchuva_lsystem/dataset_completion.py')
    revision = load_revision(root)
    if revision:
        files.extend([
            root / REVISION_NAME, root / revision['cache_manifest'], root / revision['previous_sources'],
            REPO / 'scripts/prepare_private_mask_cache.py',
            REPO / 'src/uchuva_annotation_audit/prepared_mask_cache.py',
            REPO / 'src/uchuva_annotation_audit/prepared_mask_revision.py',
        ])
    loss_revision = root / 'training_empty_targets_revision.json'
    if loss_revision.is_file():
        change = read(loss_revision)
        if change['version'] != 'empty-assignment-dtype/1':
            raise ValueError('Unknown assignment dtype correction')
        files.extend([loss_revision, verified_record(root, change['previous_sources'],
                                                      change['previous_sources_sha256'])])
    path = root/'source_lock.json'
    if create:
        write_or_check(path, dict(files={str(file): sha(file) for file in sorted(set(files))}))
    for file, digest in read(path)['files'].items():
        verify(file,digest)


def summarize(root, *, final=False):
    split = 'test' if final else 'val'
    phases = []
    for phase in PHASES:
        directory = root/'phases'/f'{phase:03d}'
        files = [directory/'evaluation'/f'{split}_{seed}.json' for seed in SEEDS]
        if not all(file.is_file() for file in files):
            continue
        reports = [read(file) for file in files]
        macro = [report['metrics']['macro_ap50_95'] for report in reports]
        scalars = [x for x in macro if x is not None]
        class_ap = {}
        for name in ('Pintona', 'Madura', 'Sobremadura'):
            measures = [report['metrics']['by_class'][name]['ap50_95'] for report in reports]
            class_ap[name] = statistics.mean(measures) if all(x is not None for x in measures) else None
        phases.append(dict(size=phase, coverage=read(directory/'manifest.json')['coverage'],
                           macro_ap50_95_mean=statistics.mean(scalars) if len(scalars)==len(SEEDS) else None,
                           macro_ap50_95_sd=statistics.stdev(scalars) if len(scalars)==len(SEEDS) else None,
                           class_ap50_95_mean=class_ap,
                           seeds=[dict(seed=seed, result=str(file), metrics=report['metrics'])
                                  for seed,file,report in zip(SEEDS,files,reports,strict=True)]))
    atomic_json(root/f'{split}_summary.json', dict(split=split, exploratory=True, phases=phases))
    title = 'Evaluación histórica de desarrollo' if final else 'Validación de la línea base privada'
    lines = [f'# {title}', '', f'Fases completas: {len(phases)} de 6.', '',
             'AP de máscaras 50–95 en porcentaje. Cada media utiliza tres semillas fijas.', '',
             '| Fotos | Con supervisión | Máscaras con clase | Macro | DE | Pintona | Madura | Sobremadura |',
             '|---:|---:|---:|---:|---:|---:|---:|---:|']

    def percentage(value):
        return '—' if value is None else f'{100*value:.2f}'

    for phase in phases:
        coverage = phase['coverage']
        values = [phase['size'], coverage['supervised_images'], coverage['supervised_masks'],
                  percentage(phase['macro_ap50_95_mean']), percentage(phase['macro_ap50_95_sd'])]
        values.extend(percentage(value) for value in phase['class_ap50_95_mean'].values())
        lines.append('| ' + ' | '.join(map(str,values)) + ' |')
    if final:
        lines.extend(['', 'Las 94 fotos históricas se consultaron en campañas anteriores. Los resultados son exploratorios.'])
    lines.extend(['', f'Las métricas por semilla, tamaño y grupo están en `{split}_summary.json`.', ''])
    target = root/f'{split}_summary.md'
    pending = target.with_suffix('.tmp')
    pending.write_text('\n'.join(lines), encoding='utf-8')
    pending.replace(target)


def wait_annotations(root, inputs, count):
    while True:
        directory, missing = prepare_phase(root, inputs, count)
        if directory is not None:
            return directory
        if any(not (root/'visual_review'/f'{ident}.jpg').is_file() for ident in missing):
            try:
                probe = SessionLock(root/'drafts.lock')
            except RuntimeError:
                update(root, 'waiting_for_rgb_drafts', phase=count, missing=len(missing))
                time.sleep(25)
                continue
            probe.close()
            update(root, 'generating_private_rgb_drafts', phase=count, missing=len(missing))
            invoke(root,ANNOTATOR,['--root',root,'draft','--through',count],tag=f'draft_{count:03d}')
        update(root, 'assistant_visual_review_required', phase=count, missing=len(missing), next_ids=missing[:8])
        time.sleep(25)


def run_campaign(root):
    with closing(SessionLock(root/'controller.lock')):
        atomic_json(root/'controller_identity.json', dict(**window_process_identity(), started=now()))
        if (root/'active_child.json').is_file():
            child = read(root/'active_child.json')
            if 'exit_code' not in child:
                if os.name != 'nt' or 'creation_tick' not in child:
                    raise RuntimeError('Previous child identity is not verifiable')
                from uchuva_lsystem.dataset_completion import owner_alive
                while owner_alive(child):
                    update(root, 'waiting_for_previous_child', pid=child['pid'], log=child['log'])
                    time.sleep(15)
                atomic_json(root/'active_child.json', dict(child, exit_code=None, disappeared=now()))
        plan_path = root/'plan.json'
        plan = read(plan_path)
        lock = read(root/'inputs_lock.json')
        verify(plan_path, lock['plan_sha256'])
        verify(root/'private_inputs.json', lock['inventory_sha256'])
        verify(plan['initial_weights'], plan['initial_weights_sha256'])
        for package, expected in plan['dependencies'].items():
            if version(package) != expected:
                raise ValueError(f'Mismatched frozen environment: {package}')
        snapshot_sources(root, create=True)
        inputs = read(root/'private_inputs.json')
        validate_inputs(inputs)
        check_partition_reference(inputs['val'])
        runs = []
        for count in PHASES:
            snapshot_sources(root)
            phase = wait_annotations(root, inputs, count)
            for seed in SEEDS:
                snapshot_sources(root)
                run = phase/'runs'/str(seed)
                if not (run/'completion.json').is_file():
                    wait_gpu(root, phase=count, seed=seed, job='train')
                    update(root, 'training', phase=count, seed=seed)
                    invoke(root, TRAINER, ['--root', root, '--phase',count,'--seed',seed,'--output',run], tag=f'train_{count:03d}_{seed}')
                sealed = completed(run,count,seed,phase/'manifest.json',plan_path)
                out = phase/'evaluation'/f'val_{seed}.json'
                if not out.is_file():
                    wait_gpu(root, phase=count, seed=seed, job='val')
                    update(root, 'validating', phase=count, seed=seed)
                    invoke(root,EVALUATOR,['--root',root,'--phase',count,'--seed',seed,'--split','val','--run',run,'--output',out],
                           tag=f'val_{count:03d}_{seed}')
                check_evaluation(out,sealed['weights_sha256'],'val')
                runs.append(sealed)
            summarize(root)
        if len(runs) != 18:
            raise ValueError('Development evaluation requires 18 completed runs')
        development = inputs['development_index']
        verify(development['path'], development['sha256'])
        index = read(development['path'])
        rows = index['rows']
        if len(rows) != 94 or ({row['group_id'] for row in rows} & {row['group_id'] for row in inputs['train']+inputs['val']}):
            raise ValueError('Development partition is not the frozen disjoint 94 photos')
        check_partition_reference(rows)
        write_or_check(root/'development.json', index)
        write_or_check(root/'weights_lock.json', dict(development_sha256=sha(root/'development.json'), runs=runs))
        for sealed in runs:
            count, seed = sealed['phase'],sealed['seed']
            phase = root/'phases'/f'{count:03d}'
            out = phase/'evaluation'/f'test_{seed}.json'
            snapshot_sources(root)
            if not out.is_file():
                wait_gpu(root,phase=count,seed=seed,job='test')
                update(root,'evaluating_development',phase=count,seed=seed)
                run = phase/'runs'/str(seed)
                invoke(root,EVALUATOR,['--root',root,'--phase',count,'--seed',seed,'--split','test','--run',run,'--output',out,
                                       '--validation',phase/'evaluation'/f'val_{seed}.json'],tag=f'test_{count:03d}_{seed}')
            check_evaluation(out,sealed['weights_sha256'],'test')
            summarize(root,final=True)
        update(root,'complete_private_review',runs=18,phases=list(PHASES),development_photos=94)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init','run'])
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    root = private_root(args.root)
    if args.action == 'init':
        initialize(root)
    else:
        run_campaign(root)


if __name__ == '__main__':
    main()
