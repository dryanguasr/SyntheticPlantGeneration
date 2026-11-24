"""Verified triangle meshes and reusable pure-Python BVH solid distances.

Distances are exact for the admitted tessellation (within floating point), not
for the untessellated CAD or hardware. Native cylinders use a circumscribed
32-sided audit prism; this can reject a marginal gap but cannot invent one.
No asset path escapes an explicit root, and no URI is downloaded implicitly.
"""
from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass
import hashlib
import heapq
import itertools
import math
from pathlib import Path, PurePosixPath

from .robot_kinematics import inverse_pose, transform_point, rotate_vector


def _sub(a, b): return tuple(x-y for x, y in zip(a, b))
def _dot(a, b): return sum(x*y for x, y in zip(a, b))
def _cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def _clamp(value): return max(0., min(1., value))


def point_segment_distance(point, a, b):
    direction = _sub(b, a)
    denominator = _dot(direction, direction)
    fraction = _clamp(_dot(_sub(point, a), direction)/denominator) if denominator else 0.
    return math.dist(point, tuple(a[i]+fraction*direction[i] for i in range(3)))


def point_triangle_distance(point, a, b, c):
    u, v, w = _sub(b, a), _sub(c, a), _sub(point, a)
    normal=_cross(u,v); denominator=_dot(normal,normal)
    if denominator > 0:
        x, y = _dot(_cross(w,v),normal)/denominator, _dot(_cross(u,w),normal)/denominator
        if x >= 0 and y >= 0 and x+y <= 1:
            return math.dist(point, tuple(a[i]+x*u[i]+y*v[i] for i in range(3)))
    return min(point_segment_distance(point,a,b), point_segment_distance(point,b,c), point_segment_distance(point,c,a))


def segment_segment_distance(p, q, a, b):
    d1, d2, r = _sub(q,p), _sub(b,a), _sub(p,a)
    aa, ee, ff = _dot(d1,d1), _dot(d2,d2), _dot(d2,r)
    if aa == 0 and ee == 0:
        return math.dist(p,a)
    if aa == 0:
        s, t = 0., _clamp(ff/ee)
    else:
        cc = _dot(d1,r)
        if ee == 0:
            t, s = 0., _clamp(-cc/aa)
        else:
            bb = _dot(d1,d2)
            denominator = aa*ee-bb*bb
            s = _clamp((bb*ff-cc*ee)/denominator) if denominator > 1e-14*aa*ee else 0.
            t = (bb*s+ff)/ee
            if t < 0:
                t, s = 0., _clamp(-cc/aa)
            elif t > 1:
                t, s = 1., _clamp((bb-cc)/aa)
    return math.dist(tuple(p[i]+s*d1[i] for i in range(3)), tuple(a[i]+t*d2[i] for i in range(3)))


def segment_triangle_distance(start, end, a, b, c):
    direction, edge1, edge2 = _sub(end,start), _sub(b,a), _sub(c,a)
    h = _cross(direction,edge2); determinant = _dot(edge1,h)
    if determinant != 0:
        delta = _sub(start,a); u = _dot(delta,h)/determinant
        q = _cross(delta,edge1); v = _dot(direction,q)/determinant
        t = _dot(edge2,q)/determinant
        if -1e-12 <= u <= 1+1e-12 and -1e-12 <= v and u+v <= 1+1e-12 and -1e-12 <= t <= 1+1e-12:
            return 0.
    return min(point_triangle_distance(start,a,b,c), point_triangle_distance(end,a,b,c),
               segment_segment_distance(start,end,a,b), segment_segment_distance(start,end,b,c),
               segment_segment_distance(start,end,c,a))


def triangle_triangle_distance(first, second):
    return min(*(segment_triangle_distance(first[i],first[(i+1)%3],*second) for i in range(3)),
               *(segment_triangle_distance(second[i],second[(i+1)%3],*first) for i in range(3)))


def _bounds(points):
    return tuple(min(p[i] for p in points) for i in range(3)), tuple(max(p[i] for p in points) for i in range(3))


