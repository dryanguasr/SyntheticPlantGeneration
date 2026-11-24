"""Extract, audit and seal a private set of new field-video frames."""

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import csv
import hashlib
from html import escape
import json
from pathlib import Path
import re
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from annotate_private_mask_ladder import DraftAnnotator, make_annotation, save_review_sheet
from reduce_video_redundancy import similar

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))
from uchuva_annotation_audit.store import SessionLock, atomic_json, read, sha
from uchuva_annotation_audit.masks import decode_mask

V6 = REPO / 'outputs/new_real_dataset/captura_20260912_v6'
BASELINE = REPO / 'outputs/daylight_augmentation_115_20261112/pilot/real_manifest.json'
PRIVATE = REPO / 'outputs/private_mask_ladder_20261121'
SOURCE_ROOT = REPO / 'Nuevo Dataset'
FRAME_NAME = re.compile(r'([0-9a-f]{16})_f(\d+)')
SOURCE_ID = re.compile(r'([0-9a-f]{16})_(?:f\d+|photo)')
MAX_CANDIDATES = 120
MAX_SEALED = 60


def jsonl(path):
    with path.open(encoding='utf-8-sig') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def group_inventory(manifest, historical):
    sources = {row['source_id']: row for row in manifest}
    known_splits = defaultdict(set)
    known_indices = defaultdict(set)
    anchors = defaultdict(list)
    for row in historical:
        name = Path(row['file']).stem
        source_match = SOURCE_ID.fullmatch(name)
        if source_match and source_match[1] in sources:
            known_splits[sources[source_match[1]]['group_id']].add(row['split'])
        frame_match = FRAME_NAME.fullmatch(name)
        if frame_match:
            source, index = frame_match[1], int(frame_match[2])
            known_indices[source].add(index)
            anchors[source].append((index, row))
    linked = defaultdict(set)
    with (V6 / 'pair_review.csv').open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            left, right = (sources[row[f'{side}_source']]['group_id'] for side in ('left', 'right'))
            if left != right and row['verdict'] in {'exact', 'pending'}:
                linked[left].add(right)
                linked[right].add(left)
    video_sources = {}
    for sid, row in sources.items():
        if row['kind'] != 'video':
            continue
        related = {row['group_id']}
        pending = list(related)
        while pending:
            current = pending.pop()
            adjacent = linked[current] - related
            related.update(adjacent)
            pending.extend(adjacent)
        splits = set().union(*(known_splits[group] for group in related))
        anchor_splits = Counter(anchor['split'] for _, anchor in anchors[sid])
        if splits & {'val', 'test'}:
            status = 'excluded_evaluation_or_related_capture'
        elif anchor_splits['train']:
            status = 'training_anchor'
        else:
            status = 'quarantine_no_training_anchor'
        video_sources[sid] = {
            'source': row['source'], 'sha256': row['source_sha256'],
            'group_id': min(related), 'recorded_capture_group': row['group_id'],
            'related_groups': sorted(related), 'linked_historical_splits': sorted(splits),
            'historical_frame_anchor_counts': anchor_splits, 'status': status,
        }
    return video_sources, known_indices, anchors


def choose_candidates(manifest, sources, known_indices, anchors):
    reserves = defaultdict(list)
    selected = []
    for row in manifest:
        sid = row['source_id']
        source = sources.get(sid)
        if (not source or source['status'] != 'training_anchor'
                or row['frame_index'] in known_indices[sid]):
            continue
        if row['selection'] == 'include':
            selected.append(row)
        elif row['selection'] == 'reserve':
            reserves[sid].append(row)
    initial = len(selected)
    existing_by_source = defaultdict(list)
    for row in selected:
        existing_by_source[row['source_id']].append(row['frame_index'])
    for sid, items in anchors.items():
        existing_by_source[sid].extend(index for index, _ in items)
    remaining = {sid: list(rows) for sid, rows in reserves.items()}
    while len(selected) < MAX_CANDIDATES and any(remaining.values()):
        for sid, pool in sorted(remaining.items()):
            if not pool or len(selected) == MAX_CANDIDATES:
                continue
            indices = existing_by_source[sid]
            row = max(pool, key=lambda r: (
                min(abs(r['frame_index'] - index) for index in indices),
                not r['quality_flags'], r['sharpness'], r['image_id'],
            ))
            selected.append(row)
            pool.remove(row)
            indices.append(row['frame_index'])
    return selected, initial, sum(map(len, reserves.values()))


