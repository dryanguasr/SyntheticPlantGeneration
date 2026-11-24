# Optimización y medición de captura — ensayo del 29 de octubre de 2026

Cierre y revisión final: 30 de octubre de 2026, America/Bogota.

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
| Cercana / difusa | 103.5 | 61.6 | 73 | 1 | 0 |
| Intermedia / sombra | 104.4 | 57.6 | 64 | 1 | 0 |
| Lejana / campo | 122.9 | 55.6 | 71 | 1 | 0 |

Media por captura: **110.3 → 58.2 s**
(1.89×). Tres vistas de una sola escena no
constituyen una distribución representativa de tiempos. La primera captura
incluye arranque frío; las otras dos sirven como aproximación al régimen
reutilizable. La resolución se mantiene en 960×720, Cycles/OptiX, 12 muestras
y denoising. Las tres condiciones de luz, dirección solar y exposición se
emparejaron entre métodos; su semilla es independiente de plantas y cámaras.

Las máscaras, cajas, clases, IDs, etiquetas YOLO y parámetros emparejados deben
ser exactos. **RGB no es necesariamente idéntico bit a bit**: se informa el
error completo y se usa un criterio numérico de ingeniería de máximo 1/255 y
error absoluto medio ≤0,001 niveles de byte por canal. No es un umbral
botánico, físico ni una prueba de eficacia. El control de repetición del método original cambió 85 de 691.200 píxeles, también con máximo 1/255. La variante optimizada cambió 64–73 píxeles por vista; ambas variaciones son numéricamente pequeñas y se informan, sin declarar igualdad RGB bit a bit.

## Estimación para completar 1.000

Se conservan **144 imágenes**; faltan **856**, equivalentes a 36 bloques de
hasta 24 vistas. Reconstruir y auditar la escena medida costó **7.28
minutos efectivos**. Esta preparación se conserva en el pronóstico; no se
supone que la GPU sea el único coste ni se omiten auditorías.

| Proyección | Original | Optimizada |
|---|---:|---:|
| Horas efectivas adicionales | 31.4 | 18.6 |
| Envolvente de planificación, h | 28.4–34.4 | 17.5–19.7 |

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
- Once pruebas puras cubren cambios de geometría, flags de frutos ocultos,
  cuantización/transparencia, materiales, condiciones y commits.
- El grafo se valida separando diez errores preexistentes de localizadores;
  no deben atribuirse a esta intervención ni repararse sobrescribiendo trabajo
  ajeno. No se generaron 1.000 imágenes ni se inició entrenamiento.

La comparación de tiempos primaria, con referencia y preparación repetidas bajo el rendimiento actual, está en `outputs/capture_optimization_matched_20261029`. El conjunto de producción sigue en 144 imágenes; los renders de diagnóstico no se suman como nuevas vistas independientes. La entrada reutilizable es `scripts/render_spatial_dataset_persistent.py`; no se ejecutó una tanda masiva.
