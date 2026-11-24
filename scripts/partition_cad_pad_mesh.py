#!/usr/bin/env python3
"""Partition a verified CAD polyhedron into an exactly equivalent convex union.

Original boundary vertices and triangles remain unchanged; a proven interior
kernel vertex may be added. Exact rational predicates certify convex unions.
No convex hull is taken across a cavity or concavity.
Native acceptance requires a separate profile revision and fresh experiment.
"""
from __future__ import annotations
import argparse
from collections import Counter
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.robot_mesh_geometry import read_collision_obj,TriangleMesh


def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def area(poly):return sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(poly,poly[1:]+poly[:1]))/2
def edges(poly):return list(zip(poly,poly[1:]+poly[:1]))
def canonical_edge(a,b):return tuple(sorted((a,b)))


def intersection(subject,clip):
    """Exact convex polygon clipping, including empty/shared-edge cases."""
    result=list(subject)
    for a,b in edges(clip):
        previous=result;result=[]
        if not previous:break
        for p,q in edges(previous):
            dp,dq=cross(a,b,p),cross(a,b,q)
            if dp>=0:result.append(p)
            if (dp<0<dq) or (dq<0<dp):
                t=dp/(dp-dq);result.append(tuple(p[k]+t*(q[k]-p[k]) for k in range(2)))
            elif dp<0 and dq==0:result.append(q)
    clean=[]
    for p in result:
        if not clean or clean[-1]!=p:clean.append(p)
    if len(clean)>1 and clean[0]==clean[-1]:clean.pop()
    return clean


def cap_boundary(triangles):
    counts=Counter(edge for triangle in triangles for edge in edges(triangle))
    for edge,count in list(counts.items()):
        reverse=(edge[1],edge[0]);cancel=min(counts[edge],counts[reverse])
        counts[edge]-=cancel;counts[reverse]-=cancel
    if any(count>1 for count in counts.values()):raise ValueError('Repeated oriented boundary edge')
    return {edge for edge,count in counts.items() if count}


def convex_merge(first,second):
    shared=set(edges(first))&{(b,a) for a,b in edges(second)}
    if not shared:return None
    boundary=cap_boundary([first,second]);following={}
    for a,b in boundary:
        if a in following:return None
        following[a]=b
    start=min(following);polygon=[start];current=following[start]
    while current!=start:
        if current in polygon or current not in following:return None
        polygon.append(current);current=following[current]
    if len(polygon)!=len(boundary):return None
    # Removing exactly collinear points changes no surface or material volume.
    changed=True
    while changed and len(polygon)>3:
        changed=False
        for i in range(len(polygon)):
            if cross(polygon[i-1],polygon[i],polygon[(i+1)%len(polygon)])==0:
                polygon.pop(i);changed=True;break
    if any(cross(polygon[i-1],polygon[i],polygon[(i+1)%len(polygon)])<0 for i in range(len(polygon))):return None
    if area(polygon)!=area(first)+area(second):raise ValueError('Convex merge changed exact area')
    return polygon


