"""Convert the sealed corrected captures to private native instance RLE masks."""

import argparse
from collections import Counter, defaultdict
from contextlib import closing
from math import isfinite, log1p, sqrt
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))

from uchuva_annotation_audit.masks import VERSION, area, intervals, mask_bbox
from uchuva_annotation_audit.prepared_mask_cache import PreparedMaskCache, input_binding, write_projection
from uchuva_annotation_audit.store import SessionLock, atomic_json, read, sha

COMPLETE_VIEWS = 115
SIZE = (960, 720)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def indexing(mask_path, palette):
    """Translate packed RGB colors to their exact visible instance IDs."""
    with Image.open(mask_path) as mask:
        require(mask.size == SIZE, f'Unexpected mask dimensions: {mask_path}')
        rgb = np.asarray(mask.convert('RGB'), dtype=np.uint32)
    colors = rgb[:, :, 0] << 16 | rgb[:, :, 1] << 8 | rgb[:, :, 2]
    unique, inverse = np.unique(colors, return_inverse=True)
    color_ids = {r << 16 | g << 8 | b: int(index) for index, (r, g, b) in palette.items()}
    require(len(color_ids) == len(palette) and set(unique).issubset(color_ids),
            f'Invalid or unknown instance palette colors: {mask_path}')
    lookup = np.asarray([color_ids[color] for color in unique], dtype=np.uint16)
    return lookup[inverse].reshape(-1)


def encode_instances(raster, width, height):
    """Encode only contiguous ID runs and preserve disconnected fragments and holes."""
    runs = defaultdict(list)
    transitions = np.flatnonzero(raster[1:] != raster[:-1]) + 1
    boundaries = np.concatenate(([0], transitions, [raster.size])).tolist()
    instance_ids = raster[boundaries[:-1]].tolist()
    for index, start, end in zip(instance_ids, boundaries, boundaries[1:]):
        if index:
            runs[index].append((start, end))
    masks = {}
    for index, spans in runs.items():
        counts = []
        previous = 0
        for start, end in spans:
            counts.extend((start - previous, end - start))
            previous = end
        if previous != raster.size:
            counts.append(raster.size - previous)
        masks[index] = {'version': VERSION, 'size': [height, width], 'counts': counts}
    return masks


def validate_masks(raster, objects):
    reconstructed = np.zeros_like(raster)
    for obj in objects:
        mask = obj['segmentation']
        require(area(mask) == obj['visible_pixels'] and mask_bbox(mask) == obj['bbox'],
                f'Invalid area or bounding box for {obj["id"]}')
        for start, end in intervals(mask):
            reconstructed[start:end] = obj['mask_id']
    require(np.array_equal(reconstructed, raster), 'Native RLE does not reproduce the indexed raster')


