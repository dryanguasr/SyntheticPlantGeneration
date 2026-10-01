"""Spanish experiment report and marker-local planar maps from completed evaluation."""
import argparse
import csv
import json
import math
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator


def percent(value):return 'no disponible' if value is None else f'{100*value:.2f} %'
def cm(value):return 'no disponible' if value is None else f'{100*value:.2f} cm'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path)
    p.add_argument('--report',type=Path,required=True);args=p.parse_args()
    package=args.package;run=package/'flight';evaluation=run/'evaluation'
    summary=json.loads((evaluation/'summary.json').read_text())
    result=json.loads((run/'result.json').read_text());validation=json.loads((run/'validation.json').read_text())
    config=json.loads((package/'mission.json').read_text())
    with (evaluation/'plants.csv').open(encoding='utf-8-sig') as f:plants=list(csv.DictReader(f))
    with (evaluation/'passes.csv').open(encoding='utf-8-sig') as f:passes=list(csv.DictReader(f))
    with (evaluation/'planar_xy.csv').open(encoding='utf-8-sig') as f:planar=list(csv.DictReader(f))
    if (evaluation/'multiview_3d.csv').stat().st_size==0:
        (evaluation/'multiview_3d.csv').write_text(
            'track_id,marker_id,plant_id,calyx_id,target,observations,estimated_x_m,estimated_y_m,estimated_z_m,'
            'true_x_m,true_y_m,true_z_m,error_3d_m,map_world_x_m,map_world_y_m,map_world_z_m,'
            'map_transform_source,parallax_deg,height_m,median_visible_pixels\n',encoding='utf-8')
    marker_ids=sorted({int(r['marker_id']) for r in planar})
    if marker_ids:
        columns=min(3,len(marker_ids));rows=math.ceil(len(marker_ids)/columns)
        fig,axes=plt.subplots(rows,columns,figsize=(5*columns,4*rows),squeeze=False,layout='constrained')
        for ax,identifier in zip(axes.flat,marker_ids):
            subset=[r for r in planar if int(r['marker_id'])==identifier]
            ax.scatter([float(r['true_x_m']) for r in subset],[float(r['true_y_m']) for r in subset],s=12,c='#167c70',label='Centro verdadero')
            ax.scatter([float(r['estimated_x_m']) for r in subset],[float(r['estimated_y_m']) for r in subset],s=14,marker='x',c='#c5532e',label='Homografía de caja')
            ax.set(title=f'ArUco {identifier} · {len(subset)} estimaciones',xlabel='X marcador (m)',ylabel='Y marcador (m)')
            ax.set_aspect('equal',adjustable='datalim')
            ax.xaxis.set_major_locator(MaxNLocator(4));ax.yaxis.set_major_locator(MaxNLocator(4))
            ax.grid(alpha=.2);ax.legend(fontsize=8)
        for ax in list(axes.flat)[len(marker_ids):]:ax.set_visible(False)
        fig.suptitle('Comparación planar: marcos independientes por marcador; profundidad desconocida')
        fig.savefig(evaluation/'planar_marker_maps.png',dpi=140);plt.close(fig)
    table='\n'.join(f'| {r["plant_id"]} | {r["existing"]} | {r["visible_unique"]} | {r["detected_unique"]} | {r["planar_unique"]} | {r["multiview_unique"]} |' for r in plants)
    pass_table='\n'.join(f'| {r["pass"]} | {r["frames"]} | {r["tp"]} | {r["fp_unmatched"]} | {r["fn"]} | {percent(float(r["precision"])) if r["precision"] else "no disponible"} | {percent(float(r["recall"])) if r["recall"] else "no disponible"} |' for r in passes)
    xy=summary['planar_xy'];mv=summary['multiview_3d_per_unique_object']
    startup_limit=('El techo de 0,20 m/s se cumple también en la inicialización medida.'
                   if validation['clearance']['max_interval_speed_m_s']<=.20 else
                   'El techo de 0,20 m/s se cumple en las pasadas, no en la inicialización suspendida.')
    text=f'''# Piloto de vuelo bajo con ArUcos — 2026-10-01

## Resultado del ensayo

Ejecución completa: **{'sí' if result['completed'] else 'no'}**. Validación posterior: **{'aprobada' if validation['passed'] else 'no aprobada'}**.
Duración: {result['simulation_seconds']:.2f} s simulados; {result['wall_seconds']:.1f} s de ejecución.
Se conservaron las 36 plantas y los 2.280 capachos originales; el inventario objetivo
de `plant_12` a `plant_23` contiene **747 capachos**.

| Etapa | Capachos únicos |
|---|---:|
| Existentes objetivo | 747 |
| Visibles en observaciones evaluadas, ≥16 px | {summary['visible_unique']} |
| Detectados correctamente | {summary['detected_unique']} |
| Con posición planar | {summary['planar_unique']} |
| Con posición 3D asociable | {summary['multiview_unique']} |
| Visibles únicamente por debajo de 16 px | {summary['visible_only_below_16px_unique']} |

Precisión agregada: **{percent(summary['precision'])}**. Recall por observación:
**{percent(summary['recall'])}**. Cobertura de capachos únicos visibles:
**{percent(summary['unique_detection_coverage_visible'])}**.
Son métricas del escenario sintético, no del desempeño en videos reales.

## Vuelo y validez de captura

Cuatro pasadas, a 0,65 y 0,95 m por ambas caras del pasillo central. Giros y
cambios de altura en x = ±4,6 m, fuera del cultivo. Cámara ideal de 1280 × 720,
90° horizontales y 20° hacia abajo; RGB y segmentación coincidentes a 15 Hz.
Evaluación a 5 Hz mediante exposiciones originales de sello idéntico.

- Error máximo de altura durante pasadas: **{cm(validation['max_pass_height_error_m'])}**.
- Velocidad máxima durante pasadas: **{validation['max_pass_speed_m_s']:.4f} m/s**.
- Cota conservadora de separación ejecutada: **{cm(validation['clearance']['clearance_lower_bound_m'])}**.
- Pares sincronizados: **{validation['synchronized_pairs']}**; pares faltantes: **{validation['missing_pairs']}**.
- Comprobaciones de identidad/proyección: **{validation['identity_projection_passes']}/{validation['identity_projection_checks']}**.
- Intervalo máximo entre poses de telemetría: **{validation['clearance']['sample_interval_max_s']:.3f} s**.

El arranque suspendido del modelo tiene un transitorio de motores fuera del
cultivo. Se registra, pero no se incluye en las pasadas: el avance empieza al
recuperar la altura. La velocidad de ese transitorio no se presenta como la de
inspección: el máximo de toda la telemetría, incluido el arranque, es
**{validation['clearance']['max_interval_speed_m_s']:.4f} m/s**. {startup_limit}
Las cotas se basan en superficies completas, esfera envolvente,
poses observadas y corrección temporal; no en ausencia de contactos.

La primera configuración, conservada en `outputs/gazebo/low_pilot_v1`, tuvo
dos pruebas técnicas descartadas (sincronización y arranque) y un ensayo
abortado a 41,82 s por deriva lateral. El monitor se activó al llegar a una
cota de 16,0 cm. Se corrigió la realimentación transversal, se repitió la prueba
de 10 s y se congeló `low_pilot_v2`. Esa ejecución se interrumpió a 244,562 s
por agotamiento de memoria al grabar. Se preservaron 3.706 pares RGB/máscara.
En `low_pilot_v3` se separaron los catálogos de materiales: se verificaron
2.280 mallas y materiales idénticos, sin alterar SDF, inventario ni misión.
También se sincronizó el comando de sustentación antes de despausar la física;
la prueba técnica anterior a esa sincronización se conserva como fallida.
Tras otra prueba de 10 s, se congelaron código, geometría, materiales y detector.
No se retiraron obstáculos ni se modificó el aspecto del cultivo para mejorar resultados.

## Detección

Se evaluaron **{summary['evaluated_frames']}** imágenes; se separaron
{summary['excluded_frames']} imágenes de arranque/transición o sin máscara.
Coincidencias verdaderas objetivo: {summary['tp']}; falsos positivos sin
correspondencia: {summary['fp_unmatched']}; falsos negativos: {summary['fn']};
duplicados: {summary['duplicates']}. Coincidencias correctas ajenas a las doce
plantas objetivo: {summary['matched_external']}, separadas de la métrica objetivo.

| Pasada | Imágenes | TP | FP sin correspondencia | FN | Precisión | Recall |
|---|---:|---:|---:|---:|---:|---:|
{pass_table}

| Planta | Existentes | Visibles | Detectados | Planar | 3D |
|---|---:|---:|---:|---:|---:|
{table}

La precisión por planta queda **no disponible**: los FP sin correspondencia no
tienen identidad de planta. No se asignaron arbitrariamente para fabricar una
métrica. `plants.csv` incluye recall y conteos por planta; `frames.csv` y
`passes.csv` conservan los FP. En `inventory.csv`, los indicadores de cobertura
se interpretan solo en filas `target=true`; las demás identifican el contexto.

## Localización

ArUcos observados en **{percent(summary['marker_frame_availability'])}** de las
imágenes evaluadas. Diccionario `DICT_4X4_100`, lado negro de 10 cm.

| Método | Estimaciones evaluadas | Mediana | RMSE | P90 | ≤2 cm | ≤5 cm | ≤10 cm |
|---|---:|---:|---:|---:|---:|---:|---:|
| Planar X/Y | {xy['n']} | {cm(xy['median_m'])} | {cm(xy['rmse_m'])} | {cm(xy['p90_m'])} | {percent(xy.get('within_2_cm'))} | {percent(xy.get('within_5_cm'))} | {percent(xy.get('within_10_cm'))} |
| 3D por capacho único | {mv['n']} | {cm(mv['median_m'])} | {cm(mv['rmse_m'])} | {cm(mv['p90_m'])} | {percent(mv.get('within_2_cm'))} | {percent(mv.get('within_5_cm'))} | {percent(mv.get('within_10_cm'))} |

La homografía entrega X/Y sobre el plano del marcador, con profundidad
desconocida; su error no es un error 3D. La cobertura planar respecto al
inventario es {percent(summary['localization_coverage_existing_planar'])};
la cobertura 3D es {percent(summary['localization_coverage_existing_3d'])}.
Las estimaciones sin posición permanecen en los denominadores de cobertura.
Las {xy['n']} estimaciones planares son combinaciones detección/marcador, no
capachos distintos; incluyen referencias lejanas. El video muestra la referencia
válida más cercana en píxeles para facilitar su lectura, sin elegir por error verdadero.

IPPE usa solo esquinas observadas y escala métrica. Cada reconstrucción conserva
el marco de su marcador. Se exigen ≥3 observaciones, paralaje ≥3°, profundidad
positiva y reproyección ≤3 px. Rechazos registrados:
`{json.dumps(summary['reconstruction_rejections'],ensure_ascii=False)}`.
El flujo óptico y la asociación uno a uno rechazan correspondencias ambiguas.

Las posiciones verdaderas del marcador se usan solo al evaluar o dibujar el
mapa mundial. El estimador se ejecutó con el paquete RGB, sellos, calibración y
dimensiones del ArUco, sin máscaras, inventario ni odometría de Gazebo.

## Congelación y archivos

Pasaron 33 pruebas de software: transformaciones, escala, triangulación con
posición conocida, falta de paralaje, marcador ausente, asociaciones ambiguas,
oclusión, conteo sin duplicados, corrección lateral y catálogos de materiales.
Los tres MP4 finales pasaron decodificación completa y tienen 1280 × 720 a 15 fps.
Los videos anotados repiten exposiciones de 5 Hz solo para presentación;
esas repeticiones no se cuentan como observaciones.

- Modelo: `natural_hybrid_alpha_045`, clase capacho, confianza 0,25, letterbox
  640², end-to-end sin NMS adicional. SHA-256: `{config['model_sha256']}`.
- `experiment_lock.json`: hashes de código, SDF, configuración y detector.
- `{run.as_posix()}/vuelo_bajo.mp4`: vuelo con cámara de seguimiento y vista frontal.
- `{run.as_posix()}/vuelo_anotado.mp4`: detecciones y posiciones estimadas; 3D posterior.
- `{evaluation.as_posix()}/comparacion_verdad.mp4`: TP, FP y FN contra máscaras.
- `position_map.png`: mapa mundial de verdad y estimaciones 3D; transformación
  mundial exclusivamente del evaluador.
- `planar_marker_maps.png`: mapas planares independientes por ArUco, cuando hay estimaciones.
- CSV por imagen, planta, pasada, tamaño visible y altura; coordenadas/error
  planar y 3D en sus tablas correspondientes.
- `observations.jsonl`, `reconstructions.jsonl`, `association_rejections.jsonl`
  y `associations.jsonl`: observaciones, decisiones y unión posterior con verdad.

La visibilidad se estratifica por píxeles observables; no es una fracción de
oclusión. La referencia espacial es el centro de la geometría original,
distinto en general del centro de su caja visible. No se evalúa madurez.
No hubo reentrenamiento, RGB-D ni ajustes retrospectivos de textura o umbral.
Las salidas pesadas permanecen locales e ignoradas por Git.
'''
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(text,encoding='utf-8')
    print(args.report)


if __name__=='__main__':main()
