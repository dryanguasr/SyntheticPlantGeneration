"""Freeze and run the private mask augmentation study in a separate output root."""

import argparse
from collections import Counter
from contextlib import closing
from importlib.metadata import version
from pathlib import Path
import random
import sys
import time

from run_private_mask_ladder import (
    REPO, SEEDS, check_partition_reference, invoke, update, verify, wait_gpu, write_or_check,
)
from uchuva_annotation_audit.masks import checked_runs, mask_bbox
from uchuva_annotation_audit.private_training import pair_supervision, sampling_order
from uchuva_annotation_audit.store import SessionLock, atomic_json, now, read, sha, window_process_identity


DEFAULT_ROOT = REPO / 'outputs/private_synthetic_masks_20261123'
LADDER = REPO / 'outputs/private_mask_ladder_20261121'
PAUSE = REPO / 'outputs/spatial_dataset_completion_20261030/pause_requested.json'
TRAINER = REPO / 'scripts/train_private_synthetic_masks.py'
EVALUATOR = REPO / 'scripts/evaluate_private_synthetic_masks.py'
DOSES = {'real': 0, 'synth_low': 120, 'synth_middle': 240, 'synth_high': 600, 'synth_framing': 240}
SLOTS = 8000


def private_root(path):
    root = path.resolve()
    if root.parent != (REPO / 'outputs').resolve() or not root.name.startswith('private_synthetic_masks_'):
        raise ValueError('Use a separate private_synthetic_masks_* directory under outputs')
    return root


def binding(row):
    return tuple(row[key] for key in ('id', 'image_sha256', 'width', 'height'))


def bind_real_labels(canonical_rows, manifest):
    entries = read(manifest)['train'] if manifest else canonical_rows
    labels = {row['id']: row for row in entries}
    if len(entries) != len(labels) or labels.keys() != {row['id'] for row in canonical_rows}:
        raise ValueError('The real annotation manifest must cover the same unique RGB IDs')
    bound = []
    for original in canonical_rows:
        row = labels[original['id']]
        annotation = Path(row['annotation']).resolve()
        if binding(row) != binding(original):
            raise ValueError(f'Wrong RGB binding: {row["id"]}')
        if not annotation.is_relative_to((REPO / 'outputs').resolve()):
            raise ValueError('Keep annotation data in the private output space')
        verify(annotation, row['annotation_sha256'])
        document = read(annotation)
        if (document.get('id'), document.get('image_sha256')) != (original['id'], original['image_sha256']):
            raise ValueError(f'Wrong annotation binding: {row["id"]}')
        size = row['width'], row['height']
        if document.get('size') != list(size):
            raise ValueError(f'Wrong annotation dimensions: {row["id"]}')
        if manifest:
            objects = document['objects']
            if len({obj['id'] for obj in objects}) != len(objects):
                raise ValueError(f'Duplicate instances: {row["id"]}')
            if document.get('full_image_uncertain') and any(obj['class_id'] is not None for obj in objects):
                raise ValueError(f'Fully uncertain row contains supervised objects: {row["id"]}')
            if not objects and not any(document.get(key) for key in
                                       ('empty_confirmed', 'verified_empty', 'full_image_uncertain', 'ignore_regions')):
                raise ValueError(f'An empty annotation must declare its supervision state: {row["id"]}')
            for obj in objects:
                label = obj['class_id']
                checked_runs(obj['segmentation'], *size)
                if label is not None and (type(label) is not int or label not in range(3)):
                    raise ValueError(f'Unknown appearance class for {row["id"]}')
                if 'bbox' in obj and obj['bbox'] != mask_bbox(obj['segmentation']):
                    raise ValueError(f'Box differs from the native mask: {row["id"]}')
            for region in document.get('ignore_regions', []):
                checked_runs(region, *size)
        bound.append(dict(original, source='real', annotation=str(annotation),
                          annotation_sha256=row['annotation_sha256']))
    return bound


