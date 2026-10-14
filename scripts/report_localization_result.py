"""Report frozen reserved results without changing the estimator or selection."""
import argparse
import collections
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.execution_budget import remaining_seconds
from uchuva_lsystem.segmentation_cycles import write


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();r=a.root.resolve()
    baseline=json.loads((r/'reserved_evaluation/baseline/metrics.json').read_text())
    winner=json.loads((r/'reserved_evaluation/winner/metrics.json').read_text())
    mapping=json.loads((r/'reserved_estimates/winner_qualified/support_8/map.json').read_text())
    presentation=r/'presentation';delivery=[]
    for item in mapping['objects']:
        delivery.append(dict(persistent_id=item['map_id'],canonical_aruco=item['marker_id'],state=item['state'],
            position_xyz_m=item['position_marker_m'],uncertainty_m=item.get('uncertainty_m'),
            uncertainty_semantics='leave-one-out sensitivity, not calibrated confidence',class_id=item['class_id'],
            supporting_observations=item['observation_ids'],source_tracks=item['track_ids'],
            rejection_reasons=item.get('rejection_reasons',[])))
    for i,item in enumerate(mapping['rejected']):
        delivery.append(dict(persistent_id=f'unlocalized_{i:06d}',canonical_aruco=item.get('marker_id'),
            state='no_localizable',position_xyz_m=None,uncertainty_m=None,class_id=None,
            source_tracks=[item.get('track_id')],supporting_observations=[],rejection_reasons=[item['reason']]))
    write(presentation/'mapa_conciliado.json',dict(version='calyx-marker-delivery/1.0',units='metres',
        axes='ArUco canonical: x right, y up, z outward',objects=delivery,
        note='Entries without location are unresolved track hypotheses, not independent biological objects. Confirmed means estimator acceptance, not guaranteed truth.'))
    fig=plt.figure(figsize=(15,9))
    for i,marker in enumerate(range(0,12,2)):
        ax=fig.add_subplot(2,3,i+1,projection='3d')
        for state,color in [('provisional','orange'),('confirmed','green')]:
            points=[v['position_marker_m'] for v in mapping['objects'] if v['marker_id']==marker and v['state']==state]
            if points:ax.scatter(*zip(*points),s=12 if state=='confirmed' else 4,c=color,label=state,alpha=.8 if state=='confirmed' else .2)
        ax.scatter([0],[0],[0],marker='s',c='black',label='ArUco')
        ax.set(title=f'ArUco {marker}',xlabel='X (m)',ylabel='Y (m)',zlabel='Z (m)')
    fig.suptitle('Mapa estimado por planta: confirmado por algoritmo / provisional')
    fig.tight_layout();fig.savefig(presentation/'mapa_3d.png',dpi=160);plt.close(fig)
    failures=collections.Counter()
    for row in winner['rows']:
        if row['correct']:continue
        if row['identity_support']<3 or row['purity']<.8:reason='identidad insuficiente o mezclada'
        elif not row['correct_marker']:reason='ArUco incorrecto'
        elif row['duplicate']:reason='duplicado'
        else:reason='error 3D mayor de 5 cm'
        failures[reason]+=1
    provenance=json.loads((r/'reserved_estimates/winner_raw/provenance.json').read_text())
    flight=json.loads((r/'reserved_flight_close_batched/full/result.json').read_text())
    validation=json.loads((r/'reserved_flight_close_batched/full/segmentation_validation.json').read_text())
    jobs={p.stem:json.loads(p.read_text()) for p in (r/'execution_jobs').glob('*.json')}
    timings={name:jobs[name]['awake_elapsed_seconds'] for name in ('reserved_full_flight','audit_reserved_truth','reserved_estimate_baseline','reserved_estimate_winner_raw','reserved_qualify_winner','reserved_evaluate_winner')}
    write(presentation/'diagnostico.json',dict(unique_visible=winner['visible_unique'],completely_hidden=winner['completely_hidden'],
        never_detected_by_winner=winner['visible_unique']-winner['detected_unique'],confirmed_failure_categories=dict(failures),
        track_rejection_counts=winner['rejection_reasons'],timings_seconds=timings,
        warning='Track rejection counts overlap biological objects and cannot be summed as unique losses. Marker/parallax/association loss attribution is incomplete.'))
    rows='\n'.join(f'| {name} | {m["localized_unique"]}/{m["visible_unique"]} | {100*m["recall"]:.2f} % | {100*m["precision"]:.2f} % | {m["duplicates"]} | {m["wrong_marker"]} | {100*m["error_median_m"]:.2f} | {100*m["error_p95_m"]:.2f} |' for name,m in [('Baseline',baseline),('Variante congelada',winner)])
    text=f'''# Cierre del piloto 3D de uchuvas — 5 de octubre de 2026

**El objetivo no se alcanzó.** La variante congelada localizó correctamente {winner['localized_unique']} de {winner['visible_unique']} capachos observables, con precisión conjunta de {100*winner['precision']:.2f} %. Se exigían más del 50 % y al menos 90 %, respectivamente. Son resultados de Gazebo; no demuestran transferencia al cultivo real.

| Variante | Correctos / visibles | Recall 3D | Precisión conjunta | Duplicados | ArUco incorrecto | Error mediano (cm) | P95 (cm) |
|---|---:|---:|---:|---:|---:|---:|---:|
{rows}

La precisión conjunta exige identidad respaldada, marcador correcto, error ≤5 cm y ausencia de duplicación. Los errores mediano/P95 incluyen identidades respaldadas del marcador correcto aunque excedan 5 cm; no describen los objetos perdidos. El denominador conserva todos los tamaños y capturas de tránsito. Hubo {winner['completely_hidden']} capachos totalmente ocultos, informados aparte. La posición estima el centro del capacho a partir del centroide de su silueta visible, no el fruto interior.

## Separación y selección

Las seis semillas 520300–520305 se reservaron antes de generar imágenes. Se conservaron todas, corrigiendo geometría sin selección por desempeño. Pasó la auditoría independiente de correspondencias panópticas y anatómicas. El estimador recibe RGB, tiempos y calibración pública, incluido el soporte rígido de marcadores opuestos; no recibe máscaras, anatomía ni odometría. La selección quedó congelada antes del vuelo reservado y no se ajustó posteriormente.

En desarrollo, 960 píxeles y ocho observaciones alcanzaron 38/388 y 97,44 % de precisión. El reservado muestra una caída a {100*winner['precision']:.2f} %. Se preservan regresiones del muestreo adaptativo y de ROI. No se entrenó otro modelo porque detectar más no resolvió la continuidad de identidad ni la geometría.

## Vuelo, pérdidas y tiempos

El vuelo completó {flight['waypoints_reached']}/{flight['waypoints_expected']} puntos, con separación mínima {flight['minimum_executed_margin_m']:.3f} m. Pasaron las verificaciones de sincronización, ArUco RGB y encuadre: {validation['passed']}. El modelo detectó al menos una vez {winner['detected_unique']} objetos distintos; detectar no equivale a localizarlos.

Fallos entre hipótesis confirmadas: {dict(failures)}. El diagnóstico JSON conserva rechazos por falta de observaciones, paralaje y consistencia; son trayectorias, no conteos independientes de capachos. No se dispone de una descomposición causal completa por objeto.

El estimador bruto tardó {provenance['seconds']:.1f} s. El P95 por fotograma segmentado fue {provenance['p95_seconds']:.3f} s, por encima de 200 ms; además falta sumar conciliación global. No se propone ejecución en línea. Los tiempos separados de captura, auditoría, estimación y conciliación están en diagnostico.json. El video es una presentación de muestras a 1 Hz y no representa rendimiento en tiempo real.

## Entregables y pendientes

- Mapa: [{presentation/'mapa_conciliado.json'}]({(presentation/'mapa_conciliado.json').as_posix()}). Confirmado significa aceptado por el algoritmo; los candidatos ambiguos permanecen provisionales.
- Video: [{presentation/'localizacion_reservada.mp4'}]({(presentation/'localizacion_reservada.mp4').as_posix()}). Segmentaciones repetidas con pesos congelados y correspondencias con observaciones guardadas; no se usan para nuevas métricas.
- Gráfico: [{presentation/'mapa_3d.png'}]({(presentation/'mapa_3d.png').as_posix()}).

No se completó la revisión específica del recorrido con vistas oblicuas; se mantuvo la pasada lateral exterior segura. Tampoco se cuantificó por separado el sesgo de silueta por oclusión ni se completaron todas las pruebas de cruces, interrupciones y aislamiento con entradas adversarias. Los aumentos de apariencia y entrenamientos adicionales no formaban el foco de esta fase. No se presenta este cierre como cumplimiento de todos los pasos del plan ni como éxito de localización.

La campaña conserva su presupuesto independiente de doce horas efectivas, excluyendo suspensión e inactividad. El saldo al generar este informe era {remaining_seconds(r)/3600:.2f} h; el consumo definitivo se registra al cerrar. No se empleará el reservado para seguir ajustando.
'''
    (ROOT/'docs/reports/cierre_localizacion_3d_2026-10-05.md').write_text(text,encoding='utf-8')
    write(r/'closure_status.json',dict(state='artifacts_ready_pending_review',objective_achieved=False,remaining_seconds=remaining_seconds(r),pending=['video_quality_review','final_budget_record','heartbeat_deactivation']))
    print('LOCALIZATION_REPORT_READY',flush=True)


if __name__=='__main__':main()
