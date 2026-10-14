"""Rebuild geometric support from RGB observations; never read evaluator data."""
import argparse
import collections
import copy
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uchuva_gazebo.localization import robust_triangulate, reconcile
from uchuva_lsystem.segmentation_cycles import write, sha, check_deadline


def supported_candidate(fit, observations, minimum):
    """Return only actual geometric inliers, retaining rejected IDs separately."""
    accepted = set(fit.get('inlier_observation_ids', []))
    support = [o for o in observations if o['observation_id'] in accepted]
    uncertainty = fit.get('uncertainty_m')
    reasons = []
    if len(support) < minimum:
        reasons.append('insufficient_geometric_support')
    if len(support) / max(1, len(observations)) < .7:
        reasons.append('inconsistent_track')
    if uncertainty is None or uncertainty > .03:
        reasons.append('unstable_triangulation')
    return support, reasons


def main():
    parser = argparse.ArgumentParser()
    for name in ('root', 'public', 'source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    calibration = json.loads((args.public / 'calibration.json').read_text())
    provenance = json.loads((args.source / 'provenance.json').read_text())
    if provenance['ground_truth_inputs'] or provenance['calibration_sha256'] != sha(args.public / 'calibration.json'):
        raise ValueError('Source must use the same public calibration and no truth')
    rigs = {str(r['id']): r for r in calibration['rig']}
    tracks = collections.defaultdict(list)
    descriptors = collections.defaultdict(list)
    classes = collections.defaultdict(list)
    for line in (args.source / 'observations.jsonl').read_text().splitlines():
        frame = json.loads(line)
        for detection in frame['detections']:
            tid = detection['track_id']
            descriptors[tid].append(detection['appearance'])
            classes[tid].append(detection['class_id'])
            # A single RGB observation may not count twice through a rigid pair.
            seen = set()
            for marker, pose in frame['marker_poses'].items():
                canonical = rigs[marker]['canonical_id']
                if canonical in seen:
                    continue
                seen.add(canonical)
                tracks[tid, canonical].append(dict(**pose, marker_id=canonical,
                    point_px=detection['center_px'], stamp_ns=frame['stamp_ns'],
                    observation_id=detection['observation_id']))
    fitted = collections.defaultdict(list)
    rejected = []
    for index, ((tid, marker), observations) in enumerate(tracks.items()):
        check_deadline(args.root)
        fit = robust_triangulate(observations, calibration['K'])
        if fit['status'] != 'estimated':
            rejected.append(dict(track_id=tid, marker_id=marker, **fit))
            continue
        x, y, z = fit['position_marker_m']
        if abs(x) > 1.2 or not -.25 <= y <= 3 or not -1.5 <= z <= .7:
            rejected.append(dict(track_id=tid, marker_id=marker, reason='outside_public_plant_envelope'))
            continue
        descriptor = np.mean(descriptors[tid], axis=0)
        descriptor /= max(np.linalg.norm(descriptor), 1e-9)
        fitted[tid].append(dict(**fit, marker_id=marker, track_ids=[tid],
            appearance=descriptor.tolist(), class_id=collections.Counter(classes[tid]).most_common(1)[0][0],
            source_observations=observations, association_cost=float(abs(x)+.3*abs(z+.18))))
        if index % 100 == 0:
            print('SUPPORT_REFIT', index, len(tracks), flush=True)
    for minimum in (5, 8):
        candidates = []
        provisional = []
        failures = copy.deepcopy(rejected)
        for tid, alternatives in fitted.items():
            values = sorted(alternatives, key=lambda value: value['association_cost'])
            if len(values) > 1 and values[1]['association_cost'] - values[0]['association_cost'] < .15:
                failures.append(dict(track_id=tid, reason='ambiguous_plant_marker'))
                continue
            candidate = copy.deepcopy(values[0])
            observations = candidate.pop('source_observations')
            support, reasons = supported_candidate(candidate, observations, minimum)
            candidate['stamps'] = [o['stamp_ns'] for o in support]
            candidate['observation_ids'] = [o['observation_id'] for o in support]
            candidate['excluded_observation_ids'] = [o['observation_id'] for o in observations if o not in support]
            if reasons:
                candidate.update(state='provisional', rejection_reasons=reasons,
                                 map_id=f'provisional_{len(provisional):06d}')
                provisional.append(candidate)
            else:
                candidates.append(candidate)
        # Conservative identity reconciliation: existing non-simultaneous rule.
        objects = reconcile(candidates)
        for item in objects:
            item['state'] = 'provisional' if item.get('reconciliation_status') == 'ambiguous' else 'confirmed'
        destination = args.output / f'support_{minimum}'
        destination.mkdir()
        os.link(args.source / 'observations.jsonl', destination / 'observations.jsonl')
        write(destination / 'map.json', dict(version='calyx-marker-map/1.1',
            units='metres', objects=objects+provisional, rejected=failures,
            center_semantics='visible-mask centroid proxy; not hidden fruit centre'))
        write(destination / 'provenance.json', dict(**{k:v for k,v in provenance.items() if k not in ('version','variant')},
            version='marker-localization-support/1.0', variant=f'support_{minimum}',
            source_observations_sha256=sha(args.source / 'observations.jsonl'),
            confirmation=dict(minimum_inliers=minimum, minimum_fraction=.7, maximum_sensitivity_m=.03),
            timing_note='Reused RGB detections; source latency is not this refinement runtime'))
        print('SUPPORT_COMPLETE', minimum, len(objects), len(provisional), flush=True)


if __name__ == '__main__':
    main()
