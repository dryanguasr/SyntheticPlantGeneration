#!/usr/bin/env python3
"""Bound continuous nominal CAD gaps from a complete native BRep motion scan.

This does not authorize collision exclusions or change any acceptance margin.
The speed bounds apply to the ideal rigid four-bar path; native closure drift,
mesh tessellation, gear tracking error and hardware uncertainty remain separate.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def summarize(motion, observation, *, maximum_driver=None):
    if observation.get('status') != 'COMPLETED' or observation.get('source_files_unchanged') is not True:
        raise ValueError('A complete native BRep scan with unchanged sources is required')
    if observation.get('assembly_sha256', '').lower() != motion['assembly_sha256'].lower():
        raise ValueError('Native observation and analytical path have different CAD sources')
    samples = motion['samples']
    if maximum_driver is not None:
        samples = [row for row in samples if row['driver_rad'] <= maximum_driver + 1e-12]
        if not samples or abs(samples[-1]['driver_rad']-maximum_driver) > 1e-12:
            raise ValueError('A restricted interval must end at a native observation')
    coordinates = [row['driver_rad'] for row in samples]
    if len(coordinates) < 2 or any(b <= a for a,b in zip(coordinates, coordinates[1:])):
        raise ValueError('The scan must cover a strictly increasing nonzero interval')
    interval = max(b-a for a,b in zip(coordinates, coordinates[1:]))
    pairs = {}
    for row in observation['pairs']:
        if row['driver_rad'] < coordinates[0]-1e-12 or row['driver_rad'] > coordinates[-1]+1e-12:
            continue
        pairs.setdefault(tuple(row['occurrences']), []).append(row)
    if not pairs:
        raise ValueError('No native occurrence pairs')
    result = []
    for names, rows in pairs.items():
        rows.sort(key=lambda row: row['driver_rad'])
        if len(rows) != len(coordinates) or any(abs(row['driver_rad']-q)>1e-12 for row,q in zip(rows,coordinates)):
            raise ValueError('Missing, repeated or unaligned native observations for '+str(names))
        if any(row.get('status') != 'NATIVE_BREP_OBSERVED' for row in rows):
            raise ValueError('Unfinished native observation')
        gaps = [row['minimum_distance_m'] for row in rows]
        if any(not math.isfinite(value) or value < 0 for value in gaps):
            raise ValueError('Invalid native minimum distance')
        speed = sum(motion['point_speed_bounds_m_per_driver_rad'][name] for name in names)
        if not math.isfinite(speed) or speed < 0:
            raise ValueError('Invalid continuous point-speed bound')
        loss = speed * interval / 2
        interval_bounds=[]
        for first,second,a,b in zip(gaps,gaps[1:],coordinates,coordinates[1:]):
            travel=speed*(b-a)
            if abs(second-first)>travel+1e-10:
                raise ValueError('Native observations contradict the declared global speed bound')
            # Both endpoint distance cones apply everywhere in this interval;
            # their intersection is stronger than using only the nearest one.
            interval_bounds.append((first+second-travel)/2)
        lower = min(interval_bounds)
        intersections = [row for row in rows if row['interference_count'] or row['interference_volumes_m3']]
        status = ('ACTUAL_BREP_INTERFERENCE' if intersections else
                  'NOMINAL_CONTINUOUS_SEPARATION_PROVED' if lower > 0 else
                  'CONTINUOUS_SEPARATION_NOT_PROVED')
        result.append({'occurrences': list(names), 'status': status,
            'samples': len(rows), 'minimum_observed_distance_m': min(gaps),
            'between_samples_lipschitz_loss_m': loss, 'continuous_lower_gap_m': lower,
            'nearest_sample_lower_gap_m': min(gaps)-loss,
            'interference_observations': intersections,
            'passes_unchanged_four_mm_self_margin': lower >= .004})
    return {'schema_version': 'cad-gripper-continuous-brep-envelope/1.0',
        'status': 'FAIL' if any(row['status']=='ACTUAL_BREP_INTERFERENCE' for row in result) else
                  'NOMINAL_GEOMETRY_SEPARATED' if all(row['continuous_lower_gap_m']>0 for row in result) else
                  'NOT_PROVED',
        'driver_interval_rad': [coordinates[0], coordinates[-1]],
        'pairs': result, 'collision_exclusions_authorized': False,
        'external_clearance_m_unchanged': .004,
        'scope': __doc__,
        'proof': 'Euclidean distance between moving rigid sets is Lipschitz with the sum L of their point-speed bounds. On each interval of width h, both endpoint cones apply; their minimum intersection is (gap_left+gap_right-L*h)/2. Every interval is covered.',
        'limitations': ['Ideal kinematic branch only; no inference of hardware stops or encoder zero.',
                        'Native closure, gear and geometric discretization error budgets must be considered before any runtime collision exclusion.',
                        'All four-millimetre criteria remain unchanged; sub-four-millimetre separation is not a margin PASS.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--motion', type=Path, required=True)
    parser.add_argument('--observation', type=Path, required=True)
    parser.add_argument('--maximum-driver', type=float)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    motion=json.loads(args.motion.read_text(encoding='utf-8-sig'))
    observed=json.loads(args.observation.read_text(encoding='utf-8-sig'))
    if observed.get('motion_file_sha256','').lower()!=digest(args.motion):
        raise ValueError('Native run did not observe these exact motion input bytes')
    report=summarize(motion, observed, maximum_driver=args.maximum_driver)
    report['source_files_sha256']={str(path):digest(path) for path in (args.motion,args.observation,Path(__file__))}
    with args.output.open('x',encoding='utf-8') as handle:
        json.dump(report,handle,indent=2,allow_nan=False);handle.write('\n')
    print(json.dumps({key:report[key] for key in ('status','driver_interval_rad','collision_exclusions_authorized')}))


if __name__=='__main__':
    main()
