"""Train YOLO-seg with exact instance rasters, preserving occluded components.

The optional polygon export remains compatibility-only: YOLO's single-contour
format cannot losslessly encode arbitrary disconnected visible instances.
No installed Ultralytics files are modified.
"""
import argparse
from copy import copy
import json
from pathlib import Path
import random
import sys
import time

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset
from ultralytics import YOLO
from ultralytics.data.dataset import YOLODataset
from ultralytics.models.yolo.segment import SegmentationTrainer, SegmentationValidator

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import VERSION, write, sha, check_deadline


def coverage_masks(native_mask, instances, size, ratio, flipped=False):
    """Experimental any-coverage targets; never used as evaluation truth.

    Resize each binary instance independently with area coverage, so IDs cannot
    erase each other. A coarse cell is positive if any source area contributes.
    This conservatively expands boundaries and can create overlapping targets.
    """
    h,w=native_mask.shape;scale=min(size/w,size/h)
    nw,nh=round(w*scale),round(h*scale);left,top=(size-nw)//2,(size-nh)//2
    result=[]
    for item in instances:
        binary=(native_mask==item['mask_id']).astype(np.float32)
        if not binary.any():raise ValueError('Instance absent from native raster')
        canvas=np.zeros((size,size),np.float32)
        canvas[top:top+nh,left:left+nw]=cv2.resize(binary,(nw,nh),interpolation=cv2.INTER_AREA)
        if flipped:canvas=canvas[:,::-1].copy()
        result.append(cv2.resize(canvas,(size//ratio,size//ratio),interpolation=cv2.INTER_AREA)>0)
    return np.asarray(result,dtype=np.uint8).reshape(-1,size//ratio,size//ratio)


class RasterDataset(Dataset):
    """Standard trainer batch contract, with masks sourced directly from IDs."""
    collate_fn = staticmethod(YOLODataset.collate_fn)

    def __init__(self, root, split, size, augment=False, ratio=4, supervision_policy='legacy_nearest'):
        if ratio not in (1,2,4) or size%ratio:raise ValueError('Invalid supervision grid')
        if supervision_policy not in ('legacy_nearest','any_coverage'):raise ValueError('Unknown supervision policy')
        if split!='train' and supervision_policy!='legacy_nearest':raise ValueError('Coverage targets are training-only')
        self.supervision_policy=supervision_policy
        self.root=Path(root);self.imgsz=size;self.augment=augment;self.ratio=ratio
        report=json.loads((self.root/'raster_manifest.json').read_text())
        self.rows=[r for r in report['images'] if r['split']==split]
        if not self.rows:raise ValueError('Empty split: '+split)
        self.im_files=[str(self.root/r['image']) for r in self.rows]
        self.rect=False;self.mosaic=False;self.labels=[]
        for row in self.rows:
            w,h=row['image_size'];boxes=[]
            for i in row['instances']:
                x1,y1,x2,y2=i['bbox'];boxes.append([(x1+x2)/2/w,(y1+y2)/2/h,(x2-x1)/w,(y2-y1)/h])
            self.labels.append({'im_file':str(self.root/row['image']), 'shape':(h,w),
                'cls':np.array([[i['class_id']] for i in row['instances']],np.float32),
                'bboxes':np.array(boxes,np.float32).reshape(-1,4), 'segments':[],
                'normalized':True,'bbox_format':'xywh'})

    def __len__(self):return len(self.rows)

    def close_mosaic(self,hyp):self.mosaic=False

    def __getitem__(self,index):
        row=self.rows[index];size=self.imgsz
        image=cv2.imread(str(self.root/row['image']));h,w=image.shape[:2]
        mask=cv2.imread(str(self.root/row['mask']),cv2.IMREAD_UNCHANGED)
        if mask is not None and mask.ndim==3 and mask.shape[2]==1:mask=mask[:,:,0]
        if mask is None or mask.shape!=(h,w):raise ValueError('Missing/misaligned exact mask')
        scale=min(size/w,size/h);nw,nh=round(w*scale),round(h*scale)
        left,top=(size-nw)//2,(size-nh)//2
        canvas=np.full((size,size,3),114,np.uint8)
        # Match Ultralytics LetterBox used by prediction. INTER_AREA on enlarged
        # crops produces different pixels despite identical geometry/normalization.
        canvas[top:top+nh,left:left+nw]=cv2.resize(image,(nw,nh),interpolation=cv2.INTER_LINEAR)
        mask_canvas=np.zeros((size,size),np.uint16)
        mask_canvas[top:top+nh,left:left+nw]=cv2.resize(mask,(nw,nh),interpolation=cv2.INTER_NEAREST)
        boxes=[]
        for item in row['instances']:
            x1,y1,x2,y2=item['bbox']
            boxes.append([((x1+x2)*scale/2+left)/size,((y1+y2)*scale/2+top)/size,
                          (x2-x1)*scale/size,(y2-y1)*scale/size])
        boxes=np.array(boxes,np.float32).reshape(-1,4)
        flipped=False
        if self.augment:
            if random.random()<.5:
                flipped=True
                canvas=canvas[:,::-1].copy();mask_canvas=mask_canvas[:,::-1].copy();boxes[:,0]=1-boxes[:,0]
            canvas=np.clip(canvas.astype(float)*random.uniform(.9,1.1),0,255).astype(np.uint8)
        small=cv2.resize(mask_canvas,(size//self.ratio,size//self.ratio),interpolation=cv2.INTER_NEAREST)
        masks=np.stack([small==item['mask_id'] for item in row['instances']]).astype(np.uint8)
        if self.supervision_policy=='any_coverage':
            masks=coverage_masks(mask,row['instances'],size,self.ratio,flipped)
        semantic=np.zeros(small.shape,np.float32)
        for item in row['instances']:semantic[small==item['mask_id']]=item['class_id']
        if self.supervision_policy=='any_coverage':
            # Auxiliary semantic head accepts one class per coarse cell. Lowest
            # stable palette ID wins ties; instance masks retain both targets.
            for i in sorted(range(len(row['instances'])),key=lambda i:row['instances'][i]['mask_id'],reverse=True):
                semantic[masks[i].astype(bool)]=row['instances'][i]['class_id']
        return dict(img=torch.from_numpy(canvas[:,:,::-1].transpose(2,0,1).copy()),
            cls=torch.tensor([[i['class_id']] for i in row['instances']],dtype=torch.float32),
            bboxes=torch.from_numpy(boxes),masks=torch.from_numpy(masks),
            sem_masks=torch.from_numpy(semantic),
            batch_idx=torch.zeros(len(boxes)),im_file=str(self.root/row['image']),
            ori_shape=(h,w),resized_shape=(size,size),ratio_pad=((scale,scale),(left,top)))


class RasterValidator(SegmentationValidator):
    def build_dataset(self,img_path,mode='val',batch=None):
        return RasterDataset(self.data['path'],'val',self.args.imgsz,False,self.args.mask_ratio)


class RasterTrainer(SegmentationTrainer):
    def build_dataset(self,img_path,mode='train',batch=None):
        return RasterDataset(self.data['path'],mode,self.args.imgsz,mode=='train',self.args.mask_ratio)

    def get_validator(self):
        return RasterValidator(self.test_loader,save_dir=self.save_dir,args=copy(self.args),_callbacks=self.callbacks)


class CoverageRasterTrainer(RasterTrainer):
    def build_dataset(self,img_path,mode='train',batch=None):
        return RasterDataset(self.data['path'],mode,self.args.imgsz,mode=='train',self.args.mask_ratio,
                             'any_coverage' if mode=='train' else 'legacy_nearest')


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--dataset',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--epochs',type=int,default=60);p.add_argument('--size',type=int,default=960)
    p.add_argument('--batch',type=int,default=2);p.add_argument('--technical',action='store_true')
    p.add_argument('--mask-ratio',type=int,choices=[1,2,4],default=4)
    p.add_argument('--supervision-policy',choices=['legacy_nearest','any_coverage'],default='legacy_nearest')
    p.add_argument('--weights',type=Path,help='Explicit initialization; defaults to the historical generic checkpoint')
    p.add_argument('--nominal-batch-size',type=int,help='Gradient accumulation reference; technical pilots default to actual batch')
    p.add_argument('--warmup-epochs',type=float,help='Technical pilots default to zero; historical main protocol uses three')
    p.add_argument('--no-amp',action='store_true',help='Disable mixed precision for controlled diagnostics')
    a=p.parse_args();a.root=a.root.resolve();a.dataset=a.dataset.resolve();a.output=a.output.resolve();check_deadline(a.root)
    contract=json.loads((a.dataset/'dataset_contract.json').read_text())
    if not contract['training_eligible'] and not a.technical:raise ValueError('Dataset quality gate not passed')
    if not a.technical:
        if a.mask_ratio!=4 or a.supervision_policy!='legacy_nearest':
            raise ValueError('Experimental supervision requires --technical')
        budget=json.loads((a.root/'common_optimization_budget.json').read_text())
        if (a.epochs,a.size,a.batch)!=(budget['epochs'],budget['image_size'],budget['batch']):
            raise ValueError('Main run differs from frozen common optimization budget')
    if a.output.exists():raise FileExistsError(a.output)
    weights=a.weights.resolve() if a.weights else a.root/'yolo26n-seg.pt'
    nominal_batch=a.nominal_batch_size if a.nominal_batch_size is not None else (a.batch if a.technical else 64)
    warmup=a.warmup_epochs if a.warmup_epochs is not None else (0 if a.technical else 3)
    if nominal_batch<1:raise ValueError('Nominal batch size must be positive')
    if warmup<0:raise ValueError('Warmup cannot be negative')
    if not a.technical and (nominal_batch!=64 or warmup!=3 or a.weights or a.no_amp):
        raise ValueError('Initialization/optimizer overrides require a versioned technical run')
    torch.set_num_threads(2)
    model=YOLO(weights)
    optimizer_counts={'executed':0}
    def count_step(optimizer,args,kwargs):optimizer_counts['executed']+=1
    def instrument_optimizer(trainer):trainer.optimizer.register_step_post_hook(count_step)
    model.add_callback('on_train_start',instrument_optimizer)
    def snapshot_parameters(trainer):
        trainer._audit_before = {n: p.detach().clone() for n, p in trainer.model.named_parameters() if p.requires_grad}
        trainer._audit_steps_before = optimizer_counts['executed']
    def verify_parameters(trainer):
        changes = [float((p.detach().float()-trainer._audit_before[n].float()).abs().max())
                   for n,p in trainer.model.named_parameters() if n in trainer._audit_before]
        record = dict(epoch=trainer.epoch+1, optimizer_steps_executed=optimizer_counts['executed'],
                      epoch_optimizer_steps=optimizer_counts['executed']-trainer._audit_steps_before,
                      changed_parameter_tensors=sum(x>0 for x in changes), maximum_absolute_update=max(changes))
        with (trainer.save_dir/'parameter_updates.jsonl').open('a') as stream:
            stream.write(json.dumps(record)+'\n')
        del trainer._audit_before
    model.add_callback('on_train_epoch_start',snapshot_parameters)
    model.add_callback('on_train_epoch_end',verify_parameters)
    def deadline(trainer):check_deadline(a.root)
    model.add_callback('on_train_epoch_start',deadline)
    started=time.perf_counter()
    trainer_class=CoverageRasterTrainer if a.supervision_policy=='any_coverage' else RasterTrainer
    result=model.train(trainer=trainer_class,data=str(a.dataset/'dataset.yaml'),epochs=a.epochs,
        imgsz=a.size,batch=a.batch,nbs=nominal_batch,warmup_epochs=warmup,device=0,workers=0,amp=not a.no_amp,optimizer='AdamW',lr0=.001,
        seed=20261002,deterministic=True,patience=0,project=str(a.output.parent),name=a.output.name,
        exist_ok=False,plots=True,mosaic=0,mixup=0,copy_paste=0,hsv_h=0,hsv_s=0,hsv_v=.1,
        overlap_mask=False,mask_ratio=a.mask_ratio,cache=False,close_mosaic=0,save=True)
    f1=np.asarray(result.seg.f1_curve) if result is not None and hasattr(result.seg,'f1_curve') else np.zeros((0,0))
    threshold=float(result.seg.px[f1.mean(0).argmax()]) if f1.size and f1.max()>0 else .25
    write(a.output/'experiment.json',dict(script_version=VERSION,seed=20261002,
        parameter_preset='synthetic_raster_yolo26n_seg',technical_only=a.technical,
        seconds=time.perf_counter()-started,initialization_sha256=sha(weights),initialization_path=str(weights),
        nominal_batch_size=nominal_batch,warmup_epochs=warmup,optimizer_steps_executed=optimizer_counts['executed'],
        epochs_requested=a.epochs,epochs_completed=int(model.trainer.epoch)+1,
        image_size=a.size,batch_requested=a.batch,amp_active=bool(model.trainer.amp),
        mask_ratio=a.mask_ratio,supervision_policy=a.supervision_policy,
        rgb_preprocessing='raster-rgb/2.0: RGB uint8, centered square 114, INTER_LINEAR, then /255',
        validation_supervision_policy='legacy_nearest; native-mask external evaluation required',
        dataset_sha256=sha(a.dataset/'raster_manifest.json'),metrics=result.results_dict if result else {},
        operating_confidence=threshold,threshold_source='synthetic_validation_mask_macro_f1_or_zero_signal_default_0_25',
        label_source='exact_visible_instance_rasters',
        general_pretraining='COCO' if not a.weights else 'inherited checkpoint; see initialization provenance',
        uchuva_training='synthetic_only'))


if __name__=='__main__':main()
