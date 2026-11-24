"""Full-mesh trials of a local two-bone insertion, with fixed end anchors."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import bpy
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.nodal_repulsion import KEY,axes,protected_anatomy,initialize_growth_poses,local_joint_candidates,counterbend_candidates
from uchuva_lsystem.collisions import build_scene_proxies
from uchuva_lsystem.blender_scene import cleanup_scene,create_project_materials
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology,audit_scene_mesh_collisions

def write(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plant',type=Path,required=True)
    parser.add_argument('--node',required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--mode',choices=('fixed_ends','counterbend'),default='fixed_ends')
    parser.add_argument('--stop-on-local-clear',action='store_true')
    parser.add_argument('--max-trials',type=int,default=100)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);args.output.mkdir(parents=True,exist_ok=False)
    plant=Plant.from_dict(json.loads(args.plant.read_text(encoding='utf-8')));anatomy=protected_anatomy(plant)
    layout=initialize_growth_poses(plant);bones={};build_scene_proxies(layout,{'growth':plant},bone_output=bones)
    axis,node=next((a,n) for a in axes(plant.axes) for n in a.nodes if n.id==args.node)
    position=axis.nodes.index(node);parts=axis.internodes[position:position+2]
    original=[deepcopy(p.provenance[KEY]['direction']) for p in parts]
    candidates=[dict(first_direction=original[0],second_direction=original[1],degrees=0,delta_z=0)]
    candidates+=(counterbend_candidates(axis,position,bones['growth'],bearing=node.reproductive_unit.pedicel.provenance[KEY]['direction'])
                 if args.mode=='counterbend' else local_joint_candidates(axis,position,bones['growth']))
    history=[];best=None
    for index,candidate in enumerate(candidates[:args.max_trials]):
        parts[0].provenance[KEY]['direction']=list(candidate['first_direction'])
        parts[1].provenance[KEY]['direction']=list(candidate['second_direction'])
        for part in parts:
            part.provenance[KEY]['local_joint_candidate']=dict(node=args.node,mode=args.mode,candidate=candidate,status='engineering_heuristic')
        write(args.output/'stage.json',dict(index=index,stage='cleanup'))
        cleanup_scene(include_hidden=True)
        write(args.output/'stage.json',dict(index=index,stage='build'))
        build_geometry_from_morphology(plant,create_project_materials(plant.seed),instance_id='growth',add_ground=False,defer_scene_update=True)
        bpy.context.view_layer.update()
        write(args.output/'stage.json',dict(index=index,stage='mesh_audit'))
        report=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,max_reported_pairs=None,limit_clearance_search=True)
        write(args.output/f'trial_{index:02d}_audit.json',report)
        critical_rows=[r for r in report['physical_collisions'] if r['semantic_a']!='leaf' and r['semantic_b']!='leaf' and '_leaf_petiole' not in r['object_a'] and '_leaf_petiole' not in r['object_b']]
        critical=len(critical_rows)
        target_critical=sum(node.reproductive_unit.id in r['object_a'] or node.reproductive_unit.id in r['object_b'] for r in critical_rows)
        row=dict(index=index,candidate=candidate,crossings=report['physical_collision_count'],critical_crossings=critical,target_critical=target_critical,warnings=report['clearance_violation_count'])
        history.append(row);write(args.output/'progress.json',history);print('LOCAL_NODE_TRIAL',row,flush=True)
        write(args.output/f'trial_{index:02d}_plant.json',plant.to_dict())
        objective=(target_critical,critical,row['crossings']) if args.stop_on_local_clear else (critical,row['crossings'])
        if best is None or objective<best[0]:best=(objective,deepcopy(plant.to_dict()))
        if not row['crossings'] or args.stop_on_local_clear and not target_critical:break
    plant=Plant.from_dict(best[1]);assert protected_anatomy(plant)==anatomy
    plant.metadata.setdefault('local_nodal_joint_reviews',[]).append(dict(node=args.node,history=history,
        status='engineering_heuristic',mode=args.mode,fixed_end_anchors=args.mode=='fixed_ends',nominal_lengths_preserved=True,
        requires_independent_ground_orientation_and_full_mesh_audit=True))
    write(args.output/'plant.json',plant.to_dict())
    write(args.output/'completion.json',dict(objective=list(best[0]),local_stop_policy=args.stop_on_local_clear,
        physical_admission='not established; complete independent audit required',anatomy_before=anatomy,anatomy_after=protected_anatomy(plant)))
    write(args.output/'source_lock.json',{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'src/uchuva_lsystem').glob('*.py')})

if __name__=='__main__':main()
