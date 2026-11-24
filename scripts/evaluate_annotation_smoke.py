"""Evaluator-only instance mask check; never supplies truth to inference."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--truth', type=Path, required=True)
    parser.add_argument('--predictions', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for frame, view in enumerate(('whole', 'detail', 'side'), 1):
        annotation = json.loads((args.truth / f'814144_{view}_annotations/annotations.json').read_text())
        pixels = np.asarray(Image.open(annotation['path']).convert('RGB'))
        truth = {key: np.all(pixels == annotation['palette'][key], axis=2)
                 for key, item in annotation['items'].items()
                 if key != '0' and item['visible_pixels'] > 0}
        record = json.loads((args.predictions / f'{frame}.json').read_text())
        archive_path = args.predictions / f'{frame}.npz'
        assert hashlib.sha256(archive_path.read_bytes()).hexdigest() == record['masks_sha256']
        with np.load(archive_path) as archive:
            height, width = map(int, archive['shape'])
            packed = archive['packed_masks']
        assert pixels.shape[:2] == (height, width)
        accepted = sorted((p for p in record['proposals'] if p['accepted']),
                          key=lambda p: -p['confidence'])
        unmatched = set(truth)
        matches = []
        for proposal in accepted:
            mask = np.unpackbits(packed[proposal['mask_reference']['index']])[:height*width].reshape(height, width).astype(bool)
            scores = [(np.count_nonzero(mask & truth[key]) / max(1, np.count_nonzero(mask | truth[key])), key)
                      for key in sorted(unmatched)]
            if scores:
                iou, key = max(scores)
                if iou >= .5:
                    unmatched.remove(key)
                    matches.append(dict(observation_id=proposal['observation_id'], truth_id=key, iou=iou))
        tp = len(matches)
        rows.append(dict(view=view, visible_instances=len(truth), accepted_predictions=len(accepted),
                         true_positives=tp, false_positives=len(accepted)-tp, false_negatives=len(unmatched),
                         matches=matches))
    tp = sum(row['true_positives'] for row in rows)
    predicted = sum(row['accepted_predictions'] for row in rows)
    visible = sum(row['visible_instances'] for row in rows)
    result = dict(version='annotation-smoke-evaluation/1.0', mask_iou_threshold=.5,
                  matching='confidence ordered one-to-one, class agnostic', rows=rows,
                  pooled_true_positives=tp, pooled_visible_instances=visible,
                  precision=tp/max(1, predicted), recall=tp/max(1, visible),
                  limitations=['Three views of one development plant; repeated objects across views',
                               'Any nonzero visible pixel qualifies; no hidden-object denominator',
                               'Orthographic diagnostic with unresolved geometry contacts; not drone accuracy',
                               'No maturity evaluation or training acceptance'])
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({key: value for key, value in result.items() if key != 'rows'}))


if __name__ == '__main__':
    main()