def load_rgb(path):
    with Image.open(path) as stream:
        return stream.convert('RGB')


def rgb_digest(rgb):
    return hashlib.sha256(f'{rgb.width}x{rgb.height}\0'.encode() + rgb.tobytes()).hexdigest()


def oriented_rgb(frame, rotation):
    rgb = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    return rgb.rotate(-rotation, expand=True) if rotation else rgb


def seek_frame(capture, index):
    if not capture.set(cv2.CAP_PROP_POS_FRAMES, index):
        raise RuntimeError(f'Could not seek frame {index}')
    success, bgr = capture.read()
    if not success or round(capture.get(cv2.CAP_PROP_POS_FRAMES)) != index + 1:
        raise RuntimeError(f'Could not confirm decoded frame {index}')
    return bgr, capture.get(cv2.CAP_PROP_POS_MSEC) / 1000


def candidate_rgb(row, capture, export_rows, output):
    ident = row['image_id']
    if ident in export_rows:
        export = export_rows[ident]
        path = V6 / export['path']
        if sha(path) != export['sha256']:
            raise ValueError(f'Changed exported RGB: {ident}')
        rgb = load_rgb(path)
        if rgb.size != (export['width'], export['height']):
            raise ValueError(f'Wrong export dimensions: {ident}')
        return path, rgb, 'sha_verified_native_v6_export'
    bgr, offset = seek_frame(capture, row['frame_index'])
    decoded = oriented_rgb(bgr, 0)
    if (decoded.size != (row['width'], row['height'])
            or abs(offset - row['timestamp_seconds']) > .025
            or hashlib.sha256(decoded.tobytes()).hexdigest() != row['pixel_sha256']):
        raise ValueError(f'Decoded frame does not reproduce the v6 index: {ident}')
    rgb = oriented_rgb(bgr, row['rotation_cw'])
    path = output / 'native_rgb' / f'{ident}.png'
    if path.exists():
        if rgb_digest(load_rgb(path)) != rgb_digest(rgb):
            raise ValueError(f'Changed previously decoded RGB: {ident}')
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix('.tmp')
        rgb.save(partial, format='PNG', compress_level=1)
        partial.replace(path)
    return path, rgb, 'source_frame_verified_against_v6_decoder_hash'


def visual_features(rgb, orb):
    hashes = []
    gray = rgb.convert('L')
    for angle in (0, 90, 180, 270):
        image = gray.rotate(angle, expand=True) if angle else gray
        pixels = np.asarray(image.resize((9, 8), Image.Resampling.LANCZOS))
        hashes.append(int.from_bytes(np.packbits(pixels[:, 1:] > pixels[:, :-1]).tobytes(), 'big'))
    width, height = gray.size
    gray = gray.resize((round(width * 480 / max(width, height)),
                        round(height * 480 / max(width, height))), Image.Resampling.BOX)
    pixels = np.asarray(gray)
    points, desc = orb.detectAndCompute(pixels, None)
    return hashes, {'gray': pixels, 'points': np.float32([point.pt for point in points]), 'desc': desc}


def distance(left, right):
    return min((value ^ right[0]).bit_count() for value in left)


