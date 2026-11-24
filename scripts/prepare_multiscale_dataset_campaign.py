"""Prepare camera-only multiscale campaign from immutable approved plants."""
import copy
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OLD = REPO / 'outputs/frozen_field_pilot_20261019'
ROOT = REPO / 'outputs/multiscale_dataset_20261020'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2), encoding='utf-8')


def main():
    ROOT.mkdir(exist_ok=False)
    (ROOT / 'source_snapshot').mkdir()
    source = OLD / 'source_snapshot/v142_materials.py'
    (ROOT / 'source_snapshot/v142_materials.py').write_bytes(source.read_bytes())
    previous = json.loads((OLD / 'protocol.json').read_text())
    scenes = []
    for original in previous['scenes']:
        if original['kind'] != 'static':
            continue
        scene = copy.deepcopy(original)
        poses = []
        # Interleave distance bins so the first smoke batch covers all three.
        for plant in scene['plants']:
            for elevation in (0, 18):
                for yaw in (-150, -105, -60, -15, 30, 75, 120, 165):
                    for name, distance in [('near', 1.2), ('middle', 2.2), ('far', 3.6)]:
                        poses.append(dict(target_plant=plant['instance_id'], distance_bin=name,
                                          distance_m=distance, yaw_deg=yaw, elevation_deg=elevation,
                                          target_height_bu=3.2))
        scene.update(views=len(poses), camera_samples=poses)
        scenes.append(scene)
    protocol = dict(version='multiscale-camera-only/1', scenes=scenes,
        total_images=sum(s['views'] for s in scenes), image_size=[1280,720],
        distances_m=[1.2,2.2,3.6], distance_definition='camera to aim point, not canopy stand-off',
        camera_parameters_status='engineering_heuristic; smoke review before full queue',
        near_camera_clearance_m=.2, lens_mm=35, plant_changes=False,
        source_pilot=str(OLD), confidence=.25, native_evaluation_iou=.5,
        eligible_pixels=100, eligible_bbox_side=8, training_input_size=960,
        candidate_native_patch_sizes=[384,640], primary_patch_size=640, stride=448,
        training_patch_cap=1600, training_epochs=10,
        native_augmentation=dict(hsv_h=0,hsv_s=0,hsv_v=.1,fliplr=.5,flipud=0,
                                 mosaic=0,mixup=0,copy_paste=0),
        augmentation_reason='Native HSV-value and horizontal flip preserve calyx appearance class and exact disconnected raster masks. No hue/class-changing transform.',
        training_gate='All image/mask/class/split/hash and native augmentation alignment audits must pass; no training during render',
        shared_topology_limitation=previous['shared_topology_limitation'],
        test_status='Historically inspected development test; not independent holdout',
        reserved_seeds_used=False, initialization=str(OLD/'training_runs/training/weights/last.pt'),
        initialization_sha256='79c3dad74e7cf9caab3c82a3e37ea72235352568d7dfacbd5c9e8284cb190073',
        no_generator_or_environment_refinement=True)
    write(ROOT/'protocol.json',protocol)
    write(ROOT/'effective_budget.json',dict(limit_seconds=None,historical_execution_seconds=0))
    write(ROOT/'run.json',dict(seed=20261020,parameter_preset='multiscale_camera_only',
        minimum_runtime_free_memory_gib=3,minimum_start_free_memory_gib=6.5))
    write(ROOT/'state.json',dict(stage='prepared_for_three_view_smoke',complete=False,
        controller_pid=None,next_action='Render three train views, verify actual scale, native masks and geometry hashes; then start serial dataset render.'))
    # Derive a new renderer; original and frozen interpreter are never edited.
    code = (OLD/'frozen/scripts/render_frozen_field_pilot.py').read_text()
    code = code.replace("ROOT=Path(__file__).resolve().parents[1]", "ROOT=Path("+repr(str(OLD/'frozen'))+")")
    start = code.index('  # Fixed target and illumination:')
    end = code.index("  camera.rotation_euler=", start)
    code = code[:start] + '''  sample=config['camera_samples'][view]
  entry=next(e for e in originals if e['instance_id']==sample['target_plant'])
  target=Vector(entry['position'])+Vector((0,0,sample['target_height_bu']))
  radius=sample['distance_m']/.125;elevation=math.radians(sample['elevation_deg'])
  # Avoid putting the camera inside unchanged plant bounds. This is camera selection,
  # not geometry repair; record any deterministic angular adjustment.
  bounds=[]
  for obj in scene.objects:
   if obj.type=='MESH' and obj in plant_meshes:
    corners=[obj.matrix_world@Vector(c) for c in obj.bound_box]
    bounds.append(([min(c[i] for c in corners)-1.6 for i in range(3)],
                   [max(c[i] for c in corners)+1.6 for i in range(3)]))
  for adjustment in (0,7,-7,14,-14,21,-21):
   angle=math.radians(sample['yaw_deg']+adjustment)
   location=target+Vector((radius*math.cos(elevation)*math.sin(angle),
                          -radius*math.cos(elevation)*math.cos(angle),radius*math.sin(elevation)))
   if location.z>.6 and not any(all(lo[i]<=location[i]<=hi[i] for i in range(3)) for lo,hi in bounds):break
  else:raise RuntimeError('No clear camera pose; preserve scene and review camera recipe')
  camera.location=location
  write(folder/'camera_sample.json',dict(sample,angular_adjustment_deg=adjustment,
       actual_distance_m=(location-target).length*.125,camera_world_bu=list(location),
       target_world_bu=list(target),clearance_method='expanded individual mesh AABB; engineering check'))
''' + code[end:]
    code = code.replace('bpy.context.view_layer.update();scene=bpy.context.scene', 'bpy.context.view_layer.update();scene=bpy.context.scene;plant_meshes=set(o for o in scene.objects if o.type=="MESH")')
    # New close views can be valid negatives; export keeps them explicitly.
    (ROOT/'render_multiscale.py').write_text(code,encoding='utf-8')
    files={str(ROOT/'protocol.json'):sha(ROOT/'protocol.json'),
           str(ROOT/'render_multiscale.py'):sha(ROOT/'render_multiscale.py'),
           str(source):sha(source),str(ROOT/'source_snapshot/v142_materials.py'):sha(ROOT/'source_snapshot/v142_materials.py'),protocol['initialization']:protocol['initialization_sha256']}
    for scene in scenes:
        for p in scene['plants']:
            assert sha(Path(p['path']))==p['sha256']
            files[p['path']]=p['sha256']
    write(ROOT/'campaign_manifest.json',dict(files=files,inherited_freeze_manifest=str(OLD/'freeze_manifest.json')))
    groups={}
    for scene in scenes:
        groups.setdefault(scene['split'],set()).update(p['sha256'] for p in scene['plants'])
    assert all(not groups[a]&groups[b] for a in groups for b in groups if a!=b)
    write(ROOT/'split_plan.json',dict(source_hashes={k:sorted(v) for k,v in groups.items()},
        neighbors='Only clones of same-scene plants; split follows source SHA256',
        augmentation_train_only=True,patches_inherit_source_split=True,
        forbidden_sources=['cancelled row-flight mixed validation/test scenes'],
        topology_independent=False,test_is_development=True,reserved_seeds_used=False))
    print(ROOT)


if __name__=='__main__':
    main()
