"""Locked six-run pilot from a reviewed synthetic subset; never renders."""
from pathlib import Path
import argparse, importlib.metadata, shutil, sys, time, traceback
from appearance_campaign import (REPO, SEEDS, GPUJobLock, read, write, sha, require,
    default_protocol, build_dataset, verify_real, verify_sources, initialize_budget,
    process_identity, source_files)
from run_appearance_campaign import (verify_sequences, verify_pair, run_subprocess,
    assert_no_orphans, preserve_partial, freeze_json)

SOURCE=REPO/'outputs/spatial_dataset_completion_20261030'
DEFAULT=REPO/'outputs/reviewed_augmentation_115_20261031'
REVIEW=SOURCE/'revisions/pause_diversity_500_20261030/assessment/review_addendum.json'


def generation_paused():
    require(read(SOURCE/'pause_requested.json')['active'], 'Generation must remain paused')
    from uchuva_lsystem.dataset_completion import owner_alive
    require(not any(owner_alive(read(SOURCE/p)) for p in ('controller_identity.json','worker_identity.json')),
            'Generation owner is still alive')


def configurations(dataset):
    return [dict(name=f'final_{arm}_{seed}',arm=arm,seed=seed,steps=4000,
        classical=True,real_only=real_only,repeat_control=real_only,dataset=str(dataset))
        for seed in SEEDS for arm,real_only in (('real_classical',True),('synthetic115_classical',False))]


def prepare(root):
    root=Path(root).resolve();generation_paused()
    require(not (root/'plan.json').exists(), 'Preserve existing pilot; use run to resume')
    root.mkdir(parents=True,exist_ok=True)
    real_source=REPO/'outputs/appearance_factorial_20261026/real_manifest.json'
    shutil.copy2(real_source,root/'real_manifest.json');real=verify_real(root)
    review=read(REVIEW);selected=review['candidates']['115']['views']
    require(len(selected)==len(set(selected))==115,'Need exactly115 reviewed views')
    locked=read(SOURCE/'revisions/pause_diversity_500_20261030/review_500_lock.json')
    locked={r['view_record']:r for r in locked['selected']}
    views=[];input_files=[REVIEW,real_source,SOURCE/'dataset/pool_lock.json']
    for i,record in enumerate(selected):
        require(record in locked and sha(record)==locked[record]['view_record_sha256'],'Reviewed view changed')
        v=read(record);require(v['status']=='complete','Unclosed reviewed view')
        require(v['view_id']!='scene_026_view_001','Technical black frame cannot enter pilot')
        for kind in ('image','mask','label'):
            require(sha(v[kind])==v[kind+'_sha256']==locked[record][kind+'_sha256'],'Pair hash changed')
            input_files.append(Path(v[kind]))
        input_files.append(Path(record))
        views.append(dict(source_id=f'view_{i:04d}',scene_id=v['scene_id'],view_id=v['view_id'],
            plant_ids=v['plant_seeds'],variants={'reviewed':v}))
    arm=dict(arm='paired_slots115',bank='reviewed',synthetic_images=115,classical=True)
    dataset=build_dataset(root,arm,real,views)
    plan=dict(kind='reviewed115_synthetic_plus_classical_vs_real_plus_classical',
        authorization='User explicitly requested115 corrected views, two recipes, three seeds; generation remains paused',
        configs=configurations(dataset),selected_records=selected,
        review_sha256=sha(REVIEW),real_manifest_sha256=sha(root/'real_manifest.json'),
        training_steps_each=4000,total_optimizer_updates=24000,screenings=0,
        paired_control='Shared576-source slot schedule; replace synthetic slots by seeded real draws in control; no synthetic exposure in control',
        real_counts={'train':461,'val':88,'test':94},synthetic_images=115,
        augmentation='Native paired HSV_v0.1 and horizontalflip0.5; other random transformations disabled',
        small_object_policy=dict(authority='Installed Ultralytics8.4.114 native RandomPerspective.box_candidates',
            width_height_strictly_greater_px=2,area_ratio_detection=.1,area_ratio_segmentation=.01,
            area_is_retained_fraction_not_absolute_pixels=True,aspect_ratio_less_than=100,
            task='detect',segmentation_training=False,additional_offline_filter=False,
            original_RGB_masks_labels_unchanged=True,
            reference='https://docs.ultralytics.com/reference/data/augment/'),
        evaluation='Best checkpoint by real val only; freeze all six before development test94; no factorial or dose selection',
        selection_used_test=False,test_status='development_previously_consulted',
        stop_after_six=True,expand_generation=False)
    write(root/'plan.json',plan);write(root/'protocol.json',default_protocol());initialize_budget(root)
    write(root/'authorization.json',dict(instruction=plan['authorization'],selection_reviewed=True,
        meaning='Approval to execute pilot, not retrospective human certification of every synthetic class',
        generation_must_remain_paused=True,automatic_expansion=False))
    native=Path(importlib.metadata.distribution('ultralytics').locate_file('ultralytics/data/augment.py'))
    paths=source_files()+[REPO/'scripts/reviewed_augmentation_pilot.py',REPO/'scripts/train_reviewed_augmentation.py',
        REPO/'scripts/evaluate_reviewed_augmentation.py',REPO/'tests/test_reviewed_augmentation_pilot.py',native,
        Path(dataset),Path(dataset).parent/'manifest.json',root/'plan.json',root/'protocol.json',
        root/'authorization.json',root/'real_manifest.json',REPO/'yolo26n.pt',*input_files]
    for p in (Path(dataset).parent).rglob('*'):
        if p.is_file():paths.append(p)
    paths=sorted(set(Path(p).resolve() for p in paths))
    write(root/'training_source_lock.json',dict(files={str(p):sha(p) for p in paths},
        packages={p:importlib.metadata.version(p) for p in ('torch','ultralytics','numpy','opencv-python')}))
    snapshots=root/'source_snapshot';snapshots.mkdir()
    for p in paths:
        if p.suffix=='.py':shutil.copy2(p,snapshots/p.name)
    verify_sources(root)
    write(root/'state.json',dict(stage='prepared',generation_paused=True,training_started=False,runs=6))
    print('Prepared115 synthetic views, six paired4000-step runs; generation paused',flush=True)


