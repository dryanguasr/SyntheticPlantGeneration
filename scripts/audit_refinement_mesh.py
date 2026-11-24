"""Blender mesh contact audit of one saved refinement morphology."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.blender_scene import cleanup_scene, create_project_materials
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology, audit_scene_mesh_collisions

parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--repair-reproductive', action='store_true')
parser.add_argument('--repair-leaves', action='store_true')
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
if args.repair_leaves and args.repair_reproductive:
    parser.error('Use one repair family per controlled trial')
out = Path(args.output)
out.mkdir(parents=True, exist_ok=False)
raw = Path(args.input).read_bytes()
plant = Plant.from_dict(json.loads(raw))
cleanup_scene()
materials = create_project_materials(plant.seed)
build_geometry_from_morphology(plant, materials, instance_id='review_plant', add_ground=False, defer_scene_update=True)
bpy.context.view_layer.update()
manifest = dict(source=str(Path(args.input).resolve()), sha256=hashlib.sha256(raw).hexdigest(),
                seed=plant.seed, objects=len(bpy.context.scene.objects), stage='mesh_audit',
                limitations=['Single isolated development plant; no support geometry',
                             'Material appearance does not affect mesh contact audit'])
(out / 'progress.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print('GEOMETRY_BUILT', manifest['objects'], flush=True)
if args.repair_reproductive or args.repair_leaves:
    from uchuva_lsystem.blender_pose_repair import repair_reproductive_poses, repair_leaf_poses
    repair_function = repair_leaf_poses if args.repair_leaves else repair_reproductive_poses
    manifest['stage'] = 'leaf_pose_search' if args.repair_leaves else 'reproductive_pose_search'
    (out / 'progress.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    repair = repair_function(plant, materials, instance_id='review_plant',
                                      checkpoint=out / 'morphology_checkpoint.json')
    (out / 'repair_report.json').write_text(json.dumps(repair, indent=2), encoding='utf-8')
    (out / 'repaired_morphology.json').write_text(json.dumps(plant.to_dict(), indent=2), encoding='utf-8')
    cleanup_scene()
    materials = create_project_materials(plant.seed)
    build_geometry_from_morphology(plant, materials, instance_id='review_plant', add_ground=False, defer_scene_update=True)
    bpy.context.view_layer.update()
    manifest['stage'] = 'mesh_audit_after_full_rebuild'
    (out / 'progress.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('REPAIR_REBUILT', len(repair['adjustments']), flush=True)
report = audit_scene_mesh_collisions(max_bvh_cache_objects=64)
(out / 'mesh_contacts.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
manifest['stage'] = 'completed'
(out / 'progress.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print('MESH_AUDIT_COMPLETE', flush=True)
