"""Copy only RGB, timestamps and predeclared public calibration for estimation."""
import argparse
import json
import os
import shutil
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--flight',type=Path,required=True)
    parser.add_argument('--calibration',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=json.loads((args.flight/'result.json').read_text())
    if not result['completed']:
        raise ValueError('Incomplete flight cannot become final capture bundle')
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'rgb').mkdir()
    frames=[]
    for pair in json.loads((args.flight/'paired/pairs.json').read_text())['pairs']:
        relative=Path(pair['rgb'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsafe RGB path')
        source=args.flight/'paired'/relative
        os.link(source,args.output/'rgb'/source.name)
        frames.append(dict(stamp_ns=pair['stamp_ns'],filename=source.name))
    if not frames or len({f['stamp_ns'] for f in frames})!=len(frames):
        raise ValueError('Missing or duplicate timestamps')
    (args.output/'frames.json').write_text(json.dumps(frames,indent=2))
    shutil.copy2(args.calibration,args.output/'calibration.json')
    print('PUBLIC_RGB_FRAMES',len(frames),flush=True)


if __name__=='__main__':main()
