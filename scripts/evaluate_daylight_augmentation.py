"""Freeze-paired real development evaluation, descriptive bootstrap and plots."""
from pathlib import Path
import argparse,contextlib,csv,statistics,time
import numpy as np
import torch
from ultralytics import YOLO
from appearance_campaign import read,write,sha,require,verify_sources,charged_job,process_identity,SEEDS,NAMES
from evaluate_appearance_campaign import evaluate_run,checked_groups,three_class_ap,mean_sd
from daylight_augmentation_pilot import generation_paused,completed


def plots(root,predictions,threshold):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from PIL import Image
    out=root/'evaluation';fig,axes=plt.subplots(1,2,figsize=(12,4.5))
    for config in read(root/'plan.json')['configs']:
        name=config['name'];rows=list(csv.DictReader((root/'training'/name/'results.csv').open()))
        for axis,key in zip(axes,('metrics/mAP50-95(B)','train/box_loss')):
            values=[float({k.strip():v for k,v in row.items()}[key]) for row in rows]
            axis.plot(np.arange(1,len(values)+1)*500,values,label=name.replace('final_',''))
            axis.set(xlabel='Actualizaciones efectivas',ylabel=key)
    axes[0].legend(fontsize=7);fig.tight_layout();fig.savefig(out/'curves.png',dpi=150);plt.close(fig)
    first=predictions[f'final_real_classical_{SEEDS[0]}']
    indices=sorted(set([0,len(first)//3,2*len(first)//3,len(first)-1]))
    names=[f'final_{arm}_{SEEDS[0]}' for arm in ('real_classical','synthetic115_classical')]
    fig,axes=plt.subplots(len(indices),2,figsize=(14,4*len(indices)),squeeze=False)
    for i,index in enumerate(indices):
        for j,name in enumerate(names):
            record=predictions[name][index];axis=axes[i,j]
            with Image.open(record['image']) as im:axis.imshow(im.convert('RGB'))
            for item in record['truth']:
                x,y,xx,yy=item['bbox'];axis.add_patch(Rectangle((x,y),xx-x,yy-y,fill=False,edgecolor='lime',linewidth=1))
            for item in record['predictions']:
                if item['confidence']<threshold:continue
                x,y,xx,yy=item['bbox'];axis.add_patch(Rectangle((x,y),xx-x,yy-y,fill=False,edgecolor='red',linewidth=1))
                axis.text(x,y,f'{NAMES[item["class_id"]]} {item["confidence"]:.2f}',color='red',fontsize=6)
            axis.set_title(name.replace('final_','')+' · '+str(record['source_row']));axis.axis('off')
    fig.suptitle('Verde: verdad real; rojo: predicción. Muestras fijas por orden, no selección de aciertos')
    fig.tight_layout();fig.savefig(out/'prediction_examples.png',dpi=130);plt.close(fig)


def evaluate(root):
    generation_paused(root);verify_sources(root);torch.set_num_threads(4)
    plan=read(root/'plan.json');lock=read(root/'evaluation_lock.json')
    runs={c['name']:completed(root,c) for c in plan['configs']}
    require(len(runs)==6 and all(runs.values()),'Need all six completed runs before development test')
    require({n:v['best_sha256'] for n,v in runs.items()}==lock['weights'],'Weights changed after freeze')
    threshold_file=root/'evaluation_threshold.json'
    if not threshold_file.exists():
        baseline=f'final_real_classical_{SEEDS[0]}'
        result=YOLO(root/'training'/baseline/'weights/best.pt').val(data=plan['configs'][0]['dataset'],
            split='val',imgsz=960,batch=2,device=0,workers=0,conf=.001,iou=.7,max_det=300,plots=False,
            project=str(root/'evaluation'),name='threshold_validation')
        threshold=float(result.box.px[np.argmax(np.asarray(result.box.f1_curve).mean(0))])
        write(threshold_file,dict(value=threshold,source=baseline,split='val',test_used=False,
            evaluation_lock_sha256=sha(root/'evaluation_lock.json')))
    threshold=read(threshold_file)
    require(not threshold['test_used'] and threshold['evaluation_lock_sha256']==sha(root/'evaluation_lock.json'),'Threshold changed')
    summaries={name:evaluate_run(root,name,threshold['value'],lock) for name in runs}
    write(root/'evaluation/summary.json',summaries)
    predictions={name:read(root/'evaluation'/name/'predictions.json') for name in runs}
    truth=[(r['source_row'],r['truth']) for r in next(iter(predictions.values()))]
    require(all([(r['source_row'],r['truth']) for r in rows]==truth for rows in predictions.values()),'Unpaired test truth')
    design=checked_groups(next(iter(predictions.values())))
    write(root/'evaluation/bootstrap_design.json',design)
    by_seed=[]
    for seed in SEEDS:
        a=f'final_real_classical_{seed}';b=f'final_synthetic115_classical_{seed}'
        by_seed.append(dict(seed=seed,real_classical=summaries[a]['ap'],synthetic_classical=summaries[b]['ap'],
            delta=summaries[b]['ap']['map50_95']-summaries[a]['ap']['map50_95'],
            best_validation_real=runs[a]['best_validation_ap'],best_validation_synthetic=runs[b]['best_validation_ap']))
    grouped={n:{g:[r for r in rows if r['group']==g] for g in design['groups']} for n,rows in predictions.items()}
    samples=[]
    for index,draw in enumerate(design['draws']):
        ds=[]
        for seed in SEEDS:
            vals=[three_class_ap([r for g in draw for r in grouped[f'final_{arm}_{seed}'][g]])['map50_95']
                for arm in ('real_classical','synthetic115_classical')]
            ds.append(vals[1]-vals[0])
        samples.append(statistics.mean(ds))
        if index%20==0:print('Bootstrap',index,'/',len(design['draws']),flush=True)
    per_class={}
    for c in range(3):
        def values(key):return [next(v['map50_95'] for v in row[key]['per_class'] if v['class_id']==c) for row in by_seed]
        a,b=values('real_classical'),values('synthetic_classical')
        per_class[NAMES[c]]=dict(real=mean_sd(a),synthetic=mean_sd(b),paired_delta=mean_sd([y-x for x,y in zip(a,b)]))
    payload=dict(by_seed=by_seed,real=mean_sd([r['real_classical']['map50_95'] for r in by_seed]),
        synthetic=mean_sd([r['synthetic_classical']['map50_95'] for r in by_seed]),
        paired_delta=mean_sd([r['delta'] for r in by_seed]),per_class=per_class,
        paired_group_bootstrap=dict(draws=samples,percentile_95=np.percentile(samples,[2.5,97.5]).tolist(),
            conditioning=design['conditioning'],limitation=design['limitation']),
        test_status='development_previously_consulted',selection_used_test=False,
        generation_paused=True,automatic_expansion=False)
    write(root/'evaluation/comparison.json',payload);plots(root,predictions,threshold['value'])
    lines=['# Piloto revisado: 115 sintéticas + clásica frente a real + clásica','',
        'Se completaron seis entrenamientos nuevos de 4.000 actualizaciones, tres semillas por receta. '
        'Mismos pesos originales, LR y decisiones de aumentación por posición. El control reemplaza las posiciones '
        'sintéticas por repeticiones reales. La generación permanece pausada.','',
        '## Resultados de desarrollo','',
        '| Semilla | Real + clásica AP50–95 | Sintética + clásica AP50–95 | Diferencia |','|---|---:|---:|---:|']
    for r in by_seed:lines.append(f"| {r['seed']} | {r['real_classical']['map50_95']:.4f} | {r['synthetic_classical']['map50_95']:.4f} | {r['delta']:+.4f} |")
    lines+=['',f"Media ± DE real: {payload['real']['mean']:.4f} ± {payload['real']['sd']:.4f}; sintética: {payload['synthetic']['mean']:.4f} ± {payload['synthetic']['sd']:.4f}.",
        f"Diferencia emparejada: {payload['paired_delta']['mean']:+.4f} ± {payload['paired_delta']['sd']:.4f}.",
        f"Intervalo descriptivo bootstrap por grupos, condicionado a tres clases: {payload['paired_group_bootstrap']['percentile_95']}.",'',
        '| Clase | Real AP50–95 media | Sintética media | Diferencia media |','|---|---:|---:|---:|']
    for c,v in per_class.items():lines.append(f"| {c} | {v['real']['mean']:.4f} | {v['synthetic']['mean']:.4f} | {v['paired_delta']['mean']:+.4f} |")
    lines+=['','## Controles y límites','',
        'Checkpoint seleccionado sólo en val real (88). Los seis pesos se congelaron antes de evaluar test (94), '
        'que es de desarrollo por consultas históricas; no es un holdout externo intacto. Bootstrap de 200 sorteos '
        'comunes, con semillas entrenadas fijas y condicionado a presencia de las tres clases. No es prueba confirmatoria.',
        '','Las 115 imágenes contienen las mismas 20 plantas del pool; vistas e instancias repetidas no son '
        'plantas independientes. Se preservaron RGB y anotaciones originales. El filtro de candidatos es el nativo '
        'de Ultralytics 8.4.114 (lado >2px; área relativa conservada, no mínimo absoluto de píxeles). '
        'No se introdujo umbral10px ni se cambió a entrenamiento de segmentación.',
        '','La exposición efectiva de imágenes e instancias de cada brazo está en sus completion.json. '
        'Los controles de secuencias/LR/aumentaciones están junto a cada corrida real. '
        'Los resúmenes incluyen AP por clase/colapsado, precisión/recall, confusión, tamaños y densidad.',
        '','## Inspección pendiente','',
        'Este informe automático requiere inspección de curvas y predicciones antes de recomendar ampliar. '
        'No se inicia generación ni otra dosis automáticamente.','',
        '![Curvas](curves.png)','![Ejemplos](prediction_examples.png)']
    (root/'evaluation/report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    write(root/'evaluation/completion.json',dict(completed=True,runs=6,comparison_sha256=sha(root/'evaluation/comparison.json'),
        report_sha256=sha(root/'evaluation/report.md'),finished_utc=time.time(),pending_technical_review=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--accounting-job');a=p.parse_args()
    if a.accounting_job:
        record=read(a.root/'execution_jobs'/(a.accounting_job+'.json'))
        require(record['state']=='active' and record['phase']=='evaluation' and process_identity(record['identity']['pid'])==record['identity'],'Accounting owner not live')
    manager=contextlib.nullcontext() if a.accounting_job else charged_job(a.root,'evaluation','reviewed115_evaluation')
    with manager:evaluate(a.root.resolve())
