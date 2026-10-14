"""Store context triangles as binary glTF; keep calyx OBJ assets unchanged."""
import argparse
from array import array
import json
import os
from pathlib import Path
import shutil
import struct
import xml.etree.ElementTree as ET


def convert(source,target):
    positions=array('f');normals=array('f');uvs=array('f')
    output=[array('f'),array('f'),array('f')]
    low=[float('inf')]*3;high=[-float('inf')]*3
    with source.open() as stream:
        for line in stream:
            if line.startswith('v '):positions.extend(map(float,line.split()[1:4]))
            elif line.startswith('vn '):normals.extend(map(float,line.split()[1:4]))
            elif line.startswith('vt '):uvs.extend(map(float,line.split()[1:3]))
            elif line.startswith('f '):
                tokens=line.split()[1:]
                if len(tokens)!=3:raise ValueError('Only already-triangulated context is accepted')
                for token in tokens:
                    v,t,n=token.split('/');v=(int(v)-1)*3;n=(int(n)-1)*3
                    point=positions[v:v+3];output[0].extend(point);output[1].extend(normals[n:n+3])
                    coord=uvs[(int(t)-1)*2:(int(t)-1)*2+2] if t else (0,0)
                    output[2].extend((coord[0],1-coord[1]))
                    for d in range(3):low[d]=min(low[d],point[d]);high[d]=max(high[d],point[d])
    count=len(output[0])//3;views=[];offset=0
    for data in output:
        views.append({'buffer':0,'byteOffset':offset,'byteLength':len(data)*4,'target':34962});offset+=len(data)*4
    document={'asset':{'version':'2.0','generator':'segmentation-context-binary/1.0'},
        'buffers':[{'byteLength':offset}],'bufferViews':views,
        'accessors':[{'bufferView':i,'componentType':5126,'count':count,'type':kind,
                      **({'min':low,'max':high} if i==0 else {})} for i,kind in enumerate(['VEC3','VEC3','VEC2'])],
        'meshes':[{'primitives':[{'attributes':{'POSITION':0,'NORMAL':1,'TEXCOORD_0':2},'mode':4,'material':0}]}],
        'materials':[{'pbrMetallicRoughness':{'baseColorFactor':[1,1,1,1],'metallicFactor':0,'roughnessFactor':1}}],
        'nodes':[{'mesh':0}],'scenes':[{'nodes':[0]}],'scene':0,
        'extras':{'coordinates':'Gazebo world Z-up metres; identity node transform','source':source.name,'uv':'V inverted for glTF convention; Gazebo rendering verification required'}}
    payload=json.dumps(document,separators=(',',':')).encode();payload+=b' '*((-len(payload))%4)
    with target.open('wb') as stream:
        stream.write(struct.pack('<III',0x46546C67,2,12+8+len(payload)+8+offset))
        stream.write(struct.pack('<II',len(payload),0x4E4F534A));stream.write(payload)
        stream.write(struct.pack('<II',offset,0x004E4942))
        for data in output:data.tofile(stream)
    return {'source_triangles':count//3,'binary_bytes':target.stat().st_size,'bounds_m':[low,high],
            'position_precision':'float32','calyx_assets':'unchanged'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False);(args.output/'meshes').mkdir()
    manifest=json.loads((args.source/'manifest.json').read_text());mapping={};reports=[]
    for mesh in manifest['meshes']:
        old=mesh['uri'];source=args.source/old
        if source.stem.startswith('context_batch_'):
            new=str(Path(old).with_suffix('.glb')).replace('\\','/')
            report=convert(source,args.output/new);assert report['source_triangles']==mesh['triangles']
            reports.append({'source':old,'target':new,**report});mesh['uri']=new
            print('BINARY_CONTEXT',new,report['binary_bytes'],flush=True)
        else:
            new=old
            for path in (source,source.with_suffix('.mtl')):
                if path.exists():
                    destination=args.output/'meshes'/path.name
                    try:os.link(path,destination)
                    except OSError:shutil.copy2(path,destination)
        mapping[old]=new
    for organ in manifest['organs']:organ['meshes']=[mapping[u] for u in organ['meshes']]
    tree=ET.parse(args.source/'field.sdf')
    for uri in tree.findall('.//uri'):
        if uri.text in mapping:uri.text=mapping[uri.text]
    ET.indent(tree);tree.write(args.output/'field.sdf',encoding='utf-8',xml_declaration=True)
    shutil.copytree(args.source/'textures',args.output/'textures');shutil.copy2(args.source/'inventory.json',args.output/'inventory.json')
    manifest['binary_context']={'reports':reports,'render_validation':'pending'}
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