def completed(root,config):
    folder=Path(root)/'training'/config['name'];p=folder/'completion.json'
    if not p.exists():return None
    v=read(p);require(v['completed'] and v['steps']==4000 and v['config']==config,'Run contract mismatch')
    for filename,key in (('weights/best.pt','best_sha256'),('weights/last.pt','last_sha256'),
        ('sampling_sequences.json','sequence_sha256'),('augmentation_decisions.json','augmentation_sha256'),
        ('learning_rates.json','learning_rates_sha256')):
        require(sha(folder/filename)==v[key],'Completed artifact changed: '+filename)
    from appearance_campaign import learning_rate
    require(read(folder/'learning_rates.json')==[learning_rate(i,4000) for i in range(4000)],'LR mismatch')
    ids=read(Path(config['dataset']).parent/'manifest.json')['train_source_ids']
    verify_sequences(config,ids,read(folder/'sampling_sequences.json'),v['exposure'])
    decisions=read(folder/'augmentation_decisions.json')
    require([(r['epoch'],r['slot']) for r in decisions]==[(e,s) for e in range(8) for s in range(1000)],'Missing augmentation slots')
    if config['real_only']:require(v['exposure']=={'real':8000},'Synthetic exposure in baseline')
    require(v['training_source_lock_sha256']==sha(Path(root)/'training_source_lock.json'),'Source lock changed')
    return v


def run(root):
    root=Path(root).resolve()
    with GPUJobLock(root/'controller.lock'):
        generation_paused();verify_sources(root);assert_no_orphans(root)
        write(root/'controller_identity.json',process_identity())
        plan=read(root/'plan.json')
        for c in plan['configs']:
            if completed(root,c):continue
            generation_paused();verify_sources(root);preserve_partial(root,c['name'])
            path=root/'configs'/(c['name']+'.json');write(path,c)
            write(root/'state.json',dict(stage='training',run=c['name'],generation_paused=True,
                completed_runs=sum(completed(root,x) is not None for x in plan['configs']),total_runs=6))
            run_subprocess(root,c['name'],'train_reviewed_augmentation.py',['--config',path],'train')
            require(completed(root,c),'Incomplete run')
        for seed in SEEDS:
            verify_pair(root,f'final_synthetic115_classical_{seed}',f'final_real_classical_{seed}',repeat=True)
        runs={c['name']:completed(root,c) for c in plan['configs']}
        freeze_json(root/'evaluation_lock.json',dict(runs=list(runs),weights={n:r['best_sha256'] for n,r in runs.items()},
            plan_sha256=sha(root/'plan.json'),source_lock_sha256=sha(root/'training_source_lock.json'),
            selection_used_test=False,test_status='development_previously_consulted'))
        if not (root/'evaluation/completion.json').exists():
            write(root/'state.json',dict(stage='evaluation',completed_runs=6,generation_paused=True))
            run_subprocess(root,'evaluation','evaluate_reviewed_augmentation.py',[],'evaluation')
        generation_paused();verify_sources(root)
        write(root/'state.json',dict(stage='pilot_complete_pending_review',completed_runs=6,
            generation_paused=True,automatic_expansion=False,report=str(root/'evaluation/report.md')))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','run'));parser.add_argument('--root',type=Path,default=DEFAULT)
    args=parser.parse_args()
    try:(prepare if args.action=='prepare' else run)(args.root)
    except BaseException as error:
        write(args.root/'controller_failure.json',dict(error=repr(error),traceback=traceback.format_exc(),time=time.time()))
        raise
