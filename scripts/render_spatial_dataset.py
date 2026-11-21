"""Render only after twenty admitted plants are frozen; no training entry point.

One rich procedural scene per four admitted trees, flattened contextual ground,
rigid plant placement and strict rebuilt scene audits before every view batch.
RGB, exact instance masks and all visible calyx boxes commit together.
"""
from pathlib import Path
import sys,json,math,random,traceback,ctypes,shutil
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'))
import bpy
from mathutils import Vector
from uchuva_lsystem.nodal_automation import read,write,sha,remaining
from uchuva_lsystem.reproductive_space import digest
from uchuva_lsystem.spatial_dataset import depth_stratum,committed_views,select_scene_plants
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.nodal_repulsion import axes
from uchuva_lsystem.scene import CultivationScene,PlantInstance
from uchuva_lsystem.collisions import build_scene_proxies
from uchuva_lsystem.blender_scene import cleanup_scene
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology,audit_scene_mesh_collisions,create_cultivation_supports
from uchuva_lsystem.blender_environment import create_outdoor_environment,audit_plant_ground_clearance,_terrain_height_at
from uchuva_lsystem.blender_reproductive_orientation import audit_calyx_orientation
from uchuva_lsystem.validation import validate_morphology_tree
from uchuva_lsystem.blender_annotations import render_crisp_calyx_annotations,global_reproductive_id
from uchuva_lsystem.blender_appearance import create_material_sets,apply_materials,apply_profile,geometry_digest
from uchuva_lsystem.appearance_diversity import plant_appearance,appearance_assignments
from uchuva_lsystem.support import SupportSystem,SupportPost,SupportLine
from render_appearance_bank import labels_from_mask


def configure():
    s=bpy.context.scene;s.unit_settings.system='METRIC';s.unit_settings.scale_length=.1
    s.render.engine='CYCLES';s.cycles.samples=12;s.cycles.use_denoising=True;s.cycles.device='GPU'
    p=bpy.context.preferences.addons['cycles'].preferences;p.compute_device_type='OPTIX';p.get_devices()
    if not any(d.type=='OPTIX' for d in p.devices):raise ValueError('OptiX unavailable')
    for d in p.devices:d.use=d.type=='OPTIX'
    s.render.resolution_x=960;s.render.resolution_y=720;s.render.resolution_percentage=100
    s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGB'
    s['uchuva_preserve_mask_components']=True


def flatten_context(seed):
    """Move procedural context into flat-bed coordinates, before plants exist."""
    for o in list(bpy.context.scene.objects):
        if o.type!='MESH':continue
        inv=o.matrix_world.inverted()
        for v in o.data.vertices:
            p=o.matrix_world@v.co
            p.z=0. if o.name=='uchuva_terrain_agricultural' else p.z-_terrain_height_at(p.x,p.y,seed)
            v.co=inv@p
        o.data.update()


