"""Conservative CAD surface/solid voxel cover, compressed into SDF boxes.

Only an explicitly identified part is refined. Mesh triangles plus the declared
CAD chord tolerance form a barrier; flood filling from outside retains enclosed
material conservatively. Open cavities stay open when the chosen resolution
can represent them. This is collision geometry, never a visual or mass edit.
"""
from __future__ import annotations

from collections import Counter, deque
import copy
import hashlib
import itertools
import math
from pathlib import Path

from .robot_kinematics import compose_poses, pose_identity
from .robot_spec import canonical_hash


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def _triangles(path):
    vertices, triangles = [], []
    for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
        row = line.split()
        if not row or row[0].startswith('#'):
            continue
        if row[0] == 'v':
            point = tuple(float(v) for v in row[1:4])
            if len(point) != 3 or not all(math.isfinite(v) for v in point):
                raise ValueError('Nonfinite CAD mesh vertex')
            vertices.append(point)
        elif row[0] == 'f':
            if len(row) != 4:
                raise ValueError('Refinement requires the admitted triangulated CAD OBJ')
            indices = [int(v.split('/')[0])-1 for v in row[1:]]
            if any(i < 0 or i >= len(vertices) for i in indices):
                raise ValueError('Invalid CAD triangle index')
            triangles.append(tuple(vertices[i] for i in indices))
    if not triangles:
        raise ValueError('CAD mesh contains no triangles')
    # Native facets can duplicate vertices at normal seams. Check the geometric
    # edge incidence at a nanometre weld scale, not its OBJ normal indices.
    edges = Counter()
    for triangle in triangles:
        welded = [tuple(round(v, 9) for v in p) for p in triangle]
        for a, b in zip(welded, welded[1:]+welded[:1]):
            if a != b:
                edges[tuple(sorted((a, b)))] += 1
    odd = sum(count % 2 for count in edges.values())
    if odd:
        raise ValueError('CAD mesh has open/odd boundary edges; solid flood-fill is not admitted')
    return vertices, triangles, dict(Counter(edges.values()))


