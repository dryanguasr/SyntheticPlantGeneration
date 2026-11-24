"""Bounded directional nodal trials with complete reconstruction per candidate.

Fallback for an own-stem contact: grow the incoming bone toward the axillary
pedicel's horizontal bearing, thereby moving the older stem away from the
pendulous capacho. No endpoint, organ or nominal length is removed or scaled.
"""
from pathlib import Path
import argparse
import json
import sys
import math
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import bpy
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.nodal_repulsion import KEY,axes,protected_anatomy,joint_angles,joint_direction,dot
from uchuva_lsystem.blender_scene import cleanup_scene,create_project_materials
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology,audit_scene_mesh_collisions

def write(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plant',type=Path,required=True)
    parser.add_argument('--node',required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);args.output.mkdir(parents=True,exist_ok=False)
    plant=Plant.from_dict(json.loads(args.plant.read_text(encoding='utf-8')));anatomy=protected_anatomy(plant)
    axis,node=next((a,n) for a in axes(plant.axes) for n in a.nodes if n.id==args.node)
    i=axis.nodes.index(node);part=axis.internodes[i];record=part.provenance[KEY]
    current=list(record['direction']);bearing,_=joint_angles(node.reproductive_unit.pedicel.provenance[KEY]['direction'])
    candidates=[current]
    for tilt in (10,20,30,35):
        for yaw in (0,-30,30,-60,60,180):
            direction=joint_direction(bearing+yaw,90-tilt)
            if math.degrees(math.acos(max(-1,min(1,dot(direction,record['input_direction'])))))<=35:
                candidates.append(direction)
    history=[];best=None
    for index,direction in enumerate(candidates):
        record['direction']=list(direction)
        cleanup_scene(include_hidden=True)
        build_geometry_from_morphology(plant,create_project_materials(plant.seed),instance_id='growth',add_ground=False)
        bpy.context.view_layer.update()
        report=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,max_reported_pairs=None,limit_clearance_search=True)
        write(args.output/f'trial_{index:02d}_audit.json',report)
        row=dict(index=index,direction=list(direction),crossings=report['physical_collision_count'],warnings=report['clearance_violation_count'])
        history.append(row);print('DIRECTIONAL_NODE_TRIAL',row,flush=True)
        write(args.output/'progress.json',history)
        if best is None or row['crossings']<best[0]:best=(row['crossings'],deepcopy(plant.to_dict()))
        if not row['crossings']:break
    plant=Plant.from_dict(best[1]);assert protected_anatomy(plant)==anatomy
    plant.metadata.setdefault('directional_nodal_trials',[]).append(dict(node=args.node,history=history,
        method='axillary bearing, lower node first; full rebuilt evaluated meshes per candidate',
        status='engineering_heuristic',requires_ground_and_orientation_audit=True))
    write(args.output/'plant.json',plant.to_dict())
    write(args.output/'completion.json',dict(physical_crossings=best[0],anatomy_before=anatomy,anatomy_after=protected_anatomy(plant)))

if __name__=='__main__':main()
