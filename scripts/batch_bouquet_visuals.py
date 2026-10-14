"""Batch exact textured triangles for flight rendering, retaining all colliders.

The individual-label source remains the A/B evaluator world. This rendering
copy keeps identity provenance but cannot supply instance segmentation.
"""
import argparse
from collections import defaultdict
import copy
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.field import element


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);(a.output/'meshes').mkdir()
    tree=ET.parse(a.source/'field.sdf');world=tree.getroot().find('world');field=world.find("model[@name='field']/link")
    manifest=json.loads((a.source/'manifest.json').read_text());lookup={m['uri']:m for m in manifest['meshes']}
    groups=defaultdict(list);materials={}
    for model in list(world.findall('model')):
        for link in model.findall('link'):
            for visual in list(link.findall('visual')):
                uri=visual.findtext('geometry/mesh/uri')
                if uri not in lookup:continue
                mat=visual.find('material');key=ET.tostring(mat,encoding='unicode')
                groups[key].append(lookup[uri]);materials[key]=copy.deepcopy(mat);link.remove(visual)
        if model.attrib['name'].startswith('calyx_'):world.remove(model)
    batches=[];uri_map={}
    for index,(key,entries) in enumerate(groups.items()):
        uri=f'meshes/batch_{index:02d}.obj';v_offset=t_offset=n_offset=triangles=0
        with (a.output/uri).open('w') as out:
            out.write('o merged\n')
            for entry in entries:
                v_count=t_count=n_count=0
                with (a.source/entry['uri']).open() as source:
                    for line in source:
                        if line.startswith('v '):v_count+=1;out.write(line)
                        elif line.startswith('vt '):t_count+=1;out.write(line)
                        elif line.startswith('vn '):n_count+=1;out.write(line)
                        elif line.startswith('# source '):out.write(line)
                        elif line.startswith('f '):
                            tokens=[s.split('/') for s in line.split()[1:]]
                            out.write('f '+' '.join(f'{int(v[0])+v_offset}/{int(v[1])+t_offset if v[1] else ""}/{int(v[2])+n_offset}' for v in tokens)+'\n');triangles+=1
                v_offset+=v_count;t_offset+=t_count;n_offset+=n_count;uri_map[entry['uri']]=uri
        visual=element(field,'visual',name=f'batched_{index}')
        element(element(element(visual,'geometry'),'mesh'),'uri',uri);visual.append(materials[key])
        batches.append({'uri':uri,'color':entries[0]['color'],'triangles':triangles,'source_meshes':[e['uri'] for e in entries]})
    assert sum(m['triangles'] for m in batches)==sum(m['triangles'] for m in manifest['meshes'])
    for organ in manifest['organs']:organ['meshes']=list(dict.fromkeys(uri_map[u] for u in organ['meshes']))
    manifest['meshes']=batches;manifest['individual_calyces']=False
    manifest['render_batch']={'surfaces':'exact triangle/UV/normal concatenation','colliders':'all preserved',
        'source':str(a.source.resolve()),'instance_segmentation':False,'visuals':len(batches)}
    shutil.copytree(a.source/'textures',a.output/'textures')
    ET.indent(tree);tree.write(a.output/'field.sdf',encoding='utf-8',xml_declaration=True)
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest['render_batch']))

if __name__=='__main__':main()
