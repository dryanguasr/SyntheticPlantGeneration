"""Independent Blender mesh check of a serialized nodal-growth specimen."""
from pathlib import Path
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
import bpy
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.blender_scene import cleanup_scene, create_project_materials
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology, audit_scene_mesh_collisions
from uchuva_lsystem.nodal_repulsion import protected_anatomy

def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')

if __name__ == '__main__':
    args=sys.argv[sys.argv.index('--')+1:]
    source=Path(args[0]);folder=Path(args[1]);folder.mkdir(parents=True,exist_ok=True)
    plant=Plant.from_dict(json.loads(source.read_text(encoding='utf-8')))
    cleanup_scene(include_hidden=True)
    materials=create_project_materials(plant.seed)
    started=time.monotonic()
    build_geometry_from_morphology(plant,materials,instance_id='growth',add_ground=False,defer_scene_update=True)
    bpy.context.view_layer.update()
    print('BUILT',time.monotonic()-started,flush=True)
    report=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,max_reported_pairs=None,limit_clearance_search=True)
    write(folder/'mesh_audit.json',report)
    write(folder/'anatomy.json',protected_anatomy(plant))
    print('AUDIT',report['physical_collision_count'],report['clearance_violation_count'],time.monotonic()-started,flush=True)
    if '--repair' in args or '--reproductive-only' in args:
        from uchuva_lsystem.blender_pose_repair_v2 import repair_size_preserving_poses
        result=repair_size_preserving_poses(plant,materials,instance_id='growth',max_passes=4,
            max_trials_per_organ=180,max_seconds=1200,growth_joint_policy=True,
            repair_clearance=False,organ_kinds=('reproductive',) if '--reproductive-only' in args else ('leaf','reproductive'),
            checkpoint=lambda p,r:write(folder/'checkpoint.json',p.to_dict()))
        write(folder/'repair.json',result);write(folder/'plant.json',plant.to_dict())
        report=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,max_reported_pairs=None,limit_clearance_search=True)
        write(folder/'after_mesh_audit.json',report)
        print('AFTER',report['physical_collision_count'],report['clearance_violation_count'],flush=True)
    if '--branches' in args:
        from uchuva_lsystem.blender_nodal_branch_repair import repair_nodal_branches
        passes=int(args[args.index('--branch-passes')+1]) if '--branch-passes' in args else 4
        seconds=float(args[args.index('--branch-seconds')+1]) if '--branch-seconds' in args else 600
        result=repair_nodal_branches(plant,passes=passes,max_seconds=seconds,defer_leaf_contacts='--defer-leaves' in args,
            checkpoint=lambda p,r:write(folder/'checkpoint.json',p.to_dict()))
        write(folder/'branch_repair.json',result);write(folder/'plant.json',plant.to_dict())
        report=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,max_reported_pairs=None,limit_clearance_search=True)
        write(folder/'after_branch_mesh_audit.json',report)
        print('AFTER_BRANCH',report['physical_collision_count'],report['clearance_violation_count'],flush=True)
