"""Private evaluator of persisted public estimates. Never used by the estimator.

Uses unchanged global native-mask matches, not nearest 3D truth. The geometric
reference is the evaluated calyx AABB center, not the internal fruit center.
"""
import argparse
from collections import Counter, defaultdict
import datetime
import importlib.util
import json
from pathlib import Path
import os
import numpy as np
import psutil
from localize_public_v1 import read, write, sha, require


def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def stats(values):
    if not values:return dict(n=0,mean=None,median=None,rmse=None,p95=None,maximum=None)
    a=np.asarray(values,float)
    return dict(n=len(a),mean=float(a.mean()),median=float(np.median(a)),rmse=float(np.sqrt(np.mean(a*a))),
                p95=float(np.percentile(a,95)),maximum=float(a.max()))


def native_matches(native,truth,predictions,detections):
    """Same fixed global confidence-ordered rule, retaining assignment provenance."""
    remaining=set(range(len(truth)));matches={};cm=np.zeros((4,4),np.int64)
    for index,p in sorted(enumerate(predictions),key=lambda pair:-pair[1]['label']['confidence']):
        x1,y1,x2,y2=p['bbox']
        counts=np.bincount(native[y1:y2,x1:x2][p['mask']].astype(np.int64),minlength=max([t['mask_id'] for t in truth],default=0)+1)
        candidates=[(int(counts[t['mask_id']])/max(1,p['area']+t['pixels']-int(counts[t['mask_id']])),k)
                    for k,t in enumerate(truth) if k in remaining]
        if candidates and max(candidates)[0]>=.5:
            overlap,k=max(candidates);remaining.remove(k);t=truth[k]
            matches[index]=dict(instance_id=t['instance_id'],mask_iou=overlap,
                true_class_id=t['class_id'],predicted_class_id=p['label']['class_id'],track_id=detections[index]['track_id'],
                eligible=t['pixels']>=100 and min(t['bbox'][2]-t['bbox'][0],t['bbox'][3]-t['bbox'][1])>=8)
            cm[t['class_id'],p['label']['class_id']]+=1
        else:cm[3,p['label']['class_id']]+=1
    for k in remaining:cm[truth[k]['class_id'],3]+=1
    return matches,cm


def pose_error(pose,camera,board):
    world=np.asarray(camera['matrix_world']);Rwc=world[:3,:3]@np.diag([1.,-1.,-1.])
    scale=board['meters_per_bu'];Rwm=np.asarray(board['R_world_from_marker'],float)
    truth_center=Rwm.T@(world[:3,3]-board['center_world_bu'])*scale
    truth_R=Rwm.T@Rwc
    Rc=np.asarray(pose['R']);pred_center=-Rc.T@np.asarray(pose['t']);pred_R=Rc.T
    angle=float(np.degrees(np.arccos(np.clip((np.trace(pred_R@truth_R.T)-1)/2,-1,1))))
    return dict(position_error_m=float(np.linalg.norm(pred_center-truth_center)),orientation_error_degrees=angle,
        estimated_camera_center_marker_m=pred_center.tolist(),true_camera_center_marker_m=truth_center.tolist())