def compare(reference, hashes, features, source, index):
    ranked = sorted(((distance(hashes, other['dhash']), other['id'], other)
                     for other in reference), key=lambda row: row[:2])
    nearest = {}
    for hamming, _, other in ranked:
        nearest.setdefault(other['split'], {'id': other['id'], 'hamming': hamming})
    shortlist = [other for _, _, other in ranked[:12]]
    shortlist.extend(other for hamming, _, other in ranked if hamming <= 6)
    nearby = [other for other in reference if other.get('source_id') == source]
    shortlist.extend(sorted(nearby, key=lambda row: abs(row['frame_index'] - index))[:6])
    compared = set()
    warnings = []
    for other in shortlist:
        if other['id'] in compared:
            continue
        compared.add(other['id'])
        metrics = similar(features, other['features'])
        hamming = distance(hashes, other['dhash'])
        if metrics or hamming <= 6:
            warnings.append({'id': other['id'], 'split': other['split'],
                             'hamming': hamming, 'orb': metrics})
    return nearest, warnings


def pages(output, records):
    font = ImageFont.truetype('segoeui.ttf', 16)
    for start in range(0, len(records), 12):
        sheet = Image.new('RGB', (1536, 1312), '#172620')
        draw = ImageDraw.Draw(sheet)
        for offset, row in enumerate(records[start:start + 12]):
            left, top = offset % 3 * 512 + 4, offset // 3 * 328
            preview = load_rgb(row['image'])
            preview.thumbnail((501, 278), Image.Resampling.LANCZOS)
            draw.text((left, top + 6), f"{start + offset + 1:03d}  {row['id']}  s={row['timestamp_seconds']:.1f}",
                      font=font, fill='white')
            draw.text((left, top + 25), f"{row['origin_short']} · coincidencias {len(row['matches'])}",
                      font=font, fill='#9dedc9')
            sheet.paste(preview, (left, top + 46))
        path = output / 'contact' / f'frames_{start + 1:03d}_{min(start + 12, len(records)):03d}.jpg'
        path.parent.mkdir(exist_ok=True)
        sheet.save(path, quality=93)


