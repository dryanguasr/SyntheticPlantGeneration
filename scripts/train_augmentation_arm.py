"""Step-controlled adapter to the existing native Ultralytics detection trainer."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import time

import torch
from torch.utils.data import DataLoader, Sampler
from ultralytics import YOLO, __version__
from ultralytics.models.yolo.detect import DetectionTrainer
from augmentation_pilot import ROOT, read, write, sha


def schedule_indices(count, seed, epoch, length=1000):
    rng=random.Random(seed); stream=[]
    # Reconstruct a single cyclic shuffled stream; epoch boundaries do not bias coverage.
    needed=(epoch+1)*length
    while len(stream)<needed:
        cycle=list(range(count));rng.shuffle(cycle);stream.extend(cycle)
    return stream[epoch*length:needed]


class FixedSampler(Sampler):
    def __init__(self, trainer, dataset):
        self.trainer,self.dataset=trainer,dataset
    def __len__(self):return 1000
    def __iter__(self):
        t=self.trainer
        indices=schedule_indices(len(self.dataset),t.args.seed,t.epoch)
        paths=[self.dataset.im_files[i] for i in indices]
        if t.control:
            real=[i for i,p in enumerate(self.dataset.im_files) if Path(p).stem.startswith('row_')]
            rng=random.Random(t.args.seed+900000+t.epoch)
            indices=[rng.choice(real) if not Path(p).stem.startswith('row_') else i for i,p in zip(indices,paths)]
        t.sequences.append(dict(epoch=t.epoch,indices=indices,
            planned_source_ids=[Path(p).stem for p in paths],
            actual_source_ids=[Path(self.dataset.im_files[i]).stem for i in indices]))
        return iter(indices)


class StepTrainer(DetectionTrainer):
    target_steps=2000
    control=False
    def __init__(self,*args,**kwargs):
        self.steps=0;self.sequences=[];self.exposure=Counter();self.instance_exposure=Counter()
        self.started=time.time();self.deadline=read(ROOT/'budget.json')['training_deadline']
        super().__init__(*args,**kwargs)

    def get_dataloader(self,dataset_path,batch_size=16,rank=0,mode='train'):
        if mode!='train':return super().get_dataloader(dataset_path,batch_size,rank,mode)
        if batch_size!=2:raise RuntimeError('Batch changed; reject incomparable automatic OOM retry')
        dataset=self.build_dataset(dataset_path,mode,batch_size)
        # Disable optional package-dependent transformations in every arm.
        def disable(transform):
            if transform.__class__.__name__=='Albumentations':transform.p=0
            for child in getattr(transform,'transforms',[]):disable(child)
        disable(dataset.transforms)
        loader=DataLoader(dataset,batch_size=2,sampler=FixedSampler(self,dataset),num_workers=0,
                          pin_memory=True,collate_fn=dataset.collate_fn)
        return loader

    def _setup_train(self):
        super()._setup_train()
        # Default 65536 scale skips initial updates on this dataset. Freeze a conservative
        # scale for every arm; any remaining nonfinite update fails the run explicitly.
        self.scaler=torch.amp.GradScaler('cuda',init_scale=1.0,growth_interval=1000000,enabled=self.amp)
        def increment(*_):self.steps+=1
        self.optimizer.register_step_post_hook(increment)
        assert self.accumulate==1
        write(self.save_dir/'augmentation_evidence.json',dict(train=repr(self.train_loader.dataset.transforms),
            val=repr(self.test_loader.dataset.transforms),args=vars(self.args),optional_albumentations_disabled=True))

    def preprocess_batch(self,batch):
        if time.time()>=self.deadline:raise TimeoutError('Campaign training deadline')
        for index,path in enumerate(batch['im_file']):
            domain='real' if Path(path).stem.startswith('row_') else 'synthetic'
            self.exposure[domain]+=1
            self.instance_exposure[domain]+=int((batch['batch_idx']==index).sum())
        return super().preprocess_batch(batch)

    def optimizer_step(self):
        if self.steps>=self.target_steps:raise RuntimeError('Attempt to exceed frozen update budget')
        for group in self.optimizer.param_groups:
            group['lr']=self.args.lr0*(1-.99*self.steps/max(1,self.target_steps-1))
        before=self.steps
        super().optimizer_step()
        if self.steps!=before+1:raise RuntimeError('AMP skipped an update; run excluded from paired comparison')
        if self.steps%100==0:
            write(self.save_dir/'progress.json',dict(steps=self.steps,target=self.target_steps,
                seconds=time.time()-self.started,exposure=dict(self.exposure),instance_exposure=dict(self.instance_exposure)))

    def validate(self):
        previous=self.best_fitness
        metrics,fitness=super().validate()
        if self.steps%500:raise RuntimeError('Validation is not at an exact 500-step boundary')
        # Explicit macro AP selects checkpoints, not an opaque weighted fitness.
        fitness=metrics['metrics/mAP50-95(B)']
        self.best_fitness=max(previous if previous is not None else -1,fitness)
        return metrics,fitness


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);args=p.parse_args()
    config=read(args.config);protocol=read(ROOT/'protocol.json');output=ROOT/'training'/config['name']
    if output.exists():raise FileExistsError(output)
    assert sha(protocol['weights'])==protocol['weights_sha256']
    for path,digest in read(ROOT/'training_source_lock.json')['files'].items():
        assert sha(path)==digest, 'Frozen training source changed: '+path
    manifest=read(Path(config['dataset']).parent/'manifest.json')
    for row in manifest['entries']:
        assert sha(row['image'])==row['image_sha256'] and sha(row['label'])==row['label_sha256']
    torch.set_num_threads(4)
    StepTrainer.target_steps=config['steps'];StepTrainer.control=config.get('repeat_control',False)
    model=YOLO(protocol['weights']);classic=config['classical']
    frozen=dict(config,protocol_sha256=sha(ROOT/'protocol.json'),dataset_sha256=sha(Path(config['dataset']).parent/'manifest.json'),
                code_sha256=sha(__file__),ultralytics=__version__,torch=torch.__version__)
    write(ROOT/'configs'/f"{config['name']}_frozen.json",frozen)
    started=time.time()
    try:
        model.train(trainer=StepTrainer,data=config['dataset'],epochs=config['steps']//500,
            imgsz=960,batch=2,nbs=2,optimizer='AdamW',lr0=.0002,lrf=.01,warmup_epochs=0,
            hsv_h=0,hsv_s=0,hsv_v=.1 if classic else 0,fliplr=.5 if classic else 0,flipud=0,
            mosaic=0,mixup=0,copy_paste=0,degrees=0,perspective=0,shear=0,translate=0,scale=0,
            erasing=0,bgr=0,multi_scale=0,seed=config['seed'],device=0,workers=0,cache=False,
            amp=True,deterministic=True,patience=0,project=str(ROOT/'training'),name=config['name'],
            exist_ok=False,plots=False,close_mosaic=0,save=True,save_period=1,val=True)
        t=model.trainer
        assert t.steps==config['steps'] and t.batch_size==2
        write(output/'sampling_sequences.json',t.sequences)
        write(output/'completion.json',dict(completed=True,steps=t.steps,seconds=time.time()-started,
            exposure=dict(t.exposure),instance_exposure=dict(t.instance_exposure),
            best_sha256=sha(output/'weights/best.pt'),last_sha256=sha(output/'weights/last.pt'),
            best_validation_ap=float(t.best_fitness),config=frozen))
    except Exception as error:
        write(output/'failure.json',dict(error=repr(error),seconds=time.time()-started))
        raise


if __name__=='__main__':main()
