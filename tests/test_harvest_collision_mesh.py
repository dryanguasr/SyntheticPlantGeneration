"""Conservative containment and fail-closed auditing of static prism batches."""
from collections import Counter
from copy import deepcopy
import json
import math
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from uchuva_gazebo.harvest_collision_mesh import (
    HEADER, PRIMITIVE, build_collision_prisms, identity_digest,
    prism_geometry, radius_factor, read_collision_prisms,
)
from uchuva_gazebo.harvest_clearance import rigid_cylinders
from uchuva_gazebo.harvest_plants import build_harvest_plants


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def sub(a, b):
    return [x-y for x, y in zip(a, b)]


class CollisionPrismTests(unittest.TestCase):
    def setUp(self):
        self.rows = [dict(id="rigid_1", source_proxy_id="plant_000:stem_1",
                          start=[.25, -.3, .2], end=[.9, .12, 1.3], radius=.013),
                     dict(id="rigid_2", source_proxy_id="plant_000:pedicel_2",
                          start=[.9, .12, 1.3], end=[.91, .14, 1.32], radius=.0018)]

    def test_closed_outward_prisms_contain_the_complete_finite_cylinder(self):
        for start, end in (([0,0,0], [0,0,1]), ([.2,-.3,.4], [.9,.6,-.1]), ([1,0,0], [-1,0,0])):
            radius = .017
            vertices, faces = prism_geometry(start, end, radius)
            edges = Counter((min(a,b), max(a,b)) for face in faces for a,b in zip(face, face[1:]+face[:1]))
            directed = Counter((a,b) for face in faces for a,b in zip(face, face[1:]+face[:1]))
            self.assertTrue(all(count == 2 for count in edges.values()))
            self.assertTrue(all(directed[(b,a)] == count for (a,b),count in directed.items()))
            direction = sub(end,start); length=math.hypot(*direction)
            axis=[value/length for value in direction]
            u=[value/(radius*radius_factor()) for value in sub(vertices[0],start)]
            v=cross(axis,u)
            # Analytical support function of a finite cylinder against every
            # outward triangle plane: max(n.p) <= plane offset proves inclusion
            # for its entire continuous volume, not only sampled ring points.
            for face in faces:
                a,b,c=[vertices[i] for i in face]
                normal=cross(sub(b,a),sub(c,a));norm=math.hypot(*normal)
                normal=[value/norm for value in normal]
                axial=sum(x*y for x,y in zip(normal,axis))
                radial=math.hypot(*cross(normal,axis))
                support=max(sum(x*y for x,y in zip(normal,start)),sum(x*y for x,y in zip(normal,end)))+radius*radial
                plane=sum(x*y for x,y in zip(normal,a))
                self.assertLessEqual(support,plane+1e-10)
            # Every prism vertex is inside the outer finite cylinder; convexity
            # extends this containment to all triangles and prism volume.
            for point in vertices:
                delta=sub(point,start);z=sum(x*y for x,y in zip(delta,axis))
                radial=math.hypot(*[delta[i]-z*axis[i] for i in range(3)])
                self.assertGreaterEqual(z,-1e-12);self.assertLessEqual(z,length+1e-12)
                self.assertLessEqual(radial,radius*radius_factor()+1e-12)
            self.assertAlmostEqual(radius_factor()-1,.035276180410083,places=14)

    def test_canonical_geometry_and_identity_roundtrip(self):
        text=build_collision_prisms(self.rows)
        vertices=[list(map(float,line.split()[1:])) for line in text.splitlines() if line.startswith("v ")]
        normals=[list(map(float,line.split()[1:])) for line in text.splitlines() if line.startswith("vn ")]
        self.assertEqual(len(normals),len(vertices))
        for normal in normals:self.assertAlmostEqual(math.hypot(*normal),1.0,places=13)
        for line in text.splitlines():
            if not line.startswith("f "):continue
            references=[tuple(map(int,token.split("//"))) for token in line.split()[1:]]
            for vertex,normal in references:
                self.assertEqual(vertex,normal)
                self.assertTrue(1<=normal<=len(normals))
            a,b,c=[vertices[vertex-1] for vertex,_ in references]
            face_normal=cross(sub(b,a),sub(c,a))
            for _,normal in references:
                self.assertGreater(sum(x*y for x,y in zip(face_normal,normals[normal-1])),0)
        recovered=read_collision_prisms(text)
        self.assertEqual(identity_digest(recovered),identity_digest(self.rows))
        for actual, source in zip(recovered,self.rows):
            for key in ("id","source_proxy_id","start","end"):
                self.assertEqual(actual[key],source[key])
            self.assertEqual(actual["source_radius"],source["radius"])
            self.assertAlmostEqual(actual["radius"],source["radius"]*radius_factor())

    def test_tampered_geometry_metadata_and_degenerate_inputs_fail_closed(self):
        text=build_collision_prisms(self.rows)
        lines=text.splitlines()
        vertex=next(index for index,line in enumerate(lines) if line.startswith("v "))
        changed=lines.copy();changed[vertex]="v 100 100 100"
        for invalid in ("\n".join(changed)+"\n", "\n".join(lines[:-1])+"\n", text+"f 1 2 3\n", text.replace('"primitive_count":2','"primitive_count":1'), HEADER+'[]\n'):
            with self.assertRaises(ValueError):read_collision_prisms(invalid)
        for field,value in (("radius",0),("radius",float("nan")),("end",self.rows[0]["start"]),("start",[float("inf"),0,0])):
            row=deepcopy(self.rows[0]);row[field]=value
            with self.assertRaises(ValueError):build_collision_prisms([row])
        with self.assertRaises(ValueError):build_collision_prisms([self.rows[0],self.rows[0]])

    def test_sdf_mesh_audit_requires_sources_and_identity_pose(self):
        uri="meshes/collision.obj";text=build_collision_prisms(self.rows)
        model=ET.fromstring('<model name="plant_000"><static>true</static><pose>2 3 0 0 0 0</pose><link name="plant_link"><collision name="batch"><pose>0 0 0 0 0 0</pose><geometry><mesh><uri>meshes/collision.obj</uri><scale>1 1 1</scale></mesh></geometry></collision></link></model>')
        report=dict(model_name="plant_000",rigid_primitive_count=2,rigid_primitive_identity_sha256=identity_digest(self.rows))
        bundle=dict(models=[model],meshes={uri:text},plants=[report])
        cylinders=rigid_cylinders(bundle)
        self.assertEqual(cylinders[0]["id"],"plant_000/rigid_1")
        self.assertEqual(cylinders[0]["start"],[2.25,2.7,.2])
        self.assertAlmostEqual(cylinders[0]["radius"],.013*radius_factor())
        with self.assertRaisesRegex(ValueError,"OBJ text"):
            rigid_cylinders(dict(models=[model]))
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            path=Path(directory)/uri;path.parent.mkdir();path.write_text(text,encoding="utf-8")
            self.assertEqual(rigid_cylinders(dict(models=[model],plants=[report]),mesh_root=directory),cylinders)
        invalid=deepcopy(bundle);invalid["plants"][0]["rigid_primitive_count"]=1
        with self.assertRaisesRegex(ValueError,"identities"):rigid_cylinders(invalid)
        for query,value in (("link/collision/pose","0 0 0 0 0 1"),("link/collision/geometry/mesh/scale","2 1 1"),("link/collision/geometry/mesh/uri","../outside.obj")):
            invalid=deepcopy(bundle);invalid["models"][0].find(query).text=value
            with self.assertRaises(ValueError):rigid_cylinders(invalid)

    def test_opt_in_batches_every_original_primitive_without_changing_organs(self):
        analytic=build_harvest_plants({})
        batched=build_harvest_plants({"collision_representation":"batched_conservative_prisms"})
        original=rigid_cylinders(analytic);outer=rigid_cylinders(batched)
        self.assertEqual(len(original),713);self.assertEqual(len(outer),713)
        self.assertEqual(sum(p["rigid_collision_count"] for p in batched["plants"]),3)
        self.assertEqual(sum(p["rigid_primitive_count"] for p in batched["plants"]),713)
        self.assertEqual([p["source_morphology"] for p in analytic["plants"]],[p["source_morphology"] for p in batched["plants"]])
        self.assertEqual([p["id"] for p in analytic["fruits"]],[p["id"] for p in batched["fruits"]])
        for old,new in zip(original,outer):
            self.assertEqual(old["id"],new["id"])
            for key in ("start","end"):
                # Historical SDF poses use fewer decimals than the source
                # endpoints now stored directly in the prism metadata.
                self.assertLess(math.dist(old[key],new[key]),1e-8)
            self.assertAlmostEqual(new["radius"],old["radius"]*radius_factor(),places=12)


if __name__=="__main__":unittest.main()
