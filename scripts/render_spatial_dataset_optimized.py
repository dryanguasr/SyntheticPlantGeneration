"""Explicit opt-in capture of admitted plants; never modifies a frozen campaign.

Blender --python this.py -- CAMPAIGN NEW_OUTPUT ACTIVE_SECONDS MAX_IMAGES
Run one complete scene per process to bound memory; resume uses the same native
awake deadline and immutable source lock. This entrypoint does not train.
"""
from pathlib import Path
import sys
import math
import random
import ctypes
import traceback
import shutil
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import bpy
from mathutils import Vector
import render_spatial_dataset as legacy
from uchuva_lsystem.nodal_automation import read,write,sha,awake_seconds
from uchuva_lsystem.spatial_dataset import committed_views,depth_stratum
from uchuva_lsystem.blender_appearance import geometry_digest
from uchuva_lsystem.blender_capture_optimized import CaptureSession
from uchuva_lsystem.capture_plan import CaptureJournal,condition_for_view
from uchuva_lsystem.reproductive_space import digest
from render_appearance_bank import labels_from_mask


def camera_pose(camera,targets,scene_index,index):
    rng=random.Random(20261029+scene_index*1000+index);focus=rng.choice(targets)
    center=sum((focus.matrix_world@Vector(v) for v in focus.bound_box),Vector())/8
    depth=depth_stratum(index);desired={'near':48.,'middle':24.,'far':10.}[depth]
    span=min(float(d) for d in focus.dimensions if d>0)
    distance=max(2.,min(100.,span*960*50/(36*desired)))
    az=rng.uniform(-math.pi*.56,-math.pi*.44);el=rng.uniform(.05,.28)
    camera.location=center+Vector((math.cos(az),math.sin(az),el)).normalized()*distance
    aim=center+Vector((rng.uniform(-.08,.08)*distance,0,rng.uniform(-.06,.06)*distance))
    camera.rotation_euler=(aim-camera.location).to_track_quat('-Z','Y').to_euler()
    return aim,distance,depth


def verify_files(files):
    for path,expected in files.items():
        if sha(path)!=expected:raise ValueError('Frozen source/input changed: '+path)


def prepare(campaign,output,active_seconds,max_images):
    if output==campaign:raise ValueError('Historical campaign cannot be the optimized output')
    if output.exists():
        budget=read(output/'budget.json')
        if budget.get('schema')!='uchuva.optimized_capture_budget/1':raise ValueError('Not an optimized capture output')
        if budget['limit_active_seconds']!=active_seconds or budget['target_images']!=max_images:
            raise ValueError('Resume cannot change the frozen budget or target')
        return
    if active_seconds<=0 or max_images<=0:raise ValueError('Positive explicit budget and target required')
    historical=read(campaign/'dataset/source_lock.json');verify_files(historical['files'])
    output.mkdir(parents=True,exist_ok=False);bank=output/'dataset';bank.mkdir()
    config=read(campaign/'dataset/config.json')
    config.update(generation_variant='earthen_floor_v6_capture_optimized',max_images=max_images,
                  illumination_variability='independent capture_condition stream; reviewed materials intact')
    # This path implements the current interior-row camera recipe explicitly.
    if not config.get('interior_targets') or not config.get('foreground_targets'):
        raise ValueError('Optimized camera contract requires interior foreground targets')
    for name,value in [('config.json',config),('pool_lock.json',read(campaign/'dataset/pool_lock.json'))]:write(bank/name,value)
    write(output/'profiles.json',read(campaign/'profiles.json'))
    write(output/'budget.json',dict(schema='uchuva.optimized_capture_budget/1',awake_started_seconds=awake_seconds(),limit_active_seconds=active_seconds,
         target_images=max_images,source_campaign=str(campaign),training_started=False))
    files=dict(historical['files'])
    paths=[Path(__file__),ROOT/'src/uchuva_lsystem/blender_capture_optimized.py',ROOT/'src/uchuva_lsystem/capture_plan.py',
           ROOT/'src/uchuva_lsystem/mask_arrays.py',
           bank/'config.json',bank/'pool_lock.json',output/'profiles.json',output/'budget.json']
    files.update({str(p.resolve()):sha(p) for p in paths})
    write(bank/'source_lock.json',dict(files=files,historical_source_lock_sha256=sha(campaign/'dataset/source_lock.json')))


