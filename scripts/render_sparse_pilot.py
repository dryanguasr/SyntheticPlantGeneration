"""Blender entrypoint: render one complete 36-plant scene and its twelve paired-side captures."""
import argparse
import json
import math
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import bpy
from mathutils import Matrix, Vector
from bpy_extras.object_utils import world_to_camera_view
from uchuva_lsystem.sparse_pilot import (UNITS_PER_METRE as U, VERSION, CALYX_COLORS,
                                        FRUIT_COLORS, walk_axes)
from uchuva_lsystem.scene import CultivationScene
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.blender_scene import cleanup_scene, create_project_materials, create_material, setup_render_settings
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology, create_cultivation_supports, audit_scene_mesh_collisions
from uchuva_lsystem.blender_annotations import render_crisp_calyx_annotations, _set_render_engine


def write(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def matrix_list(matrix):
    return [list(row) for row in matrix]


def mesh(name, vertices, faces, material):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(material)
    obj.color = (0, 0, 0, 1)
    return obj


def plate(spec, cells, white, black):
    center = Vector(spec["center_world_m"])*U
    normal = Vector(spec["normal_world"])
    up = Vector((0, 0, 1))
    right = up.cross(normal)
    half = spec["side_m"]*U/2
    def point(x, y, offset=0):
        return center + right*x + up*y + normal*offset
    margin = .02*U
    border = half+margin
    # Coplanar disjoint cells and border: no overlapping black plane / white board.
    white_vertices, white_faces, vertices, faces = [], [], [], []
    def quad(target_vertices, target_faces, x0, y0, x1, y1):
        n = len(target_vertices)
        target_vertices.extend([point(x0,y0),point(x1,y0),point(x1,y1),point(x0,y1)])
        target_faces.append((n,n+1,n+2,n+3))
    for rectangle in ((-border,-border,border,-half),(-border,half,border,border),
                      (-border,-half,-half,half),(half,-half,border,half)):
        quad(white_vertices,white_faces,*rectangle)
    for row in range(6):
        for col in range(6):
            x, y = -half+col*2*half/6, half-row*2*half/6
            quad(vertices if cells[row][col] else white_vertices,
                 faces if cells[row][col] else white_faces,x,y-2*half/6,x+2*half/6,y)
    mesh(f"aruco_{spec['id']}_plate", white_vertices, white_faces, white)
    mesh(f"aruco_{spec['id']}_cells", vertices, faces, black)
    # Physical opaque backing: the print is visible only from the outward face.
    # Keep the printed surface exactly on the exported marker coordinate plane.
    thickness = spec["backing_thickness_m"]*U
    backing_vertices = [point(x,y,offset) for offset in (0,-thickness)
                        for x,y in ((-border,-border),(border,-border),(border,border),(-border,border))]
    mesh(f"aruco_{spec['id']}_opaque_backing",backing_vertices,
         [(7,6,5,4),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)],white)
    # Marker frame: x right, y up, z outward, metres. Corner order matches OpenCV.
    transform = Matrix(((*right, 0), (*up, 0), (*normal, 0), (0, 0, 0, 1))).transposed()
    transform.translation = center/U
    spec["T_world_marker_m"] = matrix_list(transform)
    spec["corners_world_m"] = [list(point(x, y)/U) for x, y in
                                ((-half, half), (half, half), (half, -half), (-half, -half))]
    return spec


def environment(seed, instances):
    rng = random.Random(seed)
    soil = create_material("sparse_soil", (.085, .05, .023, 1))
    nodes = soil.node_tree.nodes
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 20
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = .35
    bump.inputs["Distance"].default_value = .08
    soil.node_tree.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    soil.node_tree.links.new(bump.outputs["Normal"], nodes.get("Principled BSDF").inputs["Normal"])
    mesh("ground", [(-250,-250,0), (250,-250,0), (250,250,0), (-250,250,0)], [(0,1,2,3)], soil)
    leaf = create_material("potato_context_leaf", (.075, .15, .024, 1))
    stem = create_material("potato_context_stem", (.13, .18, .04, 1))
    # Compound-leaf silhouettes, deliberately a context proxy, not a potato growth model.
    for instance in instances:
        for k in range(6):
            base = Vector(instance.position) + Vector((rng.uniform(-.4,.4)*U, rng.choice((-1,1))*.38*U, .005*U))
            top = base + Vector((rng.uniform(-.06,.06)*U, rng.uniform(-.06,.06)*U, rng.uniform(.10,.20)*U))
            from uchuva_lsystem.blender_geometry import _create_sagging_curve_between
            _create_sagging_curve_between(f"potato_stem_{instance.plant_id}_{k}", base, top,
                                         .002*U, stem, sag_factor=0)
            for j in range(3):
                center = base.lerp(top, .3+j*.3)
                for sign in (-1, 1):
                    a = rng.uniform(-.4,.4)
                    end = center + Vector((sign*.07*U, a*.06*U, .012*U))
                    mid = center.lerp(end,.55)
                    mesh("potato_leaf", [center, mid+Vector((0,.025*U,.008*U)), end,
                         mid+Vector((0,-.025*U,.008*U))], [(0,1,2,3)], leaf)
    world = bpy.data.worlds.new("sparse_sky")
    world.use_nodes = True
    world.node_tree.nodes.get("Background").inputs["Color"].default_value = (.55,.68,.85,1)
    world.node_tree.nodes.get("Background").inputs["Strength"].default_value = .6
    bpy.context.scene.world = world
    light = bpy.data.lights.new("sun", "SUN")
    light.energy = 2.0
    light.angle = math.radians(12)
    obj = bpy.data.objects.new("sun", light)
    bpy.context.scene.collection.objects.link(obj)
    obj.rotation_euler = (.5, -.4, -.5)


