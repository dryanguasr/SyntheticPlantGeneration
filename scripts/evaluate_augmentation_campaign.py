"""Frozen development evaluation with paired group bootstrap; no model selection on test."""
from __future__ import annotations
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace
import time
import numpy as np
import torch
from PIL import Image
from ultralytics import YOLO
from ultralytics.engine.validator import BaseValidator
from ultralytics.utils.metrics import ap_per_class, box_iou
from augmentation_pilot import ROOT, REPO, read, write, sha, boxes
from evaluate_union_detector import fixed_match


def stats(gt,pred,collapsed=False):
    g=torch.tensor([r['bbox'] for r in gt],dtype=torch.float32).reshape(-1,4)
    p=torch.tensor([r['bbox'] for r in pred],dtype=torch.float32).reshape(-1,4)
    gc=torch.tensor([0 if collapsed else r['class_id'] for r in gt])
    pc=torch.tensor([0 if collapsed else r['class_id'] for r in pred])
    correct=BaseValidator.match_predictions(SimpleNamespace(iouv=torch.linspace(.5,.95,10)),pc,gc,box_iou(g,p)).numpy()
    return dict(tp=correct.tolist(),conf=[r['confidence'] for r in pred],pred_cls=pc.tolist(),target_cls=gc.tolist())


def ap_summary(records,key='stats'):
    tp=np.concatenate([np.array(r[key]['tp'],dtype=bool).reshape(-1,10) for r in records])
    conf=np.concatenate([r[key]['conf'] for r in records]);pc=np.concatenate([r[key]['pred_cls'] for r in records]);gc=np.concatenate([r[key]['target_cls'] for r in records])
    out=ap_per_class(tp,conf,pc,gc)
    return dict(map50_95=float(out[5].mean()),map50=float(out[5][:,0].mean()),map75=float(out[5][:,5].mean()),
        per_class=[dict(class_id=int(c),map50_95=float(out[5][i].mean()),map50=float(out[5][i,0])) for i,c in enumerate(out[6])])


def evaluate(name,threshold):
    destination=ROOT/'evaluation'/name
    if (destination/'summary.json').exists():return read(destination/'summary.json')
    weight=ROOT/'training'/name/'weights/best.pt';lock=read(ROOT/'evaluation_lock.json')
    assert sha(weight)==lock['weights'][name]
    model=YOLO(weight);records=[];confusion=np.zeros((4,4),int);strata=defaultdict(Counter)
    for row in read(ROOT/'real_manifest.json')['rows']:
        if row['split']!='test':continue
        result=model.predict(row['image'],imgsz=960,conf=.001,iou=.7,max_det=300,device=0,verbose=False)[0]
        h,w=result.orig_shape
        gt=[dict(class_id=int(c),bbox=[(x-bw/2)*w,(y-bh/2)*h,(x+bw/2)*w,(y+bh/2)*h],size=min(bw*w,bh*h)*960/max(w,h)) for c,x,y,bw,bh in boxes(row['label'])]
        pred=[dict(class_id=int(c),confidence=float(s),bbox=b.tolist()) for b,c,s in zip(result.boxes.xyxy.cpu().numpy(),result.boxes.cls.cpu().numpy(),result.boxes.conf.cpu().numpy())]
        fixed=[p for p in pred if p['confidence']>=threshold]
        counts={}
        for key,collapsed in [('class_aware',False),('collapsed',True)]:
            tp,fp,fn=fixed_match(gt,fixed,collapsed);counts[key]=dict(tp=tp.tolist(),fp=fp.tolist(),fn=fn.tolist())
        g=torch.tensor([x['bbox'] for x in gt]).reshape(-1,4);p=torch.tensor([x['bbox'] for x in fixed]).reshape(-1,4)
        ious=box_iou(g,p).numpy();remaining=set(range(len(gt)));matched={}
        for j,prediction in enumerate(fixed):
            value,i=max(((ious[i,j],i) for i in remaining),default=(0,None))
            if value>=.5:
                matched[i]=prediction;remaining.remove(i);confusion[gt[i]['class_id'],prediction['class_id']]+=1
            else:confusion[3,prediction['class_id']]+=1
        for i in remaining:confusion[gt[i]['class_id'],3]+=1
        for i,truth in enumerate(gt):
            size=truth['size'];band='<16' if size<16 else '16-32' if size<32 else '32-64' if size<64 else '>=64'
            density='1-7' if len(gt)<=7 else '8-22' if len(gt)<=22 else '>22'
            for key in ['size:'+band,'density:'+density]:
                strata[key]['truth']+=1;strata[key]['localized']+=i in matched
                strata[key]['correct_class']+=i in matched and matched[i]['class_id']==truth['class_id']
        records.append(dict(source_row=row['source_row'],group=row['group_id'],truth=gt,predictions=pred,
            stats=stats(gt,pred),collapsed_stats=stats(gt,pred,True),fixed=counts))
    summary=dict(ap=ap_summary(records),collapsed_ap=ap_summary(records,'collapsed_stats'),threshold=threshold,
                 confusion_rows_truth_columns_pred_background_last=confusion.tolist(),strata=dict(strata),fixed={})
    for key in ['class_aware','collapsed']:
        total={k:np.sum([r['fixed'][key][k] for r in records],axis=0) for k in ['tp','fp','fn']}
        tp,fp,fn=total['tp'],total['fp'],total['fn']
        summary['fixed'][key]=dict(**{k:v.tolist() for k,v in total.items()},
            precision=float(tp.sum()/max(1,(tp+fp).sum())),recall=float(tp.sum()/max(1,(tp+fn).sum())))
    write(destination/'predictions.json',records);write(destination/'summary.json',summary)
    return summary