def prepare(output):
    manifest = jsonl(V6 / 'manifest.jsonl')
    historical = read(BASELINE)['records']
    if Counter(row['split'] for row in historical) != {'train': 461, 'val': 88, 'test': 94}:
        raise ValueError('Historical reference membership changed')
    if any(sha(row['image']) != row['image_sha256'] for row in historical):
        raise ValueError('Historical reference RGB changed')
    exports = {row['image_id']: row for row in jsonl(V6 / 'export_manifest.jsonl')}
    sources, known_indices, anchors = group_inventory(manifest, historical)
    candidates, initial, available = choose_candidates(manifest, sources, known_indices, anchors)
    for sid, source in sources.items():
        if sha(SOURCE_ROOT / source['source']) != source['sha256']:
            raise ValueError(f'Original source changed: {sid}')
    print(f'{len(sources)} source hashes verified, {len(candidates)} candidate frames', flush=True)
    baseline = []
    orb = cv2.ORB_create(nfeatures=1800, fastThreshold=10)
    for row in historical:
        rgb = load_rgb(row['image'])
        hashes, features = visual_features(rgb, orb)
        match = FRAME_NAME.fullmatch(Path(row['file']).stem)
        baseline.append({'id': f"row_{row['source_row']:04d}", 'split': row['split'],
                         'dhash': hashes, 'features': features, 'sha256': row['image_sha256'],
                         'rgb_sha256': rgb_digest(rgb), 'source_id': match[1] if match else None,
                         'frame_index': int(match[2]) if match else None})
    print(f'{len(baseline)} historical RGB feature records', flush=True)
    extracted = []
    errors = []
    for sid in sorted({row['source_id'] for row in candidates}):
        source = sources[sid]
        full_path = SOURCE_ROOT / source['source']
        capture = cv2.VideoCapture(str(full_path))
        capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
        try:
            for row in sorted((r for r in candidates if r['source_id'] == sid),
                              key=lambda r: r['frame_index']):
                try:
                    path, rgb, origin = candidate_rgb(row, capture, exports, output)
                except (RuntimeError, ValueError) as error:
                    errors.append({'id': row['image_id'], 'source_id': sid, 'reason': str(error)})
                    continue
                hashes, features = visual_features(rgb, orb)
                fingerprint = rgb_digest(rgb)
                file_digest = sha(path)
                nearest, matches = compare(baseline, hashes, features, sid, row['frame_index'])
                exact = [other['id'] for other in baseline
                         if other['rgb_sha256'] == fingerprint or other['sha256'] == file_digest]
                record = {'id': row['image_id'], 'image': str(path), 'image_sha256': file_digest,
                          'rgb_sha256': fingerprint, 'width': rgb.width, 'height': rgb.height,
                          'source_id': sid, 'source': row['source'], 'source_sha256': source['sha256'],
                          'group_id': source['group_id'], 'frame_index': row['frame_index'],
                          'timestamp_seconds': row['timestamp_seconds'], 'rotation_cw': row['rotation_cw'],
                          'origin': origin, 'origin_short': 'V6' if row['selection'] == 'include' else 'Reserva',
                          'closest_historical': nearest, 'matches': matches, 'historical_exact': exact}
                extracted.append((record, hashes, features))
        finally:
            capture.release()
        print(f'{sid} processed, {len(extracted)} extracted, {len(errors)} errors', flush=True)
    risky_groups = {row['group_id'] for row, _, _ in extracted
                    if any(match['split'] in {'val', 'test'} for match in row['matches'])
                    or any(next(other['split'] for other in baseline if other['id'] == ident) in {'val', 'test'}
                           for ident in row['historical_exact'])}
    compared = []
    records = []
    for row, hashes, features in sorted(extracted, key=lambda item: (item[0]['origin_short'] != 'V6',
                                                                    item[0]['source_id'], item[0]['frame_index'])):
        _, candidate_matches = compare(compared, hashes, features, row['source_id'], row['frame_index'])
        exact = [other['id'] for other in compared if other['rgb_sha256'] == row['rgb_sha256']]
        row['candidate_matches'] = candidate_matches
        row['candidate_exact'] = exact
        row['precheck'] = ('quarantine_link_to_evaluation' if row['group_id'] in risky_groups else
                           'duplicate_review' if row['matches'] or row['historical_exact'] or candidate_matches or exact
                           else 'eligible_for_visual_review')
        if row['precheck'] == 'eligible_for_visual_review':
            compared.append(dict(row, dhash=hashes, features=features, split='candidate'))
        records.append(row)
    record = {
        'schema_version': 'private-field-video-candidates/1', 'historical_rows': len(historical),
        'input_hashes': {str(path): sha(path) for path in (BASELINE, V6 / 'manifest.jsonl',
                                                          V6 / 'export_manifest.jsonl', V6 / 'pair_review.csv')},
        'source_inventory': sources, 'historical_exports_selected': initial,
        'train_anchored_reserve_available': available, 'selected_for_precheck': len(candidates),
        'quarantined_after_comparison': sorted(risky_groups), 'candidates': records, 'decode_errors': errors,
        'comparison': {'dhash_max_candidate_distance': 6, 'orb_perceptual_neighbors': 12,
                       'orb_same_clip_neighbors': 6, 'notes': 'Similarity provides evidence, not physical separation.'},
    }
    atomic_json(output / 'candidates.json', record)
    pages(output, records)
    print(Counter(row['precheck'] for row in records), flush=True)


def pre_review(output, decisions_path):
    records = read(output / 'candidates.json')['candidates']
    decisions = read(decisions_path)
    if set(decisions) != {row['id'] for row in records}:
        raise ValueError('Visual decisions must account for every extracted candidate')
    selected = []
    for row in records:
        decision = decisions[row['id']]
        if not decision.get('reason'):
            raise ValueError(f'Missing visual rationale: {row["id"]}')
        if decision['admit_for_masks']:
            if row['precheck'] == 'quarantine_link_to_evaluation' or row['historical_exact'] or row['candidate_exact']:
                raise ValueError(f'Excluded candidate selected: {row["id"]}')
            if row['precheck'] == 'duplicate_review' and not decision.get('verified_distinct_match'):
                raise ValueError(f'Unresolved visual similarity candidate: {row["id"]}')
            selected.append(row)
    if len(selected) > MAX_SEALED:
        raise ValueError('Too many frames queued for masks')
    return selected


