"""Train-only two-view overfit probes with measured optimizer/parameter updates.

No morphology, render, source labels, validation or test images are modified.
The diagnostic 'val' alias deliberately repeats train images; it is not evaluation.
"""
import argparse
import copy
import json
from pathlib import Path

import numpy as np
from PIL import Image
import torch
from ultralytics import YOLO
from ultralytics.models.yolo.segment import SegmentationPredictor

from train_raster_segmentation import RasterDataset, RasterTrainer
from evaluate_field_pilot import match, metrics, overlay, sha
from raster_segmentation_inference import AreaRasterSegmentationPredictor


class ProbeTrainer(RasterTrainer):
    def build_dataset(self, img_path, mode='train', batch=None):
        return RasterDataset(self.data['path'], mode, self.args.imgsz, False, 2,
                             'any_coverage' if mode == 'train' else 'legacy_nearest')

    def optimizer_step(self):
        if not hasattr(self, 'executed_steps'):
            self.executed_steps = 0
            self.attempts = 0
            self.optimizer.register_step_post_hook(self._record_executed_step)
        parameters = [(n, p) for n, p in self.model.named_parameters() if p.requires_grad]
        before = [p.detach().clone() for _, p in parameters]
        nonfinite = sum(int(not torch.isfinite(p.grad).all()) for _, p in parameters if p.grad is not None)
        scale = self.scaler.get_scale()
        executed_before = self.executed_steps
        super().optimizer_step()
        changes = [(n, float((p.detach().float() - old.float()).abs().max()))
                   for (n, p), old in zip(parameters, before)]
        self.attempts += 1
        record = dict(attempt=self.attempts, epoch=self.epoch + 1,
                      accumulation=self.accumulate, executed=self.executed_steps > executed_before,
                      executed_steps=self.executed_steps, nonfinite_gradient_tensors=nonfinite,
                      scaler_before=scale, scaler_after=self.scaler.get_scale(),
                      changed_parameter_tensors=sum(delta > 0 for _, delta in changes),
                      maximum_absolute_update=max(delta for _, delta in changes),
                      backbone_update=next(delta for n, delta in changes if n == 'model.0.conv.weight'),
                      losses={k: float(v) for k, v in self.loss_items.items()})
        with (self.save_dir / 'optimizer_trace.jsonl').open('a') as stream:
            stream.write(json.dumps(record) + '\n')

    def _record_executed_step(self, optimizer, args, kwargs):
        self.executed_steps += 1


