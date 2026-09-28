"""Batch exact visual surfaces by color and simplify collision LOD for aerial survey."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.field import element as e,material,numbers


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False);(args.output/'meshes').mkdir()
    manifest=json.loads((args.source/'manifest.json').read_text(encoding='utf-8'))
    groups=defaultdict(list)
    for mesh in manifest['meshes']:groups[tuple(mesh['color'])].append(mesh)
    tree=ET.parse(args.source/'field.sdf');link=tree.find("world/model[@name='field']/link")
    for visual in list(link.findall('visual')):
        if visual.find('geometry/mesh') is not None:link.remove(visual)
    batched=[];materials=[]
    for index,(color,entries) in enumerate(groups.items()):
        name=f'batch_{index}';uri=f'meshes/{name}.obj';triangles=0;v_offset=n_offset=0
        with (args.output/uri).open('w') as target:
            target.write(f'mtllib surface.mtl\nusemtl {name}\no merged\n')
            for mesh in entries:
                vertices=normals=0
                with (args.source/mesh['uri']).open() as source:
                    for line in source:
                        if line.startswith('v '):vertices+=1;target.write(line)
                        elif line.startswith('vn '):normals+=1;target.write(line)
                        elif line.startswith('f '):
                            indices=[item.split('//') for item in line.split()[1:]]
                            target.write('f '+' '.join(f'{int(v)+v_offset}//{int(n)+n_offset}' for v,n in indices)+'\n')
                            triangles+=1
                v_offset+=vertices;n_offset+=normals
        batched.append({'uri':uri,'color':color,'triangles':triangles,'source_meshes':[m['uri'] for m in entries]})
    # Marker black and white boxes retain exact dimensions and outward-only print.
    marker_groups=defaultdict(list)
    for visual in list(link.findall('visual')):
        if visual.attrib['name'].startswith('marker_'):
            marker_groups[tuple(map(float,visual.findtext('material/diffuse').split()))].append(visual)
            link.remove(visual)
    for index,(color,visuals) in enumerate(marker_groups.items()):
        uri=f'meshes/markers_{index}.obj';name=f'markers_{index}';offset=0;normal=0
        face_indices=((0,3,2,1),(4,5,6,7),(0,1,5,4),(3,7,6,2),(0,4,7,3),(1,2,6,5))
        normals=((0,0,-1),(0,0,1),(0,-1,0),(0,1,0),(-1,0,0),(1,0,0))
        with (args.output/uri).open('w') as stream:
            stream.write(f'mtllib surface.mtl\nusemtl {name}\no merged\n')
            for visual in visuals:
                center=list(map(float,visual.findtext('pose').split()))[:3]
                half=[float(v)/2 for v in visual.findtext('geometry/box/size').split()]
                signs=((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))
                for sign in signs:stream.write('v '+numbers([center[i]+sign[i]*half[i] for i in range(3)])+'\n')
                for face,n in zip(face_indices,normals):
                    normal+=1;stream.write('vn '+numbers(n)+'\n')
                    for tri in ((face[0],face[1],face[2]),(face[0],face[2],face[3])):
                        stream.write('f '+' '.join(f'{offset+i+1}//{normal}' for i in tri)+'\n')
                offset+=8
        batched.append({'uri':uri,'color':color,'triangles':len(visuals)*12,'source_marker_boxes':len(visuals)})
    for mesh in batched:
        name=Path(mesh['uri']).stem;color=mesh['color'];rgb=numbers(color[:3])
        materials.append(f'newmtl {name}\nKa {rgb}\nKd {rgb}\nd {color[3]}\n')
        visual=e(link,'visual',name=name);e(e(e(visual,'geometry'),'mesh'),'uri',mesh['uri']);material(visual,color)
    (args.output/'meshes/surface.mtl').write_text(''.join(materials))
    # Structural cylinders are kept only for posts and overhead cables. The
    # above-trellis mission does not claim contact capability inside the canopy.
    removed=0;kept=[]
    for index,item in enumerate(manifest['colliders']):
        source_id=item['source_id']
        if not ('_post_' in source_id or '_overhead' in source_id):
            collision=link.find(f"collision[@name='structural_{index}']")
            if collision is not None:link.remove(collision);removed+=1
        else:kept.append({**item,'sdf_name':f'structural_{index}'})
    manifest['colliders']=kept
    source_visuals=len(manifest['meshes'])
    manifest['meshes']=batched
    manifest['aerial_batch']={'source':str(args.source.resolve()),'source_visuals':source_visuals,
        'batched_visuals':len(batched),'removed_structural_colliders':removed,
        'collision_scope':'ground_markers_posts_overhead_cables_only',
        'plant_contacts':'not_simulated','status':'engineering_heuristic'}
    ET.indent(tree);tree.write(args.output/'field.sdf',encoding='utf-8',xml_declaration=True)
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(manifest['aerial_batch']))


if __name__=='__main__':main()
