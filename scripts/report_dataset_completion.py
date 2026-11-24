"""Verify real pixels/labels and publish a combined gallery without training."""
from pathlib import Path
import sys
from collections import Counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.nodal_automation import read,write,sha
from uchuva_lsystem.dataset_completion import baseline_rows,new_rows,publish_index


def audit_pixels(row,assignments):
    import numpy as np
    from PIL import Image
    annotation=read(Path(row['mask']).parent/'annotations.json')
    rgb=np.asarray(Image.open(row['mask']).convert('RGB'),dtype=np.uint32)
    h,w=rgb.shape[:2];packed=(rgb[:,:,0]<<16)|(rgb[:,:,1]<<8)|rgb[:,:,2]
    unique,inverse=np.unique(packed.reshape(-1),return_inverse=True)
    palette={(c[0]<<16)|(c[1]<<8)|c[2]:int(i) for i,c in annotation['palette'].items()}
    if any(int(c) not in palette for c in unique):raise ValueError('Unknown mask color: '+row['view_id'])
    ids=np.asarray([palette[int(c)] for c in unique],dtype=np.int32)[inverse]
    size=4096;counts=np.bincount(ids,minlength=size)
    offset=np.arange(w*h);xs=offset%w;ys=offset//w
    minx=np.full(size,w);miny=np.full(size,h);maxx=np.full(size,-1);maxy=np.full(size,-1)
    np.minimum.at(minx,ids,xs);np.minimum.at(miny,ids,ys)
    np.maximum.at(maxx,ids,xs);np.maximum.at(maxy,ids,ys)
    observed=set(np.flatnonzero(counts))-{0};declared={i['mask_id'] for i in row['instances']}
    if observed!=declared:raise ValueError('Visible target omitted or invented: '+row['view_id'])
    labels=Path(row['label']).read_text(encoding='utf-8').splitlines()
    if len(labels)!=len(row['instances']):raise ValueError('YOLO/instance count differs')
    error=0.
    for item,line in zip(row['instances'],labels):
        i=item['mask_id'];box=[int(minx[i]),int(miny[i]),int(maxx[i]-minx[i]+1),int(maxy[i]-miny[i]+1)]
        raw=annotation['items'][str(i)]
        if box!=item['bbox_xywh'] or box!=raw['bbox_xywh'] or int(counts[i])!=item['visible_pixels'] or int(counts[i])!=raw['visible_pixels']:
            raise ValueError('Pixel/box/count mismatch')
        if raw.get('semantic_class')!='calyx' or raw['instance_id']!=item['instance_id']:
            raise ValueError('Mask identity/semantic mismatch')
        if assignments[item['instance_id']]['class_id']!=item['class_id']:raise ValueError('Class mismatch')
        values=line.split();x,y,bw,bh=box;expected=[(x+bw/2)/w,(y+bh/2)/h,bw/w,bh/h]
        if int(values[0])!=item['class_id']:raise ValueError('YOLO class differs')
        delta=max(abs(float(a)-b) for a,b in zip(values[1:],expected));error=max(error,delta)
        if delta>1e-9:raise ValueError('YOLO coordinates differ')
    return dict(view_id=row['view_id'],status='pass',instances=len(row['instances']),max_yolo_error=error)


def update(root,final=False):
    root=Path(root);inherited=baseline_rows(root,verify=final);rows=new_rows(root)
    count=publish_index(root,rows);bank=root/'dataset'
    for row in rows:
        audit=bank/'views'/row['view_id']/'pixel_audit.json'
        if not audit.exists():
            record=read(bank/'scenes'/row['scene_id']/'accepted.json')
            write(audit,audit_pixels(row,record['assignments']))
    depths=Counter(r['depth_stratum'] for r in inherited+rows)
    classes=Counter(i['class_id'] for r in inherited+rows for i in r['instances'])
    continuous=[r for r in rows if r.get('depth_sampling',{}).get('version')=='continuous_distance/1']
    segments=Counter(r['depth_sampling']['segment'] for r in continuous)
    distances=sorted(r['camera_distance_m'] for r in continuous)
    visible=Counter()
    for r in inherited+rows:
        for seed in r['plant_seeds']:
            if any(i['instance_id'].startswith(f'plant_{seed}:') for i in r['instances']):visible[seed]+=1
    selected=[]
    scenes=sorted({r['scene_id'] for r in rows})[-2:]
    for scene in scenes:
        for depth in ('near','middle','far'):
            group=[r for r in rows if r['scene_id']==scene and r['depth_stratum']==depth]
            if group:selected.append(group[len(group)//2])
    cards=[]
    for row in selected:
        source='dataset/views/'+row['view_id']
        label={'near':'Cercana','middle':'Intermedia','far':'Lejana'}[row['depth_stratum']]
        cards.append(f'<article><h2>{label}: {row["view_id"]}</h2><img src="{source}/rgb.png"><p>{len(row["instances"])} capachos visibles anotados. <a href="{source}/mask_calyx_crisp_v2.png">Máscara</a> · <a href="{source}/pixel_audit.json">Auditoría de píxeles</a></p></article>')
    page=f'<!doctype html><html lang="es"><meta charset="utf-8"><title>Completar 1.000 imágenes</title><style>body{{font:17px system-ui;background:#f2f1eb;padding:24px;max-width:1500px;margin:auto}}main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:18px}}article{{background:white;padding:14px}}img{{width:100%;height:auto}}</style><h1>{count} / 1.000 imágenes completas verificadas</h1><p>{len(inherited)} heredadas intactas + {len(rows)} nuevas optimizadas. Veinte árboles admitidos preservados. Sólo cuentan escenas cerradas; los parciales quedan aparte.</p><p>Revisión humana de muestras pendiente. No se ha iniciado entrenamiento. Las vistas reutilizan plantas y no se presentan como muestras independientes.</p><main>'+''.join(cards)+'</main><p><a href="combined_index.json">Índice combinado</a> · <a href="review_summary.json">Resumen</a></p></html>'
    (root/'review.html').write_text(page,encoding='utf-8')
    summary=dict(complete_images=count,inherited_images=len(inherited),optimized_images=len(rows),
        depth_counts=dict(depths),visible_plant_count=len(visible),visible_plant_exposure=dict(visible),
        annotated_instances_by_class=dict(classes),gallery_views=[r['view_id'] for r in selected],
        continuous_distance_images=len(continuous),continuous_distance_segments=dict(segments),
        continuous_near_middle_fraction=segments['near_to_middle']/len(continuous) if continuous else None,
        continuous_distance_m_range=[distances[0],distances[-1]] if distances else None,
        all_new_pairs_pixel_audited=True,training_started=False,human_sample_review='pending')
    write(root/'review_summary.json',summary)
    if final:
        if count!=read(root/'config.json')['target_total']:raise ValueError('Cannot close below target')
        write(root/'combined_manifest.json',dict(views=inherited+rows,complete_images=count,
            inherited_source=read(root/'config.json')['source_campaign'],training_started=False,
            sample_review_required_before_training=True))
    return summary


if __name__=='__main__':
    import json
    print(json.dumps(update(Path(sys.argv[1]).resolve(),'--final' in sys.argv[2:]),ensure_ascii=False))
