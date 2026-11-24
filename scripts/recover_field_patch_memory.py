"""Bounded allocator-cache probe then exact V185 protocol rerun with memory telemetry.
No geometry, labels, optimizer hyperparameters or supervision changes.
"""
import argparse
import json
from pathlib import Path
import sys
import time
import psutil
import torch
from ultralytics import YOLO
from train_raster_segmentation import CoverageRasterTrainer, RasterValidator


class MemoryBoundTrainer(CoverageRasterTrainer):
    def get_dataloader(self, dataset_path, batch_size=16, rank=0, mode='train'):
        return super().get_dataloader(dataset_path, 1 if mode=='val' else batch_size, rank, mode)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--probe',action='store_true');parser.add_argument('--validate-only',action='store_true');args=parser.parse_args()
    root=args.root.resolve();output=root/'field_memory_recovery_v186'
    output.mkdir(exist_ok=True)
    if args.validate_only:
        run=output/'safe_validation'
        if run.exists():raise FileExistsError(run)
        torch.set_num_threads(2)
        model=YOLO(output/'training/weights/last.pt')
        records=[]
        def safe_batch(validator):
            torch.cuda.synchronize();before=torch.cuda.memory_reserved()/2**30
            torch.cuda.empty_cache()
            record=dict(batch=validator.batch_i,free_host_gib=psutil.virtual_memory().available/2**30,
                allocated_gib=torch.cuda.memory_allocated()/2**30,reserved_before_gib=before,
                reserved_after_gib=torch.cuda.memory_reserved()/2**30)
            records.append(record)
            if record['free_host_gib']<3:raise RuntimeError('Validation safety margin below3GiB')
        model.add_callback('on_val_batch_end',safe_batch)
        result=model.val(validator=RasterValidator,data=str(root/'field_closeup_v185/dataset/dataset.yaml'),
            imgsz=960,batch=1,workers=0,device=0,half=True,plots=False,mask_ratio=2,overlap_mask=False,
            project=str(output),name='safe_validation',exist_ok=False)
        run.mkdir(exist_ok=True)
        (run/'memory_trace.json').write_text(json.dumps(records,indent=2))
        (run/'summary.json').write_text(json.dumps(dict(images=60,weights_changed=False,
            plots=False,batch=1,min_free_host_gib=min(r['free_host_gib'] for r in records),
            max_reserved_after_gib=max(r['reserved_after_gib'] for r in records),metrics=result.results_dict),indent=2))
        return
    run=output/('probe' if args.probe else 'training')
    if run.exists():raise FileExistsError(run)
    torch.set_num_threads(2)
    counts={'batches':0,'steps':0};epoch_start={}
    model=YOLO(root/'field_training_v184/training/weights/last.pt')
    def step(optimizer,a,k):counts['steps']+=1
    def started(trainer):trainer.optimizer.register_step_post_hook(step)
    def epoch_begin(trainer):
        epoch_start['steps']=counts['steps']
        epoch_start['parameters']={n:p.detach().cpu().clone() for n,p in trainer.model.named_parameters() if p.requires_grad}
    def epoch_end(trainer):
        changes=[float((p.detach().cpu().float()-epoch_start['parameters'][n].float()).abs().max())
                 for n,p in trainer.model.named_parameters() if n in epoch_start['parameters']]
        with (run/'parameter_updates.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(epoch=trainer.epoch+1,steps=counts['steps'],
                epoch_steps=counts['steps']-epoch_start['steps'],changed_tensors=sum(v>0 for v in changes),max_update=max(changes)))+'\n')
        epoch_start.pop('parameters')
    def batch_end(trainer):
        counts['batches']+=1
        torch.cuda.synchronize()
        allocated=torch.cuda.memory_allocated();reserved=torch.cuda.memory_reserved()
        torch.cuda.empty_cache()  # free unused allocator blocks only, not live tensors
        free=psutil.virtual_memory().available/2**30
        record=dict(batch=counts['batches'],epoch=trainer.epoch+1,optimizer_steps=counts['steps'],
            allocated_gib=allocated/2**30,reserved_before_gib=reserved/2**30,
            reserved_after_gib=torch.cuda.memory_reserved()/2**30,
            peak_allocated_gib=torch.cuda.max_memory_allocated()/2**30,free_host_gib=free)
        with (run/'memory_trace.jsonl').open('a') as stream:stream.write(json.dumps(record)+'\n')
        if free<2:raise RuntimeError('RAM safety reserve crossed; stop this experiment')
        if args.probe and counts['batches']>=64:trainer.stop=True
    def validation_batch_end(validator):
        torch.cuda.synchronize();torch.cuda.empty_cache()
        if psutil.virtual_memory().available/2**30<3:
            raise RuntimeError('Validation safety margin below3GiB')
    model.add_callback('on_val_batch_end',validation_batch_end)
    model.add_callback('on_train_start',started)
    model.add_callback('on_train_epoch_start',epoch_begin)
    model.add_callback('on_train_epoch_end',epoch_end)
    model.add_callback('on_train_batch_end',batch_end)
    result=model.train(trainer=MemoryBoundTrainer,data=str(root/'field_closeup_v185/dataset/dataset.yaml'),
        epochs=2,imgsz=960,batch=1,nbs=1,warmup_epochs=0,device=0,workers=0,amp=True,
        optimizer='AdamW',lr0=.001,seed=20261002,deterministic=True,patience=0,
        project=str(output),name=run.name,exist_ok=False,plots=False,mosaic=0,mixup=0,copy_paste=0,
        hsv_h=0,hsv_s=0,hsv_v=.1,overlap_mask=False,mask_ratio=2,cache=False,close_mosaic=0,save=True)
    records=[json.loads(line) for line in (run/'memory_trace.jsonl').read_text().splitlines()]
    summary=dict(probe=args.probe,batches=counts['batches'],optimizer_steps=counts['steps'],
        min_free_host_gib=min(r['free_host_gib'] for r in records),
        max_allocated_gib=max(r['peak_allocated_gib'] for r in records),
        max_reserved_after_gib=max(r['reserved_after_gib'] for r in records),
        geometry_changed=False,supervision_changed=False,source='V184 final; V185 protocol',
        scientific_status='memory diagnostic only' if args.probe else 'technical pilot; native external evaluation pending')
    (run/'execution_summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
