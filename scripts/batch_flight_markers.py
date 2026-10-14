"""Batch axis-aligned marker boxes without changing geometry or calyx identity."""
import argparse
from collections import defaultdict
import copy
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'meshes').mkdir()
    for name in ('mission.json', 'preflight.json', 'inventory.json', 'provenance.json'):
        shutil.copy2(args.source/name, args.output/name)
    tree = ET.parse(args.source/'flight.sdf')
    # Resolve existing assets before moving the world to another directory.
    for tag in ('uri', 'albedo_map', 'normal_map', 'roughness_map'):
        for node in tree.findall('.//'+tag):
            if node.text and '://' not in node.text and not node.text.startswith('/mnt/'):
                node.text = (args.source/node.text).resolve().as_posix()
                if node.text[1:3] == ':/':
                    node.text = '/mnt/'+node.text[0].lower()+node.text[2:]
    link = tree.find("world/model[@name='field']/link")
    groups = defaultdict(list)
    for visual in list(link.findall('visual')):
        if visual.get('name').startswith('marker_'):
            pose = list(map(float, visual.findtext('pose').split()))
            if any(abs(x)>1e-9 for x in pose[3:]):
                raise ValueError('Rotated marker requires a full transform')
            groups[ET.tostring(visual.find('material'))].append(visual)
    signs = ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
             (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))
    faces = ((0,3,2,1),(4,5,6,7),(0,1,5,4),(3,7,6,2),(0,4,7,3),(1,2,6,5))
    normals = ((0,0,-1),(0,0,1),(0,-1,0),(0,1,0),(-1,0,0),(1,0,0))
    for index, visuals in enumerate(groups.values()):
        uri = f'meshes/marker_batch_{index}.obj'
        with (args.output/uri).open('w') as stream:
            stream.write('o markers\n')
            for k, visual in enumerate(visuals):
                center = list(map(float, visual.findtext('pose').split()))[:3]
                half = [float(x)/2 for x in visual.findtext('geometry/box/size').split()]
                for sign in signs:
                    stream.write('v '+' '.join(f'{center[d]+sign[d]*half[d]:.12g}' for d in range(3))+'\n')
                for j, (face, normal) in enumerate(zip(faces, normals)):
                    stream.write('vn '+' '.join(map(str, normal))+'\n')
                    for tri in ((face[0],face[1],face[2]),(face[0],face[2],face[3])):
                        stream.write('f '+' '.join(f'{8*k+v+1}//{6*k+j+1}' for v in tri)+'\n')
                link.remove(visual)
        visual = ET.SubElement(link, 'visual', name=f'marker_batch_{index}')
        ET.SubElement(ET.SubElement(ET.SubElement(visual,'geometry'),'mesh'),'uri').text=uri
        visual.append(copy.deepcopy(visuals[0].find('material')))
    ET.indent(tree)
    tree.write(args.output/'flight.sdf', encoding='utf-8', xml_declaration=True)
    report = {'source_boxes':sum(map(len,groups.values())), 'batches':len(groups),
              'geometry':'Exact box triangles; no marker cells removed',
              'calyx_instances':'unchanged', 'RGB_decoding_validation':'pending'}
    (args.output/'marker_batch.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))


if __name__ == '__main__':
    main()
