"""Batch non-target surfaces exactly, retaining every individual calyx model."""
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
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'meshes').mkdir()
    tree=ET.parse(args.source/'field.sdf');world=tree.getroot().find('world')
    field=world.find("model[@name='field']/link")
    manifest=json.loads((args.source/'manifest.json').read_text())
    lookup={m['uri']:m for m in manifest['meshes']}
    groups=defaultdict(list);materials={};kept=set()
    for model in world.findall('model'):
        for link in model.findall('link'):
            for visual in list(link.findall('visual')):
                uri=visual.findtext('geometry/mesh/uri')
                if uri not in lookup:continue
                if model.attrib['name'].startswith('calyx_'):
                    kept.add(uri);continue
                material=visual.find('material');key=ET.tostring(material,encoding='unicode')
                groups[key].append(lookup[uri]);materials[key]=copy.deepcopy(material);link.remove(visual)
    meshes=[];mapping={uri:uri for uri in kept}
    for uri in kept:
        meshes.append(lookup[uri]);shutil.copy2(args.source/uri,args.output/uri)
        source=(args.source/uri).with_suffix('.mtl')
        if source.exists():shutil.copy2(source,(args.output/uri).with_suffix('.mtl'))
    for index,(key,entries) in enumerate(groups.items()):
        uri=f'meshes/context_batch_{index:02d}.obj';vo=to=no=triangles=0
        with (args.output/uri).open('w') as target:
            target.write('o context\n')
            for entry in entries:
                vc=tc=nc=0
                with (args.source/entry['uri']).open() as stream:
                    for line in stream:
                        if line.startswith('v '):vc+=1;target.write(line)
                        elif line.startswith('vt '):tc+=1;target.write(line)
                        elif line.startswith('vn '):nc+=1;target.write(line)
                        elif line.startswith('# source '):target.write(line)
                        elif line.startswith('f '):
                            tokens=[v.split('/') for v in line.split()[1:]]
                            target.write('f '+' '.join(f'{int(v[0])+vo}/{int(v[1])+to if v[1] else ""}/{int(v[2])+no}' for v in tokens)+'\n')
                            triangles+=1
                vo+=vc;to+=tc;no+=nc;mapping[entry['uri']]=uri
        visual=element(field,'visual',name=f'context_batch_{index}')
        element(element(element(visual,'geometry'),'mesh'),'uri',uri);visual.append(materials[key])
        meshes.append({'uri':uri,'triangles':triangles,'color':entries[0]['color'],
                       'source_meshes':[e['uri'] for e in entries]})
    assert sum(m['triangles'] for m in meshes)==sum(m['triangles'] for m in manifest['meshes'])
    for organ in manifest['organs']:organ['meshes']=list(dict.fromkeys(mapping[uri] for uri in organ['meshes']))
    manifest['meshes']=meshes
    manifest['context_batch']={'method':'exact_triangle_uv_normal_concatenation',
                              'individual_calyx_meshes':len(kept),'context_batches':len(groups)}
    shutil.copytree(args.source/'textures',args.output/'textures')
    shutil.copy2(args.source/'inventory.json',args.output/'inventory.json')
    ET.indent(tree);tree.write(args.output/'field.sdf',encoding='utf-8',xml_declaration=True)
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest['context_batch']))


if __name__=='__main__':main()
