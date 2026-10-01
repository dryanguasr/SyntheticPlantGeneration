"""Blender BVH audit of continuous routes against original metric field surfaces.

The enclosing sphere is conservative for every drone attitude. Sampling uses a
Lipschitz correction, so a positive result is a lower bound, not vertex clearance.
Run with Blender --background --python this_file -- --field ... --output ...
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uchuva_gazebo.neo import LENGTH, WIDTH, HEIGHT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--field', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--telemetry', type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    manifest = json.loads((args.field / 'manifest.json').read_text())
    radius = math.sqrt(LENGTH**2 + WIDTH**2 + HEIGHT**2) / 2
    # All altitude changes and yaw turns are outside x = +/-4.6 m.
    route = [(-4.6, 0, .65), (4.6, 0, .65), (4.6, 0, .95),
             (-4.6, 0, .95), (-4.6, 0, .65), (4.6, 0, .65),
             (4.6, 0, .95), (-4.6, 0, .95)]
    if args.telemetry:
        route = [s['position'] for s in json.loads(args.telemetry.read_text())['samples']]
    lo = [min(p[i] for p in route) - 1 for i in range(3)]
    hi = [max(p[i] for p in route) + 1 for i in range(3)]
    vertices, triangles, names, hashes = [], [], [], {}
    for index, mesh in enumerate(manifest['meshes']):
        path = args.field / mesh['uri']
        hashes[mesh['uri']] = hashlib.sha256(path.read_bytes()).hexdigest()
        local = []; name = path.name
        with path.open() as stream:
            for line in stream:
                if line.startswith('# source '):
                    name = path.name + ':' + line.strip()[9:]
                elif line.startswith('v '):
                    local.append(tuple(map(float, line.split()[1:4])))
                elif line.startswith('f '):
                    points = [local[int(v.split('/')[0])-1] for v in line.split()[1:]]
                    if any(max(p[i] for p in points) < lo[i] or min(p[i] for p in points) > hi[i] for i in range(3)):
                        continue
                    start = len(vertices); vertices.extend(points)
                    triangles.append((start, start+1, start+2)); names.append(name)
        if index % 60 == 0: print(f'Audited mesh {index}/{len(manifest["meshes"])}', flush=True)
    # Original marker / ground boxes are included as physical surfaces.
    tree = ET.parse(args.field / 'field.sdf')
    faces = [(0,1,2),(0,2,3),(4,6,5),(4,7,6),(0,4,5),(0,5,1),
             (3,2,6),(3,6,7),(0,3,7),(0,7,4),(1,5,6),(1,6,2)]
    signs = [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
             (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
    for visual in tree.findall('.//visual'):
        size = visual.findtext('geometry/box/size')
        if not size: continue
        pose = list(map(float, visual.findtext('pose', '0 0 0 0 0 0').split()))
        if any(abs(v)>1e-9 for v in pose[3:]): raise ValueError('Rotated box requires explicit transform')
        half = [float(v)/2 for v in size.split()]; start = len(vertices)
        vertices.extend(tuple(pose[i]+sign[i]*half[i] for i in range(3)) for sign in signs)
        triangles.extend(tuple(start+i for i in f) for f in faces)
        names.extend([visual.attrib['name']]*len(faces))
    bvh = BVHTree.FromPolygons(vertices, triangles, all_triangles=True)
    segments = []; samples = []
    for index, (a,b) in enumerate(zip(route, route[1:])):
        a,b = Vector(a),Vector(b); steps = max(1, math.ceil((b-a).length/.01))
        correction = (b-a).length/steps/2
        best = None
        for j in range(steps+1):
            p = a+(b-a)*(j/steps)
            nearest, normal, triangle, distance = bvh.find_nearest(p)
            # Also check collision cylinders, even if their proxy exceeds the visible surface.
            name = names[triangle]
            for c in manifest['colliders']:
                start,end = Vector(c['start_m']),Vector(c['end_m']); axis=end-start
                u = max(0,min(1,(p-start).dot(axis)/axis.length_squared))
                d = (p-(start+u*axis)).length-c['radius_m']
                if d < distance: distance,name = d,c['source_id']
            result = {'center_m':list(p),'obstacle':name,'center_surface_distance_m':distance,
                      'envelope_clearance_lower_bound_m':distance-radius-correction}
            samples.append(result)
            if best is None or distance < best['center_surface_distance_m']: best = result
        segments.append({'segment':index,'from_m':list(a),'to_m':list(b),
                         'sampling_correction_m':correction, **best})
    minimum = min(s['envelope_clearance_lower_bound_m'] for s in segments)
    result = {'script_version':'low-flight-clearance/0.1','seed':manifest['seed'],
              'parameter_preset':'central_aisle_low_v1','required_margin_m':.15,
              'enclosing_sphere_radius_m':radius,'minimum_clearance_lower_bound_m':minimum,
              'passed':minimum>=.15,'segments':segments,'samples':samples,'source_mesh_sha256':hashes,
              'method':'triangle BVH + conservative cylinder capsules; continuous sphere sweep with Lipschitz correction',
              'excluded_triangles_lower_bound_m':1-radius,
              'scope':'planned route' if not args.telemetry else 'piecewise-linear executed poses'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_mesh_sha256','segments','samples')}),flush=True)


if __name__ == '__main__': main()