def _bounds_gap(first, second):
    return math.sqrt(sum(max(first[0][i]-second[1][i],second[0][i]-first[1][i],0.)**2 for i in range(3)))


def _winding(triangles, point):
    angle = 0.
    for triangle in triangles:
        a,b,c=(_sub(v,point) for v in triangle)
        la,lb,lc=(math.sqrt(_dot(v,v)) for v in (a,b,c))
        if min(la,lb,lc)<1e-14:
            raise ValueError('Ambiguous touching shell witness')
        denominator=la*lb*lc+_dot(a,b)*lc+_dot(b,c)*la+_dot(c,a)*lb
        angle+=2*math.atan2(_dot(a,_cross(b,c)),denominator)
    return angle/(4*math.pi)


def read_collision_obj(path, *, require_normals=True):
    """Read the triangulated SI OBJ subset shared with the native importer.

    Normal references are required because the installed native importer needs
    them. They do not replace the independent face-winding topology checks.
    """
    vertices, faces, normals, normal_faces = [], [], [], []
    for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
        row = line.split()
        if not row or row[0].startswith('#'):
            continue
        if row[0] in ('v', 'vn'):
            if len(row) != 4:
                raise ValueError('Collision OBJ positions/normals must have three components')
            value = tuple(float(x) for x in row[1:])
            if not all(math.isfinite(x) for x in value):
                raise ValueError('Nonfinite collision OBJ position/normal')
            if row[0] == 'vn':
                if abs(sum(x*x for x in value)-1) > 1e-4:
                    raise ValueError('Collision OBJ normal must be unit length')
                normals.append(value)
            else:
                vertices.append(value)
        elif row[0] == 'f':
            if len(row) != 4:
                raise ValueError('Collision OBJ must be explicitly triangulated')
            values = [x.split('/') for x in row[1:]]
            if any(not x[0] or int(x[0]) <= 0 for x in values):
                raise ValueError('Collision OBJ requires positive absolute vertex indices')
            faces.append(tuple(int(x[0])-1 for x in values))
            if require_normals:
                if any(len(x) != 3 or not x[2] or int(x[2]) <= 0 for x in values):
                    raise ValueError('Collision OBJ requires explicit positive normal indices')
                normal_faces.append(tuple(int(x[2])-1 for x in values))
    if not vertices or not faces:
        raise ValueError('Empty collision OBJ')
    if any(i >= len(vertices) for face in faces for i in face):
        raise ValueError('Collision OBJ vertex index outside asset')
    if require_normals and any(i >= len(normals) for face in normal_faces for i in face):
        raise ValueError('Collision OBJ normal index outside asset')
    return vertices, faces, normals, normal_faces