def source_files():
    package = REPO / 'src/uchuva_annotation_audit'
    return [
        Path(__file__).resolve(), TRAINER, EVALUATOR,
        REPO / 'scripts/train_private_mask_ladder.py', REPO / 'scripts/evaluate_private_mask_ladder.py',
        REPO / 'scripts/run_private_mask_ladder.py', REPO / 'src/uchuva_lsystem/dataset_completion.py',
        *(package / name for name in ('private_training.py', 'private_evaluation.py', 'prepared_mask_cache.py',
                                      'prepared_mask_revision.py', 'store.py', 'masks.py')),
    ]


def seal_sources(root):
    lock = root / 'source_lock.json'
    write_or_check(lock, {'files': {str(path): sha(path) for path in source_files()}})


def verify_sources(root):
    for path, digest in read(root / 'source_lock.json')['files'].items():
        verify(path, digest)
    if not read(PAUSE)['active']:
        raise RuntimeError('The historical render campaign must be paused')


def check_partitions(train, validation, development):
    if tuple(map(len, (train, validation, development))) != (461, 88, 94):
        raise ValueError('The frozen real partitions must contain 461, 88 and 94 photos')
    for field in ('id', 'image_sha256'):
        if len({row[field] for row in train + validation + development}) != 643:
            raise ValueError(f'Duplicate RGB across the historical partitions: {field}')
    groups = [{row['group_id'] for row in rows} for rows in (train, validation, development)]
    if groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2]:
        raise ValueError('Overlapping capture groups in the historical manifest')
    check_partition_reference(train + validation + development)


def real_and_candidate_slots(real_rows, historical_train, seed):
    # The original 461-photo order is independent of future adjudicated labels.
    historical_uncertain = {i for i, row in enumerate(historical_train)
                            if read(row['annotation']).get('full_image_uncertain')}
    order = pair_supervision(sampling_order(len(real_rows), seed, SLOTS), historical_uncertain)
    slots = [real_rows[index]['id'] for index in order]
    seen = set()
    candidates = []
    for index, image_id in enumerate(slots):
        if index % 2 == 1 and image_id in seen:
            candidates.append(index)
        seen.add(image_id)
    random.Random(f'{seed}-replacement-positions').shuffle(candidates)
    if len(candidates) < max(DOSES.values()):
        raise ValueError('Insufficient repeated real exposures in second batch positions')
    return slots, candidates


def ordered_draws(rows, seed, count, framing=False):
    ordered = sorted(rows, key=lambda row: row['id'])
    rng = random.Random(f'{seed}-synthetic-order')
    draws = []
    while len(draws) < count:
        cycle = ordered.copy()
        rng.shuffle(cycle)
        draws.extend(cycle)
    draws = draws[:count]
    if not framing:
        return [row['id'] for row in draws]
    priorities = {}
    for row in ordered:
        if row['framing_priority']:
            priorities.setdefault(row['scene_id'], []).append(row)
    for scene in priorities:
        random.Random(f'{seed}-{scene}-framing').shuffle(priorities[scene])
    positions = Counter()
    for index in range(len(ordered), len(draws)):
        scene = draws[index]['scene_id']
        pool = priorities[scene]
        draws[index] = pool[positions[scene] % len(pool)]
        positions[scene] += 1
    return [row['id'] for row in draws]


