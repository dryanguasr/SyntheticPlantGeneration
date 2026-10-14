"""Replay offline estimator with access to simulator/evaluator paths denied."""
import argparse
import json
from pathlib import Path
import runpy
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import write


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();r=a.root.resolve()
    source=r/'estimates/offline_every_frame';destination=r/'verification/isolated_replay';attempts=[]
    overlap_device=json.loads((source/'provenance.json').read_text()).get('mask_overlap_device','cpu')
    provenance=json.loads((source/'provenance.json').read_text())
    names=['field_full','field_lod','field_batched','field_binary','flight','flight_prepared','turn_test',
        'evaluator','evaluation','privileged','background_morphologies','background_audits','target_source.json','field_input.json']
    blocked=[str(r/name).replace('\\','/').lower() for name in names]
    def guard(event,arguments):
        if event!='open' or not isinstance(arguments[0],(str,bytes,Path)):return
        value=str(Path(arguments[0]).resolve()).replace('\\','/').lower()
        if any(value==prefix or value.startswith(prefix+'/') for prefix in blocked):
            attempts.append(value);raise PermissionError('Simulator/evaluator input forbidden in estimator replay')
    sys.addaudithook(guard)
    sys.argv=['track_continuous_predictions.py','--root',str(r),'--public',str(r/'public'),'--cache',str(r/'predictions'),
        '--output',str(destination),'--protocol','offline_every_frame','--mask-overlap-device',overlap_device,
        '--flow-device',provenance.get('flow_device','cpu')]
    prefix=r/'recovery/flow_cuda_prefix.jsonl'
    if provenance.get('resumed_frames'):
        from uchuva_lsystem.segmentation_cycles import sha
        if sha(prefix)!=provenance['resume_observations_sha256']:raise ValueError('Recovery prefix changed')
        sys.argv+=['--resume-observations',str(prefix)]
        if provenance.get('resume_flow_switch_frame') is not None:
            sys.argv+=['--resume-flow-switch-frame',str(provenance['resume_flow_switch_frame'])]
    runpy.run_path(str(ROOT/'scripts/track_continuous_predictions.py'),run_name='__main__')
    expected=json.loads((source/'map.json').read_text());actual=json.loads((destination/'map.json').read_text())
    if actual!=expected or attempts:raise AssertionError('Isolated replay changed or accessed private information')
    write(r/'verification/isolation.json',dict(passed=True,private_attempts=attempts,map_identical=True,
        scope='Python audit hook integration replay, not an operating-system security boundary or training-data audit'))


if __name__=='__main__':main()
