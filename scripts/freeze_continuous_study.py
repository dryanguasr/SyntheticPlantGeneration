"""Freeze reviewed development configuration before reported full-route replay."""
import argparse
import datetime
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import write,sha


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();r=a.root.resolve()
    destination=r/'experiment_lock.json'
    if destination.exists():raise FileExistsError(destination)
    if json.loads((r/'execution_jobs/continuous_unit_checks.json').read_text())['state']!='completed':
        raise ValueError('Pipeline tests not passed')
    checks=['flight/technical/continuous_validation.json','flight/technical/segmentation_validation.json',
        'turn_test/technical/continuous_validation.json','turn_test/technical/orientation_validation.json','visual_review.json']
    for relative in checks:
        if not json.loads((r/relative).read_text())['passed']:raise ValueError(f'Unverified development gate: {relative}')
    run=json.loads((r/'run.json').read_text())
    if sha(run['model'])!=run['model_sha256']:raise ValueError('Frozen weights changed')
    paths=[*ROOT.joinpath('src/uchuva_gazebo').glob('*.py'),*[ROOT/'scripts'/n for n in
        ('cache_continuous_predictions.py','track_continuous_predictions.py','evaluate_continuous_study.py','diagnose_continuous_geometry.py',
         'run_low_flight.py','run_bouquet_flight.py','run_segmentation_flight.py')],r/'flight/mission.json',r/'flight/flight.sdf',r/'public_calibration.json']
    write(destination,dict(version='continuous-study-freeze/1.0',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        scope='Retrospective simulation, frozen before reported comparison; not independent generalization',
        sha256={str(path.relative_to(ROOT)):sha(path) for path in paths},model_sha256=run['model_sha256'],
        gates={name:sha(r/name) for name in checks},tile_size=960,overlap=.2,minimum_views=8,maximum_fit_views=30,
        minimum_view_spacing_seconds=.2,minimum_parallax_degrees=3,maximum_reprojection_pixels=3,maximum_sensitivity_m=.03))


if __name__=='__main__':main()
