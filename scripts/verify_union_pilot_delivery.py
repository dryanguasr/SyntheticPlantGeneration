"""Verify frozen inputs, split isolation, resumable checkpoints and video records."""
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path

import torch
from prepare_union_pilot import ROOT, SOURCE, sha, write


def main():
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    readiness = json.loads((ROOT / 'readiness.json').read_text())
    assert sha(ROOT / 'manifest.json') == readiness['manifest_sha256']
    assert sha(SOURCE / 'source_latest.ndjson') == manifest['source_sha256']
    assert sha(ROOT / 'inputs/source_latest.ndjson') == manifest['source_sha256']
    for item in json.loads((ROOT / 'inputs/manifest.json').read_text()):
        assert sha(item['original']) == sha(item['copy']) == item['sha256']
    hashes, groups = defaultdict(set), defaultdict(set)
    for row in manifest['records']:
        assert sha(row['source_path']) == row['sha256']
        if row['status'] != 'included':
            continue
        assert sha(ROOT / row['image']) == row['sha256']
        assert sha(ROOT / row['label']) == row['label_sha256']
        hashes[row['sha256']].add(row['split'])
        groups[row['group_id']].add(row['split'])
    assert all(len(v) == 1 for v in hashes.values())
    assert all(len(v) == 1 for v in groups.values())
    status = json.loads((ROOT / 'pipeline_status.json').read_text())
    assert status['stage'] == 'completed'
    if 'mixed' in status['arms']:
        mixture_root = ROOT / 'mixed_dataset'
        mixture = json.loads((mixture_root / 'manifest.json').read_text())
        for row in mixture['records']:
            assert sha(mixture_root / 'images/train' / row['image']) == row['image_sha256']
            label = Path(row['image']).with_suffix('.txt').name
            assert sha(mixture_root / 'labels/train' / label) == row['label_sha256']
            if row['domain'] == 'synthetic':
                assert sha(row['source_image']) == row['image_sha256']
    lock = json.loads((ROOT / 'evaluation_lock.json').read_text())
    assert sha(ROOT / 'protocol.json') == lock['protocol_sha256']
    evidence = {}
    for arm in status['arms']:
        directory = ROOT / 'training' / arm
        assert sha(directory / 'weights/best.pt') == lock['arms'][arm]['weights_sha256']
        dataset_manifest = ROOT / 'manifest.json' if arm == 'real' else ROOT / 'mixed_dataset/manifest.json'
        assert sha(dataset_manifest) == lock['arms'][arm]['dataset_manifest_sha256']
        assert sha(ROOT / f'{arm}_training_config.json') == lock['arms'][arm]['training_config_sha256']
        epochs = sorted((directory / 'weights').glob('epoch*.pt'),
                        key=lambda p: int(p.stem.removeprefix('epoch')))
        # best/last are stripped by Ultralytics; periodic snapshots retain optimizer state.
        checkpoint = torch.load(epochs[-1], map_location='cpu', weights_only=False)
        assert checkpoint['epoch'] >= 0 and checkpoint.get('optimizer')
        evidence[arm] = {'resumable_checkpoint': str(epochs[-1]),
                         'checkpoint_sha256': sha(epochs[-1]), 'epoch_zero_based': checkpoint['epoch'],
                         'optimizer_state_present': True, 'videos': []}
        for summary in json.loads((ROOT / 'videos' / arm / 'summary.json').read_text()):
            video = summary['video']
            assert sha(summary['video_path']) == summary['video_sha256']
            expected = json.loads((ROOT / 'references' / f'{video}_aruco.json').read_text())
            records = [json.loads(line) for line in (ROOT / 'videos' / arm / video / 'observations.jsonl').read_text().splitlines()]
            assert len(records) == len(expected) == summary['frames']
            assert [r['frame_index'] for r in records] == [r['frame_index'] for r in expected]
            assert all(b['timestamp_seconds'] > a['timestamp_seconds'] for a, b in zip(records, records[1:]))
            assert all(r['metric_pose_status'] == 'unavailable' and not r['manual_truth_used_by_estimator'] for r in records)
            evidence[arm]['videos'].append({'video': video, 'frames_verified': len(records)})
    write(ROOT / 'delivery_integrity.json', {
        'verified_at_utc': datetime.now(timezone.utc).isoformat(),
        'original_and_derived_hashes_unchanged': True, 'split_hash_and_group_isolation': True,
        'frozen_selection_verified': True, 'arms': evidence})
    print('Input integrity, split isolation, resumable checkpoints and video timestamps verified.')


if __name__ == '__main__':
    main()
