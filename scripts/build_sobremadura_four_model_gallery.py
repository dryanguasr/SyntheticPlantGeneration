"""Read-only gallery of the same94 real photos and four existing model families.

Uses frozen prediction caches only. Never renders plants, trains, infers,
edits source annotations, or turns an unlabelled prediction into ground truth.
"""
from pathlib import Path
from collections import Counter
import argparse, json, math, shutil, sys, time
from PIL import Image

REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'src'),str(REPO/'scripts')]
from appearance_campaign import read,write,sha,verify_sources,SEEDS
from daylight_augmentation_pilot import generation_paused
from diagnose_sobremadura_pilot import iou,inspect_row

CURRENT=REPO/'outputs/daylight_augmentation_115_20261112/pilot'
HISTORY=REPO/'outputs/augmentation_pilot_20261022/synthetic_exploratory_extension'
VERSION='sobremadura-four-model-gallery/1'
MODELS=(
    dict(id='none',title='Sin aumentación',arm='r100_s0_c0',root=HISTORY,historical=True,
         real=461,synthetic=0,classical=False,date='22–26 oct.',detail='461 reales · sin clásica'),
    dict(id='classical',title='Clásica',arm='real_classical',root=CURRENT,historical=False,
         real=461,synthetic=0,classical=True,date='12 nov.',detail='461 reales · repetición emparejada'),
    dict(id='synthetic',title='Sintética',arm='r100_s100_c0',root=HISTORY,historical=True,
         real=461,synthetic=389,classical=False,date='22–26 oct.',detail='461 reales + 389 sintéticas · sin clásica'),
    dict(id='hybrid',title='Híbrida',arm='synthetic115_classical',root=CURRENT,historical=False,
         real=461,synthetic=115,classical=True,date='12 nov.',detail='461 reales + 115 sintéticas nuevas · clásica'),
)


def same_truth(expected,observed):
    if len(expected)!=len(observed):return False
    return all(a['class_id']==b['class_id'] and len(b['bbox'])==4 and
               max(abs(x-y) for x,y in zip(a['bbox'],b['bbox']))<=1e-6
               for a,b in zip(expected,observed))


def presence_status(truth,predictions,threshold):
    labelled=any(t['class_id']==2 for t in truth)
    predicted=any(p['class_id']==2 and p['confidence']>=threshold for p in predictions)
    return ('labelled_and_predicted' if predicted else 'labelled_without_prediction') if labelled else (
        'prediction_without_class2_label' if predicted else 'no_class2_label_or_prediction')


def best_candidates(truth,predictions,threshold):
    """Show competing classes as well as the best class2 score, even below cutoff."""
    overlapping=[(j,p,iou(truth['bbox'],p['bbox'])) for j,p in enumerate(predictions)
                 if iou(truth['bbox'],p['bbox'])>=.5]
    best={}
    for j,p,overlap in overlapping:
        cid=str(p['class_id'])
        if cid not in best or p['confidence']>best[cid]['confidence']:
            best[cid]=dict(class_id=p['class_id'],confidence=p['confidence'],iou=overlap,
                          prediction_index=j,above_threshold=p['confidence']>=threshold)
    return best


def candidate_regions(truth,predictions,threshold):
    result=[]
    for index,p in enumerate(predictions):
        if p['class_id']!=2 or p['confidence']<threshold:continue
        overlap,j=max(((iou(p['bbox'],t['bbox']),j) for j,t in enumerate(truth)),default=(0,None))
        kind=('no_nearby_annotation' if overlap<.1 else 'partial_overlap' if overlap<.5 else 'overlaps_annotation')
        result.append(dict(prediction_index=index,confidence=p['confidence'],bbox=p['bbox'],
            nearest_truth_index=j,nearest_truth_class=truth[j]['class_id'] if j is not None else None,
            max_iou=overlap,kind=kind))
    return result


