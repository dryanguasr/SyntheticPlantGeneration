"""Resume the frozen dataset only; never revisit historical plant-process PIDs.

Recycle the owned Blender child at completed image blocks to bound retained
memory. Inputs, generation recipe, global awake clock and committed views stay
unchanged. Only incomplete folders created by that child may be archived.
"""
from pathlib import Path
import ctypes
import json
import subprocess
import sys
import time
import traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from uchuva_lsystem.nodal_automation import read,write,sha,remaining,active_elapsed
from uchuva_lsystem.spatial_dataset import admitted_pool,committed_views
from run_nodal_automation import identity


def verify_bank(root):
    root=Path(root);bank=root/'dataset';lock=read(bank/'source_lock.json')
    for path,expected in lock['files'].items():
        if sha(path)!=expected:raise ValueError('Incompatible frozen input: '+path)
    pool=read(bank/'pool_lock.json')['plants']
    if len(pool)!=20 or len({p['seed'] for p in pool})!=20:
        raise ValueError('Twenty distinct frozen plants required')
    for p in pool:
        if sha(p['plant'])!=p['plant_sha256']:raise ValueError('Frozen tree differs')
    return bank,pool


def archive_incomplete(root,bank,before,views,folder):
    """Only new, uncommitted scene folders; never move a committed image."""
    represented={v['scene_id'] for v in views}
    for scene in sorted((bank/'scenes').glob('scene_*')):
        if scene.name in before or scene.name in represented:continue
        paths=[scene]+list((bank/'views').glob(scene.name+'_view_*'))
        for source in paths:
            target=folder/source.parent.name/source.name
            if root not in source.resolve().parents or root not in target.resolve().parents:
                raise ValueError('Archive path is outside the campaign')
            if source.parent.name=='views' and (source/'view.json').exists() and read(source/'view.json').get('status')=='complete':
                raise ValueError('Cannot relocate a committed view')
            target.parent.mkdir(parents=True,exist_ok=True);source.rename(target)


def run(root,revision,chunk_images=24):
    bank,pool=verify_bank(root);budget=read(root/'budget.json');config=read(bank/'config.json')
    # The initial plant handoff already stopped all owned generation processes.
    # A frozen pool and actual audits replace querying those now reusable PIDs.
    if not (root/'plant_pool_complete.json').exists():raise ValueError('Completed plant handoff required')
    if len(admitted_pool(root,read(root/'results.json')['rows']))!=20:raise ValueError('Plant audits differ')
    own=revision/'dataset_resume_source_lock.json'
    def verify_controller():
        expected=read(own)
        if sha(__file__)!=expected['controller_sha256'] or sha(bank/'source_lock.json')!=expected['dataset_source_lock_sha256']:
            raise ValueError('Resume controller or frozen dataset lock changed')
    verify_controller()
    child=None;timed_out=False
    cycle=max([int(p.name.split('_')[-1]) for p in (revision/'dataset_process_cycles').glob('cycle_*')],default=-1)+1
    views=committed_views(bank)
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
        while remaining(budget)>180 and len(views)<config['max_images']:
            verify_bank(root)
            verify_controller()
            folder=revision/'dataset_process_cycles'/f'cycle_{cycle:03d}';folder.mkdir(parents=True,exist_ok=False)
            before={p.name for p in (bank/'scenes').glob('scene_*')};start_count=len(views);recycled=False
            command=[read(root/'config.json')['blender'],'--background','--factory-startup','--python-exit-code','1',
                     '--python',str(ROOT/'scripts/render_spatial_dataset.py'),'--',str(root)]
            with (folder/'stdout.log').open('w',encoding='utf-8') as out,(folder/'stderr.log').open('w',encoding='utf-8') as err:
                child=subprocess.Popen(command,cwd=ROOT,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
                record=dict(**identity(child.pid,child._handle),command=command,cycle=cycle)
                write(bank/'process.json',record);write(folder/'process.json',record)
                write(root/'state.json',dict(status='running',stage='dataset_generation',valid_new_plants=20,
                    complete_images=len(views),training_started=False,active_seconds=active_elapsed(budget),remaining_seconds=remaining(budget)))
                while child.poll() is None:
                    state=read(bank/'state.json') if (bank/'state.json').exists() else {}
                    # Old state must not trigger a recycle before this child commits.
                    count=state.get('committed_images',start_count)
                    if remaining(budget)<=0 or count>=start_count+chunk_images:
                        timed_out=remaining(budget)<=0;recycled=not timed_out
                        child.terminate()
                        try:child.wait(timeout=15)
                        except subprocess.TimeoutExpired:child.kill();child.wait()
                        break
                    time.sleep(2)
                code=child.returncode;child=None
            views=committed_views(bank)
            write(folder/'completion.json',dict(exit_code=code,recycled=recycled,timed_out=timed_out,complete_images=len(views)))
            if recycled:
                archive_incomplete(root,bank,before,views,folder/'incomplete_preserved')
                cycle+=1;continue
            if code and not timed_out:raise RuntimeError('Dataset child failed; see '+str(folder))
            break
        verify_bank(root)
        write(bank/'manifest.json',dict(views=views,complete_images=len(views),training_started=False,partials_preserved=True,twenty_admitted_plants=True))
        state=dict(status='complete',stage='dataset_generation_finished',valid_new_plants=20,complete_images=len(views),
            active_seconds=active_elapsed(budget),remaining_seconds=remaining(budget),training_started=False,
            stop_reason='image_target_reached' if len(views)>=config['max_images'] else 'global_active_limit' if timed_out else 'insufficient_time_for_next_complete_scene',
            dataset_generated=bool(views),human_visual_review='pending')
        write(root/'state.json',state);write(revision/'state.json',state);write(root/'closure.json',state)
    except Exception:
        if child and child.poll() is None:child.terminate();child.wait()
        write(revision/'dataset_resume_failure.json',dict(traceback=traceback.format_exc(),active_seconds=active_elapsed(budget)))
        raise
    finally:ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


if __name__=='__main__':
    root=Path(sys.argv[1]).resolve();revision=Path(sys.argv[2]).resolve()
    handle=(revision/'supervisor.lock').open('x',encoding='utf-8')
    handle.write(json.dumps(identity()));handle.flush();write(revision/'supervisor_identity.json',identity())
    try:run(root,revision)
    finally:handle.close();(revision/'supervisor.lock').unlink(missing_ok=True)
