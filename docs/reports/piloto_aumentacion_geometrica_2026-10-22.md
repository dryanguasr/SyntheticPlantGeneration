# Piloto geométrico de aumentación — 22 de octubre de 2026

## Alcance y evidencia

Comparación de detección y clase de apariencia de capacho. No valida madurez interna ni generalización a una sesión externa. La prueba de desarrollo de 94 imágenes ya fue consultada históricamente. No se promovió ningún modelo a aplicaciones.

Se conservaron 461/88/94 imágenes train/val/test y las exclusiones previas. Los subconjuntos anidados por grupos contienen 125, 210 y 461 imágenes (27,11 %, 45,55 % y 100 %). No se dividieron grupos para alcanzar porcentajes exactos.

## Geometría antes de entrenar

Entrenamiento real: 4723 instancias; mediana 7.0 instancias/imagen y 55.99 px de lado menor a 960. Frecuencias <16/16–32/32–64/≥64 px: 2.43 %, 27.14 %, 27.27 %, 43.15 %.

Las estadísticas de cajas, centros, relación de aspecto, solapamiento y borde se calcularon solo en entrenamiento. Solapamiento de cajas y ocupación de máscara no se presentan como tasa de oclusión. La selección de cámaras no modifica arquitectura ni materiales de las plantas.

Criterio revisado por instrucción del usuario antes del entrenamiento comparativo: error relativo ≤20 % en mediana de tamaño y diferencias ≤5 puntos porcentuales en cada intervalo de tamaño. La densidad es descriptiva y no bloquea admisión. Todas las instancias visibles, incluidas las diminutas, conservan etiqueta.

## Matriz de ejecución

| Brazo | Reales | Sintéticas | Estado |
|---|---:|---:|---|
| r100_s0_c0 | 461 | 0 | screening completado |
| r100_s0_c1 | 461 | 0 | screening completado |
| r100_s25_c0 | 461 | 115 | blocked_geometry_or_count |
| r100_s25_c1 | 461 | 115 | blocked_geometry_or_count |
| r100_s50_c0 | 461 | 230 | blocked_geometry_or_count |
| r100_s50_c1 | 461 | 230 | blocked_geometry_or_count |
| r100_s100_c0 | 461 | 461 | blocked_geometry_or_count |
| r100_s100_c1 | 461 | 461 | blocked_geometry_or_count |
| r50_s0_c0 | 210 | 0 | screening completado |
| r50_s0_c1 | 210 | 0 | screening completado |
| r50_s25_c0 | 210 | 52 | blocked_geometry_or_count |
| r50_s25_c1 | 210 | 52 | blocked_geometry_or_count |
| r50_s50_c0 | 210 | 105 | blocked_geometry_or_count |
| r50_s50_c1 | 210 | 105 | blocked_geometry_or_count |
| r50_s100_c0 | 210 | 210 | blocked_geometry_or_count |
| r50_s100_c1 | 210 | 210 | blocked_geometry_or_count |
| r25_s0_c0 | 125 | 0 | screening completado |
| r25_s0_c1 | 125 | 0 | screening completado |
| r25_s25_c0 | 125 | 31 | blocked_geometry_or_count |
| r25_s25_c1 | 125 | 31 | blocked_geometry_or_count |
| r25_s50_c0 | 125 | 62 | blocked_geometry_or_count |
| r25_s50_c1 | 125 | 62 | blocked_geometry_or_count |
| r25_s100_c0 | 125 | 125 | blocked_geometry_or_count |
| r25_s100_c1 | 125 | 125 | blocked_geometry_or_count |

## Resultados de finalistas

Cada entrenamiento final empieza desde yolo26n.pt, con 4.000 actualizaciones verificadas; selección del checkpoint por AP macro de validación cada 500 actualizaciones. Receta clásica: reflejo horizontal 0,5 y HSV-valor 0,1; sin alteración de tono. Los resultados solo describen esta receta.

| Configuración | Semillas | AP50–95 media ± DE | AP colapsado | Recall fijo |
|---|---:|---:|---:|---:|
| r100_s0_c0 | 3 | 0.1850 ± 0.0046 | 0.4105 | 0.6789 |
| r100_s0_c1 | 3 | 0.1847 ± 0.0066 | 0.3964 | 0.7138 |
| r50_s0_c0 | 3 | 0.1724 ± 0.0049 | 0.3795 | 0.6387 |
| r50_s0_c1 | 3 | 0.1607 ± 0.0074 | 0.3800 | 0.5878 |
| r25_s0_c0 | 3 | 0.1409 ± 0.0059 | 0.3467 | 0.4468 |
| r25_s0_c1 | 3 | 0.1429 ± 0.0149 | 0.3613 | 0.4695 |

### Contrastes emparejados observados

- r100_s0_c1 frente a r100_s0_c0: Δ medio -0.03 puntos de AP, 3 semillas emparejadas; rango -1.11 a +1.12.
- r50_s0_c1 frente a r50_s0_c0: Δ medio -1.17 puntos de AP, 3 semillas emparejadas; rango -2.31 a -0.60.
- r25_s0_c1 frente a r25_s0_c0: Δ medio +0.20 puntos de AP, 3 semillas emparejadas; rango -1.26 a +2.46.

Los archivos por ejecución conservan AP por clase, confusión con fondo, recall por tamaño/densidad y exposición efectiva por dominio. AP final usa inferencia completa común a 960 y matching nativo de Ultralytics en IoU 0,50:0,95; el umbral operativo se fija únicamente con validación del baseline real completo. No se selecciona por test.

Los intervalos emparejados usan 200 remuestreos de los mismos componentes de adquisición; no prueban independencia por sesión ni significancia confirmatoria. La variación entre semillas se muestra por separado. Una corrida incompleta no equivale a un resultado negativo.

## Sugerencias para el generador sintético

**No se admitió una mezcla sintética comparable.** Esto es un fallo de preparación geométrica, no evidencia de que la aumentación sintética empeore el detector. No se entrenaron mezclas rechazadas para llenar la tabla.

1. Priorizar encuadres que reproduzcan la distribución de tamaños, especialmente la proporción de órganos diminutos del fondo. No borrar cajas pequeñas. Una mayor densidad por sí sola no invalida el banco.
2. Ampliar la diversidad de plantas morfológicas de entrenamiento: repetir vistas de las mismas cuatro plantas no aumenta la diversidad arquitectónica.
3. Después de resolver escala, evaluar fondos de maleza, hojas secas e iluminación con ablaciones independientes. Su utilidad sigue siendo una hipótesis, no un resultado medido aquí.

## Artefactos y límites

Campaña local: `C:\dev\SyntheticPlantGeneration\outputs\augmentation_pilot_20261022`. `geometry/`, `admissions/`, `matrix.json`, `configs/`, `training/`, `evaluation/` y `results.csv` conservan procedencia y resultados. Pesos en `training/<ejecución>/weights/best.pt`.

La prueba técnica inicial falló porque AMP omitió la primera actualización; quedó excluida. Se fijó una escala inicial conservadora para todos los brazos. Los tests y el validador del grafo tienen registros separados; no se infiere validación humana de las comprobaciones automáticas.
