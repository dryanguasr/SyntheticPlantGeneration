"""Post-hoc paired Sobremadura diagnosis from frozen predictions, no training."""
from pathlib import Path
from collections import Counter,defaultdict
import argparse,math,statistics,time
import numpy as np
from appearance_campaign import read,write,sha,require,SEEDS,NAMES,verify_sources

ARMS=('real_classical','synthetic115_classical')


def iou(a,b):
    x=max(0,min(a[2],b[2])-max(a[0],b[0]));y=max(0,min(a[3],b[3])-max(a[1],b[1]))
    return x*y/max(1e-12,(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-x*y)


def error_type(pred,truth):
    """Disjoint FP geometry relative to annotations; not biological certainty."""
    same=max((iou(pred['bbox'],t['bbox']) for t in truth if t['class_id']==2),default=0)
    other=max((iou(pred['bbox'],t['bbox']) for t in truth if t['class_id']!=2),default=0)
    if same>=.5:return 'duplicate_or_assignment'
    if other>=.5:return 'other_annotated_class'
    if max(same,other)>=.1:return 'localization_IoU_0.1_to_0.5'
    return 'background_or_unannotated'


def inspect_row(row,threshold):
    gt=row['truth'];remaining={i for i,t in enumerate(gt) if t['class_id']==2}
    assigned={};fps=[];kept=[(i,p) for i,p in enumerate(row['predictions']) if p['class_id']==2 and p['confidence']>=threshold]
    for index,p in sorted(kept,key=lambda v:-v[1]['confidence']):
        overlap,j=max(((iou(p['bbox'],gt[j]['bbox']),j) for j in remaining),default=(0,None))
        if overlap>=.5:assigned[j]=dict(prediction_index=index,iou=overlap,confidence=p['confidence']);remaining.remove(j)
        else:fps.append(dict(prediction_index=index,kind=error_type(p,gt),prediction=p))
    outcomes={}
    for j,t in enumerate(gt):
        if t['class_id']!=2:continue
        if j in assigned:outcomes[j]=dict(status='correct',**assigned[j]);continue
        candidates=[(iou(p['bbox'],t['bbox']),i,p) for i,p in enumerate(row['predictions']) if p['confidence']>=threshold]
        overlap,index,p=max(candidates,key=lambda v:v[0],default=(0,None,None))
        low=max((p['confidence'] for p in row['predictions'] if p['class_id']==2 and iou(p['bbox'],t['bbox'])>=.5),default=0)
        if overlap>=.5:status='confusion_to_'+NAMES[p['class_id']]
        elif low>0:status='correct_class_below_fixed_threshold'
        elif overlap>=.1:status='poor_localization'
        else:status='no_localized_prediction'
        outcomes[j]=dict(status=status,best_IoU=overlap,best_prediction_index=index,best_class=p['class_id'] if p else None,
            best_class2_overlap_score=low)
    return dict(tp=len(assigned),fp=len(fps),fn=len(remaining),fp_types=dict(Counter(x['kind'] for x in fps)),
        false_positives=fps,outcomes=outcomes)


def arrays(rows):
    tp=[];conf=[];labels=0
    for r in rows:
        s=r['stats'];mask=np.asarray(s['pred_cls'])==2
        tp.extend(np.asarray(s['tp'],bool).reshape(-1,10)[mask].tolist())
        conf.extend(np.asarray(s['conf'])[mask].tolist());labels+=s['target_cls'].count(2)
    return np.asarray(tp,bool).reshape(-1,10),np.asarray(conf,float),labels


def ap2(values):
    from ultralytics.utils.metrics import ap_per_class
    tp,conf,n=values
    require(n>0,'No Sobremadura truth: do not assign zero AP')
    result=ap_per_class(tp,conf,np.full(len(conf),2),np.full(n,2))
    return result


def native_class_exposure(root):
    """Reconstruct identity geometric filtering and check against actual logs."""
    from PIL import Image
    from ultralytics.utils.instance import Instances
    from ultralytics.data.augment import RandomPerspective
    manifest=read(root/'datasets/paired_slots115/manifest.json');counts={};raw=defaultdict(Counter);sizes=defaultdict(list)
    for r in manifest['entries']:
        if r['split']!='train':continue
        a=np.asarray([list(map(float,line.split())) for line in Path(r['label']).read_text().splitlines()],dtype=np.float32).reshape(-1,5)
        with Image.open(r['image']) as im:w,h=im.size
        scale=960/max(w,h);rw,rh=min(math.ceil(w*scale),960),min(math.ceil(h*scale),960)
        # LetterBox converts normalized xywh to xyxy before denormalizing.
        instances=Instances(a[:,1:].copy(),np.zeros((0,1000,2),np.float32),bbox_format='xywh',normalized=True)
        instances.convert_bbox('xyxy');instances.denormalize(rw,rh)
        instances.add_padding(round((960-rw)/2-.1),round((960-rh)/2-.1))
        boxes=instances.bboxes;keep=RandomPerspective.box_candidates(boxes.T,boxes.T)
        c=Counter(map(int,a[keep,0]));counts[r['source_id']]=c;raw[r['domain']].update(map(int,a[:,0]))
        for cid,x,y,bw,bh in a:sizes[(r['domain'],int(cid))].append(min(bw*w,bh*h)*scale)
    output=[]
    for config in read(root/'plan.json')['configs']:
        folder=root/'training'/config['name'];totals=defaultdict(Counter)
        for epoch in read(folder/'sampling_sequences.json'):
            for name in epoch['actual_source_ids']:totals['real' if name.startswith('row_') else 'synthetic'].update(counts[name])
        actual=read(folder/'completion.json')['instance_exposure']
        matched=all(sum(totals[domain].values())==n for domain,n in actual.items())
        output.append(dict(name=config['name'],classes_by_domain=dict(totals),exact_domain_total_match=matched,
            actual_domain_totals=actual,reconstructed_domain_totals={k:sum(v.values()) for k,v in totals.items()}))
    return dict(raw_training_class_counts=dict(raw),identity_filter_reconstructed_runs=output,
        reconstruction_is_exact=all(x['exact_domain_total_match'] for x in output),
        raw_class2_size_median={domain:float(np.median(sizes[(domain,2)])) for domain in ('real','synthetic')})


def run(root,out):
    started=time.time();root=root.resolve();out=out.resolve();out.mkdir(parents=True,exist_ok=True)
    verify_sources(root)
    from daylight_augmentation_pilot import generation_paused
    generation_paused(root)
    threshold=read(root/'evaluation_threshold.json')['value'];summary=read(root/'evaluation/summary.json')
    records={};all_checks=[];row_results={};transitions=Counter();regressions=defaultdict(list);fp_candidates=[]
    curves={};metrics=[]
    for seed in SEEDS:
        for arm in ARMS:
            name=f'final_{arm}_{seed}';file=root/'evaluation'/name/'predictions.json'
            require(sha(file)==summary[name]['predictions_sha256'],'Prediction cache changed')
            rows=read(file);records[name]=rows;result=ap2(arrays(rows));curves[name]=result
            expected=next(c['map50_95'] for c in summary[name]['ap']['per_class'] if c['class_id']==2)
            require(abs(float(result[5].mean())-expected)<1e-12,'Cached AP reproduction mismatch')
            inspected=[inspect_row(r,threshold) for r in rows];row_results[name]=inspected
            totals=Counter();types=Counter();outcomes=Counter()
            for v in inspected:
                totals.update({k:v[k] for k in ('tp','fp','fn')});types.update(v['fp_types']);outcomes.update(vv['status'] for vv in v['outcomes'].values())
            original=summary[name]['fixed']['class_aware']
            require(all(totals[k]==original[k][2] for k in totals),'Fixed match reproduction mismatch')
            confidence_bands={}
            for cutoff in (.001,threshold,.25,.5):
                cc=Counter();tt=Counter()
                for r in rows:
                    v=inspect_row(r,cutoff);cc.update({k:v[k] for k in ('tp','fp','fn')});tt.update(v['fp_types'])
                confidence_bands[str(cutoff)]=dict(counts=dict(cc),fp_types=dict(tt))
            metrics.append(dict(name=name,seed=seed,arm=arm,AP_by_IoU=result[5][0].tolist(),fixed=dict(totals),
                fixed_fp_types=dict(types),gt_outcomes=dict(outcomes),sensitivity_no_threshold_selection=confidence_bands))
        real=f'final_{ARMS[0]}_{seed}';mixed=f'final_{ARMS[1]}_{seed}'
        for ri,(a,b) in enumerate(zip(row_results[real],row_results[mixed])):
            for ti,old in a['outcomes'].items():
                new=b['outcomes'][ti];transitions[old['status']+' -> '+new['status']]+=1
                if old['status']=='correct' and new['status']!='correct':
                    regressions[(ri,ti)].append(dict(seed=seed,old=old,new=new))
            for fp in b['false_positives']:
                p=fp['prediction'];same_real=max((q['confidence'] for q in records[real][ri]['predictions']
                    if q['class_id']==2 and iou(q['bbox'],p['bbox'])>=.5),default=0)
                if p['confidence']>=.25 and same_real<threshold:
                    fp_candidates.append(dict(seed=seed,row_index=ri,source_row=records[real][ri]['source_row'],
                        fp=fp,control_same_class_overlap_score=same_real))
    design=read(root/'evaluation/bootstrap_design.json');draw_values=[]
    groups={n:{g:arrays([r for r in rows if r['group']==g]) for g in design['groups']} for n,rows in records.items()}
    def merge(name,draw):
        values=[groups[name][g] for g in draw]
        return np.concatenate([a[0] for a in values]),np.concatenate([a[1] for a in values]),sum(a[2] for a in values)
    for draw in design['draws']:
        diffs=[float(ap2(merge(f'final_{ARMS[1]}_{s}',draw))[5].mean()-ap2(merge(f'final_{ARMS[0]}_{s}',draw))[5].mean()) for s in SEEDS]
        draw_values.append(statistics.mean(diffs))
    loo=[]
    for excluded in design['groups']:
        values=[]
        for s in SEEDS:
            a=arrays([r for r in records[f'final_{ARMS[0]}_{s}'] if r['group']!=excluded]);b=arrays([r for r in records[f'final_{ARMS[1]}_{s}'] if r['group']!=excluded])
            values.append(float(ap2(b)[5].mean()-ap2(a)[5].mean()))
        loo.append(dict(excluded_group=excluded,mean_delta=statistics.mean(values),deltas=values))
    ranked=sorted(regressions,key=lambda k:(-len(regressions[k]),records[f'final_{ARMS[0]}_{SEEDS[0]}'][k[0]]['source_row'],k[1]))
    cases=[];used=set()
    for ri,ti in ranked:
        source_row=records[f'final_{ARMS[0]}_{SEEDS[0]}'][ri]['source_row']
        if source_row in used:continue
        used.add(source_row);r=regressions[(ri,ti)][0]
        cases.append(dict(kind='GT_regression',row_index=ri,truth_index=ti,source_row=source_row,
            affected_seeds=regressions[(ri,ti)],seed=r['seed'],bbox=records[f'final_{ARMS[0]}_{r["seed"]}'][ri]['truth'][ti]['bbox']))
        if len(cases)==2:break
    for candidate in sorted(fp_candidates,key=lambda c:(c['fp']['kind']!='other_annotated_class',-c['fp']['prediction']['confidence'])):
        if candidate['source_row'] in used:continue
        cases.append(dict(kind='new_FP_relative_to_labels',**candidate,bbox=candidate['fp']['prediction']['bbox']));break
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from PIL import Image
    fig,axes=plt.subplots(1,2,figsize=(12,4.5))
    for arm,color in zip(ARMS,('steelblue','darkorange')):
        ys=np.asarray([curves[f'final_{arm}_{s}'][-1][0] for s in SEEDS]);aps=np.asarray([curves[f'final_{arm}_{s}'][5][0] for s in SEEDS])
        axes[0].plot(np.linspace(0,1,1000),ys.mean(0),color=color,label=arm)
        axes[0].fill_between(np.linspace(0,1,1000),ys.min(0),ys.max(0),color=color,alpha=.15)
        axes[1].plot(np.linspace(.5,.95,10),aps.mean(0)*100,'o-',color=color,label=arm)
    axes[0].set(xlabel='Recall Sobremadura',ylabel='Precisión interpolada, IoU0,5',ylim=(0,1),title='Media y rango de las tres semillas')
    axes[1].set(xlabel='IoU de evaluación',ylabel='AP Sobremadura (%)',title='¿Ranking o precisión geométrica?');axes[0].legend(fontsize=8)
    fig.tight_layout();fig.savefig(out/'precision_recall.png',dpi=160);plt.close(fig)
    for index,c in enumerate(cases,1):
        fig,axes=plt.subplots(1,2,figsize=(12,5.5));seed=c['seed'];ri=c['row_index']
        for axis,arm in zip(axes,ARMS):
            record=records[f'final_{arm}_{seed}'][ri]
            with Image.open(record['image']) as im:axis.imshow(im.convert('RGB'));w,h=im.size
            a,b,cc,dd=c['bbox'];pad=max(65,(cc-a)*.8,(dd-b)*.8);left,right=max(0,a-pad),min(w,cc+pad);top,bottom=max(0,b-pad),min(h,dd+pad)
            for kind in ('truth','predictions'):
                for item in record[kind]:
                    if kind=='predictions' and item['confidence']<threshold:continue
                    x,y,xx,yy=item['bbox']
                    if xx<left or x>right or yy<top or y>bottom:continue
                    color='lime' if kind=='truth' else 'red' if item['class_id']==2 else 'orange'
                    axis.add_patch(Rectangle((x,y),xx-x,yy-y,fill=False,edgecolor=color,linewidth=1.4))
                    label=NAMES[item['class_id']]+(' GT' if kind=='truth' else f" {item['confidence']:.2f}")
                    axis.text(x,max(top,y),label,color=color,fontsize=8,clip_on=True,bbox=dict(facecolor='black',alpha=.5,pad=.4,edgecolor='none'))
            axis.set_xlim(left,right);axis.set_ylim(bottom,top);axis.axis('off');axis.set_title(f'{arm}\nSemilla{seed} · fila{c["source_row"]}')
        fig.suptitle('Verde: etiqueta · rojo: predicción Sobremadura · naranja: otras clases',fontsize=11)
        fig.tight_layout();fig.savefig(out/f'error_pair_{index}.png',dpi=160);plt.close(fig);c['image']=f'error_pair_{index}.png'
    result=dict(threshold_fixed_from_original_val=threshold,class_id=2,truth_per_seed=58,metrics=metrics,
        truth_transitions_across_three_fixed_seeds=dict(transitions),
        bootstrap_same_original_draws=dict(percentile_95=np.percentile(draw_values,[2.5,97.5]).tolist(),values=draw_values,
            conditioning=design['conditioning'],posthoc=True,no_significance_claim=True),leave_one_group_out=loo,
        cases=cases,case_selection='Error-focused: prioritize regressions repeated across seeds, then first distinct source row; plus new high-score FP. Not representative error frequency.',
        exposure=native_class_exposure(root),no_new_training_or_inference=True,generation_paused=True,
        predictions_hashes={n:summary[n]['predictions_sha256'] for n in records},script_sha256=sha(__file__),wall_seconds=time.time()-started)
    write(out/'diagnosis.json',result)
    print('Saved',out/'diagnosis.json',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    run(a.root,a.out)
