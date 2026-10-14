"""Spanish report of the controlled texture test and completed physical flight."""
import argparse
import csv
import json
import math
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    p=argparse.ArgumentParser();p.add_argument('--comparison',type=Path,required=True);p.add_argument('--run',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    ab=json.loads((a.comparison/'texture_ab.json').read_text());result=json.loads((a.run/'result.json').read_text())
    telemetry=json.loads((a.run/'telemetry.json').read_text());trace=telemetry['samples']
    detection=json.loads((a.run/'detection_summary.json').read_text())
    peak_tilt=max(math.degrees(abs(s[k])) for s in trace for k in ('roll','pitch'))
    speeds=[math.dist(x['position'],y['position'])/(y['t']-x['t']) for x,y in zip(trace,trace[1:]) if y['t']>x['t']]
    passes=[r for r in telemetry['reached'] if r['phase'].endswith('_pass')]
    continuous_margin=min(min(x['clearance_lower_bound_m'],y['clearance_lower_bound_m'])-math.dist(x['position'],y['position'])/2 for x,y in zip(trace,trace[1:]))
    if not result['completed'] or len(passes)!=12 or continuous_margin<.15:
        raise RuntimeError('Full flight or piecewise-linear executed clearance validation failed')
    summary={**result,'completed_row_faces':len(passes),'peak_roll_pitch_deg':peak_tilt,'peak_measured_speed_m_s':max(speeds),
             'executed_piecewise_linear_clearance_lower_bound_m':continuous_margin}
    (a.run/'flight_summary.json').write_text(json.dumps(summary,indent=2))
    with (a.run/'completed_passes.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['index','phase','t']);writer.writeheader();writer.writerows(passes)
    fig,(ax,az)=plt.subplots(1,2,figsize=(12,5))
    ax.scatter([(c-2.5)*1.4 for r in range(6) for c in range(6)],[(r-2.5)*1.8 for r in range(6) for c in range(6)],c='forestgreen',label='36 plantas')
    ax.plot([s['position'][0] for s in trace],[s['position'][1] for s in trace],lw=1,label='Recorrido ejecutado')
    ax.set(xlabel='X (m)',ylabel='Y (m)',title='Doce caras, giros fuera de los extremos');ax.axis('equal');ax.legend()
    az.plot([s['t'] for s in trace],[s['position'][2] for s in trace]);az.set(xlabel='Tiempo simulado (s)',ylabel='Altura (m)',title='Altura ejecutada');az.grid(alpha=.3)
    fig.tight_layout();fig.savefig(a.run/'route.png',dpi=160);plt.close(fig)
    rows=[]
    names={'flat_legacy':'Material anterior (diagnóstico)','flat_pbr':'Color plano, mismo PBR','textured':'Albedo texturizado'}
    for key,stats in ab['summary'].items():
        rows.append(f'| {names[key]} | {stats["visible"]} | {stats["tp"]} | {stats["fp"]} | {stats["fn"]} | {100*stats["recall"]:.3f} % |')
    sizes=json.loads((a.comparison/'texture_size_analysis.json').read_text())['rows']
    size_rows=[]
    for group in ('<16','16-31','32-63','>=64'):
        before=next(r for r in sizes if r['variant']=='flat_pbr' and r['sqrt_bbox_area_px']==group)
        after=next(r for r in sizes if r['variant']=='textured' and r['sqrt_bbox_area_px']==group)
        size_rows.append(f'| {group} | {after["visible"]} | {before["tp"]} | {after["tp"]} | {100*after["recall"]:.2f} % |')
    # Reproducible illustration, explicitly one selected view out of all 24.
    records=[json.loads(s) for s in (a.comparison/'texture_ab_observations.jsonl').read_text().splitlines()]
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',24)
    board=Image.new('RGB',(1600,555),'#eceee6');draw=ImageDraw.Draw(board)
    draw.text((20,12),'Gazebo: color plano / albedo texturizado | misma vista y visibilidad',font=font,fill='black')
    for col,variant in enumerate(('flat_pbr','textured')):
        image=Image.open(a.comparison/('ab_'+variant)/'010_rgb.png').convert('RGB');d=ImageDraw.Draw(image)
        record=next(v for v in records if v['variant']==variant and v['frame_id']==10)
        for box in record['detections']:
            d.rectangle(box['box_xyxy_px'],outline='#6aff88',width=3)
            d.text((box['box_xyxy_px'][0],max(0,box['box_xyxy_px'][1]-28)),f"{box['confidence']:.0%}",font=font,fill='#6aff88')
        board.paste(image.resize((800,450)),(col*800,62))
        row=next(v for v in ab['frames'] if v['variant']==variant and v['index']==10)
        draw.text((col*800+15,523),f'{"Color plano" if col==0 else "Con texturas"}: {row["tp"]} aciertos; {row["visible"]} referencias visibles',font=font,fill='black')
    board.save(a.comparison/'texture_comparison.jpg',quality=94)
    comparison=a.comparison.as_posix();run=a.run.as_posix()
    report=f'''# Vuelo por hileras y prueba de texturas — 2026-10-02

El Neo completó **{len(passes)}/12 caras** con movimiento físico por motores,
sin cambios directos de pose. Se conservaron 36 plantas, 23.385 hojas,
2.340 capachos, ArUcos y tutorado. Las texturas mejoraron modestamente la
detección, pero el desempeño continúa siendo insuficiente.

## Video y recorrido

- [Video completo a 4×, con cámara del dron y vista de seguimiento](../../{run}/vuelo_completo_4x.mp4).
- [Cámara original a velocidad simulada](../../{run}/onboard.mp4).
- [Seguimiento del Neo](../../{run}/chase.mp4).
- [Muestras anotadas a aproximadamente 1 Hz, reproducidas a 4×](../../{run}/annotated_samples_4x.mp4).
- [Recorrido y altura medidos](../../{run}/route.png).

Duración simulada: {result['simulation_seconds']:.1f} s.
Margen mínimo monitorizado: {result['minimum_executed_margin_m']:.3f} m.
Cota conservadora entre poses ejecutadas, con interpolación lineal: {continuous_margin:.3f} m.
Máximo absoluto de roll/pitch: {peak_tilt:.2f}°.
Velocidad máxima medida entre poses: {max(speeds):.3f} m/s.
Tiempo de ejecución, incluido arranque: {result['wall_seconds']:.1f} s.
Se completaron {result['waypoints_reached']}/{result['waypoints_expected']} puntos.

La cámara ideal usa 1280×720, 15 fps, 60° horizontales y 15° hacia abajo.
**No reproduce la cámara de fábrica del DJI Neo** ni permite extrapolar estas
distancias a ese hardware. Los pasillos se recorrieron a 0,65 o 0,80 m, a
0,9 m de los ejes de hilera. Los giros se hicieron fuera de X = ±4,8 m.
La distribución sigue siendo 1,4 m entre plantas y 1,8 m entre hileras;
no se recalibró a los aproximadamente 3 m observados por el usuario.

## Comparación controlada de apariencia

24 vistas por variante, mismos puntos y parámetros. RGB y máscaras tienen
sellos simulados idénticos. El IoU de las máscaras entre control PBR y
texturas fue **{min(ab['paired_mask_iou']):.3f} en el peor par**.
La rugosidad se mantiene igual en ambos: la diferencia controlada es el albedo.
Cambian tanto el color medio como el detalle espacial; no se aísla el efecto
exclusivo de las nervaduras.
El material anterior sin PBR cambió la cobertura visible y se reporta aparte;
no se usó para afirmar un efecto aislado de textura.

| Variante | Observaciones visibles | Aciertos | FP | FN | Recall |
|---|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

Son **observaciones por imagen**, con repeticiones entre vistas e incluyendo
plantas de fondo, no capachos únicos. Se usan máscaras con ≥16 píxeles visibles
y coincidencias uno a uno con IoU ≥0,5. No observar FP en sólo 10 detecciones
no demuestra una precisión general del 100 %.

El detector sigue siendo `natural_hybrid_alpha_045`, SHA-256
`{ab['model_sha256']}`. Entrada RGB con letterbox 640×640, confianza 0,25,
salida end-to-end, sin NMS adicional ni reentrenamiento. Las máscaras no se
entregaron al estimador; entraron únicamente en la evaluación posterior.

### Tamaño aparente (análisis descriptivo posterior)

La medida es la raíz del área de la caja visible en el RGB original, no tamaño
físico ni tasa de oclusión. La mayoría de referencias son pequeñas o de fondo.

| Tamaño equivalente (px) | Visibles | Aciertos planos | Aciertos texturizados | Recall texturizado |
|---|---:|---:|---:|---:|
{chr(10).join(size_rows)}

[Comparación ilustrativa de la vista 10](../../{comparison}/texture_comparison.jpg).
Se seleccionó porque muestra dos aciertos; los resultados de la tabla incluyen
las 24 vistas, no sólo el ejemplo favorable.

## Detecciones durante el vuelo completo

Se analizaron {detection['counts']['frames']} imágenes RGB originales, con
{detection['counts']['detections']} detecciones acumuladas en
{detection['counts']['frames_with_detections']} imágenes. No son objetos únicos
ni aciertos verificados: este video completo no dispone de máscaras de
instancia en la copia agrupada. Las métricas de precisión/recall proceden
exclusivamente de la prueba A/B individualizada.
Los MP4 pueden repetir cuadros para presentación; no se utilizaron esas
repeticiones como observaciones independientes. Las posiciones planares que
guarda el motor de la app no constituyen localización 3D validada en este ensayo.

## Geometría, rendimiento y límites

La malla de inspección tiene 5.824.267 triángulos y conserva 107.159 objetos
geométricos con procedencia. La prueba de silueta de tres plantas dio IoU
0,974–0,979, con menos de 0,6 % de cambio de cobertura frente a la exportación
previa. Para grabar se agruparon exactamente triángulos, UV y normales en
19 materiales; el paquete individualizado quedó preservado para máscaras.

Las mallas completas, sin ese LOD, sirvieron para auditar el recorrido. La
física final usa 36 envolventes conservadoras para los ejes principales:
contienen los cilindros originales, con radio máximo de unos 4,33 cm. Se
volvió a comprobar la trayectoria contra ellas. Se conservan tutorado y
paneles; no se podó ni desactivó un obstáculo para habilitar el vuelo.
El controlador utiliza odometría de Gazebo; no es navegación autónoma con RGB.

Los contactos internos pendientes de v4 siguen pendientes. La prueba no
valida botánica, madurez, fuerzas de cosecha, sensores reales ni transferencia
al cultivo real. La mejora de 2 a 10 aciertos es exploratoria, con muestra
pequeña, y no demuestra significación estadística. Los fallos y la primera
comparación de máscaras no equivalente se conservaron.

## Archivos de evaluación

- [CSV por vista](../../{comparison}/texture_ab.csv).
- [Métricas A/B y comprobación de máscaras](../../{comparison}/texture_ab.json).
- [Observaciones JSONL](../../{comparison}/texture_ab_observations.jsonl).
- [Resumen del vuelo](../../{run}/flight_summary.json).
- [Doce pasadas completadas](../../{run}/completed_passes.csv).
- [Detecciones RGB del vuelo](../../{run}/detections.jsonl).
- [Validación de videos](../../{run}/video_validation.json).

La implementación y los comandos se describen en
[la guía de reproducción](../guides/vuelo_hileras_texturas.md).
'''
    a.report.write_text(report,encoding='utf-8');print(a.report)

if __name__=='__main__':main()
