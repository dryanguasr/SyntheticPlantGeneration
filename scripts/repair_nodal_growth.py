"""Small physical-review worker; no render batch, training or organ pruning."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import shutil
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import bpy
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.nodal_repulsion import protected_anatomy,initialize_growth_poses,revise_pedicel_mobility,restore_calyx_toward_gravity
from uchuva_lsystem.blender_scene import cleanup_scene,create_project_materials
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology,audit_scene_mesh_collisions
from uchuva_lsystem.blender_pose_repair_v2 import repair_size_preserving_poses
from uchuva_lsystem.blender_nodal_branch_repair import repair_nodal_branches
from uchuva_lsystem.validation import validate_morphology_tree

def write(path,value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--plant',type=Path,required=True)
    parser.add_argument('--raw',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--rounds',type=int,default=4)
    parser.add_argument('--pedicel-excursion',type=float,default=75)
    parser.add_argument('--gravity-restore-units',nargs='*',default=[])
    parser.add_argument('--gravity-restore-fraction',type=float,default=1.)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    args.output.mkdir(parents=True,exist_ok=False)
    sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'src/uchuva_lsystem').glob('*.py'))}
    write(args.output/'source_lock.json',sources)
    snapshot=args.output/'source_snapshot';snapshot.mkdir()
    for relative in sources:
        target=snapshot/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/relative,target)
    plant=Plant.from_dict(json.loads(args.plant.read_text(encoding='utf-8')))
    raw=Plant.from_dict(json.loads(args.raw.read_text(encoding='utf-8')))
    invariant=protected_anatomy(raw)
    assert protected_anatomy(plant)==invariant
    initialize_growth_poses(plant)
    if args.gravity_restore_units:
        restore_calyx_toward_gravity(plant,args.gravity_restore_units,fraction=args.gravity_restore_fraction)
    if args.pedicel_excursion!=75:
        revise_pedicel_mobility(plant,args.pedicel_excursion,
            reason='Physical review: coordinate/component search at the original unmeasured 75 degree prior left mutually blocked capachos or an own-stem collision; expand search without changing calyx gravity, organs or dimensions')
    history=[]
    def rebuild():
        cleanup_scene(include_hidden=True)
        materials=create_project_materials(plant.seed)
        build_geometry_from_morphology(plant,materials,instance_id='growth',add_ground=False,defer_scene_update=True)
        bpy.context.view_layer.update()
        return materials
    def audit(label):
        mesh=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,max_reported_pairs=None,limit_clearance_search=True)
        write(args.output/f'{label}_mesh.json',mesh)
        history.append(dict(stage=label,crossings=mesh['physical_collision_count'],clearance_warnings=mesh['clearance_violation_count']))
        write(args.output/'progress.json',history)
        print('REVIEW_AUDIT',history[-1],flush=True)
        return mesh
    def checkpoint(p,row):
        assert protected_anatomy(p)==invariant
        write(args.output/'checkpoint.json',p.to_dict())
    materials=rebuild();mesh=audit('initial')
    for iteration in range(args.rounds):
        if mesh['physical_collision_count']==0:break
        branch=repair_nodal_branches(plant,passes=3,max_seconds=600,defer_leaf_contacts=True,checkpoint=checkpoint)
        write(args.output/f'round_{iteration}_branch.json',branch)
        # The branch stage may temporarily move leaves into contacts. Clear
        # these with exact leaf reconstruction before any admission decision.
        joint=repair_size_preserving_poses(plant,materials,instance_id='growth',max_passes=4,
            max_trials_per_organ=180,max_seconds=900,growth_joint_policy=True,repair_clearance=False,
            organ_kinds=('leaf','reproductive'),checkpoint=checkpoint)
        write(args.output/f'round_{iteration}_joint.json',joint)
        write(args.output/f'round_{iteration}_plant.json',plant.to_dict())
        # The scene used for search is never accepted directly.
        plant=Plant.from_dict(plant.to_dict());materials=rebuild();mesh=audit(f'round_{iteration}_independent')
    write(args.output/'plant.json',plant.to_dict())
    write(args.output/'validation.json',validate_morphology_tree(plant,stage='adapted'))
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==digest for p,digest in sources.items()),'Sources changed during review'
    write(args.output/'completion.json',dict(status='mesh_crossings_cleared_requires_ground_orientation_and_visual_review'
        if mesh['physical_collision_count']==0 else 'unresolved_not_admitted',history=history,
        anatomy_before=invariant,anatomy_after=protected_anatomy(plant),training_started=False,
        scope='No change to historical campaign; no organ deletion or nominal dimension change'))
    if mesh['physical_collision_count']:raise SystemExit(2)

if __name__=='__main__':main()
