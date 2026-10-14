"""Blender adapter: morphology JSON -> evaluated meshes in metres -> Gazebo SDF.

Run with Blender --background --python scripts/export_gazebo_field.py -- ...
No existing .blend, context plants, or generic plant prototypes are consumed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import shutil
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import bpy
from mathutils import Vector
from uchuva_gazebo.field import VERSION, write_world, prepare_mesh_assets
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.scene import CultivationScene
from uchuva_lsystem.sparse_pilot import UNITS_PER_METRE as U, CALYX_COLORS, FRUIT_COLORS, walk_axes
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology, create_cultivation_supports
from uchuva_lsystem.blender_scene import cleanup_scene, create_project_materials, create_material
from uchuva_lsystem.collisions import build_scene_proxies


def export_objects(objects, output, prefix, individual_calyces=False, textures=False):
    """Stream OBJ meshes grouped by material; preserve source object identity in sidecar."""
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    streams, entries, offsets, identities, uv_offsets = {}, {}, {}, [], {}
    try:
        for obj in objects:
            if obj.hide_render or obj.type not in {"MESH", "CURVE"}:
                continue
            evaluated = obj.evaluated_get(deps)
            mesh = evaluated.to_mesh()
            try:
                mesh.calc_loop_triangles()
                by_material = {}
                for tri in mesh.loop_triangles:
                    by_material.setdefault(tri.material_index, []).append(tri)
                ids = []
                for slot, triangles in by_material.items():
                    mat = mesh.materials[slot] if slot < len(mesh.materials) else None
                    key = mat.name if mat else "default"
                    if individual_calyces and obj.get("uchuva_semantic_class") == "calyx":
                        key = obj.name
                    if key not in streams:
                        name = f"{prefix}_{len(streams):02d}.obj"
                        streams[key] = (output / "meshes" / name).open("w", encoding="utf-8")
                        offsets[key] = 1
                        uv_offsets[key] = 1
                        color = tuple(mat.diffuse_color) if mat else (.15,.3,.05,1)
                        entries[key] = {"uri": f"meshes/{name}", "color": color, "triangles": 0}
                        if textures and mat:
                            preset = mat.get('uchuva_texture_preset')
                            if mat.name.startswith('calyx_ntc_'):
                                grade = int(mat.name.split('_')[-1])
                                preset = ('calyx_green_v0','calyx_green_v1','calyx_transition_v0','calyx_transition_v1','calyx_straw_v0','calyx_straw_v1','calyx_dry_v0')[grade]
                            if preset: entries[key]['texture_preset'] = preset
                    stream = streams[key]
                    start = offsets[key]
                    used = sorted({v for tri in triangles for v in tri.vertices})
                    mapping = {v:start+i for i,v in enumerate(used)}
                    stream.write(f"o {obj.name.replace(' ', '_')}\n")
                    for vertex_id in used:
                        point = (evaluated.matrix_world @ mesh.vertices[vertex_id].co) / U
                        stream.write("v " + " ".join(f"{v:.8f}" for v in point) + "\n")
                    for tri in triangles:
                        uv = mesh.uv_layers.active if textures else None
                        if uv:
                            start_uv = uv_offsets[key]
                            for loop in tri.loops:
                                stream.write('vt '+' '.join(str(v) for v in uv.data[loop].uv)+'\n')
                            stream.write('f '+' '.join(f'{mapping[v]}/{start_uv+i}' for i,v in enumerate(tri.vertices))+'\n')
                            uv_offsets[key] += 3
                        else:
                            stream.write("f " + " ".join(str(mapping[v]) for v in tri.vertices) + "\n")
                    offsets[key] += len(used)
                    entries[key]["triangles"] += len(triangles)
                    ids.append(entries[key]["uri"])
                identities.append({"object": obj.name, "meshes": ids,
                    "plant_id": obj.get("uchuva_plant_id"),
                    "organ_id": obj.get("uchuva_organ_id"),
                    "reproductive_id": obj.get("uchuva_reproductive_instance_id"),
                    "semantic_class": obj.get("uchuva_semantic_class"),
                    "center_world_m": [sum((obj.matrix_world @ Vector(v))[i] for v in obj.bound_box)/8/U for i in range(3)]})
            finally:
                evaluated.to_mesh_clear()
    finally:
        for stream in streams.values():
            stream.close()
    return list(entries.values()), identities


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--markers", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--individual-calyces", action="store_true")
    parser.add_argument('--textures', action='store_true')
    parser.add_argument('--normal-maps', action='store_true', help='Opt-in tangent-space normals; historical export stays unchanged')
    parser.add_argument('--visual-lod', action='store_true', help='Visual-only mesh decimation; organs and morphology remain intact')
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    if args.normal_maps and not args.textures:
        parser.error('--normal-maps requires --textures')
    started = time.perf_counter()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    scene = CultivationScene.from_dict(payload["scene"])
    if scene.metadata.get("units_per_metre") != U:
        raise ValueError("Source units must explicitly be eight units per metre")
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "meshes").mkdir()
    cleanup_scene()
    materials = create_project_materials(seed=scene.seed)
    materials["stake_tie"] = create_material("sparse_light_strings", (.7,.72,.65,1))
    for grade, color in enumerate(CALYX_COLORS):
        materials[f"calyx_ntc_{grade}"] = create_material(f"calyx_ntc_{grade}", color)
        materials[f"fruit_ntc_{grade}"] = create_material(f"fruit_ntc_{grade}", FRUIT_COLORS[grade])
    meshes, identities, reports, plants = [], [], [], {}
    for index, instance in enumerate(scene.plant_instances):
        plant = Plant.from_dict(payload["plants"][instance.plant_id])
        plants[instance.plant_id] = plant
        before = set(bpy.data.objects)
        report = build_geometry_from_morphology(plant, materials, instance_id=instance.plant_id,
            position=instance.position, rotation_deg=instance.rotation_deg, plant_scale=instance.scale,
            add_ground=False, defer_scene_update=True)
        reports.append({"plant_id": instance.plant_id, **report})
        objects = sorted(set(bpy.data.objects)-before, key=lambda o:o.name)
        grades = {f"{instance.plant_id}:{n.reproductive_unit.id}": n.reproductive_unit.synthetic_reference_grade
                  for a in walk_axes(plant.axes) for n in a.nodes if n.reproductive_unit}
        for obj in objects:
            grade = grades.get(obj.get("uchuva_reproductive_instance_id"))
            if obj.get("uchuva_semantic_class") == "fruit" and grade is not None:
                obj.data.materials.clear()
                obj.data.materials.append(materials[f"fruit_ntc_{grade}"])
        if args.visual_lod:
            for obj in objects:
                if obj.type=='CURVE':
                    obj.data.resolution_u=1
                    obj.data.bevel_resolution=0
                elif obj.type=='MESH' and len(obj.data.polygons)>96:
                    modifier=obj.modifiers.new('inspection_visual_lod','DECIMATE')
                    modifier.ratio=max(.15,48/len(obj.data.polygons))
                    modifier.use_collapse_triangulate=True
        batch, mapping = export_objects(objects, args.output, instance.plant_id, args.individual_calyces, args.textures)
        meshes.extend(batch)
        identities.extend(mapping)
        for obj in objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        # Release evaluated source data without purging reusable materials.
        for datablocks in (bpy.data.meshes, bpy.data.curves):
            for block in list(datablocks):
                if block.users == 0:
                    datablocks.remove(block)
        print(f"Exported {index+1}/{len(scene.plant_instances)}", flush=True)
    before = set(bpy.data.objects)
    create_cultivation_supports(scene, materials, reports)
    batch, mapping = export_objects(sorted(set(bpy.data.objects)-before, key=lambda o:o.name), args.output, "supports")
    meshes.extend(batch)
    identities.extend(mapping)
    # Navigation LOD: primary axes and trellis cables; leaves/calyxes visual only.
    primary_axes = {(key,a.id) for key,p in plants.items() for a in p.axes}
    colliders = []
    for proxy in build_scene_proxies(scene, plants):
        if proxy.start is None or proxy.end is None:
            continue
        if proxy.kind in {"support_line", "support_tie"} or (
                proxy.kind == "stem" and (proxy.plant_id,proxy.axis_id) in primary_axes):
            colliders.append({"source_id":proxy.proxy_id, "start_m":[v/U for v in proxy.start],
                              "end_m":[v/U for v in proxy.end], "radius_m":proxy.radius/U})
    for post in scene.support_system.posts:
        colliders.append({"source_id":post.id, "start_m":[v/U for v in post.position],
                          "end_m":[post.position[0]/U,post.position[1]/U,(post.position[2]+post.height)/U],
                          "radius_m":max(post.section_width,post.section_depth)/U/2})
    patterns = {str(spec["id"]):json.loads((args.markers / f"{spec['id']}.json").read_text()) for spec in payload["markers"]}
    prepare_mesh_assets(args.output / "meshes", meshes, individual_material_files=args.individual_calyces)
    write_world(args.output / "field.sdf", meshes, payload["markers"], patterns, colliders)
    if args.textures:
        source=ROOT/'assets/textures/current'
        texture_manifest=json.loads((source/'manifest.json').read_text())
        (args.output/'textures').mkdir()
        tree=ET.parse(args.output/'field.sdf')
        lookup={m['uri']:m for m in meshes}
        for visual in tree.findall('.//visual'):
            entry=lookup.get(visual.findtext('geometry/mesh/uri'),{})
            preset=entry.get('texture_preset')
            if not preset:continue
            files=texture_manifest['texture_sets'][preset]['files']
            mat=visual.find('material')
            mat.find('diffuse').text='1 1 1 1'
            mat.find('ambient').text='1 1 1 1'
            metal=ET.SubElement(ET.SubElement(mat,'pbr'),'metal')
            ET.SubElement(metal,'metalness').text='0'
            ET.SubElement(metal,'roughness').text='.95'
            for kind in (('albedo','roughness','normal') if args.normal_maps else ('albedo','roughness')):
                filename=files[kind]
                shutil.copy2(source/filename,args.output/'textures'/filename)
                element=ET.SubElement(metal,kind+'_map')
                element.text='textures/'+filename
                if kind=='normal':element.set('type','tangent')
        ET.indent(tree);tree.write(args.output/'field.sdf',encoding='utf-8',xml_declaration=True)
    if args.individual_calyces:
        tree=ET.parse(args.output/'field.sdf');world=tree.getroot().find('world')
        link=world.find("model[@name='field']/link")
        calyces=[o for o in identities if o['semantic_class']=='calyx']
        lookup={uri:o for o in calyces for uri in o['meshes']}
        for visual in list(link.findall('visual')):
            uri=visual.findtext('geometry/mesh/uri')
            if uri not in lookup: continue
            organ=lookup[uri];name='calyx_'+str(calyces.index(organ)).zfill(5)
            model=ET.SubElement(world,'model',name=name);ET.SubElement(model,'static').text='true'
            child=ET.SubElement(model,'link',name='link');link.remove(visual);child.append(visual)
            plugin=ET.SubElement(model,'plugin',filename='gz-sim-label-system',name='gz::sim::systems::Label')
            ET.SubElement(plugin,'label').text='1';organ['model_name']=name
        ET.indent(tree);tree.write(args.output/'field.sdf',encoding='utf-8',xml_declaration=True)
        (args.output/'inventory.json').write_text(json.dumps({'seed':scene.seed,'script_version':VERSION,
            'parameter_preset':payload['preset'],'calyces':calyces},indent=2))
    manifest = {"script_version": VERSION, "seed":scene.seed, "parameter_preset":scene.preset_name,
        "source_sha256":hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "source_input":str(args.input.resolve()), "units":"metres", "source_units_per_metre":U,
        "crown_preset":payload['preset'], "export_seconds":time.perf_counter()-started,
        "individual_calyces":args.individual_calyces,
        "texture_maps_exported":args.textures, "inspection_visual_lod":args.visual_lod,
        "exporter_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "parameter_status":"manual_initial_guess", "physics_status":"engineering_heuristic",
        "plant_count":len(plants), "markers":payload["markers"], "meshes":meshes,
        "colliders":colliders, "organs":identities, "context_seedlings":False,
        "agronomic_maturity":None, "human_validation":"pending",
        "limitations":["Static crop; no wind, detachment or measured contact mechanics",
            "Only primary stems and supports collide; canopy is visual-only",
            "UV albedo and roughness maps exported; full Blender shader not reproduced" if args.textures else "Flat material colors; procedural Blender shaders are not exported",
            "Camera rigs are not a drone flight controller or harvester",
            "Source morphology warnings remain unresolved; no new collision validation"]}
    (args.output / "manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({"world":str(args.output / "field.sdf"), "triangles":sum(m["triangles"] for m in meshes)}),flush=True)


if __name__ == "__main__":
    main()
