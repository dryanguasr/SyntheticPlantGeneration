"""Evaluator-only join of frozen RGB estimates and Gazebo instance truth."""
import argparse
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
import sys
import cv2
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.multiview import match_detections, iou
from uchuva_gazebo.evaluation import visible_boxes as mask_boxes
from validate_low_capture import decode_mask


def rows(path):return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def table(path,data):
    if not data:path.write_text('');return
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        fields=list(dict.fromkeys(k for row in data for k in row))
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(data)


def statistics(values):
    if not values:return {'n':0,'median_m':None,'rmse_m':None,'p90_m':None,
                          'within_2_cm':None,'within_5_cm':None,'within_10_cm':None}
    a=np.asarray(values)
    return {'n':len(a),'median_m':float(np.median(a)),'rmse_m':float(np.sqrt(np.mean(a*a))),
            'p90_m':float(np.percentile(a,90)),**{f'within_{cm}_cm':float(np.mean(a<=cm/100)) for cm in (2,5,10)}}


def marker_coordinates(point,marker):
    normal=np.array(marker['normal_world']);up=np.array([0,0,1]);right=np.cross(up,normal)
    return np.column_stack((right,up,normal)).T@(np.asarray(point)-marker['center_world_m'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path)
    p.add_argument('--run',default='flight');p.add_argument('--estimates',type=Path,required=True)
    args=p.parse_args();package=args.package;run=package/args.run;out=run/'evaluation';out.mkdir(exist_ok=False)
    inventory=json.loads((package/'evaluator/inventory.json').read_text())
    objects={o['panoptic_instance']:o for o in inventory['calyces']};by_id={o['reproductive_id']:o for o in objects.values()}
    markers={m['id']:m for m in inventory['markers']}
    pairs={p['stamp_ns']:p for p in json.loads((run/'pairs.json').read_text())['pairs']}
    samples=json.loads((run/'telemetry.json').read_text())['samples']; times=np.array([s['t'] for s in samples])
    frames=[];associations=[];planar=[];visible=set();detected=set();localized2d=set();observations={}
    plant_stats=defaultdict(Counter);group_stats=defaultdict(Counter);excluded=[];small_unique=set()
    unavailable_3d_observations=Counter()
    video=cv2.VideoWriter(str(out/'comparacion_5hz.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),5,(1280,720))
    if not video.isOpened():raise RuntimeError('Cannot open comparison video')
    for record in rows(args.estimates/'observations.jsonl'):
        stamp=record['stamp_ns'];sample=samples[int(np.argmin(abs(times-stamp*1e-9)))]
        phase=sample['phase']
        if not phase.startswith('pass_'):
            excluded.append({'stamp_ns':stamp,'reason':'startup_or_transition'});continue
        if stamp not in pairs:excluded.append({'stamp_ns':stamp,'reason':'missing_mask'});continue
        references=mask_boxes(decode_mask(run/pairs[stamp]['mask']))
        small=[r for r in references if r['pixels']<16]
        refs=[r for r in references if r['pixels']>=16]
        for r in small:
            if objects[r['instance']]['target']:small_unique.add(objects[r['instance']]['reproductive_id'])
        dets=record['detections'];matches,duplicates=match_detections([d['box_xyxy_px'] for d in dets],[r['box'] for r in refs])
        image=cv2.imread(str(run/pairs[stamp]['rgb']))
        hit=set(matches.values());tp=fn=external=0;fp=0
        for j,r in enumerate(refs):
            o=objects[r['instance']]
            if not o['target']:continue
            identifier=o['reproductive_id'];visible.add(identifier)
            size='16_63' if r['pixels']<64 else '64_255' if r['pixels']<256 else '256_plus'
            # This is visible pixel support, explicitly not an occlusion fraction.
            key=f'{phase}|{sample["target"][2]:.2f}|visible_pixels_{size}'
            plant_stats[o['plant_id']]['visible_observations']+=1;group_stats[key]['visible']+=1
            if j in hit:tp+=1;detected.add(identifier);plant_stats[o['plant_id']]['tp']+=1;group_stats[key]['tp']+=1
            else:fn+=1;plant_stats[o['plant_id']]['fn']+=1;group_stats[key]['fn']+=1
            x1,y1,x2,y2=r['box']
            cv2.rectangle(image,(x1,y1),(x2,y2),(70,190,70) if j in hit else (210,90,210),1)
        for i,d in enumerate(dets):
            if d.get('position_3d_unavailable_reason'):unavailable_3d_observations[d['position_3d_unavailable_reason']]+=1
            matched=matches.get(i);o=None
            if matched is not None:o=objects[refs[matched]['instance']]
            is_small=matched is None and any(iou(d['box_xyxy_px'],r['box'])>=.5 for r in small)
            if o is None and not is_small:fp+=1
            if o and not o['target']:external+=1
            x1,y1,x2,y2=map(round,d['box_xyxy_px'])
            cv2.rectangle(image,(x1,y1),(x2,y2),(70,240,100) if o and o['target'] else (20,160,255),2)
            row={'stamp_ns':stamp,'observation_id':d['observation_id'],'track_id':d['track_id'],'pass':phase,
                 'height_m':sample['target'][2],'plant_id':o['plant_id'] if o else None,
                 'calyx_id':o['reproductive_id'] if o else None,'target':o['target'] if o else False,
                 'match_status':'true_positive' if o else 'below_16px_reference' if is_small else 'duplicate' if i in duplicates else 'false_positive',
                 'visible_pixels':refs[matched]['pixels'] if o else None}
            associations.append(row);observations[d['observation_id']]=row
            if o and o['target']:
                for position in d['positions_by_marker']:
                    estimate=position['position_cm'];marker=markers.get(position['marker_id'])
                    if estimate is None or marker is None:continue
                    gt=marker_coordinates(o['center_world_m'],marker)
                    ex,ey=estimate['x']/100,estimate['y']/100
                    planar.append({**row,'marker_id':marker['id'],'estimated_x_m':ex,'estimated_y_m':ey,
                        'true_x_m':gt[0],'true_y_m':gt[1],'error_x_m':ex-gt[0],'error_y_m':ey-gt[1],
                        'error_xy_m':float(np.linalg.norm([ex-gt[0],ey-gt[1]])),'depth':'unknown'})
                    localized2d.add(o['reproductive_id'])
        frames.append({'stamp_ns':stamp,'pass':phase,'height_m':sample['target'][2],'tp':tp,'fp_unmatched':fp,'fn':fn,
            'duplicates':len(duplicates),'matched_external':external,'visible_below_16px':len(small),
            'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,
            'markers_observed':len(record['markers']),
            'marker_poses_available':sum(p['status']=='estimated' for p in record['marker_poses'].values())})
        cv2.rectangle(image,(0,0),(1280,60),(25,25,25),-1)
        cv2.putText(image,f'{phase} | {sample["target"][2]:.2f} m | t={stamp/1e9:.2f}s | TP {tp} FP {fp} FN {fn}',
                    (12,25),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),1)
        cv2.putText(image,'Verde: coincidencia | Magenta: visible no detectado | Naranja: no objetivo / falso positivo',
                    (12,49),cv2.FONT_HERSHEY_SIMPLEX,.5,(230,230,230),1)
        video.write(image)
    video.release()
    reconstruction_rows=[];rejection_counts=Counter();localized3d=set();chosen={}
    for recon in rows(args.estimates/'reconstructions.jsonl'):
        linked=[observations.get(o['observation_id']) for o in recon['observations_used']]
        linked=[o for o in linked if o and o['calyx_id']]
        ids={o['calyx_id'] for o in linked}
        if recon['status']!='estimated':rejection_counts[recon['reason']]+=1;continue
        if len(ids)!=1 or len(linked)<3:
            rejection_counts['evaluation_inconsistent_or_insufficient_truth_matches']+=1;continue
        identifier=next(iter(ids));o=by_id[identifier];m=markers[recon['marker_id']]
        gt=marker_coordinates(o['center_world_m'],m);estimate=np.array(recon['position_marker_m'])
        err=float(np.linalg.norm(estimate-gt))
        normal=np.array(m['normal_world']);up=np.array([0,0,1]);right=np.cross(up,normal)
        world=np.column_stack((right,up,normal))@estimate+m['center_world_m']
        row={'track_id':recon['track_id'],'marker_id':recon['marker_id'],'plant_id':o['plant_id'],'calyx_id':identifier,
             'target':o['target'],'observations':len(recon['observations_used']),
             'estimated_x_m':estimate[0],'estimated_y_m':estimate[1],'estimated_z_m':estimate[2],
             'true_x_m':gt[0],'true_y_m':gt[1],'true_z_m':gt[2],'error_3d_m':err,
             'map_world_x_m':world[0],'map_world_y_m':world[1],'map_world_z_m':world[2],
             'map_transform_source':'evaluator_only_true_marker_pose','parallax_deg':recon['parallax_deg'],
             'height_m':linked[0]['height_m'],'median_visible_pixels':float(np.median([r['visible_pixels'] for r in linked]))}
        reconstruction_rows.append(row)
        if o['target']:
            localized3d.add(identifier)
            # Select one estimate per object by observation count, never by true error.
            if identifier not in chosen or row['observations']>chosen[identifier]['observations']:chosen[identifier]=row
    total=Counter()
    for f in frames:
        for k in ('tp','fp_unmatched','fn','duplicates','matched_external'):total[k]+=f[k]
    pass_rows=[]
    for phase in sorted({f['pass'] for f in frames}):
        subset=[f for f in frames if f['pass']==phase]; c=Counter()
        for f in subset:
            for k in ('tp','fp_unmatched','fn','duplicates','matched_external'):c[k]+=f[k]
        pass_rows.append({'pass':phase,'frames':len(subset),**c,'precision':c['tp']/(c['tp']+c['fp_unmatched']) if c['tp']+c['fp_unmatched'] else None,
                          'recall':c['tp']/(c['tp']+c['fn']) if c['tp']+c['fn'] else None})
    plant_rows=[]
    for plant in [f'plant_{i:02d}' for i in range(12,24)]:
        ids={o['reproductive_id'] for o in objects.values() if o['plant_id']==plant};c=plant_stats[plant]
        plant_rows.append({'plant_id':plant,'existing':len(ids),'visible_unique':len(ids&visible),'detected_unique':len(ids&detected),
            'planar_unique':len(ids&localized2d),'multiview_unique':len(ids&localized3d),'tp':c['tp'],'fn':c['fn'],
            'recall':c['tp']/(c['tp']+c['fn']) if c['tp']+c['fn'] else None,
            'precision':None,'precision_note':'unmatched false positives have no plant identity'})
    summary={'existing_target':747,'visible_unique':len(visible),'detected_unique':len(detected),
        'planar_unique':len(localized2d),'multiview_unique':len(localized3d),'small_visible_unique':len(small_unique),
        'visible_only_below_16px_unique':len(small_unique-visible),
        'evaluated_frames':len(frames),'excluded_frames':len(excluded),**total,
        'precision':total['tp']/(total['tp']+total['fp_unmatched']) if total['tp']+total['fp_unmatched'] else None,
        'recall':total['tp']/(total['tp']+total['fn']) if total['tp']+total['fn'] else None,
        'unique_detection_coverage_existing':len(detected)/747,'unique_detection_coverage_visible':len(detected)/len(visible) if visible else None,
        'localization_coverage_existing_3d':len(localized3d)/747,
        'localization_coverage_visible_3d':len(localized3d)/len(visible) if visible else None,
        'localization_coverage_detected_3d':len(localized3d)/len(detected) if detected else None,
        'localization_coverage_existing_planar':len(localized2d)/747,
        'localization_coverage_visible_planar':len(localized2d)/len(visible) if visible else None,
        'localization_coverage_detected_planar':len(localized2d)/len(detected) if detected else None,
        'marker_frame_availability':sum(f['markers_observed']>0 for f in frames)/len(frames) if frames else None,
        'planar_xy':statistics([r['error_xy_m'] for r in planar]),
        'multiview_3d_per_unique_object':statistics([r['error_3d_m'] for r in chosen.values()]),
        'reconstruction_rejections':dict(rejection_counts),
        'observations_without_3d_marker_pose':dict(unavailable_3d_observations)}
    table(out/'frames.csv',frames);table(out/'passes.csv',pass_rows);table(out/'plants.csv',plant_rows)
    table(out/'planar_xy.csv',planar);table(out/'multiview_3d.csv',reconstruction_rows)
    error_groups=defaultdict(list)
    for r in planar:
        size='16_63' if r['visible_pixels']<64 else '64_255' if r['visible_pixels']<256 else '256_plus'
        error_groups[('planar_xy',r['height_m'],size)].append(r['error_xy_m'])
    for r in reconstruction_rows:
        if not r['target']:continue
        size='16_63' if r['median_visible_pixels']<64 else '64_255' if r['median_visible_pixels']<256 else '256_plus'
        error_groups[('multiview_3d',r['height_m'],size)].append(r['error_3d_m'])
    table(out/'localization_error_strata.csv',[{'method':k[0],'height_m':k[1],'visible_pixel_group':k[2],**statistics(v)} for k,v in error_groups.items()])
    table(out/'size_height_visibility.csv',[{'group':k,**dict(v),'recall':v['tp']/v['visible']} for k,v in group_stats.items()])
    table(out/'inventory.csv',[{'plant_id':o['plant_id'],'calyx_id':o['reproductive_id'],'target':o['target'],
        'x_m':o['center_world_m'][0],'y_m':o['center_world_m'][1],'z_m':o['center_world_m'][2],
        'visible':o['reproductive_id'] in visible,'detected':o['reproductive_id'] in detected,
        'planar_available':o['reproductive_id'] in localized2d,'multiview_available':o['reproductive_id'] in localized3d} for o in objects.values()])
    (out/'associations.jsonl').write_text(''.join(json.dumps(a)+'\n' for a in associations))
    (out/'excluded_frames.json').write_text(json.dumps(excluded,indent=2))
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    fig,axes=plt.subplots(2,1,figsize=(12,8),layout='constrained')
    target=[o for o in objects.values() if o['target']]
    for ax,coord,label in ((axes[0],1,'Y mundo (m)'),(axes[1],2,'Z mundo (m)')):
        ax.scatter([o['center_world_m'][0] for o in target],[o['center_world_m'][coord] for o in target],s=9,c='#bec5c9',label='Existentes (747)')
        seen=[o for o in target if o['reproductive_id'] in detected]
        ax.scatter([o['center_world_m'][0] for o in seen],[o['center_world_m'][coord] for o in seen],s=13,c='#167c70',label='Detectados correctamente')
        ax.scatter([r['map_world_x_m'] for r in chosen.values()],[r['map_world_y_m' if coord==1 else 'map_world_z_m'] for r in chosen.values()],marker='x',c='#c5532e',s=30,label='Estimación 3D')
        ax.set(xlabel='X mundo (m)',ylabel=label);ax.grid(alpha=.2);ax.legend()
    fig.suptitle('Piloto: verdad sintética y reconstrucciones ArUco\nEl marco mundial se usa únicamente en el evaluador para dibujar el mapa')
    fig.savefig(out/'position_map.png',dpi=160);plt.close(fig)
    def value(x):return 'no disponible' if x is None else f'{x:.3f}'
    report=f'''# Piloto de vuelo bajo: detección y localización

Ensayo exploratorio sintético. Detector `natural_hybrid_alpha_045`, capacho,
confianza 0,25, sin reentrenamiento ni evaluación de madurez.

## Cobertura

| Etapa | Capachos únicos objetivo |
|---|---:|
| Existentes | 747 |
| Visibles con ≥16 píxeles | {len(visible)} |
| Detectados (IoU ≥0,5) | {len(detected)} |
| Con estimación planar | {len(localized2d)} |
| Con reconstrucción 3D asociable | {len(localized3d)} |

Se evaluaron {len(frames)} exposiciones originales de las cuatro pasadas a 5 Hz.
Se excluyeron {len(excluded)} observaciones de arranque/transición o sin máscara.
Precisión agregada: {value(summary['precision'])}; recall: {value(summary['recall'])}.
Coincidencias ajenas a las doce plantas: {total['matched_external']}; duplicados: {total['duplicates']}.
Disponibilidad de ArUcos por imagen: {value(summary['marker_frame_availability'])}.

## Localización

Error planar X/Y (metros): `{json.dumps(summary['planar_xy'])}`.
Esta homografía supone el plano del marcador; profundidad desconocida. No es error 3D.

Error 3D por capacho único (metros): `{json.dumps(summary['multiview_3d_per_unique_object'])}`.
Cobertura 3D respecto al inventario: {len(localized3d)}/747.
Se selecciona por número de observaciones, nunca por menor error verdadero.
Las reconstrucciones mantienen su propio marco de marcador; solo el evaluador
aplica la pose verdadera del marcador para dibujar el mapa mundial.

Rechazos multivista: `{json.dumps(dict(rejection_counts),ensure_ascii=False)}`.

## Archivos y límites

- `frames.csv`, `passes.csv`, `plants.csv`: resultados por imagen, pasada y planta.
- `inventory.csv`: inventario completo e indicadores de cobertura.
- `planar_xy.csv`, `multiview_3d.csv`: coordenadas y errores individuales.
- `size_height_visibility.csv`: errores de detección según píxeles visibles y altura.
- `associations.jsonl`: unión con verdad sintética hecha únicamente por el evaluador.
- `position_map.png`: posiciones verdaderas y estimadas.

Las máscaras son soporte visible, no una medida de fracción ocluida. Se informa
visibilidad como cantidad de píxeles. Las instancias menores de 16 píxeles se
separan. La precisión por planta queda sin valor: un falso positivo no tiene
identidad verdadera de planta y asignársela arbitrariamente sesgaría esa métrica.
Los falsos positivos sin correspondencia se conservan en los totales y registros.
La referencia 3D es el centro de la geometría; el detector entrega el centro de
la caja visible, que puede diferir incluso con una caja correcta.

Este resultado mide exclusivamente este escenario ideal de Gazebo; no demuestra
desempeño equivalente en los vídeos reales ni precisión física del DJI Neo.
'''
    (out/'reporte.md').write_text(report,encoding='utf-8');print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
