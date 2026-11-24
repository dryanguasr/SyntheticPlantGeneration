"""Small approval batch: surface-only crop views and isolated contracting shells.

Never commits to the paused bank or starts training. The shape fixtures have no
internal berry and are not whole-plant physical admissions.
"""
from pathlib import Path
import sys, json, traceback
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'src'),str(REPO/'scripts')]
from uchuva_lsystem.nodal_automation import read,write,sha
from uchuva_lsystem.calyx_diffusion_texture import surface_plan
from uchuva_lsystem.blender_calyx_diffusion_profile import make_review_material


def context(out):
    import bpy
    from mathutils import Matrix
    import render_spatial_dataset as legacy
    from render_appearance_bank import labels_from_mask
    from uchuva_lsystem.blender_capture_optimized import refresh_hidden_fruit_transforms,binary_geometry_digest
    from uchuva_lsystem.blender_capture_dual_scene import DualSceneCaptureSession
    from uchuva_lsystem.blender_capture_skies import CaptureSkyBackground
    from uchuva_lsystem.blender_appearance import geometry_digest
    plan=read(out/'plan.json');source=Path(plan['source']);folder=source/'dataset/scenes/scene_027'
    accepted=read(folder/'accepted.json');capture=read(folder/'capture_plan.json')
    assert sha(folder/'scene.blend')==capture['checkpoint_sha256']
    bpy.ops.wm.open_mainfile(filepath=str(folder/'scene.blend'));legacy.configure()
    scene=bpy.context.scene;refresh_hidden_fruit_transforms(scene)
    assert geometry_digest(scene)==accepted['geometry_sha256']
    before=binary_geometry_digest(scene);camera=scene.camera
    views=[read(source/'dataset/views'/v/'view.json') for v in plan['context_views']]
    visible={i['instance_id'] for row in views for i in row['instances']}
    groups={c:[] for c in (0,1,2)}
    for iid in sorted(visible):groups[accepted['assignments'][iid]['class_id']].append(iid)
    chosen={iid:surface_plan(c,j,20261031+j%6) for c,ids in groups.items() for j,iid in enumerate(ids)}
    materials={};modified={}
    for obj in scene.objects:
        if obj.get('uchuva_semantic_class')!='calyx':continue
        iid=str(obj.get('uchuva_reproductive_instance_id'))
        if iid not in chosen:continue
        p=chosen[iid];base=obj.data.materials[0]
        key=(base.name,p.class_id,p.name,p.seed)
        if key not in materials:materials[key]=make_review_material(base,p,bump_scale=.1,map_manifest=plan['vein_maps_manifest'])
        obj.data.materials[0]=materials[key];modified[iid]=p.to_dict()
    if not modified:raise ValueError('No calyx IDs matched')
    assert binary_geometry_digest(scene)==before
    records=[]
    with DualSceneCaptureSession(scene,read(source/'profiles.json'),read(source/'dataset/config.json'),27,camera) as session:
        sky=None
        for original in views:
            aim=original['depth_sampling']['aim_bu']
            camera.matrix_world=Matrix(original['camera_matrix'])
            condition=original['lighting']['capture_condition']
            lighting=session.lighting(camera,tuple(aim),condition=condition)
            if sky is None:sky=CaptureSkyBackground(session)
            lighting=sky.apply(condition,lighting)
            # Comparison uses the recorded camera, not a new stochastic draw or
            # an unevaluated matrix after changing location/rotation channels.
            camera.matrix_world=Matrix(original['camera_matrix']);bpy.context.view_layer.update()
            difference=max(abs(camera.matrix_world[i][j]-original['camera_matrix'][i][j]) for i in range(4) for j in range(4))
            if difference>1e-6:raise ValueError('Recorded camera differs')
            session.verify_geometry()
            dest=out/original['view_id'];dest.mkdir(exist_ok=False)
            scene.render.filepath=str(dest/'rgb.png');bpy.ops.render.render(write_still=True)
            annotation=session.mask(camera,dest,width=960,height=720)
            labels,instances=labels_from_mask(annotation,accepted['assignments'],960,720)
            if instances!=original['instances']:raise ValueError('Instances changed')
            if labels!=Path(original['label']).read_text(encoding='utf-8'):raise ValueError('YOLO changed')
            if sha(annotation['path'])!=original['mask_sha256']:raise ValueError('Mask bytes changed')
            (dest/'labels.txt').write_text(labels,encoding='utf-8');write(dest/'annotations.json',annotation)
            row=dict(original,image=str(dest/'rgb.png'),mask=annotation['path'],label=str(dest/'labels.txt'),
                preview_only=True,original_image=original['image'],camera_max_difference=difference,
                geometry_unchanged=True,mask_exactly_identical=True,instances_identical=True)
            for key in ('image','mask','label'):row[key+'_sha256']=sha(row[key])
            write(dest/'view.json',row);records.append(row)
            print('APPROVAL_CONTEXT_COMPLETE',original['view_id'],flush=True)
    assert binary_geometry_digest(scene)==before
    write(out/'context_result.json',dict(records=records,modified=modified,geometry_unchanged=True,
        context_shape_changes=False,source_scene_physical_admission=accepted['physical_admission']))