def evaluate(root,route):
    stage=root/'metric_localization_v1';protocol=read(stage/'protocol.json')
    freeze=read(stage/'private_evaluation_readiness_v1.json')
    require(freeze['passed'] and sha(Path(__file__))==freeze['evaluator_sha256'] and
            sha(stage/'protocol.json')==freeze['protocol_sha256'],'Evaluation changed after predeclaration')
    output=stage/'private_evaluation'/route
    require(not output.exists(),'Preserve previous partial or complete private evaluation')
    output.mkdir(parents=True)
    inputs={}
    def bound(path):
        inputs[str(path.resolve())]=sha(path)
        return read(path)
    flight=root/'flights'/route;est=stage/'public_estimates'/route
    summary=bound(est/'summary.json');require(summary['complete'],'Public estimate incomplete')
    for name,digest in summary['output_sha256'].items():require(sha(est/name)==digest,'Estimate hash mismatch')
    require(summary['binding']['protocol_sha256']==sha(stage/'protocol.json'),'Localization protocol differs')
    full_protocol=bound(root/'protocol.json');scene=next(x for x in full_protocol['scenes'] if x['name']==route)
    count=scene['views'];observations=bound(flight/'tracking_new/observations.json')
    require(sha(flight/'tracking_new/observations.json')==summary['binding']['tracking_sha256'],'Tracking changed')
    poses=[json.loads(line) for line in (est/'poses.jsonl').read_text().splitlines()]
    require(len(poses)==len(observations)==count,'Frame count mismatch')
    board=bound(root/'geometry_private/board_private.json');bounds=bound(root/'geometry_private/evaluated_bounds_private.json')
    mapping=bound(root/'geometry_private/class_mapping_private.json')
    old=bound(flight/'evaluation_private_v1/summary.json')
    require(board['side_bu']*board['meters_per_bu']==.20,'Wrong physical marker side')
    centers={};Rwm=np.asarray(board['R_world_from_marker']);origin=np.asarray(board['center_world_bu'])
    for identity,item in mapping.items():
        prefix='uchuva_'+item['unit_id']+'_calyx'
        found=[b for b in bounds if b['plant_id']==item['plant_id'] and b['semantic']=='calyx' and
               (b['name']==prefix or b['name'].startswith(prefix+'.'))]
        require(len(found)==1,'3D reference ambiguous or absent: '+identity)
        center=(np.asarray(found[0]['min'])+np.asarray(found[0]['max']))/2
        centers[identity]=Rwm.T@(center-origin)*board['meters_per_bu']
    smoke_path=root.parent/'evaluate_smoke_private_v1.py'
    helper_path=root.parents[1]/'multiscale_dataset_20261020/evaluate_multiscale_v1.py'
    require(sha(smoke_path)==freeze['smoke_helper_sha256'] and sha(helper_path)==freeze['prediction_helper_sha256'],'Native helper changed')
    smoke=module(smoke_path,'metric_smoke_helper');helper=module(helper_path,'metric_prediction_helper')
    by_observation={};visible={scope:set() for scope in protocol['evaluation']['scopes']};inspection_visible={k:set() for k in visible}
    pose_rows=[];minimum=psutil.virtual_memory().available/2**30
    for i,(p,o,sample) in enumerate(zip(poses,observations,scene['trajectory'])):
        free=psutil.virtual_memory().available/2**30;minimum=min(minimum,free);require(free>=3,'RAM early stop')
        write(output/'progress.json',dict(pid=os.getpid(),stage='private_matching_and_pose_error',completed=i,total=count,minimum_free_gib=minimum))
        camera=bound(root/'captures'/route/f'view_{i:03d}/camera_private.json')
        require(p['frame']==o['frame']==i and p['stamp_ns']==o['stamp_ns']==sample['stamp_ns'],'Timeline mismatch')
        for variant in ['visual_only','fused']:
            if p[variant] is not None:
                pose_rows.append(dict(frame=i,stamp_ns=p['stamp_ns'],phase=sample['phase'],side=sample['side'],variant=variant,
                                      **pose_error(p[variant],camera,board)))
        folder=root/'captures'/route/f'view_{i:03d}'
        inputs[str(folder/'annotations_private.json')]=sha(folder/'annotations_private.json')
        inputs[str(folder/'mask_calyx_crisp_v2.png')]=sha(folder/'mask_calyx_crisp_v2.png')
        native,truth=smoke.original_truth(folder,mapping)
        stem=f'frame_{i:03d}';record=bound(flight/'predictions_new/predictions'/(stem+'.json'))
        require(sha(flight/'predictions_new/predictions'/(stem+'.json'))==o['prediction_record_sha256'],'Prediction/tracking binding differs')
        predictions=helper.load_predictions(flight/'predictions_new/predictions',stem,record['binding'])
        require(len(predictions)==len(o['detections']),'Prediction order/count mismatch')
        for a,b in zip(predictions,o['detections']):
            require(a['bbox']==b['box_xyxy_px'] and a['label']['class_id']==b['class_id'],'Prediction order differs')
        matches,cm=native_matches(native,truth,predictions,o['detections'])
        require(np.array_equal(cm,np.asarray(old['per_frame'][i]['metrics']['all']['confusion'])),'Assignments do not reproduce completed native confusion')
        for j,m in matches.items():
            by_observation[f'{i}:{j}']=dict(m,frame=i,phase=sample['phase'],plant_id=mapping[m['instance_id']]['plant_id'],
                                           is_current_target=mapping[m['instance_id']]['plant_id']==sample['target_plant'])
        for t in truth:
            eligible=t['pixels']>=100 and min(t['bbox'][2]-t['bbox'][0],t['bbox'][3]-t['bbox'][1])>=8
            target=mapping[t['instance_id']]['plant_id']==sample['target_plant']
            for scope in visible:
                if scope.startswith('target') and not target:continue
                if scope.endswith('eligible') and not eligible:continue
                visible[scope].add(t['instance_id'])
                if sample['phase'].startswith('inspection'):inspection_visible[scope].add(t['instance_id'])
    write(output/'pose_errors.json',pose_rows)
    write(output/'native_assignment_provenance.json',by_observation)
    pose_metrics={}
    for variant in ['visual_only','fused']:
        rows=[p for p in pose_rows if p['variant']==variant]
        pose_metrics[variant]=dict(frames=len(rows),total_frames=count,coverage=len(rows)/count,
            position_error_m=stats([p['position_error_m'] for p in rows]),
            orientation_error_degrees=stats([p['orientation_error_degrees'] for p in rows]),by_phase={})
        for phase in sorted({s['phase'] for s in scene['trajectory']}):
            subset=[p for p in rows if p['phase']==phase];n=sum(s['phase']==phase for s in scene['trajectory'])
            pose_metrics[variant]['by_phase'][phase]=dict(frames=len(subset),total_frames=n,coverage=len(subset)/n,
                position_error_m=stats([p['position_error_m'] for p in subset]),
                orientation_error_degrees=stats([p['orientation_error_degrees'] for p in subset]))
    geometric={}
    for variant in ['visual_only','fused']:
        candidates=[json.loads(line) for line in (est/(variant+'_triangulation.jsonl')).read_text().splitlines()]
        strict=[];all_inlier_distances=[];rejected=Counter();details=[]
        for row in candidates:
            result=row['result']
            if result['status']!='estimated':continue
            position=np.asarray(result['position_marker_m'])
            require(len(result['inlier_observation_ids'])>=3,'Geometric support insufficient')
            matched=[by_observation[o] for o in result['inlier_observation_ids'] if o in by_observation]
            identities=Counter(m['instance_id'] for m in matched)
            distances=[float(np.linalg.norm(position-centers[m['instance_id']])) for m in matched]
            all_inlier_distances.extend(distances)
            reason=None
            if len(matched)<len(result['inlier_observation_ids']):reason='unmatched_inlier_observations'
            elif len(identities)!=1:reason='mixed_true_identities'
            detail=dict(track_id=row['track_id'],inliers=len(result['inlier_observation_ids']),matched_inliers=len(matched),
                true_identity_counts=dict(identities),attribution_rejection=reason,all_matched_inlier_errors_m=distances,
                estimate_marker_m=result['position_marker_m'],parallax_degrees=result['parallax_deg'],
                reprojection_max_px=result['reprojection_max_px'])
            if reason:rejected[reason]+=1
            else:
                identity=next(iter(identities));error=float(np.linalg.norm(position-centers[identity]))
                item=dict(track_id=row['track_id'],instance_id=identity,plant_id=mapping[identity]['plant_id'],error_m=error,
                    true_class_id=mapping[identity]['class_id'],inliers=len(matched))
                strict.append(item);detail['strict_error_m']=error
            details.append(detail)
        write(output/(variant+'_calyx_details.json'),details)
        write(output/(variant+'_strict_attribution.json'),strict)
        localized={r['instance_id'] for r in strict}
        geometric[variant]=dict(total_tracks=len(candidates),estimated_tracks=len(details),strictly_attributed_tracks=len(strict),
            attribution_rejections=dict(rejected),unique_strictly_localized_instances=len(localized),
            strict_track_error_m=stats([r['error_m'] for r in strict]),
            all_matched_inlier_error_m_including_mixed_tracks=stats(all_inlier_distances),
            duplicate_estimates_per_identity=dict(Counter(r['instance_id'] for r in strict)),coverage={},inspection_visibility_coverage={})
        for key,scopes in [('coverage',visible),('inspection_visibility_coverage',inspection_visible)]:
            for scope,instances in scopes.items():
                selected=localized&instances
                geometric[variant][key][scope]=dict(unique_visible=len(instances),unique_localized=len(selected),
                    fraction=len(selected)/len(instances) if instances else None,
                    strict_track_error_m=stats([r['error_m'] for r in strict if r['instance_id'] in instances]),
                    definition='End-of-route map vs instances ever visible in scope; not online per-frame coverage')
    write(output/'input_hashes.json',inputs)
    result=dict(version='private-full-routes-metric-evaluation/1',passed=True,route=route,frames=count,
        localization_executed=True,scientific_promotion=False,inference_rerun=False,tracking_rerun=False,
        minimum_free_gib=minimum,native_matching_confusions_reproduced=count,
        pose=pose_metrics,calyx=geometric,public_stage_summary=summary,
        reference=protocol['evaluation']['calyx_reference'],limitations=protocol['limitations'],
        coverage_warning='Conditional errors; missing/unassigned tracks remain in coverage denominators. Calyx reference is not a measured internal fruit center.',
        protocol_sha256=sha(stage/'protocol.json'),evaluator_sha256=sha(Path(__file__)),
        output_sha256={p.name:sha(p) for p in output.glob('*.json') if p.name not in {'summary.json','progress.json'}})
    write(output/'summary.json',result)
    write(output/'progress.json',dict(pid=None,stage='complete',completed=count,total=count,minimum_free_gib=minimum))
    print(json.dumps(dict(route=route,passed=True,pose_coverage=pose_metrics['fused']['coverage'],
                         strict_tracks=geometric['fused']['strictly_attributed_tracks'])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--route',required=True)
    a=p.parse_args();evaluate(a.root.resolve(),a.route)
