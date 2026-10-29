"""One new-seed pose search followed by automatic strict spatial admission."""
from pathlib import Path
import sys,json,hashlib,traceback,os,ctypes
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import bpy
from uchuva_lsystem.nodal_automation import read,write,sha,remaining,mesh_objective,physically_admitted
from uchuva_lsystem.execution_budget import awake_seconds
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.nodal_repulsion import (KEY,axes,protected_anatomy,initialize_growth_poses,
    resolve_nodal_repulsion,revise_pedicel_mobility,restore_calyx_toward_gravity)
from uchuva_lsystem.blender_scene import cleanup_scene,create_project_materials,create_material
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology,audit_scene_mesh_collisions
from uchuva_lsystem.blender_environment import audit_plant_ground_clearance
from uchuva_lsystem.blender_reproductive_orientation import audit_calyx_orientation
from uchuva_lsystem.blender_pose_repair_v2 import repair_size_preserving_poses
from uchuva_lsystem.blender_nodal_branch_repair import repair_nodal_branches
from uchuva_lsystem.blender_nodal_local_repair import repair_local_nodal_contacts
from uchuva_lsystem.validation import validate_morphology_tree
from uchuva_lsystem.scene import CultivationScene,PlantInstance
from uchuva_lsystem.spatial_admission import make_plan,validate_plan,replay_pose,eligible_organs,KEY as SPACE_KEY


def contact_options(plant,mesh):
    """Resolve complete organ groups from the real Blender identity tags."""
    if mesh.get('truncated'):raise ValueError('A truncated audit cannot drive admission')
    eligible=eligible_organs(plant);leaf_ids={x[5:] for x in eligible if x.startswith('leaf:')}
    fruit_ids={x[6:] for x in eligible if x.startswith('fruit:')}
    mapping={}
    for obj in bpy.context.scene.objects:
        unit=str(obj.get('uchuva_reproductive_id',''));organ=str(obj.get('uchuva_organ_id',''))
        if unit in fruit_ids:mapping[obj.name]='fruit:'+unit;continue
        for suffix in ('_petiole','_midrib',''):
            leaf=organ[:-len(suffix)] if suffix and organ.endswith(suffix) else organ if not suffix else ''
            if leaf in leaf_ids:mapping[obj.name]='leaf:'+leaf;break
    return [[mapping[n] for n in (row['object_a'],row['object_b']) if n in mapping]
            for row in mesh['physical_collisions']]


