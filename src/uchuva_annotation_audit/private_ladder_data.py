"""Freeze private image order and independent historical reference masks."""

from collections import Counter, defaultdict, deque
import json
from pathlib import Path
import random

from PIL import Image

from .masks import encode_mask, mask_bbox, polygons_mask
from .store import atomic_json, read, sha


REPO = Path(__file__).resolve().parents[2]
VERSION = 'private-mask-ladder-inputs/1'
SEED = 20261121
DOSES = (20, 40, 80, 160, 320, 461)
SPLIT_COUNTS = {'train': 461, 'val': 88, 'test': 94}
CLASS_NAMES = {'0': 'Pintona', '1': 'Madura', '2': 'Sobremadura'}


def _require(condition, detail):
    if not condition:
        raise ValueError(detail)


def _lock(path):
    return {'path': str(path), 'sha256': sha(path)}


def _freeze(path, payload):
    """Permit a compatible restart after interruption, never overwrite evidence."""
    if path.exists():
        _require(read(path) == payload, f'Existing frozen record differs: {path}')
    else:
        atomic_json(path, payload, exclusive=True)
    return _lock(path)


def _read_snapshot(path):
    with path.open(encoding='utf-8') as stream:
        return {position: json.loads(line) for position, line in enumerate(stream, 1) if line.strip()}


