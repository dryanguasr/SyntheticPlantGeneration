"""One optimized scene or its checkpoint continuation; no morphology creation."""
from pathlib import Path
import sys,ctypes,traceback,shutil
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import bpy
import render_spatial_dataset as legacy
from uchuva_lsystem.continuous_capture_distance import continuous_camera_pose
from render_appearance_bank import labels_from_mask
from uchuva_lsystem.dataset_completion import verify_sources,select_next_scene
from uchuva_lsystem.nodal_automation import read,write,sha,awake_seconds
from uchuva_lsystem.capture_plan import CaptureJournal
from uchuva_lsystem.capture_skies import sky_condition_for_view
from uchuva_lsystem.blender_capture_skies import CaptureSkyBackground
from uchuva_lsystem.blender_capture_dual_scene import DualSceneCaptureSession
from uchuva_lsystem.blender_capture_optimized import refresh_hidden_fruit_transforms,binary_geometry_digest
from uchuva_lsystem.blender_appearance import geometry_digest
from uchuva_lsystem.reproductive_space import digest


def preserve_partial(root,job,folder):
    target=job/'partial_views'/folder.name
    if root not in folder.resolve().parents or root not in target.resolve().parents:raise ValueError('Partial recovery outside root')
    target.parent.mkdir(parents=True,exist_ok=True);folder.rename(target)


