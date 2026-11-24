"""Exactly six new paired runs from the sealed115 corrected-image bank."""
from pathlib import Path
import argparse,sys,shutil,importlib.metadata,time,traceback
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'src'),str(REPO/'scripts')]
from appearance_campaign import (read,write,sha,require,source_files,default_protocol,verify_real,
    build_dataset,initialize_budget,verify_sources,process_identity,GPUJobLock,SEEDS)
from reviewed_augmentation_pilot import configurations,completed
from run_appearance_campaign import run_subprocess,verify_pair,preserve_partial,freeze_json


def generation_paused(root):
    root=Path(root);bank=root.parent/'bank'
    require(read(REPO/'outputs/spatial_dataset_completion_20261030/pause_requested.json')['active'],
            'Historical generation must stay paused')
    sealed=read(bank/'sealed.json')
    require(sealed['complete_images']==115 and sealed['rendering_stopped'],'Need sealed bounded bank')
    require(sha(bank/'manifest.json')==sealed['manifest_sha256'],'Sealed bank changed')
    from uchuva_lsystem.dataset_completion import owner_alive
    for job in (bank/'jobs').glob('job_*'):
        if (job/'exit.json').exists():continue
        if (job/'process.json').exists():require(not owner_alive(read(job/'process.json')),'Own capture worker still active')


def prepare(root):
    root=Path(root).resolve();generation_paused(root);bank=root.parent/'bank'
    require(not (root/'plan.json').exists(),'Preserve prepared pilot; resume run')
    review=read(bank/'technical_review.json')
    require(review['passed'] and review['sealed_sha256']==sha(bank/'sealed.json'),'Need technical bank review before training')
    root.mkdir(parents=True,exist_ok=True)
    prior=REPO/'outputs/reviewed_augmentation_115_20261031'
    previous=read(prior/'plan.json');old_packages=read(prior/'training_source_lock.json')['packages']
    packages={p:importlib.metadata.version(p) for p in old_packages};require(packages==old_packages,'Changed training packages')
    shutil.copy2(prior/'real_manifest.json',root/'real_manifest.json');real=verify_real(root)
    manifest=read(bank/'manifest.json');rows={r['view_id']:r for r in manifest['views']}
    order=read(bank/'plan.json')['views'];require(len(rows)==len(order)==115,'Exactly115 new images required')
    views=[];inputs=[bank/'sealed.json',bank/'manifest.json',bank/'source_lock.json',bank/'plan.json',bank/'baseline.json',bank/'technical_review.json',
        bank/'pixel_reverification.json',bank.parent/'verify_bank_for_training.py']
    # Preserve the evidence supporting cached geometric masks, not only RGBs.
    inputs.extend(sorted((bank/'prepared').glob('*/native_mask_validation.json')))
    inputs.extend(sorted((bank/'prepared').glob('*/checkpoint.json')))
    inputs.extend(sorted((bank/'prepared').glob('*/surface_plans.json')))
    for i,item in enumerate(order):
        r=rows[item['view_id']]
        for k in ('image','mask','label'):
            require(sha(r[k])==r[k+'_sha256'],'Changed generated pair');inputs.append(Path(r[k]))
        record=bank/'views'/r['view_id']/'view.json';inputs.extend([record,record.parent/'pixel_audit.json'])
        views.append(dict(source_id=f'view_{i:04d}',scene_id=r['scene_id'],view_id=r['view_id'],
            plant_ids=r['plant_seeds'],variants={'reviewed':r}))
    dataset=build_dataset(root,dict(arm='paired_slots115',bank='reviewed',synthetic_images=115,classical=True),real,views)
    plan=dict(kind='daylight115_synthetic_plus_classical_vs_real_plus_classical',configs=configurations(dataset),
        authorization='User explicitly authorized115 corrected RGBs, sparse overmature calyces, varied skies, and six new paired4000-step runs; no expansion before results',
        selected_records=[str(bank/'views'/v['view_id']/'view.json') for v in order],
        source_camera_selection_same_as_previous=True,bank_root=str(bank),bank_manifest_sha256=sha(bank/'manifest.json'),
        training_steps_each=4000,total_optimizer_updates=24000,screenings=0,synthetic_images=115,
        paired_control=previous['paired_control'],real_counts=previous['real_counts'],
        small_object_policy=previous['small_object_policy'],augmentation=previous['augmentation'],
        selection_used_test=False,test_status='development_previously_consulted',
        evaluation=previous['evaluation'],stop_after_six=True,expand_generation=False,
        inference_scope='overall new synthetic-bank effect; appearance, sky distribution and class proportions changed jointly, not a component ablation')
    write(root/'plan.json',plan);write(root/'protocol.json',default_protocol());initialize_budget(root)
    require(read(root/'protocol.json')==read(prior/'protocol.json'),'Protocol differs from prior pilot')
    write(root/'authorization.json',dict(instruction=plan['authorization'],selection_reviewed=True,
        meaning='User approved corrected method and execution of115-image pilot; no claim of individual human annotation certification',
        generation_must_remain_paused=True,automatic_expansion=False))
    native=Path(importlib.metadata.distribution('ultralytics').locate_file('ultralytics/data/augment.py'))
    paths=source_files()+[REPO/'scripts/reviewed_augmentation_pilot.py',REPO/'scripts/daylight_augmentation_pilot.py',
        REPO/'scripts/train_daylight_augmentation.py',REPO/'scripts/evaluate_daylight_augmentation.py',
        REPO/'tests/test_daylight_augmentation_pilot.py',REPO/'scripts/report_daylight_115_bank.py',native,root/'plan.json',root/'protocol.json',
        root/'authorization.json',root/'real_manifest.json',REPO/'yolo26n.pt',*inputs]
    paths += [p for p in Path(dataset).parent.rglob('*') if p.is_file()]
    write(root/'training_source_lock.json',dict(files={str(p.resolve()):sha(p) for p in sorted(set(map(Path,paths)))},packages=packages))
    snapshot=root/'source_snapshot';snapshot.mkdir()
    for p in paths:
        if p.suffix=='.py':shutil.copy2(p,snapshot/p.name)
    verify_sources(root);write(root/'state.json',dict(stage='prepared',runs=6,training_started=False))