def build(root):
    root=root.resolve();assert root.is_relative_to((REPO/'outputs').resolve())
    root.mkdir(parents=True,exist_ok=True);started=time.time()
    generation_paused(CURRENT);verify_sources(CURRENT)
    assert read(CURRENT/'technical_review.json')['technical_review_complete']
    inputs={}
    def checked(path,expected=None):
        path=Path(path).resolve();digest=sha(path)
        if expected is not None:assert digest==expected,path
        if str(path) in inputs:assert inputs[str(path)]==digest,path
        inputs[str(path)]=digest
        return read(path)
    manifest=checked(CURRENT/'real_manifest.json')
    checked(CURRENT/'training_source_lock.json')
    checked(REPO/'outputs/spatial_dataset_completion_20261030/pause_requested.json')
    threshold_record=checked(CURRENT/'evaluation_threshold.json');threshold=threshold_record['value']
    history_inputs=checked(HISTORY/'confirmation_evaluation_20261026/inputs.json')
    source_rows=sorted((r for r in manifest['records'] if r['split']=='test'),key=lambda r:r['source_row'])
    assert len(source_rows)==94
    source_by_id={r['source_row']:r for r in source_rows};expected={};rows=[]
    (root/'previews').mkdir(exist_ok=True);(root/'thumbs').mkdir(exist_ok=True);(root/'data').mkdir(exist_ok=True)
    for row in source_rows:
        for kind in ('image','label'):
            path=Path(row[kind]);assert sha(path)==row[kind+'_sha256'];inputs[str(path.resolve())]=row[kind+'_sha256']
        with Image.open(row['image']) as image:
            image=image.convert('RGB');w,h=image.size
            preview=image.copy();preview.thumbnail((1440,1440));preview.save(root/'previews'/f"row_{row['source_row']}.jpg",quality=94)
            thumb=image.copy();thumb.thumbnail((160,160));thumb.save(root/'thumbs'/f"row_{row['source_row']}.jpg",quality=85)
        truth=[]
        for line in Path(row['label']).read_text().splitlines():
            if not line.strip():continue
            c,x,y,bw,bh=map(float,line.split());assert int(c) in (0,1,2)
            truth.append(dict(class_id=int(c),bbox=[(x-bw/2)*w,(y-bh/2)*h,(x+bw/2)*w,(y+bh/2)*h]))
        expected[row['source_row']]=truth
        rows.append(dict(id=row['source_row'],group=row['group_id'],file=row['file'],w=w,h=h,
            truth=truth,gt_sobre=sum(t['class_id']==2 for t in truth),
            image=f"previews/row_{row['source_row']}.jpg",thumb=f"thumbs/row_{row['source_row']}.jpg",
            original=Path(row['image']).as_uri(),source_image_sha256=row['image_sha256'],source_label_sha256=row['label_sha256']))
    assert sum(r['gt_sobre'] for r in rows)==58
    registry=[];counts={}
    for seed in SEEDS:
        seed_data={};counts[str(seed)]={}
        for model in MODELS:
            campaign=model['root'];name=f"final_{model['arm']}_{seed}"
            completion=checked(campaign/'training'/name/'completion.json')
            assert completion['completed'] and completion['steps']==4000
            config=completion['config'];assert config['classical']==model['classical']
            if model['historical']:
                assert config['real_images']==model['real'] and config['synthetic_images']==model['synthetic']
            else:
                assert config['real_only']==(model['id']=='classical')
            lock=checked(campaign/'evaluation_lock.json')
            weight=campaign/'training'/name/'weights/best.pt';digest=sha(weight)
            assert digest==lock['weights'][name]==completion['best_sha256'];inputs[str(weight.resolve())]=digest
            cache=campaign/'evaluation'/name/'predictions.json';summary_file=cache.parent/'summary.json'
            if model['historical']:
                proof=history_inputs[name]
                records=checked(cache,proof['predictions_sha256'])
                summary=checked(summary_file,proof['summary_sha256'])
                assert sha(campaign/'training'/name/'completion.json')==proof['completion_sha256']
                assert digest==proof['best_sha256']
            else:
                summary=checked(summary_file)
                records=checked(cache,summary['predictions_sha256'])
                assert summary['inputs']['weight_sha256']==digest
            assert len(records)==94 and {r['source_row'] for r in records}==set(source_by_id)
            data={};statuses=Counter()
            for record in records:
                rid=record['source_row'];assert record['group']==source_by_id[rid]['group_id']
                assert same_truth(expected[rid],record['truth']),f'Changed truth in {name} row{rid}'
                for pred in record['predictions']:
                    assert pred['class_id'] in (0,1,2) and 0<=pred['confidence']<=1
                    assert len(pred['bbox'])==4 and all(math.isfinite(v) for v in pred['bbox'])
                predictions=record['predictions'];inspection=inspect_row(record,threshold)
                statuses[presence_status(record['truth'],predictions,threshold)]+=1
                data[str(rid)]=dict(predictions=[[*p['bbox'],p['class_id'],p['confidence']] for p in predictions],
                    tp=inspection['tp'],fp=inspection['fp'],fn=inspection['fn'],
                    candidate_regions=candidate_regions(record['truth'],predictions,threshold),
                    candidates={str(i):best_candidates(t,predictions,threshold) for i,t in enumerate(record['truth']) if t['class_id']==2})
            seed_data[model['id']]=data
            counts[str(seed)][model['id']]=dict(statuses)
            registry.append({k:v for k,v in model.items() if k!='root'}|dict(seed=seed,root=str(campaign),
                run=name,steps=4000,weight=str(weight.resolve()),weight_sha256=digest,
                predictions_sha256=sha(cache),summary_sha256=sha(summary_file),
                geometric_waiver_historical=completion['config'].get('exploratory_waiver',False),
                ap_sobre=next(c['map50_95'] for c in summary['ap']['per_class'] if c['class_id']==2)))
        payload='window.MODEL_DATA=window.MODEL_DATA||{};window.MODEL_DATA['+str(seed)+']='+json.dumps(seed_data,separators=(',',':'))+';'
        (root/'data'/f'seed_{seed}.js').write_text(payload,encoding='utf-8')
    diagnosis=checked(CURRENT/'diagnostics/sobremadura/diagnosis.json')
    focus={c['source_row']:c['bbox'] for c in diagnosis['cases']}
    meta=dict(version=VERSION,rows=rows,seeds=list(SEEDS),threshold=threshold,threshold_source=threshold_record,
        models=[{k:v for k,v in m.items() if k not in ('root','arm')} for m in MODELS],
        names=['Pintona','Madura','Sobremadura'],class_colors=['#39bb85','#efaf31','#eb5dbe'],
        comparison_warning='Referencias de octubre + pareja reciente. Bancos, dosis y muestreo distintos: galería descriptiva, no ablación controlada de cuatro tratamientos.',
        annotation_warning='Sin etiqueta Sobre no demuestra ausencia biológica. Las predicciones no se convierten en anotaciones.',
        cases=[dict(row=113,seed=20261023,label='Oscura: compiten Pintona y Sobre',bbox=focus[113]),
               dict(row=183,seed=20261022,label='Seca clara: cae la confianza',bbox=focus[183]),
               dict(row=364,seed=20261024,label='Madura: candidato Sobre',bbox=focus[364])])
    (root/'gallery_data.js').write_text('window.GALLERY='+json.dumps(meta,separators=(',',':'))+';',encoding='utf-8')
    write(root/'model_registry.json',dict(version=VERSION,models=registry,common_threshold=threshold,
        synthetic_means='Real plus synthetic data, without classical transforms; not a model trained exclusively on synthetic images',
        historical_models_do_not_use_new_textures=True,four_way_causal_comparison=False))
    write(root/'gallery_summary.json',dict(version=VERSION,real_test_images=94,images_labelled_sobre=sum(r['gt_sobre']>0 for r in rows),
        labelled_sobre_instances=58,status_counts=counts,models=4,seeds=3,
        cached_prediction_sets=12,new_inference=False,new_training=False,new_plant_renders=False,
        previews_are_resized_review_copies=True,source_RGB_and_labels_unchanged=True,
        generation_paused=True,build_seconds=time.time()-started))
    for path,digest in inputs.items():assert sha(path)==digest,path
    inputs[str(Path(__file__).resolve())]=sha(__file__)
    for source,dest in (('sobremadura_gallery.html','index.html'),('sobremadura_gallery.js','gallery.js'),('sobremadura_gallery.css','gallery.css')):
        path=REPO/'scripts/assets'/source;inputs[str(path.resolve())]=sha(path);shutil.copy2(path,root/dest)
    write(root/'input_lock.json',dict(version=VERSION,files=inputs,root_source=str(CURRENT),generation_paused=True))
    print(root/'index.html');print(read(root/'gallery_summary.json'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=REPO/'outputs/sobremadura_four_models_20261113')
    build(parser.parse_args().root)
