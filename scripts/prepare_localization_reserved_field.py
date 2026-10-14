"""Assemble the six reserved seeds only after every evaluated-mesh audit passes."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uchuva_lsystem.segmentation_cycles import write, sha


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    run = json.loads((root / 'run.json').read_text())
    sources = json.loads((root / 'reserved_audit_selection.json').read_text())
    if set(sources) != set(map(str, run['final_seeds'])):
        raise ValueError('All six reserved seeds must be retained')
    accepted = []
    for seed in run['final_seeds']:
        folder = root / 'reserved_audits' / sources[str(seed)]
        audit = json.loads((folder / 'mesh_audit.json').read_text())
        plant = json.loads((folder / 'morphology.json').read_text())
        if audit['acceptance'] != 'passed' or plant['seed'] != seed:
            raise ValueError(f'Reserved morphology not approved: {seed}')
        accepted.append((seed, folder))
    destination = root / 'approved_morphologies'
    destination.mkdir(exist_ok=False)
    for seed, folder in accepted:
        shutil.copy2(folder / 'morphology.json', destination / f'{seed}.json')
        shutil.copy2(folder / 'mesh_audit.json', destination / f'{seed}_audit.json')
    write(root / 'field_budget.json', dict(final_seeds=run['final_seeds'],
        reservation_sha256=sha(root / 'run.json'), selection='geometry only; no RGB or model metrics'))
    subprocess.run([sys.executable, str(ROOT / 'scripts/assemble_segmentation_field.py'),
        '--root', str(root), '--group', 'final', '--iteration', '2',
        '--seed-manifest', str(root / 'run.json'), '--output', str(root / 'reserved_field_input.json')], check=True)


if __name__ == '__main__':
    main()