def _consistent_face_signs(vertices, faces):
    """Orient closed triangle chains without changing any surface coordinates."""
    edges={}
    for number,face in enumerate(faces):
        points=[tuple(round(v,9) for v in vertices[i]) for i in face]
        for a,b in zip(points,points[1:]+points[:1]):
            if a==b:continue
            edges.setdefault(tuple(sorted((a,b))),[]).append((number,1 if a<b else -1))
    if any(len(rows)%2 for rows in edges.values()):
        raise ValueError('Open/odd collision boundary cannot be repaired by orientation')
    adjacency=[[] for _ in faces]
    for rows in edges.values():
        if len(rows)==2:
            (a,da),(b,db)=rows
            adjacency[a].append((b,-da*db));adjacency[b].append((a,-da*db))
    signs=[0]*len(faces);components=[];component_of={}
    for seed in range(len(faces)):
        if signs[seed]:continue
        group=[];stack=[seed];signs[seed]=1
        while stack:
            face=stack.pop();group.append(face);component_of[face]=len(components)
            for other,relative in adjacency[face]:
                wanted=signs[face]*relative
                if signs[other] and signs[other]!=wanted:
                    raise ValueError('Collision mesh manifold sheet is not orientable')
                if not signs[other]:signs[other]=wanted;stack.append(other)
        components.append(group)
    preferred=[1 if sum(signs[i]<0 for i in group)<=len(group)/2 else -1 for group in components]
    constraints=[]
    for rows in edges.values():
        if len(rows)<=2:continue
        values=Counter()
        for face,direction in rows:values[component_of[face]]+=signs[face]*direction
        values={key:value for key,value in values.items() if value}
        if values:constraints.append(values)
    variables=sorted({key for row in constraints for key in row},key=lambda key:-sum(abs(row.get(key,0)) for row in constraints))
    chosen={};calls=0
    def search(index):
        nonlocal calls
        calls+=1
        if calls>100_000:raise ValueError('Ambiguous nonmanifold orientation exceeds bounded solver budget')
        for row in constraints:
            total=sum(value*chosen[key] for key,value in row.items() if key in chosen)
            remaining=sum(abs(value) for key,value in row.items() if key not in chosen)
            if abs(total)>remaining:return False
        if index==len(variables):return True
        key=variables[index]
        for value in (preferred[key],-preferred[key]):
            chosen[key]=value
            if search(index+1):return True
        del chosen[key]
        return False
    if not search(0):raise ValueError('Nonmanifold closed sheets have no balanced orientation')
    final=[signs[i]*chosen.get(component_of[i],preferred[component_of[i]]) for i in range(len(faces))]
    if any(sum(final[i]*direction for i,direction in rows) for rows in edges.values()):
        raise ValueError('Orientation repair failed directed edge verification')
    return final,{'manifold_sheets':len(components),'nonmanifold_edges':sum(len(v)>2 for v in edges.values()),
                  'flipped_triangles':sum(s<0 for s in final),'orientation_search_states':calls}


def repair_collision_obj(source, destination):
    """Write a separate collision OBJ: same positions/triangles, new orientation.

    Never changes its source or a visual asset. Native physics and the auditor
    must both consume the returned destination hash, not different face orders.
    """
    source,destination=Path(source),Path(destination)
    if source.resolve()==destination.resolve() or destination.exists():
        raise ValueError('Collision orientation repair requires a fresh separate artifact')
    vertex_lines=[];vertices=[];faces=[]
    for line in source.read_text(encoding='utf-8-sig').splitlines():
        row=line.split()
        if not row:continue
        if row[0]=='v':vertex_lines.append(line);vertices.append(tuple(float(v) for v in row[1:4]))
        elif row[0]=='f':
            if len(row)!=4:raise ValueError('Collision source must be triangulated')
            faces.append(tuple(int(v.split('/')[0])-1 for v in row[1:]))
    signs,report=_consistent_face_signs(vertices,faces)
    oriented=[face if sign>0 else (face[0],face[2],face[1]) for face,sign in zip(faces,signs)]
    normals=[]
    for face in oriented:
        a,b,c=(vertices[i] for i in face);n=_cross(_sub(b,a),_sub(c,a));length=math.sqrt(_dot(n,n))
        if length<1e-18:raise ValueError('Degenerate source triangle cannot receive a collision normal')
        normals.append(tuple(v/length for v in n))
    content='# Collision-only orientation revision; source vertex coordinates and triangle surfaces preserved.\n'
    content+='\n'.join(vertex_lines)+'\n'
    content+=''.join('vn '+' '.join(format(v,'.17g') for v in n)+'\n' for n in normals)
    content+=''.join('f '+' '.join(f'{v+1}//{i+1}' for v in face)+'\n' for i,face in enumerate(oriented))
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(content,encoding='utf-8')
    # The exact same validator used by admission checks the new artifact.
    TriangleMesh(vertices,oriented)
    report.update(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  collision_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
                  vertices_unchanged=True,unoriented_triangles_unchanged=sorted(tuple(sorted(f)) for f in faces)==sorted(tuple(sorted(f)) for f in oriented),
                  vertex_count=len(vertices),triangle_count=len(faces),new_face_normals=len(normals))
    return report