def organs(out):
    import bpy,bmesh
    from mathutils import Vector
    from uchuva_lsystem.blender_scene import cleanup_scene
    from uchuva_lsystem.blender_geometry import create_calyx_mesh,_create_cylinder_between
    from uchuva_lsystem.blender_appearance import create_material_sets
    from uchuva_lsystem.calyx_deterioration import deterioration_state,deform_calyx_point
    plan=read(out/'plan.json');profiles=read(Path(plan['source'])/'profiles.json')
    cleanup_scene(include_hidden=True);scene=bpy.context.scene
    scene.render.engine='CYCLES';scene.cycles.samples=32;scene.cycles.use_denoising=True
    scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=.01
    scene.render.resolution_x=1960;scene.render.resolution_y=640;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB'
    scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast'
    prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.get_devices()
    for device in prefs.devices:device.use=device.type=='OPTIX'
    scene.cycles.device='GPU';sets=create_material_sets(20261031,profiles)
    world=bpy.data.worlds.new('approval_neutral');world.use_nodes=True;scene.world=world
    world.node_tree.nodes['Background'].inputs['Color'].default_value=(.65,.68,.72,1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value=.6
    for location,energy,size in [((10,-10,12),1500,12),((26,1,10),650,10)]:
        bpy.ops.object.light_add(type='AREA',location=location);light=bpy.context.object;light.data.energy=energy;light.data.size=size
        light.rotation_euler=(Vector((18,0,2))-light.location).to_track_quat('-Z','Y').to_euler()
    bpy.ops.object.camera_add(location=(18,-48,3));camera=bpy.context.object
    camera.rotation_euler=(Vector((18,0,3))-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type='ORTHO';camera.data.ortho_scale=42;scene.camera=camera
    results=[]
    for si,spec in enumerate(plan['specimens']):
        for o in [o for o in scene.objects if o.get('approval_fixture')]:bpy.data.objects.remove(o,do_unlink=True)
        calyx=spec['calyx'];length=calyx['length_cm'];radius=calyx['radius_cm'];cells=[]
        stages=[surface_plan(1,2,20261031+si)]+[surface_plan(2,j,20261031+si) for j in range(6)]
        for j,p in enumerate(stages):
            base=sets['class_candidate'][p.class_id];pos=Vector((j*6,0,2))
            obj=create_calyx_mesh(f'approval_{si}_{j}',length,radius*2,calyx['ribs'],0,calyx['inflation'],
                'base',spec['mesh_seed'],profile=calyx['profile'],tip_length_ratio=calyx['tip_length_ratio'],
                wrinkle=calyx['wrinkle'],asymmetry=calyx['asymmetry'],pubescence=calyx['pubescence'],
                vein_contrast=calyx['vein_contrast'],maturity_progress=calyx['maturity_progress'],turgor=calyx['turgor'],
                materials={'base':base},location=pos,calyx_state=calyx['state'])[0]
            obj['approval_fixture']=True;state=deterioration_state(spec['texture_seed'],p.contraction,p.phenotype)
            for vertex in obj.data.vertices:vertex.co=deform_calyx_point(vertex.co,length=length,radius=radius,state=state)
            obj.data.update();mat=make_review_material(base,p,map_manifest=plan['vein_maps_manifest'])
            obj.data.materials[0]=mat
            anchor=pos+Vector((0,0,length*.5))
            ped=_create_cylinder_between(f'ped_{si}_{j}',anchor,anchor+Vector((0,0,spec['pedicel_length_cm'])),.028,sets['candidate']['petiole'],vertices=10);ped['approval_fixture']=True
            bm=bmesh.new();bm.from_mesh(obj.data);bad=sum(not e.is_manifold for e in bm.edges);volume=abs(bm.calc_volume(signed=True));bm.free()
            error=(obj.data.vertices[-2].co-Vector((0,0,length*.5))).length
            if bad or error>1e-6:raise ValueError('Shell fixture topology/attachment invalid')
            coords=[v.co for v in obj.data.vertices];bounds=[max(v[i] for v in coords)-min(v[i] for v in coords) for i in range(3)]
            cells.append(dict(plan=p.to_dict(),shape=state.to_dict(),bbox_cm=bounds,volume_cm3=volume,attachment_error_cm=error,nonmanifold_edges=bad))
        dest=out/f'organs_{si}.png';scene.render.filepath=str(dest);bpy.ops.render.render(write_still=True)
        results.append(dict(image=str(dest),image_sha256=sha(dest),cells=cells));print('APPROVAL_ORGANS_COMPLETE',si,flush=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'organ_fixtures.blend'))
    write(out/'organs_result.json',dict(records=results,scope='isolated hollow calyx fixtures; internal berry compatibility not certified',
        physiological_resorption='unverified mechanism; visible drying/contraction hypothesis',whole_plant_admission=False))


if __name__=='__main__':
    mode,directory=sys.argv[sys.argv.index('--')+1:];out=Path(directory).resolve()
    try:
        plan=read(out/'plan.json');assert read(Path(plan['source'])/'pause_requested.json')['active']
        for path,h in read(out/'source_lock.json')['files'].items():
            if sha(path)!=h:raise ValueError('Frozen source changed: '+path)
        {'context':context,'organs':organs}[mode](out)
    except Exception:
        write(out/f'{mode}_failure.json',dict(traceback=traceback.format_exc()));raise