def _nested_order(rows, density_by_id, seed=SEED):
    """Visit all capture groups first, alternating density ranks within groups."""
    rng = random.Random(seed)
    groups = defaultdict(list)
    for row in rows:
        groups[row['group_id']].append(row)
    group_order = sorted(groups)
    rng.shuffle(group_order)
    density_queues = {}
    for group in group_order:
        entries = sorted(groups[group], key=lambda row: row['id'])
        rng.shuffle(entries)
        entries.sort(key=lambda row: density_by_id[row['id']])
        bins = [deque() for _ in range(3)]
        for index, row in enumerate(entries):
            bins[3 * index // len(entries)].append(row)
        for bucket in bins:
            shuffled = list(bucket)
            rng.shuffle(shuffled)
            bucket.clear()
            bucket.extend(shuffled)
        rng.shuffle(bins)
        density_queues[group] = deque(bucket for bucket in bins if bucket)
    order = []
    pending_groups = deque(group_order)
    while pending_groups:
        group = pending_groups.popleft()
        buckets = density_queues[group]
        bucket = buckets.popleft()
        order.append(bucket.popleft())
        if bucket:
            buckets.append(bucket)
        if buckets:
            pending_groups.append(group)
    return order


def _split_records(records):
    splits = defaultdict(list)
    groups, hashes, source_rows = {}, set(), set()
    for record in records:
        split, group = record['split'], record['group_id']
        source_row, image_sha = record['source_row'], record['image_sha256']
        _require(record.get('domain') == 'real' and split in SPLIT_COUNTS, 'Unexpected split or image domain')
        _require(isinstance(group, str) and group, 'Missing acquisition component identity')
        _require(groups.setdefault(group, split) == split, f'Group crosses splits: {group}')
        _require(type(source_row) is int and source_row > 1 and source_row not in source_rows,
                 f'Duplicate or invalid source row {source_row!r}')
        _require(image_sha not in hashes, f'Duplicate image hash {image_sha}')
        splits[split].append(record)
        hashes.add(image_sha)
        source_rows.add(source_row)
    counts = {split: len(rows) for split, rows in splits.items()}
    _require(counts == SPLIT_COUNTS, f'Unexpected historical split counts: {counts}')
    return splits


def _historical_objects(segments, width, height, ident):
    objects = []
    for index, segment in enumerate(segments):
        _require(isinstance(segment, list) and len(segment) >= 7 and len(segment) % 2 == 1,
                 f'{ident}: malformed source polygon {index}')
        class_id = segment[0]
        _require(type(class_id) is int and str(class_id) in CLASS_NAMES,
                 f'{ident}: unmapped historical class {class_id!r}')
        _require(all(type(point) in (int, float) and 0 <= point <= 1 for point in segment[1:]),
                 f'{ident}: non-normalized source polygon {index}')
        points = [[x * width, y * height] for x, y in zip(segment[1::2], segment[2::2])]
        mask = encode_mask(polygons_mask([{'role': 'outer', 'points': points}], width, height))
        objects.append({'id': f'historical_{index}', 'class_id': class_id, 'segmentation': mask,
                        'bbox': mask_bbox(mask)})
    return objects


def _sealed_reference(root, split, row, raw, snapshot_sha):
    objects = _historical_objects(raw['annotations']['segments'], row['width'], row['height'], row['id'])
    payload = {
        'objects': objects,
        'ignore_regions': [],
        'review_state': 'historical_reference_not_adjudicated_for_private_ladder',
        'image_sha256': row['image_sha256'],
        'source_row': row['source_row'],
        'snapshot_sha256': snapshot_sha,
        'format': 'Ultralytics NDJSON normalized polygons rasterized at native image dimensions',
    }
    asset = _freeze(root / 'reference' / split / f"{row['id']}.json", payload)
    return {**row, 'annotation': asset['path'], 'annotation_sha256': asset['sha256']}


def _verify_assets(entries):
    for path, expected in entries:
        _require(sha(path) == expected, f'Frozen asset changed: {path}')


def verify_prepared_inputs(root):
    """Recheck the private and public-to-the-trainer sides of a completed import."""
    root = Path(root).resolve()
    inputs = read(root / 'private_inputs.json')
    _require(inputs['schema_version'] == VERSION, 'Unsupported private ladder data version')
    development = inputs['development_index']
    _verify_assets((item['path'], item['sha256']) for item in [*inputs['assets'].values(), development])
    development_rows = read(development['path'])['rows']
    collections = {'train': inputs['train'], 'val': inputs['val'], 'test': development_rows}
    _require({split: len(rows) for split, rows in collections.items()} == SPLIT_COUNTS,
             'Private input counts differ after preparation')
    round_ids = [row['student_round_id'] for row in inputs['train'] if row.get('student_round_id')]
    _require(len(round_ids) == len(set(round_ids)) == 50, 'Student round overlap differs after preparation')
    groups, image_hashes, ids = {}, set(), set()
    for split, rows in collections.items():
        for row in rows:
            _require(groups.setdefault(row['group_id'], split) == split, 'A frozen group crosses splits')
            _require(row['image_sha256'] not in image_hashes and row['id'] not in ids,
                     'A frozen image is duplicated')
            image_hashes.add(row['image_sha256'])
            ids.add(row['id'])
            _verify_assets([(row['image'], row['image_sha256'])])
            if split == 'train':
                _require('annotation' not in row, 'Historical training reference exposed to the annotator')
            else:
                _verify_assets([(row['annotation'], row['annotation_sha256'])])
    return inputs


def prepare(root):
    """Prepare verified inputs for the 20→461 ladder without altering originals."""
    root = Path(root).resolve()
    outputs = (REPO / 'outputs').resolve()
    _require(root.parent == outputs, 'Use a dedicated top-level directory under outputs')
    pilot = outputs / 'daylight_augmentation_115_20261112' / 'pilot'
    snapshot = outputs / 'datasets' / 'union_anotadas_20261021_v1'
    round_root = outputs / 'revision_cruzada_uchuva_20261119' / 'coordinacion'
    source_paths = {'curated_manifest': pilot / 'real_manifest.json',
                    'historical_seal': pilot / 'training_source_lock.json',
                    'snapshot_metadata': snapshot / 'download_manifest.json',
                    'source_snapshot': snapshot / 'source_latest.ndjson',
                    'student_round': round_root / 'round.json'}
    _require(not any(path.is_relative_to(root) for path in source_paths.values()),
             'Private ladder cannot be prepared inside a frozen input directory')
    if (root / 'private_inputs.json').exists():
        return verify_prepared_inputs(root)

    assets = {name: _lock(path) for name, path in source_paths.items()}
    historical_seal = read(source_paths['historical_seal'])['files']
    manifest_hash = assets['curated_manifest']['sha256']
    _require(historical_seal.get(str(source_paths['curated_manifest'])) == manifest_hash,
             'The curated split differs from its historical seal')
    download = read(source_paths['snapshot_metadata'])
    snapshot_hash = assets['source_snapshot']['sha256']
    _require(snapshot_hash == download['source_sha256'], 'The original NDJSON snapshot changed')
    raw_rows = _read_snapshot(source_paths['source_snapshot'])
    metadata = raw_rows[1]
    _require(metadata.get('type') == 'dataset' and metadata.get('task') == 'segment'
             and metadata.get('class_names') == CLASS_NAMES == download['source_metadata']['class_names'],
             'The source is not segmentation data with the frozen three-class mapping')
    downloaded_images = {item['source_row']: item for item in download['images']}
    _require(len(downloaded_images) == len(download['images']), 'Duplicate source snapshot image rows')
    round_index = read(source_paths['student_round'])['images']
    round_images = {item['image_sha256']: ident for ident, item in round_index.items()}
    _require(len(round_index) == len(round_images) == 50, 'Expected 50 unique images in the student round')
    splits = _split_records(read(source_paths['curated_manifest'])['records'])
    _require(set(round_images) <= {row['image_sha256'] for row in splits['train']},
             'A student round image is missing from the fixed training inventory')

    output_rows = defaultdict(list)
    density = {}
    for records in splits.values():
        for record in records:
            split, position = record['split'], record['source_row']
            raw, download_row = raw_rows.get(position, {}), downloaded_images.get(position, {})
            _require(raw.get('type') == 'image' and raw.get('file') == record['file'] == download_row.get('file')
                     and download_row.get('sha256') == record['image_sha256'],
                     f'Original source record and image hash disagree for row {position}')
            image = Path(record['image']).resolve()
            _verify_assets([(image, record['image_sha256'])])
            with Image.open(image) as native:
                width, height = native.size
            _require((width, height) == (raw['width'], raw['height']), f'Image dimensions changed for row {position}')
            row = {'id': f'row_{position:04d}', 'source_row': position, 'image': str(image), 'width': width, 'height': height,
                   'group_id': record['group_id'], 'image_sha256': record['image_sha256']}
            if split == 'train':
                row['student_round_id'] = round_images.get(record['image_sha256'])
                density[row['id']] = len(raw['annotations']['segments'])
            output_rows[split].append(row)

    # Historical training geometry is absent from all sidecars. Validation and
    # development references stay distinct so development can be gated by the runner.
    train = _nested_order(output_rows['train'], density)
    val = [_sealed_reference(root, 'val', row, raw_rows[row['source_row']], snapshot_hash) for row in output_rows['val']]
    development = [_sealed_reference(root, 'development', row, raw_rows[row['source_row']], snapshot_hash)
                   for row in output_rows['test']]
    development_index = _freeze(root / 'reference' / 'development_index.json', {
        'rows': development,
        'status': 'historically_consulted_development_reference_not_independent_validation',
    })
    counts = {str(dose): dict(Counter(row['group_id'] for row in train[:dose])) for dose in DOSES}
    inputs = {'schema_version': VERSION, 'sampling_seed': SEED, 'train': train, 'val': val,
              'development_index': development_index, 'assets': assets,
              'census': {'splits': SPLIT_COUNTS, 'phase_capture_components': counts, 'student_overlap': 50,
                         'capture_session_independence_verified': False},
              'sampling': 'round-robin capture component and within-component density tertiles; historical density counts only'}
    _freeze(root / 'private_inputs.json', inputs)
    return inputs