def extrusion_partition(vertices,faces,axis=2):
    TriangleMesh(vertices,faces)
    indices=[i for i in range(3) if i!=axis]
    rational=[tuple(F(str(x)) for x in vertex) for vertex in vertices]
    levels=sorted({p[axis] for p in rational})
    if len(levels)!=2:raise ValueError('Only exact two-plane straight extrusions are supported')
    lower,upper=levels;caps=[[],[]];sides={}
    for face in faces:
        points=[rational[i] for i in face];projected=[tuple(p[i] for i in indices) for p in points]
        heights={p[axis] for p in points}
        if len(heights)==1:
            index=0 if points[0][axis]==lower else 1
            if area(projected)==0:raise ValueError('Degenerate planar cap')
            if area(projected)<0:projected.reverse()
            caps[index].append(projected)
        else:
            unique=set(projected)
            if len(unique)!=2:raise ValueError('Side is not a straight extruded boundary edge')
            edge=canonical_edge(*unique);side=[]
            for point,project in zip(points,projected):
                side.append((F(int(project==edge[1])),(point[axis]-lower)/(upper-lower)))
            if area(side)<0:side.reverse()
            sides.setdefault(edge,[]).append(side)
    if not all(caps):raise ValueError('Both planar caps are required')
    for triangles in caps:
        for i,first in enumerate(triangles):
            for second in triangles[i+1:]:
                if abs(area(intersection(first,second)))>0:raise ValueError('Cap triangle interiors overlap')
    boundaries=[cap_boundary(cap) for cap in caps]
    if boundaries[0]!=boundaries[1]:raise ValueError('Upper and lower cap boundaries differ')
    cap_areas=[sum(area(t) for t in cap) for cap in caps]
    if cap_areas[0]!=cap_areas[1]:raise ValueError('Cap areas differ')
    for triangle in caps[0]:
        if sum(abs(area(intersection(triangle,other))) for other in caps[1])!=area(triangle):
            raise ValueError('Planar caps do not cover the same material region')
    expected={canonical_edge(*edge) for edge in boundaries[0]}
    if set(sides)!=expected:raise ValueError('Side walls differ from exact cap boundary')
    for triangles in sides.values():
        if sum(area(t) for t in triangles)!=1:raise ValueError('Side wall does not cover full extrusion')
        for i,first in enumerate(triangles):
            for second in triangles[i+1:]:
                if abs(area(intersection(first,second)))>0:raise ValueError('Side triangles overlap')
    polygons=[list(t) for t in caps[0]];merges=0;changed=True
    while changed:
        changed=False
        for i in range(len(polygons)):
            for j in range(i+1,len(polygons)):
                merged=convex_merge(polygons[i],polygons[j])
                if merged is not None:
                    polygons[i]=merged;polygons.pop(j);merges+=1;changed=True;break
            if changed:break
    if sum(area(poly) for poly in polygons)!=cap_areas[0]:raise ValueError('Partition volume mismatch')
    cells=[]
    for polygon in polygons:
        points=[]
        for height in (lower,upper):
            for p in polygon:
                point=[None]*3;point[axis]=height
                for i,value in zip(indices,p):point[i]=value
                points.append(tuple(float(value) for value in point))
        n=len(polygon);triangles=[]
        for i in range(1,n-1):triangles.extend([(0,i+1,i),(n,n+i,n+i+1)])
        for i in range(n):
            j=(i+1)%n;triangles.extend([(i,j,n+j),(i,n+j,n+i)])
        # The ordered projected plane has positive normal on axes0/2 and
        # negative normal on axis1; adapt the prism orientation accordingly.
        if axis==1:triangles=[(a,c,b) for a,b,c in triangles]
        TriangleMesh(points,triangles)
        cells.append((points,triangles))
    return cells,{'status':'EXACT_GEOMETRY_PARTITION_ONLY','native_acceptance':False,
        'axis':axis,'levels_m':[float(lower),float(upper)],'source_cap_triangles':len(caps[0]),
        'convex_cells':len(cells),'exact_convex_merges':merges,'boundary_edges':len(expected),
        'proof':'Rational disjoint cap triangles, identical cap coverage, exact extruded boundary walls, area-preserving convex adjacent unions.',
        'cross_section_area_m2':float(cap_areas[0]),'exact_area_fraction':str(cap_areas[0]),
        'volume_m3':float(cap_areas[0]*(upper-lower)),'exact_volume_fraction':str(cap_areas[0]*(upper-lower)),
        'surface_change':'None; only interior partition surfaces are added, without filling any cap cavity.',
        'coordinate_scope':'Exact rational predicates on decimal representations of parsed source float coordinates; output reparses to the same original float vertices.'}


def write_obj(path,vertices,faces):
    lines=['# Original project-authored exact convex partition of source CAD tessellation.']
    for p in vertices:lines.append('v '+' '.join(str(v) for v in p))
    for a,b,c in faces:
        u=[vertices[b][i]-vertices[a][i] for i in range(3)];v=[vertices[c][i]-vertices[a][i] for i in range(3)]
        normal=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        length=math.sqrt(sum(n*n for n in normal));lines.append('vn '+' '.join(str(n/length) for n in normal))
    for n,face in enumerate(faces,1):lines.append('f '+' '.join(str(i+1)+'//'+str(n) for i in face))
    path.write_text('\n'.join(lines)+'\n')


def determinant(a,b,c):
    return a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])


def subtract(a,b):return tuple(x-y for x,y in zip(a,b))


