"""Join frozen RGB-only estimates to independently audited evaluator truth."""
import argparse,collections,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import write,sha
from uchuva_gazebo.multiview import match_detections


def main():
    p=argparse.ArgumentParser();p.add_argument('--truth',type=Path,required=True);p.add_argument('--estimates',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    assert json.loads((a.truth.parent/'mapping_audit.json').read_text())['passed']
    truth=json.loads(a.truth.read_text());objects=truth['objects'];frames={f['stamp_ns']:f for f in truth['frames']}
    observations={};detected=set();sizes=collections.defaultdict(list)
    for frame in truth['frames']:
        for instance in frame['instances']:sizes[str(instance['code'])].append(instance['pixels'])
    for line in (a.estimates/'observations.jsonl').read_text().splitlines():
        frame=json.loads(line);gt=frames[frame['stamp_ns']]['instances'];dets=frame['detections']
        matches,_=match_detections([d['box_xyxy_px'] for d in dets],[g['bbox'] for g in gt],threshold=.5)
        for i,det in enumerate(dets):
            code=str(gt[matches[i]]['code']) if i in matches else None
            observations[det['observation_id']]=code
            if code:detected.add(code)
    prediction=json.loads((a.estimates/'map.json').read_text());rows=[];claimed=set();errors=[];localized=set()
    ordered=sorted((p for p in prediction['objects'] if p['state']=='confirmed'),key=lambda p:p.get('reprojection_max_px',float('inf')))
    for point in ordered:
        votes=collections.Counter(observations.get(o) for o in point['observation_ids']);votes.pop(None,None)
        code,n=votes.most_common(1)[0] if votes else (None,0)
        purity=n/max(1,sum(votes.values()));same_marker=bool(code and point['marker_id']==objects[code]['canonical_marker_id'])
        error=float(np.linalg.norm(np.asarray(point['position_marker_m'])-objects[code]['position_marker_m'])) if same_marker else None
        duplicate=bool(code and code in claimed)
        identity_supported=bool(code and purity>=.8 and n>=3)
        correct=bool(identity_supported and same_marker and error<=.05 and not duplicate)
        if identity_supported and same_marker:
            errors.append(error)
            if correct:claimed.add(code);localized.add(code)
        rows.append(dict(map_id=point['map_id'],anatomical_id=objects[code]['reproductive_id'] if code else None,code=code,identity_support=n,purity=purity,correct_marker=same_marker,error_m=error,duplicate=duplicate,correct=correct))
    visible={code for code,o in objects.items() if o['ever_visible']};hidden=set(objects)-visible
    by_size=[]
    for low,high,name in [(0,16,'<16'),(16,32,'16-31'),(32,64,'32-63'),(64,float('inf'),'>=64')]:
        subset={code for code in visible if low<=max(sizes[code])**.5<high}
        by_size.append(dict(maximum_visible_equivalent_side_px=name,visible=len(subset),localized=len(subset&localized)))
    precision=len(localized)/len(rows) if rows else 0.;recall=len(localized)/max(1,len(visible))
    write(a.output/'metrics.json',dict(version='marker-localization-metrics/1.0',visible_unique=len(visible),completely_hidden=len(hidden),detected_unique=len(detected),localized_unique=len(localized),predicted_confirmed=len(rows),precision=precision,recall=recall,success=recall>.5 and precision>=.9,duplicates=sum(r['duplicate'] for r in rows),wrong_marker=sum(r['code'] is not None and not r['correct_marker'] for r in rows),error_median_m=float(np.median(errors)) if errors else None,error_p95_m=float(np.percentile(errors,95)) if errors else None,error_tolerance_m=.05,identity_match_policy='one-to-one per-frame IoU >=0.5, >=3 supporting matches and >=80% identity purity; unique claim at <=5cm and correct marker',size_strata=by_size,rows=rows,rejection_reasons=dict(collections.Counter(r['reason'] for r in prediction['rejected'])),estimator_sha256=sha(a.estimates/'provenance.json'),truth_sha256=sha(a.truth),scope=('Gazebo reserved evaluation' if a.truth.parent.name=='reserved' else 'Gazebo development')+'; all visible sizes and transit frames retained'))
    print('LOCALIZATION_METRICS',len(localized),len(visible),precision,recall,flush=True)


if __name__=='__main__':main()