def draft(output, decisions_path):
    selected = pre_review(output, decisions_path)
    annotator = DraftAnnotator(read(PRIVATE / 'plan.json'))
    for index, row in enumerate(selected, 1):
        destination = output / 'drafts' / f'{row["id"]}.json'
        destination.parent.mkdir(exist_ok=True)
        record = read(destination) if destination.exists() else annotator.draft(row)
        if not destination.exists():
            atomic_json(destination, record, exclusive=True)
        sheet = output / 'mask_review' / f'{row["id"]}.jpg'
        if not sheet.exists():
            save_review_sheet(row, record, sheet)
        print(f'{index}/{len(selected)} {row["id"]} {len(record["candidates"])} MobileSAM candidates', flush=True)


def sealed_overlay(row, record, target):
    rgb = load_rgb(row['image'])
    rgb.thumbnail((960, 840), Image.Resampling.LANCZOS)
    overlay = rgb.copy()
    colors = {0: '#22e3a0', 1: '#ffd534', 2: '#ff68b0', None: '#dce3de'}
    layers = [(region, None) for region in record['ignore_regions']]
    layers.extend((obj['segmentation'], obj['class_id']) for obj in record['objects'])
    for segmentation, label in sorted(layers, key=lambda layer: layer[1] is not None):
        mask = decode_mask(segmentation).resize(rgb.size, Image.Resampling.NEAREST)
        opacity = mask.point(lambda p: (100 if label is None else 136) if p else 0)
        overlay.paste(colors[label], (0, 0), opacity)
    compare_rgb = Image.new('RGB', (rgb.width * 2, rgb.height + 34), '#172620')
    compare_rgb.paste(rgb, (0, 34))
    compare_rgb.paste(overlay, (rgb.width, 34))
    draw = ImageDraw.Draw(compare_rgb)
    font = ImageFont.truetype('segoeui.ttf', 15)
    count = Counter(obj['class_id'] for obj in record['objects'])
    draw.text((8, 7), row['id'], fill='white', font=font)
    draw.text((rgb.width + 8, 7),
              f"P {count[0]}   M {count[1]}   S {count[2]}   Inciertas {count[None]}   Exclusiones {len(record['ignore_regions'])}",
              fill='white', font=font)
    target.parent.mkdir(exist_ok=True)
    temporary = target.with_suffix('.tmp')
    compare_rgb.save(temporary, format='JPEG', quality=93)
    temporary.replace(target)


