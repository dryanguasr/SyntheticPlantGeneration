"""Own sequential benchmark workers; no continuation of a production campaign."""
from pathlib import Path
import sys
import os
import subprocess
import time
import traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from uchuva_lsystem.nodal_automation import read,write,sha,awake_seconds
from uchuva_lsystem.capture_plan import condition_for_view,profiles_for_condition
from uchuva_lsystem.appearance_profiles import resolved_profile
from run_nodal_automation import identity


def run(campaign,output):
    if not (output/'preparation_complete.json').exists():raise ValueError('Audited prepare phase must finish first')
    lockpath=output/'benchmark.lock'
    handle=os.open(lockpath,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    os.write(handle,str(os.getpid()).encode());os.close(handle)
    child=None;started=awake_seconds()
    try:
        prepared=read(output/'preparation_complete.json')
        if sha(output/'audited_scene.blend')!=prepared['scene_sha256']:raise ValueError('Saved scene changed')
        schedule=read(output/'schedule.json');profiles=read(output/'profiles.json')
        for row in schedule:
            condition=condition_for_view(13,row['index'])
            # Preserve a separate range of depths while exercising light reuse.
            row['condition']=condition;row['diagnostic_light']=condition['diagnostic_light']
            p,light=profiles_for_condition(profiles,condition);row['lighting']=resolved_profile(p,'LT',light)
        write(output/'schedule.json',schedule)
        prepared['schedule_sha256']=sha(output/'schedule.json');write(output/'preparation_complete.json',prepared)
        source=read(campaign/'dataset/source_lock.json')
        files=dict(source['files'])
        additional=[ROOT/'scripts/benchmark_spatial_capture.py',ROOT/'scripts/run_capture_benchmark.py',
            ROOT/'scripts/report_capture_benchmark.py',ROOT/'scripts/render_spatial_dataset_optimized.py',
            ROOT/'scripts/audit_saved_capture_scene.py',
            ROOT/'src/uchuva_lsystem/blender_capture_optimized.py',ROOT/'src/uchuva_lsystem/capture_plan.py',
            ROOT/'src/uchuva_lsystem/mask_arrays.py',
            output/'audited_scene.blend',output/'schedule.json',output/'scene_record.json',output/'profiles.json']
        if (output/'revisions/reloaded_scene_audit/complete.json').exists():
            additional.extend((output/'revisions/reloaded_scene_audit'/name) for name in
                ('complete.json','camera_invariance.json','mesh.json','ground.json','orientation.json'))
        files.update({str(p.resolve()):sha(p) for p in additional})
        write(output/'benchmark_source_lock.json',dict(files=files,source_campaign=str(campaign),
            source_lock_sha256=sha(campaign/'dataset/source_lock.json'),training_started=False))
        blender=read(campaign/'config.json')['blender']
        for mode in ('baseline','optimized'):
            command=[blender,'--background','--factory-startup','--python-exit-code','1','--python',
                     str(ROOT/'scripts/benchmark_spatial_capture.py'),'--',mode,str(campaign),str(output)]
            with (output/(mode+'.stdout.log')).open('w',encoding='utf-8') as out,(output/(mode+'.stderr.log')).open('w',encoding='utf-8') as err:
                job_start=awake_seconds()
                child=subprocess.Popen(command,cwd=ROOT,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
                write(output/(mode+'_process.json'),dict(**identity(child.pid,child._handle),command=command))
                while child.poll() is None:
                    if awake_seconds()-started>3600:
                        child.terminate();child.wait(timeout=20);raise RuntimeError('Small benchmark active-time safety limit reached')
                    time.sleep(2)
                code=child.returncode;child=None
            write(output/(mode+'_job.json'),dict(exit_code=code,total_process_active_seconds=awake_seconds()-job_start))
            if code:raise RuntimeError(mode+' worker failed; preserved logs')
        for path,expected in files.items():
            if sha(path)!=expected:raise ValueError('Benchmark source/input changed: '+path)
        from report_capture_benchmark import summarize
        summarize(output)
        write(output/'completion.json',dict(status='complete',active_seconds=awake_seconds()-started,
              training_started=False,new_rgb_images=6,production_campaign_unchanged=True))
    except BaseException:
        write(output/'supervisor_failure.json',dict(traceback=traceback.format_exc()));raise
    finally:
        if child is not None and child.poll() is None:
            child.terminate();child.wait(timeout=20)
        lockpath.unlink()


if __name__=='__main__':run(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
