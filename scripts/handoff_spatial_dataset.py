"""External conditional phase supervisor; frozen plant workers stay unchanged.

At twenty independently admitted plants, stop only recorded matching process
identities, freeze the pool, and use only the original remaining awake budget.
"""
from pathlib import Path
from datetime import datetime,timezone
import ctypes
from ctypes import wintypes
import json
import shutil
import subprocess
import sys
import time
import traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'))
from uchuva_lsystem.nodal_automation import read,write,sha,remaining,active_elapsed,unique_admissions
from uchuva_lsystem.spatial_dataset import admitted_pool,committed_views
from run_nodal_automation import identity


def stop_recorded(record):
    """Terminate only a PID whose native creation tick matches our saved record."""
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];k.OpenProcess.restype=wintypes.HANDLE
    k.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(ctypes.c_ulonglong)]*4
    k.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT]
    k.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];k.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=k.OpenProcess(0x1000|1|0x100000,False,record['pid'])
    if not handle:
        error=ctypes.get_last_error()
        if error==87:return dict(pid=record['pid'],status='already_absent')
        raise OSError(error,'Cannot inspect/stop owned phase process')
    try:
        t=[ctypes.c_ulonglong() for _ in range(4)]
        if not k.GetProcessTimes(handle,*[ctypes.byref(v) for v in t]):raise OSError('Process identity query failed')
        if t[0].value!=record['creation_tick']:return dict(pid=record['pid'],status='pid_reused_not_touched')
        if t[1].value:return dict(pid=record['pid'],status='already_exited')
        if not k.TerminateProcess(handle,0):raise OSError('Owned process termination failed')
        if k.WaitForSingleObject(handle,15000)!=0:raise TimeoutError('Owned process did not stop')
        return dict(pid=record['pid'],creation_tick=record['creation_tick'],status='stopped_owned_identity')
    finally:k.CloseHandle(handle)


def pool_rows(root):
    rows=read(root/'results.json')['rows'] if (root/'results.json').exists() else []
    seen={r['seed'] for r in rows};origin={r['seed']:r['origin'] for r in read(root/'queue.json')}
    for p in sorted((root/'plants').glob('*/admission.json')):
        row=read(p)
        if row['seed'] in seen:continue
        row['origin']=origin.get(row['seed'],'fresh_seed_after_ranked_queue');rows.append(row);seen.add(row['seed'])
    return rows


def stop_plant_phase(root,revision):
    saved=read(root/'state.json');write(revision/'plant_state_before_stop.json',saved)
    stopped=[stop_recorded(read(root/'controller_identity.json'))]
    for p in (root/'plants').glob('*/process.json'):stopped.append(stop_recorded(read(p)))
    write(revision/'stopped_identities.json',stopped)
    lock=root/'controller.lock'
    if lock.exists():lock.rename(revision/'stopped_plant_controller.lock')


def freeze_pool(root,plants):
    bank=root/'dataset';bank.mkdir(exist_ok=True);locked=[]
    for p in plants:
        target=bank/'inputs'/f'seed_{p["seed"]}.json';target.parent.mkdir(exist_ok=True)
        if target.exists():
            if sha(target)!=p['plant_sha256']:raise ValueError('Frozen pool tree differs')
        else:shutil.copy2(p['plant'],target)
        locked.append(dict(p,plant=str(target.resolve())))
    write(bank/'pool_lock.json',dict(plants=locked,count=20,selection='first20independently admitted unique plants',
        source_pool_lock_sha256=sha(root/'source_lock.json'),training_authorized=False))
    policy=read(root/'phase_policy.json')
    write(bank/'config.json',dict(max_images=1000,views_per_scene=policy.get('dataset_views_per_scene',60),plants_per_scene=policy.get('dataset_plants_per_scene',4),
        crop_gap_bu=policy.get('dataset_crop_gap_bu',3.),extra_weed_centres=policy.get('dataset_extra_weeds',False),
        context_modes=policy.get('dataset_context_modes',read(root/'profiles.json')['context']['modes']),
        generation_variant=policy.get('dataset_generation_variant','four_plant_open_context_v1'),
        columns=policy.get('dataset_columns',4),
        support_modes=policy.get('dataset_support_modes',['horizontal']),
        asset_dir=policy.get('dataset_asset_dir'),
        foreground_targets=policy.get('dataset_foreground_targets',False),
        interior_targets=policy.get('dataset_interior_targets',False),
        textured_soil=policy.get('dataset_textured_soil',False),
        natural_floor=policy.get('dataset_natural_floor',False),
        depth_strata=['near','middle','far'],image_size=[960,720],min_free_bytes=1073741824,
        physical_scope='same strict crop audit; flat contextual ground; no further plant thinning',
        global_budget=str(root/'budget.json'),global_budget_sha256=sha(root/'budget.json')))
    sources=list((ROOT/'src/uchuva_lsystem').glob('*.py'))+[ROOT/'scripts'/n for n in
        ['render_spatial_dataset.py','handoff_spatial_dataset.py','render_appearance_bank.py','appearance_campaign.py','run_nodal_automation.py']]
    inputs=[bank/'pool_lock.json',bank/'config.json',root/'profiles.json',root/'budget.json']+[Path(p['plant']) for p in locked]
    if (bank/'excluded_views.json').exists():inputs.append(bank/'excluded_views.json')
    if policy.get('dataset_asset_dir'):inputs+=list(Path(policy['dataset_asset_dir']).glob('*'))
    lock={str(p.resolve()):sha(p) for p in sources+inputs}
    write(bank/'source_lock.json',dict(files=lock))
    for p in sources:
        target=bank/'frozen_source'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    return bank