def seal(output, decisions_path, mask_decisions_path):
    if (output / 'frame_manifest.json').exists():
        raise FileExistsError('This frame cohort is already sealed. Use a new private output for revisions.')
    selected = pre_review(output, decisions_path)
    selected_ids = {row['id'] for row in selected}
    candidate_records = read(output / 'candidates.json')['candidates']
    shortlisted = read(decisions_path)
    decisions = read(mask_decisions_path) if mask_decisions_path else {}
    if set(decisions) != selected_ids:
        raise ValueError('Explicit mask decisions required for all shortlisted frames')
    train = []
    discarded = {}
    class_counts = Counter()
    ignore_count = 0
    annotations = output / 'annotations'
    annotations.mkdir(exist_ok=True)
    mask_decisions_sha = sha(mask_decisions_path) if mask_decisions_path else None
    for row in selected:
        decision = decisions[row['id']]
        if not decision['admit']:
            if not decision.get('reason'):
                raise ValueError(f'Missing reason for rejecting a frame: {row["id"]}')
            discarded[row['id']] = decision['reason']
            continue
        if sha(row['image']) != row['image_sha256']:
            raise ValueError(f'Candidate RGB changed: {row["id"]}')
        draft_record = read(output / 'drafts' / f'{row["id"]}.json')
        decision['decision_digest'] = mask_decisions_sha
        annotation = make_annotation(row, draft_record, decision)
        annotation['video_lineage'] = {key: row[key] for key in ('source', 'source_sha256', 'source_id',
                                                                  'timestamp_seconds', 'frame_index', 'group_id')}
        resolved = sum(obj['class_id'] is not None for obj in annotation['objects'])
        if not resolved:
            raise ValueError(f'No resolved foreground in admitted frame: {row["id"]}')
        path = annotations / f'{row["id"]}.json'
        atomic_json(path, annotation)
        sealed_overlay(row, annotation, output / 'sealed_review' / f'{row["id"]}.jpg')
        class_counts.update(str(obj['class_id']) for obj in annotation['objects'])
        ignore_count += len(annotation['ignore_regions'])
        train.append(dict(row, annotation=str(path), annotation_sha256=sha(path), resolved_masks=resolved))
    counts = Counter(row['group_id'] for row in train)
    usable = len(train) >= 20 and len(counts) >= 3 and max(counts.values(), default=0) * 2 <= len(train)
    state = {'schema_version': 'private-field-video-masks/1', 'eligible_for_training': usable,
             'train': train if usable else [], 'sealed_but_below_gate': [] if usable else train,
             'candidate_count': len(candidate_records), 'mask_review_count': len(selected),
             'group_counts': counts, 'sealed_count': len(train), 'mask_review_rejected': discarded,
             'class_counts': class_counts, 'explicit_ignore_regions': ignore_count,
             'reviewed_by': 'Codex', 'human_adjudicated': False,
             'candidates_sha256': sha(output / 'candidates.json'),
             'triage_sha256': sha(decisions_path),
             'mask_decisions_sha256': mask_decisions_sha}
    cards = []
    admitted_ids = {row['id'] for row in train}
    for ordinal, row in enumerate(candidate_records):
        ident = row['id']
        mask_review = output / 'mask_review' / f'{ident}.jpg'
        if ident in admitted_ids:
            image = output / 'sealed_review' / f'{ident}.jpg'
        else:
            image = mask_review if mask_review.is_file() else Path(row['image'])
        note = discarded.get(ident, shortlisted[ident]['reason'])
        admitted = ' · sellado' if ident in admitted_ids else ''
        cards.append(f'<article><h2>{ordinal + 1:03d} · {escape(ident)}{admitted}</h2>'
                     f'<p>{escape(note)}</p><a href="{image.as_uri()}"><img loading="lazy" src="{image.as_uri()}" '
                     f'alt="{escape(ident)}"></a><p>{escape(row["group_id"])} · {row["timestamp_seconds"]:.3f} s</p></article>')
    (output / 'galeria.html').write_text(
        '<!doctype html><html lang="es"><meta charset="utf-8"><title>Revisión privada de fotogramas</title>'
        '<style>body{font:16px system-ui;margin:2rem;color:#e8f4ec;background:#122019}'
        'main{display:grid;grid-template-columns:repeat(auto-fit,minmax(21rem,1fr));gap:1rem}'
        'article{padding:1rem;background:#213429;border-radius:12px}h2{font-size:1rem}img{width:100%}</style>'
        f'<h1>Revisión privada de fotogramas</h1><p>{len(candidate_records)} candidatos · {len(train)} sellados · '
        f'{len(counts)} grupos de captura</p><main>' + ''.join(cards) + '</main></html>', encoding='utf-8')
    atomic_json(output / 'frame_manifest.json', state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('command', choices=('prepare', 'draft', 'seal'))
    parser.add_argument('--decisions', type=Path)
    parser.add_argument('--mask-decisions', type=Path)
    args = parser.parse_args()
    if args.command in ('draft', 'seal') and not args.decisions:
        parser.error(f'{args.command} requires --decisions')
    if args.command == 'seal' and not args.mask_decisions:
        parser.error('seal requires --mask-decisions')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    cv2.setNumThreads(2)
    with closing(SessionLock(output / 'frame_audit.lock')):
        if args.command == 'prepare':
            prepare(output)
        elif args.command == 'draft':
            draft(output, args.decisions)
        else:
            seal(output, args.decisions, args.mask_decisions)


if __name__ == '__main__':
    main()
