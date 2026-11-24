"""Build or benchmark native mask projections from private training rows on CPU."""

import argparse
import json
from pathlib import Path
import statistics
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))

from run_private_mask_ladder import DEFAULT_ROOT, PHASES, private_root, snapshot_sources, verify
from uchuva_annotation_audit.store import atomic_json, read, sha


def selected_rows(root, phase, requested_ids, limit):
    plan_path = root / 'plan.json'
    inventory_path = root / 'private_inputs.json'
    seal = read(root / 'inputs_lock.json')
    verify(plan_path, seal['plan_sha256'])
    verify(inventory_path, seal['inventory_sha256'])
    snapshot_sources(root)
    plan = read(plan_path)
    if plan['size'] != 960 or phase not in plan['phases']:
        raise ValueError('The phase is outside the sealed 960-pixel campaign')
    expected = read(inventory_path)['train'][:phase]
    by_id = {row['id']: row for row in expected}
    if len(by_id) != phase or len(set(requested_ids)) != len(requested_ids) or not set(requested_ids).issubset(by_id):
        raise ValueError('Unexpected or repeated training identity in the selected phase')
    requested = set(requested_ids)
    ordered = [row for row in expected if not requested or row['id'] in requested]
    if limit is not None:
        ordered = ordered[:limit]
    manifest = root / 'phases' / f'{phase:03d}' / 'manifest.json'
    recorded = None
    if manifest.is_file():
        training = read(manifest)['train']
        if [row['id'] for row in training] != list(by_id):
            raise ValueError('The sealed phase order differs from the private inventory')
        recorded = {row['id']: row for row in training}
    output = []
    for row in ordered:
        ident = row['id']
        ann = (root / 'annotations' / f'{ident}.json').resolve()
        if ann.parent != root / 'annotations':
            raise ValueError(f'Annotation path escapes the private training directory: {ident}')
        document = read(ann)
        if (document['review_state'] != 'assistant_visual_reviewed' or document['id'] != ident
                or document['image_sha256'] != row['image_sha256']
                or document['size'] != [row['width'], row['height']]):
            raise ValueError(f'Missing exact reviewed training annotation: {ident}')
        projected_row = dict(row, annotation=str(ann), annotation_sha256=sha(ann))
        if recorded is not None and recorded[ident] != projected_row:
            raise ValueError(f'Training annotation differs from the sealed phase: {ident}')
        output.append(projected_row)
    return output, plan['size']


def check_exact(first, second):
    if first.dtype != second.dtype or first.shape != second.shape or first.tobytes() != second.tobytes():
        raise ValueError('The cached and original projection differ in dtype, shape or bytes')


def benchmark(cache, dataset):
    from uchuva_annotation_audit.private_training import PrivateDataset

    entries = cache.preflight(dataset.rows)
    times = []
    for index, entry in enumerate(entries):
        start = time.perf_counter()
        baseline = dataset._prepare(index)
        project_seconds = time.perf_counter() - start
        reads = []
        for _ in range(3):
            start = time.perf_counter()
            projected = cache.load(entry)
            reads.append(time.perf_counter() - start)
            for first, second in zip(baseline, projected, strict=True):
                check_exact(first, second)
        times.append(dict(id=entry.binding['id'], archive_bytes=entry.fingerprint[0], masks=len(baseline[1]),
                          direct_seconds=project_seconds, cache_read_seconds=reads))
    cached = PrivateDataset(dataset.rows, dataset.order, dataset.seed, dataset.size, dataset.ratio)
    frozen = cache.bind(cached)
    for slot in range(len(dataset)):
        direct, prepared = dataset[slot], cached[slot]
        for field in direct:
            first, second = direct[field], prepared[field]
            if hasattr(first, 'numpy'):
                check_exact(first.numpy(), second.numpy())
            elif first != second:
                raise ValueError(f'The prepared and original sample differ at slot {slot}: {field}')
    direct = [row['direct_seconds'] for row in times]
    readers = [statistics.median(row['cache_read_seconds']) for row in times]
    return dict(frozen, timings=times, exact_projected_arrays=True, exact_augmented_slots=len(dataset),
                median_direct_seconds=statistics.median(direct), median_cache_read_seconds=statistics.median(readers),
                measured_after_files_created=True)


def seal_manifest(root, cache, rows):
    from uchuva_annotation_audit.prepared_mask_cache import digest

    entries = cache.preflight(rows)
    receipts = {str(phase): dict(protocol_key=cache.protocol_key, rows=phase,
                                  entries_sha256=digest([(entry.binding, entry.sha256) for entry in entries[:phase]]))
                for phase in PHASES}
    path = root / 'revisions' / 'prepared_cache_20261121' / 'cache_manifest.json'
    payload = dict(version=1, phase_receipts=receipts)
    if path.exists():
        if read(path) != payload:
            raise ValueError(f'Existing cache manifest differs: {path}')
    else:
        atomic_json(path, payload, exclusive=True)
    return dict(rows=len(entries), manifest=str(path), manifest_sha256=sha(path), phase_receipts=receipts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('build', 'check', 'benchmark', 'manifest'))
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--phase', type=int, choices=PHASES, required=True)
    parser.add_argument('--row-id', action='append', default=[])
    parser.add_argument('--limit', type=int)
    parser.add_argument('--cpu-threads', type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error('--limit must be positive')
    if args.action == 'manifest' and (args.phase != PHASES[-1] or args.limit is not None or args.row_id):
        parser.error('manifest requires the complete 461-photo training cohort')
    root = private_root(args.root)
    limit = args.limit
    if args.action == 'benchmark' and limit is None and not args.row_id:
        limit = 3
    rows, size = selected_rows(root, args.phase, args.row_id, limit)

    import cv2
    import torch
    from uchuva_annotation_audit.prepared_mask_cache import PreparedMaskCache
    from uchuva_annotation_audit.private_training import PrivateDataset

    cv2.setNumThreads(1)  # Matches the frozen trainer's projection environment.
    torch.set_num_threads(args.cpu_threads)
    cache = PreparedMaskCache(root, size=size)
    if args.action == 'manifest':
        print(json.dumps(seal_manifest(root, cache, rows), indent=2), flush=True)
        return
    order = list(range(len(rows))) + list(reversed(range(len(rows))))
    dataset = PrivateDataset(rows, order, 20261022, size=size)
    started = time.perf_counter()
    created = cache.build(dataset) if args.action != 'check' else 0
    build_seconds = time.perf_counter() - started
    if args.action == 'benchmark':
        result = benchmark(cache, dataset)
    else:
        result = cache.bind(dataset)
    print(json.dumps(dict(result, phase=args.phase, cache=str(cache.root), created=created,
                          build_seconds=build_seconds, threads=args.cpu_threads), indent=2), flush=True)


if __name__ == '__main__':
    main()
