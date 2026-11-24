"""CPU-only diagnostic snapshots; never writes bank selection/training files."""
from __future__ import annotations
import argparse
import math
from pathlib import Path
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'src'),str(REPO/'scripts')]
from appearance_campaign import read,write,sha,awake_seconds,process_identity


def main(out):
    import bpy
    from mathutils import Matrix, Vector
    from mathutils.bvhtree import BVHTree
    from uchuva_lsystem.morphology import Plant
    from uchuva_lsystem.appearance_profiles import component_seed
    from uchuva_lsystem.blender_scene import cleanup_scene
    from uchuva_lsystem.blender_geometry import build_geometry_from_morphology,create_cultivation_supports
    from uchuva_lsystem.blender_environment import create_outdoor_environment
    from uchuva_lsystem.blender_appearance import create_material_sets,apply_materials,apply_profile,geometry_digest
    from uchuva_lsystem.scene import CultivationScene,PlantInstance,CultivationSupport
    from uchuva_lsystem.support import SupportSystem,SupportPost,SupportLine
    from uchuva_lsystem.blender_annotations import camera_metadata
    start=awake_seconds();manifest=read(out/'input_manifest.json');root=Path(manifest['campaign'])
    source_lock=Path(manifest.get('source_lock_path',root/'banks/source_lock.json'))
    assert sha(source_lock)==manifest['bank_source_lock_sha256']
    for path,expected in read(source_lock)['files'].items():assert sha(path)==expected
    assert sha(out/'profiles.json')==manifest['profiles_sha256']
    profiles=read(out/'profiles.json');seed=profiles['seed'];scene_id='scene_00'
    cleanup_scene(include_hidden=True);scene=bpy.context.scene
    scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=.125
    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=8
    scene.cycles.use_denoising=True;scene.cycles.denoiser='OPENIMAGEDENOISE'
    scene.render.threads_mode='FIXED';scene.render.threads=2
    scene.render.resolution_x=768;scene.render.resolution_y=576;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB'
    env_seed=component_seed(seed,'bank_context',scene_id)
    env=create_outdoor_environment(seed=env_seed,scene_radius=18,terrain_size=64,terrain_subdivisions=24,
        background_cluster_count=0,mode=profiles['context']['modes'][0],vegetation_centres=[(-8.,0.),(8.,0.)])
    bpy.context.view_layer.update();terrain=bpy.data.objects['uchuva_terrain_agricultural']
    bvh=BVHTree.FromObject(terrain,bpy.context.evaluated_depsgraph_get());inverse=terrain.matrix_world.inverted()
    sets=create_material_sets(component_seed(seed,'bank_material',scene_id),profiles)
    layout=CultivationScene(scene_id=scene_id,preset_name='diagnostic_snapshot',seed=seed)
    assignments={};foliage={};builds=[]
    for row in manifest['plants']:
        assert sha(row['path'])==row['sha256'];plant=Plant.from_dict(read(row['path']))
        index=row['index'];identity=row['plant_id'];x=(index-.5)*16
        hit=bvh.ray_cast(inverse@Vector((x,0,1000.)),Vector((0,0,-1)));assert hit[0] is not None
        z=float((terrain.matrix_world@hit[0]).z)
        rotation=component_seed(seed,'bank_orientation',identity)%360
        instance=PlantInstance(plant_id=identity,seed=plant.seed,position=(x,0,z),rotation_deg=rotation,role='foreground')
        layout.plant_instances.append(instance)
        build=build_geometry_from_morphology(plant,sets['previous'],instance_id=identity,position=instance.position,
            rotation_deg=rotation,plant_scale=1.,add_ground=False,defer_scene_update=True)
        builds.append(dict(build,plant_id=identity));foliage[identity]=row['foliage']
        def visit(axes):
            for axis in axes:
                for node in axis.nodes:
                    unit=node.reproductive_unit
                    if unit and unit.calyx:
                        c=unit.provenance['appearance_pilot']['class_id']
                        assignments[identity+':'+unit.id]=dict(class_id=c)
                visit(axis.child_axes)
        visit(plant.axes)
        layout.supports.append(CultivationSupport(identity+'_stake',identity,(x+.7,.5,z),12.,.08,
            section_width=.12,section_depth=.15,tie_heights=[]))
    layout.support_system=SupportSystem(id=scene_id+'_background_trellis',mode='background_context',
        posts=[SupportPost(f'{scene_id}_post_{i}',(x,8.,0.),20.,.26,.30,scene_id) for i,x in enumerate((-24.,-8.,8.,24.))],
        lines=[SupportLine(f'{scene_id}_top_{i}',(-24.,8.,z),(24.,8.,z),.012,scene_id) for i,z in enumerate((17.,20.))]+
              [SupportLine(f'{scene_id}_string_{i}',(x,8.,20.),(x,8.,.8),.007,scene_id) for i,x in enumerate(range(-22,23,3))])
    bpy.context.view_layer.update()
    bounds=[o.matrix_world@Vector(v) for o in scene.objects if o.get('uchuva_plant_id') in foliage
        and o.type in {'MESH','CURVE','SURFACE'} for v in o.bound_box]
    plane=max(v.y for v in bounds)+.7
    for stake in layout.supports:stake.position=(stake.position[0],plane,stake.position[2])
    create_cultivation_supports(layout,sets['previous'],builds)
    objects=[o for o in scene.objects if o.get('uchuva_semantic_class')]
    apply_materials(objects,sets,'candidate',assignments,foliage_profiles=foliage,seed=seed)
    bpy.ops.object.camera_add();camera=bpy.context.object;scene.camera=camera
    camera.data.sensor_width=36;camera.data.clip_start=.01;camera.data.clip_end=250
    views=[]
    for i,row in enumerate(manifest['plants']):
        own=[o for o in scene.objects if o.get('uchuva_plant_id')==row['plant_id'] and not o.hide_render
             and o.get('uchuva_semantic_class') in {'leaf','calyx','stem','flower'}]
        points=[o.matrix_world@Vector(v) for o in own for v in o.bound_box]
        low=Vector(tuple(min(v[d] for v in points) for d in range(3)))
        high=Vector(tuple(max(v[d] for v in points) for d in range(3)))
        target=(low+high)*.5;span=max(high.x-low.x,(high.z-low.z)*768/576)*1.12
        distance=span*40/36
        views.append((f'plant_{i}_context',target+Vector((-.18,-1,.16)).normalized()*distance,target,40.,
                      'Diagnostic whole-crown view; camera fit for inspection, not a selected bank camera'))
    calyces=[o for o in scene.objects if o.get('uchuva_semantic_class')=='calyx'
             and assignments.get(str(o.get('uchuva_reproductive_instance_id')),{}).get('class_id') in (1,2)]
    focus=min(calyces,key=lambda o:o.matrix_world.translation.y)
    target=focus.matrix_world.translation.copy()
    views.append(('capachos_detail',target+Vector((.7,-3.6,.6)),target,50.,
                  'Diagnostic close view of existing mature/overmature appearance; not selected training image'))
    if manifest.get('fixed_cameras'):
        views=[view for view in views if view[0] in manifest['fixed_cameras']]
    bpy.context.view_layer.update();geometry=geometry_digest(scene)
    for name,position,target,lens,note in views:
        camera.location=position;camera.rotation_euler=(target-position).to_track_quat('-Z','Y').to_euler();camera.data.lens=lens
        if name in manifest.get('fixed_cameras',{}):
            fixed=manifest['fixed_cameras'][name]
            camera.matrix_world=Matrix(fixed['matrix_world']);camera.data.lens=fixed['lens_mm']
            target=Vector(manifest['fixed_light_targets'][name])
        effective=apply_profile(profiles,'LT',camera,target);bpy.context.view_layer.update()
        assert scene.cycles.device=='CPU' and geometry_digest(scene)==geometry
        scene.render.filepath=str(out/(name+'.png'));bpy.ops.render.render(write_still=True)
        # Sparse CPU ray samples support a preliminary image-colour diagnostic.
        # They are not exported as annotation masks or used for training.
        frame=camera.data.view_frame(scene=scene);x0=min(v.x for v in frame);x1=max(v.x for v in frame)
        y0=min(v.y for v in frame);y1=max(v.y for v in frame);z=frame[0].z
        rotation=camera.matrix_world.to_quaternion();dg=bpy.context.evaluated_depsgraph_get();samples=[]
        for y in range(96):
            for x in range(128):
                direction=rotation@Vector((x0+(x+.5)/128*(x1-x0),y1-(y+.5)/96*(y1-y0),z))
                hit=scene.ray_cast(dg,camera.location,direction.normalized(),distance=250)
                obj=hit[4] if hit[0] else None
                identity=str(obj.get('uchuva_reproductive_instance_id','')) if obj else ''
                record=assignments.get(identity) if obj and obj.get('uchuva_semantic_class')=='calyx' else None
                samples.append(dict(x=x,y=y,instance_id=identity if record else None,class_id=record['class_id'] if record else None))
        write(out/(name+'.json'),dict(name=name,image=str(out/(name+'.png')),image_sha256=sha(out/(name+'.png')),
            scope=note,provisional=True,training_eligible=False,geometry_sha256=geometry,camera=camera_metadata(camera,768,576),
            effective_profile=effective,render=dict(device='CPU',samples=8,denoiser='OPENIMAGEDENOISE',threads=2),
            ray_grid=[128,96],ray_samples=samples))
        print('PROVISIONAL_PREVIEW',name,flush=True)
    write(out/'completion.json',dict(complete=True,images=len(views),provisional=True,training_eligible=False,
        script_sha256=sha(__file__),source_manifest_sha256=sha(out/'input_manifest.json'),
        awake_seconds=awake_seconds()-start,accounting=manifest.get('accounting','Parallel CPU diagnostic inside the live bank active-time window; no second GPU workload')))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
    out=args.output.resolve()
    if read(out/'input_manifest.json').get('own_charged_job'):
        from appearance_campaign import charged_job
        with charged_job(Path(read(out/'input_manifest.json')['campaign']),phase='render',job_id='pendulous_diagnostic'):
            main(out)
    else:
        main(out)
