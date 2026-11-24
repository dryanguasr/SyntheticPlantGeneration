"""Retest reference and preparation after a measured host-performance change.

One fresh interpretation/audit of the same twelve immutable trees (no new
morphology), then one original-method triplet against the completed optimized
triplet. Workers run sequentially; original outputs remain untouched.
"""
from pathlib import Path
import sys,subprocess,time,shutil,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from uchuva_lsystem.nodal_automation import read,write,sha,awake_seconds
from run_nodal_automation import identity


def worker(blender,command,logs,label):
    start=awake_seconds();child=None
    try:
        with (logs/(label+'.stdout.log')).open('w',encoding='utf-8') as out,(logs/(label+'.stderr.log')).open('w',encoding='utf-8') as err:
            child=subprocess.Popen([blender,'--background','--factory-startup','--python-exit-code','1']+command,
                cwd=ROOT,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
            write(logs/(label+'_process.json'),dict(**identity(child.pid,child._handle),command=command))
            while child.poll() is None:
                if awake_seconds()-start>3600:raise RuntimeError('Bounded retiming job exceeded active-time limit')
                time.sleep(2)
            code=child.returncode;child=None
        write(logs/(label+'_job.json'),dict(exit_code=code,total_process_active_seconds=awake_seconds()-start))
        if code:raise RuntimeError(label+' failed; evidence preserved')
    finally:
        if child is not None and child.poll() is None:child.terminate();child.wait(timeout=20)


def run(campaign,optimized,output,preparation):
    if not read(optimized/'quality_acceptance.json')['numeric_rgb_equivalence']:raise ValueError('Optimized quality gate required')
    if not (optimized/'completion.json').exists():raise ValueError('Optimized worker must finish before retiming')
    output.mkdir(parents=True,exist_ok=False)
    blender=read(campaign/'config.json')['blender']
    try:
        worker(blender,['--python',str(ROOT/'scripts/benchmark_spatial_capture.py'),'--','prepare',str(campaign),str(preparation)],output,'prepare')
        original=read(optimized/'scene_record.json');fresh=read(preparation/'scene_record.json')
        if [(p['seed'],p['plant_sha256']) for p in original['plants']]!=[(p['seed'],p['plant_sha256']) for p in fresh['plants']]:
            raise ValueError('Retimed preparation uses different plant inputs')
        # Timed reconstruction is a workload control; captures still use the
        # exact same saved file as the optimized method, not a new interpretation.
        (output/'dataset').mkdir()
        for name in ('audited_scene.blend','preparation_complete.json','scene_record.json','profiles.json','schedule.json'):
            shutil.copy2(optimized/name,output/name)
        shutil.copy2(optimized/'dataset/config.json',output/'dataset/config.json')
        shutil.copy2(preparation/'prepare_timings.json',output/'prepare_timings.json')
        shutil.copytree(optimized/'optimized',output/'optimized')
        shutil.copytree(optimized/'baseline_repeat',output/'baseline_repeat')
        shutil.copy2(optimized/'optimized_job.json',output/'optimized_job.json')
        files=dict(read(optimized/'benchmark_source_lock.json')['files'])
        paths=[Path(__file__),ROOT/'scripts/summarize_capture_optimization.py']+[output/n for n in
            ('audited_scene.blend','scene_record.json','profiles.json','schedule.json','dataset/config.json','prepare_timings.json')]
        files.update({str(p.resolve()):sha(p) for p in paths})
        write(output/'benchmark_source_lock.json',dict(files=files,variant='host_matched_original_vs_dual_scene',
            optimized_copied_not_rerendered=True,retimed_preparation=str(preparation)))
        worker(blender,['--python',str(ROOT/'scripts/benchmark_spatial_capture.py'),'--','baseline',str(campaign),str(output)],output,'baseline')
        for path,expected in files.items():
            if sha(path)!=expected:raise ValueError('Frozen input changed: '+path)
        from report_capture_benchmark import summarize,pixel_difference
        try:summarize(output)
        except SystemExit:
            if not (output/'comparison.json').exists():raise
        comparison=read(output/'comparison.json');original_acceptance=read(optimized/'quality_acceptance.json')
        exact_keys=('annotations_equal','labels_equal','instances_equal','camera_equal','lighting_equal','geometry_equal')
        numeric=all(all(c[k] for k in exact_keys) and c['mask']['changed_pixels']==0
            and c['rgb']['max_channel_error']<=1 and max(c['rgb']['mean_channel_error'])<=.001 for c in comparison['comparisons'])
        acceptance=dict(original_acceptance,strict_pixel_equal=comparison['strict_equal'],numeric_rgb_equivalence=numeric,
            annotations_exact=all(c['mask']['changed_pixels']==0 and c['annotations_equal'] and c['labels_equal'] for c in comparison['comparisons']),
            matched_reference_self_repeat=pixel_difference(output/'baseline/view_000/rgb.png',output/'baseline_repeat/rgb.png'))
        write(output/'quality_acceptance.json',acceptance)
        if not numeric:raise RuntimeError('Matched test failed exact annotations/bounded RGB quality')
        from summarize_capture_optimization import main
        main(output,output)
        write(output/'completion.json',dict(status='complete',new_rgb_images=3,no_new_morphology=True,
            optimized_copied_not_rerendered=True,production_dataset_images=144,training_started=False))
    except BaseException:
        write(output/'failure.json',dict(traceback=traceback.format_exc()));raise


if __name__=='__main__':run(*[Path(p).resolve() for p in sys.argv[1:]])