@dataclass(frozen=True)
class _Node:
    bounds: tuple
    left: int | None
    right: int | None
    triangles: tuple


def _build_nodes(triangles):
    nodes=[]
    def build(indices):
        bounds=_bounds([p for i in indices for p in triangles[i]])
        node_id=len(nodes);nodes.append(None)
        if len(indices)<=8:
            nodes[node_id]=_Node(bounds,None,None,tuple(indices))
        else:
            axis=max(range(3),key=lambda i:bounds[1][i]-bounds[0][i])
            indices=sorted(indices,key=lambda n:(sum(p[axis] for p in triangles[n]),n))
            middle=len(indices)//2
            left,right=build(indices[:middle]),build(indices[middle:])
            nodes[node_id]=_Node(bounds,left,right,())
        return node_id
    build(list(range(len(triangles))))
    return tuple(nodes)


def _surfaces_intersect(first,second,nodes_a,nodes_b):
    bounds_a=[_bounds(triangle) for triangle in first]
    bounds_b=[_bounds(triangle) for triangle in second]
    stack=[(0,0)]
    while stack:
        i,j=stack.pop();a,b=nodes_a[i],nodes_b[j]
        if _bounds_gap(a.bounds,b.bounds)>1e-12:continue
        if a.triangles and b.triangles:
            if any(_bounds_gap(bounds_a[x],bounds_b[y])<=1e-12 and
                   triangle_triangle_distance(first[x],second[y])<=1e-12 for x in a.triangles for y in b.triangles):return True
        elif not a.triangles:
            stack.extend(((a.left,j),(a.right,j)))
        else:
            stack.extend(((i,b.left),(i,b.right)))
    return False


