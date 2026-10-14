"""Replay frozen RGB estimates while denying access to private simulator files."""
import argparse
import json
import runpy
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import write


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args();root=args.root.resolve()
    source=root/'reserved_estimates/winner_raw';out=root/'verification/isolated_replay'
    run=json.loads((root/'run.json').read_text());attempts=[]
    blocked=[str(root/p).replace('\\','/').lower() for p in ('evaluator','reserved_field_full','reserved_field_lod','reserved_flight_close','reserved_flight_close_batched','reserved_morphologies','approved_morphologies')]
    def guard(event,arguments):
        if event!='open' or not isinstance(arguments[0],(str,bytes,Path)):return
        value=str(Path(arguments[0]).resolve()).replace('\\','/').lower()
        if any(value==prefix or value.startswith(prefix+'/') for prefix in blocked):
            attempts.append(value);raise PermissionError('Simulator truth inaccessible during isolation replay')
    sys.addaudithook(guard)
    sys.argv=['estimate_marker_localization.py','--root',str(root),'--public',str(root/'public/reserved'),
        '--model',run['model'],'--output',str(out),'--variant','persistent','--mode','all_tiles',
        '--tile-size','960','--refine-corners','--detections-cache',str(source)]
    runpy.run_path(str(ROOT/'scripts/estimate_marker_localization.py'),run_name='__main__')
    expected=json.loads((source/'map.json').read_text());actual=json.loads((out/'map.json').read_text())
    if expected!=actual or attempts:raise AssertionError('Replay differs or attempted private input access')
    write(root/'verification/isolation.json',dict(passed=True,private_file_attempts=attempts,
        map_identical=True,scope='Frozen estimator replay with cached RGB detections; private simulator directories denied by Python audit hook. This is an integration check, not an OS security sandbox or detector training-data audit.'))
    print('ISOLATED_REPLAY_IDENTICAL',flush=True)


if __name__=='__main__':main()
