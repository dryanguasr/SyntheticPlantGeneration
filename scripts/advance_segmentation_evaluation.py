"""Validate a completed development flight and evaluate immutable RGB observations."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uchuva_lsystem.execution_budget import remaining_seconds


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--iteration', type=int, required=True)
    parser.add_argument('--flight', type=Path, required=True)
    args = parser.parse_args()
    cycle = args.root / f'cycle_{args.iteration:02d}'
    if not json.loads((args.flight / 'result.json').read_text())['completed']:
        raise ValueError('Flight did not complete; preserve and diagnose it')
    validation = args.flight / 'segmentation_validation.json'
    if not validation.exists():
        subprocess.run([sys.executable, str(ROOT / 'scripts/validate_segmentation_capture.py'),
                        str(args.flight)], check=True)
    if not json.loads(validation.read_text())['passed']:
        raise ValueError('Flight validation did not pass')
    reference = args.root / 'fixed_development'
    if not (reference / 'reference/reference_lock.json').exists():
        if args.iteration != 1:
            raise ValueError('First-cycle reference is required')
        subprocess.run([sys.executable, str(ROOT / 'scripts/freeze_segmentation_reference.py'),
                        '--flight', str(args.flight), '--output', str(reference)], check=True)
    comparisons = [(cycle, args.flight, 'evaluation_current'),
                   (cycle, reference / 'reference', 'evaluation_reference')]
    if args.iteration > 1:
        comparisons.append((args.root / f'cycle_{args.iteration-1:02d}', args.flight,
                            'evaluation_previous_current'))
    for model_cycle, flight, name in comparisons:
        output = cycle / name
        if (output / 'metrics.json').exists():
            continue
        training = json.loads((model_cycle / 'training/experiment.json').read_text())
        timeout = min(1800, remaining_seconds(args.root) - 5400)
        if timeout <= 0:
            raise TimeoutError('Preserve final closure reserve')
        subprocess.run([sys.executable, str(ROOT / 'scripts/run_effective_job.py'),
            '--root', str(args.root), '--name', f'cycle{args.iteration}_{name}', '--timeout', str(timeout), '--',
            sys.executable, str(ROOT / 'scripts/evaluate_segmentation_flight.py'),
            '--root', str(args.root), '--flight', str(flight),
            '--model', str(model_cycle / 'training/weights/best.pt'), '--output', str(output),
            '--size', str(training['image_size']), '--confidence', str(training['operating_confidence']),
            '--scope', 'development'], check=True)
    print('DEVELOPMENT_EVALUATIONS_COMPLETE; diagnosis and cycle closure remain pending', flush=True)


if __name__ == '__main__':
    main()
