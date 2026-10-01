"""Freeze the validated pilot before evaluated acquisition, without tuning detector thresholds."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path);args=p.parse_args()
    package=args.package.resolve()
    validation=json.loads((package/'technical/validation.json').read_text())
    if not validation['passed']:raise RuntimeError('Technical gate failed')
    files=[package/'mission.json',package/'flight.sdf',package/'preflight.json',
           ROOT/'scripts/run_low_flight.py',ROOT/'scripts/estimate_low_flight.py',
           ROOT/'scripts/run_neo_flight.py',
           ROOT/'src/uchuva_gazebo/multiview.py',ROOT/'desktop/uchuva_aruco/vision.py',
           ROOT/'src/uchuva_gazebo/low_flight_control.py',
           ROOT/'scripts/evaluate_low_flight.py',ROOT/'src/uchuva_gazebo/evaluation.py',
           ROOT/'scripts/validate_low_capture.py',
           ROOT/'mobile/android/app/src/main/assets/detector.onnx']
    files.extend(sorted(p for p in (package/'meshes').iterdir() if p.is_file()))
    files.extend(sorted(p for p in (package/'neo_visual').rglob('*') if p.is_file()))
    files.append(ROOT/'scripts/prepare_low_flight.py')
    for uri in ET.parse(package/'flight.sdf').findall('.//mesh/uri'):
        mesh=(package/uri.text).resolve();files.append(mesh)
        if mesh.suffix.lower()=='.obj':
            with mesh.open() as stream:
                for line in stream:
                    if line.startswith('mtllib '):files.append(mesh.parent/line.strip()[7:]);break
    files=sorted(set(path.resolve() for path in files))
    config=json.loads((package/'mission.json').read_text())
    payload={k:config[k] for k in ('script_version','seed','parameter_preset')}
    payload.update({'sha256':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        'ippe_max_reprojection_px':3,'ippe_ambiguity_gap_px':.25,'flow_min_points':3,
        'flight_horizontal_command_max_m_s':.16,'flight_vertical_command_max_m_s':.08,
        'startup':'dynamic motor settling at the exterior endpoint before first pass',
        'technical_validation':validation,'status':'frozen_before_evaluated_acquisition'})
    with (package/'experiment_lock.json').open('x') as f:json.dump(payload,f,indent=2)
    print(package/'experiment_lock.json')


if __name__=='__main__':main()