def store_arm(root, arm, real_rows, extra, seed_schedules, count):
    rows = real_rows + extra
    by_id = {row['id']: row for row in rows}
    if len(by_id) != len(rows) or len({row['image_sha256'] for row in rows}) != len(rows):
        raise ValueError(f'Duplicate images in {arm}')
    uncertain = {row['id'] for row in real_rows if read(row['annotation']).get('full_image_uncertain')}
    arm_manifest = root / 'manifests' / f'{arm}.json'
    write_or_check(arm_manifest, {'train': rows})
    for seed, (real_slots, positions, draws) in seed_schedules.items():
        slots = real_slots.copy()
        for position, image_id in zip(sorted(positions[:count]), draws, strict=True):
            slots[position] = image_id
        if set(slots) != by_id.keys() or len(slots) != SLOTS:
            raise ValueError(f'Wrong coverage or step budget for {arm}/{seed}')
        if any(a in uncertain and b in uncertain for a, b in zip(slots[::2], slots[1::2], strict=True)):
            raise ValueError(f'The fixed schedule contains an entirely uncertain batch: {arm}/{seed}')
        write_or_check(root / 'schedules' / f'{arm}_{seed}.json',
                       dict(arm=arm, seed=seed, slots=slots, manifest_sha256=sha(arm_manifest)))


def initialize(root, real_label_manifest, frame_manifest, bank_path=None):
    historical = read(LADDER / 'phases/461/manifest.json')
    settings = read(LADDER / 'plan.json')
    train = bind_real_labels(historical['train'], real_label_manifest)
    validation = historical['val']
    development_path = LADDER / 'development.json'
    check_partitions(train, validation, read(development_path)['rows'])
    bank_path = (bank_path or root / 'bank/manifest.json').resolve()
    bank = [dict(row, source='synthetic') for row in read(bank_path)['train']]
    if len(bank) != 115 or len({row['scene_id'] for row in bank}) != 7:
        raise ValueError('Expected the 115 corrected views across seven scenes')
    check_partition_reference(bank)
    verify(settings['initial_weights'], settings['initial_weights_sha256'])
    for folder in ('manifests', 'schedules'):
        (root / folder).mkdir(parents=True, exist_ok=True)
    if frame_manifest is None:
        frame_manifest = root / 'frames/frame_manifest.json'
    label_source = (real_label_manifest or LADDER / 'phases/461/manifest.json').resolve()
    plan = {key: settings[key] for key in ('steps', 'size', 'batch', 'seeds', 'training_device',
                                          'initial_weights', 'initial_weights_sha256', 'dependencies')}
    plan.update(version='private-synthetic-masks/1', doses=DOSES,
                frame_manifest=str(frame_manifest.resolve()), real_labels=str(label_source),
                real_labels_sha256=sha(label_source), bank_manifest=str(bank_path),
                bank_sha256=sha(bank_path), development_reference=str(development_path),
                development_sha256=sha(development_path))
    write_or_check(root / 'plan.json', plan)
    write_or_check(root / 'validation.json', {'rows': validation})
    base = {seed: real_and_candidate_slots(train, historical['train'], seed) for seed in SEEDS}
    for arm, dose in DOSES.items():
        schedules = {seed: (*base[seed], ordered_draws(bank, seed, dose, arm == 'synth_framing'))
                     for seed in SEEDS}
        store_arm(root, arm, train, bank if dose else [], schedules, dose)
    lock_inputs(root, DOSES)


def lock_inputs(root, arms, name='inputs_lock.json'):
    paths = [root / 'plan.json', root / 'validation.json']
    for arm in arms:
        paths.append(root / 'manifests' / f'{arm}.json')
        paths.extend(root / 'schedules' / f'{arm}_{seed}.json' for seed in SEEDS)
    write_or_check(root / name, {'files': {str(path): sha(path) for path in paths}})


def verify_inputs(root, name):
    for path, digest in read(root / name)['files'].items():
        verify(path, digest)