class TriangleMesh:
    """Immutable geometry with triangle BVH and closed-component witnesses."""
    def __init__(self, vertices, faces, *, verify_closed=True):
        self.vertices = tuple(tuple(p) for p in vertices)
        self.faces = tuple(tuple(f) for f in faces)
        if not self.vertices or not self.faces or any(len(p)!=3 or not all(math.isfinite(v) for v in p) for p in self.vertices):
            raise ValueError('Empty or nonfinite triangle mesh')
        if any(len(f)!=3 or any(type(i) is not int or not 0<=i<len(self.vertices) for i in f) for f in self.faces):
            raise ValueError('Invalid triangle indices')
        self.triangles = tuple(tuple(self.vertices[i] for i in face) for face in self.faces)
        # Match topology keys on a 1 nm decimal grid for CAD normal-seam
        # duplicates. This never rewrites coordinates: all distances and native
        # physics use the actual admitted OBJ positions, not these edge keys.
        edge_faces = {}; directed = Counter(); parents = list(range(len(self.faces)))
        def root(i):
            while parents[i]!=i:
                parents[i]=parents[parents[i]];i=parents[i]
            return i
        for number, triangle in enumerate(self.triangles):
            if math.sqrt(_dot(_cross(_sub(triangle[1],triangle[0]),_sub(triangle[2],triangle[0])),
                                   _cross(_sub(triangle[1],triangle[0]),_sub(triangle[2],triangle[0])))) < 1e-18:
                raise ValueError('Degenerate collision triangle')
            welded = [tuple(round(v,9) for v in p) for p in triangle]
            for a,b in zip(welded,welded[1:]+welded[:1]):
                if a==b:continue
                edge=tuple(sorted((a,b))); directed[edge]+=1 if a<b else -1
                if edge in edge_faces:
                    parents[root(number)]=root(edge_faces[edge][0])
                edge_faces.setdefault(edge,[]).append(number)
        if verify_closed and (any(len(f)%2 for f in edge_faces.values()) or any(directed.values())):
            raise ValueError('Collision mesh is not closed and consistently oriented at its welded edges')
        self.closed = verify_closed
        # Contact along a nonmanifold edge must not merge independently closed
        # solids before their orientation is checked. Otherwise an outward
        # large body could hide an inside-out smaller body sharing that edge.
        sheet_neighbors=[[] for _ in self.faces]
        for face_ids in edge_faces.values():
            if len(face_ids)==2:
                a,b=face_ids;sheet_neighbors[a].append(b);sheet_neighbors[b].append(a)
        remaining=set(range(len(self.faces))); closed_sheets=[]
        while remaining:
            pending=[remaining.pop()];sheet=[]
            while pending:
                i=pending.pop();sheet.append(i)
                for other in sheet_neighbors[i]:
                    if other in remaining:remaining.remove(other);pending.append(other)
            membership=set(sheet)
            closed=all(sum(i in membership for i in ids)%2==0 for ids in edge_faces.values())
            origin=self.triangles[sheet[0]][0]
            volume=sum(_dot(_sub(a,origin),_cross(_sub(b,origin),_sub(c,origin)))/6
                       for i in sheet for a,b,c in (self.triangles[i],))
            if closed and abs(volume)>=1e-24:closed_sheets.append(sheet)
        assigned={i for sheet in closed_sheets for i in sheet}
        residual={}
        for i in range(len(self.faces)):
            if i not in assigned:residual.setdefault(root(i),[]).append(i)
        components=closed_sheets+list(residual.values())
        self.component_points=tuple(self.triangles[ids[0]][0] for ids in components)
        # A consistently oriented shell can still be wholly inside-out. Admit
        # positive outer shells, and negative cavity shells only when strictly
        # nested, with no surface intersection. Opposite overlapping shells
        # would cancel winding and make both the auditor and backface-culling
        # native contacts unsafe, so they are rejected.
        groups=[tuple(self.triangles[i] for i in ids) for ids in components]
        group_bounds=[_bounds([p for triangle in group for p in triangle]) for group in groups]
        group_nodes={}
        volumes=[]
        for group in groups:
            origin=group[0][0]
            volumes.append(sum(_dot(_sub(a,origin),_cross(_sub(b,origin),_sub(c,origin)))/6 for a,b,c in group))
        if verify_closed:
            if any(abs(volume)<1e-24 for volume in volumes):
                raise ValueError('Collision shell has no unambiguous solid volume')
            for i,group in enumerate(groups):
                # Positive shells represent a union of material, including
                # redundant nested solids. They cannot cancel another solid's
                # winding. Only subtractive cavity shells need a verified
                # surrounding material shell.
                if volumes[i]>0:continue
                containers=[]
                for j,other in enumerate(groups):
                    if i==j:continue
                    lo,hi=group_bounds[i]; outer_lo,outer_hi=group_bounds[j]
                    if not all(outer_lo[k]<lo[k] and hi[k]<outer_hi[k] for k in range(3)):continue
                    witness=tuple(sum(p[k] for p in group[0])/3 for k in range(3))
                    if abs(_winding(other,witness))<.5:continue
                    # Bounds nesting alone is insufficient for concave solids.
                    # Exact pair checks occur only for potential cavity shells.
                    if i not in group_nodes:group_nodes[i]=_build_nodes(group)
                    if j not in group_nodes:group_nodes[j]=_build_nodes(other)
                    if _surfaces_intersect(group,other,group_nodes[i],group_nodes[j]):
                        raise ValueError('Intersecting nested collision shells have ambiguous solid orientation')
                    containers.append(j)
                surrounding_material=sum(1 if volumes[j]>0 else -1 for j in containers)
                if surrounding_material<=0:
                    raise ValueError('Collision shell is inside-out or has ambiguous overlapping orientation')
        self.component_signed_volumes=tuple(volumes)
        # A closed oriented component contributes zero winding outside its
        # own bounds, even when other components overlap or form cavities.
        # Require closure at the actual coordinates for this optimization:
        # the admission-only 1-nm seam keys cannot justify pruning a crack.
        self.containment_components=[]
        for group,bounds in zip(groups,group_bounds):
            balance=Counter()
            for triangle in group:
                for a,b in zip(triangle,triangle[1:]+triangle[:1]):
                    if a!=b:balance[tuple(sorted((a,b)))]+=1 if a<b else -1
            exact_closed=verify_closed and not any(balance.values())
            self.containment_components.append((group,bounds if exact_closed else None))
        self.containment_components=tuple(self.containment_components)
        self.nodes=_build_nodes(self.triangles)
        self.bounds=self.nodes[0].bounds

    def contains(self, point):
        if any(point[i]<self.bounds[0][i]-1e-12 or point[i]>self.bounds[1][i]+1e-12 for i in range(3)):
            return False
        # Generalized oriented winding handles overlapping closed shells where
        # a parity ray would incorrectly classify a double overlap as outside.
        try:
            return sum(_winding(group,point) for group,bounds in self.containment_components
                if bounds is None or all(bounds[0][i]-1e-12<=point[i]<=bounds[1][i]+1e-12
                                         for i in range(3)))>.5
        except ValueError:return True

    def support(self,direction):
        """Exact maximum vertex projection, pruned by conservative node bounds."""
        def upper(bounds):
            return sum(direction[k]*bounds[1 if direction[k]>=0 else 0][k] for k in range(3))
        best=-math.inf;heap=[(-upper(self.bounds),0)]
        while heap:
            negative,index=heapq.heappop(heap)
            if -negative<=best:continue
            node=self.nodes[index]
            if node.triangles:
                best=max(best,*(_dot(direction,p) for i in node.triangles for p in self.triangles[i]))
            else:
                for child in (node.left,node.right):
                    bound=upper(self.nodes[child].bounds)
                    if bound>best:heapq.heappush(heap,(-bound,child))
        return best


