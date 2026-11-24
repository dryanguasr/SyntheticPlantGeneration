"""One extra optimized triplet after the first paired benchmark has finished."""
from pathlib import Path
import sys,subprocess,time,shutil,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from uchuva_lsystem.nodal_automation import read,write,sha,awake_seconds
from run_nodal_automation import identity


def run(campaign,source,output):
    controller_sha=sha(__file__)
    # Recovery uses the already-complete baseline. The interrupted optimized
    # triplet is preserved separately and is not counted as a completed trial.
    if not (source/'baseline/complete.json').exists():raise ValueError('Completed baseline required')
    if len(read(source/'baseline/complete.json')['views'])!=3:raise ValueError('Three complete reference views required')
    if sha(__file__)!=controller_sha:raise ValueError('Controller changed while waiting')
    output.mkdir(parents=True,exist_ok=False)
    (output/'dataset').mkdir()
    for name in ('audited_scene.blend','preparation_complete.json','scene_record.json','profiles.json','schedule.json'):
        shutil.copy2(source/name,output/name)
    shutil.copy2(source/'dataset/config.json',output/'dataset/config.json')
    shutil.copytree(source/'baseline',output/'baseline')
    shutil.copy2(source/'baseline_job.json',output/'baseline_job.json')
    shutil.copy2(source/'prepare_timings.json',output/'prepare_timings.json')
    files=dict(read(source/'benchmark_source_lock.json')['files'])
    additional=[Path(__file__),ROOT/'scripts/benchmark_capture_dual_scene.py',
        ROOT/'src/uchuva_lsystem/blender_capture_dual_scene.py']
    additional += [output/name for name in ('audited_scene.blend','scene_record.json','profiles.json','schedule.json')]
    files.update({str(p.resolve()):sha(p) for p in additional})
    write(output/'benchmark_source_lock.json',dict(files=files,variant='dual_scene_shared_objects_persistent_cycles',
        baseline_source=str(source),baseline_copied_not_rerendered=True))
    blender=read(campaign/'config.json')['blender']
    command=[blender,'--background','--factory-startup','--python-exit-code','1','--python',
             str(ROOT/'scripts/benchmark_capture_dual_scene.py'),'--',str(campaign),str(output)]
    child=None
    try:
        started=awake_seconds()
        with (output/'optimized.stdout.log').open('w',encoding='utf-8') as out,(output/'optimized.stderr.log').open('w',encoding='utf-8') as err:
            child=subprocess.Popen(command,cwd=ROOT,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
            write(output/'optimized_process.json',dict(**identity(child.pid,child._handle),command=command))
            while child.poll() is None:
                if awake_seconds()-started>2400:
                    child.terminate();child.wait(timeout=20);raise RuntimeError('Additional triplet safety limit reached')
                time.sleep(2)
            code=child.returncode;child=None
        write(output/'optimized_job.json',dict(exit_code=code,total_process_active_seconds=awake_seconds()-started))
        if code:raise RuntimeError('Dual-scene variant failed; sources and outputs preserved')
        for path,expected in files.items():
            if sha(path)!=expected:raise ValueError('Frozen source/input changed: '+path)
        from report_capture_benchmark import summarize,pixel_difference
        try:summarize(output)
        except SystemExit:
            if not (output/'comparison.json').exists():raise
        comparison=read(output/'comparison.json')
        repeat=pixel_difference(output/'baseline/view_000/rgb.png',output/'baseline_repeat/rgb.png')
        # Explicit numerical equivalence criterion, not a botanical or physical
        # tolerance: <=1 byte level and <=0.001 byte mean error per RGB channel.
        # Exact equality remains mandatory for all annotations and scene inputs.
        exact_keys=('annotations_equal','labels_equal','instances_equal','camera_equal','lighting_equal','geometry_equal')
        numeric=all(all(c[k] for k in exact_keys) and c['mask']['changed_pixels']==0
                    and c['rgb']['max_channel_error']<=1
                    and max(c['rgb']['mean_channel_error'])<=.001 for c in comparison['comparisons'])
        write(output/'quality_acceptance.json',dict(strict_pixel_equal=comparison['strict_equal'],
            numeric_rgb_equivalence=numeric,annotations_exact=all(c['mask']['changed_pixels']==0 and
            c['annotations_equal'] and c['labels_equal'] for c in comparison['comparisons']),
            baseline_self_repeat=repeat,criterion=dict(max_rgb_byte_error=1,max_mean_rgb_byte_error_per_channel=.001),
            criterion_provenance='engineering numerical-equivalence criterion; no physical/annotation tolerance changed',
            no_resolution_samples_or_denoising_changes=True))
        if not numeric:raise RuntimeError('Dual variant failed exact annotations or bounded RGB equivalence')
        write(output/'completion.json',dict(status='complete',new_rgb_images=4,baseline_copied_not_rerendered=True,
              active_seconds=awake_seconds()-started,training_started=False))
    except BaseException:
        write(output/'failure.json',dict(traceback=traceback.format_exc()));raise
    finally:
        if child is not None and child.poll() is None:child.terminate();child.wait(timeout=20)


if __name__=='__main__':run(*[Path(p).resolve() for p in sys.argv[1:]])
