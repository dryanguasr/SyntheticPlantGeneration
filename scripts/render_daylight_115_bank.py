"""Bounded RGB-only recapture with exact, audited geometric ID-mask caching.

The original raster is reusable only with bit-exact camera/geometry/visibility
and unchanged intrinsics. One native ID pass validates each prepared layout.
All visible IDs are reclassified from the new frozen appearance assignment;
no tiny objects are removed here. Native RGB quality is unchanged.
"""
from pathlib import Path
import sys,copy,shutil,time,traceback
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'src'),str(REPO/'scripts')]
from uchuva_lsystem.nodal_automation import read,write,sha,awake_seconds
from uchuva_lsystem.daylight_115_bank import (exact_mask_cache_gate,visibility_fingerprint,camera_intrinsics,memory_snapshot)


def run(bank,job):
    import bpy
    import render_spatial_dataset as legacy
    from render_appearance_bank import labels_from_mask
    from uchuva_lsystem.blender_capture_optimized import CaptureSession,binary_geometry_digest,refresh_hidden_fruit_transforms
    from uchuva_lsystem.blender_capture_skies import CaptureSkyBackground
    from uchuva_lsystem.blender_daylight_balance import DaylightRadianceBalance
    from uchuva_lsystem.blender_appearance import create_material_sets
    from uchuva_lsystem.continuous_capture_distance import continuous_camera_pose
    from uchuva_lsystem.calyx_ash_drying import surface_plan
    from uchuva_lsystem.blender_calyx_ash_drying import make_review_material
    plan=read(bank/'plan.json');task=read(job/'task.json');sid=task['scene_id'];source=Path(plan['source'])
    lock_sha=sha(bank/'source_lock.json')
    for p,h in read(bank/'source_lock.json')['files'].items():assert sha(p)==h,p
    assert read(source/'pause_requested.json')['active']
    originals={r['view_id']:read(r['record']) for r in plan['views'] if r['scene_id']==sid}
    folder=source/'dataset/scenes'/sid;capture=read(folder/'capture_plan.json');accepted=read(folder/'accepted.json')
    expected=next(iter(originals.values()))['bulk_geometry_sha256']
    assert all(r['bulk_geometry_sha256']==expected for r in originals.values())
    assert accepted['physical_admission'] and read(folder/'mesh.json')['physical_collision_count']==0
    assert read(folder/'ground.json')['status']=='valid' and read(folder/'orientation.json')['status']=='valid'
    prepared=bank/'prepared'/sid;manifest=prepared/'checkpoint.json';started=awake_seconds()
    if manifest.exists():
        state=read(manifest)
        assert state['source_lock_sha256']==lock_sha
        assert sha(prepared/'scene.blend')==state['checkpoint_sha256']
        bpy.ops.wm.open_mainfile(filepath=str(prepared/'scene.blend'));legacy.configure();scene=bpy.context.scene
        warmup=False
        if binary_geometry_digest(scene)!=expected:
            refresh_hidden_fruit_transforms(scene);warmup=True
        assert binary_geometry_digest(scene)==expected
        assert visibility_fingerprint(scene)==state['visibility_sha256']
        surface=read(prepared/'surface_plans.json')
    else:
        assert sha(folder/'scene.blend')==capture['checkpoint_sha256']
        bpy.ops.wm.open_mainfile(filepath=str(folder/'scene.blend'));legacy.configure();scene=bpy.context.scene
        warmup=binary_geometry_digest(scene)!=expected
        if warmup:refresh_hidden_fruit_transforms(scene)
        assert binary_geometry_digest(scene)==expected
        visibility=visibility_fingerprint(scene);profiles=read(source/'profiles.json')
        sets=create_material_sets(plan['seed'],profiles);assignments=read(bank/'assignments'/f'{sid}.json')
        materials={};indices={0:0,1:0,2:0};surface={}
        for o in sorted(scene.objects,key=lambda o:o.name):
            if o.get('uchuva_semantic_class')!='calyx':continue
            iid=str(o.get('uchuva_reproductive_instance_id'));cid=assignments[iid]['class_id']
            index=indices[cid];indices[cid]+=1;p=surface_plan(cid,(index%5)+1 if cid==2 else 2,plan['seed'])
            key=(cid,p.name)
            if key not in materials:materials[key]=make_review_material(sets['class_candidate'][cid],p,bump_scale=.1,map_manifest=plan['vein_maps_manifest'])
            o.data.materials[0]=materials[key];surface[iid]=p.to_dict()
        assert binary_geometry_digest(scene)==expected and visibility_fingerprint(scene)==visibility
        prepared.mkdir(parents=True,exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(prepared/'scene.blend'))
        state=dict(checkpoint_sha256=sha(prepared/'scene.blend'),source_lock_sha256=lock_sha,
            original_checkpoint_sha256=capture['checkpoint_sha256'],bulk_geometry_sha256=expected,
            visibility_sha256=visibility,intrinsics=camera_intrinsics(scene.camera))
        write(prepared/'surface_plans.json',surface);write(manifest,state)
    print('BANK_PREPARED',sid,'warmup',warmup,flush=True)
    assignments=read(bank/'assignments'/f'{sid}.json');camera=scene.camera;profiles=read(source/'profiles.json')
    targets=[bpy.data.objects[n] for n in capture['camera_target_names']]
    rows=[];reason='requested_block_complete';last_original=None
    native_needed=not (prepared/'native_mask_validation.json').exists()
    old_persistent=scene.render.use_persistent_data;scene.render.use_persistent_data=True
    with CaptureSession(scene,profiles,read(source/'dataset/config.json'),int(sid[-3:]),camera) as session:
        sky=None;adjustment=None;balance=None
        for name in task['view_ids']:
            if (bank/'views'/name/'view.json').exists():continue
            original=originals[name];item=next(r for r in plan['views'] if r['view_id']==name)
            aim,depth=continuous_camera_pose(camera,targets,int(sid[-3:]),int(name[-3:]))
            condition=item['condition'];session.profiles=copy.deepcopy(profiles)
            session.profiles['lighting']['candidate']['fill_energy']=condition['fill_energy_w']
            lighting=session.lighting(camera,tuple(aim),condition=condition)
            if sky is None:
                sky=CaptureSkyBackground(session)
                nodes=scene.world.node_tree.nodes;links=scene.world.node_tree.links
                original_color=session.background.inputs['Color'].links[0].from_socket
                adjustment=nodes.new('ShaderNodeHueSaturation');links.new(original_color,adjustment.inputs['Color'])
                links.new(adjustment.outputs[0],session.background.inputs['Color'])
            adjustment.inputs['Saturation'].default_value=condition['analytic_sky_saturation']
            adjustment.inputs['Value'].default_value=condition['analytic_sky_value']
            lighting=sky.apply(condition,lighting)
            if balance is None:balance=DaylightRadianceBalance(session)
            lighting=balance.apply(condition,lighting)
            lighting['camera_background']['same_analytic_atmosphere']=condition['sky_type']!='overcast'
            lighting['analytic_sky_color_adjustment']={k:condition[k] for k in ('analytic_sky_saturation','analytic_sky_value')}
            bpy.context.view_layer.update();pose=[list(r) for r in camera.matrix_world]
            exact_mask_cache_gate(original,pose,binary_geometry_digest(scene),visibility_fingerprint(scene),
                state['visibility_sha256'],camera_intrinsics(camera),state['intrinsics'])
            dest=bank/'views'/name;dest.mkdir(parents=True,exist_ok=False)
            assert sha(original['mask'])==original['mask_sha256']
            mask=dest/'mask_calyx_crisp_v2.png';shutil.copy2(original['mask'],mask)
            annotation=read(Path(original['mask']).parent/'annotations.json');annotation['path']=str(mask)
            write(dest/'annotations.json',annotation)
            labels,instances=labels_from_mask(annotation,assignments,960,720)
            (dest/'labels.txt').write_text(labels,encoding='utf-8')
            old_labels,old_instances=labels_from_mask(annotation,accepted['assignments'],960,720)
            assert old_instances==original['instances'] and old_labels==Path(original['label']).read_text(encoding='utf-8')
            start=awake_seconds();scene.render.filepath=str(dest/'rgb.png');bpy.ops.render.render(write_still=True)
            session.verify_geometry();assert visibility_fingerprint(scene)==state['visibility_sha256']
            row=dict(status='complete',view_id=name,scene_id=sid,source_record=item['record'],
                source_lock_sha256=lock_sha,geometry_sha256=accepted['geometry_sha256'],bulk_geometry_sha256=expected,
                camera_matrix=pose,depth_sampling=depth,depth_stratum=depth['depth_stratum'],
                camera_distance_m=depth['distance_m'],plant_seeds=original['plant_seeds'],lighting=lighting,
                instances=instances,image=str(dest/'rgb.png'),mask=str(mask),label=str(dest/'labels.txt'),
                render_config=dict(original['render_config'],shared_geometry_mask_scene=False,
                    persistent_cycles_data=True,id_mask_cached=True),mask_cache=dict(used=True,exact_gate=True,
                    original_mask_sha256=original['mask_sha256'],visibility_sha256=state['visibility_sha256'],
                    native_validation=str(prepared/'native_mask_validation.json')),
                capture_active_seconds=awake_seconds()-start,memory=memory_snapshot())
            for key in ('image','mask','label'):row[key+'_sha256']=sha(row[key])
            rows.append((dest,row));write(dest/'pending.json',row);last_original=original
            print('BANK_RGB',name,'seconds',round(row['capture_active_seconds'],2),'memory',row['memory'],flush=True)
            if row['memory'].get('private_bytes',0)>18*1024**3 or row['memory'].get('available_bytes',10*1024**3)<2.5*1024**3:
                reason='recycle_private_memory';break
        if native_needed and rows:
            # One fresh native pass per layout independently verifies the cache.
            debug=job/'native_mask_check';debug.mkdir(exist_ok=False)
            scene.render.dither_intensity=0
            native=session.mask(camera,debug,width=960,height=720)
            assert sha(native['path'])==last_original['mask_sha256'],'Native exact mask cache check failed'
            write(prepared/'native_mask_validation.json',dict(passed=True,checked_view=last_original['view_id'],
                source_lock_sha256=lock_sha,source_mask_sha256=last_original['mask_sha256'],
                native_mask_sha256=sha(native['path']),bulk_geometry_sha256=expected,
                camera_exact=True,quality_policy='bit-exact, no tolerance'))
            print('BANK_NATIVE_CACHE_VERIFIED',sid,last_original['view_id'],flush=True)
    scene.render.use_persistent_data=old_persistent
    assert binary_geometry_digest(scene)==expected
    for dest,row in rows:write(dest/'view.json',row)
    write(job/'result.json',dict(completed=True,views=[r['view_id'] for _,r in rows],reason=reason,
        scene_id=sid,active_seconds=awake_seconds()-started,warmup_required=warmup,mask_cache_native_validated=True))


if __name__=='__main__':
    bank,job=[Path(p).resolve() for p in sys.argv[sys.argv.index('--')+1:]]
    try:run(bank,job)
    except BaseException:
        write(job/'failure.json',dict(traceback=traceback.format_exc()));raise