def main(root,revision):
    write(revision/'supervisor_identity.json',identity());budget=read(root/'budget.json')
    phase_lock=read(revision/'source_lock.json')
    def verify():
        for p,h in phase_lock['files'].items():
            if sha(p)!=h:raise ValueError('Transition source/policy changed: '+p)
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    child=None
    try:
        while remaining(budget)>0:
            verify();rows=pool_rows(root);plants=admitted_pool(root,rows)
            write(revision/'state.json',dict(stage='waiting_for20',valid_plants=len(unique_admissions(rows)),remaining_seconds=remaining(budget)))
            if plants:break
            if (root/'controller_failure.json').exists():raise RuntimeError('Plant controller requires diagnosis before phase handoff')
            time.sleep(1)
        else:
            write(revision/'state.json',dict(stage='complete',dataset_started=False,reason='global_budget_expired_before20'))
            return
        # No dataset work overlaps a recorded live plant-generation process.
        stop_plant_phase(root,revision)
        rows=pool_rows(root);plants=admitted_pool(root,rows)
        if len(plants)!=20:raise ValueError('Twenty independent admissions required after stopping phase')
        write(root/'results.json',dict(rows=rows,valid_new_plants=len(unique_admissions(rows)),training_started=False,dataset_generated=False))
        write(root/'plant_pool_complete.json',dict(status='complete',reason='20_valid_plants_reached',plants=plants,
            active_seconds=active_elapsed(budget),remaining_seconds=remaining(budget),global_budget_sha256=sha(root/'budget.json')))
        bank=freeze_pool(root,plants);verify()
        command=[read(root/'config.json')['blender'],'--background','--factory-startup','--python-exit-code','1',
                 '--python',str(ROOT/'scripts/render_spatial_dataset.py'),'--',str(root)]
        write(root/'state.json',dict(status='running',stage='dataset_generation',valid_new_plants=20,
              active_seconds=active_elapsed(budget),remaining_seconds=remaining(budget),training_started=False))
        with (bank/'stdout.log').open('w',encoding='utf-8') as out,(bank/'stderr.log').open('w',encoding='utf-8') as err:
            child=subprocess.Popen(command,cwd=ROOT,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
            write(bank/'process.json',dict(**identity(child.pid,child._handle),command=command));terminated=False
            while child.poll() is None:
                if remaining(budget)<=0:
                    child.terminate()
                    try:child.wait(timeout=10)
                    except subprocess.TimeoutExpired:child.kill();child.wait()
                    terminated=True;break
                time.sleep(2)
            code=child.returncode;child=None
        views=committed_views(bank)
        write(bank/'manifest.json',dict(views=views,complete_images=len(views),training_started=False,
            partials_preserved=True,twenty_admitted_plants=True))
        state=dict(status='complete' if code==0 or terminated else 'needs_attention',stage='dataset_generation_finished',
            valid_new_plants=20,complete_images=len(views),active_seconds=active_elapsed(budget),remaining_seconds=remaining(budget),
            stop_reason='global_active_limit' if terminated else 'dataset_worker_finished',worker_exit_code=code,training_started=False,
            dataset_generated=bool(views),human_visual_review='pending')
        write(root/'state.json',state);write(revision/'state.json',state)
        if state['status']=='complete':write(root/'closure.json',state)
        else:raise RuntimeError('Dataset worker failed; preserve scenes and committed views')
    except Exception:
        if child and child.poll() is None:child.terminate();child.wait()
        write(revision/'failure.json',dict(traceback=traceback.format_exc(),active_seconds=active_elapsed(budget)))
        raise
    finally:ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


if __name__=='__main__':
    root=Path(sys.argv[1]).resolve();revision=Path(sys.argv[2]).resolve()
    # A stale lock requires identity-based recovery, never blind removal.
    handle=(revision/'supervisor.lock').open('x',encoding='utf-8')
    handle.write(json.dumps(identity()));handle.flush()
    try:main(root,revision)
    finally:
        handle.close();(revision/'supervisor.lock').unlink(missing_ok=True)
