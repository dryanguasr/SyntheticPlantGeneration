"""Chain exact-mask export, measured common budget and one fresh training run."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uchuva_lsystem.execution_budget import remaining_seconds
from uchuva_lsystem.segmentation_cycles import write


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--iteration', type=int, required=True)
    parser.add_argument('--capture-folder',default='dataset_captures')
    args = parser.parse_args()
    cycle = args.root / f'cycle_{args.iteration:02d}'
    dataset = cycle / 'dataset'
    if not (dataset / 'dataset_contract.json').exists():
        subprocess.run([sys.executable, str(ROOT / 'scripts/export_raster_cycle.py'),
                        '--captures', str(cycle / args.capture_folder), '--output', str(dataset),
                        '--protocol-root', str(args.root)], check=True)
    contract = json.loads((dataset / 'dataset_contract.json').read_text())
    if not contract['training_eligible']:
        raise ValueError('Dataset remains ineligible')

    def train(name, output, epochs, size, batch, timeout, technical=False):
        command = [sys.executable, str(ROOT / 'scripts/run_effective_job.py'),
                   '--root', str(args.root), '--name', name, '--timeout', str(timeout), '--',
                   sys.executable, str(ROOT / 'scripts/train_raster_segmentation.py'),
                   '--root', str(args.root), '--dataset', str(dataset), '--output', str(output),
                   '--epochs', str(epochs), '--size', str(size), '--batch', str(batch)]
        if technical:
            command.append('--technical')
        return subprocess.run(command).returncode

    budget_path = args.root / 'common_optimization_budget.json'
    if not budget_path.exists():
        if args.iteration != 1:
            raise ValueError('Common budget must be frozen in the first cycle')
        for size, batch in ((960, 2), (960, 1), (768, 1)):
            name = f'full_dataset_benchmark_{size}_{batch}'
            output = args.root / name
            if not (output / 'experiment.json').exists():
                code = train(name, output, 3, size, batch, 1800, technical=True)
                if code:
                    log = (args.root / 'execution_jobs' / f'{name}.log').read_text(errors='replace')
                    if 'out of memory' in log.lower():
                        continue
                    raise RuntimeError(f'Benchmark failed; inspect {name} without bypassing its error')
            experiment = json.loads((output / 'experiment.json').read_text())
            if experiment['epochs_completed'] != 3:
                raise ValueError('Incomplete benchmark')
            rows = list(csv.DictReader((output / 'results.csv').open()))
            times = [float(next(value for key, value in row.items() if key.strip() == 'time')) for row in rows]
            per_epoch = max(times[-1] / 3, (times[-1] - times[0]) / 2)
            # Reserve final closure, two later capture batches and flight/field work.
            reserve = 5400 + 3600 + 2700
            epochs = min(60, int(max(0, remaining_seconds(args.root) - reserve) / (3 * per_epoch * 1.25)))
            if epochs < 1:
                raise TimeoutError('Insufficient effective budget for three common training runs and closure')
            write(budget_path, dict(version='common-optimization-budget/1.0', epochs=epochs,
                image_size=size, batch=batch, measured_epoch_seconds=per_epoch,
                benchmark=str(output), reserve_seconds=reserve, runtime_safety_factor=1.25,
                selection='runtime and memory only; no development or final model metrics',
                seed=20261002, initialization='same general yolo26n-seg.pt for each cycle'))
            break
        else:
            raise RuntimeError('All permitted benchmark memory configurations failed')
    budget = json.loads(budget_path.read_text())
    if (cycle / 'training/experiment.json').exists():
        print('Training already complete; no duplicate run', flush=True)
        return
    timeout = min(remaining_seconds(args.root) - 5400,
                  budget['epochs'] * budget['measured_epoch_seconds'] * 1.5 + 300)
    if timeout <= 0:
        raise TimeoutError('Preserve final closure reserve')
    code = train(f'cycle{args.iteration}_main_training', cycle / 'training', budget['epochs'],
                 budget['image_size'], budget['batch'], timeout)
    if code:
        raise RuntimeError('Main training failed; retain outputs and diagnose before retrying')
    print('MAIN_TRAINING_COMPLETE', args.iteration, flush=True)


if __name__ == '__main__':
    main()
