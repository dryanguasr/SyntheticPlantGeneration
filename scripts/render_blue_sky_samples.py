"""Render a bounded approval sample from physically admitted checkpoints.

No journal, dataset writes, plant edits or training. Classes below are new local
appearance assignments and are reflected in new labels; original labels stay
immutable. ID masks, pixel boxes and all geometry must remain exact.
"""
from pathlib import Path
import sys, copy, traceback
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'src'),str(REPO/'scripts')]
from uchuva_lsystem.nodal_automation import read,write,sha


def run(out, scene_id):
    import bpy
    import render_spatial_dataset as legacy
    from render_appearance_bank import labels_from_mask
    from uchuva_lsystem.blender_capture_optimized import refresh_hidden_fruit_transforms,binary_geometry_digest
    from uchuva_lsystem.blender_capture_dual_scene import DualSceneCaptureSession
    from uchuva_lsystem.blender_capture_skies import CaptureSkyBackground
    from uchuva_lsystem.blender_appearance import create_material_sets
    from uchuva_lsystem.continuous_capture_distance import continuous_camera_pose
    from uchuva_lsystem.calyx_ash_drying import surface_plan
    from uchuva_lsystem.blender_calyx_ash_drying import make_review_material
    for p,h in read(out/'source_lock.json')['files'].items():
        assert sha(p)==h,p
    plan=read(out/'plan.json');source=Path(plan['source'])
    assert read(source/'pause_requested.json')['active']
    folder=source/'dataset/scenes'/scene_id
    accepted=read(folder/'accepted.json');capture=read(folder/'capture_plan.json')
    assert accepted['physical_admission']
    assert sha(folder/'scene.blend')==capture['checkpoint_sha256']
    assert read(folder/'ground.json')['status']=='valid'
    assert read(folder/'orientation.json')['status']=='valid'
    assert read(folder/'mesh.json')['physical_collision_count']==0
    bpy.ops.wm.open_mainfile(filepath=str(folder/'scene.blend'));legacy.configure()
    scene=bpy.context.scene;refresh_hidden_fruit_transforms(scene)
    original_views=[read(source/'dataset/views'/r['source_view']/'view.json') for r in plan['views'] if r['scene_id']==scene_id]
    # Full compiled RNA reads of all coordinates/topology/transforms; exact
    # comparison to the original production capture, not a sampled proxy.
    before=binary_geometry_digest(scene)
    assert all(before==r['bulk_geometry_sha256'] for r in original_views),'Full geometry differs from original capture'
    print('BLUE_REVIEW_CHECKPOINT_GEOMETRY_VERIFIED',scene_id,flush=True)
    camera=scene.camera
    profiles=read(source/'profiles.json')
    sets=create_material_sets(plan['seed'],profiles)
    assignments=read(out/f'{scene_id}_assignments.json')
    materials={};changed={};indices={0:0,1:0,2:0}
    for obj in sorted(scene.objects,key=lambda o:o.name):
        if obj.get('uchuva_semantic_class')!='calyx':continue
        iid=str(obj.get('uchuva_reproductive_instance_id'))
        cid=assignments[iid]['class_id'];index=indices[cid];indices[cid]+=1
        # Preserve all mesh dimensions. Deterioration here is material only.
        grade=(index%5)+1 if cid==2 else 2
        p=surface_plan(cid,grade,plan['seed'])
        key=(cid,p.name)
        if key not in materials:
            materials[key]=make_review_material(sets['class_candidate'][cid],p,bump_scale=.1,map_manifest=plan['vein_maps_manifest'])
        obj.data.materials[0]=materials[key]
        changed[iid]=p.to_dict()
    assert binary_geometry_digest(scene)==before
    print('BLUE_REVIEW_MATERIALS_READY',scene_id,len(materials),flush=True)
    records=[]
    targets=[bpy.data.objects[name] for name in capture['camera_target_names']]
    with DualSceneCaptureSession(scene,profiles,read(source/'dataset/config.json'),int(scene_id[-3:]),camera) as session:
        sky=None;adjustment=None
        for item in [r for r in plan['views'] if r['scene_id']==scene_id]:
            original=read(source/'dataset/views'/item['source_view']/'view.json')
            # Reproduce the original location/Euler channels. Decomposing a
            # serialized matrix introduces subpixel roundoff at raster edges.
            recovered_aim,recovered_depth=continuous_camera_pose(camera,targets,int(scene_id[-3:]),int(item['source_view'][-3:]))
            assert recovered_depth['focus_object']==original['depth_sampling']['focus_object']
            assert max(abs(a-b) for a,b in zip(recovered_aim,original['depth_sampling']['aim_bu']))<1e-6
            aim=original['depth_sampling']['aim_bu'];condition=item['condition']
            session.profiles=copy.deepcopy(profiles)
            session.profiles['lighting']['candidate']['fill_energy']=condition.get('fill_energy_w',profiles['lighting']['candidate']['fill_energy'])
            lighting=session.lighting(camera,tuple(aim),condition=condition)
            if sky is None:
                sky=CaptureSkyBackground(session)
                # The same analytic-sky color adjustment feeds illumination and
                # camera background. Never paint a blue plate behind grey light.
                nodes=scene.world.node_tree.nodes;links=scene.world.node_tree.links
                original_sky=session.background.inputs['Color'].links[0].from_socket
                adjustment=nodes.new('ShaderNodeHueSaturation');adjustment.name='review_analytic_sky_color'
                links.new(original_sky,adjustment.inputs['Color'])
                links.new(adjustment.outputs['Color'],session.background.inputs['Color'])
            adjustment.inputs['Saturation'].default_value=condition['analytic_sky_saturation']
            adjustment.inputs['Value'].default_value=condition['analytic_sky_value']
            lighting=sky.apply(condition,lighting)
            lighting['analytic_sky_color_adjustment']={k:condition[k] for k in ('analytic_sky_saturation','analytic_sky_value')}
            bpy.context.view_layer.update()
            assert max(abs(camera.matrix_world[i][j]-original['camera_matrix'][i][j]) for i in range(4) for j in range(4))<1e-6
            session.verify_geometry()
            dest=out/item['source_view'];dest.mkdir(exist_ok=False)
            # Validate the inexpensive exact-ID pass before the RGB render.
            annotation=session.mask(camera,dest,width=960,height=720)
            assert sha(annotation['path'])==original['mask_sha256'],'ID mask changed'
            # Verify original classes as well as boxes from this exact new mask.
            old_labels,old_instances=labels_from_mask(annotation,accepted['assignments'],960,720)
            assert old_instances==original['instances']
            assert old_labels==Path(original['label']).read_text(encoding='utf-8')
            labels,instances=labels_from_mask(annotation,assignments,960,720)
            assert len(instances)==len(old_instances)
            for a,b in zip(instances,old_instances):
                for k in set(a)|set(b):
                    if k!='class_id':assert a.get(k)==b.get(k),(k,a.get(k),b.get(k))
            print('BLUE_REVIEW_MASK_EXACT',original['view_id'],flush=True)
            scene.render.filepath=str(dest/'rgb.png');bpy.ops.render.render(write_still=True)
            (dest/'labels.txt').write_text(labels,encoding='utf-8');write(dest/'annotations.json',annotation)
            session.verify_geometry()
            row=dict(status='complete_preview',source_view=original['view_id'],scene_id=scene_id,
                preview_only=True,bank_images_added=0,training_started=False,
                image=str(dest/'rgb.png'),mask=annotation['path'],label=str(dest/'labels.txt'),
                camera_matrix=[list(r) for r in camera.matrix_world],depth_sampling=original['depth_sampling'],
                lighting=lighting,instances=instances,geometry_unchanged=True,
                mask_exactly_identical=True,boxes_and_instances_unchanged=True,
                appearance_assignments_local_only=True,source_scene_physical_admission=True,
                source_geometry_sha256=accepted['geometry_sha256'])
            for key in ('image','mask','label'):row[key+'_sha256']=sha(row[key])
            write(dest/'view.json',row);records.append(row)
            print('BLUE_REVIEW_COMPLETE',original['view_id'],flush=True)
    assert binary_geometry_digest(scene)==before
    write(out/f'{scene_id}_result.json',dict(records=records,surface_plans=changed,
        all_geometry_unchanged=True,contraction_applied=False,
        scope='material/light-only preview of admitted scene; flowers/context retain original audit limits'))


if __name__=='__main__':
    args=sys.argv[sys.argv.index('--')+1:];out=Path(args[0]).resolve();scene=args[1]
    try:run(out,scene)
    except Exception:
        write(out/f'{scene}_failure.json',dict(traceback=traceback.format_exc()));raise
