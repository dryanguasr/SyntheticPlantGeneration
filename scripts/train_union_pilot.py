"""Bounded native Ultralytics detection training with optimizer-step evidence."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import torch
from ultralytics import YOLO, __version__
from prepare_union_pilot import ROOT, sha, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm', choices=['real', 'mixed'], default='real')
    parser.add_argument('--dataset', type=Path)
    parser.add_argument('--target-steps', type=int)
    args = parser.parse_args()
    protocol = json.loads((ROOT/'protocol.json').read_text())
    readiness = json.loads((ROOT/'readiness.json').read_text())
    assert readiness['training_allowed'] and readiness['manifest_sha256'] == sha(ROOT/'manifest.json')
    assert sha(protocol['weights']) == protocol['weights_sha256']
    output = ROOT / 'training' / args.arm
    if output.exists():
        raise FileExistsError(output)
    dataset = args.dataset or ROOT/'dataset/data.yaml'
    deadline = datetime.fromisoformat(protocol['training_stop_utc']).timestamp()
    if time.time() >= deadline:
        raise TimeoutError('Training admission deadline reached')
    if args.arm == 'mixed' and not args.target_steps:
        raise ValueError('Mixed arm requires matched optimizer steps')
    torch.set_num_threads(4)
    started = time.monotonic()
    state = {'optimizer_steps':0, 'batches':0, 'epochs':[], 'stop_reason':None}
    model = YOLO(protocol['weights'])
    frozen = {**protocol, 'arm':args.arm, 'dataset':str(dataset.resolve()), 'dataset_yaml_sha256':sha(dataset),
              'ultralytics_version':__version__, 'training_script_sha256':sha(__file__), 'target_steps':args.target_steps}
    write(ROOT/f'{args.arm}_training_config.json', frozen)

    def increment(optimizer, hook_args, hook_kwargs):
        state['optimizer_steps'] += 1

    def on_start(trainer):
        trainer.optimizer.register_step_post_hook(increment)
        transforms = repr(trainer.train_loader.dataset.transforms)
        val_transforms = repr(trainer.test_loader.dataset.transforms)
        if 'RandomHSV' not in transforms or 'RandomFlip' not in transforms:
            raise RuntimeError('Native color/flip transformations missing')
        if 'RandomHSV' in val_transforms or 'RandomFlip' in val_transforms:
            raise RuntimeError('Validation augmentation is enabled')
        write(output/'augmentation_evidence.json', {'train':transforms,'val':val_transforms,
              'args':vars(trainer.args), 'native_transforms_verified':True})

    def epoch_start(trainer):
        trainer._union_before = {n:p.detach().clone() for n,p in trainer.model.named_parameters() if p.requires_grad}
        trainer._union_step_start = state['optimizer_steps']
        trainer._union_epoch_time = time.monotonic()

    def batch_end(trainer):
        state['batches'] += 1
        reason = None
        if args.target_steps and state['optimizer_steps'] >= args.target_steps:
            reason = 'matched_optimizer_steps'
        elif time.monotonic()-started >= protocol['max_training_seconds']:
            reason = '90_minute_budget'
        elif time.time() >= deadline:
            reason = 'absolute_training_cutoff'
        if reason:
            state['stop_reason'] = reason
            trainer.stop = True
        if state['batches'] % 50 == 0:
            write(output/'progress.json', {'epoch':trainer.epoch+1, 'steps':state['optimizer_steps'],
                  'batches':state['batches'], 'elapsed_seconds':time.monotonic()-started,
                  'updated_at_utc':datetime.now(timezone.utc).isoformat()})

    def epoch_end(trainer):
        changes = [float((p.detach().float()-trainer._union_before[n].float()).abs().max())
                   for n,p in trainer.model.named_parameters() if n in trainer._union_before]
        record = {'epoch':trainer.epoch+1, 'optimizer_steps':state['optimizer_steps'],
                  'epoch_steps':state['optimizer_steps']-trainer._union_step_start,
                  'changed_tensors':sum(x>0 for x in changes), 'maximum_update':max(changes),
                  'seconds':time.monotonic()-trainer._union_epoch_time}
        state['epochs'].append(record)
        write(output/'optimizer_evidence.json', state)
        del trainer._union_before

    for event, callback in [('on_train_start',on_start),('on_train_epoch_start',epoch_start),
                            ('on_train_batch_end',batch_end),('on_train_epoch_end',epoch_end)]:
        model.add_callback(event, callback)
    keys = ['imgsz','batch','optimizer','lr0','nbs','warmup_epochs','hsv_h','hsv_s','hsv_v','fliplr','flipud',
            'mosaic','mixup','copy_paste','degrees','perspective','shear','translate','scale','seed']
    kwargs = {key:protocol[key] for key in keys}
    try:
        result = model.train(data=str(dataset.resolve()), epochs=protocol['epochs'], **kwargs,
            device=0, workers=0, cache=False, amp=True, deterministic=True, patience=0,
            project=str((ROOT/'training').resolve()), name=args.arm, exist_ok=False, plots=False,
            close_mosaic=0, save=True, save_period=1, val=True, erasing=0)
        state.update(completed=True, seconds=time.monotonic()-started,
                     metrics=result.results_dict if result is not None else {},
                     actual_batch=model.trainer.batch_size,
                     best_sha256=sha(output/'weights/best.pt'), last_sha256=sha(output/'weights/last.pt'))
        write(output/'completion.json', state)
    except Exception as exc:
        write(output/'failure.json', {'error_type':type(exc).__name__, 'message':str(exc), 'state':state})
        raise


if __name__ == '__main__':
    main()