def run(root,job):
    verify_sources(root);bank=root/'dataset';config=read(bank/'config.json');profiles=read(root/'profiles.json')
    index,resume=select_next_scene(root);scene_id=f'scene_{index:03d}';folder=bank/'scenes'/scene_id
    write(bank/'state.json',dict(stage='resuming_scene' if resume else 'building_scene',scene_index=index,training_started=False))
    start=awake_seconds()
    if resume:
        record=read(folder/'accepted.json');plan=read(folder/'capture_plan.json')
        if sha(folder/'scene.blend')!=plan['checkpoint_sha256']:raise ValueError('Checkpoint changed')
        bpy.ops.wm.open_mainfile(filepath=str(folder/'scene.blend'));legacy.configure()
        refresh_hidden_fruit_transforms(bpy.context.scene)
        if geometry_digest(bpy.context.scene)!=record['geometry_sha256']:raise ValueError('Checkpoint geometry differs')
        camera=bpy.context.scene.camera;targets=[bpy.data.objects[name] for name in plan['camera_target_names']]
    else:
        result=legacy.build_scene(root,bank,index,read(bank/'pool_lock.json')['plants'],profiles)
        if result is None:
            write(job/'result.json',dict(status='scene_rejected',scene_id=scene_id,active_seconds=awake_seconds()-start));return
        record,camera,objects=result
        front={p['seed'] for j,p in enumerate(record['plants']) if j%config['columns']==config['columns']//2 and j//config['columns']<2}
        targets=[o for o in objects if o.get('uchuva_semantic_class')=='calyx'
                 and o.get('uchuva_plant_id') in {'plant_'+str(seed) for seed in front}]
        bpy.ops.wm.save_as_mainfile(filepath=str(folder/'scene.blend'))
        plan=dict(version='optimized-completion/1',camera_target_names=[o.name for o in targets],
            checkpoint_sha256=sha(folder/'scene.blend'),geometry_sha256=record['geometry_sha256'],
            source_lock_sha256=sha(root/'source_lock.json'),capture_seed=20261029)
        write(folder/'capture_plan.json',plan)
        refresh_hidden_fruit_transforms(bpy.context.scene)
        if geometry_digest(bpy.context.scene)!=record['geometry_sha256']:
            raise ValueError('Fresh checkpoint changed its audited geometry')
    preparation=awake_seconds()-start
    print('COMPLETION_SCENE_ADMITTED',scene_id,'resume',resume,flush=True)
    journal=CaptureJournal(bank);session=None;captured=[]
    try:
        with DualSceneCaptureSession(bpy.context.scene,profiles,config,index,camera) as session:
            sky_background=None
            for view_index in range(config['views_per_scene']):
                view_id=f'{scene_id}_view_{view_index:03d}';out=bank/'views'/view_id
                if (out/'view.json').exists() or (out/'rejected.json').exists():continue
                if len(journal.paths)>=config['max_images']:break
                if shutil.disk_usage(bank).free<config['min_free_bytes']:raise RuntimeError('Disk-space reserve reached')
                if out.exists():preserve_partial(root,job,out)
                out.mkdir(parents=True,exist_ok=False);started=awake_seconds()
                aim,depth_sample=continuous_camera_pose(camera,targets,index,view_index)
                distance=depth_sample['distance_bu'];depth=depth_sample['depth_stratum']
                condition=sky_condition_for_view(index,view_index)
                lighting=session.lighting(camera,tuple(aim),condition=condition)
                if sky_background is None:sky_background=CaptureSkyBackground(session)
                lighting=sky_background.apply(condition,lighting)
                session.verify_geometry();bpy.context.scene.render.filepath=str(out/'rgb.png')
                bpy.ops.render.render(write_still=True)
                annotation=session.mask(camera,out,width=960,height=720)
                labels,instances=labels_from_mask(annotation,record['assignments'],960,720)
                (out/'labels.txt').write_text(labels,encoding='utf-8');write(out/'annotations.json',annotation)
                session.verify_geometry()
                if not instances:
                    write(out/'rejected.json',dict(reason='no_visible_target',
                        retained_as_negative_candidate=True,counts_toward_target=False))
                    continue
                pose=[list(row) for row in camera.matrix_world]
                row=dict(status='complete',view_id=view_id,scene_id=scene_id,depth_stratum=depth,
                    generation_variant=config['generation_variant'],source_lock_sha256=sha(root/'source_lock.json'),
                    render_config=dict(engine='CYCLES',samples=12,denoising=True,width=960,height=720,
                        unit_scale_length=.1,shared_geometry_mask_scene=True,persistent_cycles_data=True),
                    camera_matrix=pose,camera_sha256=digest(pose),camera_distance_bu=distance,camera_distance_m=.1*distance,
                    depth_sampling=depth_sample,
                    geometry_sha256=record['geometry_sha256'],bulk_geometry_sha256=session.expected,
                    plant_seeds=[p['seed'] for p in record['plants']],lighting=lighting,instances=instances,
                    capture_active_seconds=awake_seconds()-started,image=str((out/'rgb.png').resolve()),
                    mask=annotation['path'],label=str((out/'labels.txt').resolve()))
                for key in ('image','mask','label'):row[key+'_sha256']=sha(row[key])
                journal.commit(out,row);captured.append(view_id)
                write(bank/'state.json',dict(stage='capturing',scene_index=index,last_view=view_id,
                    raw_complete_images=len(journal.paths),scene_closure_pending=True,training_started=False))
                print('COMPLETION_VIEW',view_id,len(instances),'raw_pairs',len(journal.paths),flush=True)
            if geometry_digest(bpy.context.scene)!=record['geometry_sha256']:raise ValueError('Final full geometry guard failed')
        after=binary_geometry_digest(bpy.context.scene)
        if after!=session.expected:
            refresh_hidden_fruit_transforms(bpy.context.scene);after=binary_geometry_digest(bpy.context.scene)
        if after!=session.expected:raise ValueError('Geometry differs after closing capture session')
        journal.consolidate();verify_sources(root)
        count=sum(read(p).get('status')=='complete' for p in (bank/'views').glob(scene_id+'_view_*/view.json'))
        write(folder/'capture_complete.json',dict(geometry_unchanged=True,geometry_sha256=record['geometry_sha256'],
            bulk_geometry_sha256=after,views=count,checkpoint_sha256=plan['checkpoint_sha256'],
            source_lock_sha256=sha(root/'source_lock.json'),resumed=resume))
        write(job/'result.json',dict(status='scene_complete',scene_id=scene_id,new_views=captured,
            preparation_active_seconds=preparation,active_seconds=awake_seconds()-start,training_started=False))
    except Exception:
        write(job/'failure.json',dict(traceback=traceback.format_exc(),scene_id=scene_id));raise


if __name__=='__main__':
    root,job=[Path(p).resolve() for p in sys.argv[sys.argv.index('--')+1:]]
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001);run(root,job)
    finally:ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
