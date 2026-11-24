#!/usr/bin/env python3
"""Prepare portable collision-only CAD derivatives; never mutate visual assets."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.robot_mesh_geometry import (
    MeshRepository, TriangleMesh, read_collision_obj, repair_collision_obj,
    _consistent_face_signs)


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def restore_native_source(source, destination, repair):
    if digest(source)!=repair['native_sha256']:
        raise ValueError('Native source restoration hash differs')
    original_vertices,original_faces,_,_=read_collision_obj(source)
    old,new=repair['replace_position_m'],repair['with_position_m']
    movement=math.dist(old,new)
    if not 0<movement<=repair['maximum_position_change_m']<=5e-9:
        raise ValueError('Numeric seam change exceeds its explicit bound')
    changed=[];lines=[];vertex_index=0
    for line in source.read_text(encoding='utf-8-sig').splitlines():
        row=line.split()
        if row and row[0]=='v':
            vertex_index+=1
            if tuple(map(float,row[1:]))==tuple(old):
                line='v '+' '.join(format(v,'.17g') for v in new)
                changed.append({'vertex_index_one_based':vertex_index,'before_m':old,'after_m':new,'distance_m':movement})
        lines.append(line)
    if not changed:raise ValueError('Declared native seam vertex not found')
    destination.write_text('\n'.join(lines)+'\n')
    return {'change_class':repair['change_class'],'source_document':repair['source_document'],
            'native_source_sha256':repair['native_sha256'],'native_uri':repair['native_uri'],
            'reason':repair['reason'],'maximum_position_change_m':movement,
            'affected_vertices':changed,'native_vertex_count':len(original_vertices),
            'native_triangle_count':len(original_faces)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',type=Path,required=True)
    parser.add_argument('--asset-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--native-export',type=Path)
    parser.add_argument('--seam-repairs',type=Path)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Use a fresh output; previous evidence is immutable')
    args.output.mkdir(parents=True)
    root=args.asset_root.resolve();out=args.output.resolve()
    data=json.loads(args.profile.read_text(encoding='utf-8-sig'))
    repairs=json.loads(args.seam_repairs.read_text())['repairs'] if args.seam_repairs else {}
    geometries={s['geometry']['sha256']:s['geometry'] for link in data['links'] for s in link['collisions'] if s['geometry']['type']=='mesh'}
    all_assets={s['geometry']['uri']:s['geometry']['sha256'] for link in data['links'] for key in ('collisions','visuals') for s in link[key] if s['geometry']['type']=='mesh'}
    for uri,expected in all_assets.items():
        src=(root/uri).resolve()
        if not src.is_relative_to(root) or digest(src)!=expected:raise ValueError('Source mesh path/hash differs')
        destination=out/uri;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,destination)
    (out/'collision_meshes').mkdir()
    (out/'source_restorations').mkdir()
    entries={}
    for source_hash,g in sorted(geometries.items()):
        source=root/g['uri'];restoration=None
        if source_hash in repairs:
            if args.native_export is None:raise ValueError('Native export root required for explicit restoration')
            repair=repairs[source_hash];native=(args.native_export/repair['native_uri']).resolve()
            if not native.is_relative_to(args.native_export.resolve()):raise ValueError('Native source escapes root')
            source=out/'source_restorations'/f'{source_hash}.obj'
            restoration=restore_native_source(native,source,repair)
        v,f,_,_=read_collision_obj(source)
        _,orientation=_consistent_face_signs(v,f)
        if orientation['flipped_triangles'] or restoration:
            temporary=out/'collision_meshes'/f'from_{source_hash}.obj'
            report=repair_collision_obj(source,temporary)
            final=temporary.with_name(report['collision_sha256']+'.obj');temporary.rename(final)
            uri=final.relative_to(out).as_posix();sha=report['collision_sha256']
        else:
            mesh=TriangleMesh(v,f)
            uri=g['uri'];sha=source_hash
            report={**orientation,'vertices_unchanged':True,'unoriented_triangles_unchanged':True,
                    'component_signed_volumes_m3':mesh.component_signed_volumes,
                    'vertex_count':len(v),'triangle_count':len(f)}
        if restoration:
            report.update(restoration)
            report['source_visual_sha256']=source_hash
            report['restored_triangles_from_native']=len(f)-len(read_collision_obj(root/g['uri'])[1])
        entries[source_hash]={'collision_uri':uri,'collision_sha256':sha,
                              'positions_unchanged':restoration is None,
                              'unoriented_triangles_unchanged':restoration is None,'report':report}
    admitted=[{**g,'uri':entries[key]['collision_uri'],'sha256':entries[key]['collision_sha256']} for key,g in geometries.items()]
    repo=MeshRepository(out,admitted)
    report={'schema_version':'cad-collision-derivatives/1','asset_root':'.',
            'source_profile_sha256':digest(args.profile),
            'source_code_sha256':{'scripts/prepare_cad_collision_assets.py':digest(__file__),
                                  'src/uchuva_gazebo/robot_mesh_geometry.py':digest(ROOT/'src/uchuva_gazebo/robot_mesh_geometry.py')},
            'seam_repairs_config_sha256':digest(args.seam_repairs) if args.seam_repairs else None,
            'source_asset_hashes':all_assets,'entries':entries,
            'admission':{'status':'PASS','scope':'Closed oriented tessellation, normals, finite coordinates, portable paths and hashes; not a dynamic mission validation',
                         'unique_collision_assets':len(repo.meshes),'visual_assets_unchanged':True,
                         'derived_assets':sum(row['collision_sha256']!=key for key,row in entries.items()),
                         'native_contact_validation_status':'PENDING for these exact derivatives'}}
    (out/'collision_derivatives.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['admission'],indent=2))


if __name__=='__main__':main()
