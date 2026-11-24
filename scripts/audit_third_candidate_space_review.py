"""Independent mesh/ground/orientation audit and fixed-camera single-plant view.

Never trains, launches another seed, deletes interpreted organs or relaxes the
historical physical criteria. The omission happens in the regenerated Plant.
"""
from pathlib import Path
from array import array
import ctypes
import hashlib
import json
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
import bpy
from mathutils import Vector
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.scene import CultivationScene, PlantInstance
from uchuva_lsystem.nodal_repulsion import axes, protected_anatomy
from uchuva_lsystem.reproductive_space import validate_admission
from uchuva_lsystem.validation import validate_morphology_tree
from uchuva_lsystem.blender_scene import cleanup_scene, create_project_materials, create_material
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology, audit_scene_mesh_collisions
from uchuva_lsystem.blender_environment import audit_plant_ground_clearance
from uchuva_lsystem.blender_reproductive_orientation import audit_calyx_orientation


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def read(path): return json.loads(path.read_text(encoding='utf-8'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_mesh_hash(vertices, polygons):
    """Exact world geometry, invariant to bmesh's vertex/face enumeration.

    No rounding or tolerance. Vertex multiplicity and oriented polygon cycles
    are retained. This compares embedded faces, not arbitrary vertex indices.
    """
    points = [tuple(p) for p in vertices]
    faces = []
    for poly in polygons:
        cycle = tuple(points[i] for i in poly)
        faces.append(min(cycle[i:]+cycle[:i] for i in range(len(cycle))))
    value = [sorted(points), sorted(faces)]
    return hashlib.sha256(json.dumps(value,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def manifest():
    """World vertices, topology and identity, including the hidden fruits."""
    result = {}
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in bpy.context.scene.objects:
        if not obj.get('uchuva_organ_id') or obj.type not in {'MESH','CURVE'}:
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            points = [tuple(evaluated.matrix_world @ v.co) for v in mesh.vertices]
            vertices = array('d', (c for v in points for c in v))
            topology = array('I', (i for poly in mesh.polygons for i in (len(poly.vertices), *poly.vertices)))
            result[obj.name] = dict(unit_id=str(obj.get('uchuva_reproductive_id','')),
                organ_id=str(obj.get('uchuva_organ_id')), kind=str(obj.get('uchuva_organ_kind','')),
                semantic=str(obj.get('uchuva_semantic_class','')), hidden_render=bool(obj.hide_render),
                world_mesh_sha256=canonical_mesh_hash(points,[tuple(p.vertices) for p in mesh.polygons]),
                enumeration_sha256=hashlib.sha256(vertices.tobytes()+topology.tobytes()).hexdigest())
        finally: evaluated.to_mesh_clear()
    if not result: raise ValueError('No tagged organ geometry in the independent scene')
    return result


def main(out):
    out.mkdir(parents=True, exist_ok=True)
    prior = ROOT/'outputs/nodal_controller_automation_20261027/plants/seed_2026102602_retry03'
    plant = Plant.from_dict(read(out/'plant.json'))
    original = Plant.from_dict(read(prior/'plant.json'))
    assert plant.seed == original.seed == 2026102602
    lock = read(out/'source_lock.json')
    def verify():
        for p, h in lock['files'].items():
            if sha(ROOT/p) != h: raise ValueError('Frozen source/input changed: '+p)
    verify()
    bpy.context.scene.unit_settings.system='METRIC'
    bpy.context.scene.unit_settings.scale_length=.1
    def rebuild(tree):
        cleanup_scene(include_hidden=True)
        bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,0))
        terrain=bpy.context.object;terrain.name='uchuva_terrain_agricultural'
        terrain.data.materials.append(create_material('review_soil',(.14,.105,.055,1),roughness=.95))
        build_geometry_from_morphology(tree,create_project_materials(tree.seed),
            instance_id='growth',add_ground=False,defer_scene_update=True)
        bpy.context.view_layer.update()
        return terrain
    write(out/'audit_state.json', dict(stage='baseline_independent_rebuild', seed=plant.seed))
    rebuild(original)
    before_mesh = audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,
        max_reported_pairs=None,limit_clearance_search=True)
    assert before_mesh['physical_collision_count'] == 3
    write(out/'baseline_mesh.json', before_mesh)
    before = manifest(); write(out/'baseline_object_manifest.json', before)
    write(out/'audit_state.json', dict(stage='corrected_independent_rebuild', seed=plant.seed))
    terrain = rebuild(plant)
    after = manifest(); write(out/'final_object_manifest.json', after)
    omitted = set(read(out/'admission_plan.json')['selected_units'])
    expected = {k:v for k,v in before.items() if v['unit_id'] not in omitted}
    missing = sorted(set(expected)-set(after)); extra = sorted(set(after)-set(expected))
    def geometric_record(v): return {k:x for k,x in v.items() if k!='enumeration_sha256'}
    changed = sorted(k for k in set(expected)&set(after) if geometric_record(expected[k]) != geometric_record(after[k]))
    reindexed = sorted(k for k in set(expected)&set(after)
                      if expected[k]['enumeration_sha256'] != after[k]['enumeration_sha256'])
    equality = dict(retained_object_count=len(expected), removed_object_count=len(before)-len(expected),
                    missing=missing,extra=extra,changed=changed,
                    all_retained_world_vertices_and_faces_identical=not(missing or extra or changed),
                    changed_raw_enumeration=reindexed,comparison='Exact canonical points and oriented faces; no tolerance or rounding',
                    omitted_whole_units=sorted(omitted),hidden_fruits_included=True)
    write(out/'geometry_comparison.json', equality)
    assert equality['all_retained_world_vertices_and_faces_identical'], equality
    final_mesh = audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,
        max_reported_pairs=None,limit_clearance_search=True)
    ground = audit_plant_ground_clearance(seed=plant.seed,terrain_object=terrain,required_clearance_m=.001)
    layout = CultivationScene('third_candidate','space_admission_review',plant.seed,
                             plant_instances=[PlantInstance('growth',plant.seed)])
    orientation = audit_calyx_orientation([plant],layout,list(bpy.context.scene.objects))
    morphology = validate_morphology_tree(plant,stage='adapted')
    for name, value in [('final_mesh',final_mesh),('ground',ground),('orientation',orientation),('morphology',morphology)]:
        write(out/(name+'.json'),value)
    space = validate_admission(plant)
    calyces = [x for x in after.values() if x['semantic']=='calyx']
    fruit_objects = [x for x in after.values() if x['kind']=='fruit']
    counts = protected_anatomy(plant)['counts']
    assert len(calyces) == counts['calyces'] == 405
    assert len(fruit_objects) == counts['fruits'] == 405
    passed = (final_mesh['physical_collision_count']==0 and ground['status']=='valid'
              and orientation['status']=='valid' and not morphology['errors'])
    result = dict(status='admitted' if passed else 'not_admitted',seed=plant.seed,
        counts=counts,physical_crossings=final_mesh['physical_collision_count'],
        proximity_warnings=final_mesh['clearance_violation_count'],
        leaf_leaf_soft_occupancy=final_mesh['soft_occupancy_intersection_count'],
        ground_status=ground['status'],orientation_status=orientation['status'],
        checked_calyces=orientation['checked_count'],morphology_errors=morphology['errors'],
        sparse_admission=space,retained_geometry_identical=True,
        annotation_identity_check=dict(calyces=len(calyces),fruits_including_hidden=len(fruit_objects),
                                       absent_removed_units=not any(v['unit_id'] in omitted for v in after.values())),
        scope='Unchanged strict audit; leaf-leaf soft occupancy and proximity warnings retained. Flat plane, not exhaustive flowers/context or mechanics.',
        other_seeds_tested=False,new_training_started=False,human_visual_review='pending')
    write(out/'admission.json',result)
    assert passed, result
    verify()
    # All appearance and camera settings are replayed from the prior view.
    from uchuva_lsystem.blender_appearance import create_material_sets, apply_materials, apply_profile, geometry_digest
    preview = read(prior/'preview_configuration.json')
    profiles = read(ROOT/'outputs/nodal_controller_automation_20261027/profiles.json')
    geometry_before = geometry_digest(bpy.context.scene)
    target = Vector(preview['target'])
    bpy.ops.object.camera_add(location=preview['camera_position']);camera=bpy.context.object
    camera.data.lens=preview['lens_mm'];camera.data.clip_end=500
    camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
    bpy.context.scene.camera=camera
    assignments = {k:v for k,v in preview['assignments'].items() if k.split(':',1)[1] not in omitted}
    sets = create_material_sets(plant.seed,profiles)
    apply_materials(list(bpy.context.scene.objects),sets,'candidate',assignments,
                    foliage_profiles={'growth':preview['foliage']},seed=plant.seed)
    light = apply_profile(profiles,'LT',camera,tuple(target))
    assert geometry_digest(bpy.context.scene)==geometry_before
    write(out/'preview_configuration.json',dict(camera_position=list(camera.location),
        target=list(target),lens_mm=camera.data.lens,source=str(prior/'preview_configuration.json'),
        all_retained_class_assignments_identical=True,assignments=assignments,
        lighting=light,geometry_sha256=geometry_before))
    scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=24
    scene.cycles.use_denoising=True;scene.cycles.device='GPU'
    preferences=bpy.context.preferences.addons['cycles'].preferences
    preferences.compute_device_type='OPTIX';preferences.get_devices()
    for device in preferences.devices: device.use=device.type=='OPTIX'
    scene.render.resolution_x=800;scene.render.resolution_y=700;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.filepath=str(out/'passed_fixed_camera.png')
    write(out/'audit_state.json',dict(stage='rendering_admitted_candidate',seed=plant.seed))
    bpy.ops.render.render(write_still=True)
    verify()
    write(out/'audit_state.json',dict(stage='complete',seed=plant.seed,status='admitted',new_training_started=False))
    print('THIRD_CANDIDATE_ADMITTED',json.dumps(result),flush=True)


if __name__=='__main__':
    out=Path(sys.argv[sys.argv.index('--')+1]).resolve()
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
        main(out)
    except Exception:
        write(out/'failure.json',dict(traceback=traceback.format_exc(),new_training_started=False))
        raise
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