def evaluate(weights, data, output, tag, historical=False):
    model = YOLO(weights)
    rows = [r for r in json.loads((data / 'raster_manifest.json').read_text())['images'] if r['split'] == 'train']
    result = []
    for row in rows:
        rgb = Image.open(row['image']).convert('RGB')
        native = np.array(Image.open(row['mask']))
        prediction = model.predict(row['image'], imgsz=960, rect=False, retina_masks=True,
                                   conf=.001, max_det=300, device=0, verbose=False,
                                   predictor=AreaRasterSegmentationPredictor if historical else SegmentationPredictor)[0]
        masks = (np.zeros((0, *native.shape), dtype=bool) if prediction.masks is None
                 else prediction.masks.data.cpu().numpy().astype(bool))
        labels = [dict(class_id=int(c), confidence=float(s)) for c, s in
                  zip(prediction.boxes.cls.cpu().tolist(), prediction.boxes.conf.cpu().tolist())]
        thresholds = {}
        for threshold in (.25, .01):
            ids = [i for i, label in enumerate(labels) if label['confidence'] >= threshold]
            selected_labels = [labels[i] for i in ids]
            counts, matches, missed = match(native, row['instances'], masks[ids], selected_labels)
            total = metrics({k: sum(c[k] for c in counts) for k in ('tp', 'fp', 'fn')})
            thresholds[str(threshold)] = dict(**total, detections=len(ids))
            if threshold == .25:
                overlay(rgb, masks[ids], selected_labels).save(output / f'{tag}_{Path(row["image"]).stem}.jpg', quality=95)
        result.append(dict(image=Path(row['image']).name, maximum_confidence=max([p['confidence'] for p in labels], default=0),
                           thresholds=thresholds))
    del model
    torch.cuda.empty_cache()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    out = root / 'overfit_diagnosis_v183'
    out.mkdir(exist_ok=False)
    torch.set_num_threads(2)
    source = root / 'field_pilot_v181/dataset'
    source_manifest = source / 'raster_manifest.json'
    all_rows = json.loads(source_manifest.read_text())['images']
    selected = [copy.deepcopy(r) for r in all_rows if Path(r['image']).stem in
                ('train_a_view_003', 'train_b_view_003')]
    assert len(selected) == 2 and all(r['split'] == 'train' for r in selected)
    data = out / 'two_train_views'
    for split in ('train', 'val'):
        (data / 'images' / split).mkdir(parents=True)
    for row in selected:
        for field in ('image', 'mask'):
            row[field] = str(source / row[field])
        assert sha(Path(row['image'])) == row['rgb_sha256']
        assert sha(Path(row['mask'])) == row['raster_sha256']
    aliases = [dict(r, split='val') for r in selected]
    (data / 'raster_manifest.json').write_text(json.dumps(dict(images=selected + aliases), indent=2))
    (data / 'dataset.yaml').write_text(f'path: {data.as_posix()}\ntrain: images/train\nval: images/val\nnames:\n  0: pintona\n  1: madura\n  2: sobremadura\n')
    # Reconstruct possible attempts, NOT actual historical AMP executions.
    last = -1
    attempts = []
    for ni in range(12 * 32):
        accumulate = max(1, int(np.interp(ni, [0, 96], [1, 64]).round())) if ni < 96 else 63
        if ni - last >= accumulate:
            attempts.append(ni); last = ni
    protocol = dict(version='train-only-overfit/183',source_manifest_sha256=sha(source_manifest),
                    images=[r['image'] for r in selected],epochs=40,batches_per_arm=80,
                    size=960,batch=1,lr=.001,warmup_epochs=0,weight_decay=0,
                    augmentation=False,amp=True,training_only=True,
                    historical_v182_reconstructed_attempts=attempts,
                    historical_note='From installed trainer and saved args; actual AMP executed steps were not logged in V182',
                    comparison_note='All probe arms share constant LR, no warmup/decay/augmentation; this isolates accumulation and initialization, not an exact V182 replay')
    (out / 'protocol.json').write_text(json.dumps(protocol, indent=2))
    v182 = root / 'field_training_v182/training/weights/last.pt'
    v177 = root / 'crop_combined_v177/training/weights/last.pt'
    baseline = dict(v182=evaluate(v182, data, out, 'before_v182'),
                    v177_linear=evaluate(v177, data, out, 'before_v177_linear'),
                    v177_area=evaluate(v177, data, out, 'before_v177_area', True))
    (out / 'baseline.json').write_text(json.dumps(baseline, indent=2))
    results = {}
    for name, weights, nbs in [('v182_acc64', v182, 64), ('v182_acc1', v182, 1), ('v177_acc1', v177, 1)]:
        model = YOLO(weights)
        model.train(trainer=ProbeTrainer, data=str(data / 'dataset.yaml'), epochs=40,
                    imgsz=960,batch=1,nbs=nbs,warmup_epochs=0,device=0,workers=0,
                    amp=True,optimizer='AdamW',lr0=.001,lrf=1,weight_decay=0,
                    seed=20261002,deterministic=True,patience=0,project=str(out),name=name,
                    exist_ok=False,plots=False,val=False,save=False,mosaic=0,mixup=0,
                    copy_paste=0,hsv_h=0,hsv_s=0,hsv_v=0,overlap_mask=False,mask_ratio=2,
                    cache=False,close_mosaic=0)
        # Standard saved checkpoints contain EMA; also inspect actual optimizer model.
        model.model = model.trainer.model
        raw_path = out / name / 'raw_final.pt'
        model.save(raw_path)
        trace = [json.loads(line) for line in (out / name / 'optimizer_trace.jsonl').read_text().splitlines()]
        results[name] = dict(initial_sha256=sha(weights),nbs=nbs,attempts=len(trace),
                             executed=sum(t['executed'] for t in trace),
                             changed_steps=sum(t['changed_parameter_tensors'] > 0 for t in trace),
                             nonfinite_attempts=sum(t['nonfinite_gradient_tensors'] > 0 for t in trace),
                             raw=evaluate(raw_path,data,out,name+'_raw'),
                             ema=evaluate(out/name/'weights/last.pt',data,out,name+'_ema'))
        (out / 'results.json').write_text(json.dumps(results, indent=2))
        print('PROBE_RESULT', name, json.dumps(results[name]), flush=True)
        del model
        torch.cuda.empty_cache()
    assert sha(source_manifest) == protocol['source_manifest_sha256']


if __name__ == '__main__':
    main()
