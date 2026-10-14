"""Check native paired observations before any segmentation flight evaluation."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import VERSION,write,sha
from uchuva_gazebo.segmentation_evaluation import decode_panoptic_rgb,whole_plant_in_frame


def main():
    parser=argparse.ArgumentParser();parser.add_argument('flight',type=Path)
    args=parser.parse_args();output=args.flight/'segmentation_validation.json'
    if output.exists():raise FileExistsError(output)
    capture=json.loads((args.flight/'paired/pairs.json').read_text())
    flight=json.loads((args.flight/'result.json').read_text())
    preflight=json.loads((args.flight.parent/'preflight.json').read_text())
    mission=json.loads((args.flight.parent/'mission.json').read_text())
    telemetry=json.loads((args.flight/'telemetry.json').read_text())['samples']
    times=np.array([sample['t'] for sample in telemetry])
    targets={point['phase']:point.get('target_plant_id') for point in mission['waypoints']}
    inventory=json.loads((args.flight.parent/'inventory.json').read_text())
    label_counts=Counter(item['semantic_label'] for item in inventory['calyces'])
    native_inventory_valid=True
    framing_available='plant_mesh_bounds_m' in preflight
    detector=cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100))
    rows=[];stamps=[];labels=set()
    for pair in capture['pairs']:
        stamp=pair['stamp_ns'];stamps.append(stamp)
        if Path(pair['rgb']).stem!=str(stamp) or Path(pair['mask']).stem!=str(stamp):raise ValueError('Timestamp mismatch')
        rgb=cv2.imread(str(args.flight/'paired'/pair['rgb']))
        native=cv2.imread(str(args.flight/'paired'/pair['mask']))
        if rgb is None or native is None or rgb.shape!=native.shape:raise ValueError('Invalid paired pixels')
        codes=decode_panoptic_rgb(native[:,:,::-1]);identities=np.unique(codes);identities=identities[identities>0]
        for identity in identities:
            label=int(identity)//65536;instance=int(identity)%65536
            native_inventory_valid &= label in label_counts and 1<=instance<=label_counts[label]
        labels.update(int(v)//65536 for v in identities)
        _,ids,_=detector.detectMarkers(rgb)
        decoded=[] if ids is None else ids.ravel().tolist()
        row={'stamp_ns':stamp,'visible_native_instances':len(identities),'aruco_ids':decoded}
        if framing_available and len(times):
            pose=telemetry[int(np.abs(times-stamp/1e9).argmin())];target=targets.get(pose['phase'])
            markers=[m for m in preflight['markers'] if m['plant_id']==target]
            target_index=int(target.split('_')[-1]) if target else -1
            seen={int((v//65536-1)//3) for v in identities}
            row.update(target_plant=target,phase=pose['phase'],
                target_marker_decoded=bool(set(decoded)&{m['id'] for m in markers}),
                target_native_mask_visible=target_index in seen,
                whole_target_with_5_percent_margin=bool(target and whole_plant_in_frame(
                    preflight['plant_mesh_bounds_m'][target],markers,pose['position'],pose['quaternion_xyzw'],
                    hull_points=preflight.get('plant_mesh_hulls_m',{}).get(target))))
        rows.append(row)
    duration=(max(stamps)-min(stamps))/1e9 if stamps else 0
    checks={'flight_completed':flight['completed'],'writer_no_error':capture['error'] is None,
        'native_labels_and_instance_counts_match_inventory':bool(native_inventory_valid),
        'unique_exact_timestamp_pairs':len(stamps)==len(set(stamps)),'at_least_40_pairs':len(stamps)>=40,
        'at_least_8_seconds_of_rgb_and_masks':duration>=8,
        'native_targets_visible':any(r['visible_native_instances'] for r in rows),
        'aruco_decoded_from_rgb':any(r['aruco_ids'] for r in rows),
        'executed_clearance_ge_15cm':(flight['minimum_executed_margin_m'] or 0)>=.15}
    if framing_available:
        usable=[r for r in rows if r.get('target_marker_decoded') and r.get('target_native_mask_visible') and r.get('whole_target_with_5_percent_margin')]
        checks['at_least_30_full_target_rgb_marker_mask_pairs']=len(usable)>=30
    write(output,{'script_version':VERSION,'seed':230926,'parameter_preset':'native_segmentation_technical_capture',
        'passed':all(checks.values()),'checks':checks,'paired_duration_seconds':duration,
        'frames':rows,'semantic_labels_seen':sorted(labels),'excluded_observations':len(capture['excluded']),
        'source_pairs_sha256':sha(args.flight/'paired/pairs.json'),
        'scope':'technical synchronization and decoding only, not a completed experimental cycle'})
    print(json.dumps({'passed':all(checks.values()),'checks':checks,'pairs':len(rows),'seconds':duration}))
    if not all(checks.values()):raise SystemExit(1)


if __name__=='__main__':main()
