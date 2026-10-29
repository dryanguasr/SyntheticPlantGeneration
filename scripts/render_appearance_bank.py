"""Build a reviewed, geometrically paired B/L/T/LT bank without changing plants.

Run from ordinary Python with --blender PATH. The child Blender worker owns the
GPU lock and the awake-time ledger. No bank work starts before human review.
Camera candidates are masked first; only the common selected views get four RGB
renders. Interrupted attempts, rejected scenes and source snapshots are retained.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))
from appearance_campaign import (BANKS, DOSES, charged_job, read, remaining_budget,
                                require, sha, verify_review, verify_real, write,
                                initialize_budget, process_identity, awake_seconds, elapsed_job)
from uchuva_lsystem.appearance_profiles import CLASSES, canonical_hash, component_seed

VERSION = "reviewed-appearance-bank/2.6"
SCENES = 12
PLANTS_PER_SCENE = 2
CAMERAS_PER_SCENE = 40
MAX_CANDIDATES = SCENES * CAMERAS_PER_SCENE
MAX_MORPHOLOGY_ATTEMPTS = 4
MAX_VIEWS = 230
SIZE_BOUNDS = (16., 32., 64.)
RGB_RESERVE_SECONDS = 3 * 3600


def available_doses(count):
    """Only genuinely available complete doses; repeated views never count."""
    require(isinstance(count, int) and count >= 0, "Invalid view count")
    return [dose for dose in DOSES if dose <= count]


def size_bin(value):
    require(math.isfinite(value) and value > 0, "Invalid box size")
    return sum(value >= edge for edge in SIZE_BOUNDS)


def capture_dimensions(real_width, real_height, longest_side=960):
    require(min(real_width, real_height, longest_side) > 0, "Invalid training image dimensions")
    ratio = longest_side / max(real_width, real_height)
    return max(1, round(real_width*ratio)), max(1, round(real_height*ratio))


def reference_target(instances):
    """Joint class × minimum-box-side distribution, exclusively real train."""
    counts = [0] * 12
    for item in instances:
        class_id = item["class_id"]
        require(class_id in (0, 1, 2), "Unknown reference class")
        counts[4 * class_id + size_bin(float(item["min_side_960"]))] += 1
    require(sum(counts) > 0, "No training reference instances")
    return [value / sum(counts) for value in counts]


def labels_from_mask(annotation, assignments, width, height):
    """Retain every visible valid calyx, including one-pixel fragments.

    Boxes enclose visible mask pixels, not inferred full organs. Mask occupancy
    and projected box overlap are deliberately not called physical occlusion.
    """
    require(width > 0 and height > 0, "Invalid image dimensions")
    rows, instances, seen = [], [], set()
    for identifier, item in sorted(annotation["items"].items(), key=lambda p: int(p[0])):
        if item.get("semantic_class") != "calyx" or not item.get("visible_pixels", 0):
            continue
        identity = item.get("instance_id", item.get("name"))
        require(identity in assignments and identity not in seen, "Missing/duplicate mask instance assignment")
        seen.add(identity)
        class_id = assignments[identity]["class_id"]
        require(class_id in (0, 1, 2), "Unknown assigned appearance class")
        box = item.get("bbox_xywh")
        require(isinstance(box, (list, tuple)) and len(box) == 4, "Missing visible mask box")
        x, y, w, h = map(float, box)
        require(all(math.isfinite(v) for v in (x, y, w, h)) and min(x, y) >= 0
                and min(w, h) > 0 and x + w <= width and y + h <= height, "Invalid visible mask box")
        require(0 < item["visible_pixels"] <= w * h, "Invalid mask pixel count")
        rows.append(f"{class_id} {(x+w/2)/width:.10f} {(y+h/2)/height:.10f} {w/width:.10f} {h/height:.10f}\n")
        instances.append(dict(instance_id=identity, mask_id=int(identifier), class_id=class_id,
                              bbox_xywh=list(box), visible_pixels=item["visible_pixels"],
                              min_side_960=min(w, h) * 960 / max(width, height),
                              mask_box_fill_ratio=item["visible_pixels"] / (w * h)))
    return "".join(rows), instances


def validate_pair(view):
    """Reject incomplete or mismatched visual factors before dataset assembly."""
    require(set(view["variants"]) == set(BANKS), "Incomplete four-bank view")
    for key in ("geometry_sha256", "camera_sha256", "assignments_sha256"):
        require(view.get(key), f"Missing {key}")
        require(all(row.get(key) == view[key] for row in view["variants"].values()), f"Unpaired {key}")
    for key in ("label_sha256", "mask_sha256"):
        hashes = {row.get(key) for row in view["variants"].values()}
        require(len(hashes) == 1 and None not in hashes, f"Unpaired {key}")
    return True


def verify_view_files(view):
    validate_pair(view)
    for row in view["variants"].values():
        for key in ("image", "label", "mask"):
            require(sha(row[key]) == row[key+"_sha256"], f"Changed paired {key}: {view['view_id']}")


def select_views(candidates, target, limit=MAX_VIEWS):
    """Deterministic nested order, scene-balanced, softly matched by class/size.

    Each next choice is from the least represented available scenes. Among
    those choices minimize total-variation distance of the accumulated joint
    histogram to training. Density is descriptive, never an admission gate.
    """
    require(0 <= limit <= MAX_VIEWS and len(candidates) <= MAX_CANDIDATES, "Candidate/view budget exceeded")
    require(len(target) == 12 and abs(sum(target) - 1) < 1e-6, "Invalid reference distribution")
    require(len({r["view_id"] for r in candidates}) == len(candidates), "Duplicate candidate view")
    pool = sorted((r for r in candidates if r.get("instances")), key=lambda r: r["view_id"])
    histograms = {}
    for row in pool:
        counts = [0] * 12
        for item in row["instances"]:
            counts[4 * item["class_id"] + size_bin(float(item["min_side_960"]))] += 1
        histograms[row["view_id"]] = counts
    selected, total, scene_counts = [], [0] * 12, Counter()
    while pool and len(selected) < limit:
        minimum = min(scene_counts[r["scene_id"]] for r in pool)
        eligible = [r for r in pool if scene_counts[r["scene_id"]] == minimum]
        def score(row):
            proposed = [a+b for a, b in zip(total, histograms[row["view_id"]])]
            denominator = sum(proposed)
            return (sum(abs(a/denominator-b) for a, b in zip(proposed, target)), row["view_id"])
        winner = min(eligible, key=score)
        selected.append(winner)
        total = [a+b for a, b in zip(total, histograms[winner["view_id"]])]
        scene_counts[winner["scene_id"]] += 1
        pool.remove(winner)
    return selected


def _write_once(path, payload):
    path = Path(path)
    if path.exists():
        require(read(path) == payload, f"Existing evidence differs: {path}")
    else:
        write(path, payload)


def _axes(axes):
    for axis in axes:
        yield axis
        yield from _axes(axis.child_axes)


def reviewed_plant_contract(profiles):
    """Resolve an explicit versioned preset; never infer plant load from a view.

    The reviewed profile must carry the resolved parameter hash, so a preset
    implementation cannot change between the reviewed gallery and this bank.
    This accepts v2 and the richer v3 through their shared audited contract,
    rather than accepting any name merely because it contains a version.
    """
    from uchuva_lsystem.parameters import get_morphology_parameters
    from uchuva_lsystem.grammar import reproductive_load_policy
    name = profiles.get("plant_preset", "")
    require(isinstance(name, str) and re.fullmatch(r"[a-z][a-z0-9_]*_v[1-9][0-9]*", name),
            "An explicit versioned morphology preset is required")
    parameters = get_morphology_parameters(name)
    require(parameters.get("preset_name") == name, "Resolved morphology preset name differs")
    require(parameters.get("morphology_contract_version") == "audit-morphology/2",
            "Morphology contract is not supported by the current validators")
    require(profiles.get("load_policy") == "architecture_driven"
            and reproductive_load_policy(parameters) == "architecture_driven",
            "Reviewed plant load must be architecture_driven")
    require(parameters["reproduction"]["target_reproductive_units_range"].get("active") is False,
            "Historical reproductive quota must be explicitly inactive")
    radii = parameters["internode"]["radius_cm_by_order"]
    maximum_order = int(parameters["axis"]["max_branch_order"]["value"])
    for order in range(maximum_order + 1):
        require(str(order) in radii, f"Missing radius parameters for enabled order {order}")
        low, high = float(radii[str(order)]["min"]), float(radii[str(order)]["max"])
        require(math.isfinite(low) and math.isfinite(high) and 0 < low <= high,
                f"Invalid radius parameters for enabled order {order}")
    parameter_hash = canonical_hash(parameters)
    require(profiles.get("plant_parameters_sha256") == parameter_hash,
            "Reviewed resolved plant parameters changed or their hash is missing")
    return dict(version="appearance-plant-contract/1", preset_name=name,
                morphology_contract_version=parameters["morphology_contract_version"],
                architecture_profile_version=parameters.get("architecture_profile_version"),
                load_policy="architecture_driven", phenology_model="literature_cohort_v1",
                parameters=parameters, parameters_sha256=parameter_hash)


def prepare_plants(seed, scene_id, attempt, instances, folder, *, plant_contract, diversity=None, scene_index=0):
    """No camera input: adult development exists before capture objectives."""
    from uchuva_lsystem.grammar import generate_morphology_tree, reproductive_counts
    from uchuva_lsystem.validation import validate_morphology_tree
    counts = Counter(item["class_id"] for item in instances)
    thresholds = (counts[0] / sum(counts.values()), (counts[0]+counts[1]) / sum(counts.values()))
    plants, records = [], []
    for index in range(PLANTS_PER_SCENE):
        plant_id = f"{scene_id}_a{attempt:02d}_p{index:02d}"
        morphology_seed = component_seed(seed, "bank_morphology", plant_id)
        require(canonical_hash(plant_contract["parameters"]) == plant_contract["parameters_sha256"],
                "Frozen plant input parameters changed")
        plant = generate_morphology_tree(morphology_seed, params=plant_contract["parameters"],
                                        phenology_model=plant_contract["phenology_model"])
        assignments = []
        before = reproductive_counts(plant)
        visual_profile=None
        class_map={}
        if diversity:
            from uchuva_lsystem.appearance_diversity import plant_appearance, appearance_assignments
            visual_profile=plant_appearance(seed,plant_id,scene_index,index,[counts[c] for c in range(3)])
            ids=[n.reproductive_unit.id for a in _axes(plant.axes) for n in a.nodes
                 if n.reproductive_unit is not None and n.reproductive_unit.calyx is not None]
            class_map=appearance_assignments(seed,plant_id,ids,visual_profile['class_probabilities'])
            plant.metadata['appearance_diversity']=visual_profile
        for axis in _axes(plant.axes):
            for node in axis.nodes:
                unit = node.reproductive_unit
                if unit is None or unit.calyx is None:
                    continue
                q = component_seed(seed, "bank_appearance", plant_id + ":" + unit.id) / 2**32
                c = class_map[unit.id] if visual_profile else (0 if q < thresholds[0] else 1 if q < thresholds[1] else 2)
                unit.synthetic_reference_grade = (3, 5, 6)[c]
                unit.calyx.material_key = ("calyx_transition_v1", "calyx_straw_v1", "calyx_dry_v1")[c]
                unit.provenance["appearance_pilot"] = dict(class_id=c, class_name=CLASSES[c],
                    basis="synthetic capacho appearance assignment", human_validation="approved_profile_not_individual_truth",
                    agronomic_maturity=None, seed=component_seed(seed, "bank_appearance", plant_id + ":" + unit.id))
                assignments.append(dict(unit_id=unit.id, class_id=c, grade=unit.synthetic_reference_grade))
        require(before == reproductive_counts(plant), "Appearance assignment changed reproductive load")
        validation = validate_morphology_tree(plant, stage="generated")
        path = folder / (plant_id + ".json")
        _write_once(path, plant.to_dict())
        _write_once(path.with_name(plant_id + "_validation.json"), validation)
        require(validation["parameter_contract"]["snapshot_verified"] is True,
                "Generated plant lacks a verified effective parameter snapshot")
        require(plant.metadata.get("reproductive_load_policy") == "architecture_driven",
                "Generated plant changed reproductive load policy")
        records.append(dict(plant_id=plant_id, seed=morphology_seed, path=str(path.resolve()), sha256=sha(path),
                            assignments=assignments, counts=before, validation=validation["status"],
                            appearance_diversity=visual_profile,
                            preset_name=plant_contract["preset_name"],
                            input_parameters_sha256=plant_contract["parameters_sha256"],
                            effective_parameters_sha256=plant.metadata["effective_parameters_sha256"]))
        plants.append(plant)
    return plants, records


def source_snapshot(root, profiles_file):
    """Fail closed on resume with changed reviewed profiles, code or input data."""
    contract_path = root/"banks/plant_contract.json"
    _write_once(contract_path, reviewed_plant_contract(read(profiles_file)))
    paths = [Path(__file__), REPO/"scripts/appearance_campaign.py",REPO/'scripts/report_appearance_bank.py',
             REPO/'scripts/execute_appearance_pilot.py',root/"review_lock.json", profiles_file,
             root/"real_manifest.json", root/"references/real_instances.json", root/"texture_assets.json", contract_path]
    paths.extend(sorted((REPO/"src/uchuva_lsystem").glob("*.py")))
    continuation=Path(read(profiles_file).get('pose_continuation_manifest', root/'recovery/bank_pose_continuation_20261027/manifest.json'))
    if continuation.exists():
        recovered=read(continuation);paths.append(continuation)
        previous=Path(recovered['previous_source_lock'])
        require(sha(previous)==recovered['previous_source_lock_sha256'],'Changed recovery origin lock')
        paths.append(previous)
        for row in recovered['rows']:
            for key in ('raw','adapted'):
                p=Path(row[key+'_path']);require(sha(p)==row[key+'_sha256'],'Changed recovery tree input');paths.append(p)
    assets = read(root/"texture_assets.json")
    for path, expected in assets["files"].items():
        require(sha(path) == expected, "Changed texture asset: " + path)
        paths.append(Path(path))
    require(sha(assets["manifest"]) == assets["manifest_sha256"], "Changed texture asset manifest")
    paths.append(Path(assets["manifest"]))
    signature = dict(version=VERSION, files={str(p.resolve()): sha(p) for p in paths},
        plant_contract_sha256=sha(contract_path),
        policy=dict(scenes=SCENES, plants_per_scene=PLANTS_PER_SCENE, cameras_per_scene=CAMERAS_PER_SCENE,
                    morphology_attempts_per_scene=MAX_MORPHOLOGY_ATTEMPTS, maximum_selected=MAX_VIEWS,
                    rgb_reserve_seconds=RGB_RESERVE_SECONDS,
                    density_gate=False, size_gate=False, require_valid_mesh=True,
                    admission_policy=read(profiles_file).get('geometry_review',{}).get('admission_policy'),
                    diversity=read(profiles_file).get('diversity')))
    lock = root/"banks/source_lock.json"
    _write_once(lock, signature)
    for source in paths:
        # Snapshot all source and input metadata; large image assets are hash locked.
        if source.suffix.lower() not in {".py", ".json"}:
            continue
        try:
            relative = source.resolve().relative_to(REPO)
        except ValueError:
            relative = Path("external") / (sha(source)[:12] + "_" + source.name)
        target = root/"banks/source_snapshot"/relative
        if target.exists():
            require(sha(target) == sha(source), "Snapshot differs: " + str(target))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    return signature


def _configure_render(profiles):
    import bpy
    scene = bpy.context.scene
    config = profiles["render"]
    require(config["engine"] == "CYCLES", "Only reviewed Cycles configuration supported")
    scene.render.engine = config["engine"]
    scene.cycles.samples = int(config["samples"])
    scene.cycles.use_denoising = bool(config.get("denoise", True))
    scene.cycles.device = "GPU"
    preferences = bpy.context.preferences.addons["cycles"].preferences
    preferences.compute_device_type = config["device"]
    preferences.get_devices()
    devices = [device for device in preferences.devices if device.type == config["device"]]
    require(bool(devices), "Requested GPU backend unavailable")
    for device in preferences.devices:
        device.use = device in devices
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene["uchuva_preserve_mask_components"] = True
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = .125


def _new_camera():
    import bpy
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.name = "appearance_bank_camera"
    camera.data.sensor_width = 36
    camera.data.clip_start, camera.data.clip_end = .01, 250
    camera.data.dof.use_dof = False
    bpy.context.scene.camera = camera
    return camera


def _camera_snapshot(camera, width, height):
    from uchuva_lsystem.blender_annotations import camera_metadata
    result = camera_metadata(camera, width, height)
    # Preserve exact float32 matrix values for a bit-identical reload. Rounded
    # diagnostic matrices can move a one-pixel mask boundary after restoration.
    result["matrix_world"] = [[float(value) for value in line] for line in camera.matrix_world]
    return result


def _center(obj):
    from mathutils import Vector
    return sum((obj.matrix_world @ Vector(v) for v in obj.bound_box), Vector()) / 8


def _camera_pose(camera, objects, reference, seed, scene_id, index, width, height, assignments=None):
    """Choose scale from real train; alter only camera after plant freeze."""
    from mathutils import Vector
    rng = random.Random(component_seed(seed, "bank_camera", f"{scene_id}:{index}"))
    calyces = sorted((o for o in objects if o.get("uchuva_semantic_class") == "calyx"), key=lambda o: o.name)
    matching=[o for o in calyces if (assignments or {}).get(str(o.get('uchuva_reproductive_instance_id')),{}).get('class_id')==reference['class_id']]
    pool=matching or calyces
    focus = pool[component_seed(seed,'bank_focus',f'{scene_id}:{index}')%len(pool)]
    target = _center(focus)
    span = min(float(v) for v in focus.dimensions if v > 0)
    lens = (35., 50., 70.)[index % 3]
    desired = max(2., float(reference["min_side_960"]) * max(width, height) / 960)
    requested_distance=span * width * lens / (36 * desired)
    distance = max(.6,min(40.,requested_distance))
    azimuth = rng.uniform(0, 2*math.pi)
    elevation = rng.uniform(-.15, .28)
    camera.data.lens = lens
    camera.location = target + Vector((math.cos(azimuth), math.sin(azimuth), elevation)).normalized() * distance
    # Off-centre aims vary the composition while preserving the physical plant.
    target += Vector((rng.uniform(-.18,.18), 0, rng.uniform(-.16,.16))) * distance
    camera.rotation_euler = (target-camera.location).to_track_quat("-Z", "Y").to_euler()
    return target, dict(reference_class_id=reference["class_id"], reference_source_row=reference["source_row"],
                       desired_min_side_960=reference["min_side_960"],requested_distance_bu=requested_distance,
                       effective_distance_bu=distance,focus_object=focus.name,
                       focus_policy='hashed existing calyx, reference class when available; physical camera distance 0.6--40 BU',
                       camera_seed=component_seed(seed,"bank_camera",f"{scene_id}:{index}"))


def scene_physically_admitted(mesh, ground, policy=None):
    """Keep the strict gate independent of preset complexity and camera fit.

    A larger crown may increase rejection; neither richer architecture nor a
    useful projected occlusion overrides evaluated intersections/clearance.
    Leaf-leaf soft occupancy remains separately described by the mesh auditor.
    """
    if policy == 'mesh_intersections_block_positive_gaps_descriptive/1':
        return (mesh.get('tolerate_only_leaf_leaf') is True
                and mesh.get('status') in {'valid','invalid'}
                and mesh.get('physical_collision_count',-1)==0
                and mesh.get('clearance_violation_count',-1)>=0
                and ground.get('status')=='valid' and ground.get('physical_collision_count',-1)==0)
    require(policy is None, 'Unknown geometry admission policy')
    return (mesh.get("tolerate_only_leaf_leaf") is True and mesh.get("status") == "valid"
            and mesh.get("physical_collision_count", -1) == 0
            and mesh.get("clearance_violation_count", -1) == 0
            and ground.get("status") == "valid" and ground.get("physical_collision_count", -1) == 0)


def _build_scene(root, profiles, instances, scene_index, attempt, signature):
    import bpy
    from uchuva_lsystem.blender_appearance import create_material_sets, geometry_digest
    from uchuva_lsystem.blender_scene import cleanup_scene
    from uchuva_lsystem.blender_geometry import (build_geometry_from_morphology, create_cultivation_supports,
        audit_scene_mesh_collisions, audit_scene_geometry_envelopes)
    from uchuva_lsystem.blender_environment import create_outdoor_environment, audit_plant_ground_clearance
    from uchuva_lsystem.scene import CultivationScene, CultivationSupport, PlantInstance
    from uchuva_lsystem.blender_bank_repair import repair_bank_plants
    from uchuva_lsystem.support import SupportSystem, SupportPost, SupportLine
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    scene_id = f"scene_{scene_index:02d}"
    folder = root/f"banks/scenes/{scene_id}/attempt_{attempt:02d}"
    folder.mkdir(parents=True, exist_ok=False)
    write(folder/'scene_build_started.json',dict(identity=process_identity(),started_utc=time.time()))
    require(sha(root/"banks/plant_contract.json") == signature["plant_contract_sha256"], "Plant contract changed")
    plant_contract = read(root/"banks/plant_contract.json")
    plants, records = prepare_plants(profiles["seed"], scene_id, attempt, instances, folder/"plants",
                                    plant_contract=plant_contract,diversity=profiles.get('diversity'),scene_index=scene_index)
    continuation=Path(profiles.get('pose_continuation_manifest', root/'recovery/bank_pose_continuation_20261027/manifest.json'))
    if continuation.exists():
        recovered=read(continuation)
        if recovered['scene_id']==scene_id and recovered['attempt']==attempt:
            from uchuva_lsystem.morphology import Plant
            from uchuva_lsystem.blender_bank_repair import anatomy_signature
            for row in recovered['rows']:
                index=row['index'];require(records[index]['plant_id']==row['plant_id'],'Recovery plant identity differs')
                require(canonical_hash(plants[index].to_dict())==row['raw_canonical_sha256'],'Regenerated raw tree differs from recovery origin')
                require(sha(row['adapted_path'])==row['adapted_sha256'],'Changed saved adapted input')
                saved=Plant.from_dict(read(row['adapted_path']))
                require(anatomy_signature(saved)==anatomy_signature(plants[index])==row['anatomy_signature'],
                        'Recovery changed anatomy or appearance classes')
                plants[index]=saved
                records[index]['pose_continuation']=dict(path=row['adapted_path'],sha256=row['adapted_sha256'],
                    original_raw_sha256=row['raw_sha256'],scope='angles only; verified parameter snapshot, organs and class assignments')
            _write_once(folder/'continuation_applied.json',dict(manifest=str(continuation),sha256=sha(continuation),verified=True))
    if any(r["validation"] == "invalid" for r in records):
        _write_once(folder/"rejected.json", dict(reason="morphology_integrity", plants=records))
        return None
    layout = CultivationScene(scene_id=scene_id, preset_name="appearance_fixed_pair_v1", seed=profiles["seed"])
    assignments = {}
    for index, (plant, record) in enumerate(zip(plants, records)):
        # Two independent crowns with spacing defined before camera selection.
        position = ((index-.5)*16, 0., 0.)
        rotation = component_seed(profiles["seed"], "bank_orientation", record["plant_id"]) % 360
        layout.plant_instances.append(PlantInstance(plant_id=record["plant_id"], seed=record["seed"],
                                                   position=position, rotation_deg=rotation, role="foreground"))
        layout.supports.append(CultivationSupport(support_id=record["plant_id"]+"_stake", plant_id=record["plant_id"],
            position=(position[0]+.7, .5+.2*(scene_index%3), position[2]), height=12.+scene_index%3, radius=.08,
            section_width=.12, section_depth=.15, tie_heights=[]))
        assignments.update({record["plant_id"]+":"+r["unit_id"]: r for r in record["assignments"]})
    if not assignments:
        _write_once(folder/"rejected.json", dict(reason="no_reproductive_calyces", plants=records, organs_added=False))
        return None
    environment_seed = component_seed(profiles["seed"], "bank_context", scene_id)
    # Visible trellis context is a downstream scene interpreter; it does not
    # bend branches or create reproductive sites. Common to all four banks.
    support_y=8.+scene_index%3
    layout.support_system=SupportSystem(id=scene_id+'_background_trellis',mode='background_context',
        posts=[SupportPost(f'{scene_id}_post_{i}',(x,support_y,0.),20.,.26,.30,scene_id)
               for i,x in enumerate((-24.,-8.,8.,24.))],
        lines=[SupportLine(f'{scene_id}_top_{i}',(-24.,support_y,z),(24.,support_y,z),.012,scene_id)
               for i,z in enumerate((17.,20.))]+
              [SupportLine(f'{scene_id}_string_{i}',(x,support_y,20.),(x,support_y,.8),.007,scene_id)
               for i,x in enumerate(range(-22,23,3))],
        provenance=dict(status='engineering_heuristic',purpose='scene context only; no plant growth feedback'))
    environment=None
    builds=[]
    def rebuild(current):
        nonlocal environment,builds
        cleanup_scene(include_hidden=True)
        _configure_render(profiles)
        environment=create_outdoor_environment(seed=environment_seed,scene_radius=18,terrain_size=64,
            terrain_subdivisions=24,background_cluster_count=0,
            mode=profiles['context']['modes'][scene_index%len(profiles['context']['modes'])],
            vegetation_centres=[(p.position[0],p.position[1]) for p in layout.plant_instances])
        bpy.context.view_layer.update()
        terrain=bpy.data.objects['uchuva_terrain_agricultural']
        tree=BVHTree.FromObject(terrain,bpy.context.evaluated_depsgraph_get())
        inverse=terrain.matrix_world.inverted()
        sets=create_material_sets(component_seed(profiles['seed'],'bank_material',scene_id),profiles)
        builds=[]
        for plant,record,instance,stake in zip(current,records,layout.plant_instances,layout.supports):
            x,y,_=instance.position
            hit=tree.ray_cast(inverse@Vector((x,y,1000.)),Vector((0,0,-1)))
            require(hit[0] is not None,'Plant root outside terrain')
            z=float((terrain.matrix_world@hit[0]).z)
            instance.position=(x,y,z)
            stake.position=(x+.7,.5+.2*(scene_index%3),z)
            build=build_geometry_from_morphology(plant,sets['previous'],instance_id=record['plant_id'],
                position=instance.position,rotation_deg=instance.rotation_deg,plant_scale=1.,add_ground=False,defer_scene_update=True)
            builds.append(dict(build,plant_id=record['plant_id']))
        bpy.context.view_layer.update()
        # Rigid stakes are context, not a physiological growth constraint. Put
        # them behind the full evaluated crown rather than forcing nodal organs
        # around an arbitrary near-stem stake. No camera enters this decision.
        bounds=[o.matrix_world@Vector(v) for o in bpy.context.scene.objects
                if o.get('uchuva_plant_id') in {p.plant_id for p in layout.plant_instances}
                and o.type in {'MESH','CURVE','SURFACE'} for v in o.bound_box]
        require(bool(bounds),'Missing crown bounds for support placement')
        support_plane=max(v.y for v in bounds)+.7
        for stake in layout.supports:
            stake.position=(stake.position[0],support_plane,stake.position[2])
        create_cultivation_supports(layout,sets['previous'],builds)
        bpy.context.view_layer.update()
        return sets
    def audit(stage):
        mesh=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,max_reported_pairs=None,limit_clearance_search=True)
        ground=audit_plant_ground_clearance(seed=environment_seed)
        write(folder/(stage+'_mesh.json'),mesh);write(folder/(stage+'_ground.json'),ground)
        print('APPEARANCE_BANK_AUDIT',scene_id,attempt,stage,mesh['physical_collision_count'],mesh['clearance_violation_count'],ground['status'],flush=True)
        return mesh,ground
    sets,mesh,ground,validations=repair_bank_plants(plants,records,layout,rebuild,audit,folder,write)
    # This environmental mode deliberately uses procedural context in all four factors.
    environment["asset_policy_effective"] = "procedural_context_frozen_within_scene; absent_external_assets_recorded"
    environment["review_basis"] = "same create_outdoor_environment and reviewed context modes as calibration; no additional external assets"
    environment['support_placement']='behind evaluated foreground crown, 0.7 BU engineering clearance; frozen before camera selection'
    _write_once(folder/"environment.json", environment)
    _write_once(folder/"layout.json", layout.to_dict())
    bpy.context.view_layer.update()
    objects = [o for o in bpy.context.scene.objects if o.get("uchuva_semantic_class") in {"leaf","calyx","flower","stem"}]
    actual = {str(o.get("uchuva_reproductive_instance_id")) for o in objects if o.get("uchuva_semantic_class") == "calyx"}
    require(actual == set(assignments), "Geometry lost or invented a reproductive instance")
    envelopes = audit_scene_geometry_envelopes()
    from uchuva_lsystem.blender_reproductive_orientation import audit_calyx_orientation
    orientation_audit = audit_calyx_orientation(plants, layout, objects)
    _write_once(folder/"calyx_orientation_audit.json", orientation_audit)
    require(orientation_audit['status']=='valid', 'Interpreted calyx orientation or pedicel attachment differs from morphology')
    _write_once(folder/"mesh_audit.json", mesh)
    _write_once(folder/"ground_audit.json", ground)
    _write_once(folder/"envelopes.json", envelopes)
    policy=profiles.get('geometry_review',{}).get('admission_policy')
    if any(v['errors'] for v in validations) or not scene_physically_admitted(mesh, ground,policy):
        _write_once(folder/"rejected.json", dict(reason="physical_mesh_or_clearance", physical_collisions=mesh["physical_collision_count"],
                    clearance_violations=mesh["clearance_violation_count"], terrain_status=ground["status"],
                    terrain_collisions=ground["physical_collision_count"], strict_leaf_only=mesh.get("tolerate_only_leaf_leaf"),
                    organs_removed=False, note="AABB/proxy diagnostics cannot override evaluated-mesh rejection"))
        return None
    camera = _new_camera()
    geometry_hash = geometry_digest(bpy.context.scene)
    record = dict(scene_id=scene_id, attempt=attempt, plants=records, assignments=assignments,
                  geometry_sha256=geometry_hash, assignments_sha256=canonical_hash(assignments),
                  source_lock_sha256=canonical_hash(signature), folder=str(folder.resolve()),
                  plant_contract_sha256=signature["plant_contract_sha256"],
                  blend=str((folder/"common_scene.blend").resolve()), physical_admission="passed_evaluated_mesh_and_terrain",
                  admission_policy=policy,positive_clearance_warnings=mesh['clearance_violation_count'],
                  foliage_profiles={r['plant_id']:r['appearance_diversity'] for r in records},
                  limitations=["leaf-leaf intersections reported as soft occupancy, not proven physical validity",
                               "grass and debris are depth occluders; mesh audit does not exhaustively test all their contacts"])
    bpy.ops.wm.save_as_mainfile(filepath=record["blend"])
    record["blend_sha256"] = sha(record["blend"])
    _write_once(folder/"accepted.json", record)
    return record


def _collect_candidates(root, profiles, references, signature):
    import bpy
    from uchuva_lsystem.blender_appearance import geometry_digest
    from uchuva_lsystem.blender_annotations import render_crisp_calyx_annotations, camera_metadata
    instances = references["instances"]
    stop = False
    for scene_index in range(SCENES):
        if stop or remaining_budget(root, "render") <= RGB_RESERVE_SECONDS:
            break
        scene_id = f"scene_{scene_index:02d}"
        scene = None
        for attempt in range(MAX_MORPHOLOGY_ATTEMPTS):
            folder = root/f"banks/scenes/{scene_id}/attempt_{attempt:02d}"
            if (folder/"rejected.json").exists():
                continue
            if (folder/"accepted.json").exists():
                scene = read(folder/"accepted.json")
                require(scene.get("plant_contract_sha256") == signature["plant_contract_sha256"],
                        "Accepted scene belongs to another reviewed plant contract")
                require(Path(scene["blend"]).is_file(), "Accepted scene lacks preserved common geometry")
                require(sha(scene["blend"]) == scene["blend_sha256"], "Changed common scene file")
                bpy.ops.wm.open_mainfile(filepath=scene["blend"])
                require(geometry_digest(bpy.context.scene) == scene["geometry_sha256"], "Common blend geometry changed")
            else:
                if (folder/'scene_build_started.json').exists():
                    _write_once(folder/'rejected.json',dict(reason='interrupted_preacceptance_scene',evidence_retained=True))
                    continue
                if (folder/"common_scene.blend").exists():
                    # A crash between saving the blend and accepting its record
                    # must not overwrite that evidence or silently consume it.
                    _write_once(folder/"rejected.json", dict(reason="incomplete_scene_save", evidence_retained=True))
                    continue
                scene = _build_scene(root, profiles, instances, scene_index, attempt, signature)
            if scene is not None:
                break
            if remaining_budget(root, "render") <= RGB_RESERVE_SECONDS:
                stop = True
                break
        if scene is None:
            continue
        _configure_render(profiles)
        camera = bpy.context.scene.camera
        objects = [o for o in bpy.context.scene.objects if o.get("uchuva_semantic_class") == "calyx"]
        image_sizes = {}
        for index in range(CAMERAS_PER_SCENE):
            view_id = f"{scene_id}_view_{index:02d}"
            folder = root/"banks/candidates"/view_id
            if (folder/"candidate.json").exists():
                old = read(folder/"candidate.json")
                require(old["geometry_sha256"] == scene["geometry_sha256"], "Candidate belongs to another scene attempt")
                for key in ("mask", "label"):
                    require(sha(old[key]) == old[key+"_sha256"], "Changed candidate " + key)
                continue
            if remaining_budget(root, "render") <= RGB_RESERVE_SECONDS:
                stop = True
                break
            folder.mkdir(parents=True, exist_ok=True)
            # Failed temporary mask attempts are retained in independent subdirectories.
            attempt_folder = folder/f"mask_attempt_{len(list(folder.glob('mask_attempt_*'))):03d}"
            attempt_folder.mkdir()
            reference = instances[component_seed(profiles["seed"], "bank_reference", view_id) % len(instances)]
            image_path = reference["image"]
            if image_path not in image_sizes:
                image = bpy.data.images.load(image_path, check_existing=False)
                image_sizes[image_path] = tuple(int(v) for v in image.size)
                bpy.data.images.remove(image)
            width, height = capture_dimensions(*image_sizes[image_path], longest_side=max(profiles["render"]["width"], profiles["render"]["height"]))
            target, request = _camera_pose(camera, objects, reference, profiles["seed"], scene_id, index, width, height,scene['assignments'])
            request.update(reference_image_dimensions=list(image_sizes[image_path]), reference_split="train")
            bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y = width, height
            bpy.context.view_layer.update()
            require(geometry_digest(bpy.context.scene) == scene["geometry_sha256"], "Camera selection changed morphology")
            pose = _camera_snapshot(camera, width, height)
            annotation = render_crisp_calyx_annotations(camera, attempt_folder, width=width, height=height)
            labels, visible = labels_from_mask(annotation, scene["assignments"], width, height)
            label = attempt_folder/"labels.txt"
            label.write_text(labels, encoding="utf-8")
            write(attempt_folder/"annotations.json", annotation)
            row = dict(view_id=view_id, scene_id=scene_id, plant_ids=[r["plant_id"] for r in scene["plants"]],
                scene_record=str(Path(scene["folder"])/"accepted.json"), geometry_sha256=scene["geometry_sha256"],
                camera=pose, camera_sha256=canonical_hash(pose), target=list(target), request=request,
                assignments_sha256=scene["assignments_sha256"], instances=visible,
                mask=annotation["path"], mask_sha256=sha(annotation["path"]),
                label=str(label.resolve()), label_sha256=sha(label),
                status="eligible" if visible else "no_visible_target", density=len(visible))
            write(folder/"candidate.json", row)
            print("APPEARANCE_BANK_MASK", view_id, len(visible), flush=True)
        if scene_index==0 and profiles.get('diversity',{}).get('early_preview'):
            preview=root/'banks/candidates'/f'{scene_id}_view_00'/'candidate.json'
            if preview.exists():_render_pair_block(root,profiles,[read(preview)])


def _selection(root, references):
    paths = sorted((root/"banks/candidates").glob("*/candidate.json"))
    rows = [read(p) for p in paths]
    require(len(rows) <= MAX_CANDIDATES, "More than 480 unique camera candidates")
    target = reference_target(references["instances"])
    selected = select_views(rows, target)
    selection = dict(version=VERSION, selected_view_ids=[r["view_id"] for r in selected],
        candidates={str(p.resolve()): sha(p) for p in paths}, reference_histogram=target,
        method="greedy joint class/min-side histogram; least represented scene first; view-ID tie break",
        used_validation=False, used_test=False, size_density_admission_gate=False,
        actual_candidates=len(rows), eligible_candidates=sum(bool(r["instances"]) for r in rows),
        available_doses=available_doses(len(selected)), scenes=sorted({r["scene_id"] for r in selected}))
    _write_once(root/"banks/selection_lock.json", selection)
    return selected


def _render_pair_block(root, profiles, selection):
    import bpy
    from mathutils import Matrix, Vector
    from uchuva_lsystem.blender_appearance import create_material_sets, apply_profile, apply_materials, geometry_digest
    from uchuva_lsystem.blender_annotations import render_crisp_calyx_annotations, camera_metadata
    grouped = defaultdict(list)
    for row in selection:
        grouped[row["scene_id"]].append(row)
    stop = False
    for scene_id in sorted(grouped):
        if stop:
            break
        scene_record = read(grouped[scene_id][0]["scene_record"])
        require(sha(scene_record["blend"]) == scene_record["blend_sha256"], "Changed common scene file")
        bpy.ops.wm.open_mainfile(filepath=scene_record["blend"])
        _configure_render(profiles)
        sets = create_material_sets(component_seed(profiles["seed"], "bank_material", scene_id), profiles)
        objects = [o for o in bpy.context.scene.objects if o.get("uchuva_semantic_class")]
        camera = bpy.context.scene.camera
        for row in grouped[scene_id]:
            folder = root/"banks/candidates"/row["view_id"]
            if (folder/"view.json").exists():
                verify_view_files(read(folder/"view.json"))
                continue
            camera.matrix_world = Matrix(row["camera"]["matrix_world"])
            camera.data.lens = row["camera"]["lens_mm"]
            width, height = row["camera"]["width"], row["camera"]["height"]
            bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y = width, height
            bpy.context.view_layer.update()
            pose = _camera_snapshot(camera, width, height)
            require(canonical_hash(pose) == row["camera_sha256"], "Restored camera differs from common mask")
            variants = {}
            for bank in BANKS:
                captures = sorted((folder/bank).glob("attempt_*/capture.json"))
                if captures:
                    require(len(captures) == 1, "Multiple completed variant attempts")
                    variants[bank] = read(captures[0])
                    for key in ("image", "label", "mask"):
                        require(sha(variants[bank][key]) == variants[bank][key+"_sha256"], "Changed paired artifact")
                    continue
                if remaining_budget(root, "render") <= 120:
                    stop = True
                    break
                out = folder/bank/f"attempt_{len(list((folder/bank).glob('attempt_*'))):03d}"
                out.mkdir(parents=True)
                before = geometry_digest(bpy.context.scene)
                require(before == row["geometry_sha256"], "Changed common geometry")
                config = apply_profile(profiles, bank, camera, Vector(row["target"]))
                apply_materials(objects, sets, config["material_mode"], scene_record["assignments"],
                    foliage_profiles=scene_record.get('foliage_profiles'),seed=profiles['seed'])
                require(geometry_digest(bpy.context.scene) == before, "Visual factor changed geometry")
                require(canonical_hash(_camera_snapshot(camera,width,height)) == row["camera_sha256"], "Visual factor changed camera")
                started = time.perf_counter()
                bpy.context.scene.render.filepath = str(out/"rgb.png")
                bpy.ops.render.render(write_still=True)
                annotation = render_crisp_calyx_annotations(camera, out, width=width, height=height)
                labels, visible = labels_from_mask(annotation, scene_record["assignments"], width, height)
                (out/"labels.txt").write_text(labels, encoding="utf-8")
                require(sha(annotation["path"]) == row["mask_sha256"], "Visual factor changed instance mask")
                require(sha(out/"labels.txt") == row["label_sha256"], "Visual factor changed labels")
                write(out/"annotations.json", annotation)
                capture = dict(bank=bank, view_id=row["view_id"], effective_profile=config,
                    image=str((out/"rgb.png").resolve()), image_sha256=sha(out/"rgb.png"),
                    label=str((out/"labels.txt").resolve()), label_sha256=sha(out/"labels.txt"),
                    mask=annotation["path"], mask_sha256=sha(annotation["path"]),
                    camera_sha256=row["camera_sha256"], geometry_sha256=before,
                    foliage_profiles_sha256=canonical_hash(scene_record.get('foliage_profiles',{})),
                    assignments_sha256=row["assignments_sha256"], visible_instances=len(visible),
                    render_wall_seconds=time.perf_counter()-started)
                write(out/"capture.json", capture)
                variants[bank] = capture
                print("APPEARANCE_BANK_RGB", row["view_id"], bank, flush=True)
            if len(variants) == len(BANKS):
                view = dict(row, variants=variants)
                validate_pair(view)
                _write_once(folder/"view.json", view)


def _render_pairs(root, profiles, selection):
    # Finish the smallest complete dose before spending time on the next dose.
    # Within each block load each common scene once, avoiding hundreds of loads.
    offset = 0
    endpoints = sorted(set(min(dose, len(selection)) for dose in DOSES))
    for endpoint in endpoints:
        if remaining_budget(root, "render") <= 120:
            break
        _render_pair_block(root, profiles, selection[offset:endpoint])
        if any(not (root/"banks/candidates"/r["view_id"]/"view.json").exists() for r in selection[offset:endpoint]):
            break
        offset = endpoint


def _manifest(root, selected):
    # Training gets the complete prefix of the frozen nested order. A later
    # completed view cannot silently replace a missing earlier paired view.
    views = []
    for candidate in selected:
        path = root/"banks/candidates"/candidate["view_id"]/"view.json"
        if not path.exists():
            break
        row = read(path)
        verify_view_files(row)
        views.append(row)
    result = dict(version=VERSION, views=views, selected_views=len(selected), complete_views=len(views),
                  available_doses=available_doses(len(views)), target_views=MAX_VIEWS,
                  status="complete" if len(views) == MAX_VIEWS else "insufficient_complete_views",
                  source_lock_sha256=sha(root/"banks/source_lock.json"),
                  plant_contract_sha256=sha(root/"banks/plant_contract.json"),
                  selection_lock_sha256=sha(root/"banks/selection_lock.json"),
                  geometry_mismatch="descriptive only; no size or density admission gate",
                  annotation_contract="every visible valid calyx pixel region, no object/label deletion",
                  selected_scenes=len({r["scene_id"] for r in views}),
                  selected_plants=sorted({p for r in views for p in r["plant_ids"]}))
    path = root/"banks/manifest.json"
    if path.exists() and read(path) != result:
        # Preserve earlier incomplete exposure declarations before append-only recovery.
        archive = root/"banks/manifest_history"/(sha(path)+".json")
        archive.parent.mkdir(parents=True, exist_ok=True)
        if not archive.exists():
            shutil.copy2(path, archive)
    write(path, result)
    return result


def worker(root):
    review = verify_review(root)
    profiles_file = Path(review.get("profiles_file", root/"profiles.json"))
    profiles = read(profiles_file)
    reviewed_plant_contract(profiles)
    verify_real(root)
    references = read(root/"references/real_instances.json")
    require(references["source_split"] == "train" and references["test_images_read"] is False, "Wrong reference split")
    signature = source_snapshot(root, profiles_file)
    with charged_job(root, phase="render", job_id="appearance_bank"):
        try:
            if not (root/"banks/selection_lock.json").exists():
                _collect_candidates(root, profiles, references, signature)
            selected = _selection(root, references)
            _render_pairs(root, profiles, selected)
            for path, expected in signature["files"].items():
                require(sha(path) == expected, "Sources/inputs changed during bank rendering: " + path)
            result = _manifest(root, selected)
            write(root/"banks/state.json", dict(state=result["status"], complete_views=result["complete_views"],
                                              available_doses=result["available_doses"], used_test=False))
        except BaseException as error:
            path = root/"banks/failures"/f"failure_{time.time_ns()}.json"
            write(path, dict(error=repr(error), evidence_retained=True, source_lock_sha256=canonical_hash(signature)))
            raise


def _stop_owned_child(process):
    """Stop the exact Popen handle we created, never a discovered/reused PID."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def launch_worker(root, blender):
    """Watch the child's awake-time ledger without charging the parent twice."""
    initialize_budget(root)
    require(remaining_budget(root, "render") > 0, "No generation budget remains")
    folder = root/"banks/launches"/f"launch_{time.time_ns()}"
    folder.mkdir(parents=True)
    command = [str(blender), "--background", "--factory-startup", "--python-exit-code", "1", "--python", str(Path(__file__).resolve()),
               "--", "--root", str(root), "--worker"]
    record = dict(command=command, state="starting", parent=process_identity(), launched_utc=time.time(),
                  active_time_owner="Blender charged_job only", stdout=str(folder/"stdout.log"), stderr=str(folder/"stderr.log"))
    write(folder/"process.json", record)
    process = None
    owned_jobs = []
    try:
        with (folder/"stdout.log").open("wb") as stdout, (folder/"stderr.log").open("wb") as stderr:
            process = subprocess.Popen(command, cwd=str(REPO), stdout=stdout, stderr=stderr,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            identity = process_identity(process.pid)
            require(identity is not None, "Cannot confirm the launched Blender identity")
            record.update(state="running", child=identity)
            write(folder/"process.json", record)
            startup = awake_seconds()
            while process.poll() is None:
                require(process_identity(process.pid) == identity, "Launched Blender identity changed")
                owned_jobs = [(path, read(path)) for path in (root/"execution_jobs").glob("*.json")
                              if read(path).get("identity") == identity]
                require(owned_jobs or awake_seconds()-startup < 180, "Blender did not start its active-time ledger")
                require(remaining_budget(root, "render") > 0, "Generation active-time budget exhausted; preserving unfinished pair")
                time.sleep(.5)
            require(process.returncode == 0, f"Blender worker failed with exit code {process.returncode}; see {folder}")
            record.update(state="complete", exit_code=process.returncode)
    except BaseException as error:
        # Record the live owner's final awake-time estimate before terminating.
        charges = [(path, max(float(row.get("active_seconds",0)), elapsed_job(row)))
                   for path, row in owned_jobs if row.get("state") == "active"]
        if process is not None:
            _stop_owned_child(process)
        for path, seconds in charges:
            row = read(path)
            if row.get("state") != "active":
                continue
            write(folder/("interrupted_"+path.name), row)
            row.update(state="interrupted", active_seconds=seconds, ended_utc=time.time(),
                       recovery="Owned Blender stopped by launcher; partial render evidence retained")
            write(path, row)
        record.update(state="failed", error=repr(error), child_confirmed_stopped=process is None or process.poll() is not None)
        raise
    finally:
        if process is not None and process.poll() is None:
            _stop_owned_child(process)
        record["ended_utc"] = time.time()
        write(folder/"process.json", record)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--blender", type=Path)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    verify_review(root)  # Deliberately first: no mutation, process or GPU before review.
    if args.worker:
        worker(root)
    else:
        require(args.blender is not None and args.blender.is_file(), "Supply an existing Blender executable")
        launch_worker(root, args.blender)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else None)