def conservative_boxes(path, cell_m, chord_tolerance_m):
    """Cover every source triangle, then compress exactly the occupied cells.

Triangle/box separating axes prevent a triangle's rectangular bounds from
filling an aperture. Intersected cells are never omitted during compression.
Closed internal voids may be filled; this remains conservative and is recorded.
"""
    if not math.isfinite(cell_m) or cell_m <= 0 or not 0 <= chord_tolerance_m < cell_m:
        raise ValueError('Require positive voxel size and smaller nonnegative chord tolerance')
    vertices, triangles, edge_counts = _triangles(path)
    lower = [min(p[i] for p in vertices) for i in range(3)]
    upper = [max(p[i] for p in vertices) for i in range(3)]
    origin = [math.floor(v/cell_m)*cell_m-cell_m for v in lower]
    dims = [math.ceil((upper[i]-origin[i])/cell_m)+1 for i in range(3)]
    nx, ny, nz = dims
    count = nx*ny*nz
    if count > 2_000_000:
        raise ValueError('Refinement grid exceeds the bounded standard-library budget')
    states = bytearray(count)  # 0 unknown; 1 boundary/material; 2 outside
    stride = nx*ny
    def index(x, y, z):
        return x+nx*y+stride*z
    half = cell_m/2+chord_tolerance_m
    for triangle in triangles:
        a, b, c = triangle
        edges = [tuple(q[i]-p[i] for i in range(3)) for p, q in ((a,b),(b,c),(c,a))]
        axes = [_cross(edges[0], edges[1])]
        axes += [_cross(edge, unit) for edge in edges for unit in ((1,0,0),(0,1,0),(0,0,1))]
        projections = []
        for axis in axes:
            if max(abs(v) for v in axis) < 1e-18:
                continue
            values = [_dot(p, axis) for p in triangle]
            pad = half*sum(abs(v) for v in axis)+1e-14*sum(abs(v) for v in axis)
            projections.append((axis, min(values)-pad, max(values)+pad))
        lows = [max(0, math.floor((min(p[i] for p in triangle)-chord_tolerance_m-origin[i])/cell_m)) for i in range(3)]
        highs = [min(dims[i]-1, math.floor((max(p[i] for p in triangle)+chord_tolerance_m-origin[i])/cell_m)) for i in range(3)]
        for z in range(lows[2], highs[2]+1):
            cz = origin[2]+(z+.5)*cell_m
            for y in range(lows[1], highs[1]+1):
                cy = origin[1]+(y+.5)*cell_m
                for x in range(lows[0], highs[0]+1):
                    at = index(x,y,z)
                    if states[at]:
                        continue
                    cx = origin[0]+(x+.5)*cell_m
                    if all(lo <= axis[0]*cx+axis[1]*cy+axis[2]*cz <= hi for axis, lo, hi in projections):
                        states[at] = 1
    surface_count = states.count(1)
    queue = deque()
    for z in range(nz):
        for y in range(ny):
            for x in (0,nx-1):
                at=index(x,y,z)
                if states[at] == 0:states[at]=2;queue.append(at)
    for z in range(nz):
        for x in range(nx):
            for y in (0,ny-1):
                at=index(x,y,z)
                if states[at] == 0:states[at]=2;queue.append(at)
    for y in range(ny):
        for x in range(nx):
            for z in (0,nz-1):
                at=index(x,y,z)
                if states[at] == 0:states[at]=2;queue.append(at)
    while queue:
        at=queue.popleft();x=at%nx;y=(at//nx)%ny;z=at//stride
        neighbors=[]
        if x:neighbors.append(at-1)
        if x+1<nx:neighbors.append(at+1)
        if y:neighbors.append(at-nx)
        if y+1<ny:neighbors.append(at+nx)
        if z:neighbors.append(at-stride)
        if z+1<nz:neighbors.append(at+stride)
        for other in neighbors:
            if states[other] == 0:states[other]=2;queue.append(other)
    interior_count=states.count(0)
    for at in range(count):
        if states[at] == 0:states[at]=1
    occupied_count=states.count(1)
    occupied_digest=hashlib.sha256(states).hexdigest()
    boxes=[];covered=0
    def full_row(x0,x1,y,z):
        return all(v==1 for v in states[index(x0,y,z):index(x1,y,z)])
    # Grow X, then Z, then Y. This favors thin planar housing walls while
    # preserving every occupancy decision exactly; no bounding union of holes.
    for z in range(nz):
        for y in range(ny):
            for x in range(nx):
                if states[index(x,y,z)] != 1:continue
                x1=x+1
                while x1<nx and states[index(x1,y,z)]==1:x1+=1
                z1=z+1
                while z1<nz and full_row(x,x1,y,z1):z1+=1
                y1=y+1
                while y1<ny and all(full_row(x,x1,y1,zz) for zz in range(z,z1)):y1+=1
                for zz in range(z,z1):
                    for yy in range(y,y1):
                        states[index(x,yy,zz):index(x1,yy,zz)]=bytes(x1-x)
                size=[(x1-x)*cell_m,(y1-y)*cell_m,(z1-z)*cell_m]
                center=[origin[0]+(x+x1)*cell_m/2,origin[1]+(y+y1)*cell_m/2,origin[2]+(z+z1)*cell_m/2]
                boxes.append({'center_m':center,'size_m':size})
                covered+=(x1-x)*(y1-y)*(z1-z)
    if covered!=occupied_count or states.count(1):
        raise ValueError('Box compression lost or duplicated occupied source cells')
    return boxes, {'algorithm':'triangle_sat_surface_cover_and_outside_flood_fill_v1',
        'mesh_bounds_m':{'min':lower,'max':upper},'cell_m':cell_m,'chord_tolerance_m':chord_tolerance_m,
        'grid_dimensions':dims,'grid_cells':count,'surface_cells':surface_count,'interior_cells':interior_count,
        'occupied_cells':occupied_count,'occupied_grid_sha256':occupied_digest,'source_triangles':len(triangles),
        'edge_incidence_counts':edge_counts,'box_count':len(boxes),'compression_cell_coverage_exact':True,
        'maximum_surface_cover_outward_error_bound_m':math.sqrt(3)*(cell_m+chord_tolerance_m),
        'limitations':['Closed internal voids may be filled conservatively.',
                       'Narrow openings below the voxel resolution may close; do not label them collision-free.',
                       'CAD tessellation chord tolerance is an export input, not a measured hardware error.']}


def apply_refinements(data, asset_root, config):
    """Return a copied RobotSpec and evidence; source visuals/inertias unchanged."""
    result=copy.deepcopy(data)
    root=Path(asset_root).resolve(strict=True)
    reports=[]
    for entry in config['refinements']:
        matches=[(i,link) for i,link in enumerate(result['links'])
                 if any(c['name']==entry['collision_name'] for c in link['collisions'])]
        if len(matches)!=1:raise ValueError('Refinement must identify exactly one original collider')
        index,link=matches[0]
        old=next(c for c in link['collisions'] if c['name']==entry['collision_name'])
        visual=next((v for v in link['visuals'] if v['name']==entry['visual_name']),None)
        if visual is None or visual['geometry'].get('sha256')!=entry['mesh_sha256']:
            raise ValueError('Refinement visual/source identity differs')
        mesh=(root/visual['geometry']['uri']).resolve(strict=True)
        if not mesh.is_relative_to(root) or hashlib.sha256(mesh.read_bytes()).hexdigest()!=entry['mesh_sha256']:
            raise ValueError('Refinement mesh path/hash differs from admitted source')
        boxes,report=conservative_boxes(mesh,entry['cell_m'],entry['chord_tolerance_m'])
        replacement=[]
        for number,box in enumerate(boxes):
            pose=pose_identity();pose['xyz_m']=box['center_m']
            shape={'name':old['name']+'_cellcover_'+str(number),
                   'pose':compose_poses(visual['pose'],pose),'geometry':{'type':'box','size_m':box['size_m']}}
            if 'surface' in old:shape['surface']=copy.deepcopy(old['surface'])
            replacement.append(shape)
        link['collisions']=[c for c in link['collisions'] if c['name']!=old['name']]+replacement
        report.update(link=link['name'],original_collision=old,mesh_sha256=entry['mesh_sha256'],
                      config_sha256=canonical_hash(config),source_visual_name=visual['name'],
                      replacement_sha256=canonical_hash(replacement))
        reports.append(report)
        result['parameter_metadata'][f'/links/{index}/collisions']={
            'status':'derivado_de_CAD','source':entry['source_document'],
            'revision':entry['mesh_sha256'],'method':'Conservative source-triangle voxel cover; report '+canonical_hash(report),
            'uncertainty':'Explicit mesh chord tolerance and voxel cover; no hardware-contact validation',
            'update_class':'cad_reexport'}
    return result, {'schema_version':'cad-collision-refinement/1.0','refinements':reports,
                    'visuals_and_inertias_unchanged':True,'native_contact_validation':'NOT_EXECUTED'}
