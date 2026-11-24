"""Spanish report from persisted evidence, including incomplete and negative results."""
from collections import defaultdict
from pathlib import Path
import csv
import statistics
import numpy as np
from augmentation_pilot import ROOT, REPO, read, write


def report():
    results=read(ROOT/'evaluation/summary.json') if (ROOT/'evaluation/summary.json').exists() else {}
    matrix=read(ROOT/'matrix.json') if (ROOT/'matrix.json').exists() else []
    real=read(ROOT/'geometry/real_train.json')['summary']
    grouped=defaultdict(list);table=[]
    for name,value in results.items():
        completion=read(ROOT/'training'/name/'completion.json');cfg=completion['config']
        row=dict(run=name,arm=cfg['arm'],real_images=cfg['real_images'],synthetic_images=cfg['synthetic_images'],
            classical=cfg['classical'],seed=cfg['seed'],repeat_control=cfg.get('repeat_control',False),
            ap=value['ap']['map50_95'],ap50=value['ap']['map50'],ap75=value['ap']['map75'],
            collapsed_ap=value['collapsed_ap']['map50_95'],precision=value['fixed']['class_aware']['precision'],
            recall=value['fixed']['class_aware']['recall'],steps=completion['steps'],seconds=completion['seconds'],
            real_exposure=completion['exposure'].get('real',0),synthetic_exposure=completion['exposure'].get('synthetic',0))
        table.append(row);grouped[('repeat_' if row['repeat_control'] else '')+row['arm']].append(row)
    if table:
        with (ROOT/'results.csv').open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=list(table[0]));writer.writeheader();writer.writerows(table)
    lines=['# Piloto geométrico de aumentación — 22 de octubre de 2026','',
        '## Alcance y evidencia','',
        'Comparación de detección y clase de apariencia de capacho. No valida madurez interna ni generalización a una sesión externa. La prueba de desarrollo de 94 imágenes ya fue consultada históricamente. No se promovió ningún modelo a aplicaciones.', '',
        'Se conservaron 461/88/94 imágenes train/val/test y las exclusiones previas. Los subconjuntos anidados por grupos contienen 125, 210 y 461 imágenes (27,11 %, 45,55 % y 100 %). No se dividieron grupos para alcanzar porcentajes exactos.', '',
        '## Geometría antes de entrenar','',
        f"Entrenamiento real: {real['instances']} instancias; mediana {real['density']['p50']:.1f} instancias/imagen y {real['min_side_960']['p50']:.2f} px de lado menor a 960. Frecuencias <16/16–32/32–64/≥64 px: "+', '.join(f'{100*x:.2f} %' for x in real['size_fractions'])+'.', '',
        'Las estadísticas de cajas, centros, relación de aspecto, solapamiento y borde se calcularon solo en entrenamiento. Solapamiento de cajas y ocupación de máscara no se presentan como tasa de oclusión. La selección de cámaras no modifica arquitectura ni materiales de las plantas.', '',
        'Criterio revisado por instrucción del usuario antes del entrenamiento comparativo: error relativo ≤20 % en mediana de tamaño y diferencias ≤5 puntos porcentuales en cada intervalo de tamaño. La densidad es descriptiva y no bloquea admisión. Todas las instancias visibles, incluidas las diminutas, conservan etiqueta.', '',
        '## Matriz de ejecución','', '| Brazo | Reales | Sintéticas | Estado |','|---|---:|---:|---|']
    for a in matrix:
        done=(ROOT/'training'/('screen_'+a['arm'])/'completion.json').exists()
        state='screening completado' if done else a['status']
        lines.append(f"| {a['arm']} | {a['real_images']} | {a['synthetic_images']} | {state} |")
    lines+=['','## Resultados de finalistas','',
        'Cada entrenamiento final empieza desde yolo26n.pt, con 4.000 actualizaciones verificadas; selección del checkpoint por AP macro de validación cada 500 actualizaciones. Receta clásica: reflejo horizontal 0,5 y HSV-valor 0,1; sin alteración de tono. Los resultados solo describen esta receta.', '',
        '| Configuración | Semillas | AP50–95 media ± DE | AP colapsado | Recall fijo |','|---|---:|---:|---:|---:|']
    aggregates={}
    for arm,rows in grouped.items():
        avg=statistics.mean(r['ap'] for r in rows);std=statistics.stdev(r['ap'] for r in rows) if len(rows)>1 else 0
        aggregates[arm]=dict(n=len(rows),mean=avg,std=std)
        lines.append(f"| {arm} | {len(rows)} | {avg:.4f} ± {std:.4f} | {statistics.mean(r['collapsed_ap'] for r in rows):.4f} | {statistics.mean(r['recall'] for r in rows):.4f} |")
    if table:
        lines+=['','### Contrastes emparejados observados','']
        for arm,rows in grouped.items():
            if arm.startswith('repeat_'):continue
            baseline=arm.split('_s')[0]+'_s0_c0'
            if arm==baseline or baseline not in grouped:continue
            reference={r['seed']:r['ap'] for r in grouped[baseline]}
            deltas=[r['ap']-reference[r['seed']] for r in rows if r['seed'] in reference]
            if deltas:lines.append(f"- {arm} frente a {baseline}: Δ medio {100*statistics.mean(deltas):+.2f} puntos de AP, {len(deltas)} semillas emparejadas; rango {100*min(deltas):+.2f} a {100*max(deltas):+.2f}.")
    lines+=['','Los archivos por ejecución conservan AP por clase, confusión con fondo, recall por tamaño/densidad y exposición efectiva por dominio. AP final usa inferencia completa común a 960 y matching nativo de Ultralytics en IoU 0,50:0,95; el umbral operativo se fija únicamente con validación del baseline real completo. No se selecciona por test.', '',
        'Los intervalos emparejados usan 200 remuestreos de los mismos componentes de adquisición; no prueban independencia por sesión ni significancia confirmatoria. La variación entre semillas se muestra por separado. Una corrida incompleta no equivale a un resultado negativo.', '',
        '## Sugerencias para el generador sintético','']
    admitted=[a for a in matrix if a['synthetic_ratio']>0 and a['status']=='ready']
    if not admitted:
        lines+=['**No se admitió una mezcla sintética comparable.** Esto es un fallo de preparación geométrica, no evidencia de que la aumentación sintética empeore el detector. No se entrenaron mezclas rechazadas para llenar la tabla.', '',
            '1. Priorizar encuadres que reproduzcan la distribución de tamaños, especialmente la proporción de órganos diminutos del fondo. No borrar cajas pequeñas. Una mayor densidad por sí sola no invalida el banco.',
            '2. Ampliar la diversidad de plantas morfológicas de entrenamiento: repetir vistas de las mismas cuatro plantas no aumenta la diversidad arquitectónica.',
            '3. Después de resolver escala, evaluar fondos de maleza, hojas secas e iluminación con ablaciones independientes. Su utilidad sigue siendo una hipótesis, no un resultado medido aquí.']
    else:
        lines+=['1. Elegir la proporción sintética por validación y revisar su diferencia emparejada frente al control real y al control de repetición. No atribuir a sintéticos una mejora que también aparece al repetir imágenes reales.',
            '2. Revisar primero los estratos de tamaño/densidad y clases con menor AP en los archivos de evaluación; las recomendaciones específicas deben apoyarse en esos resultados.',
            '3. La calibración de cajas no elimina diferencias de textura, fondo, visibilidad ni diversidad entre plantas. Ensayar esos componentes por separado, conservando el banco geométrico como control.']
    lines+=['','## Artefactos y límites','',
        f'Campaña local: `{ROOT}`. `geometry/`, `admissions/`, `matrix.json`, `configs/`, `training/`, `evaluation/` y `results.csv` conservan procedencia y resultados. Pesos en `training/<ejecución>/weights/best.pt`.', '',
        'La prueba técnica inicial falló porque AMP omitió la primera actualización; quedó excluida. Se fijó una escala inicial conservadora para todos los brazos. Los tests y el validador del grafo tienen registros separados; no se infiere validación humana de las comprobaciones automáticas.', '']
    destination=REPO/'docs/reports/piloto_aumentacion_geometrica_2026-10-22.md'
    destination.write_text('\n'.join(lines),encoding='utf-8')
    write(ROOT/'aggregates.json',aggregates)
    if table:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,ax=plt.subplots(figsize=(10,5))
        for classic in [False,True]:
            rr=[r for r in table if r['classical']==classic and r['synthetic_images']==0 and not r['repeat_control']]
            xs=sorted({r['real_images'] for r in rr})
            ys=[statistics.mean(r['ap'] for r in rr if r['real_images']==x) for x in xs]
            errors=[statistics.stdev([r['ap'] for r in rr if r['real_images']==x]) if sum(r['real_images']==x for r in rr)>1 else 0 for x in xs]
            ax.errorbar(xs,ys,yerr=errors,marker='o',label='Clásica' if classic else 'Sin aumentación')
        ax.set(xlabel='Imágenes reales distintas',ylabel='AP50–95 macro (desarrollo)',title='Datos reales: media y desviación entre semillas');ax.legend();fig.tight_layout();fig.savefig(ROOT/'learning_curves.png',dpi=160);plt.close(fig)
        fig,ax=plt.subplots(figsize=(10,5))
        for n in sorted({r['real_images'] for r in table}):
            for classic in [False,True]:
                rr=[r for r in table if r['real_images']==n and r['classical']==classic and not r['repeat_control']]
                xs=sorted({r['synthetic_images']/n for r in rr})
                if not xs:continue
                ys=[statistics.mean(r['ap'] for r in rr if r['synthetic_images']/n==x) for x in xs]
                ax.plot(xs,ys,marker='o',label=f"{n} reales, clásica={classic}")
        ax.set(xlabel='Sintéticas / reales',ylabel='AP50–95 macro (desarrollo)',title='Proporciones admitidas y evaluadas');ax.legend();fig.tight_layout();fig.savefig(ROOT/'mixture_curves.png',dpi=160);plt.close(fig)
    print(destination)


if __name__=='__main__':report()