class _PosedMesh:
    def __init__(self, mesh, pose):
        self.mesh,self.pose=mesh,pose
        self.inverse=inverse_pose(pose)
        lower,upper=[],[]
        for axis in range(3):
            direction=rotate_vector(self.inverse['quaternion_xyzw'],[int(axis==i) for i in range(3)])
            upper.append(pose['xyz_m'][axis]+mesh.support(direction))
            lower.append(pose['xyz_m'][axis]-mesh.support(tuple(-v for v in direction)))
        self.bounds=tuple(lower),tuple(upper)
        self.vertex_cache={}
        self.node_bounds={0:self.bounds}
        self.triangle_cache={}
        self.triangle_bounds_cache={}

    def bounds_of(self,index):
        if index not in self.node_bounds:
            lo,hi=self.mesh.nodes[index].bounds
            self.node_bounds[index]=_bounds([transform_point(self.pose,p) for p in itertools.product(*zip(lo,hi))])
        return self.node_bounds[index]

    def triangle(self,index):
        if index not in self.triangle_cache:
            for i in self.mesh.faces[index]:
                if i not in self.vertex_cache:self.vertex_cache[i]=tuple(transform_point(self.pose,self.mesh.vertices[i]))
            self.triangle_cache[index]=tuple(self.vertex_cache[i] for i in self.mesh.faces[index])
        return self.triangle_cache[index]

    def triangle_bounds(self,index):
        if index not in self.triangle_bounds_cache:
            self.triangle_bounds_cache[index]=_bounds(self.triangle(index))
        return self.triangle_bounds_cache[index]

    def contains(self,point):return self.mesh.contains(transform_point(self.inverse,point))