def star_partition(vertices,faces):
    """Exact boundary tetrahedra from a rigorously verified visibility kernel.

    The source must be a single closed oriented component. A strictly interior
    point on the inner side of EVERY outward triangle plane is a star kernel.
    Radial tetrahedra then partition the source, retaining every boundary face.
    Only adjacent tetrahedral unions proven convex are merged.
    """
    original=TriangleMesh(vertices,faces)
    if len(original.component_signed_volumes)!=1:raise ValueError('One closed material component is required')
    points=[];mapping={}
    for vertex in vertices:
        key=tuple(F(str(x)) for x in vertex)
        if key not in mapping:mapping[key]=len(points);points.append(key)
    triangles=[tuple(mapping[tuple(F(str(x)) for x in vertices[i])] for i in face) for face in faces]
    counts=Counter(tuple(sorted((a,b))) for face in triangles for a,b in zip(face,face[1:]+face[:1]))
    if set(counts.values())!={2}:raise ValueError('Exact source vertices do not form a watertight manifold')
    lower=[min(p[k] for p in points) for k in range(3)];upper=[max(p[k] for p in points) for k in range(3)]
    # Prove the exact decimal representation that the output OBJ will contain,
    # including the rounding of this newly added INTERIOR point.
    kernel=tuple(F(str(float((a+b)/2))) for a,b in zip(lower,upper))
    def side(point,face):
        a,b,c=(points[i] for i in face)
        return determinant(subtract(b,a),subtract(c,a),subtract(point,a))
    kernel_sides=[side(kernel,face) for face in triangles]
    if any(value>=0 for value in kernel_sides):raise ValueError('Bounding center is not a strict star kernel; no arbitrary hull fallback')
    kernel_index=len(points);points.append(kernel)
    cells=[[(a,b,c),(kernel_index,b,a),(kernel_index,c,b),(kernel_index,a,c)] for a,b,c in triangles]
    original_volume=-sum(kernel_sides)/6
    merge_count=0
    def is_convex(boundary,fast_rejection=True):
        ids={i for face in boundary for i in face}
        # Fast rejection only; every accepted union still uses exact rationals.
        floats={i:tuple(float(v) for v in points[i]) for i in ids}
        if fast_rejection:
            for face in boundary:
                a,b,c=(floats[i] for i in face)
                for i in ids:
                    # This cutoff only skips impossible merge attempts. It is
                    # never an acceptance tolerance: the exact test follows.
                    if determinant(subtract(b,a),subtract(c,a),subtract(floats[i],a))>1e-18:return False
        return all(side(points[i],face)<=0 for face in boundary for i in ids)
    while True:
        ownership={};pairs=set()
        for i,cell in enumerate(cells):
            for face in cell:
                key=tuple(sorted(face))
                if key in ownership:pairs.add(tuple(sorted((i,ownership[key]))))
                else:ownership[key]=i
        merged=False
        for i,j in sorted(pairs):
            first={tuple(sorted(face)):face for face in cells[i]};second={tuple(sorted(face)):face for face in cells[j]}
            shared=first.keys()&second.keys()
            boundary=[face for key,face in first.items() if key not in shared]+[face for key,face in second.items() if key not in shared]
            if is_convex(boundary):
                cells[i]=boundary;cells.pop(j);merge_count+=1;merged=True;break
        if not merged:break
    output=[];cell_volume=F(0);remaining=Counter()
    for cell in cells:
        if not is_convex(cell,False):raise ValueError('Final cell is not exactly convex')
        ids=sorted({i for face in cell for i in face});local={i:n for n,i in enumerate(ids)}
        coordinates=[tuple(float(x) for x in points[i]) for i in ids];local_faces=[tuple(local[i] for i in face) for face in cell]
        TriangleMesh(coordinates,local_faces)
        reference=points[ids[0]]
        cell_volume+=sum(determinant(*(subtract(points[i],reference) for i in face)) for face in cell)/6
        for face in cell:remaining[tuple(sorted(face))]+=1
        output.append((coordinates,local_faces))
    original_faces={tuple(sorted(face)) for face in triangles}
    if any(count!=(1 if face in original_faces else 2) for face,count in remaining.items()) or not original_faces<=remaining.keys():
        raise ValueError('Partition changed the original boundary or left an interior seam open')
    if cell_volume!=original_volume:raise ValueError('Exact rational union volume changed')
    return output,{'status':'EXACT_GEOMETRY_PARTITION_ONLY','native_acceptance':False,
        'method':'star_kernel_tetrahedra_then_exact_convex_adjacent_unions',
        'source_boundary_triangles':len(triangles),'convex_cells':len(output),'exact_convex_merges':merge_count,
        'kernel_point_m':[float(v) for v in kernel],'kernel_halfspace_determinants_strictly_negative':True,
        'original_boundary_faces_preserved_once':len(original_faces),'interior_faces_paired':sum(c==2 for c in remaining.values()),
        'exact_volume_fraction':str(original_volume),'volume_m3':float(original_volume),
        'surface_change':'None: all original triangles preserved exactly once; only interior partition surfaces added.',
        'proof':'Exact watertight oriented source, strict visibility kernel behind every boundary plane, radial tetrahedra, adjacent unions accepted only after exact rational convexity, original boundary multiplicity and exact volume equality.',
        'coordinate_scope':'Rational predicates on decimal representations of parsed source float coordinates. Original boundary float vertices are unchanged; one interior kernel vertex may be added.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--axis',type=int,choices=(0,1,2),default=2)
    parser.add_argument('--method',choices=('extrusion','star'),required=True)
    args=parser.parse_args();vertices,faces,_,_=read_collision_obj(args.input)
    cells,report=extrusion_partition(vertices,faces,args.axis) if args.method=='extrusion' else star_partition(vertices,faces)
    args.output.mkdir(parents=True,exist_ok=False)
    report['source_path']=str(args.input);report['source_sha256']=hashlib.sha256(args.input.read_bytes()).hexdigest()
    report['script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();report['cells']=[]
    original={tuple(p) for p in vertices}
    if args.method=='star':original.add(tuple(report['kernel_point_m']))
    for i,(points,triangles) in enumerate(cells):
        if not set(points)<=original:raise ValueError('Partition introduced a non-original vertex')
        path=args.output/('cell_%03d.obj'%i);write_obj(path,points,triangles)
        replay,tri,_,_=read_collision_obj(path)
        if replay!=points or tri!=triangles:raise ValueError('OBJ serialization changed a cell')
        report['cells'].append({'uri':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'vertices':len(points),'triangles':len(triangles)})
    (args.output/'certificate.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({key:report[key] for key in ('status','convex_cells','volume_m3')}))


if __name__=='__main__':main()