def adopt_children(root):
    from uchuva_lsystem.dataset_completion import owner_alive
    for p in sorted((root/'children').glob('*.json')):
        record=read(p)
        if record.get('returncode') is not None:continue
        ident=record.get('identity')
        if not ident:continue
        while owner_alive(dict(pid=ident['pid'],creation_tick=ident['created'])):
            write(root/'state.json',dict(stage='adopting_existing_training_child',child=record['name'],identity=ident));time.sleep(3)
        record.update(recovered_parent=True);write(p,record)


def run(root):
    root=Path(root).resolve()
    with GPUJobLock(root/'controller.lock'):
        generation_paused(root);verify_sources(root);adopt_children(root)
        write(root/'controller_identity.json',process_identity());plan=read(root/'plan.json')
        for c in plan['configs']:
            if completed(root,c):continue
            generation_paused(root);verify_sources(root);preserve_partial(root,c['name'])
            path=root/'configs'/(c['name']+'.json');write(path,c)
            write(root/'state.json',dict(stage='training',run=c['name'],completed_runs=sum(completed(root,x) is not None for x in plan['configs']),total_runs=6,automatic_expansion=False))
            run_subprocess(root,c['name'],'train_daylight_augmentation.py',['--config',path],'train')
            require(completed(root,c),'Incomplete training run')
        for seed in SEEDS:verify_pair(root,f'final_synthetic115_classical_{seed}',f'final_real_classical_{seed}',repeat=True)
        runs={c['name']:completed(root,c) for c in plan['configs']}
        freeze_json(root/'evaluation_lock.json',dict(runs=list(runs),weights={n:r['best_sha256'] for n,r in runs.items()},
            plan_sha256=sha(root/'plan.json'),source_lock_sha256=sha(root/'training_source_lock.json'),
            selection_used_test=False,test_status='development_previously_consulted'))
        if not (root/'evaluation/completion.json').exists():
            write(root/'state.json',dict(stage='evaluation',completed_runs=6,automatic_expansion=False))
            run_subprocess(root,'evaluation','evaluate_daylight_augmentation.py',[],'evaluation')
        generation_paused(root);verify_sources(root)
        write(root/'state.json',dict(stage='pilot_complete_pending_review',completed_runs=6,automatic_expansion=False,
            report=str(root/'evaluation/report.md')))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'));p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    try:(prepare if a.action=='prepare' else run)(a.root)
    except BaseException:
        write(a.root/'controller_failure.json',dict(traceback=traceback.format_exc(),time=time.time()));raise
