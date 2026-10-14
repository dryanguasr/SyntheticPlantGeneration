"""Freeze the twelve-hour experiment and prepare reproducible new morphologies."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import VERSION, CLASSES, group_seeds, assert_disjoint, write, sha, check_deadline
from uchuva_lsystem.sparse_pilot import sparse_morphology_parameters, prepare_plant, walk_axes
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.bouquet import train_bouquet
from uchuva_lsystem.validation import validate_morphology_tree


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--group', choices=['train', 'val', 'development', 'final'], default='train')
    p.add_argument('--limit', type=int)
    p.add_argument('--offset',type=int,default=0)
    p.add_argument('--resolve', action='store_true')
    a = p.parse_args()
    if not (a.root/'run.json').exists():
        a.root.mkdir(parents=True, exist_ok=False)
        now = datetime.now(timezone.utc)
        groups = group_seeds(); assert_disjoint(groups)
        status = subprocess.check_output(['git', 'status', '--porcelain', '-uall'], cwd=ROOT, text=True)
        paths = [line[3:] for line in status.splitlines()]
        write(a.root/'run.json', dict(script_version=VERSION, seed=420100,
            parameter_preset='bouquet_calyx_appearance_cycles_v1', started_utc=now.isoformat(),
            deadline_unix=now.timestamp()+12*3600, classes=CLASSES, groups=groups,
            initialization='general_pretrained_only', training_domain='synthetic_only',
            target_cycles=3, optional_fourth_requires_time_reserve=True,
            maximum_images_per_cycle=240, human_class_validation='pending',
            head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            preexisting_changes={name:sha(ROOT/name) for name in paths if (ROOT/name).is_file()}))
    check_deadline(a.root)
    seeds = group_seeds()[a.group][a.offset:]
    if a.limit: seeds = seeds[:a.limit]
    for seed in seeds:
        path = a.root/('resolved_morphologies' if a.resolve else 'morphologies')/a.group/f'{seed}.json'
        if path.exists(): continue
        check_deadline(a.root); started = time.perf_counter()
        plant = train_bouquet(prepare_plant(generate_morphology_tree(seed, sparse_morphology_parameters('individual_dense_crown_v3'))))
        rng = random.Random(seed+719)
        for axis in walk_axes(plant.axes):
            for node in axis.nodes:
                if node.leaf:
                    node.leaf.curl = rng.uniform(.12, .32)
                    node.leaf.twist_deg = rng.uniform(-22, 22)
                    node.leaf.insertion_angle_deg = rng.uniform(95, 155)
                    node.leaf.provenance['appearance_cycle_pose'] = 'manual_initial_guess_cycle_1'
        if a.resolve:
            from uchuva_lsystem.scene import CultivationScene, PlantInstance
            from uchuva_lsystem.collisions import resolve_global_collisions
            scene = CultivationScene(str(seed), 'cycle_single_plant', seed,
                plant_instances=[PlantInstance('plant',seed)])
            contacts = resolve_global_collisions(scene, {'plant':plant}, iterations=16,
                optimize_poses=False, allow_leaf_leaf_overlap=True)
            write(path.with_name(f'{seed}_proxy_contacts.json'), contacts)
        plant.metadata['segmentation_contract'] = {'version':VERSION, 'classes':CLASSES,
            'green_in_pintona':True, 'agronomic_maturity':'unknown', 'group':a.group}
        write(path, plant.to_dict())
        write(path.with_name(f'{seed}_validation.json'), dict(script_version=VERSION,seed=seed,
            parameter_preset=plant.parameter_preset, **validate_morphology_tree(plant)))
        print('MORPHOLOGY', a.group, seed, round(time.perf_counter()-started,2), flush=True)


if __name__ == '__main__': main()