def main():
    torch.set_num_threads(4);lock=read(ROOT/'evaluation_lock.json');runs=lock['runs']
    if not runs:raise RuntimeError('No completed final comparisons')
    threshold_path=ROOT/'evaluation_threshold.json'
    if not threshold_path.exists():
        baseline=next(n for n in runs if n.startswith('final_r100_s0_c0_'))
        config=read(ROOT/'training'/baseline/'completion.json')['config']
        val=YOLO(ROOT/'training'/baseline/'weights/best.pt').val(data=config['dataset'],split='val',imgsz=960,batch=2,
            device=0,workers=0,conf=.001,iou=.7,max_det=300,plots=False,project=str(ROOT/'evaluation'),name='threshold_validation')
        curve=np.asarray(val.box.f1_curve);threshold=float(val.box.px[np.argmax(curve.mean(0))])
        write(threshold_path,dict(value=threshold,source=baseline,split='val',test_used=False))
    threshold=read(threshold_path)['value'];summaries={}
    for name in runs:
        summaries[name]=evaluate(name,threshold)
    write(ROOT/'evaluation/summary.json',summaries)
    # Paired resampling uses the same acquisition components and indices for both runs.
    comparisons=[]
    for name in runs:
        cfg=read(ROOT/'training'/name/'completion.json')['config']
        baseline=f"final_r{cfg['real_fraction']}_s0_c0_{cfg['seed']}"
        if baseline==name or baseline not in runs:continue
        a=read(ROOT/'evaluation'/name/'predictions.json');b=read(ROOT/'evaluation'/baseline/'predictions.json')
        groups=sorted({r['group'] for r in a});ga={g:[r for r in a if r['group']==g] for g in groups};gb={g:[r for r in b if r['group']==g] for g in groups}
        rng=np.random.default_rng(20261022);deltas=[]
        for _ in range(200):
            sampled=rng.choice(groups,len(groups),replace=True)
            aa=[r for g in sampled for r in ga[g]];bb=[r for g in sampled for r in gb[g]]
            deltas.append(ap_summary(aa)['map50_95']-ap_summary(bb)['map50_95'])
        comparisons.append(dict(run=name,baseline=baseline,delta=summaries[name]['ap']['map50_95']-summaries[baseline]['ap']['map50_95'],
            group_bootstrap_95=np.quantile(deltas,[.025,.975]).tolist(),groups=len(groups),replicates=200,
            limitation='Grouping is conservative but session independence is not verified; exploratory interval, not confirmatory significance'))
    write(ROOT/'evaluation/paired_bootstrap.json',comparisons)
    from report_augmentation_campaign import report
    report()
    write(ROOT/'state.json',dict(stage='complete',complete=True,finished=time.time(),runs=len(runs)))


if __name__=='__main__':main()
