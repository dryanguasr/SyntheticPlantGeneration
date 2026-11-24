"""Explicit dual-scene variant of the admitted-tree capture entrypoint.

Blender --python this.py -- CAMPAIGN NEW_OUTPUT ACTIVE_SECONDS MAX_IMAGES
One scene per worker; a calling supervisor must recycle workers and enforce
the same deadline. No campaign is launched by importing this module.
"""
from pathlib import Path
import sys,ctypes,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import render_spatial_dataset_optimized as renderer
from uchuva_lsystem.blender_capture_dual_scene import DualSceneCaptureSession
from uchuva_lsystem.capture_conditions import balanced_condition_for_view
from uchuva_lsystem.nodal_automation import read,write,sha


def run(campaign,output,seconds,images):
    fresh=not output.exists()
    renderer.prepare(campaign,output,seconds,images)
    variant=output/'capture_variant.json'
    bank=output/'dataset'
    paths=[Path(__file__).resolve(),ROOT/'src/uchuva_lsystem/blender_capture_dual_scene.py',
           ROOT/'src/uchuva_lsystem/capture_conditions.py']
    if fresh:
        write(variant,dict(version='admitted-capture/7',variant='dual_scene_shared_objects_persistent_cycles',
            capture_seed=20261029,plants_modified=False,objects_shared_with_mask=True,
            light_schedule='balanced_depth_light/2; all depths receive all three reviewed lighting profiles',
            resolution=[960,720],samples=12,denoising=True,no_training=True,
            required_supervision='one GPU worker, recycle each complete scene, hard native-awake deadline'))
        config=read(bank/'config.json')
        config.update(generation_variant='earthen_floor_v7_shared_geometry_capture',
                      global_budget=str(output/'budget.json'),global_budget_sha256=sha(output/'budget.json'))
        write(bank/'config.json',config)
        lock=read(bank/'source_lock.json')
        for path in paths+[variant,bank/'config.json']:lock['files'][str(path.resolve())]=sha(path)
        write(bank/'source_lock.json',lock)
    elif not variant.exists() or read(variant).get('version')!='admitted-capture/7':
        raise ValueError('Cannot mix a different capture variant into an existing output')
    # Explicit runtime dependency selection; the frozen historical renderer and
    # botanical model are untouched. The selected sources are in this bank lock.
    previous=renderer.CaptureSession;previous_conditions=renderer.condition_for_view
    try:
        renderer.CaptureSession=DualSceneCaptureSession
        renderer.condition_for_view=balanced_condition_for_view
        renderer.run(campaign,output,seconds,images)
    finally:
        renderer.CaptureSession=previous;renderer.condition_for_view=previous_conditions


if __name__=='__main__':
    campaign,output,seconds,images=sys.argv[sys.argv.index('--')+1:]
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
        run(Path(campaign).resolve(),Path(output).resolve(),float(seconds),int(images))
    except Exception:
        write(Path(output)/'failure.json',dict(traceback=traceback.format_exc()));raise
    finally:ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
