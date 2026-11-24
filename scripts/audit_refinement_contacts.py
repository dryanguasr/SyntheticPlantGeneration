"""Read-only conservative contact audit of saved development morphologies."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.scene import CultivationScene, PlantInstance
from uchuva_lsystem.collisions import audit_proxy_contacts, build_scene_proxies


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', nargs='+', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    records = []
    for index, filename in enumerate(args.inputs):
        start = time.monotonic()
        path = Path(filename)
        raw = path.read_bytes()
        plant = Plant.from_dict(json.loads(raw))
        instance = PlantInstance(plant_id='review_plant', seed=plant.seed)
        scene = CultivationScene('isolated_review', 'saved_morphology', plant.seed,
                                 plant_instances=[instance])
        plants = {instance.plant_id: plant}
        proxies = build_scene_proxies(scene, plants)
        audit = audit_proxy_contacts(scene, plants, proxies=proxies)
        audit['limitations'] = ['Conservative proxies, not mesh intersection proof',
                               'Isolated plant without support geometry',
                               'No camera-dependent occlusion measurement']
        name = f'{index:02d}_{path.parent.name}_{plant.seed}.json'
        (output / name).write_text(json.dumps(audit, indent=2), encoding='utf-8')
        record = dict(source=str(path.resolve()), sha256=hashlib.sha256(raw).hexdigest(),
                      proxy_count=len(proxies), counts=audit['counts'],
                      elapsed_seconds=time.monotonic()-start, report=name)
        records.append(record)
        (output / 'progress.json').write_text(json.dumps(dict(completed=len(records),
            total=len(args.inputs), records=records), indent=2), encoding='utf-8')
        print('AUDIT_COMPLETE', len(records), '/', len(args.inputs), record['counts'], flush=True)


if __name__ == '__main__':
    main()
