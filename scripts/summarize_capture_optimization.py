"""Production-cost projection from measured paired captures, not GPU guesses."""
from pathlib import Path
import sys,json,math,statistics
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.nodal_automation import read,write,sha


def project(folder,mode,remaining,build_seconds):
    complete=read(folder/mode/'complete.json')
    stages=read(folder/mode/'timings.json')['stages']
    observed=[v['active_seconds'] for v in complete['views']]
    batches=math.ceil(remaining/24)
    cold=batches;warm=remaining-cold
    warm_mean=statistics.mean(observed[1:])
    process=read(folder/(mode+'_job.json'))['total_process_active_seconds']
    # Remove the extra baseline self-repeat from production startup costs.
    repeat=read(folder/'baseline_repeat/complete.json')['active_seconds'] if mode=='optimized' and (folder/'baseline_repeat/complete.json').exists() else 0.
    external=max(0.,process-complete['total_active_seconds']-repeat)
    # A fresh build already computes its initial historical hash and warms
    # hidden organs inside its ground audit. Loading/refreshing the benchmark
    # fixture and its additional initial/final common QA guards are not charged
    # again as generation. The optimized production entry retains a final full
    # guard, session preparation, and one consolidated manifest per scene.
    extra=sum(s['active_seconds'] for s in stages if mode=='optimized' and s['stage'] in
              {'prepare_capture_session','final_full_geometry_guard','consolidate_manifest_once'})
    fixed=build_seconds+external+extra
    total=batches*fixed+cold*observed[0]+warm*warm_mean
    low=batches*(.8*build_seconds+external+extra)+cold*observed[0]+warm*min(observed[1:])
    high=batches*(1.2*build_seconds+external+extra)+cold*observed[0]+warm*max(observed[1:])
    return dict(capture_seconds=observed,capture_mean_seconds=statistics.mean(observed),
        warm_capture_mean_seconds=warm_mean,cold_captures=cold,warm_captures=warm,
        scenes=batches,scene_build_seconds=build_seconds,extra_per_scene_seconds=external+extra,
        estimated_remaining_active_hours=total/3600,
        planning_range_active_hours=[low/3600,high/3600],
        range_provenance='engineering envelope: observed warm-view extremes and +/-20% scene preparation; not confidence interval',
        one_off_repeat_control_seconds_excluded=repeat)