def checked_capture(row, bank, lock_hash, assignments):
    view_id = row['view_id']
    require(row['status'] == 'complete' and row['source_lock_sha256'] == lock_hash,
            f'Capture is incomplete or outside the frozen bank: {view_id}')
    for key in ('image', 'mask', 'label'):
        require(sha(row[key]) == row[f'{key}_sha256'], f'Changed {key}: {view_id}')
    with Image.open(row['image']) as image:
        require(image.size == SIZE and image.mode in ('RGB', 'RGBA'), f'Invalid RGB: {view_id}')
        image.verify()
    pixel_audit = bank / 'views' / view_id / 'pixel_audit.json'
    receipt_path = Path(row['mask_cache']['native_validation'])
    original_record = Path(row['source_record'])
    original = read(original_record)
    receipt = read(receipt_path)
    require(receipt['passed'] and receipt['source_lock_sha256'] == lock_hash,
            f'Native mask receipt failed: {view_id}')
    require(read(pixel_audit)['status'] == 'pass', f'Historical pixel audit failed: {view_id}')
    for key in ('view_id', 'scene_id', 'mask_sha256', 'geometry_sha256', 'camera_matrix'):
        require(row[key] == original[key], f'Capture provenance changed {key}: {view_id}')
    require(row['mask_sha256'] == row['mask_cache']['original_mask_sha256'],
            f'Native mask hash is not the preserved original: {view_id}')

    metadata_path = Path(row['mask']).parent / 'annotations.json'
    metadata = read(metadata_path)
    width, height = SIZE
    raster = indexing(row['mask'], metadata['palette'])
    encoded = encode_instances(raster, width, height)
    labels = Path(row['label']).read_text(encoding='utf-8').splitlines()
    require(len(labels) == len(row['instances']) == len(encoded),
            f'Missing/extra instance declarations: {view_id}')
    require({item['mask_id'] for item in row['instances']} == encoded.keys(),
            f'Declared instances differ from visible IDs: {view_id}')

    objects = []
    semantic_ids = set()
    for item, line in zip(row['instances'], labels, strict=True):
        mask_id = item['mask_id']
        native = metadata['items'][str(mask_id)]
        instance = item['instance_id']
        x, y, box_width, box_height = item['bbox_xywh']
        class_id = item['class_id']
        require(instance not in semantic_ids and native['instance_id'] == instance,
                f'Native mask identity mismatch: {view_id} / {mask_id}')
        semantic_ids.add(instance)
        require(native['semantic_class'] == 'calyx' and native['bbox_xywh'] == item['bbox_xywh']
                and native['visible_pixels'] == item['visible_pixels'],
                f'Native calyx metadata mismatch: {view_id} / {mask_id}')
        require(type(class_id) is int and 0 <= class_id < 3 and assignments[instance]['class_id'] == class_id,
                f'Changed corrected appearance class: {view_id} / {mask_id}')
        values = line.split()
        require(len(values) == 5 and int(values[0]) == class_id, f'Wrong YOLO class: {view_id} / {mask_id}')
        expected = ((x + box_width / 2) / width, (y + box_height / 2) / height,
                    box_width / width, box_height / height)
        errors = [abs(float(actual) - target) for actual, target in zip(values[1:], expected, strict=True)]
        require(all(isfinite(error) and error <= 1e-9 for error in errors),
                f'Wrong YOLO coordinates: {view_id} / {mask_id}')
        objects.append({'id': instance, 'mask_id': mask_id, 'class_id': class_id,
                        'bbox': [x, y, x + box_width, y + box_height],
                        'bbox_source': 'native_mask_pixels', 'visible_pixels': item['visible_pixels'],
                        'segmentation': encoded[mask_id]})
    validate_masks(raster, objects)
    receipts = {str(path): sha(path) for path in (pixel_audit, receipt_path, original_record, metadata_path)}
    return objects, receipts, raster


def framing_features(objects, width, height):
    valid = [obj for obj in objects if obj['class_id'] is not None]
    scale = 960 / max(width, height)
    sides = [sqrt(obj['visible_pixels'] if 'visible_pixels' in obj else area(obj['segmentation'])) * scale
             for obj in valid]
    return {'instance_count': len(valid), 'median_mask_side_at_960': float(np.median(sides)) if sides else None}


def framing_reference(real_manifest):
    real_rows = read(real_manifest)['train']
    require(len(real_rows) == 461, 'Expected the sealed 461-image real cohort')
    features = []
    for row in real_rows:
        require(sha(row['annotation']) == row['annotation_sha256'], f'Changed real annotation: {row["id"]}')
        annotation = read(row['annotation'])
        require(annotation['id'] == row['id'] and annotation['image_sha256'] == row['image_sha256']
                and annotation['size'] == [row['width'], row['height']], f'Real annotation identity mismatch: {row["id"]}')
        features.append(framing_features(annotation['objects'], row['width'], row['height']))
    result = {}
    for key in features[0]:
        values = [x[key] for x in features if x[key] is not None]
        q25, q50, q75 = np.percentile(np.log1p(values), [25, 50, 75])
        result[key] = {'raw_median': float(np.median(values)), 'log1p_median': float(q50),
                       'log1p_iqr': float(q75 - q25), 'images': len(values)}
    return result


def prioritize_framing(rows, reference):
    scenes = defaultdict(list)
    for row in rows:
        features = row['framing_features']
        distance = sum(abs(log1p(features[key]) - stats['log1p_median']) / max(stats['log1p_iqr'], .1)
                       for key, stats in reference.items())
        row['framing_distance'] = distance
        scenes[row['scene_id']].append(row)
    for scene_rows in scenes.values():
        ranked = sorted(scene_rows, key=lambda row: (row['framing_distance'], row['id']))
        for rank, row in enumerate(ranked):
            row['framing_priority'] = rank < (len(ranked) + 1) // 2


