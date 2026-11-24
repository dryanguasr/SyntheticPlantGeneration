"""Complete the authorized real controls when no synthetic dose was admitted.

Uses the unchanged exact-step trainer/evaluator. Never renders, relaxes the
physical gate, or presents real-only results as a factorial comparison.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import statistics
import time
import traceback

from appearance_campaign import (GPUJobLock, SEEDS, prepare_matrix, read, write, sha,
    require, process_identity, verify_sources, charged_job, budget_usage)
from run_appearance_campaign import (make_config, run_arm, completed, block_fits,
    assert_no_orphans, freeze_json)


def control_plan(matrix):
    require(matrix['available_doses']==[], 'Fallback requires no complete synthetic dose')
    arms=matrix['matrix']
    require(len(arms)==2 and all(a['bank']=='real' and a['synthetic_images']==0 for a in arms),
            'Fallback must contain only the two authorized real controls')
    require({a['classical'] for a in arms}=={True,False}, 'Missing classical recipe')
    arms=sorted(arms,key=lambda a:not a['classical'])
    return ([make_config(a,SEEDS[0],2000,'screen') for a in arms],
            [[make_config(a,s,4000) for s in SEEDS] for a in arms])


def freeze_evaluation(root, configs):
    runs={c['name']:completed(root,c) for c in configs}
    require(len(runs)==6 and all(runs.values()), 'Require all six complete controls before development test')
    for seed in SEEDS:
        pair=[c for c in configs if c['seed']==seed]
        a,b=[root/'training'/c['name'] for c in pair]
        require(read(a/'sampling_sequences.json')==read(b/'sampling_sequences.json'), 'Unpaired real sampling')
        require(read(a/'learning_rates.json')==read(b/'learning_rates.json'), 'Different LR schedules')
    lock=dict(kind='real_controls_only_synthetic_generation_blocked', runs=list(runs),
        weights={name:value['best_sha256'] for name,value in runs.items()},
        protocol_sha256=sha(root/'protocol.json'),matrix_sha256=sha(root/'matrix_lock.json'),
        training_source_lock_sha256=sha(root/'training_source_lock.json'),
        selection_used_test=False,test_status='development_previously_consulted',
        synthetic_comparisons='not executed; no complete admitted dose',
        repetition_controls='not applicable; no synthetic winner')
    freeze_json(root/'evaluation_lock.json',lock)
    return lock,runs


def evaluate_controls(root, configs):
    import numpy as np
    import torch
    from ultralytics import YOLO
    from evaluate_appearance_campaign import evaluate_run,checked_groups,three_class_ap,mean_sd
    lock,runs=freeze_evaluation(root,configs)
    torch.set_num_threads(4)
    threshold_path=root/'evaluation_threshold.json'
    if not threshold_path.exists():
        baseline=next(c for c in configs if c['classical'] and c['seed']==SEEDS[0])
        name=baseline['name']
        result=YOLO(root/'training'/name/'weights/best.pt').val(data=baseline['dataset'],split='val',
            imgsz=960,batch=2,device=0,workers=0,conf=.001,iou=.7,max_det=300,plots=False,
            project=str(root/'evaluation'),name='threshold_validation')
        threshold=float(result.box.px[np.argmax(np.asarray(result.box.f1_curve).mean(0))])
        write(threshold_path,dict(value=threshold,source=name,split='val',test_used=False,
            weight_sha256=lock['weights'][name],evaluation_lock_sha256=sha(root/'evaluation_lock.json')))
    threshold=read(threshold_path)
    require(not threshold['test_used'] and threshold['evaluation_lock_sha256']==sha(root/'evaluation_lock.json'),
            'Operating threshold lock changed')
    summaries={name:evaluate_run(root,name,threshold['value'],lock) for name in lock['runs']}
    write(root/'evaluation/summary.json',summaries)
    predictions={name:read(root/'evaluation'/name/'predictions.json') for name in lock['runs']}
    draws=checked_groups(next(iter(predictions.values())))
    write(root/'evaluation/real_only_bootstrap_draws.json',draws)
    by_seed=[]
    sampled=[]
    for seed in SEEDS:
        off=next(c['name'] for c in configs if c['seed']==seed and not c['classical'])
        on=next(c['name'] for c in configs if c['seed']==seed and c['classical'])
        by_seed.append(dict(seed=seed,without_classical=summaries[off]['ap'],with_classical=summaries[on]['ap'],
            difference=summaries[on]['ap']['map50_95']-summaries[off]['ap']['map50_95'],
            validation_without_classical=runs[off]['best_validation_ap'],validation_with_classical=runs[on]['best_validation_ap']))
    grouped={name:{g:[r for r in rows if r['group']==g] for g in draws['groups']} for name,rows in predictions.items()}
    for draw in draws['draws']:
        differences=[]
        for seed in SEEDS:
            names=[next(c['name'] for c in configs if c['seed']==seed and c['classical']==v) for v in (False,True)]
            values=[three_class_ap([row for g in draw for row in grouped[name][g]])['map50_95'] for name in names]
            differences.append(values[1]-values[0])
        sampled.append(statistics.mean(differences))
    payload=dict(kind=lock['kind'],by_seed=by_seed,
        without_classical=mean_sd([x['without_classical']['map50_95'] for x in by_seed]),
        with_classical=mean_sd([x['with_classical']['map50_95'] for x in by_seed]),
        paired_difference=mean_sd([x['difference'] for x in by_seed]),
        paired_group_bootstrap=dict(mean_draw_differences=sampled,
            percentile_95=np.percentile(sampled,[2.5,97.5]).tolist(),
            conditioning=draws['conditioning'],limitation=draws['limitation']),
        synthetic_comparisons='not executed; no admitted views; no conclusion about effects L/T/LT',
        test_status='development_previously_consulted',selection_used_test=False)
    write(root/'evaluation/real_only_comparisons.json',payload)
    write(root/'evaluation/real_only_completion.json',dict(completed=True,runs=6,
        comparisons_sha256=sha(root/'evaluation/real_only_comparisons.json'),finished_utc=time.time()))


def run(root):
    root=root.resolve();revision=root/'revisions/real_controls_after_bank_rejection_20261027'
    revision.mkdir(parents=True,exist_ok=True)
    with GPUJobLock(root/'pipeline.lock'):
        old=read(root/'pipeline_controller.json');owner=old.get('identity')
        require(not owner or process_identity(owner['pid'])!=owner,'Original pipeline is still alive')
        assert_no_orphans(root)
        bank=read(root/'banks/manifest.json')
        require(bank['complete_views']==0 and bank['available_doses']==[], 'Wrong fallback condition')
        identity=process_identity();status=root/'controls_controller.json'
        if status.exists():
            previous=read(status);pid=previous.get('identity')
            require(not pid or process_identity(pid['pid'])!=pid,'Control controller still alive')
            write(revision/'controller_history'/f'{time.time_ns()}.json',previous)
        write(status,dict(identity=identity,state='running',script_sha256=sha(__file__),started_utc=time.time()))
        try:
            matrix=prepare_matrix(root);screen,blocks=control_plan(matrix)
            plan=dict(kind='complete_original_real_controls_only',screens=screen,final_blocks=blocks,
                synthetic_blocked=True,bank_manifest_sha256=sha(root/'banks/manifest.json'),
                training_protocol_unchanged=True,no_additional_renders=True)
            freeze_json(root/'real_only_plan.json',plan)
            source=read(root/'training_source_lock.json')
            if str(Path(__file__).resolve()) not in source['files']:
                require(not list((root/'training').glob('*/completion.json')), 'Never change source lock after training')
                freeze_json(revision/'initial_training_source_lock.json',source)
                source['files'].update({str(Path(__file__).resolve()):sha(__file__),
                    str(root/'real_only_plan.json'):sha(root/'real_only_plan.json')})
                write(root/'training_source_lock.json',source)
            verify_sources(root)
            for block in [screen,*blocks]:
                require(block_fits(root,block),'Insufficient active time for a complete real control block')
                for config in block:run_arm(root,config)
            with charged_job(root,'evaluation','real_controls_development_evaluation'):
                evaluate_controls(root,[c for block in blocks for c in block])
            write(status,dict(identity=identity,state='evaluation_complete_pending_review',finished_utc=time.time(),budget_usage=budget_usage(root)))
            write(root/'state.json',dict(stage='real_controls_evaluation_complete_pending_review',complete=False,
                synthetic_status='blocked_no_admitted_views',real_final_runs=6,screen_runs=2))
        except BaseException as error:
            failure=dict(error=repr(error),traceback=traceback.format_exc(),identity=identity,when_utc=time.time())
            write(revision/'failures'/f'{time.time_ns()}.json',failure)
            write(status,dict(**failure,state='needs_attention'))
            write(root/'state.json',dict(**failure,stage='needs_attention',complete=False))
            raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True)
    run(parser.parse_args().root)
