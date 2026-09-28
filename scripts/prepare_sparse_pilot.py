"""Prepare immutable morphology inputs and ArUco patterns; no Blender required."""
import argparse
from dataclasses import asdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uchuva_lsystem.sparse_pilot import (VERSION, PRESET, SparseConfig, create_sparse_scene,
    prepare_plant, attach_strings, marker_specs, sparse_morphology_parameters, REFERENCE_FRAMES)
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.parameters import get_morphology_parameters
from uchuva_lsystem.validation import validate_morphology_tree
from uchuva_lsystem.collisions import resolve_global_collisions
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.scene import CultivationScene


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def resolve_one(task):
    scene_dict, identifier, plant_dict = task
    local_scene = CultivationScene.from_dict(scene_dict)
    plant = Plant.from_dict(plant_dict)
    report = resolve_global_collisions(local_scene,{identifier:plant},optimize_poses=False)
    return identifier, plant.to_dict(), report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=230926)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    import cv2
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100)
    markers = args.output / "markers"
    markers.mkdir()
    for identifier in range(72):
        pattern = cv2.aruco.generateImageMarker(dictionary, identifier, 600)
        # Export cells too: Blender creates exact vector-like cell geometry, no filtering.
        write(markers / f"{identifier}.json", (pattern[50::100, 50::100] == 0).astype(int).tolist())
        cv2.imwrite(str(markers / f"{identifier}.png"), pattern)
    config = SparseConfig()
    reference = ROOT / "Nuevo Dataset" / "Norma.webp"
    train = ROOT/"outputs/new_real_dataset/captura_20260912_v6/images/train"
    write(args.output / "config.json", {"script_version": VERSION, "preset": PRESET,
          "seed": args.seed, "scene_seeds": [args.seed+i for i in range(4)],
          "config": asdict(config), "reference_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
          "morphology_parameters": sparse_morphology_parameters(),
          "density_references": [{"path":str(train/name),"sha256":hashlib.sha256((train/name).read_bytes()).hexdigest(),
                                  "split":"train","use":"qualitative_crown_coverage_not_measurement"} for name in REFERENCE_FRAMES],
          "collision_resolution_mode":"8_iterations_no_exhaustive_pose_search_global_mesh_audit_required",
          "reference": str(reference), "width": 1280, "height": 960,
          "scene_count": 4, "capture_count": 48, "faces_per_scene": ["front","back"], "grouping": "user_approximation"})
    for index in range(4):
        folder = args.output / f"scene_{index:02d}"
        folder.mkdir()
        scene = create_sparse_scene(args.seed+index, config)
        plants, validations = {}, {}
        for instance in scene.plant_instances:
            plant = prepare_plant(generate_morphology_tree(instance.seed, sparse_morphology_parameters()),config)
            plants[instance.plant_id] = plant
            validations[instance.plant_id] = validate_morphology_tree(plant)
        write(folder / "potential_morphologies.json", {k: v.to_dict() for k,v in plants.items()})
        # Sparse separated crowns: solve each plant locally, then audit full Blender scene.
        # The dense-crop solver rebuilds every plant for each local candidate otherwise.
        collision_report = {"scope":"intraplant_resolution_global_mesh_audit_required","plants":{}}
        tasks = []
        for instance in scene.plant_instances:
            local_scene = deepcopy(scene)
            local_scene.plant_instances = [instance]
            local_scene.support_system = None
            tasks.append((local_scene.to_dict(),instance.plant_id,plants[instance.plant_id].to_dict()))
        # Pure morphology workers; Blender itself remains a single process.
        with ProcessPoolExecutor(max_workers=8) as executor:
            for identifier, plant_dict, report in executor.map(resolve_one,tasks):
                plants[identifier] = Plant.from_dict(plant_dict)
                collision_report["plants"][identifier] = report
                print(f"Resolved {index}:{identifier}",flush=True)
        attach_strings(scene, plants, config)
        validations = {key: validate_morphology_tree(plant) for key, plant in plants.items()}
        write(folder / "collision_resolution.json", collision_report)
        write(folder / "input.json", {"script_version": VERSION, "seed": scene.seed, "preset": PRESET,
              "scene": scene.to_dict(), "plants": {k: v.to_dict() for k, v in plants.items()},
              "markers": marker_specs(scene, config), "faces": ["front", "back"]})
        write(folder / "morphology_validation.json", validations)
        print(folder, flush=True)


if __name__ == "__main__":
    main()
