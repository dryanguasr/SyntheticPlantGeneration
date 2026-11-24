"""Dependency injection adapter for the frozen paired-capture harness.

Does not edit the historical/current benchmark sources. Only the optimized
session class is substituted explicitly, in this worker process, then restored.
"""
from pathlib import Path
import sys,ctypes,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import uchuva_lsystem.blender_capture_optimized as capture_module
from uchuva_lsystem.blender_capture_dual_scene import DualSceneCaptureSession
from benchmark_spatial_capture import capture,Timings
from uchuva_lsystem.nodal_automation import write,read,awake_seconds


def repeat_original_rgb(output):
    """A genuine original-method self-repeat, before installing ID colors."""
    import bpy
    import render_spatial_dataset as legacy
    from uchuva_lsystem.blender_appearance import geometry_digest,apply_profile
    from uchuva_lsystem.blender_capture_optimized import refresh_hidden_fruit_transforms
    from uchuva_lsystem.capture_plan import profiles_for_condition
    folder=output/'baseline_repeat';folder.mkdir()
    timer=Timings(folder/'timings.json');started=awake_seconds()
    timer.call('load',bpy.ops.wm.open_mainfile,filepath=str(output/'audited_scene.blend'))
    legacy.configure();bpy.context.view_layer.update()
    timer.call('refresh_hidden_fruit_transforms',refresh_hidden_fruit_transforms,bpy.context.scene)
    scene=bpy.context.scene;camera=scene.camera
    expected=read(output/'scene_record.json')['geometry_sha256']
    if timer.call('geometry_before',geometry_digest,scene)!=expected:raise ValueError('Repeat geometry differs')
    view=read(output/'schedule.json')[0]
    camera.location=view['location'];camera.rotation_euler=view['rotation']
    profiles,light=profiles_for_condition(read(output/'profiles.json'),view['condition'])
    apply_profile(profiles,'LT',camera,view['aim'],light)
    legacy.camera_background(read(output/'dataset/config.json'),13);bpy.context.view_layer.update()
    scene.render.filepath=str(folder/'rgb.png')
    timer.call('rgb_render',bpy.ops.render.render,write_still=True)
    if timer.call('geometry_after',geometry_digest,scene)!=expected:raise ValueError('Repeat changed geometry')
    write(folder/'complete.json',dict(active_seconds=awake_seconds()-started,original_method=True,
        index=0,geometry_sha256=expected,parameters_unchanged=True))


if __name__=='__main__':
    campaign,output=[Path(p).resolve() for p in sys.argv[sys.argv.index('--')+1:]]
    previous=capture_module.CaptureSession
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
        repeat_original_rgb(output)
        capture_module.CaptureSession=DualSceneCaptureSession
        capture(campaign,output,'optimized')
    except Exception:
        write(output/'dual_scene_failure.json',dict(traceback=traceback.format_exc()));raise
    finally:
        capture_module.CaptureSession=previous
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