def freeze_frames(root, manifest_path):
    while not manifest_path.is_file():
        update(root, 'waiting_for_frame_audit')
        time.sleep(45)
    gate = read(manifest_path)
    write_or_check(root / 'frame_gate_lock.json', dict(path=str(manifest_path), sha256=sha(manifest_path),
                                                     eligible=gate['eligible_for_training']))
    if not gate['eligible_for_training']:
        return False
    frames = [dict(row, source='frames') for row in gate['train']]
    groups = Counter(row['group_id'] for row in frames)
    if not 20 <= len(frames) <= 60 or len(groups) < 3 or 2 * max(groups.values()) > len(frames):
        raise ValueError('Admitted frames do not meet the frozen coverage gate')
    plan = read(root / 'plan.json')
    validation = read(root / 'validation.json')['rows']
    holdout = validation + read(plan['development_reference'])['rows']
    for field in ('id', 'image_sha256', 'group_id'):
        if {row[field] for row in frames} & {row[field] for row in holdout}:
            raise ValueError(f'Frame overlap with an evaluation partition: {field}')
    check_partition_reference(frames)
    train = read(root / 'manifests/real.json')['train']
    historical = read(LADDER / 'phases/461/manifest.json')['train']
    count = round(SLOTS * len(frames) / (len(train) + len(frames)))
    schedules = {}
    for seed in SEEDS:
        slots, positions = real_and_candidate_slots(train, historical, seed)
        order = sampling_order(len(frames), seed, count)
        schedules[seed] = slots, positions, [frames[index]['id'] for index in order]
    store_arm(root, 'frames', train, frames, schedules, count)
    lock_inputs(root, ['frames'], 'frame_inputs_lock.json')
    return True


def child_recovery(root):
    path = root / 'active_child.json'
    if not path.exists():
        return
    child = read(path)
    if 'exit_code' in child:
        return
    if 'creation_tick' not in child:
        raise RuntimeError('Cannot verify the exact identity of the previous child')
    from uchuva_lsystem.dataset_completion import owner_alive

    while owner_alive(child):
        update(root, 'waiting_for_previous_child', pid=child['pid'], log=child['log'])
        time.sleep(15)
    atomic_json(path, dict(child, exit_code=None, recovery_at=now()))


def completed(root, arm, seed):
    run = root / 'runs' / arm / str(seed)
    report = read(run / 'completion.json')
    weights = run / 'weights/last.pt'
    manifest = root / 'manifests' / f'{arm}.json'
    schedule = root / 'schedules' / f'{arm}_{seed}.json'
    expected = dict(arm=arm, seed=seed, steps=4000, exposures=SLOTS, manifest_sha256=sha(manifest),
                    schedule_sha256=sha(schedule), plan_sha256=sha(root / 'plan.json'), weights_sha256=sha(weights))
    if any(report.get(key) != value for key, value in expected.items()):
        raise ValueError(f'Incompatible completion: {arm}/{seed}')
    slots = read(schedule)['slots']
    if report['image_exposures'] != dict(Counter(slots)):
        raise ValueError(f'Image exposures differ from the sealed schedule: {arm}/{seed}')
    if arm != 'real':
        base = read(root / 'schedules' / f'real_{seed}.json')['slots']
        counts = Counter(report['exposures_by_source'])
        source = 'frames' if arm == 'frames' else 'synthetic'
        changes = [index for index, (original, current) in enumerate(zip(base, slots, strict=True))
                   if original != current]
        first = {}
        for index, image in enumerate(base):
            first.setdefault(image, index)
        if (len(changes) != counts[source] or any(
                index % 2 != 1 or first[base[index]] == index for index in changes)):
            raise ValueError(f'Unpaired real exposures: {arm}/{seed}')
        if arm in DOSES and len(changes) != DOSES[arm]:
            raise ValueError(f'Synthetic dose differs from plan: {arm}/{seed}')
    return dict(arm=arm, seed=seed, weights=str(weights), weights_sha256=expected['weights_sha256'])


def evaluate(root, arm, seed, split, sealed):
    path = root / 'evaluation' / arm / f'{split}_{seed}.json'
    if not path.exists():
        wait_gpu(root, phase=arm, seed=seed, job=split)
        update(root, 'validating' if split == 'val' else 'evaluating_development', arm=arm, seed=seed)
        invoke(root, EVALUATOR, [root, arm, seed, split], tag=f'{split}_{arm}_{seed}')
    report = read(path)
    if (report['weights_sha256'], report['arm'], report['seed'], report['split']) != (
            sealed['weights_sha256'], arm, seed, split):
        raise ValueError('Evaluation metadata differs from selected weights')
    verify(root / report['predictions']['path'], report['predictions']['sha256'])


