"""Pixel/annotation equivalence and active-time estimates for a paired capture."""
from pathlib import Path
from collections import defaultdict
import sys
import math
import statistics
import json
from PIL import Image,ImageChops,ImageStat
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.nodal_automation import read,write,sha


def pixel_difference(a,b):
    with Image.open(a) as x,Image.open(b) as y:
        if x.size!=y.size or x.mode!=y.mode:raise ValueError('Image format/size changed')
        delta=ImageChops.difference(x,y)
        changed=sum(any(pixel) if isinstance(pixel,tuple) else bool(pixel) for pixel in delta.getdata())
        extrema=delta.getextrema()
        return dict(changed_pixels=changed,total_pixels=x.width*x.height,
                    max_channel_error=max(high for low,high in extrema),mean_channel_error=ImageStat.Stat(delta).mean)


def summarize(root,existing=144,target=1000):
    prepared=read(root/'preparation_complete.json')
    bas=read(root/'baseline/complete.json');opt=read(root/'optimized/complete.json')
    assert bas['quality']==opt['quality']==prepared['quality']
    assert bas['scene_sha256']==opt['scene_sha256']==prepared['scene_sha256']
    comparisons=[]
    for b,o in zip(bas['views'],opt['views'],strict=True):
        i=b['index'];bf=root/'baseline'/f'view_{i:03d}';of=root/'optimized'/f'view_{i:03d}'
        ann_b=read(bf/'annotations.json');ann_o=read(of/'annotations.json')
        ann_b.pop('path');ann_o.pop('path')
        rgb=pixel_difference(bf/'rgb.png',of/'rgb.png')
        mask=pixel_difference(bf/'mask_calyx_crisp_v2.png',of/'mask_calyx_crisp_v2.png')
        eligible=[x for x in b['instances'] if min(x['bbox_xywh'][2:])>=6 and x['visible_pixels']>=24]
        row=dict(index=i,depth=b['depth'],diagnostic_light=b['diagnostic_light'],rgb=rgb,mask=mask,
            annotations_equal=ann_b==ann_o,labels_equal=(bf/'labels.txt').read_bytes()==(of/'labels.txt').read_bytes(),
            instances_equal=b['instances']==o['instances'],camera_equal=b['camera_matrix']==o['camera_matrix'],
            lighting_equal=b['lighting']==o['lighting'],geometry_equal=b['geometry_sha256']==o['geometry_sha256'],
            all_visible_instances=len(b['instances']),eligible_legacy_6px_24pixels=len(eligible))
        row['strict_equal']=all(row[k] for k in ('annotations_equal','labels_equal','instances_equal','camera_equal','lighting_equal','geometry_equal')) and rgb['changed_pixels']==mask['changed_pixels']==0
        comparisons.append(row)
    timing={}
    per_view_stages={'lighting','geometry_guard_before','geometry_guard_after','rgb_render','mask_and_stats',
        'labels','annotation_write','view_record_write','growing_manifest_write','incremental_manifest_write'}
    for mode,complete in [('baseline',bas),('optimized',opt)]:
        groups=defaultdict(list)
        for row in read(root/mode/'timings.json')['stages']:groups[row['stage']].append(row['active_seconds'])
        n=len(complete['views'])
        observed=[row['active_seconds'] for row in complete['views']]
        per_view=statistics.mean(observed)
        stage_mean=sum(sum(v) for k,v in groups.items() if k in per_view_stages)/n
        # Both sides include the same initial and final full historical guards.
        overhead=max(0.,complete['total_active_seconds']-sum(observed))
        process_seconds=read(root/(mode+'_job.json'))['total_process_active_seconds']
        startup=max(0.,process_seconds-complete['total_active_seconds'])
        timing[mode]=dict(total_active_seconds=complete['total_active_seconds'],capture_mean_seconds=per_view,
            capture_observed_seconds=observed,attributed_capture_mean_seconds=stage_mean,scene_session_overhead_seconds=overhead,
            worker_startup_verification_seconds=startup,total_process_active_seconds=process_seconds,
            stages={k:dict(count=len(v),total_seconds=sum(v),mean_seconds=statistics.mean(v)) for k,v in groups.items()})
    build=read(root/'prepare_timings.json')['stages'][0]['active_seconds']
    remaining=max(0,target-existing);scenes=math.ceil(remaining/24)
    for mode,t in timing.items():
        # Match the current 24-view memory recycling policy; no extra views
        # claimed independent and no skipped physical audits in the forecast.
        fixed_per_scene=build+t['scene_session_overhead_seconds']+t['worker_startup_verification_seconds']
        samples=t['capture_observed_seconds']
        t['forecast_remaining_active_hours']=(scenes*fixed_per_scene+remaining*t['capture_mean_seconds'])/3600
        t['forecast_observed_capture_range_hours']=[(scenes*fixed_per_scene+remaining*x)/3600 for x in (min(samples),max(samples))]
    result=dict(strict_equal=all(c['strict_equal'] for c in comparisons),comparisons=comparisons,timings=timing,
        measured_scene_build_and_audit_seconds=build,existing_images=existing,target_images=target,
        remaining_images=remaining,remaining_scenes_24views=scenes,
        warm_capture_speedup=timing['baseline']['capture_mean_seconds']/timing['optimized']['capture_mean_seconds'],
        end_to_end_forecast_speedup=timing['baseline']['forecast_remaining_active_hours']/timing['optimized']['forecast_remaining_active_hours'],
        limits=['three paired views from one scene; not a timing confidence interval',
            'scene preparation repeated and full audits retained every 24 views',
            'range varies capture only, not scene-build complexity or future resource contention',
            'native awake time excludes suspension; calendar time can be longer',
            'no large dataset continuation or training started',
            '6px/24 visible pixels is a historical export eligibility example; all mask labels preserved; future training policy must be frozen explicitly'])
    write(root/'comparison.json',result)
    cards=[]
    for c in comparisons:
        i=c['index'];cards.append(f'<article><h2>{c["depth"]} · {c["diagnostic_light"]}</h2><img src="optimized/view_{i:03d}/rgb.png"><p>{c["all_visible_instances"]} instancias completas; {c["eligible_legacy_6px_24pixels"]} cumplen el filtro histórico 6px/24píxeles. Máscara y etiquetas conservan todas.</p><a href="optimized/view_{i:03d}/mask_calyx_crisp_v2.png">Máscara</a></article>')
    (root/'review.html').write_text('<!doctype html><html lang="es"><meta charset="utf-8"><title>Benchmark de captura</title><style>body{font:17px system-ui;background:#f4f3ee;padding:24px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px}img{width:100%}article{padding:12px;background:white}</style><h1>Captura emparejada: original y optimizada</h1><p>Árboles y materiales intactos. Tres profundidades/condiciones; no entrenamiento. Equivalencia exacta: '+str(result['strict_equal'])+'</p><main>'+''.join(cards)+'</main><p><a href="comparison.json">Métricas y tiempos completos</a></p>',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('comparisons','timings')},indent=2))
    for mode,t in timing.items():print(mode,t['capture_mean_seconds'],t['forecast_remaining_active_hours'])
    if not result['strict_equal']:raise SystemExit('Equivalence failed; optimization cannot be promoted')
    return result


if __name__=='__main__':summarize(Path(sys.argv[1]).resolve())