def _primitive_mesh(geometry):
    if geometry['type']=='box':
        x,y,z=(v/2 for v in geometry['size_m'])
        vertices=[(-x,-y,-z),(x,-y,-z),(x,y,-z),(-x,y,-z),(-x,-y,z),(x,-y,z),(x,y,z),(-x,y,z)]
        faces=[]
        for quad in ((0,3,2,1),(4,5,6,7),(0,1,5,4),(3,7,6,2),(0,4,7,3),(1,2,6,5)):
            faces.extend((quad[0],quad[i],quad[i+1]) for i in (1,2))
    elif geometry['type']=='cylinder':
        sections=32;radius=geometry['radius_m']/math.cos(math.pi/sections);half=geometry['length_m']/2
        vertices=[(radius*math.cos(2*math.pi*i/sections),radius*math.sin(2*math.pi*i/sections),z)
                  for z in (-half,half) for i in range(sections)]+[(0,0,-half),(0,0,half)]
        faces=[]
        for i in range(sections):
            j=(i+1)%sections
            faces.extend(((i,j,sections+j),(i,sections+j,sections+i),(2*sections,j,i),(2*sections+1,sections+i,sections+j)))
    else:
        raise ValueError('Only box/cylinder primitives have audit polyhedra')
    return TriangleMesh(vertices,faces)