def run_arm(root, arm):
    sealed_runs = []
    lock = 'frame_inputs_lock.json' if arm == 'frames' else 'inputs_lock.json'
    for seed in SEEDS:
        verify_sources(root)
        verify_inputs(root, lock)
        if not (root / 'runs' / arm / str(seed) / 'completion.json').exists():
            wait_gpu(root, phase=arm, seed=seed, job='train')
            update(root, 'training', arm=arm, seed=seed)
            invoke(root, TRAINER, [root, arm, seed], tag=f'train_{arm}_{seed}')
        sealed = completed(root, arm, seed)
        evaluate(root, arm, seed, 'val', sealed)
        sealed_runs.append(sealed)
    return sealed_runs


def run_campaign(root):
    with closing(SessionLock(root / 'controller.lock')):
        atomic_json(root / 'controller_identity.json', dict(**window_process_identity(), started=now()))
        child_recovery(root)
        seal_sources(root)
        verify_sources(root)
        verify_inputs(root, 'inputs_lock.json')
        plan = read(root / 'plan.json')
        verify(plan['bank_manifest'], plan['bank_sha256'])
        verify(plan['real_labels'], plan['real_labels_sha256'])
        for name, expected in plan['dependencies'].items():
            if version(name) != expected:
                raise ValueError(f'Environment changed: {name}')
        if not (root / 'preflight.json').is_file():
            wait_gpu(root, phase='synth_high', seed=SEEDS[0], job='preflight')
            update(root, 'preflight')
            invoke(root, TRAINER, [root, 'synth_high', SEEDS[0], '--preflight'], tag='preflight')
        preflight = read(root / 'preflight.json')
        protocol = preflight['protocol']
        if (preflight.get('passed') is not True or not preflight.get('projection_exact')
                or preflight['updates'] != 1 or protocol['plan_sha256'] != sha(root / 'plan.json')
                or protocol['manifest_sha256'] != sha(root / 'manifests/synth_high.json')
                or protocol['schedule_sha256'] != sha(root / 'schedules' / f'synth_high_{SEEDS[0]}.json')
                or protocol['worker_sha256'] != sha(TRAINER)):
            raise ValueError('The maximum-density preflight did not pass')
        runs = [sealed for arm in DOSES for sealed in run_arm(root, arm)]
        if freeze_frames(root, Path(plan['frame_manifest'])):
            runs.extend(run_arm(root, 'frames'))
        development = Path(plan['development_reference'])
        verify(development, plan['development_sha256'])
        write_or_check(root / 'weights_lock.json',
                       dict(runs=runs, development_sha256=plan['development_sha256']))
        for sealed in runs:
            verify_sources(root)
            evaluate(root, sealed['arm'], sealed['seed'], 'test', sealed)
        update(root, 'reporting', finished_runs=len(runs))
        invoke(root, EVALUATOR, [root, 'report'], tag='report')
        update(root, 'complete_private_review', finished_runs=len(runs), development_photos=94)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('init', 'run'))
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--real-label-manifest', type=Path)
    parser.add_argument('--frame-manifest', type=Path)
    parser.add_argument('--bank-manifest', type=Path)
    args = parser.parse_args()
    root = private_root(args.root)
    if args.command == 'init':
        root.mkdir(parents=True, exist_ok=True)
        with closing(SessionLock(root / 'initialization.lock')):
            initialize(root, args.real_label_manifest, args.frame_manifest, args.bank_manifest)
    else:
        try:
            run_campaign(root)
        except Exception as exc:
            if 'locked' not in str(exc).lower():
                atomic_json(root / 'failure.json', dict(error=str(exc), type=type(exc).__name__, at=now()))
            raise


if __name__ == '__main__':
    main()