def main(source,optimized):
    acceptance=read(optimized/'quality_acceptance.json')
    if not acceptance['numeric_rgb_equivalence']:raise ValueError('Cannot project accepted optimization before quality gate')
    comparison=read(optimized/'comparison.json');build=read(source/'prepare_timings.json')['stages'][0]['active_seconds']
    b=project(source,'baseline',856,build);o=project(optimized,'optimized',856,build)
    result=dict(existing_images=144,target_images=1000,remaining_images=856,
        baseline=b,optimized=o,production_speedup=b['estimated_remaining_active_hours']/o['estimated_remaining_active_hours'],
        raw_capture_speedup=b['capture_mean_seconds']/o['capture_mean_seconds'],
        quality_acceptance=acceptance,
        conditions='one twelve-plant/four-row scene, three depths/lighting conditions; same meshes/cameras/materials/12 samples/960x720/denoising',
        limits=['one measured preparation, three paired captures, no statistical timing confidence interval',
                'same 24-view process recycling and independent full scene admission retained',
                'phase entry provides one scene per process; controller deployment is separate',
                'benchmark captures are not added to the 144-image production bank',
                'no training, efficacy estimate or untouched test evaluation'])
    write(optimized/'production_estimate.json',result)
    cases=comparison['comparisons']
    table='\n'.join(f"| {c['depth']} / {c['diagnostic_light']} | {b['capture_seconds'][i]:.1f} | {o['capture_seconds'][i]:.1f} | {c['rgb']['changed_pixels']} | {c['rgb']['max_channel_error']} | {c['mask']['changed_pixels']} |" for i,c in enumerate(cases))
    report=f'''# Optimización y medición de captura — 29 de octubre de 2026

Se implementaron captura con buffers de geometría, registro/paleta persistentes,
luces reutilizables, cuantización con arrays y journal por vista. La variante
adicional conserva la caché de Cycles y rasteriza máscaras en otra escena que
comparte exactamente los mismos objetos y colecciones. No se modificaron
árboles, órganos, materiales, resolución, muestras ni denoising. No hubo un
nuevo entrenamiento ni se amplió la campaña cerrada de 144 imágenes.

Un control del método original mostró un cambio importante de rendimiento
del equipo después de la interrupción. Por eso se repitieron tanto la
referencia como la preparación con el rendimiento actual. Las tablas y
proyecciones usan esa comparación posterior, no atribuyen al algoritmo la
aceleración general del sistema. Los intentos anteriores quedan preservados.

## Comparación medida

| Profundidad / luz | Original, s | Optimizada, s | Píxeles RGB distintos | Máximo RGB, niveles de 255 | Píxeles de máscara distintos |
|---|---:|---:|---:|---:|---:|
{table}

Media por captura: **{b['capture_mean_seconds']:.1f} → {o['capture_mean_seconds']:.1f} s**
({result['raw_capture_speedup']:.2f}×). Tres vistas de una sola escena no
constituyen una distribución representativa de tiempos. La primera captura
incluye arranque frío; las otras dos sirven como aproximación al régimen
reutilizable. La resolución se mantiene en 960×720, Cycles/OptiX, 12 muestras
y denoising. Las tres condiciones de luz, dirección solar y exposición se
emparejaron entre métodos; su semilla es independiente de plantas y cámaras.

Las máscaras, cajas, clases, IDs, etiquetas YOLO y parámetros emparejados deben
ser exactos. **RGB no es necesariamente idéntico bit a bit**: se informa el
error completo y se usa un criterio numérico de ingeniería de máximo 1/255 y
error absoluto medio ≤0,001 niveles de byte por canal. No es un umbral
botánico, físico ni una prueba de eficacia. Control de repetición del método
original: {acceptance['baseline_self_repeat']}.

## Estimación para completar 1.000

Se conservan **144 imágenes**; faltan **856**, equivalentes a 36 bloques de
hasta 24 vistas. Reconstruir y auditar la escena medida costó **{build/60:.2f}
minutos efectivos**. Esta preparación se conserva en el pronóstico; no se
supone que la GPU sea el único coste ni se omiten auditorías.

| Proyección | Original | Optimizada |
|---|---:|---:|
| Horas efectivas adicionales | {b['estimated_remaining_active_hours']:.1f} | {o['estimated_remaining_active_hours']:.1f} |
| Envolvente de planificación, h | {b['planning_range_active_hours'][0]:.1f}–{b['planning_range_active_hours'][1]:.1f} | {o['planning_range_active_hours'][0]:.1f}–{o['planning_range_active_hours'][1]:.1f} |

Se carga una captura fría por bloque y las demás al coste medio de las dos
vistas posteriores. El rango combina sus extremos y ±20 % de preparación,
como margen de ingeniería, **no como intervalo de confianza**. La suspensión
no cuenta en el reloj nativo; el calendario puede ser mayor. Se excluye el
control de repetición de calidad, que es trabajo de diagnóstico de este ensayo,
y no se vuelve a cargar la lectura del fixture ni su guarda inicial como si
fueran una segunda generación. Los números conservadores de `comparison.json`
incluyen costes del harness; `production_estimate.json` describe la proyección
ajustada al flujo de producción y sus límites.

## Integridad, incidencias y alcance

Los veinte árboles fuente permanecen intactos; doce están presentes en esta
escena. Las auditorías efectivas conservan cero cruces duros, suelo de 1 mm y
orientación/unión válida. Hoja–hoja y proximidades conservan su tratamiento
anterior; contexto/flores no tienen certificación exhaustiva.

Se preservaron dos intentos que rechazaron hashes antes de renderizar. La
causa identificada es la caché de transformaciones de frutos internos ocultos
al recargar: quedan fuera del grafo de evaluación de viewport. La actualización
usa el mismo ciclo temporal de visibilidad del auditor de suelo, restaurando
las banderas originales y sin tocar `hide_render`. Las auditorías de malla,
suelo y orientación antes/después de recarga fueron iguales. No se relajó
ninguna tolerancia física ni de anotación.

La primera corrida optimizada quedó interrumpida tras una vista completa y
una segunda parcial. Windows registra parada/reinicio de CodexSandboxService
el 29/10 a las 23:13:21–24 de Bogotá, coincidente con la desaparición de sus
procesos; no se encontró un error de Blender. Se preservaron fuentes, logs,
parcial y lock huérfano. Esa corrida **no se cuenta como ensayo completo**.
La referencia completa se reutilizó en una revisión independiente, con un
control adicional de repetición RGB del método original.

Todos los capachos visibles válidos permanecen en máscara y metadatos,
incluidos los diminutos. La exclusión de pequeños corresponde al consumidor
de entrenamiento con política explícita; no se simplificaron ni retiraron
objetos del RGB. El exportador histórico tiene filtros de 6 píxeles y 24
píxeles visibles; no se atribuyen automáticamente al entrenador factorial ni
se fija una nueva política de entrenamiento en este benchmark.

## Artefactos y comprobaciones

- `outputs/capture_optimization_20261029`: preparación, referencia y evidencia
  de los intentos anteriores, incluidos archivos y fuentes preservados.
- `outputs/capture_optimization_dual_20261029`: tres capturas optimizadas,
  repetición RGB, `comparison.json`, `quality_acceptance.json`,
  `production_estimate.json` y galería `review.html`.
- Diez pruebas puras cubren cambios de geometría, flags de frutos ocultos,
  cuantización/transparencia, materiales, condiciones y commits.
- El grafo se valida separando diez errores preexistentes de localizadores;
  no deben atribuirse a esta intervención ni repararse sobrescribiendo trabajo
  ajeno. No se generaron 1.000 imágenes ni se inició entrenamiento.
'''
    path=ROOT/'docs/reports/optimizacion_captura_2026-10-29.md';path.write_text(report,encoding='utf-8')
    write(optimized/'report_manifest.json',dict(report=str(path),sha256=sha(path),analysis_source_sha256=sha(__file__),
        inputs={str(p):sha(p) for p in [source/'baseline/complete.json',source/'prepare_timings.json',
              optimized/'optimized/complete.json',optimized/'quality_acceptance.json',optimized/'comparison.json']}))
    print(json.dumps({k:result[k] for k in ['production_speedup','raw_capture_speedup']},indent=2))
    print('production_hours',b['estimated_remaining_active_hours'],o['estimated_remaining_active_hours'],o['planning_range_active_hours'])


if __name__=='__main__':main(*[Path(p).resolve() for p in sys.argv[1:]])
