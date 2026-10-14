"""Freeze usable raw development observations once; never select by model output."""
import argparse
import json
from pathlib import Path
import shutil
import os
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import write,sha


def main():
    p=argparse.ArgumentParser();p.add_argument('--flight',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    validation=json.loads((a.flight/'segmentation_validation.json').read_text())
    if not validation['passed']:raise ValueError('Unvalidated flight')
    usable={f['stamp_ns'] for f in validation['frames'] if f.get('target_marker_decoded')
        and f.get('target_native_mask_visible') and f.get('whole_target_with_5_percent_margin')}
    if len(usable)<30:raise ValueError('Insufficient whole-bush observations with decoded target marker')
    capture=json.loads((a.flight/'paired/pairs.json').read_text())
    selected=[row for row in capture['pairs'] if row['stamp_ns'] in usable]
    a.output.mkdir(parents=True,exist_ok=False);checksums={}
    for name in ('mission.json','preflight.json','inventory.json','provenance.json'):
        shutil.copy2(a.flight.parent/name,a.output/name)
    flight=a.output/'reference';(flight/'paired').mkdir(parents=True)
    for name in ('result.json','telemetry.json','segmentation_validation.json'):
        shutil.copy2(a.flight/name,flight/name)
    for row in selected:
        for kind in ('rgb','mask'):
            source=a.flight/'paired'/row[kind];target=flight/'paired'/row[kind]
            target.parent.mkdir(parents=True,exist_ok=True)
            try:os.link(source,target)
            except OSError:shutil.copy2(source,target)
            checksums[row[kind]]=sha(target)
    write(flight/'paired/pairs.json',{'pairs':selected,'excluded':[],'error':None})
    write(flight/'reference_lock.json',{'script_version':'fixed-development-reference/1.0','seed':420200,
        'parameter_preset':'full_bush_rgb_decoded_marker','selection':'image usability only, before main-model inference',
        'source_flight':str(a.flight.resolve()),'source_pairs_sha256':sha(a.flight/'paired/pairs.json'),
        'pairs_sha256':sha(flight/'paired/pairs.json'),'sha256':checksums,'pairs':len(selected)})
    print(json.dumps({'fixed_pairs':len(selected),'flight':str(flight)}))


if __name__=='__main__':main()
