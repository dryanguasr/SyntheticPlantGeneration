"""Use bundled Blender bmesh to bound exact plant meshes for tight framing."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import bmesh


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--field',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    source=args.field/'manifest.json';manifest=json.loads(source.read_text())
    output=args.field/'framing_hulls.json'
    if output.exists():raise FileExistsError(output)
    groups={}
    for entry in manifest['meshes']:
        stem=Path(entry['uri']).stem
        if stem.startswith('plant_'):groups.setdefault('_'.join(stem.split('_')[:2]),[]).append(entry['uri'])
    hulls={}
    for plant,uris in groups.items():
        vertices=set()
        for uri in uris:
            with (args.field/uri).open() as stream:
                for line in stream:
                    if line.startswith('v '):vertices.add(tuple(map(float,line.split()[1:4])))
        mesh=bmesh.new()
        for point in vertices:mesh.verts.new(point)
        result=bmesh.ops.convex_hull(mesh,input=list(mesh.verts),use_existing_faces=False)
        hulls[plant]=[list(v.co) for v in result['geom'] if isinstance(v,bmesh.types.BMVert)]
        if len(hulls[plant])<4:raise ValueError('Invalid plant hull')
        mesh.free();print('FRAMING_HULL',plant,len(vertices),len(hulls[plant]),flush=True)
    output.write_text(json.dumps(dict(version='exact-mesh-framing-hulls/1.0',seed=manifest['seed'],
        parameter_preset=manifest['parameter_preset'],manifest_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        method='Bundled Blender bmesh convex hull; no external dependency',plants=hulls),indent=2))


if __name__=='__main__':main()