def build_scene(root,bank,index,pool,profiles):
    scene_id=f'scene_{index:03d}';folder=bank/'scenes'/scene_id;folder.mkdir(parents=True,exist_ok=False)
    config=read(bank/'config.json');count=int(config.get('plants_per_scene',4))
    rng=random.Random(20261029+index);selected=select_scene_plants(pool,count,rng)
    trees=[Plant.from_dict(read(p['plant'])) for p in selected]
    for tree in trees:
        if validate_morphology_tree(tree,stage='adapted')['errors']:raise ValueError('Invalid pool morphology')
    local=[]
    for tree in trees:
        l=CultivationScene('bounds','bounds',tree.seed,plant_instances=[PlantInstance('bounds',tree.seed)])
        proxies=build_scene_proxies(l,{'bounds':tree})
        low=[min(p.aabb()[0][d] for p in proxies) for d in range(3)]
        high=[max(p.aabb()[1][d] for p in proxies) for d in range(3)]
        local.append((low,high))
    gap=float(config.get('crop_gap_bu',3.))
    sx=max(h[0]-l[0] for l,h in local)+gap;sy=max(h[1]-l[1] for l,h in local)+gap
    columns=int(config.get('columns',4 if count>=8 else 2));row_count=math.ceil(count/columns)
    positions=[(((j%columns)-(columns-1)/2)*sx,((j//columns)-(row_count-1)/2)*sy,0) for j in range(count)]
    layout=CultivationScene(scene_id,'admitted_multiplant_cultivation_rows',20261029+index)
    cleanup_scene(include_hidden=True);configure()
    envseed=20271029+index
    modes=config.get('context_modes',profiles.get('context',{}).get('modes',['open_field_hybrid']))
    centres=[(p[0],p[1]) for p in positions]
    if config.get('extra_weed_centres'):
        centres += [(p[0]+sx*.35,p[1]+sy*.35) for p in positions]
        centres += [(p[0]-sx*.35,p[1]-sy*.35) for p in positions]
    floor_plan=None
    if config.get('natural_floor'):
        from uchuva_lsystem.cultivation_floor import plan_cultivation_floor
        root_positions=[(p[0]-(low[0]+high[0])/2,p[1]-(low[1]+high[1])/2,0) for p,(low,high) in zip(positions,local)]
        floor_plan=plan_cultivation_floor(envseed,root_positions,
            (min(p[0] for p in positions)-sx,max(p[0] for p in positions)+sx,
             min(p[1] for p in positions)-sy,max(p[1] for p in positions)+sy))
        centres=floor_plan['vegetation_centres']
    environment=create_outdoor_environment(seed=envseed,scene_radius=max(sx,sy)*2,terrain_size=100,
        terrain_subdivisions=24,background_cluster_count=0,mode=modes[index%len(modes)],
        vegetation_centres=centres,asset_dir=config.get('asset_dir'))
    if config.get('asset_dir') and environment['assets']['missing']:
        raise ValueError('Explicit environment assets missing: '+str(environment['assets']['missing']))
    if config.get('textured_soil'):
        terrain=bpy.data.objects[environment['terrain_object']]
        terrain.data.materials.clear();terrain.data.materials.append(bpy.data.materials['Uchuva_Suelo_agricola_PBR'])
        environment['effective_ground_material']='Uchuva_Suelo_agricola_PBR'
    bpy.context.view_layer.update();flatten_context(envseed)
    if floor_plan is not None:
        from uchuva_lsystem.blender_cultivation_floor import apply_cultivation_floor
        environment['natural_floor']=apply_cultivation_floor(floor_plan,environment['terrain_object'])
        write(folder/'floor_plan.json',floor_plan)
    sets=create_material_sets(20261029+index,profiles);builds=[];assignments={};foliage={}
    for j,(tree,record,pos,(low,high)) in enumerate(zip(trees,selected,positions,local)):
        pid='plant_'+str(tree.seed);position=(pos[0]-(low[0]+high[0])/2,pos[1]-(low[1]+high[1])/2,0)
        inst=PlantInstance(pid,tree.seed,position=position,rotation_deg=0.);layout.plant_instances.append(inst)
        b=build_geometry_from_morphology(tree,sets['previous'],instance_id=pid,position=position,
                                        add_ground=False,defer_scene_update=True);builds.append(dict(b,plant_id=pid))
        v=plant_appearance(20261029,pid,index,j%3,[1,1,1]);foliage[pid]=v
        ids=[n.reproductive_unit.id for a in axes(tree.axes) for n in a.nodes if n.reproductive_unit and n.reproductive_unit.calyx]
        classes=appearance_assignments(tree.seed,pid,ids,v['class_probabilities'])
        assignments.update({global_reproductive_id(pid,u):dict(class_id=c) for u,c in classes.items()})
    bpy.context.view_layer.update()
    plant_objects=[o for o in bpy.context.scene.objects if o.get('uchuva_plant_id') in foliage]
    corners=[o.matrix_world@Vector(v) for o in plant_objects if o.type in {'MESH','CURVE'} for v in o.bound_box]
    posts=[];lines=[]
    support_mode=config.get('support_modes',['horizontal'])[index%len(config.get('support_modes',['horizontal']))]
    for row_index in range(row_count):
        ids={p.plant_id for p in layout.plant_instances[row_index*columns:(row_index+1)*columns]}
        bound=[o.matrix_world@Vector(v) for o in plant_objects if o.get('uchuva_plant_id') in ids and o.type in {'MESH','CURVE'} for v in o.bound_box]
        back=max(v.y for v in bound)+min(.75,gap/2);top=max(v.z for v in bound)+.5
        left=min(v.x for v in bound)-1.;right=max(v.x for v in bound)+1.
        xs=[left+(right-left)*j/columns for j in range(columns+1)]
        posts += [SupportPost(scene_id+f'_r{row_index}_post_{j}',(x,back,0),top,.25,.25,scene_id) for j,x in enumerate(xs)]
        heights=[top*.4,top*.7,top] if support_mode=='horizontal' else [top]
        lines += [SupportLine(scene_id+f'_r{row_index}_wire_{j}',(left,back,z),(right,back,z),.01,scene_id) for j,z in enumerate(heights)]
        if support_mode=='overhead_strings':
            # Reference-inspired slanted strings outside the evaluated crown envelope.
            # No branch is moved and no support attachment is claimed.
            for j in range(columns*5+1):
                x=left+(right-left)*j/(columns*5)
                lines.append(SupportLine(scene_id+f'_r{row_index}_string_{j}',
                    (x,back+.18,.3),(x+.6,back+.18,top),.009,scene_id,'stake_tie'))
    layout.support_system=SupportSystem(scene_id+'_trellis','background_context',posts=posts,lines=lines)
    create_cultivation_supports(layout,sets['previous'],builds);bpy.context.view_layer.update()
    if support_mode=='overhead_strings':
        string_material=bpy.data.materials.new(scene_id+'_pale_support_string');string_material.use_nodes=True
        bsdf=string_material.node_tree.nodes.get('Principled BSDF')
        bsdf.inputs['Base Color'].default_value=(.68,.64,.49,1);bsdf.inputs['Roughness'].default_value=.9
        for o in bpy.context.scene.objects:
            if '_string_' in o.name and hasattr(o.data,'materials'):
                o.data.materials.clear();o.data.materials.append(string_material)
    mesh=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,max_reported_pairs=None,limit_clearance_search=True)
    ground=audit_plant_ground_clearance(seed=envseed,required_clearance_m=.001)
    orientation=audit_calyx_orientation(trees,layout,list(bpy.context.scene.objects))
    for n,v in [('mesh',mesh),('ground',ground),('orientation',orientation),('layout',layout.to_dict()),('environment',environment)]:write(folder/(n+'.json'),v)
    if mesh['physical_collision_count'] or ground['status']!='valid' or orientation['status']!='valid':
        write(folder/'rejected.json',dict(reason='scene_physical_audit',crossings=mesh['physical_collision_count'],ground=ground['status'],orientation=orientation['status']))
        return None
    objects=[o for o in bpy.context.scene.objects if o.get('uchuva_semantic_class')]
    actual={str(o.get('uchuva_reproductive_instance_id')) for o in objects if o.get('uchuva_semantic_class')=='calyx'}
    if actual!=set(assignments):raise ValueError('Scene lost or invented target identities')
    apply_materials(objects,sets,'candidate',assignments,foliage_profiles=foliage,seed=20261029+index)
    bpy.ops.object.camera_add();camera=bpy.context.object;camera.data.sensor_width=36;camera.data.lens=50
    camera.data.clip_start=.01;camera.data.clip_end=1000;bpy.context.scene.camera=camera
    record=dict(scene_id=scene_id,plants=selected,assignments=assignments,foliage=foliage,
        geometry_sha256=geometry_digest(bpy.context.scene),flat_context=True,physical_admission=True,
        generation_variant=config.get('generation_variant','four_plant_open_context_v1'),
        source_lock_sha256=sha(bank/'source_lock.json'),crop_gap_bu=gap,weed_centres=centres,
        support_mode=support_mode,rows=row_count,columns=columns,
        scope='strict crops/ground audit; leaf-leaf soft, proximity warnings; context not exhaustively certified')
    write(folder/'accepted.json',record)
    return record,camera,objects


def camera_background(config,index):
    """Use the cached CC0 field panorama for camera rays; retain LT illumination."""
    if not config.get('asset_dir'):return None
    image=bpy.data.images.get('UchuvaAsset_farmland_overcast_2k')
    if image is None:raise ValueError('Configured panorama was not loaded')
    world=bpy.context.scene.world;n=world.node_tree.nodes;l=world.node_tree.links
    output=next(x for x in n if x.type=='OUTPUT_WORLD');old=output.inputs['Surface'].links[0].from_socket
    env=n.new('ShaderNodeTexEnvironment');env.image=image
    tex=n.new('ShaderNodeTexCoord');mapping=n.new('ShaderNodeMapping');mapping.inputs['Rotation'].default_value[2]=index*.47
    l.new(tex.outputs['Generated'],mapping.inputs['Vector']);l.new(mapping.outputs['Vector'],env.inputs['Vector'])
    bg=n.new('ShaderNodeBackground');bg.inputs['Strength'].default_value=.55;l.new(env.outputs['Color'],bg.inputs['Color'])
    path=n.new('ShaderNodeLightPath');mix=n.new('ShaderNodeMixShader');l.new(path.outputs['Is Camera Ray'],mix.inputs[0])
    l.new(old,mix.inputs[1]);l.new(bg.outputs[0],mix.inputs[2]);l.new(mix.outputs[0],output.inputs['Surface'])
    return dict(asset=image.name,camera_only=True,strength=.55,rotation_rad=index*.47)


def run(root):
    bank=root/'dataset';pool=read(bank/'pool_lock.json')['plants'];assert len(pool)==20
    budget=read(root/'budget.json');profiles=read(root/'profiles.json');lock=read(bank/'source_lock.json')
    def verify():
        for p,h in lock['files'].items():
            if sha(p)!=h:raise ValueError('Dataset source/input changed: '+p)
    verify();existing=committed_views(bank);config=read(bank/'config.json')
    scene_index=0;rejected_scenes=0
    while remaining(budget)>180 and len(existing)<config['max_images']:
        if (bank/'scenes'/f'scene_{scene_index:03d}').exists():scene_index+=1;continue
        write(bank/'state.json',dict(stage='building_scene',scene_index=scene_index,committed_images=len(existing),remaining_seconds=remaining(budget)))
        scene=build_scene(root,bank,scene_index,pool,profiles)
        if scene is None:
            rejected_scenes+=1;scene_index+=1
            if rejected_scenes>=2 and not existing:raise ValueError('Two rebuilt scenes rejected before any usable image; diagnosis required')
            continue
        record,camera,objects=scene;targets=[o for o in objects if o.get('uchuva_semantic_class')=='calyx']
        if config.get('foreground_targets'):
            if config.get('interior_targets'):
                front={p['seed'] for j,p in enumerate(record['plants']) if j%config['columns']==config['columns']//2 and j//config['columns']<2}
            else:front={p['seed'] for p in record['plants'][:config['columns']]}
            targets=[o for o in targets if o.get('uchuva_plant_id') in {'plant_'+str(seed) for seed in front}]
        for index in range(config['views_per_scene']):
            if remaining(budget)<30 or len(existing)>=config['max_images']:break
            if shutil.disk_usage(bank).free<config.get('min_free_bytes',1073741824):
                write(bank/'resource_stop.json',dict(reason='disk_space_reserve'));return
            view_id=f'{record["scene_id"]}_view_{index:03d}';out=bank/'views'/view_id;out.mkdir(parents=True,exist_ok=False)
            rng=random.Random(20261029+scene_index*1000+index);focus=rng.choice(targets)
            center=sum((focus.matrix_world@Vector(v) for v in focus.bound_box),Vector())/8
            stratum=depth_stratum(index);desired={'near':48.,'middle':24.,'far':10.}[stratum]
            span=min(float(d) for d in focus.dimensions if d>0)
            distance=max(2.,min(100.,span*960*50/(36*desired)))
            az=rng.uniform(-math.pi*.56,-math.pi*.44) if config.get('interior_targets') else (rng.uniform(-math.pi*.68,-math.pi*.32) if config.get('foreground_targets') else rng.uniform(-math.pi*.95,-math.pi*.05))
            el=rng.uniform(.05,.28) if config.get('foreground_targets') else rng.uniform(-.08,.25)
            camera.location=center+Vector((math.cos(az),math.sin(az),el)).normalized()*distance
            aim=center+Vector((rng.uniform(-.08,.08)*distance,0,rng.uniform(-.06,.06)*distance))
            camera.rotation_euler=(aim-camera.location).to_track_quat('-Z','Y').to_euler()
            lighting=apply_profile(profiles,'LT',camera,tuple(aim))
            lighting['camera_background']=camera_background(config,scene_index);bpy.context.view_layer.update()
            if geometry_digest(bpy.context.scene)!=record['geometry_sha256']:raise ValueError('Camera or appearance changed geometry')
            s=bpy.context.scene;s.render.filepath=str(out/'rgb.png');bpy.ops.render.render(write_still=True)
            annotation=render_crisp_calyx_annotations(camera,out,width=960,height=720)
            labels,instances=labels_from_mask(annotation,record['assignments'],960,720)
            (out/'labels.txt').write_text(labels,encoding='utf-8');write(out/'annotations.json',annotation)
            if geometry_digest(bpy.context.scene)!=record['geometry_sha256']:raise ValueError('Annotation changed geometry')
            if not instances:
                write(out/'rejected.json',dict(reason='no_visible_target',retained_as_negative_candidate=True));continue
            pose=[[float(v) for v in row] for row in camera.matrix_world]
            row=dict(status='complete',view_id=view_id,scene_id=record['scene_id'],depth_stratum=stratum,
                generation_variant=record['generation_variant'],source_lock_sha256=sha(bank/'source_lock.json'),
                render_config=dict(engine='CYCLES',samples=12,denoising=True,unit_scale_length=.1,width=960,height=720),
                camera_distance_bu=distance,camera_distance_m=distance*.1,camera_matrix=pose,camera_sha256=digest(pose),
                geometry_sha256=record['geometry_sha256'],plant_seeds=[p['seed'] for p in record['plants']],
                instances=instances,lighting=lighting,image=str((out/'rgb.png').resolve()),label=str((out/'labels.txt').resolve()),mask=annotation['path'])
            for k in ['image','label','mask']:row[k+'_sha256']=sha(row[k])
            write(out/'view.json',row);existing.append(row)
            write(bank/'manifest.json',dict(views=existing,complete_images=len(existing),training_started=False,test_images_used=False))
            write(bank/'state.json',dict(stage='rendering_views',scene_index=scene_index,committed_images=len(existing),remaining_seconds=remaining(budget)))
            print('SPATIAL_DATASET',view_id,len(instances),'images',len(existing),flush=True)
        scene_index+=1;verify()
    verify();write(bank/'state.json',dict(stage='complete',committed_images=len(existing),remaining_seconds=remaining(budget),training_started=False))


if __name__=='__main__':
    root=Path(sys.argv[sys.argv.index('--')+1]).resolve()
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001);run(root)
    except Exception:
        write(root/'dataset/failure.json',dict(traceback=traceback.format_exc()));raise
    finally:ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
