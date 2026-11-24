"""Supervise one owned GPU worker until the combined bank reaches 1,000.

No new morphology, no training, no rewrite/reset of the historical budget.
Closed checkpoints and per-view commits permit hash-compatible recovery.
"""
from pathlib import Path
from datetime import datetime,timezone
import sys,os,ctypes,subprocess,time,traceback,shutil
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from uchuva_lsystem.nodal_automation import read,write,sha,awake_seconds
from uchuva_lsystem.spatial_dataset import committed_views
from uchuva_lsystem.dataset_completion import (process_identity,owner_alive,verify_sources,
    verify_pool,baseline_rows,new_rows,preserve_unbuilt,publish_index)
from report_dataset_completion import update


def prepare(source,root):
    if root.exists():verify_sources(root);return
    original=read(source/'dataset/source_lock.json')
    for filename,expected in original['files'].items():
        if sha(filename)!=expected:raise ValueError('Historical source/input changed: '+filename)
    pool=verify_pool(source);rows=committed_views(source/'dataset')
    if len(rows)!=144:raise ValueError('Expected the preserved 144-image bank')
    if not read(ROOT/'outputs/capture_optimization_matched_20261029/quality_acceptance.json')['numeric_rgb_equivalence']:
        raise ValueError('Optimized capture has not passed its quality gate')
    root.mkdir(parents=True,exist_ok=False);bank=root/'dataset';bank.mkdir()
    first=max(int(p.name.split('_')[-1]) for p in (source/'dataset/scenes').glob('scene_*'))+1
    config=read(source/'dataset/config.json');config.update(max_images=1000-len(rows),first_scene_index=first,
        generation_variant='earthen_floor_v9_matte_continuous_distance',global_budget=str(root/'budget.json'))
    config.pop('global_budget_sha256',None)
    horizon=bank/'horizon_assets'
    subprocess.run([read(source/'config.json')['blender'],'--background','--factory-startup',
        '--python-exit-code','1','--python',str(ROOT/'scripts/prepare_capture_horizon_assets.py'),
        '--',str(Path(config['asset_dir'])/'farmland_overcast_2k.hdr'),str(horizon)],
        check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
    config['horizon_assets_manifest']=str((horizon/'manifest.json').resolve())
    write(bank/'config.json',config);write(bank/'pool_lock.json',dict(plants=pool))
    write(root/'profiles.json',read(source/'profiles.json'))
    write(root/'config.json',dict(version='optimized-completion/1',source_campaign=str(source),target_total=1000,
        inherited_count=len(rows),new_target=1000-len(rows),worker= str(ROOT/'scripts/render_dataset_completion.py'),
        blender=read(source/'config.json')['blender'],worker_safety_active_seconds=7200,
        training_authorized=False,sample_review_before_training=True,monitor_interval_minutes=60))
    write(root/'authorization.json',dict(date=datetime.now(timezone.utc).isoformat(),
        instruction='Completa las1000imágenes con versión optimizada y seguimiento cada hora. Conserva plantas válidas y muestra muestras antes de piloto.',
        target_total=1000,generate_new_plants=False,modify_valid_plants=False,training_authorized=False,
        historical_budgets_unchanged=True,explicit_new_time_limit=None))
    write(root/'phase_policy.json',dict(phase='optimized_generation_only',target_total=1000,
        inherited_images=144,new_images=856,first_new_scene_index=first,valid_plant_pool=20,
        architecture_changes_allowed=False,training_authorized=False,human_samples_required_before_pilot=True,
        monitor_interval_minutes=60,physical_admission='unchanged: zero audited hard crossings, ground1mm, orientation/attachment valid'))
    write(root/'budget.json',dict(schema='uchuva.goal_limited_capture/1',awake_started_seconds=awake_seconds(),
        limit_active_seconds=None,stop_rule='1000 verified combined images; no user-imposed new time ceiling',
        planning_estimate_additional_active_hours=[18,22],native_clock_excludes_suspension=True,
        historical_budget_sha256=sha(source/'budget.json')))
    inherited=[]
    for row in rows:
        p=source/'dataset/views'/row['view_id']/'view.json'
        entry={k:row[k] for k in ('view_id','scene_id','image','mask','label','image_sha256','mask_sha256','label_sha256')}
        entry.update(view_record=str(p),view_record_sha256=sha(p));inherited.append(entry)
    write(root/'baseline_lock.json',dict(source_dataset=str(source/'dataset'),views=inherited,
        excluded_historical_views=read(source/'dataset/excluded_views.json')['view_ids']))
    own=[Path(__file__),ROOT/'scripts/render_dataset_completion.py',ROOT/'scripts/report_dataset_completion.py',
        ROOT/'scripts/prepare_capture_horizon_assets.py',horizon/'manifest.json',
        horizon/'landscape_clean.exr',horizon/'sky_matte.png',
        ROOT/'scripts/render_spatial_dataset_optimized.py',ROOT/'scripts/run_nodal_automation.py']
    own += [ROOT/'src/uchuva_lsystem'/n for n in ('dataset_completion.py','capture_plan.py','capture_conditions.py',
        'mask_arrays.py','blender_capture_optimized.py','blender_capture_dual_scene.py',
        'capture_skies.py','blender_capture_skies.py','continuous_capture_distance.py','horizon_matte.py')]
    own += [root/n for n in ('config.json','authorization.json','phase_policy.json','budget.json','baseline_lock.json','profiles.json')]
    own += [bank/'config.json',bank/'pool_lock.json']
    files=dict(original['files']);files.update({str(p.resolve()):sha(p) for p in own})
    lock=dict(files=files,version='optimized-completion-source/1',historical_source_lock_sha256=sha(source/'dataset/source_lock.json'))
    write(root/'source_lock.json',lock);write(bank/'source_lock.json',lock)
    publish_index(root,[])
    write(root/'state.json',dict(status='prepared',complete_images=144,optimized_images=0,
        first_scene_index=first,training_started=False,human_sample_review='pending'))


def acquire(root):
    lock=root/'controller.lock'
    if lock.exists():
        old=read(lock)
        if owner_alive(old):raise RuntimeError('Controller with matching native identity already active')
        target=root/'recovery'/('obsolete_lock_'+str(time.time_ns())+'.json');target.parent.mkdir(exist_ok=True)
        lock.rename(target)
    with lock.open('x',encoding='utf-8') as f:
        import json
        f.write(json.dumps(process_identity()))
    write(root/'controller_identity.json',process_identity())
    return lock


def review_pause_active(root):
    flag=Path(root)/'pause_requested.json'
    return flag.exists() and read(flag).get('active',True)


def run(source,root):
    if review_pause_active(root):
        print('User review pause active; no generation or training started',flush=True);return
    prepare(source,root);lock=acquire(root);child=None
    try:
        if (root/'controller_failure.json').exists():
            archive=root/'recovery'/('previous_failure_'+str(time.time_ns())+'.json');archive.parent.mkdir(exist_ok=True)
            (root/'controller_failure.json').rename(archive)
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
        verify_sources(root);baseline_rows(root);verify_pool(source)
        # A prior owner can disappear without killing its worker. Adopt that
        # exact owned identity; never start another GPU worker beside it.
        for p in sorted((root/'jobs').glob('job_*/process.json')):
            if (p.parent/'exit.json').exists():continue
            record=read(p)
            while owner_alive(record):
                write(root/'controller_heartbeat.json',dict(stage='adopting_existing_worker',job=str(p.parent),identity=record))
                time.sleep(5)
            write(p.parent/'exit.json',dict(owner_recovered=True,result_exists=(p.parent/'result.json').exists()))
        rejection_streak=0
        while True:
            verify_sources(root);rows=new_rows(root);count=publish_index(root,rows)
            if review_pause_active(root):
                write(root/'state.json',dict(status='paused_for_diversity_review',complete_images=count,
                    optimized_images=len(rows),training_started=False,human_sample_review='pending'));return
            if count==1000:
                summary=update(root,final=True)
                write(root/'state.json',dict(status='awaiting_user_sample_review',**summary,
                    native_awake_span_seconds=awake_seconds()-read(root/'budget.json')['awake_started_seconds']))
                write(root/'completion.json',dict(complete_images=count,training_started=False,
                    human_sample_review='pending',sample_gallery=str(root/'review.html')));return
            cycle=max([int(p.name.split('_')[-1]) for p in (root/'jobs').glob('job_*')],default=-1)+1
            job=root/'jobs'/f'job_{cycle:03d}';job.mkdir(parents=True,exist_ok=False)
            preserve_unbuilt(root,job/'construction_preserved')
            # Verify all raw prefix pairs before resuming a checkpoint.
            new_rows(root,closed_only=False)
            config=read(root/'config.json');command=[config['blender'],'--background','--factory-startup',
                '--python-exit-code','1','--python',config['worker'],'--',str(root),str(job)]
            started=awake_seconds();write(job/'start.json',dict(awake_seconds=started,complete_before=count))
            with (job/'stdout.log').open('w',encoding='utf-8') as out,(job/'stderr.log').open('w',encoding='utf-8') as err:
                child=subprocess.Popen(command,cwd=ROOT,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
                record=dict(**process_identity(child.pid,child._handle),command=command)
                write(job/'process.json',record);write(root/'worker_identity.json',record)
                write(root/'state.json',dict(status='running',complete_images=count,optimized_images=len(rows),
                    current_job=str(job),training_started=False,human_sample_review='pending'))
                while child.poll() is None:
                    if awake_seconds()-started>config['worker_safety_active_seconds']:
                        child.terminate();child.wait(timeout=20);raise RuntimeError('Owned worker safety timeout; checkpoint preserved')
                    write(root/'controller_heartbeat.json',dict(stage='running',current_job=str(job),identity=record,
                        job_active_seconds=awake_seconds()-started,verified_images=count))
                    time.sleep(5)
                code=child.returncode;child=None
            write(job/'exit.json',dict(exit_code=code,active_seconds=awake_seconds()-started))
            if code:raise RuntimeError('Worker failed; preserve partials and diagnose '+str(job))
            result=read(job/'result.json')
            rejection_streak=rejection_streak+1 if result['status']=='scene_rejected' else 0
            if rejection_streak>=2:raise RuntimeError('Two physical scene rejections; diagnosis required, no relaxed admission')
            update(root)
    except Exception:
        write(root/'controller_failure.json',dict(traceback=traceback.format_exc()))
        raise
    finally:
        if child is not None and child.poll() is None:child.terminate();child.wait(timeout=20)
        lock.unlink(missing_ok=True);ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


if __name__=='__main__':run(*[Path(p).resolve() for p in sys.argv[1:]])
