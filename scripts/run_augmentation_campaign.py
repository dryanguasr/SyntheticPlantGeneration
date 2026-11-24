"""Serial, bounded orchestration. Selection reads validation only."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

from augmentation_pilot import ROOT, REPO, read, write, sha, make_dataset, gate


def job(script, args, name, deadline):
    if time.time()>=deadline:raise TimeoutError(name)
    log=ROOT/'logs'/f'{name}.log';log.parent.mkdir(exist_ok=True)
    write(ROOT/'state.json',dict(stage=name,pid=os.getpid(),updated=time.time(),complete=False))
    with log.open('w',encoding='utf-8') as out:
        subprocess.run([sys.executable,str(REPO/'scripts'/script),*map(str,args)],cwd=REPO,
            stdout=out,stderr=subprocess.STDOUT,check=True,timeout=max(1,deadline-time.time()))


def run_arm(config):
    output=ROOT/'training'/config['name']
    if (output/'completion.json').exists():
        complete=read(output/'completion.json')
        assert complete['steps']==config['steps'] and sha(output/'weights/best.pt')==complete['best_sha256']
        assert complete['config']['dataset_sha256']==sha(Path(config['dataset']).parent/'manifest.json')
        assert complete['config']['protocol_sha256']==sha(ROOT/'protocol.json')
        for key in ['seed','classical','dataset','steps','name']:
            assert complete['config'][key]==config[key],key
        for path,digest in read(ROOT/'training_source_lock.json')['files'].items():assert sha(path)==digest,path
        return complete
    path=ROOT/'configs'/f"{config['name']}.json";write(path,config)
    job('train_augmentation_arm.py',['--config',path],config['name'],read(ROOT/'budget.json')['training_deadline'])
    return read(output/'completion.json')


def prepare_matrix():
    real=read(ROOT/'real_manifest.json')['rows'];subsets=read(ROOT/'subsets.json')
    candidates=read(ROOT/'synthetic/manifest.json')['rows'] if (ROOT/'synthetic/manifest.json').exists() else []
    # The camera-calibration frames remain evidence but are not forced into the bank.
    candidates=[r for r in candidates if int(r['synthetic_id'].split('_')[-1])>=6]
    # Geometry-only selection: match a shuffled real image sequence without replacement.
    # This ordering is shared by all ratios; no validation score enters bank selection.
    import random, math
    import numpy as np
    target=[r for r in real if r['split']=='train'];random.Random(20261022).shuffle(target)
    def feature(row):
        sizes=[b['min_side_960'] for b in row['geometry']['boxes']]
        hist=np.histogram(sizes,[0,16,32,64,np.inf])[0]/max(1,len(sizes))
        return np.array([math.log1p(float(np.median(sizes)) if sizes else 0),*hist])
    features=[feature(r) for r in candidates];ordered=[];remaining=list(range(len(candidates)))
    for i in range(len(candidates)):
        wanted=feature(target[i%len(target)])
        chosen=min(remaining,key=lambda j:float(np.sum((features[j]-wanted)**2)))
        ordered.append(candidates[chosen]);remaining.remove(chosen)
    candidates=ordered
    write(ROOT/'synthetic/bank_order.json',dict(ids=[r['synthetic_id'] for r in candidates],
        method='nearest unused candidate to seeded train-image size sequence; log median size/four size fractions; density descriptive only',test_or_val_used=False))
    matrix=[]
    for fraction in [100,50,25]:
        selected=[r for r in real if r['source_row'] in subsets[str(fraction)]]
        for ratio in [0,.25,.5,1]:
            n=round(len(selected)*ratio);synthetic=candidates[:n]
            admission=gate(selected,synthetic) if ratio else dict(passed=True)
            admitted=admission['passed'] and len(synthetic)==n
            name=f'r{fraction}_s{int(ratio*100)}'
            write(ROOT/'admissions'/f'{name}.json',dict(admission,requested=n,available=len(candidates),admitted=admitted))
            dataset=make_dataset(name,selected,synthetic) if admitted else None
            for classical in [False,True]:
                matrix.append(dict(arm=name+f'_c{int(classical)}',real_fraction=fraction,synthetic_ratio=ratio,
                    real_images=len(selected),synthetic_images=n,classical=classical,
                    dataset=str(dataset) if dataset else None,status='ready' if admitted else 'blocked_geometry_or_count'))
    write(ROOT/'matrix.json',matrix)
    return matrix


def train():
    protocol=read(ROOT/'protocol.json');deadline=read(ROOT/'budget.json')['training_deadline']
    matrix=read(ROOT/'matrix.json') if (ROOT/'matrix.json').exists() else prepare_matrix()
    results={}
    for arm in matrix:
        if arm['status']!='ready':continue
        config=dict(arm,name='screen_'+arm['arm'],seed=protocol['seeds'][0],steps=2000)
        results[arm['arm']]=run_arm(config)
    finalists=[]
    for fraction in [100,50,25]:
        group=[a for a in matrix if a['real_fraction']==fraction and a['arm'] in results]
        for classical in [False,True]:
            same=[a for a in group if a['classical']==classical]
            finalists.extend(a for a in same if a['synthetic_ratio']==0)
            synthetic=[a for a in same if a['synthetic_ratio']>0]
            if synthetic:
                finalists.append(max(synthetic,key=lambda a:(results[a['arm']]['best_validation_ap'],-a['synthetic_ratio'])))
    lock=ROOT/'finalists_lock.json'
    payload=dict(finalists=finalists,screening={k:v['best_validation_ap'] for k,v in results.items()},
                 selection='validation macro AP only; ties prefer less synthetic',test_read=False)
    if lock.exists():assert read(lock)==payload
    else:write(lock,payload)
    final_results=[]
    for fraction in [100,50,25]:
        group=[a for a in finalists if a['real_fraction']==fraction]
        # Budget admission estimates measured screening seconds; complete a paired seed block.
        estimate=sum(results[a['arm']]['seconds']*2.2 for a in group)
        for seed in protocol['seeds']:
            if time.time()+estimate>=deadline:
                write(ROOT/'budget_exclusions.json',dict(fraction=fraction,seed=seed,estimated_block_seconds=estimate));break
            for arm in group:
                config=dict(arm,name=f"final_{arm['arm']}_{seed}",seed=seed,steps=4000)
                final_results.append(run_arm(config))
    mixtures=[r for r in final_results if r['config']['synthetic_ratio']>0]
    controls=[]
    if mixtures:
        by_arm={}
        for row in mixtures:by_arm.setdefault(row['config']['arm'],[]).append(row)
        eligible={k:v for k,v in by_arm.items() if len(v)==3}
        if eligible:
            winner=max(eligible,key=lambda k:sum(r['best_validation_ap'] for r in eligible[k])/3)
            for result in eligible[winner]:
                config=dict(result['config']);config.update(name='repeat_'+config['name'],repeat_control=True)
                if time.time()+result['seconds']*1.2<deadline:
                    control=run_arm(config)
                    original=read(ROOT/'training'/result['config']['name']/'sampling_sequences.json')
                    repeated=read(ROOT/'training'/control['config']['name']/'sampling_sequences.json')
                    assert len(original)==len(repeated)
                    for a,b in zip(original,repeated):
                        assert a['planned_source_ids']==b['planned_source_ids']
                        assert all(x==y for x,y in zip(a['actual_source_ids'],b['actual_source_ids']) if x.startswith('row_'))
                        assert all(x.startswith('row_') for x in b['actual_source_ids'])
                    write(ROOT/'training'/control['config']['name']/'repetition_pair_check.json',dict(passed=True,original=result['config']['name']))
                    controls.append(control)
    write(ROOT/'evaluation_lock.json',dict(created=time.time(),finalists_sha256=sha(lock),
        runs=[r['config']['name'] for r in final_results+controls],
        weights={r['config']['name']:r['best_sha256'] for r in final_results+controls},
        test_status=protocol['test_status'],selection_used_test=False))
    job('evaluate_augmentation_campaign.py',[],'evaluation',read(ROOT/'budget.json')['deadline'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['matrix','train']);args=p.parse_args()
    if args.action=='matrix':prepare_matrix()
    else:train()
