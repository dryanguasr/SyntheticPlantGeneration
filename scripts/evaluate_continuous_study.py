"""Retrospective target-row evaluation; all simulator truth stays in this script."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import sys
import time
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.continuous_evaluation import mask_iou_matrix,one_to_one_masks,target_scope
from uchuva_gazebo.segmentation_evaluation import decode_panoptic_rgb,mask_matches,mask_confusion
from uchuva_lsystem.segmentation_cycles import write,sha


def main():
    p=argparse.ArgumentParser()
    for name in ('flight','truth','cache','estimates','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);begin=time.perf_counter()
    from ultralytics.utils.metrics import ap_per_class
    if not json.loads((a.truth.parent/'mapping_audit.json').read_text())['passed']:raise ValueError('Anatomical mapping not audited')
    truth=json.loads(a.truth.read_text());objects=truth['objects'];frames={f['stamp_ns']:f for f in truth['frames']}
    if any(o.get('role') not in ('target','background') for o in objects.values()):raise ValueError('Explicit roles required')
    visible={k for k,v in objects.items() if v['role']=='target' and v['ever_visible']}
    hidden={k for k,v in objects.items() if v['role']=='target' and not v['ever_visible']}
    pairs={p['stamp_ns']:p for p in json.loads((a.flight/'paired/pairs.json').read_text())['pairs']}
    prediction=json.loads((a.estimates/'map.json').read_text())
    matches_by_observation={};detected=set();evidence={};histories=defaultdict(list)
    tp=[];collapsed_tp=[];conf=[];classes=[];gtclasses=[];thresholds=np.arange(.5,1,.05)
    totals=Counter();confusion=np.zeros((4,4),int);ious_matched=[];centroid_errors=[]
    last_match={};recoveries=Counter();maximum_pixels=defaultdict(int);visible_frames=Counter()
    for frame in truth['frames']:
        for instance in frame['instances']:
            code=str(instance['code'])
            if objects[code]['role']=='target':maximum_pixels[code]=max(maximum_pixels[code],instance['pixels']);visible_frames[code]+=1
    with (a.output/'frame_diagnostics.jsonl').open('w',encoding='utf-8') as stream:
        for line in (a.estimates/'observations.jsonl').open(encoding='utf-8'):
            observation=json.loads(line);stamp=observation['stamp_ns'];instances=frames[stamp]['instances']
            cache=json.loads((a.cache/f'{stamp}.json').read_text());proposals=cache['proposals']
            with np.load(a.cache/f'{stamp}.npz') as packed:
                h,w=map(int,packed['shape']);masks=np.unpackbits(packed['packed_masks'],axis=1,count=h*w).reshape(-1,h,w).astype(bool)
            native=cv2.imread(str(a.flight/'paired'/pairs[stamp]['mask']))
            codes=decode_panoptic_rgb(native[:,:,::-1]);ious=mask_iou_matrix(masks,codes,instances)
            target,ignore=target_scope(ious,instances,objects)
            included=[i for i,v in enumerate(proposals) if v['cross_tile_suppressed_by'] is None and not ignore[i]]
            included.sort(key=lambda i:-proposals[i]['confidence'])
            predicted_cls=np.array([proposals[i]['class_id'] for i in included],int)
            predicted_conf=np.array([proposals[i]['confidence'] for i in included])
            true_cls=np.array([objects[str(instances[j]['code'])]['class_id'] for j in target],int)
            scoped_ious=ious[np.ix_(included,target)]
            frame_tp,_=mask_matches(scoped_ious,predicted_cls,true_cls,thresholds)
            frame_collapsed,_=mask_matches(scoped_ious,predicted_cls,true_cls,thresholds,collapse=True)
            tp.append(frame_tp);collapsed_tp.append(frame_collapsed);conf.append(predicted_conf);classes.append(predicted_cls);gtclasses.append(true_cls)
            operating=np.array([proposals[i]['accepted'] for i in included],bool)
            confusion+=mask_confusion(scoped_ious[operating],predicted_cls[operating],true_cls)
            totals.update(frames=1,target_observations=len(target),predictions=int(operating.sum()),tp=int(frame_tp[operating,0].sum()),collapsed_tp=int(frame_collapsed[operating,0].sum()))
            lookup={v['observation_id']:i for i,v in enumerate(proposals)}
            dets=observation['detections'];indices=[lookup[d['observation_id']] for d in dets]
            matches=one_to_one_masks(ious[indices]);matched_target=set();rows=[]
            for i,d in enumerate(dets):
                j=matches.get(i);code=str(instances[j]['code']) if j is not None else None
                matches_by_observation[d['observation_id']]=code
                role=objects[code]['role'] if code else None
                rows.append(dict(observation_id=d['observation_id'],track_id=d['track_id'],matched_code=code,role=role))
                if role=='target':
                    previous=last_match.get(code)
                    if previous and totals['frames']>previous[0]+1:
                        recoveries['interruptions_followed_by_detection']+=1
                        recoveries['same_track_recovered']+=d['track_id']==previous[1]
                    last_match[code]=(totals['frames'],d['track_id'])
                    detected.add(code);matched_target.add(j);histories[code].append((stamp,d['track_id']))
                    ious_matched.append(float(ious[indices[i],j]))
                    ys,xs=np.nonzero(codes==int(code));error=float(np.linalg.norm(np.array(d['center_px'])-[xs.mean(),ys.mean()]));centroid_errors.append(error)
            missed=[]
            for j in target:
                code=str(instances[j]['code']);best=int(np.argmax(ious[:,j])) if len(proposals) else None
                best_iou=float(ious[best,j]) if best is not None else 0
                reason='detected' if j in matched_target else 'cause_not_determined'
                if reason!='detected':
                    if best is None or best_iou==0:reason='no_overlapping_proposal_above_0.001'
                    elif best_iou<.5:reason='poor_mask_delineation'
                    elif proposals[best]['cross_tile_suppressed_by'] is not None:reason='cross_tile_suppression'
                    elif not proposals[best]['accepted']:reason='below_operating_confidence'
                    else:reason='one_to_one_competition_or_duplicate'
                    missed.append(dict(code=code,reason=reason,best_iou=best_iou))
                if code not in evidence or best_iou>evidence[code]['best_iou']:
                    evidence[code]=dict(stamp_ns=stamp,best_iou=best_iou,reason=reason,proposal_id=proposals[best]['observation_id'] if best is not None else None,
                        confidence=proposals[best]['confidence'] if best is not None else None,
                        evidence_status='observed_at_this_frame; not a proven global causal explanation')
            stream.write(json.dumps(dict(stamp_ns=stamp,matches=rows,missed_target=missed))+'\n')
            if totals['frames']%100==0:stream.flush();print('MASK_EVALUATION',totals['frames'],flush=True)
    def ap_summary(matches):
        all_tp=np.concatenate(matches);all_conf=np.concatenate(conf);all_cls=np.concatenate(classes);all_gt=np.concatenate(gtclasses)
        if not len(all_gt) or not len(all_conf):return dict(map50=0.,map50_95=0.)
        metrics=ap_per_class(all_tp,all_conf,all_cls,all_gt,plot=False)
        return dict(map50=float(metrics[5][:,0].mean()),map50_95=float(metrics[5].mean()),
            per_class=[dict(class_id=int(cls),map50=float(metrics[5][i,0]),map50_95=float(metrics[5][i].mean())) for i,cls in enumerate(metrics[6])])
    map_rows=[];claimed=set();localized=set();errors=[];intrusions=0
    confirmed=sorted((o for o in prediction['objects'] if o['state']=='confirmed'),key=lambda o:o.get('reprojection_max_px',float('inf')))
    for item in confirmed:
        support=item['observation_ids'];votes=Counter(matches_by_observation.get(o) for o in support);votes.pop(None,None)
        code,n=votes.most_common(1)[0] if votes else (None,0)
        purity=n/max(1,len(support));identity=bool(code and n>=3 and purity>=.8)
        role=objects[code]['role'] if code else None;intrusion=bool(identity and role=='background')
        intrusions+=intrusion;same_marker=bool(identity and item['marker_id']==objects[code]['canonical_marker_id'])
        delta=np.asarray(item['position_marker_m'])-objects[code]['position_marker_m'] if same_marker else None
        error=float(np.linalg.norm(delta)) if delta is not None else None
        duplicate=bool(identity and code in claimed)
        if identity:claimed.add(code)
        correct=bool(identity and role=='target' and same_marker and error<=.05 and not duplicate)
        if correct:localized.add(code)
        if same_marker and role=='target':errors.append(error)
        map_rows.append(dict(map_id=item['map_id'],code=code,role=role,identity_support=n,purity=purity,correct=correct,
            identity_supported=identity,background_intrusion=intrusion,duplicate=duplicate,correct_marker=same_marker,error_m=error,error_xyz_m=delta.tolist() if delta is not None else None))
    lost=[];track_reasons=defaultdict(list)
    for r in prediction['rejected']:track_reasons[r['track_id']].append(r.get('reason','cause_not_determined'))
    for code in sorted(visible-localized,key=int):
        tracks={tid for _,tid in histories[code]};related=[r for r in map_rows if r['code']==code]
        causes=[]
        if code not in detected:causes.append(evidence.get(code,{}).get('reason','no_evaluated_frame_support'))
        elif related:causes.append('incorrect_or_duplicate_3d_localization')
        else:
            reasons=[r for tid in tracks for r in track_reasons[tid]]
            causes+=sorted(set(reasons)) or ['tracking_marker_or_reconciliation_not_determined']
        lost.append(dict(code=code,anatomical_id=objects[code]['reproductive_id'],causes=causes,evidence=evidence.get(code),
            distinct_tracks=len(tracks),fragmentation_is_associated_not_proven_cause=len(tracks)>1))
    switches=sum(sum(a[1]!=b[1] for a,b in zip(items,items[1:])) for items in histories.values())
    metrics=dict(version='continuous-target-metrics/1.0',scope='retrospective Gazebo; not independent generalization or real crop transfer',
        target_visible_unique=len(visible),target_completely_hidden=len(hidden),localized_unique=len(localized),
        confirmed_predictions=len(confirmed),precision_3d=len(localized)/max(1,len(confirmed)),recall_3d=len(localized)/max(1,len(visible)),
        association_precision=sum(r['identity_supported'] and r['role']=='target' and r['correct_marker'] and not r['duplicate'] for r in map_rows)/max(1,len(confirmed)),
        background_intrusions=intrusions,duplicates=sum(r['duplicate'] for r in map_rows),
        wrong_marker=sum(r['role']=='target' and r['identity_support']>=3 and not r['correct_marker'] for r in map_rows),
        error_median_m=float(np.median(errors)) if errors else None,error_p95_m=float(np.percentile(errors,95)) if errors else None,
        mask_ap=ap_summary(tp),collapsed_mask_ap=ap_summary(collapsed_tp),totals=dict(totals),
        precision_2d=totals['tp']/max(1,totals['predictions']),recall_2d=totals['tp']/max(1,totals['target_observations']),
        mean_matched_mask_iou=float(np.mean(ious_matched)) if ious_matched else None,
        centroid_error_median_px=float(np.median(centroid_errors)) if centroid_errors else None,
        centroid_error_p95_px=float(np.percentile(centroid_errors,95)) if centroid_errors else None,
        confusion=confusion.tolist(),identity_switches=switches,fragmented_target_objects=sum(len({tid for _,tid in items})>1 for items in histories.values()),
        interruption_recovery=dict(recoveries),
        size_strata=[dict(equivalent_visible_side_px=label,visible=sum(low<=maximum_pixels[c]**.5<high for c in visible),
            localized=sum(low<=maximum_pixels[c]**.5<high for c in localized)) for low,high,label in
            [(0,16,'<16'),(16,32,'16-31'),(32,64,'32-63'),(64,float('inf'),'>=64')]],
        view_strata=[dict(visible_capture_count=label,visible=sum(low<=visible_frames[c]<high for c in visible),
            localized=sum(low<=visible_frames[c]<high for c in localized)) for low,high,label in [(1,3,'1-2'),(3,8,'3-7'),(8,float('inf'),'>=8')]],
        seconds=time.perf_counter()-begin,truth_sha256=sha(a.truth),
        identity_rule='one-to-one mask IoU>=0.5, >=3 supports, >=80% of all geometric support (unmatched counts against purity)',
        scope_rule='2D: ignore matched context proposals only in evaluator; all unmatched predictions retained. 3D: every confirmed target-map object retained including background intrusions.')
    write(a.output/'metrics.json',metrics);write(a.output/'map_diagnostics.json',map_rows);write(a.output/'missed_target_catalog.json',lost)


if __name__=='__main__':main()
