"""Describe sky coverage without counting unclosed views as a finished bank."""
from pathlib import Path
from collections import Counter,defaultdict
import sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.nodal_automation import read,write


def report(root):
    root=Path(root);bank=root/'dataset';counts=Counter();depths=defaultdict(Counter);selected={}
    pending=Counter();versions=Counter()
    for p in sorted((bank/'views').glob('*/view.json')):
        row=read(p)
        if row.get('status')!='complete':continue
        sky=row.get('lighting',{}).get('camera_background',{}).get('sky_type','historical_overcast')
        version=row.get('lighting',{}).get('camera_background',{}).get('sky_replacement_version','previous')
        versions[version]+=1
        if not (bank/'scenes'/row['scene_id']/'capture_complete.json').exists():
            pending[sky]+=1
        else:
            counts[sky]+=1;depths[sky][row['depth_stratum']]+=1
        if version=='aligned_horizon_matte/3':selected[(sky,row['depth_stratum'])]=row['view_id']
    result=dict(closed_sky_counts=dict(counts),closed_depths_by_sky={k:dict(v) for k,v in depths.items()},
        prefix_sky_counts_pending_scene_closure=dict(pending),sky_implementation_counts=dict(versions),
        sample_view_ids=list(selected.values()),counts_describe_configuration_not_observed_weather=True,
        training_started=False,provenance='counts per committed view; unclosed prefixes kept separate')
    write(root/'sky_coverage.json',result)
    names={'clear_blue':'Azul despejado','hazy_clear':'Despejado con bruma','overcast':'Cubierto'}
    cards=[]
    for (sky,depth),view_id in sorted(selected.items()):
        closed=(bank/'scenes'/read(bank/'views'/view_id/'view.json')['scene_id']/'capture_complete.json').exists()
        cards.append(f'<article><h2>{names[sky]} · {depth}</h2><img src="dataset/views/{view_id}/rgb.png"><p>{view_id} · '+
            ('Escena cerrada' if closed else 'Prefijo: cierre de escena pendiente')+'</p></article>')
    (root/'sky_review.html').write_text('<!doctype html><html lang="es"><meta charset="utf-8"><title>Variedad de cielos</title>'+
        '<style>body{font:17px system-ui;max-width:1400px;margin:auto;padding:20px;background:#f1f0e9}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(350px,1fr));gap:20px}img{width:100%}</style>'+
        '<h1>Muestras de cielos de producción</h1><p>Plantas admitidas intactas. Revisión humana pendiente; sin entrenamiento.</p><main>'+''.join(cards)+'</main></html>',encoding='utf-8')
    return result


if __name__=='__main__':print(json.dumps(report(sys.argv[1]),ensure_ascii=False))
