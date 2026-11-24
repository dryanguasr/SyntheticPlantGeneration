"""Audited angular correction of saved plants; no camera targets or training.

The parent freezes sources and accounts for active preparation time. The Blender
worker preserves generated trees, writes adapted trees separately and rebuilds
the complete scene before evaluating its physical admission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def worker(args):
    import bpy
    from uchuva_lsystem.appearance_profiles import component_seed
    from uchuva_lsystem.blender_appearance import create_material_sets
    from uchuva_lsystem.blender_scene import cleanup_scene
    from uchuva_lsystem.blender_geometry import (
        build_geometry_from_morphology, audit_scene_mesh_collisions, audit_scene_geometry_envelopes)
    from uchuva_lsystem.blender_environment import create_outdoor_environment, audit_plant_ground_clearance
    from uchuva_lsystem.blender_pose_repair_v2 import repair_size_preserving_poses
    from uchuva_lsystem.morphology import Plant
    from uchuva_lsystem.grammar import record_reproductive_counts
    from uchuva_lsystem.validation import validate_morphology_tree
    from uchuva_lsystem.axis_pose_repair import repair_axis_poses
    from uchuva_lsystem.scene import PlantInstance

    root, out = args.root.resolve(), args.output.resolve()
    source = root / "calibration" / args.source_round
    manifest = read(out / "input_manifest.json")
    assert sha(source / "profiles.json") == manifest["profiles_sha256"]
    profiles = read(out / "profiles.json")
    for path, digest in read(root / "texture_assets.json")["files"].items():
        assert sha(path) == digest
    records = []
    for original in read(source / "plants.json")["plants"]:
        index = original["index"]
        if index not in args.indices:
            continue
        assert sha(original["path"]) == original["sha256"] == manifest["trees"][str(index)]
        folder = out / f"plant_{index:02d}"
        folder.mkdir(exist_ok=True)
        if (folder / "result.json").exists():
            raise FileExistsError("Use a new attempt to preserve prior repair evidence")
        plant = Plant.from_dict(read(original["path"]))
        plant_id = f"calibration_{index:02d}"
        environment_seed = component_seed(20261026, "context", index)

        def build(current):
            cleanup_scene(include_hidden=True)
            sets = create_material_sets(component_seed(20261026, "material", index), profiles)
            build_geometry_from_morphology(current, sets["previous"], instance_id=plant_id,
                                          add_ground=False, defer_scene_update=True)
            bpy.context.view_layer.update()
            bpy.context.scene.unit_settings.system = "METRIC"
            bpy.context.scene.unit_settings.scale_length = .125
            environment = create_outdoor_environment(seed=environment_seed, scene_radius=5, terrain_size=12,
                terrain_subdivisions=18, background_cluster_count=0,
                mode=profiles["context"]["modes"][index % 2])
            bpy.context.view_layer.update()
            return sets, environment

        def audit(prefix):
            mesh = audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True, limit_clearance_search=True,
                                              max_reported_pairs=None)
            ground = audit_plant_ground_clearance(seed=environment_seed)
            write(folder / f"{prefix}_mesh.json", mesh)
            write(folder / f"{prefix}_ground.json", ground)
            write(folder / f"{prefix}_envelopes.json", audit_scene_geometry_envelopes())
            print("CONTACT_AUDIT", index, prefix, mesh["physical_collision_count"],
                  mesh["clearance_violation_count"], ground["physical_collision_count"], flush=True)
            return mesh, ground

        sets, environment = build(plant)
        write(folder / "environment.json", environment)
        mesh, ground = audit("before")
        write(folder / "generated.json", plant.to_dict())
        for axis_pass in range(args.axis_passes):
            from mathutils import Vector
            from mathutils.bvhtree import BVHTree
            inventory = {o.name: {"type": o.type, "hide_render": o.hide_render,
                "properties": {k: v for k, v in o.items() if k.startswith("uchuva_") and isinstance(v, (str,int,float,bool))}}
                for o in bpy.context.scene.objects}
            write(folder / f"axis_{axis_pass:02d}_inventory.json", inventory)
            terrain = bpy.data.objects["uchuva_terrain_agricultural"]
            terrain_bvh = BVHTree.FromObject(terrain, bpy.context.evaluated_depsgraph_get())
            inverse = terrain.matrix_world.inverted()
            def ground_height(x, y):
                origin = inverse @ Vector((x, y, 1000.))
                hit = terrain_bvh.ray_cast(origin, Vector((0,0,-1)))
                if hit[0] is None:
                    raise ValueError("Axis candidate outside evaluated terrain")
                return (terrain.matrix_world @ hit[0]).z
            axis_report = repair_axis_poses(plant, instance=PlantInstance(plant_id=plant_id,seed=plant.seed),
                intersection_pairs=mesh["physical_collisions"],object_inventory=inventory,
                clearance_pairs=mesh["clearance_violations"],
                include_organ_axis_constraints=args.organ_axis,
                angular_step_deg=args.axis_step,
                max_passes=2,max_trials_per_axis=48,max_seconds=240,ground_height=ground_height)
            write(folder / f"axis_{axis_pass:02d}_repair.json", axis_report)
            write(folder / f"axis_{axis_pass:02d}_adapted.json", plant.to_dict())
            if not axis_report["changes"]:
                break
            sets, _ = build(plant)
            mesh, ground = audit(f"axis_{axis_pass:02d}")
        report = repair_size_preserving_poses(plant, sets["previous"], instance_id=plant_id,
            max_passes=args.passes, max_trials_per_organ=args.trials, max_seconds=args.seconds,
            ground_clearance_m=.001,fine_angular_step_deg=args.fine_step,
            dense_reproductive_step_deg=args.dense_step,clearance_tiebreak=args.clearance_tiebreak,
            checkpoint=folder / "checkpoint.json")
        write(folder / "repair.json", report)
        record_reproductive_counts(plant, "adapted")
        validation = validate_morphology_tree(plant, stage="adapted")
        write(folder / "adapted_validation.json", validation)
        adapted_path = folder / "adapted.json"
        write(adapted_path, plant.to_dict())
        # Re-read the actual serialised tree. Never accept solver cache scores as
        # substitutes for a complete reconstruction and independent audit.
        rebuilt = Plant.from_dict(read(adapted_path))
        build(rebuilt)
        mesh, ground = audit("after")
        admitted = (not validation["errors"] and mesh["physical_collision_count"] == 0
                    and mesh["clearance_violation_count"] == 0 and ground["status"] == "valid"
                    and ground["physical_collision_count"] == 0)
        row = dict(original, path=str(adapted_path), sha256=sha(adapted_path), generated_path=original["path"],
                   generated_sha256=original["sha256"], validation_stage="adapted", physical_admission=admitted)
        records.append(row)
        write(folder / "result.json", dict(record=row, physical_admission=admitted,
            remaining_intersections=mesh["physical_collision_count"], remaining_clearances=mesh["clearance_violation_count"],
            terrain_collisions=ground["physical_collision_count"], training_eligible=False))
        write(out / "plants.json", dict(plants=records, training_eligible=False, review="pending"))
    write(out / "repair_completion.json", dict(complete=len(records) == len(args.indices), plants=len(records),
        all_physically_admitted=all(r["physical_admission"] for r in records), training_eligible=False,
        camera_used_by_repair=False, human_review="pending"))


def launch(args):
    from appearance_campaign import charged_job, remaining_budget, process_identity
    root, out = args.root.resolve(), args.output.resolve()
    if not out.is_relative_to(root) or out == root:
        raise ValueError("Repair output must be a new directory inside its campaign")
    if out.exists():
        raise FileExistsError("Use a new attempt directory, never overwrite repair evidence")
    source = root / "calibration" / args.source_round
    out.mkdir(parents=True)
    shutil.copy2(source / "profiles.json", out / "profiles.json")
    snapshot = out / "source_snapshot"
    files = list((REPO / "src/uchuva_lsystem").glob("*.py")) + list((REPO / "assets/textures/current").glob("*")) + [Path(__file__)]
    hashes = {}
    for path in files:
        if not path.is_file():
            continue
        relative = path.relative_to(REPO)
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        hashes[str(relative)] = sha(target)
    write(snapshot / "snapshot_manifest.json", dict(files=hashes))
    write(out / "input_manifest.json", dict(profiles_sha256=sha(source / "profiles.json"),
        trees={str(r["index"]): r["sha256"] for r in read(source / "plants.json")["plants"]},
        indices=args.indices, passes=args.passes, trials=args.trials, seconds_per_plant=args.seconds,axis_passes=args.axis_passes,
        fine_angular_step_deg=args.fine_step,dense_reproductive_step_deg=args.dense_step,
        clearance_tiebreak=args.clearance_tiebreak,
        include_organ_axis_constraints=args.organ_axis,
        axis_angular_step_deg=args.axis_step,
        cpu_workers=args.cpu_workers, resource="CPU geometry only; one active-time accounting owner"))
    # These workers only evaluate CPU geometry: they never render or train. A
    # single accounting owner holds the campaign GPU lock throughout, so no
    # training/render workload can overlap them. Each worker owns separate files.
    count = min(args.cpu_workers, len(args.indices))
    jobs = []
    for number in range(count):
        indices = args.indices[number::count]
        destination = out if count == 1 else out / f"worker_{number:02d}"
        destination.mkdir(exist_ok=True)
        if count != 1:
            for name in ("profiles.json", "input_manifest.json"):
                shutil.copy2(out / name, destination / name)
        command = ["C:/Program Files/Blender Foundation/Blender 5.1/blender.exe", "--background", "--factory-startup",
            "--python-exit-code", "1", "--python", str(snapshot / "scripts" / Path(__file__).name), "--", "--worker",
            "--root", str(root), "--source-round", args.source_round, "--output", str(destination),
            "--indices", ",".join(map(str, indices)), "--seconds", str(args.seconds), "--passes", str(args.passes), "--trials", str(args.trials),
            "--axis-passes",str(args.axis_passes),"--axis-step",str(args.axis_step)]
        if args.fine_step is not None:
            command += ["--fine-step",str(args.fine_step)]
        if args.dense_step is not None:
            command += ["--dense-step",str(args.dense_step)]
        if args.clearance_tiebreak:
            command += ["--clearance-tiebreak"]
        if args.organ_axis:
            command += ["--organ-axis"]
        jobs.append(dict(output=destination, command=command, indices=indices))
    with charged_job(root, phase="render", job_id="repair_" + out.name):
        try:
            for job in jobs:
                job["log"] = (job["output"] / "worker.log").open("w", encoding="utf-8")
                process = subprocess.Popen(job["command"], cwd=REPO, stdout=job["log"], stderr=subprocess.STDOUT)
                job["process"] = process
                write(job["output"] / "process.json", dict(identity=process_identity(process.pid), command=job["command"],
                    started_utc=time.time(), resource="CPU geometry only", accounting_owner="repair_" + out.name))
            while any(job["process"].poll() is None for job in jobs):
                if remaining_budget(root, "render") <= 0:
                    raise TimeoutError("Active generation budget exhausted")
                time.sleep(2)
            failures = [{"output":str(j["output"]), "exit_code":j["process"].returncode} for j in jobs if j["process"].returncode]
            if failures:
                raise RuntimeError(f"Blender workers failed; evidence preserved: {failures}")
            if count != 1:
                records = sorted([r for job in jobs for r in read(job["output"] / "plants.json")["plants"]],key=lambda r:r["index"])
                assert [r["index"] for r in records] == sorted(args.indices)
                write(out / "plants.json", dict(plants=records,training_eligible=False,review="pending"))
                write(out / "repair_completion.json",dict(complete=True,plants=len(records),
                    all_physically_admitted=all(r["physical_admission"] for r in records),training_eligible=False,
                    camera_used_by_repair=False,human_review="pending",cpu_workers=count))
        except BaseException as error:
            for job in jobs:
                process = job.get("process")
                if process is not None and process.poll() is None:
                    process.terminate()
                    process.wait(timeout=30)
            write(out / "failure.json", dict(error=repr(error), workers=[dict(output=str(j["output"]),
                exit_code=j["process"].returncode) for j in jobs if "process" in j]))
            raise
        finally:
            for job in jobs:
                if "log" in job:
                    job["log"].close()
    print(out, flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-round", default="lower_crown_v6_raw")
    parser.add_argument("--indices", default="0,1,2,3")
    parser.add_argument("--seconds", type=float, default=600)
    parser.add_argument("--passes", type=int, default=2)
    parser.add_argument("--trials", type=int, default=56)
    parser.add_argument("--axis-passes", type=int, default=0)
    parser.add_argument("--axis-step", type=float, default=3.)
    parser.add_argument("--fine-step", type=float, default=None)
    parser.add_argument("--dense-step", type=float, default=None)
    parser.add_argument("--clearance-tiebreak", action="store_true")
    parser.add_argument("--organ-axis", action="store_true")
    parser.add_argument("--cpu-workers", type=int, choices=(1,2), default=1,
                        help="Independent CPU geometry workers; no rendering or GPU allocation")
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else None)
    args.indices = [int(value) for value in args.indices.split(",")]
    if not args.indices or len(set(args.indices)) != len(args.indices) or any(i not in range(4) for i in args.indices):
        raise ValueError("Specify unique plant indices 0..3")
    if args.worker:
        worker(args)
    else:
        launch(args)


if __name__ == "__main__":
    main()
