"""Private CPU-only native-mask full-route evaluation, by target, phase and side."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
HELPER_SHA = '111f4359578dae14adaef24626b82bc94b644efef82d1b4076d54a7906b34527'
SMOKE_SHA = 'a2f0feaf7624c826ae1305b66ab349690dbd2affc6c08e94c395f31fa69e987b'
TARGET_POLICY = {
    'target_plant': 'Per-frame frozen trajectory target_plant; evaluator only',
    'matching': 'confidence-ordered class-agnostic native mask IoU>=0.5 against ALL visible truth first',
    'neighbor_matches': 'ignored even with wrong class; never target false positives',
    'small_target_matches': 'ignored in target_eligible',
    'duplicate_small_predictions': 'global one-to-one unmatched duplicates retain centroid FP rule; differs from global eligible any-small-ignore policy',
    'unmatched_false_positive': 'only if predicted mask centroid lies inside union bounding rectangle of all visible current-target calyx boxes',
    'target_region_source': 'private evaluator only; never input to inference or tracking',
    'empty_target': 'no envelope, no target false positives; all metrics still reported'
}

def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def module(p, name):
    s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def target_associate(native, truth, predictions, detections, eligible_only, helper, smoke, target_plant, full_result):
    full=full_result  # Reuse global all-object assignments; never rematch after target selection.
    by_prediction={r['prediction_index']:(identity,r) for identity,r in full['matches'].items()}
    target=[t for t in truth if t['plant_id']==target_plant]
    selected={t['instance_id']:t for t in target if not eligible_only or (t['pixels']>=100 and min(t['bbox'][2]-t['bbox'][0],t['bbox'][3]-t['bbox'][1])>=8)}
    all_by_id={t['instance_id']:t for t in truth}
    envelope=None if not target else [min(t['bbox'][0] for t in target),min(t['bbox'][1] for t in target),max(t['bbox'][2] for t in target),max(t['bbox'][3] for t in target)]
    cm=np.zeros((4,4),np.int64);matches={};ignored_neighbor=ignored_small=ignored_outside=0
    for i,p in enumerate(predictions):
        if i in by_prediction:
            identity,result=by_prediction[i];t=all_by_id[identity]
            if t['plant_id']!=target_plant:ignored_neighbor+=1;continue
            if identity not in selected:ignored_small+=1;continue
            cm[t['class_id'],p['label']['class_id']]+=1;matches[identity]=result
        else:
            yy,xx=np.nonzero(p['mask']);x=p['bbox'][0]+float(xx.mean());y=p['bbox'][1]+float(yy.mean())
            if envelope is not None and envelope[0]<=x<envelope[2] and envelope[1]<=y<envelope[3]:cm[3,p['label']['class_id']]+=1
            else:ignored_outside+=1
    remaining=set(selected)-set(matches)
    for identity in remaining:cm[selected[identity]['class_id'],3]+=1
    return dict(metrics=dict(**helper.summarize(cm),truth_total=len(target),truth_in_scope=len(selected),truth_excluded_small=len(target)-len(selected),ignored_small_predictions=ignored_small,ignored_neighbor_predictions=ignored_neighbor,ignored_unmatched_outside_target=ignored_outside),matches=matches,visible_ids=set(selected),unmatched_ids=remaining)

def matrix(path, metrics, title):
    image=Image.new('RGB',(760,600),'white');draw=ImageDraw.Draw(image)
    draw.text((12,12),title,fill='black');draw.text((12,34),'Filas verdad / columnas prediccion: pintona, madura, sobremadura, sin pareja',fill='black')
    cm=np.asarray(metrics['confusion']);maximum=max(1,int(cm.max()))
    labels=['pintona','madura','sobremadura','sin pareja']
    for i in range(4):
        draw.text((10,90+i*105+42),labels[i],fill='black');draw.text((120+i*145,65),labels[i],fill='black')
        for j in range(4):
            x=110+j*145;y=90+i*105;v=int(cm[i,j])/maximum
            draw.rectangle((x,y,x+143,y+103),fill=(int(240-160*v),int(248-100*v),255))
            draw.text((x+45,y+45),str(cm[i,j]),fill='black')
    draw.text((12,530),f"P={metrics['precision']:.2%}, R={metrics['recall']:.2%}, F1={metrics['f1']:.2%}",fill='black')
    draw.text((12,554),'Apariencia del capacho, no madurez interna; métricas por observación.',fill='black')
    image.save(path)

def temporal_summary(rows):
    switches=[];adjacent_visible=0;adjacent_matched=0;lost=0;gained=0;pair_details=[]
    for previous,current in zip(rows,rows[1:]):
        if current['frame']!=previous['frame']+1:continue  # Grouping must never create artificial adjacency.
        jointly_visible=previous['visible_ids']&current['visible_ids']
        both_matched=set(previous['matches'])&set(current['matches'])
        assert both_matched<=jointly_visible
        adjacent_visible+=len(jointly_visible);adjacent_matched+=len(both_matched)
        pair_switches=0
        for identity in sorted(both_matched):
            a=previous['matches'][identity];b=current['matches'][identity]
            if a['track_id']!=b['track_id']:
                switches.append(dict(previous_frame=previous['frame'],frame=current['frame'],
                    true_instance_id=identity,previous_track_id=a['track_id'],track_id=b['track_id']))
                pair_switches+=1
        lost+=len((set(previous['matches'])&jointly_visible)-set(current['matches']))
        gained+=len((set(current['matches'])&jointly_visible)-set(previous['matches']))
        pair_details.append(dict(previous_frame=previous['frame'],frame=current['frame'],
            jointly_visible_true_instances=len(jointly_visible),both_spatially_matched=len(both_matched),
            identity_switches=pair_switches))
    visible=sum(len(r['visible_ids']) for r in rows);matched=sum(len(r['matches']) for r in rows)
    seen=set().union(*(r['visible_ids'] for r in rows));seen_matched=set().union(*(set(r['matches']) for r in rows))
    correct=sum(m['true_class_id']==m['predicted_class_id'] for r in rows for m in r['matches'].values())
    return dict(visible_truth_observations=visible,spatially_matched_truth_observations=matched,
        correct_class_spatial_matches=correct,spatial_omissions=visible-matched,
        spatial_coverage=matched/max(1,visible),unique_true_instances_visible=len(seen),
        unique_true_instances_matched=len(seen_matched),adjacent_jointly_visible_truth_pairs=adjacent_visible,
        adjacent_both_matched_pairs=adjacent_matched,
        adjacent_pairs_missing_at_least_one_match=adjacent_visible-adjacent_matched,
        consecutive_match_coverage=adjacent_matched/max(1,adjacent_visible),
        adjacent_identity_switches=len(switches),
        conditional_adjacent_switch_rate=len(switches)/adjacent_matched if adjacent_matched else None,
        previous_match_lost_while_still_visible=lost,new_match_while_previously_visible=gained,
        changes=switches,pairs=pair_details,
        definition='Change of predicted track ID for the same true instance matched by native maskIoU>=0.5 in adjacent frames; matching ignores class.',
        not_computed=['IDF1','HOTA','MOTA','reidentification after a missing match','3D localization'])



def summarize_group(groups,helper):
    result=dict(detection={},tracking={})
    for mode,rows in groups.items():
        cm=sum((np.asarray(r['metrics']['confusion']) for r in rows),np.zeros((4,4),np.int64))
        metrics=helper.summarize(cm)
        for key in ['truth_total','truth_in_scope','truth_excluded_small','ignored_small_predictions','ignored_neighbor_predictions','ignored_unmatched_outside_target']:
            metrics[key]=sum(r['metrics'].get(key,0) for r in rows)
        result['detection'][mode]=metrics;result['tracking'][mode]=temporal_summary(rows)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--scene',required=True)
    args=p.parse_args();root=args.root.resolve();flight=root/'flights'/args.scene
    protocol=read(root/'protocol.json');scene=next(x for x in protocol['scenes'] if x['name']==args.scene);count=scene['views']
    assert count==len(scene['trajectory']) and count>0 and scene['fps']==4
    helper_path=root.parents[1]/'multiscale_dataset_20261020/evaluate_multiscale_v1.py'
    assert sha(helper_path)==HELPER_SHA
    smoke_path=root.parent/'evaluate_smoke_private_v1.py'
    assert sha(smoke_path)==SMOKE_SHA
    helper=module(helper_path,'frozen_route_metrics');smoke=module(smoke_path,'frozen_smoke_metrics')
    validation=read(flight/'validation_v1.json');pred=flight/'predictions_new';tracks=flight/'tracking_new'
    ps=read(pred/'summary.json');ts=read(tracks/'summary.json');observations=read(tracks/'observations.json');frames=read(flight/'public/frames.json')
    assert validation['passed'] and validation['frames']==len(frames)==len(observations)==count
    assert ps['complete'] and len(ps['frames'])==count and ts['tracking_complete'] and not ts['private_inputs']
    for name,digest in validation['source_hashes'].items():assert sha(root/name)==digest
    for name,digest in validation['public_files'].items():assert sha(flight/'public'/name)==digest
    output=flight/'evaluation_private_v1'
    if output.exists():raise FileExistsError('Preserve prior evaluation: '+str(output))
    mapping=read(root/'captures'/args.scene/'class_mapping_private.json')
    groups={k:[] for k in ['all','eligible','target_all','target_eligible']};per_frame=[]
    for i,(frame,obs) in enumerate(zip(frames,observations)):
        helper.memory_guard();assert obs['frame']==i and obs['stamp_ns']==frame['stamp_ns']
        stem=f'frame_{i:03d}';record=read(pred/'predictions'/(stem+'.json'));binding=record['binding']
        assert sha(pred/'predictions'/(stem+'.json'))==obs['prediction_record_sha256']
        assert binding['frame']==i and binding['stamp_ns']==frame['stamp_ns'] and binding['rgb_sha256']==frame['rgb_sha256'] and binding['run_binding']==ps['run_binding']
        assert record['inference_uses_ground_truth'] is False
        predictions=helper.load_predictions(pred/'predictions',stem,binding);detections=obs['detections']
        assert len(predictions)==len(detections) and len({d['track_id'] for d in detections})==len(detections)
        for a,b in zip(predictions,detections):
            assert a['bbox']==b['box_xyxy_px'] and a['label']['class_id']==b['class_id'] and abs(a['label']['confidence']-b['confidence'])<1e-10
        native,truth=smoke.original_truth(root/'captures'/args.scene/f'view_{i:03d}',mapping)
        for t in truth:t['plant_id']=mapping[t['instance_id']]['plant_id']
        pose=scene['trajectory'][i];target_plant=pose['target_plant'];phase=pose['phase'];side=pose['side']
        assert target_plant in {p['instance_id'] for p in scene['plants']}
        assert isinstance(phase,str) and phase.replace('_','').isalnum() and isinstance(side,str) and side.replace('_','').isalnum()
        full_result=smoke.associate(native,truth,predictions,detections,False,helper)
        entry=dict(frame=i,stamp_ns=frame['stamp_ns'],target_plant=target_plant,phase=phase,side=side,metrics={})
        for mode in groups:
            eligible=mode.endswith('eligible')
            if mode.startswith('target'):result=target_associate(native,truth,predictions,detections,eligible,helper,smoke,target_plant,full_result)
            elif mode=='all':result=full_result
            else:result=smoke.associate(native,truth,predictions,detections,True,helper)
            result['frame']=i;result['phase']=phase;result['side']=side;result['target_plant']=target_plant;groups[mode].append(result);entry['metrics'][mode]=result['metrics']
        per_frame.append(entry)
    report=dict(version='private-full-route-evaluation/1',passed=True,scene=args.scene,frames=count,fps=4,video_duration_seconds=count/4,first_to_last_seconds=(count-1)/4,
        cpu_only=True,inference_rerun=False,localization_performed=False,scientific_promotion=False,
        target_false_positive_policy=read(root/'protocol.json')['evaluation']['target_false_positive_policy'],target_matching_order=read(root/'protocol.json')['evaluation']['target_matching_order'],target_eligible_policy=read(root/'protocol.json')['evaluation']['target_eligible_policy'],target_implementation=TARGET_POLICY,
        binding=dict(protocol_sha256=sha(root/'protocol.json'),evaluator_sha256=sha(Path(__file__)),helper_sha256=HELPER_SHA,smoke_evaluator_sha256=SMOKE_SHA,validation_sha256=sha(flight/'validation_v1.json'),predictions_summary_sha256=sha(pred/'summary.json'),tracking_summary_sha256=sha(tracks/'summary.json'),observations_sha256=sha(tracks/'observations.json')),
        detection={},tracking={},per_frame=per_frame,marker_8_decoded_frames=validation['marker_8_decoded_frames'],
        limitations=['Routes may have different durations and target coverage; compare inspection and transit separately; partial orbits remain explicit in protocol.','Target envelopes are evaluator truth; no automatic target ROI capability or perfect false-positive attribution is claimed.','Target eligible uses global one-to-one matching: unmatched duplicate-small predictions keep the centroid FP rule, unlike all-object eligible which ignores any small-object IoU>=0.5 match.','Adjacent ID switches conditional on paired spatial matches, not IDF1/HOTA/MOTA.','One common ArUco8, no independent marker acquisition at C07; 3D localization and final PiP remain pending.','Validation plants with shared morphology; no external holdout or production claim.','Eligible100pixels/side8 is an engineering convention, not universal YOLO limit.'])
    output.mkdir()
    aggregate=summarize_group(groups,helper)
    report['detection']=aggregate['detection'];report['tracking']=aggregate['tracking']
    for mode,metrics in report['detection'].items():matrix(output/f'confusion_{mode}.png',metrics,args.scene+' / '+mode)
    for dimension in ['phase','side','target_plant']:
        report['by_'+dimension]={}
        for value in sorted({r[dimension] for r in groups['all']}):
            subgroup={mode:[r for r in rows if r[dimension]==value] for mode,rows in groups.items()}
            grouped=summarize_group(subgroup,helper)
            grouped['frame_indices']=[r['frame'] for r in subgroup['all']]
            grouped['frames']=len(grouped['frame_indices'])
            grouped['duration_seconds']=grouped['frames']/4
            report['by_'+dimension][value]=grouped
            if dimension=='phase':
                for mode,metrics in grouped['detection'].items():matrix(output/f'confusion_phase_{value}_{mode}.png',metrics,args.scene+' / '+value+' / '+mode)
    report['matrix_sha256']={p.name:sha(p) for p in output.glob('confusion_*.png')};helper.write(output/'summary.json',report)
    print(json.dumps(dict(passed=True,scene=args.scene,report=str(output/'summary.json'))))

if __name__=='__main__':main()