def run(job_path):
    job=read(job_path);folder=Path(job['folder']);run_root=Path(job['run_root'])
    config=read(run_root/'config.json');budget=read(run_root/'budget.json');lock=read(run_root/'source_lock.json')
    def time_left():return min(remaining(budget),max(0.,job['active_deadline']-awake_seconds()))
    def search_left():return 0. if space_plan is not None else max(0.,time_left()-config['qualification_reserve_seconds'])
    def allowance(seconds):return max(.01,min(seconds,search_left()-3))
    def verify_sources():
        if lock.get('seed_queue_sha256') and sha(run_root/'seed_queue.json')!=lock['seed_queue_sha256']:
            raise RuntimeError('Frozen seed queue changed')
        if lock.get('continuations_sha256') and sha(run_root/'continuations.json')!=lock['continuations_sha256']:
            raise RuntimeError('Frozen continuation inputs changed')
        for relative,digest in lock['sources'].items():
            if sha(ROOT/relative)!=digest:raise RuntimeError('Frozen source changed: '+relative)
        for name in ('config','profiles'):
            if sha(run_root/(name+'.json'))!=lock[name+'_sha256']:
                raise RuntimeError('Frozen configuration changed: '+name)
    verify_sources()
    folder.mkdir(parents=True,exist_ok=True);started=awake_seconds();last_checkpoint=started
    write(folder/'identity.json',dict(pid=__import__('os').getpid(),job=job,started_awake=started))
    history=[];best=None;best_payload=None;space_plan=None;space_payload=None;stage='generation';round_number=-1
    def status(stage_name,**kwargs):
        nonlocal stage
        stage=stage_name
        write(folder/'state.json',dict(seed=job['seed'],stage=stage,round=round_number,
            active_elapsed_seconds=awake_seconds()-started,time_remaining_seconds=time_left(),
            best_crossings=None if best is None else best[0],**kwargs))
    status('generation')
    if job.get('raw'):
        assert sha(job['raw'])==job['raw_sha256']
        raw=Plant.from_dict(read(job['raw']))
    else:
        raw=generate_morphology_tree(job['seed'],preset_name='trained_trellis_nodal_repulsion_v8',
            phenology_model='literature_cohort_v1',resolve_growth=False)
    write(folder/'raw.json',raw.to_dict());invariant=protected_anatomy(raw)
    original_invariant=invariant
    if job.get('initial'):
        assert sha(job['initial'])==job['initial_sha256']
        plant=Plant.from_dict(read(job['initial']))
    else:plant=Plant.from_dict(raw.to_dict())
    if protected_anatomy(plant)!=invariant:raise RuntimeError('Initial input changed anatomy')
    def checkpoint(p,row):
        nonlocal last_checkpoint
        if protected_anatomy(p)!=invariant:raise RuntimeError('Correction changed anatomy')
        with (folder/'adjustments.jsonl').open('a',encoding='utf-8') as handle:
            handle.write(json.dumps(dict(stage=stage,round=round_number,adjustment=row),ensure_ascii=False)+'\n')
        if awake_seconds()-last_checkpoint>=15:
            write(folder/'checkpoint.json',p.to_dict());last_checkpoint=awake_seconds()
    if not job.get('initial') and search_left()>config['proxy_seconds']+20:
        status('proxy_growth')
        resolve_nodal_repulsion(plant,sweeps=4,max_seconds=allowance(config['proxy_seconds']),checkpoint=checkpoint)
    initialize_growth_poses(plant)
    revise_pedicel_mobility(plant,config['pedicel_excursion_deg'],reason='Frozen automated physical-review search; no organ or dimension change; calyx remains pendulous')
    bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=.1
    def rebuild():
        cleanup_scene(include_hidden=True)
        bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,0))
        terrain=bpy.context.object;terrain.name='uchuva_terrain_agricultural'
        materials=create_project_materials(plant.seed)
        terrain.data.materials.append(create_material('nodal_review_soil',(.14,.105,.055,1),roughness=.95))
        build_geometry_from_morphology(plant,materials,instance_id='growth',add_ground=False,defer_scene_update=True)
        bpy.context.view_layer.update()
        return materials,terrain
    def audit(label):
        nonlocal best,best_payload,space_plan,space_payload
        mesh=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,max_reported_pairs=None,limit_clearance_search=True)
        write(folder/(label+'_mesh.json'),mesh)
        row=dict(stage=label,crossings=mesh['physical_collision_count'],proximity_warnings=mesh['clearance_violation_count'])
        history.append(row);write(folder/'history.json',history)
        objective=mesh_objective(mesh)
        if best is None or objective<best:
            best=objective;best_payload=plant.to_dict();write(folder/'best_plant.json',best_payload)
            write(folder/'best_state.json',dict(objective=list(best),stage=label,independent_reconstruction=True))
        if config.get('automatic_spatial_admission') and SPACE_KEY not in plant.metadata and space_plan is None:
            try:
                proposal=make_plan(plant,contact_options(plant,mesh),evidence_sha256=sha(folder/(label+'_mesh.json')))
                space_plan=proposal;space_payload=plant.to_dict()
                write(folder/'feasible_space_plan.json',proposal)
                write(folder/'space_source_pose.json',space_payload)
            except ValueError as error:
                write(folder/(label+'_space_rejection.json'),dict(reason=str(error),loss_guards='each strictly below5% of original'))
        print('AUTO_MESH',job['seed'],row,flush=True)
        return mesh
    def hard_units(mesh):
        result=set()
        for row in mesh['physical_collisions']:
            for side in ('a','b'):
                if row['semantic_'+side]!='calyx':continue
                obj=bpy.data.objects.get(row['object_'+side])
                if obj:result.add(str(obj.get('uchuva_reproductive_id')))
        return result
    status('initial_build');materials,terrain=rebuild();mesh=audit('initial_independent')
    for round_number in range(0 if job.get('audit_only') else config['rounds']):
        if not mesh['physical_collision_count'] or search_left()<20:break
        status('leaf_correction')
        result=repair_size_preserving_poses(plant,materials,instance_id='growth',max_passes=2,
            max_trials_per_organ=120,max_seconds=allowance(config['leaf_seconds']),growth_joint_policy=True,
            repair_clearance=False,organ_kinds=('leaf',),ground_clearance_m=.001,terrain_object=terrain,checkpoint=checkpoint)
        write(folder/f'round_{round_number}_leaf.json',result)
        if search_left()<15:break
        status('reproductive_coordination')
        result=repair_size_preserving_poses(plant,materials,instance_id='growth',max_passes=2,
            max_trials_per_organ=140,max_seconds=allowance(config['reproductive_seconds']),growth_joint_policy=True,
            repair_clearance=False,organ_kinds=('reproductive',),ground_clearance_m=.001,terrain_object=terrain,checkpoint=checkpoint)
        write(folder/f'round_{round_number}_reproductive.json',result)
        status('independent_rebuild');materials,terrain=rebuild();mesh=audit(f'round_{round_number}_coordinate_independent')
        if not mesh['physical_collision_count'] or search_left()<25:break
        if mesh['physical_collision_count']>config.get('branch_trigger_crossings',64):
            write(folder/f'round_{round_number}_plant.json',plant.to_dict())
            continue
        status('branch_correction')
        result=repair_nodal_branches(plant,passes=1,max_seconds=allowance(config['branch_seconds']),
            defer_leaf_contacts=True,checkpoint=checkpoint)
        write(folder/f'round_{round_number}_branch.json',result)
        status('independent_rebuild');materials,terrain=rebuild();mesh=audit(f'round_{round_number}_branch_independent')
        if not mesh['physical_collision_count'] or search_left()<25:break
        if mesh['physical_collision_count']<=config['local_trigger_crossings'] or round_number>0:
            status('automatic_local_joints')
            result=repair_local_nodal_contacts(plant,mesh,max_nodes=2,max_trials=32,
                max_seconds=allowance(config['local_seconds']),checkpoint=checkpoint,
                candidate_modes=config.get('local_candidate_modes',('counterbend_pair','fixed_pair')))
            write(folder/f'round_{round_number}_local.json',result)
            status('independent_rebuild');materials,terrain=rebuild();mesh=audit(f'round_{round_number}_local_independent')
        if not mesh['physical_collision_count'] or search_left()<20:break
        units=hard_units(mesh);fraction=.5 if round_number==0 else 1.
        active={u.id:u for a in axes(plant.axes) for n in a.nodes if (u:=n.reproductive_unit) is not None}
        units={k for k in units if active[k].provenance.get(KEY,{}).get('fraction',0)<fraction}
        if units:
            status('automatic_gravity_restoration',units=sorted(units),fraction=fraction)
            restore_calyx_toward_gravity(plant,units,fraction=fraction)
            write(folder/f'round_{round_number}_gravity.json',dict(units=sorted(units),fraction=fraction,only_more_downward=True))
            materials,terrain=rebuild();mesh=audit(f'round_{round_number}_gravity_independent')
        write(folder/f'round_{round_number}_plant.json',plant.to_dict())
        if search_left()<config['minimum_round_seconds']:break
    # A final organ pass may stop before its normal reconstruction. Qualify it
    # while the reserved time remains; never silently discard its improvements.
    if stage=='leaf_correction' and time_left()>90:
        status('last_provisional_independent_rebuild')
        materials,terrain=rebuild();mesh=audit('last_provisional_independent')
    # A worse provisional perturbation never replaces the best fully audited tree.
    if space_plan is not None:
        source_pose=Plant.from_dict(space_payload)
        plant=generate_morphology_tree(raw.seed,params=raw.metadata['effective_parameters'],
            phenology_profile=raw.metadata['phenology_profile'],phenology_model=raw.metadata['phenology_model'],
            resolve_growth=False,spatial_admission_plan=space_plan)
        replay_pose(source_pose,plant);invariant=protected_anatomy(plant)
        write(folder/'space_admission_plan.json',space_plan)
        write(folder/'space_validation.json',validate_plan(plant))
    else:plant=Plant.from_dict(best_payload)
    status('final_independent_rebuild')
    materials,terrain=rebuild();mesh=audit('final_independent')
    ground=audit_plant_ground_clearance(seed=plant.seed,terrain_object=terrain,required_clearance_m=.001)
    layout=CultivationScene('automated_nodal','automated_nodal',plant.seed,plant_instances=[PlantInstance('growth',plant.seed)])
    orientation=audit_calyx_orientation([plant],layout,list(bpy.context.scene.objects))
    morphology=validate_morphology_tree(plant,stage='adapted')
    for name,value in [('ground',ground),('orientation',orientation),('morphology',morphology)]:write(folder/(name+'.json'),value)
    assert protected_anatomy(plant)==invariant
    write(folder/'plant.json',plant.to_dict());verify_sources()
    admitted=physically_admitted(mesh,ground,orientation,morphology,invariant,protected_anatomy(plant))
    result=dict(status='admitted' if admitted else 'not_admitted',seed=job['seed'],anatomy_sha256=invariant['sha256'],counts=invariant['counts'],
        original_counts=original_invariant['counts'],spatial_admission=validate_plan(plant),
        physical_crossings=mesh['physical_collision_count'],proximity_warnings=mesh['clearance_violation_count'],
        ground_status=ground['status'],orientation_status=orientation['status'],morphology_errors=morphology['errors'],
        plant=str(folder/'plant.json'),raw=str(folder/'raw.json'),folder=str(folder),
        source_lock_sha256=sha(run_root/'source_lock.json'),active_elapsed_seconds=awake_seconds()-started,
        scope='same strict audited scope; leaf-leaf soft; proximity warnings; no exhaustive flower/context certification; flat diagnostic ground',
        anatomy_before=invariant,anatomy_after=protected_anatomy(plant),new_training_started=False)
    write(folder/'admission.json',result);status('admitted' if admitted else 'not_admitted')
    show_rejected=job.get('render_rejected_preview',False) or (config.get('diagnostic_rejected_previews') and job['index']<4)
    if (admitted or show_rejected) and job.get('render_preview',config['previews']) and time_left()>20:
        try:
            status('preview')
            render_preview(plant,raw,folder,run_root,job['index'],admitted=admitted)
            result['preview' if admitted else 'diagnostic_preview']=str(folder/('preview.png' if admitted else 'rejected_preview.png'));write(folder/'admission.json',result)
        except Exception:
            write(folder/'preview_failure.json',dict(traceback=traceback.format_exc(),physical_admission_preserved=True))
    result['active_elapsed_seconds']=awake_seconds()-started
    write(folder/'completion.json',result)


