"""Small isolated-organ visual fixture; does not open or modify bank scenes."""
from pathlib import Path
import sys,copy,json,math,time
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'src'),str(REPO/'scripts')]
from uchuva_lsystem.nodal_automation import read,write,sha
from uchuva_lsystem.calyx_deterioration import deterioration_state


def render(out):
    import bpy,bmesh
    from mathutils import Vector
    from uchuva_lsystem.blender_scene import cleanup_scene
    from uchuva_lsystem.blender_geometry import create_calyx_mesh,_create_cylinder_between
    from uchuva_lsystem.blender_appearance import create_material_sets
    from uchuva_lsystem.blender_calyx_deterioration import apply_shell_state
    plan=read(out/'plan.json');profiles=read(plan['profiles'])
    for p,h in read(out/'source_lock.json')['files'].items():
        if sha(p)!=h:raise ValueError('Frozen pilot source changed: '+p)
    source=Path(plan['source_campaign']);assert read(source/'pause_requested.json')['active']
    cleanup_scene(include_hidden=True);scene=bpy.context.scene
    scene.render.engine='CYCLES';scene.cycles.samples=32;scene.cycles.use_denoising=True
    scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=.01
    scene.render.resolution_x=1600;scene.render.resolution_y=600;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB'
    scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast'
    scene.view_settings.exposure=0;scene.view_settings.gamma=1
    prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.get_devices()
    for device in prefs.devices:device.use=device.type=='OPTIX'
    scene.cycles.device='GPU'
    sets=create_material_sets(20261031,profiles)
    world=bpy.data.worlds.new('diagnostic_neutral_world');world.use_nodes=True;scene.world=world
    world.node_tree.nodes['Background'].inputs['Color'].default_value=(.65,.68,.72,1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value=.45
    bpy.ops.object.light_add(type='AREA',location=(8,-9,12));key=bpy.context.object;key.name='key';key.data.energy=1100;key.data.shape='DISK';key.data.size=8
    key.rotation_euler=(Vector((12,0,2))-key.location).to_track_quat('-Z','Y').to_euler()
    bpy.ops.object.light_add(type='AREA',location=(18,1,9));fill=bpy.context.object;fill.data.energy=450;fill.data.size=7
    fill.rotation_euler=(Vector((12,0,2))-fill.location).to_track_quat('-Z','Y').to_euler()
    bpy.ops.object.camera_add(location=(12,-40,2.5));camera=bpy.context.object;camera.rotation_euler=(Vector((12,0,2.5))-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type='ORTHO';camera.data.ortho_scale=30;camera.data.clip_start=.01;camera.data.clip_end=200;scene.camera=camera
    records=[]
    for source_index,spec in enumerate(plan['specimens']):
        if source_index:
            for obj in [o for o in bpy.data.objects if o.get('deterioration_fixture')]:bpy.data.objects.remove(obj,do_unlink=True)
        calyx=spec['calyx'];length=calyx['length_cm'];radius=calyx['radius_cm'];base_seed=spec['mesh_seed']
        cells=[]
        for index,stage in enumerate(plan['stages']):
            mat=sets['class_candidate'][stage['class_id']];position=Vector((index*6,0,2))
            obj=create_calyx_mesh(f'fixture_{source_index}_{index}',length,radius*2,calyx['ribs'],0,
                calyx['inflation'],'fixture_base',base_seed,profile=calyx['profile'],
                tip_length_ratio=calyx['tip_length_ratio'],wrinkle=calyx['wrinkle'],asymmetry=calyx['asymmetry'],
                pubescence=calyx['pubescence'],vein_contrast=calyx['vein_contrast'],
                maturity_progress=calyx['maturity_progress'],turgor=calyx['turgor'],
                materials={'fixture_base':mat},location=position,calyx_state=calyx['state'])[0]
            obj['deterioration_fixture']=True
            state=deterioration_state(spec['texture_seed'],stage['severity'],spec.get('phenotype','dark_proximal'))
            apply_shell_state(obj,state,length,radius,mat)
            anchor=position+Vector((0,0,length*.5))
            pedicel=_create_cylinder_between(f'pedicel_{source_index}_{index}',anchor,anchor+Vector((0,0,spec['pedicel_length_cm'])),.028,sets['candidate']['petiole'],vertices=10)
            pedicel['deterioration_fixture']=True
            bm=bmesh.new();bm.from_mesh(obj.data);bad=sum(not e.is_manifold for e in bm.edges);volume=abs(bm.calc_volume(signed=True));bm.free()
            if bad:raise ValueError('Non-manifold diagnostic shell')
            proximal=obj.data.vertices[-2].co
            attachment_error=(proximal-Vector((0,0,length*.5))).length
            if attachment_error>1e-6:raise ValueError('Proximal attachment moved')
            coords=[v.co for v in obj.data.vertices];bounds=[max(v[i] for v in coords)-min(v[i] for v in coords) for i in range(3)]
            cells.append(dict(stage=stage,state=state.to_dict(),bbox_local_extent_cm=bounds,shell_volume_cm3=volume,
                attachment_error_cm=attachment_error,nonmanifold_edges=bad,mesh_vertices=len(obj.data.vertices)))
        for mode in ('field','diffuse'):
            key.data.energy=1100 if mode=='field' else 650;key.data.size=5 if mode=='field' else 12
            world.node_tree.nodes['Background'].inputs['Strength'].default_value=.3 if mode=='field' else .6
            file=out/f'specimen_{source_index}_{mode}.png';scene.render.filepath=str(file);bpy.ops.render.render(write_still=True)
            records.append(dict(specimen=source_index,lighting=mode,image=str(file),image_sha256=sha(file),cells=cells))
            write(out/'progress.json',dict(completed_images=len(records),target_images=4))
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'diagnostic_scene.blend'))
    write(out/'result.json',dict(completed=True,records=records,
        scope='isolated calyx surface/shape fixtures, no whole-plant admission and no internal berry compatibility claim',
        source_plants_modified=False,bank_images_modified=False,training_started=False,
        new_classes=False,grading_status='engineering_heuristic_pending_user_review',
        physiological_resorption='not simulated; observed drying/compression only'))


if __name__=='__main__':render(Path(sys.argv[sys.argv.index('--')+1]).resolve())
