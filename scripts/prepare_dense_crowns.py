"""Regenerate one field with denser individual crowns, preserving its layout."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uchuva_lsystem.sparse_pilot import sparse_morphology_parameters, prepare_plant, walk_axes, attach_strings
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.scene import CultivationScene
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.collisions import resolve_global_collisions
from uchuva_lsystem.validation import validate_morphology_tree

VERSION = 'individual-crowns/1.0'

def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')

def counts(plant):
    axes = list(walk_axes(plant.axes))
    return {'axes': len(axes), 'leaves': sum(n.leaf is not None for a in axes for n in a.nodes),
            'calyxes': sum(bool(n.reproductive_unit and n.reproductive_unit.calyx) for a in axes for n in a.nodes)}

def worker(task):
    scene_dict, identifier, seed, preset, output = task
    plant = prepare_plant(generate_morphology_tree(seed, sparse_morphology_parameters(preset)))
    before = counts(plant)
    scene = CultivationScene.from_dict(scene_dict)
    scene.plant_instances = [i for i in scene.plant_instances if i.plant_id == identifier]
    scene.support_system = None
    report = resolve_global_collisions(scene, {identifier: plant}, optimize_poses=False,
                                      allow_leaf_leaf_overlap=preset == 'individual_dense_crown_v3')
    assert before == counts(plant), 'Collision resolution must preserve organs'
    folder = Path(output) / 'plants'
    write(folder / f'{identifier}.json', plant.to_dict())
    provenance={'script_version':VERSION,'seed':seed,'parameter_preset':preset}
    write(folder / f'{identifier}_contacts.json', {**report,**provenance})
    write(folder / f'{identifier}_validation.json', {**validate_morphology_tree(plant),**provenance})
    print(f'Prepared {identifier}: {before}', flush=True)
    return identifier, plant.to_dict()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--preset', choices=['individual_dense_crown_v3', 'sparse_overhead_dense_crown_v2'], default='individual_dense_crown_v3')
    p.add_argument('--workers', type=int, default=2)
    p.add_argument('--plants', nargs='+', help='Small technical comparison subset; full field is the default')
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output / 'plants').mkdir()
    source = json.loads(a.source.read_text())
    write(a.output/'configuration.json', {'script_version':VERSION,'parameter_preset':a.preset,
        'seed':source['seed'],
        'parameters':sparse_morphology_parameters(a.preset),'technical_subset':a.plants,
        'source_sha256':hashlib.sha256(a.source.read_bytes()).hexdigest()})
    scene = CultivationScene.from_dict(source['scene'])
    if a.plants:
        scene.plant_instances=[i for i in scene.plant_instances if i.plant_id in a.plants]
        if len(scene.plant_instances)!=len(a.plants):raise ValueError('Unknown or duplicate plant IDs')
    tasks = [(source['scene'], i.plant_id, source['plants'][i.plant_id]['seed'], a.preset, str(a.output)) for i in scene.plant_instances]
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        plants = {k: Plant.from_dict(v) for k,v in pool.map(worker, tasks)}
    # Posts and overhead cables stay fixed; attachment strings must reach regenerated nodes.
    if not a.plants:
        attach_strings(scene, plants)
    payload = {**deepcopy(source), 'script_version': VERSION, 'preset': a.preset,
               'scene': scene.to_dict(), 'plants': {k:v.to_dict() for k,v in plants.items()}}
    scene.metadata['crown_preset'] = a.preset
    payload['scene'] = scene.to_dict()
    write(a.output / 'input.json', payload)
    rows = [{'plant_id': k, 'before': counts(Plant.from_dict(source['plants'][k])), 'after': counts(v)} for k,v in plants.items()]
    medians = {key: {side: statistics.median(r[side][key] for r in rows) for side in ('before','after')} for key in ('axes','leaves','calyxes')}
    ordered = sorted(rows, key=lambda r:(r['before']['leaves'],r['plant_id']))
    write(a.output / 'comparison.json', {'script_version': VERSION, 'seed': source['seed'], 'parameter_preset': a.preset,
        'source_sha256': hashlib.sha256(a.source.read_bytes()).hexdigest(), 'parameters': sparse_morphology_parameters(a.preset),
        'medians': medians, 'plants': rows, 'review_plants': [ordered[i]['plant_id'] for i in (0,len(ordered)//2,-1)],
        'field_layout': 'unchanged', 'real_spacing_user_observation_m': 'approximately 3 or more; not applied',
        'parameter_status': 'engineering_heuristic', 'human_validation': 'pending'})
    print(json.dumps(medians), flush=True)

if __name__ == '__main__':
    main()
