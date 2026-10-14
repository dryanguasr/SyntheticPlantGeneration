"""Apply reproducible bouquet training to the existing dense field."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from uchuva_lsystem.bouquet import train_bouquet, PRESET
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.scene import CultivationScene
from uchuva_lsystem.sparse_pilot import attach_strings, walk_axes
from uchuva_lsystem.collisions import build_scene_proxies


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'plants').mkdir()
    payload = json.loads(args.source.read_text())
    scene = CultivationScene.from_dict(payload['scene'])
    plants = {k:train_bouquet(Plant.from_dict(v)) for k,v in payload['plants'].items()}
    attach_strings(scene, plants)
    scene.metadata['crown_preset'] = PRESET
    rows = []
    for instance in scene.plant_instances:
        plant = plants[instance.plant_id]
        single = CultivationScene.from_dict(scene.to_dict())
        single.plant_instances = [instance]
        single.support_system = None
        proxies = build_scene_proxies(single, {instance.plant_id:plant})
        boxes = [proxy.aabb() for proxy in proxies]
        bounds = [[(min(b[0][d] for b in boxes)-instance.position[d])/8,
                   (max(b[1][d] for b in boxes)-instance.position[d])/8] for d in range(3)]
        axes = list(walk_axes(plant.axes))
        rows.append({'plant_id':instance.plant_id, 'proxy_bounds_m':bounds,
                     'axes':len(axes), 'leaves':sum(n.leaf is not None for a in axes for n in a.nodes)})
        (args.output/'plants'/f'{instance.plant_id}.json').write_text(json.dumps(plant.to_dict(),indent=2))
    payload.update(preset=PRESET, script_version=PRESET, scene=scene.to_dict(),
                   plants={k:v.to_dict() for k,v in plants.items()})
    (args.output/'input.json').write_text(json.dumps(payload,indent=2))
    report = {'preset':PRESET, 'source_sha256':hashlib.sha256(args.source.read_bytes()).hexdigest(),
              'height_reference_m':1.8, 'plants':rows, 'review_plants':['plant_13','plant_03','plant_27'],
              'note':'Proxy bounds are screening estimates; rendered mesh bounds must be checked separately.',
              'layout':'unchanged; 1.4 m within rows, 1.8 m between rows; posts 2.5 m'}
    (args.output/'comparison.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'plants':len(rows),'max_proxy_height_m':max(r['proxy_bounds_m'][2][1] for r in rows)}))


if __name__ == '__main__':
    main()
