"""Read-only extension of the current paired diagnosis, without new inference."""
from pathlib import Path
from collections import Counter
import argparse,statistics,sys,importlib.metadata
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'src'),str(REPO/'scripts')]
from appearance_campaign import read,write,sha,SEEDS,verify_sources
from daylight_augmentation_pilot import generation_paused
from diagnose_sobremadura_pilot import inspect_row

CURRENT=REPO/'outputs/daylight_augmentation_115_20261112/pilot'
PREVIOUS=REPO/'outputs/reviewed_augmentation_115_20261031'


def run(root):
    root=root.resolve();root.mkdir(parents=True,exist_ok=True)
    generation_paused(CURRENT);verify_sources(CURRENT)
    inputs={}
    def load(p):
        p=Path(p).resolve();inputs[str(p)]=sha(p);return read(p)
    diagnosis=load(CURRENT/'diagnostics/sobremadura/diagnosis.json')
    comparison=load(CURRENT/'evaluation/comparison.json')
    summaries=load(CURRENT/'evaluation/summary.json')
    exposure=load(CURRENT/'diagnostics/exposure/exposure.json')
    threshold=load(CURRENT/'evaluation_threshold.json')['value']
    totals={};outcomes={};fp_types={};common_ious=[];batches={}
    for arm in ('real_classical','synthetic115_classical'):
        metrics=[m for m in diagnosis['metrics'] if m['arm']==arm]
        totals[arm]={k:sum(m['fixed'][k] for m in metrics) for k in ('tp','fp','fn')}
        counts=Counter()
        for m in metrics:counts.update(m['gt_outcomes'])
        outcomes[arm]=dict(counts)
        types=Counter()
        for m in metrics:types.update(m['fixed_fp_types'])
        fp_types[arm]=dict(types)
    for seed in SEEDS:
        names=[f'final_{arm}_{seed}' for arm in ('real_classical','synthetic115_classical')]
        records=[]
        for name in names:
            path=CURRENT/'evaluation'/name/'predictions.json'
            assert sha(path)==summaries[name]['predictions_sha256']
            records.append(load(path))
        for a,b in zip(*records):
            assert a['source_row']==b['source_row'] and a['truth']==b['truth']
            aa=inspect_row(a,threshold);bb=inspect_row(b,threshold)
            for index,item in enumerate(a['truth']):
                if item['class_id']==2 and aa['outcomes'][index]['status']==bb['outcomes'][index]['status']=='correct':
                    common_ious.append((aa['outcomes'][index]['iou'],bb['outcomes'][index]['iou']))
        sequence=load(CURRENT/'training'/names[1]/'sampling_sequences.json');counts=Counter()
        for epoch in sequence:
            ids=epoch['actual_source_ids'];assert len(ids)==1000
            for offset in range(0,1000,2):counts[sum(x.startswith('view_') for x in ids[offset:offset+2])]+=1
        assert sum(counts.values())==4000
        batches[str(seed)]=dict(real_real=counts[0],real_synthetic=counts[1],synthetic_synthetic=counts[2],
            fraction_updates_containing_synthetic=(counts[1]+counts[2])/4000)
    previous=load(PREVIOUS/'evaluation/comparison.json')
    prior_diagnosis=load(PREVIOUS/'diagnostics/sobremadura_20261031/diagnosis.json')
    raw=[d for d in exposure['distributions'] if d['stage']=='raw' and d['class_id']==2]
    kept=[d for d in exposure['distributions'] if d['stage']=='native_kept' and d['class_id']==2]
    loss=Path(importlib.metadata.distribution('ultralytics').locate_file('ultralytics/utils/loss.py'))
    inputs[str(loss.resolve())]=sha(loss)
    result=dict(version='sobre-texture-transfer-diagnosis/1',seeds=list(SEEDS),real_test_images=94,
        original_truth_boxes_class2_per_seed=58,common_threshold_from_val=threshold,
        comparison=comparison['per_class']['Sobremadura'],
        same_objects_repeated_across_seeds=True,fixed_class2_counts=totals,outcomes_by_target=outcomes,
        fixed_false_positive_geometry_types=fp_types,
        common_class2_true_positives=dict(appearances=len(common_ious),real_median_iou=statistics.median(v[0] for v in common_ious),
            hybrid_median_iou=statistics.median(v[1] for v in common_ious),conditional_on_both_being_true_positive=True),
        leave_one_group_out=diagnosis['leave_one_group_out'],
        every_leave_one_group_out_mean_delta_negative=all(d['mean_delta']<0 for d in diagnosis['leave_one_group_out']),
        native_size_distributions=kept,raw_size_distributions=raw,
        previous_hybrid_mean_ap_class2=previous['per_class']['Sobremadura']['synthetic']['mean'],
        current_hybrid_mean_ap_class2=comparison['per_class']['Sobremadura']['synthetic']['mean'],
        previous_raw_min_side_median=prior_diagnosis['exposure']['raw_class2_size_median'],
        batch_composition=batches,
        counts_are_not_gradient_weights=True,
        loss_implementation_observed=dict(path=str(loss),sha256=sha(loss),ultralytics=importlib.metadata.version('ultralytics'),
            target_scores_sum_normalization_present='target_scores_sum = max(target_scores.sum(), 1)' in loss.read_text(encoding='utf-8'),
            limitation='Installed implementation inspected; no saved per-step assignment scores or gradients. Cannot infer gradient shares from label counts.'),
        causal_attribution=False,joint_changes=['texture','class proportions and assignment','sky and illumination'],
        no_new_training=True,no_new_inference=True,no_plant_renders=True,source_annotations_unchanged=True,
        generation_paused=True)
    for path,digest in inputs.items():assert sha(path)==digest,path
    write(root/'texture_transfer_diagnosis.json',result)
    inputs[str(Path(__file__).resolve())]=sha(__file__)
    write(root/'diagnosis_inputs.json',dict(files=inputs,result_sha256=sha(root/'texture_transfer_diagnosis.json')))
    print(root/'texture_transfer_diagnosis.json')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=REPO/'outputs/sobremadura_four_models_20261113')
    run(parser.parse_args().root)