class MeshRepository:
    """Explicit root, immutable verified assets, bounded posed-BVH cache."""
    def __init__(self, asset_root, geometries):
        if asset_root is None:raise ValueError('Collision meshes require an explicit asset root')
        self.asset_root=Path(asset_root).resolve(strict=True)
        if not self.asset_root.is_dir():raise ValueError('Mesh asset root must be a directory')
        self.meshes={};self.primitives={};self.posed=OrderedDict();self.asset_hashes={}
        for geometry in geometries:
            if 'geometry' in geometry:geometry=geometry['geometry']
            if geometry.get('type')=='mesh':self._load(geometry)

    def _load(self,geometry):
        uri,digest=geometry.get('uri'),geometry.get('sha256')
        if not isinstance(uri,str) or '\\' in uri or ':' in uri or PurePosixPath(uri).is_absolute() or '..' in PurePosixPath(uri).parts:
            raise ValueError('Mesh URI must stay portable and relative to its asset root')
        if geometry.get('scale',[1,1,1])!=[1,1,1] and tuple(geometry.get('scale',()))!=(1,1,1):
            raise ValueError('Collision meshes must already be in SI without implicit scaling')
        key=(uri,digest)
        if key in self.meshes:return self.meshes[key]
        path=(self.asset_root/uri).resolve(strict=True)
        if not path.is_relative_to(self.asset_root) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('Collision mesh asset path/hash differs from admitted bytes')
        vertices,faces,_,_=read_collision_obj(path)
        self.meshes[key]=TriangleMesh(vertices,faces)
        self.asset_hashes[uri]=digest
        return self.meshes[key]

    def prepare(self,shape):
        geometry,pose=shape['geometry'],shape['pose']
        values=tuple(pose['xyz_m'])+tuple(pose['quaternion_xyzw'])
        if len(values)!=7 or not all(math.isfinite(v) for v in values) or abs(sum(v*v for v in values[3:])-1)>1e-6:
            raise ValueError('Collision pose requires finite position and unit quaternion')
        if geometry['type']=='mesh':
            mesh=self._load(geometry);identity=('mesh',geometry['uri'],geometry['sha256'])
        else:
            identity=(geometry['type'],tuple(geometry.get('size_m',())),geometry.get('radius_m'),geometry.get('length_m'))
            if identity not in self.primitives:self.primitives[identity]=_primitive_mesh(geometry)
            mesh=self.primitives[identity]
        key=(identity,values)
        if key not in self.posed:
            self.posed[key]=_PosedMesh(mesh,pose)
            if len(self.posed)>128:self.posed.popitem(last=False)
        self.posed.move_to_end(key)
        return self.posed[key]

    def world_bounds(self,shape):
        if shape['geometry']['type']=='sphere':
            center=shape['pose']['xyz_m'];radius=shape['geometry']['radius_m']
            return tuple(v-radius for v in center),tuple(v+radius for v in center)
        return self.prepare(shape).bounds

    def conservative_world_bounds(self,shape):
        """Cheap enclosing bounds for pruning; never a reported exact mesh gap."""
        if shape['geometry']['type']!='mesh':return self.world_bounds(shape)
        mesh=self._load(shape['geometry']);lo,hi=mesh.bounds
        return _bounds([transform_point(shape['pose'],p) for p in itertools.product(*zip(lo,hi))])

    def surface_distance(self,shape,point,limit=math.inf):
        if shape['geometry']['type']=='sphere':
            return min(limit,abs(math.dist(point,shape['pose']['xyz_m'])-shape['geometry']['radius_m']))
        mesh=self.prepare(shape);best=limit
        heap=[(_bounds_gap(mesh.bounds,(point,point)),0)]
        while heap:
            lower,index=heapq.heappop(heap)
            if lower>=best:continue
            node=mesh.mesh.nodes[index]
            if node.triangles:
                best=min(best,*(point_triangle_distance(point,*mesh.triangle(i)) for i in node.triangles))
            else:
                for child in (node.left,node.right):
                    lower=_bounds_gap(mesh.bounds_of(child),(point,point))
                    if lower<best:heapq.heappush(heap,(lower,child))
        return best

    def point_distance(self,shape,point,limit=math.inf):
        if shape['geometry']['type']=='sphere':
            return min(limit,max(0.,math.dist(point,shape['pose']['xyz_m'])-shape['geometry']['radius_m']))
        mesh=self.prepare(shape)
        if mesh.contains(point):return 0.
        return self.surface_distance(shape,point,limit)

    def segment_distance(self,shape,start,end,limit=math.inf):
        if shape['geometry']['type']=='sphere':
            return min(limit,max(0.,point_segment_distance(shape['pose']['xyz_m'],start,end)-shape['geometry']['radius_m']))
        mesh=self.prepare(shape)
        if mesh.contains(start) or mesh.contains(end):return 0.
        bounds=_bounds((start,end));best=limit;heap=[(_bounds_gap(mesh.bounds,bounds),0)]
        while heap:
            lower,index=heapq.heappop(heap)
            if lower>=best:continue
            node=mesh.mesh.nodes[index]
            if node.triangles:
                best=min(best,*(segment_triangle_distance(start,end,*mesh.triangle(i)) for i in node.triangles))
                if best==0:return 0.
            else:
                for child in (node.left,node.right):
                    lower=_bounds_gap(mesh.bounds_of(child),bounds)
                    if lower<best:heapq.heappush(heap,(lower,child))
        return best

    def shape_distance(self,first,second,limit=math.inf):
        if first['geometry']['type']=='sphere':
            radius=first['geometry']['radius_m']
            return max(0.,self.point_distance(second,first['pose']['xyz_m'],limit+radius)-radius)
        if second['geometry']['type']=='sphere':return self.shape_distance(second,first,limit)
        a,b=self.prepare(first),self.prepare(second)
        best=limit;heap=[(_bounds_gap(a.bounds,b.bounds),0,0)]
        while heap:
            lower,i,j=heapq.heappop(heap)
            if lower>=best:continue
            na,nb=a.mesh.nodes[i],b.mesh.nodes[j]
            if na.triangles and nb.triangles:
                for ta in na.triangles:
                    for tb in nb.triangles:
                        if _bounds_gap(a.triangle_bounds(ta),b.triangle_bounds(tb))>=best:continue
                        best=min(best,triangle_triangle_distance(a.triangle(ta),b.triangle(tb)))
                        if best<=1e-12:return 0.
            else:
                children=((na.left,j),(na.right,j)) if not na.triangles and (nb.triangles or
                    sum((x-y)**2 for x,y in zip(*na.bounds))>=sum((x-y)**2 for x,y in zip(*nb.bounds))) else ((i,nb.left),(i,nb.right))
                for ci,cj in children:
                    lower=_bounds_gap(a.bounds_of(ci),b.bounds_of(cj))
                    if lower<best:heapq.heappush(heap,(lower,ci,cj))
        if _bounds_gap(a.bounds,b.bounds)==0:
            if any(b.contains(transform_point(a.pose,p)) for p in a.mesh.component_points):return 0.
            if any(a.contains(transform_point(b.pose,p)) for p in b.mesh.component_points):return 0.
        return best
