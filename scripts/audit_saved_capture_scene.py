"""Re-audit a saved benchmark scene and diagnose capture-only invariance.

The pre-serialization guard failure is preserved. No tolerance is widened and
no plant/crop object is moved, resized, removed or regenerated in this audit.
The saved file, re-audited geometry and exact after-load hash become the common
boundary for both capture methods.
"""
from pathlib import Path
import sys,ctypes,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import bpy
from uchuva_lsystem.nodal_automation import read,write,sha
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.scene import CultivationScene
from uchuva_lsystem.blender_geometry import audit_scene_mesh_collisions
from uchuva_lsystem.blender_environment import audit_plant_ground_clearance
from uchuva_lsystem.blender_reproductive_orientation import audit_calyx_orientation
from uchuva_lsystem.blender_appearance import geometry_digest
from uchuva_lsystem.blender_capture_optimized import binary_geometry_digest
from benchmark_spatial_capture import Timings


def audit(output):
    folder=output/'revisions/reloaded_scene_audit';folder.mkdir(parents=True,exist_ok=False)
    timer=Timings(folder/'timings.json')
    timer.call('load_saved_scene',bpy.ops.wm.open_mainfile,filepath=str(output/'audited_scene.blend'))
    bpy.context.view_layer.update()
    scene=bpy.context.scene;camera=scene.camera
    before=timer.call('binary_before_camera',binary_geometry_digest,scene)
    invariance=[]
    for view in read(output/'schedule.json'):
        camera.location=view['location'];camera.rotation_euler=view['rotation'];bpy.context.view_layer.update()
        after=timer.call('binary_after_camera',binary_geometry_digest,scene)
        invariance.append(dict(index=view['index'],unchanged=before==after,sha256=after))
    write(folder/'camera_invariance.json',invariance)
    if not all(r['unchanged'] for r in invariance):raise ValueError('Loaded geometry depends on camera')
    record=read(output/'scene_record.json')
    trees=[Plant.from_dict(read(p['plant'])) for p in record['plants']]
    layout=CultivationScene.from_dict(read(output/'dataset/scenes/scene_013/layout.json'))
    mesh=timer.call('independent_mesh_audit',audit_scene_mesh_collisions,tolerate_only_leaf_leaf=True,
        max_reported_pairs=None,limit_clearance_search=True)
    write(folder/'mesh.json',mesh)
    ground=timer.call('ground_audit',audit_plant_ground_clearance,seed=20271029+13,required_clearance_m=.001)
    write(folder/'ground.json',ground)
    orientation=timer.call('orientation_audit',audit_calyx_orientation,trees,layout,list(scene.objects))
    write(folder/'orientation.json',orientation)
    if mesh['physical_collision_count'] or ground['status']!='valid' or orientation['status']!='valid':
        raise ValueError('Saved scene fails independent physical re-admission')
    after=timer.call('full_historical_hash_after_reload',geometry_digest,scene)
    original=record['geometry_sha256']
    record.update(pre_serialization_geometry_sha256=original,geometry_sha256=after,
        geometry_hash_reference='after saved-file reload, camera invariance and fresh physical audits',
        reloaded_audit=str(folder),saved_scene_sha256=sha(output/'audited_scene.blend'))
    write(output/'scene_record.json',record)
    prepared=read(output/'preparation_complete.json')
    prepared.update(post_reload_geometry_sha256=after,pre_serialization_geometry_sha256=original,
        reloaded_scene_audit=str(folder),scene_sha256=sha(output/'audited_scene.blend'))
    write(output/'preparation_complete.json',prepared)
    write(folder/'complete.json',dict(physical_admission=True,camera_invariant=True,
        pre_serialization_geometry_sha256=original,post_reload_geometry_sha256=after,
        same_hash=original==after,plant_inputs_unchanged=True,
        explanation='Pre-serialization hash is not silently reused after reload; shared saved file is freshly admitted and pinned exactly.'))


if __name__=='__main__':
    root=Path(sys.argv[sys.argv.index('--')+1]).resolve()
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001);audit(root)
    except Exception:
        write(root/'revisions/reloaded_scene_audit/failure.json',dict(traceback=traceback.format_exc()));raise
    finally:ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