def camera_metadata(camera, markers, centers, width, height):
    scene = bpy.context.scene
    fx = camera.data.lens/camera.data.sensor_width*width
    # Horizontal sensor fit, square pixels, no shift, no lens distortion.
    K = [[fx, 0, width/2], [0, fx, height/2], [0,0,1]]
    pose = camera.matrix_world.copy()
    pose.translation /= U
    world_to_cv = Matrix.Diagonal((1,-1,-1,1)) @ pose.inverted()
    observations = []
    for spec in markers:
        corners = [world_to_camera_view(scene, camera, Vector(p)*U) for p in spec["corners_world_m"]]
        transform = Matrix(spec["T_world_marker_m"])
        normal = Vector(spec["normal_world"])
        facing = normal.dot(pose.translation - Vector(spec["center_world_m"])) > 0
        observations.append({**spec, "T_camera_marker_m": matrix_list(world_to_cv @ transform),
             "corners_px": [[p.x*width, (1-p.y)*height] for p in corners],
             "front_facing": facing,
             "in_frame": all(p.z > 0 and 0 <= p.x <= 1 and 0 <= p.y <= 1 for p in corners),
             "visibility": "occlusion_not_assumed_from_projection"})
    capachos = []
    for identifier, record in centers.items():
        point = Vector(record["center_world_m"])
        own = [m for m in markers if m["plant_id"] == record["plant_id"]]
        capachos.append({"instance_id": identifier, **record,
            "center_camera_m": list(world_to_cv @ point),
            "centers_marker_m": {str(m["id"]): list(Matrix(m["T_world_marker_m"]).inverted() @ point) for m in own}})
    return {"K": K, "distortion": [0]*5, "T_world_camera_blender_m": matrix_list(pose),
            "T_camera_world_opencv_m": matrix_list(world_to_cv),
            "axes": "world Z up; OpenCV camera X right Y down Z forward; marker X right Y up Z outward",
            "markers": observations, "capachos": capachos}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-dir", type=Path, required=True)
    parser.add_argument("--build-only",action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    folder = args.scene_dir.resolve()
    if (folder / "render_complete.json").exists() or (folder / "cultivation.blend").exists():
        raise FileExistsError("Preserve existing scene; use a new output folder")
    payload = json.loads((folder / "input.json").read_text(encoding="utf-8"))
    scene_data = CultivationScene.from_dict(payload["scene"])
    started = time.perf_counter()
    cleanup_scene()
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1/U
    scene["uchuva_preserve_mask_components"] = True
    materials = create_project_materials(seed=scene_data.seed)
    materials["stake_tie"] = create_material("sparse_light_strings", (.70,.72,.65,1))
    for grade, color in enumerate(CALYX_COLORS):
        materials[f"calyx_ntc_{grade}"] = create_material(f"calyx_ntc_{grade}", color)
        materials[f"fruit_ntc_{grade}"] = create_material(f"fruit_ntc_{grade}", FRUIT_COLORS[grade])
    grades, geometry = {}, []
    for index, instance in enumerate(scene_data.plant_instances):
        plant = Plant.from_dict(payload["plants"][instance.plant_id])
        for axis in walk_axes(plant.axes):
            for node in axis.nodes:
                unit = node.reproductive_unit
                if unit and unit.synthetic_reference_grade is not None:
                    grades[f"{instance.plant_id}:{unit.id}"] = unit.synthetic_reference_grade
        report = build_geometry_from_morphology(plant, materials, instance_id=instance.plant_id,
            position=instance.position, rotation_deg=instance.rotation_deg, plant_scale=instance.scale,
            add_ground=False,defer_scene_update=True)
        geometry.append({"plant_id": instance.plant_id, **report})
        print(f"PLANT {index+1}/36 {time.perf_counter()-started:.1f}s", flush=True)
    create_cultivation_supports(scene_data, materials, geometry)
    # Grade-specific fruit material, independent of the historic maturity ontology.
    for obj in scene.objects:
        identifier = obj.get("uchuva_reproductive_instance_id", "")
        if identifier in grades and obj.get("uchuva_semantic_class") == "fruit":
            obj.data.materials.clear()
            obj.data.materials.append(materials[f"fruit_ntc_{grades[identifier]}"])
    environment(scene_data.seed, scene_data.plant_instances)
    white = create_material("marker_white", (.9,.9,.9,1), roughness=1)
    black = create_material("marker_black", (.002,.002,.002,1), roughness=1)
    markers = [plate(spec, json.loads((folder.parent/"markers"/f"{spec['id']}.json").read_text()), white, black)
               for spec in payload["markers"]]
    bpy.context.view_layer.update()
    centers = {}
    for obj in scene.objects:
        # Black background in annotation passes, including all context occluders.
        obj.color = (0,0,0,1)
        identifier = obj.get("uchuva_reproductive_instance_id", "")
        if obj.get("uchuva_semantic_class") == "calyx" and identifier in grades:
            center = sum((obj.matrix_world @ Vector(v) for v in obj.bound_box), Vector())/8/U
            centers[identifier] = {"center_world_m": list(center), "plant_id": obj["uchuva_plant_id"],
                                   "synthetic_reference_grade": grades[identifier],
                                   "center_definition": "mesh_local_bounds_midpoint_transformed"}
        elif obj.get("uchuva_semantic_class") in {"flower", "calyx"}:
            obj["uchuva_annotation_visible"] = False
    setup_render_settings(1280,960)
    _set_render_engine(scene, "BLENDER_EEVEE_NEXT")
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.resolution_percentage = 100
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 8
    cameras = []
    for face in payload.get("faces", [payload.get("face", "front")]):
        side = -1 if face == "front" else 1
        target_index = 14
        target_instance = scene_data.plant_instances[target_index]
        target = Vector(target_instance.position)
        plant_height = geometry[target_index]["height"]
        for distance_name, distance_m in (("close", .75), ("mid", 1.6), ("far", 3.2)):
            for height_name, height in (("drone", plant_height/2), ("harvester", .4*U)):
                name = f"{face}_{distance_name}_{height_name}"
                data = bpy.data.cameras.new(name)
                data.lens, data.sensor_width, data.sensor_fit = 35, 36, "HORIZONTAL"
                data.clip_start, data.clip_end = .01, 1000
                camera = bpy.data.objects.new(name, data)
                scene.collection.objects.link(camera)
                camera.location = target + Vector((.1*U, side*distance_m*U, height))
                look = target + Vector((0,0,plant_height*.40))
                camera.rotation_euler = (look-camera.location).to_track_quat("-Z", "Y").to_euler()
                cameras.append((name,camera,{"distance_band": distance_name, "horizontal_distance_m": math.hypot(.1,distance_m),
                    "height_band": height_name, "height_m": height/U, "face": face, "target_plant_id": target_instance.plant_id}))
    bpy.context.view_layer.update()
    scene.camera = cameras[0][1]
    write(folder/"geometry.json", {"script_version": VERSION, "seed": scene_data.seed, "preset": scene_data.preset_name,
                                  "reports": geometry, "build_seconds": time.perf_counter()-started,
                                  "grades": grades, "physical_acceptance": "pending_global_mesh_audit"})
    write(folder/"capture_plan.json", {"markers":markers,"centers":centers,
        "views":[{"name":name,"capture":capture} for name,_,capture in cameras]})
    bpy.ops.wm.save_as_mainfile(filepath=str(folder/"cultivation.blend"))
    if args.build_only:
        return
    print("AUDIT begin", flush=True)
    audit = audit_scene_mesh_collisions(max_bvh_cache_objects=128,limit_clearance_search=True)
    write(folder/"mesh_audit.json", audit)
    print(f"AUDIT {audit['status']} physical={audit['physical_collision_count']}", flush=True)
    captures = []
    for name, camera, capture in cameras:
        capture_start = time.perf_counter()
        output = folder/name
        output.mkdir(exist_ok=False)
        scene.camera = camera
        scene.render.filepath = str(output/"rgb.png")
        bpy.ops.render.render(write_still=True)
        mask = render_crisp_calyx_annotations(camera, output, width=1280, height=960)
        metadata = camera_metadata(camera, markers, centers, 1280, 960)
        write(output/"capture.json", {"script_version": VERSION, "seed": scene_data.seed, "preset": scene_data.preset_name,
            "scene_id": scene_data.scene_id, "capture": capture, "mask": mask,
            "geometry": metadata, "seconds": time.perf_counter()-capture_start})
        captures.append(name)
        print(f"CAPTURE {name} {time.perf_counter()-capture_start:.1f}s", flush=True)
    write(folder/"render_complete.json", {"script_version": VERSION, "seed": scene_data.seed,
          "preset": scene_data.preset_name, "captures": captures, "seconds": time.perf_counter()-started})


if __name__ == "__main__":
    main()
