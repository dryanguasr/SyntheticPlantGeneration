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


class RasterDataset(Dataset):
    """Standard trainer batch contract, with masks sourced directly from IDs."""
    collate_fn = staticmethod(YOLODataset.collate_fn)

    def __init__(self, root, split, size, augment=False, ratio=4):
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
        canvas[top:top+nh,left:left+nw]=cv2.resize(image,(nw,nh),interpolation=cv2.INTER_AREA)
        mask_canvas=np.zeros((size,size),np.uint16)
        mask_canvas[top:top+nh,left:left+nw]=cv2.resize(mask,(nw,nh),interpolation=cv2.INTER_NEAREST)
        boxes=[]
        for item in row['instances']:
            x1,y1,x2,y2=item['bbox']
            boxes.append([((x1+x2)*scale/2+left)/size,((y1+y2)*scale/2+top)/size,
                          (x2-x1)*scale/size,(y2-y1)*scale/size])
        boxes=np.array(boxes,np.float32).reshape(-1,4)
        if self.augment:
            if random.random()<.5:
                canvas=canvas[:,::-1].copy();mask_canvas=mask_canvas[:,::-1].copy();boxes[:,0]=1-boxes[:,0]
            canvas=np.clip(canvas.astype(float)*random.uniform(.9,1.1),0,255).astype(np.uint8)
        small=cv2.resize(mask_canvas,(size//self.ratio,size//self.ratio),interpolation=cv2.INTER_NEAREST)
        masks=np.stack([small==item['mask_id'] for item in row['instances']]).astype(np.uint8)
        semantic=np.zeros(small.shape,np.float32)
        for item in row['instances']:semantic[small==item['mask_id']]=item['class_id']
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


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--dataset',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--epochs',type=int,default=60);p.add_argument('--size',type=int,default=960)
    p.add_argument('--batch',type=int,default=2);p.add_argument('--technical',action='store_true')
    a=p.parse_args();a.root=a.root.resolve();a.dataset=a.dataset.resolve();a.output=a.output.resolve();check_deadline(a.root)
    contract=json.loads((a.dataset/'dataset_contract.json').read_text())
    if not contract['training_eligible'] and not a.technical:raise ValueError('Dataset quality gate not passed')
    if not a.technical:
        budget=json.loads((a.root/'common_optimization_budget.json').read_text())
        if (a.epochs,a.size,a.batch)!=(budget['epochs'],budget['image_size'],budget['batch']):
            raise ValueError('Main run differs from frozen common optimization budget')
    if a.output.exists():raise FileExistsError(a.output)
    model=YOLO(a.root/'yolo26n-seg.pt')
    def deadline(trainer):check_deadline(a.root)
    model.add_callback('on_train_epoch_start',deadline)
    started=time.perf_counter()
    result=model.train(trainer=RasterTrainer,data=str(a.dataset/'dataset.yaml'),epochs=a.epochs,
        imgsz=a.size,batch=a.batch,device=0,workers=0,amp=True,optimizer='AdamW',lr0=.001,
        seed=20261002,deterministic=True,patience=0,project=str(a.output.parent),name=a.output.name,
        exist_ok=False,plots=True,mosaic=0,mixup=0,copy_paste=0,hsv_h=0,hsv_s=0,hsv_v=.1,
        overlap_mask=False,mask_ratio=4,cache=False,close_mosaic=0,save=True)
    f1=np.asarray(result.seg.f1_curve) if result is not None and hasattr(result.seg,'f1_curve') else np.zeros((0,0))
    threshold=float(result.seg.px[f1.mean(0).argmax()]) if f1.size and f1.max()>0 else .25
    write(a.output/'experiment.json',dict(script_version=VERSION,seed=20261002,
        parameter_preset='synthetic_raster_yolo26n_seg',technical_only=a.technical,
        seconds=time.perf_counter()-started,initialization_sha256=sha(a.root/'yolo26n-seg.pt'),
        epochs_requested=a.epochs,epochs_completed=int(model.trainer.epoch)+1,
        image_size=a.size,batch_requested=a.batch,amp_active=bool(model.trainer.amp),
        dataset_sha256=sha(a.dataset/'raster_manifest.json'),metrics=result.results_dict if result else {},
        operating_confidence=threshold,threshold_source='synthetic_validation_mask_macro_f1_or_zero_signal_default_0_25',
        label_source='exact_visible_instance_rasters',general_pretraining='COCO',uchuva_training='synthetic_only'))


if __name__=='__main__':main()
