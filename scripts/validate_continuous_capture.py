"""Fail closed on reduced capture, unmatched exposures or invalid study roles."""
import argparse
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import write


def main():
    p=argparse.ArgumentParser();p.add_argument('flight',type=Path);a=p.parse_args()
    package=a.flight.parent
    mission=json.loads((package/'mission.json').read_text())
    pairs=json.loads((a.flight/'paired/pairs.json').read_text())
    result=json.loads((a.flight/'result.json').read_text())
    inventory=json.loads((package/'inventory.json').read_text())
    preflight=json.loads((package/'preflight.json').read_text())
    stamps=np.array([p['stamp_ns'] for p in pairs['pairs']],dtype=np.int64)
    if len(stamps)<2:raise ValueError('Too few captured pairs')
    deltas=np.diff(stamps)/1e9
    missing_intervals=[dict(after_stamp_ns=int(stamps[i]),gap_seconds=float(d),missing_expected=max(0,round(d*30)-1))
                       for i,d in enumerate(deltas) if d>1.5/30]
    actual_rgb={p.stem for p in (a.flight/'paired/rgb').glob('*.png')}
    actual_mask={p.stem for p in (a.flight/'paired/mask').glob('*.png')}
    selected=set(map(str,stamps))
    tree=ET.parse(package/'flight.sdf')
    rates=[float(s.findtext('update_rate','0')) for s in tree.findall('.//sensor') if s.get('name') in ('onboard','instances')]
    target=set(mission['target_plant_ids']);all_ids={o['plant_id'] for o in inventory['calyces']}
    role_valid=all(o['role']==('target' if o['plant_id'] in target else 'background') for o in inventory['calyces'])
    marker_ids=[m['id'] for m in preflight['markers']]
    checks=dict(flight_completed=result['completed'],all_exact_pairs=pairs.get('selection')=='all_exact_pairs',
        no_hidden_pair_filter=selected==actual_rgb&actual_mask,no_unpaired_exposures=not pairs['excluded'],
        no_writer_error=pairs['error'] is None,unique_ordered_stamps=bool(np.all(deltas>0)),
        both_sensors_30hz=rates==[30.,30.],measured_rate_30hz=abs(float(np.median(deltas))-1/30)<.002,
        no_missing_30hz_intervals=not missing_intervals,at_least_8_seconds=(stamps[-1]-stamps[0])/1e9>=8,
        six_targets_twelve_background=len(target)==6 and len(all_ids-target)==12 and role_valid,
        unique_marker_codes=len(marker_ids)==36 and len(set(marker_ids))==36,
        clearance_ge_15cm=(result.get('minimum_executed_margin_m') or 0)>=.15,
        resolution_and_masks_valid=True)
    for pair in pairs['pairs']:
        rgb=cv2.imread(str(a.flight/'paired'/pair['rgb']));mask=cv2.imread(str(a.flight/'paired'/pair['mask']))
        if rgb is None or mask is None or rgb.shape!=(720,1280,3) or mask.shape!=rgb.shape:
            checks['resolution_and_masks_valid']=False;break
    # Comparisons involving NumPy timestamps produce numpy.bool_, which JSON
    # cannot serialize. Preserve every check, converting only its scalar type.
    checks={name:bool(value) for name,value in checks.items()}
    report=dict(version='continuous-capture-validation/1.0',passed=all(checks.values()),checks=checks,
        captured_pairs=len(stamps),median_interval_seconds=float(np.median(deltas)),missing_intervals=missing_intervals,
        scope='Capture integrity only. Anatomy-code mapping, framing and actual turn orientation require separate evaluation.')
    write(a.flight/'continuous_validation.json',report);print(json.dumps(report),flush=True)
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
