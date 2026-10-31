"""Prescreen admitted catalog targets before expensive visual/SDF preparation.

This diagnostic uses the frozen catalog's exact cylinder endpoints and the
unchanged motion validator. It is not the final exported-SDF or Gazebo audit.
No organs, source files, physical thresholds or sample counts are changed.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uchuva_gazebo.harvest_plants import _config, _load_catalog_plant, _clearance_obstacles, _candidate_clearance, _metres
from uchuva_gazebo.harvester_robot import HarvesterConfig, inverse_kinematics
import uchuva_gazebo.harvest_clearance as motion
from uchuva_lsystem.scene import PlantInstance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Preserve prior screening evidence; use a new output")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    c = _config(config["plants"])
    robot = HarvesterConfig(**config["robot"])
    proxies = []
    for index, seed in enumerate(c["seeds"]):
        instance = PlantInstance(f"plant_{index:03d}", seed,
            position=tuple(value * 8 for value in c["positions_m"][index]), rotation_deg=c["rotations_deg"][index])
        _, _, source, _ = _load_catalog_plant(c["morphology_files"][index], c["proxy_catalog_files"][index], instance, c["source_units_per_metre"])
        proxies.extend(source)
    pedicels = {p.attachment_id: p for p in proxies if p.kind == "pedicel"}
    cache = _clearance_obstacles(proxies)
    cylinders = [{"id": p.proxy_id, "start": list(_metres(p.start)), "end": list(_metres(p.end)), "radius": p.radius / 8}
                 for p in proxies if p.kind in {"stem", "pedicel"}]
    report = dict(kind="catalog_motion_prescreen", final_exported_sdf_audit="pending", gazebo="pending", attempts=[], selected_ids=[],
                  selected_fruits=[], config=config, source_cylinder_count=len(cylinders))

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")

    for index, origin in enumerate(c["positions_m"]):
        pid = f"plant_{index:03d}"
        candidates = []
        for calyx in proxies:
            if calyx.kind != "calyx" or calyx.plant_id != pid:
                continue
            center = list(_metres(calyx.center))
            if not c["minimum_target_height_m"] <= center[2] <= c["maximum_target_height_m"] or center[0] >= origin[0]:
                continue
            clearance, limiting, cut = _candidate_clearance(calyx, pedicels[calyx.attachment_id], proxies, c, cache)
            if clearance < c["clearance_m"]:
                continue
            fruit = dict(id=calyx.attachment_id, plant_id=pid, center_world_m=center,
                         cut_point_world_m=list(cut), radius_m=max(calyx.half_extents) / 8,
                         minimum_initial_clearance_m=clearance)
            candidates.append((center[0], -center[2], fruit))
        candidates.sort(key=lambda row: row[:2])
        selected_count = 0
        print("CANDIDATES", pid, len(candidates), flush=True)
        for _, _, fruit in candidates:
            start_time = time.monotonic()
            attempt = dict(id=fruit["id"], center_world_m=fruit["center_world_m"])
            cut = fruit["cut_point_world_m"]
            base = [cut[0] - config["pickup_standoff_m"], cut[1], 0, 0]
            candidate_fruits = report["selected_fruits"] + [fruit]
            cuts = {pedicels[f["id"]].proxy_id: f["cut_point_world_m"] for f in candidate_fruits}
            trimmed = [dict(row, end=cuts[row["id"]]) if row["id"] in cuts else row for row in cylinders]
            try:
                joints = inverse_kinematics([config["pickup_standoff_m"], 0, cut[2]], config=robot)
                state = motion._world_clearance(joints, base, motion._CylinderIndex(trimmed), candidate_fruits, fruit, robot)
                attempt["cut_state"] = state
                if min(state[key] for key in ("robot_clearance_m", "held_clearance_m", "held_robot_clearance_m")) < .004:
                    attempt.update(passed=False, reason="cut_endpoint_clearance")
                else:
                    # Only the cylinder extraction is substituted. All IK,
                    # samples, margins and exact narrow-phase checks are the
                    # production validator. Final SDF validation is separate.
                    with patch.object(motion, "rigid_cylinders", return_value=trimmed):
                        plan = motion.plan_harvest_motion({"fruits": candidate_fruits, "models": []}, robot,
                            carry_tcp_base_m=config["carry_tcp_base_m"], pickup_standoff_m=config["pickup_standoff_m"])
                    attempt.update(passed=True, plan=plan["targets"][fruit["id"]])
                    report["selected_ids"].append(fruit["id"])
                    report["selected_fruits"].append(fruit)
                    selected_count += 1
            except ValueError as error:
                attempt.update(passed=False, reason=str(error))
            attempt["elapsed_seconds"] = time.monotonic() - start_time
            report["attempts"].append(attempt)
            save()
            print("TARGET", fruit["id"], attempt["passed"], round(attempt["elapsed_seconds"], 2), attempt.get("reason", "passed"), flush=True)
            if selected_count == c["max_dynamic_fruits_per_plant"]:
                break
        if selected_count != c["max_dynamic_fruits_per_plant"]:
            report["complete"] = False
            save()
            return
    report["complete"] = True
    save()


if __name__ == "__main__":
    main()
