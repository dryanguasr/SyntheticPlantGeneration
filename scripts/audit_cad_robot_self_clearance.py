#!/usr/bin/env python3
"""Enumerate nonexcluded CAD collisions near contact at saved coordinate zero.

Box SAT is conservative. An overlap is a collider contact candidate, not proof
that the original detailed CAD surfaces intersect. When mesh colliders are
present, the explicit asset root is hash/topology verified and distances use
the shared triangle BVH and solid containment; this is the tessellation, not
the exact native BRep. Cylinder audit prisms remain conservative.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.robot_spec import resolve_robot_profile
from uchuva_gazebo.robot_kinematics import forward_kinematics, collision_shapes
from uchuva_gazebo.robot_motion import shape_box, box_separation
from uchuva_gazebo.robot_mesh_geometry import MeshRepository


def audit(robot, source_report, threshold=.004, asset_root=None):
    data=robot.to_dict()
    positions={row['name']:0 for row in data['joints'] if row['type']!='fixed'}
    shapes=collision_shapes(robot,forward_kinematics(robot,positions))
    mesh_mode=any(row['geometry']['type']=='mesh' for row in shapes)
    repository=MeshRepository(asset_root,shapes) if mesh_mode else None
    boxes=[(row,repository.world_bounds(row) if repository else shape_box(row)) for row in shapes]
    exclusions={tuple(sorted(row['links'])) for row in data['collision_policy']['excluded_pairs']}
    records=[]
    def identity(shape):
        value={'link':shape['link'],'name':shape['name']}
        match=re.fullmatch(r'part_(\d+)_bounds',shape['name'])
        if match:
            source=source_report['parts'][int(match[1])]
            value.update({key:source[key] for key in ('occurrence_id','occurrence_name_path','source_path','source_sha256')})
        return value
    for index,(a,ah) in enumerate(boxes):
        for b,bh in boxes[index+1:]:
            if a['link']==b['link'] or tuple(sorted((a['link'],b['link']))) in exclusions:
                continue
            if repository:
                lower=math.sqrt(sum(max(ah[0][i]-bh[1][i],bh[0][i]-ah[1][i],0)**2 for i in range(3)))
                if lower>=threshold:
                    continue
                gap=repository.shape_distance(a,b,threshold)
            else:
                if math.dist(a['pose']['xyz_m'],b['pose']['xyz_m']) > math.sqrt(sum(x*x for x in ah))+math.sqrt(sum(x*x for x in bh))+threshold:
                    continue
                gap=box_separation(a,ah,b,bh)
            if gap<threshold:
                records.append({'separation_lower_bound_m':gap,'first':identity(a),'second':identity(b)})
    records.sort(key=lambda row:row['separation_lower_bound_m'])
    return {'schema_version':'cad-self-bound-audit/1.0','scope':__doc__,'robot_spec_sha256':robot.sha256,
            'joint_positions':positions,'threshold_m':threshold,'shapes':len(shapes),
            'distance_method':'shared_native_mesh_bytes_BVH_solid_distance' if repository else 'conservative_box_SAT',
            'verified_collision_assets':repository.asset_hashes if repository else {},
            'zero_distance_semantics':'Surface touch or solid overlap; no signed penetration depth. Mesh discretization uncertainty remains separate.',
            'overlap_candidate_count':sum(row['separation_lower_bound_m']<=1e-12 for row in records),'pairs':records}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',required=True,type=Path)
    parser.add_argument('--import-report',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--asset-root',type=Path)
    args=parser.parse_args()
    result=audit(resolve_robot_profile(args.profile),json.loads(args.import_report.read_text(encoding='utf-8-sig')),asset_root=args.asset_root)
    result['source_files_sha256']={str(path):hashlib.sha256(path.read_bytes()).hexdigest()
                                   for path in (args.profile,args.import_report,Path(__file__))}
    with args.output.open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2,allow_nan=False);handle.write('\n')
    print(json.dumps({'overlap_candidates':result['overlap_candidate_count'],'pairs_below_4mm':len(result['pairs']),
        'worst':result['pairs'][:12]},indent=2))


if __name__=='__main__':main()