def render_preview(plant,raw,folder,run_root,index,*,admitted=True):
    from mathutils import Vector
    from uchuva_lsystem.collisions import build_scene_proxies
    from uchuva_lsystem.blender_appearance import create_material_sets,apply_materials,apply_profile,geometry_digest
    from uchuva_lsystem.appearance_diversity import plant_appearance,appearance_assignments
    profiles=read(run_root/'profiles.json');before=geometry_digest(bpy.context.scene)
    layout=CultivationScene('preview','preview',raw.seed,plant_instances=[PlantInstance('growth',raw.seed)])
    proxies=build_scene_proxies(layout,{'growth':raw})
    low=[min(p.aabb()[0][d] for p in proxies) for d in range(3)];high=[max(p.aabb()[1][d] for p in proxies) for d in range(3)]
    target=Vector([(a+b)/2 for a,b in zip(low,high)]);span=max(b-a for a,b in zip(low,high))
    position=target+Vector((.32,-1,.24)).normalized()*span*2.5
    bpy.ops.object.camera_add(location=position);camera=bpy.context.object;camera.data.lens=48;camera.data.clip_end=500
    camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler();bpy.context.scene.camera=camera
    sets=create_material_sets(plant.seed,profiles);visual=plant_appearance(20261027,'growth',0,index%3,[1,1,1])
    ids=[n.reproductive_unit.id for a in axes(plant.axes) for n in a.nodes if n.reproductive_unit and n.reproductive_unit.calyx]
    classes=appearance_assignments(plant.seed,'growth',ids,visual['class_probabilities'])
    assignments={'growth:'+k:dict(class_id=v) for k,v in classes.items()}
    apply_materials(list(bpy.context.scene.objects),sets,'candidate',assignments,foliage_profiles={'growth':visual},seed=plant.seed)
    lighting=apply_profile(profiles,'LT',camera,tuple(target))
    assert geometry_digest(bpy.context.scene)==before,'Appearance or camera changed geometry'
    write(folder/'preview_configuration.json',dict(camera_position=list(position),target=list(target),lens_mm=48,
        basis='raw original crown; independent of repair',foliage=visual,assignments=assignments,lighting=lighting,geometry_sha256=before))
    scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=12;scene.cycles.use_denoising=True;scene.cycles.device='GPU'
    preferences=bpy.context.preferences.addons['cycles'].preferences;preferences.compute_device_type='OPTIX';preferences.get_devices()
    for device in preferences.devices:device.use=device.type=='OPTIX'
    scene.render.resolution_x=800;scene.render.resolution_y=700;scene.render.resolution_percentage=100
    stem='preview' if admitted else 'rejected_preview'
    scene.render.image_settings.file_format='PNG';scene.render.filepath=str(folder/(stem+'_pending.png'))
    bpy.ops.render.render(write_still=True)
    (folder/(stem+'_pending.png')).replace(folder/(stem+'.png'))


if __name__=='__main__':
    path=Path(sys.argv[sys.argv.index('--')+1])
    power_record=None
    try:
        if os.name=='nt':
            power_record=Path(read(path)['folder'])/'power_request.json'
            requested=ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
            write(power_record,dict(requested=bool(requested),transient=True,permanent_settings_changed=False))
        run(path)
    except Exception:
        job=read(path);write(Path(job['folder'])/'failure.json',dict(traceback=traceback.format_exc(),new_training_started=False))
        raise
    finally:
        if os.name=='nt':
            released=ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            if power_record and power_record.exists():
                record=read(power_record);record['released']=bool(released);write(power_record,record)