def project_aligned_raster(row, annotation, raster):
    """Equivalent any-pixel projection for the 960x720 captures on a 240 grid."""
    size, ratio, width, height = 960, 4, *SIZE
    grid = size // ratio
    top = (size - height) // 2
    require(top % ratio == 0, 'The capture letterbox is not aligned to the mask grid')
    image_bytes = np.fromfile(row['image'], dtype=np.uint8)
    image = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
    require(image is not None and image.shape[:2] == (height, width), 'Cannot decode the frozen synthetic RGB')
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    canvas[top:top + height] = image
    objects = annotation['objects']
    obj_index = np.full(int(raster.max()) + 1, -1, dtype=np.int32)
    obj_index[[obj['mask_id'] for obj in objects]] = np.arange(len(objects), dtype=np.int32)
    positive = np.flatnonzero(raster)
    y, x = np.divmod(positive, width)
    masks = np.zeros((len(objects), grid, grid), dtype=np.bool_)
    masks[obj_index[raster[positive]], (y + top) // ratio, x // ratio] = True
    require(np.all(masks.any(axis=(1, 2))), 'An instance disappeared on the aligned grid')
    classes = np.asarray([obj['class_id'] for obj in objects], dtype=np.int64)
    boxes = []
    scale = 1 / size
    for obj in objects:
        x1, y1, x2, y2 = obj['bbox']
        boxes.append([(x1 + x2) * scale / 2, (y1 + y2) * scale / 2 + top / size,
                      (x2 - x1) * scale, (y2 - y1) * scale])
    return canvas, masks, classes, np.asarray(boxes, dtype=np.float32), np.zeros((grid, grid), dtype=np.bool_)


def prepare_projection(cache, row, annotation, raster):
    binding = input_binding(row, cache.protocol_key)
    projection, receipt = cache.describe(binding)
    with closing(SessionLock(cache.root / 'writer.lock')):
        if not receipt.exists():
            value = project_aligned_raster(row, annotation, raster)
            write_projection(projection, value, binding, cache.size, cache.grid)
            atomic_json(receipt, {'binding': binding, 'sha256': sha(projection), 'bytes': projection.stat().st_size},
                        exclusive=True)
        entry = cache.preflight([row])[0]
    return {'path': str(projection), 'sha256': entry.sha256, 'receipt': str(receipt), 'binding': binding,
            'receipt_sha256': sha(receipt), 'bytes': projection.stat().st_size}


def check_projection_examples(cache, rows):
    from uchuva_annotation_audit.private_training import PrivateDataset

    by_density = sorted(rows, key=lambda row: row['instance_count'])
    examples = [by_density[index] for index in (0, len(rows) // 2, -1)]
    reference = PrivateDataset(examples, list(range(len(examples))), seed=20261022)
    entries = cache.preflight(examples)
    checks = []
    for index, row in enumerate(examples):
        direct = reference._prepare(index)
        cached = cache.load(entries[index])
        require(all(np.array_equal(expected, actual) for expected, actual in zip(direct, cached, strict=True)),
                f'Packed projection differs from PrivateDataset: {row["id"]}')
        checks.append({'id': row['id'], 'instance_count': row['instance_count'],
                       'identical_fields': ['rgb', 'masks', 'classes', 'boxes', 'ignored']})
        print(f'Packed projection checked: {row["id"]} ({row["instance_count"]} masks)', flush=True)
    return checks


def prepare(bank, real_manifest, output, cache_root):
    require(not output.is_relative_to(bank) and not output.is_relative_to(real_manifest.parents[2]),
            'Outputs must be separate from historical dataset roots')
    require(not cache_root.is_relative_to(bank) and not cache_root.is_relative_to(real_manifest.parents[2]),
            'Projections must be separate from historical dataset roots')
    manifest_path = bank / 'manifest.json'
    lock_path = bank / 'source_lock.json'
    seal_path = bank / 'sealed.json'
    manifest_hash, lock_hash = sha(manifest_path), sha(lock_path)
    seal = read(seal_path)
    require(seal['manifest_sha256'] == manifest_hash and seal['source_lock_sha256'] == lock_hash
            and seal['complete_images'] == COMPLETE_VIEWS and seal['rendering_stopped'], 'Bank seal failed')
    source = read(manifest_path)
    views = source['views']
    require(source['pixel_audited'] and source['complete_images'] == len(views) == COMPLETE_VIEWS
            and len({row['view_id'] for row in views}) == COMPLETE_VIEWS
            and len({row['image_sha256'] for row in views}) == COMPLETE_VIEWS,
            'Expected 115 unique pixel-audited captures')
    reference = framing_reference(real_manifest)
    cache = PreparedMaskCache(cache_root)
    cache.root.mkdir(parents=True, exist_ok=True)
    protocol_path = cache.root / 'protocol.json'
    with closing(SessionLock(cache.root / 'writer.lock')):
        if not protocol_path.exists():
            atomic_json(protocol_path, cache.protocol, exclusive=True)
        cache.check_protocol()
    rows = []
    source_receipts = {str(path): sha(path) for path in (manifest_path, lock_path, seal_path, real_manifest)}
    assignments = {}
    totals = Counter()
    for index, row in enumerate(views, 1):
        scene = row['scene_id']
        if scene not in assignments:
            path = bank / 'assignments' / f'{scene}.json'
            assignments[scene] = read(path)
            source_receipts[str(path)] = sha(path)
        objects, receipts, raster = checked_capture(row, bank, lock_hash, assignments[scene])
        source_receipts.update(receipts)
        ident = f'synthetic_{row["view_id"]}'
        width, height = SIZE
        annotation_path = output / 'annotations' / f'{ident}.json'
        annotation = {'id': ident, 'size': [width, height], 'image_sha256': row['image_sha256'],
                      'objects': objects, 'ignore_regions': [], 'full_image_uncertain': False,
                      'empty_confirmed': False, 'method': 'corrected_synthetic_native_id_raster',
                      'source_view': row['view_id'], 'source_manifest_sha256': manifest_hash,
                      'source_mask_sha256': row['mask_sha256']}
        if annotation_path.is_file():
            require(read(annotation_path) == annotation, f'Existing conversion changed: {ident}')
        else:
            atomic_json(annotation_path, annotation, exclusive=True)
        reread = read(annotation_path)
        require(reread == annotation, f'Serialized annotations differ from the conversion: {ident}')
        validate_masks(raster, reread['objects'])
        classes = Counter(str(obj['class_id']) for obj in objects)
        totals.update(classes)
        converted = {'id': ident, 'source_row': None, 'student_round_id': None,
                     'scene_id': scene, 'group_id': scene, 'image': row['image'],
                     'image_sha256': row['image_sha256'], 'width': width, 'height': height,
                     'annotation': str(annotation_path), 'annotation_sha256': sha(annotation_path),
                     'mask': row['mask'], 'mask_sha256': row['mask_sha256'],
                     'label': row['label'], 'label_sha256': row['label_sha256'],
                     'source_record': row['source_record'], 'view_id': row['view_id'],
                     'instance_count': len(objects), 'instance_counts': dict(classes),
                     'framing_features': framing_features(objects, width, height)}
        converted['projection'] = prepare_projection(cache, converted, reread, raster)
        rows.append(converted)
        if index % 10 == 0 or index == len(views):
            print(f'Native synth masks: {index}/{len(views)} views, {sum(totals.values())} masks', flush=True)
    prioritize_framing(rows, reference)
    examples = check_projection_examples(cache, rows)
    result = {'schema_version': 'private-synthetic-mask-bank/1', 'train': rows,
              'classes': {'0': 'Pintona', '1': 'Madura', '2': 'Sobremadura'},
              'images': len(rows), 'instances': sum(totals.values()), 'instance_counts': dict(totals),
              'scene_counts': dict(Counter(row['scene_id'] for row in rows)),
              'framing_priority_count': sum(row['framing_priority'] for row in rows),
              'framing_reference_960': reference, 'real_manifest_sha256': sha(real_manifest),
              'source_manifest_sha256': manifest_hash, 'pixel_exact_native_rle': True,
              'projection_cache': {'protocol_key': cache.protocol_key, 'path': str(cache.root),
                                   'input_protocol_sha256': sha(protocol_path), 'verified_examples': examples}}
    source_receipts[str(Path(__file__).resolve())] = sha(__file__)
    atomic_json(output / 'source_receipts.json', {'files': source_receipts})
    result['source_receipts_sha256'] = sha(output / 'source_receipts.json')
    atomic_json(output / 'manifest.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bank', type=Path, default=REPO / 'outputs/daylight_augmentation_115_20261112/bank')
    parser.add_argument('--real-manifest', type=Path,
                        default=REPO / 'outputs/private_mask_ladder_20261121/phases/461/manifest.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cache-root', type=Path)
    args = parser.parse_args()
    cv2.setNumThreads(1)
    result = prepare(args.bank.resolve(), args.real_manifest.resolve(), args.output.resolve(),
                     args.cache_root.resolve() if args.cache_root else args.output.resolve().parent)
    print(f'{result["images"]} views and {result["instances"]} masks verified, '
          f'{result["framing_priority_count"]} views prioritized for framing.')


if __name__ == '__main__':
    main()