def run(campaign,output,active_seconds,max_images):
    prepare(campaign,output,active_seconds,max_images)
    bank=output/'dataset';lock=read(bank/'source_lock.json');verify_files(lock['files'])
    budget=read(output/'budget.json');config=read(bank/'config.json');profiles=read(output/'profiles.json')
    left=lambda:budget['limit_active_seconds']-(awake_seconds()-budget['awake_started_seconds'])
    existing=committed_views(bank);journal=CaptureJournal(bank)
    if left()<180 or len(existing)>=budget['target_images']:return
    index=max([int(p.name.split('_')[-1]) for p in (bank/'scenes').glob('scene_*')],default=-1)+1
    start=awake_seconds();scene=legacy.build_scene(output,bank,index,read(bank/'pool_lock.json')['plants'],profiles)
    if scene is None:
        write(bank/'state.json',dict(stage='scene_rejected',scene_index=index));return
    record,camera,objects=scene
    preparation_seconds=awake_seconds()-start
    front={p['seed'] for j,p in enumerate(record['plants'])
           if j%config['columns']==config['columns']//2 and j//config['columns']<2}
    targets=[o for o in objects if o.get('uchuva_semantic_class')=='calyx'
             and o.get('uchuva_plant_id') in {'plant_'+str(seed) for seed in front}]
    try:
        with CaptureSession(bpy.context.scene,profiles,config,index,camera) as session:
            for view_index in range(config['views_per_scene']):
                if left()<30 or len(journal.paths)>=budget['target_images']:break
                if shutil.disk_usage(bank).free<config.get('min_free_bytes',1073741824):
                    raise RuntimeError('Capture disk-space reserve reached')
                start=awake_seconds();view_id=f'{record["scene_id"]}_view_{view_index:03d}'
                folder=bank/'views'/view_id;folder.mkdir(parents=True,exist_ok=False)
                aim,distance,depth=camera_pose(camera,targets,index,view_index)
                condition=condition_for_view(index,view_index)
                lighting=session.lighting(camera,tuple(aim),condition=condition)
                session.verify_geometry();bpy.context.scene.render.filepath=str(folder/'rgb.png')
                bpy.ops.render.render(write_still=True)
                annotation=session.mask(camera,folder,width=960,height=720)
                labels,instances=labels_from_mask(annotation,record['assignments'],960,720)
                (folder/'labels.txt').write_text(labels,encoding='utf-8');write(folder/'annotations.json',annotation)
                session.verify_geometry()
                if not instances:
                    write(folder/'rejected.json',dict(reason='no_visible_target'));continue
                pose=[list(r) for r in camera.matrix_world]
                row=dict(status='complete',view_id=view_id,scene_id=record['scene_id'],depth_stratum=depth,
                    generation_variant=record['generation_variant'],source_lock_sha256=sha(bank/'source_lock.json'),
                    render_config=dict(engine='CYCLES',samples=12,denoising=True,width=960,height=720,unit_scale_length=.1),
                    camera_distance_bu=distance,camera_distance_m=distance*.1,camera_matrix=pose,camera_sha256=digest(pose),
                    geometry_sha256=record['geometry_sha256'],bulk_geometry_sha256=session.expected,
                    plant_seeds=[p['seed'] for p in record['plants']],instances=instances,lighting=lighting,
                    capture_active_seconds=awake_seconds()-start,image=str((folder/'rgb.png').resolve()),
                    mask=annotation['path'],label=str((folder/'labels.txt').resolve()))
                for k in ('image','mask','label'):row[k+'_sha256']=sha(row[k])
                journal.commit(folder,row)
                write(bank/'state.json',dict(stage='capturing',committed_images=len(journal.paths),remaining_seconds=max(0,left())))
    finally:
        if geometry_digest(bpy.context.scene)!=record['geometry_sha256']:raise ValueError('Final full historical geometry guard failed')
        journal.consolidate()
    verify_files(lock['files'])
    write(bank/'state.json',dict(stage='scene_complete_restart_for_next',scene_index=index,
        committed_images=len(journal.paths),preparation_active_seconds=preparation_seconds,remaining_seconds=max(0,left()),training_started=False))


if __name__=='__main__':
    campaign,output,seconds,images=sys.argv[sys.argv.index('--')+1:]
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
        run(Path(campaign).resolve(),Path(output).resolve(),float(seconds),int(images))
    except Exception:
        write(Path(output)/'failure.json',dict(traceback=traceback.format_exc()));raise
    finally:ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
