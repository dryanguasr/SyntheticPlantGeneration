"""Freeze validation selection, then measure grouped test and matched comparisons."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import torch
from ultralytics import YOLO
from prepare_union_pilot import ROOT, sha, write
from evaluate_union_videos import iou


def metrics_dict(result):
    box=result.box
    return {'map50_95':float(box.map),'map50':float(box.map50),'map75':float(box.map75),
            'per_class':[{'class_id':int(cid),'ap50_95':float(box.all_ap[j].mean()),'ap50':float(box.all_ap[j,0]),
                          'ap75':float(box.all_ap[j,5])} for j,cid in enumerate(box.ap_class_index)],
            'ultralytics_results':{k:float(v) for k,v in result.results_dict.items()}}


def fixed_match(ground_truth,predictions,agnostic=False):
    """Confidence-ordered one-to-one IoU matches, no test threshold selection."""
    remaining=set(range(len(ground_truth)));tp=np.zeros(3,int);fp=np.zeros(3,int)
    for pred in sorted(predictions,key=lambda p:p['confidence'],reverse=True):
        cid=0 if agnostic else pred['class_id']
        candidates=[(iou(np.asarray(pred['bbox']),np.asarray(ground_truth[j]['bbox'])),j) for j in remaining
                    if agnostic or pred['class_id']==ground_truth[j]['class_id']]
        best=max(candidates,default=(0,None))
        if best[0]>=.5:
            tp[cid]+=1;remaining.remove(best[1])
        else:fp[cid]+=1
    fn=np.zeros(3,int)
    for j in remaining:fn[0 if agnostic else ground_truth[j]['class_id']]+=1
    return tp,fp,fn


def fixed_evaluation(model,threshold,arm):
    manifest=json.loads((ROOT/'manifest.json').read_text())['records']
    records=[r for r in manifest if r['status']=='included' and r['split']=='test']
    totals={key:[np.zeros(3,int) for _ in range(3)] for key in ['class_aware','class_collapsed']}
    confusion=np.zeros((4,4),int); predictions_out=[]
    for row in records:
        pred=model.predict(str(ROOT/row['image']),imgsz=960,conf=threshold,iou=.7,max_det=300,device=0,verbose=False)[0]
        h,w=pred.orig_shape;gt=[]
        for line in (ROOT/row['label']).read_text().splitlines():
            cid,x,y,bw,bh=map(float,line.split())
            gt.append({'class_id':int(cid),'bbox':[(x-bw/2)*w,(y-bh/2)*h,(x+bw/2)*w,(y+bh/2)*h]})
        predictions=[{'class_id':int(c),'confidence':float(s),'bbox':b.tolist()} for b,c,s in zip(
            pred.boxes.xyxy.cpu().numpy(),pred.boxes.cls.cpu().numpy(),pred.boxes.conf.cpu().numpy())]
        for key,agnostic in [('class_aware',False),('class_collapsed',True)]:
            counts=fixed_match(gt,predictions,agnostic)
            for j in range(3):totals[key][j]+=counts[j]
        remaining=set(range(len(gt)))
        for prediction in sorted(predictions,key=lambda x:x['confidence'],reverse=True):
            best=max(((iou(np.asarray(prediction['bbox']),np.asarray(gt[j]['bbox'])),j) for j in remaining),default=(0,None))
            if best[0]>=.5:
                confusion[gt[best[1]]['class_id'],prediction['class_id']]+=1;remaining.remove(best[1])
            else:confusion[3,prediction['class_id']]+=1
        for j in remaining:confusion[gt[j]['class_id'],3]+=1
        predictions_out.append({'source_row':row['source_row'],'image':row['image'],'predictions':predictions})
    result={'confidence':threshold,'matching_iou':.5,'images':len(records),'confusion_rows_truth_cols_pred_background_last':confusion.tolist()}
    for key,(tp,fp,fn) in totals.items():
        precision=np.divide(tp,tp+fp,out=np.zeros(3,float),where=tp+fp>0)
        recall=np.divide(tp,tp+fn,out=np.zeros(3,float),where=tp+fn>0)
        result[key]={'tp':tp.tolist(),'fp':fp.tolist(),'fn':fn.tolist(),'precision':precision.tolist(),'recall':recall.tolist(),
                     'micro_precision':float(tp.sum()/max(1,(tp+fp).sum())), 'micro_recall':float(tp.sum()/max(1,(tp+fn).sum()))}
    write(ROOT/'evaluation'/arm/'test_predictions.json',predictions_out)
    write(ROOT/'evaluation'/arm/'test_fixed_threshold.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arms',nargs='+',default=['real'])
    args=parser.parse_args()
    torch.set_num_threads(4)
    data=str((ROOT/'dataset/data.yaml').resolve())
    selected={}
    for arm in args.arms:
        complete=json.loads((ROOT/'training'/arm/'completion.json').read_text())
        assert complete['completed'] and complete['optimizer_steps']>0
        weight=ROOT/'training'/arm/'weights/best.pt'
        assert sha(weight)==complete['best_sha256']
        model=YOLO(weight)
        val=model.val(data=data,split='val',imgsz=960,batch=2,device=0,workers=0,conf=.001,iou=.7,
                      max_det=300,plots=False,project=str((ROOT/'evaluation'/arm).resolve()),name='validation')
        dataset_manifest = ROOT/'manifest.json' if arm == 'real' else ROOT/'mixed_dataset/manifest.json'
        selected[arm]={'weights_sha256':sha(weight),'validation':metrics_dict(val),'optimizer_steps':complete['optimizer_steps'],
                       'training_config_sha256':sha(ROOT/f'{arm}_training_config.json'),
                       'dataset_manifest_sha256':sha(dataset_manifest)}
        if arm=='real':
            curve=np.asarray(val.box.f1_curve)
            threshold=float(val.box.px[np.argmax(curve.mean(0))]) if curve.size else .25
        write(ROOT/'evaluation'/arm/'validation_summary.json',selected[arm])
    if 'real' not in selected:raise ValueError('Real validation defines the common threshold')
    lock={'created_at_utc':datetime.now(timezone.utc).isoformat(),'confidence':threshold,
          'confidence_source':'argmax real validation mean class F1; common for both arms',
          'arms':selected,'protocol_sha256':sha(ROOT/'protocol.json'), 'imgsz':960,'nms_iou':.7,
          'detector_evaluation_script_sha256':sha(__file__),
          'video_evaluation_script_sha256':sha(Path(__file__).with_name('evaluate_union_videos.py')),
          'test_used_for_selection':False,'videos_used_for_selection':False}
    if (ROOT/'evaluation_lock.json').exists():raise FileExistsError('Evaluation already locked')
    write(ROOT/'evaluation_lock.json',lock)
    summaries={}
    for arm in args.arms:
        weight=ROOT/'training'/arm/'weights/best.pt';model=YOLO(weight)
        test=model.val(data=data,split='test',imgsz=960,batch=2,device=0,workers=0,conf=.001,iou=.7,
                       max_det=300,plots=False,project=str((ROOT/'evaluation'/arm).resolve()),name='test_ap')
        summary={'test':metrics_dict(test),'fixed_threshold':fixed_evaluation(model,threshold,arm)}
        collapsed=YOLO(weight).val(data=data,split='test',single_cls=True,imgsz=960,batch=2,device=0,workers=0,
                                  conf=.001,iou=.7,max_det=300,plots=False,project=str((ROOT/'evaluation'/arm).resolve()),name='test_collapsed')
        summary['test_class_collapsed']=metrics_dict(collapsed)
        summaries[arm]=summary;write(ROOT/'evaluation'/arm/'summary.json',summary)
    if 'mixed' in summaries:
        summaries['comparison']={'equal_optimizer_steps':selected['real']['optimizer_steps']==selected['mixed']['optimizer_steps'],
                                 'delta_map50_95':summaries['mixed']['test']['map50_95']-summaries['real']['test']['map50_95'],
                                 'selection_rule':'no post-test retuning; report both arms including negative result',
                                 'single_training_seed':True}
    write(ROOT/'evaluation/summary.json',summaries)


if __name__=='__main__':main()
