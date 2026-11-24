# Piloto exploratorio con aumentación sintética — 22 de octubre de 2026

## Resultado del cierre — 26 de octubre de 2026

**Piloto completado: 24 screenings, 18 finalistas sintéticos, 18 controles reales y tres controles de repetición. La mejora frente al control real con clásica se mantiene en las tres semillas, pero no queda confirmado un aporte consistente del contenido sintético frente a repetir imágenes reales.**

La mezcla seleccionada previamente por validación es **461 reales + 115 sintéticas, con clásica**. En las 94 imágenes de test de desarrollo obtiene AP50–95 macro **20,81 ± 1,65 %**, frente a **18,47 ± 0,66 %** con real + clásica y **19,94 ± 3,57 %** con repetición real. Media ± DE entre tres semillas; no son intervalos de confianza.

| Comparación de la mezcla seleccionada | Δ semilla 20261022 | Δ semilla 20261023 | Δ semilla 20261024 | Δ media |
|---|---:|---:|---:|---:|
| Frente a real con igual clásica | +1,19 | +2,06 | +3,77 | **+2,34** |
| Frente a repetición real emparejada | −0,36 | −2,56 | +5,55 | **+0,88** |

Diferencias en puntos porcentuales de AP. El intervalo exploratorio por grupos de la diferencia media es [+1,29; +3,42] frente a real con clásica y [−0,67; +2,81] frente a repetición. Solo hay seis grupos de adquisición, muy desiguales; los intervalos están condicionados a las tres semillas entrenadas y a la presencia de las tres clases. No prueban independencia entre sesiones ni generalización externa. El test ya se había consultado durante desarrollo y no se usó para elegir la mezcla ni sus pesos.

La diferencia media positiva frente a repetición depende de una sola semilla favorable y presenta DE de **4,19 puntos**. No recomendar un cambio de modelo ni atribuir el beneficio exclusivamente al contenido sintético con esta evidencia. El contraste evita atribuir al contenido sintético una ventaja que no se mantiene de forma estable frente a otro muestreo de imágenes reales.

**Madura empeora aunque suba el AP macro:** −0,81 puntos frente a real con clásica y −1,59 frente a repetición. Pintona mejora +2,39 y Sobremadura +5,44 puntos frente a real con clásica. Por ello la próxima iteración debe revisar la correspondencia visual de las clases, especialmente Madura, y conservar métricas por clase como condición de interpretación. Son etiquetas de apariencia del capacho, no madurez interna validada.


## Alcance y evidencia

Comparación de detección y clase de apariencia de capacho. No valida madurez interna ni generalización a una sesión externa. La prueba de desarrollo de 94 imágenes ya fue consultada históricamente. No se promovió ningún modelo a aplicaciones.

Se conservaron 461/88/94 imágenes train/val/test y las exclusiones previas. Los subconjuntos anidados por grupos contienen 125, 210 y 461 imágenes (27,11 %, 45,55 % y 100 %). No se dividieron grupos para alcanzar porcentajes exactos.

## Geometría antes de entrenar

Entrenamiento real: 4723 instancias; mediana 7.0 instancias/imagen y 55.99 px de lado menor a 960. Frecuencias <16/16–32/32–64/≥64 px: 2.43 %, 27.14 %, 27.27 %, 43.15 %.

Las estadísticas de cajas, centros, relación de aspecto, solapamiento y borde se calcularon solo en entrenamiento. Solapamiento de cajas y ocupación de máscara no se presentan como tasa de oclusión. La selección de cámaras no modifica arquitectura ni materiales de las plantas.

El usuario autorizó expresamente entrenar con las imágenes disponibles pese al incumplimiento de tamaños. Se conservaron los diagnósticos originales: estas mezclas NO son geométricamente validadas. Densidad y tamaños se reportan como limitaciones; todas las etiquetas visibles permanecen.


Comparación del banco completo (tamaños medidos al redimensionar a 960):

| Medida | Real train | Sintético disponible |
|---|---:|---:|
| Imágenes / instancias | 461 / 4723 | 389 / 6718 |
| Mediana de lado menor (px) | 55.99 | 52.50 |
| Mediana de instancias por imagen | 7 | 13 |
| <16 px | 2.43 % | 19.98 % |
| 16–32 px | 27.14 % | 15.91 % |
| 32–64 px | 27.27 % | 20.77 % |
| ≥64 px | 43.15 % | 43.35 % |
| Proporción de instancias Pintona | 76.24 % | 35.08 % |
| Proporción de instancias Madura | 16.07 % | 43.76 % |
| Proporción de instancias Sobremadura | 7.69 % | 21.15 % |

La mediana global similar no compensa el exceso de objetos diminutos ni la distinta representación de clases. Los diagnósticos por brazo en `admissions/` conservan desglose espacial y por clase; la autorización de entrenar no convierte esos desajustes en equivalencia.

![Encuadres reales y sintéticos](../../outputs/augmentation_pilot_20261022/visual_review_size_pairs/pares_2.jpg)

## Matriz de ejecución

| Brazo | Reales | Sintéticas | Estado |
|---|---:|---:|---|
| r100_s0_c0 | 461 | 0 | screening completado |
| r100_s0_c1 | 461 | 0 | screening completado |
| r100_s25_c0 | 461 | 115 | screening completado |
| r100_s25_c1 | 461 | 115 | screening completado |
| r100_s50_c0 | 461 | 230 | screening completado |
| r100_s50_c1 | 461 | 230 | screening completado |
| r100_s100_c0 | 461 | 389 | screening completado |
| r100_s100_c1 | 461 | 389 | screening completado |
| r50_s0_c0 | 210 | 0 | screening completado |
| r50_s0_c1 | 210 | 0 | screening completado |
| r50_s25_c0 | 210 | 52 | screening completado |
| r50_s25_c1 | 210 | 52 | screening completado |
| r50_s50_c0 | 210 | 105 | screening completado |
| r50_s50_c1 | 210 | 105 | screening completado |
| r50_s100_c0 | 210 | 210 | screening completado |
| r50_s100_c1 | 210 | 210 | screening completado |
| r25_s0_c0 | 125 | 0 | screening completado |
| r25_s0_c1 | 125 | 0 | screening completado |
| r25_s25_c0 | 125 | 31 | screening completado |
| r25_s25_c1 | 125 | 31 | screening completado |
| r25_s50_c0 | 125 | 62 | screening completado |
| r25_s50_c1 | 125 | 62 | screening completado |
| r25_s100_c0 | 125 | 125 | screening completado |
| r25_s100_c1 | 125 | 125 | screening completado |

## Resultados de finalistas

Cada entrenamiento final empieza desde yolo26n.pt, con 4.000 actualizaciones verificadas; selección del checkpoint por AP macro de validación cada 500 actualizaciones. Receta clásica: reflejo horizontal 0,5 y HSV-valor 0,1; sin alteración de tono. Los resultados solo describen esta receta.

| Configuración | Semillas | AP50–95 media ± DE | AP colapsado | Recall fijo |
|---|---:|---:|---:|---:|
| r100_s0_c0 | 3 | 0.1850 ± 0.0046 | 0.4105 | 0.6789 |
| r100_s0_c1 | 3 | 0.1847 ± 0.0066 | 0.3964 | 0.7138 |
| r100_s100_c0 | 3 | 0.2089 ± 0.0098 | 0.4200 | 0.6984 |
| r100_s25_c1 | 3 | 0.2081 ± 0.0165 | 0.4169 | 0.7522 |
| r25_s0_c0 | 3 | 0.1409 ± 0.0059 | 0.3467 | 0.4468 |
| r25_s0_c1 | 3 | 0.1429 ± 0.0149 | 0.3613 | 0.4695 |
| r25_s50_c0 | 3 | 0.1483 ± 0.0050 | 0.3671 | 0.5092 |
| r25_s50_c1 | 3 | 0.1449 ± 0.0072 | 0.3636 | 0.5288 |
| r50_s0_c0 | 3 | 0.1724 ± 0.0049 | 0.3795 | 0.6387 |
| r50_s0_c1 | 3 | 0.1607 ± 0.0074 | 0.3800 | 0.5878 |
| r50_s100_c0 | 3 | 0.1746 ± 0.0100 | 0.3953 | 0.6311 |
| r50_s100_c1 | 3 | 0.1785 ± 0.0242 | 0.4145 | 0.6775 |
| repeat_r100_s25_c1 | 3 | 0.1994 ± 0.0357 | 0.4059 | 0.7239 |

### Contrastes emparejados observados

- r100_s0_c1 frente a r100_s0_c0: Δ medio -0.03 puntos de AP, 3 semillas emparejadas; rango -1.11 a +1.12.
- r100_s100_c0 frente a r100_s0_c0: Δ medio +2.39 puntos de AP, 3 semillas emparejadas; rango +1.77 a +3.38.
- r100_s25_c1 frente a r100_s0_c0: Δ medio +2.31 puntos de AP, 3 semillas emparejadas; rango +0.08 a +3.67.
- r25_s0_c1 frente a r25_s0_c0: Δ medio +0.20 puntos de AP, 3 semillas emparejadas; rango -1.26 a +2.46.
- r25_s50_c0 frente a r25_s0_c0: Δ medio +0.74 puntos de AP, 3 semillas emparejadas; rango +0.02 a +1.82.
- r25_s50_c1 frente a r25_s0_c0: Δ medio +0.40 puntos de AP, 3 semillas emparejadas; rango -0.43 a +1.29.
- r50_s0_c1 frente a r50_s0_c0: Δ medio -1.17 puntos de AP, 3 semillas emparejadas; rango -2.31 a -0.60.
- r50_s100_c0 frente a r50_s0_c0: Δ medio +0.22 puntos de AP, 3 semillas emparejadas; rango -1.05 a +1.59.
- r50_s100_c1 frente a r50_s0_c0: Δ medio +0.61 puntos de AP, 3 semillas emparejadas; rango -1.99 a +3.03.

Los archivos por ejecución conservan AP por clase, confusión con fondo, recall por tamaño/densidad y exposición efectiva por dominio. AP final usa inferencia completa común a 960 y matching nativo de Ultralytics en IoU 0,50:0,95; el umbral operativo se fija únicamente con validación del baseline real completo. No se selecciona por test.

Los intervalos emparejados usan 200 remuestreos de los mismos componentes de adquisición; no prueban independencia por sesión ni significancia confirmatoria. La variación entre semillas se muestra por separado. Una corrida incompleta no equivale a un resultado negativo.

## Sugerencias para el generador sintético

1. Elegir la proporción sintética por validación y revisar su diferencia emparejada frente al control real y al control de repetición. No atribuir a sintéticos una mejora que también aparece al repetir imágenes reales.
2. Revisar primero los estratos de tamaño/densidad y clases con menor AP en los archivos de evaluación; las recomendaciones específicas deben apoyarse en esos resultados.
3. La calibración de cajas no elimina diferencias de textura, fondo, visibilidad ni diversidad entre plantas. Ensayar esos componentes por separado, conservando el banco geométrico como control.

## Artefactos y límites

Campaña local: `C:\dev\SyntheticPlantGeneration\outputs\augmentation_pilot_20261022\synthetic_exploratory_extension`. `geometry/`, `admissions/`, `matrix.json`, `configs/`, `training/`, `evaluation/` y `results.csv` conservan procedencia y resultados. Pesos en `training/<ejecución>/weights/best.pt`.

La prueba técnica inicial falló porque AMP omitió la primera actualización; quedó excluida. Se fijó una escala inicial conservadora para todos los brazos. Los tests y el validador del grafo tienen registros separados; no se infiere validación humana de las comprobaciones automáticas.

## Desajuste sintético y proporciones efectivas

Banco: 389 imágenes disponibles, incluidas las 12 vistas de calibración, procedentes exclusivamente de plantas train. Las cantidades se anidan sobre el orden previo, sin usar test para elegirlas. No hay nuevos renders.

Las proporciones son sintéticas/reales, no porcentaje del total. Para 461 reales se usan 115, 230 y 389 sintéticas: 24,95 %, 49,89 % y 84,38 %; no se inventan las 72 imágenes faltantes para llegar a 100 %. Para 210 reales: 52, 105 y 210; para 125: 31, 62 y 125.

La sobreabundancia de instancias diminutas, la apariencia simplificada de fondos/hojas, las oclusiones y las cuatro plantas de origen limitan la interpretación. Una mejora o caída mide el efecto de este banco disponible, no el de un generador geométricamente emparejado ni generalización externa.

Los controles reales se reutilizan por hash: mismo modelo inicial, pasos, semillas, optimizador, resolución y receta clásica. El presupuesto inicial se amplió por autorización del usuario el 23 de octubre y nuevamente el 26 de octubre para completar tres repeticiones y la evaluación; los presupuestos, cierres e intentos anteriores se conservaron. Las cifras intermedias de validación ya se habían consultado antes de esta extensión solicitada por el usuario; se conserva su carácter exploratorio.

## Confirmación final con tres controles de repetición

Se verificaron 24 screenings de 2.000 actualizaciones, 18 finalistas sintéticos, 18 controles reales heredados y tres controles de repetición, estos últimos 39 entrenamientos de 4.000 actualizaciones. Todos conservan la inicialización, receta, datos y calendario de aprendizaje congelados. Las tres semillas son 20261022, 20261023 y 20261024.

La mezcla seleccionada antes del test por mayor AP medio de validación fue `r100_s25_c1`. No se cambió el ganador al consultar el test. La autorización del 26 de octubre permite terminar los pendientes; no aporta nuevas imágenes ni cambia el protocolo. Los cierres incompletos y el primer control truncado permanecen archivados.

En cada repetición se conservaron los 8.000 puestos planificados y las muestras reales originales de su mezcla emparejada. Cada puesto sintético se sustituyó por una imagen real: exposición sintética efectiva cero y exposición real 8.000. El campo nominal `synthetic_images` de su configuración identifica la mezcla de referencia, no imágenes sintéticas realmente consumidas.

### Diferencias emparejadas con la misma receta clásica

| Mezcla | Referencia | Δ semillas (puntos AP) | Δ medio ± DE | Intervalo por grupos de la media |
|---|---|---|---:|---:|
| r100_s100_c0 | r100_s0_c0 | +1.77, +2.00, +3.38 | +2.39 ± 0.87 | [-1.02, +7.63] |
| r100_s25_c1 | r100_s0_c1 | +1.19, +2.06, +3.77 | +2.34 ± 1.31 | [+1.29, +3.42] |
| r25_s50_c0 | r25_s0_c0 | +1.82, +0.37, +0.02 | +0.74 ± 0.95 | [-2.59, +3.25] |
| r25_s50_c1 | r25_s0_c1 | -2.12, +1.89, +0.83 | +0.20 ± 2.08 | [-1.59, +1.33] |
| r50_s100_c0 | r50_s0_c0 | +1.59, +0.12, -1.05 | +0.22 ± 1.32 | [-1.52, +2.11] |
| r50_s100_c1 | r50_s0_c1 | +1.39, +0.32, +3.64 | +1.78 ± 1.69 | [-0.81, +4.89] |
| r100_s25_c1 | repeat_r100_s25_c1 | -0.36, -2.56, +5.55 | +0.88 ± 4.19 | [-0.67, +2.81] |

La DE resume variación entre las tres diferencias de semillas emparejadas. El intervalo percentil usa 200 remuestreos comunes de seis grupos y promedia las diferencias de esas tres semillas ya entrenadas. No es un intervalo para nuevas semillas ni para sesiones independientes. Los grupos contienen 25, 48, 15, 3, 2 y 1 imágenes; son pocos y muy desiguales.

El remuestreo complementario conserva las tres clases en cada réplica, rechazando y registrando sorteos sin alguna clase para evitar que cambie el denominador del AP macro. El bootstrap original del evaluador congelado se preserva por separado; incluye una réplica sin Madura y solo compara con real sin clásica. Ninguno de estos intervalos demuestra significación confirmatoria ni independencia por sesión.

![Diferencias emparejadas](C:/dev/SyntheticPlantGeneration/outputs/augmentation_pilot_20261022/synthetic_exploratory_extension/confirmation_evaluation_20261026/paired_test_comparisons.png)

### Resultados por semilla y clase

AP50–95, AP colapsado y valores por clase están expresados en porcentaje. P/R usan el umbral común elegido exclusivamente en validación.

| Ejecución | AP | Pintona | Madura | Sobremadura | Colapsado | P | R | Exposición real/sintética |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| final_r100_s0_c0_20261022 | 18.93 | 39.17 | 8.25 | 9.35 | 42.25 | 36.06 | 65.13 | 8000/0 |
| final_r100_s0_c0_20261023 | 18.01 | 36.17 | 8.61 | 9.24 | 39.32 | 30.71 | 64.50 | 8000/0 |
| final_r100_s0_c0_20261024 | 18.57 | 39.47 | 7.38 | 8.84 | 41.57 | 28.66 | 74.03 | 8000/0 |
| final_r100_s0_c1_20261022 | 17.81 | 34.92 | 8.44 | 10.07 | 37.59 | 30.08 | 69.11 | 8000/0 |
| final_r100_s0_c1_20261023 | 19.13 | 36.99 | 11.85 | 8.56 | 38.89 | 24.25 | 78.12 | 8000/0 |
| final_r100_s0_c1_20261024 | 18.47 | 40.55 | 8.97 | 5.89 | 42.46 | 33.51 | 66.91 | 8000/0 |
| final_r100_s100_c0_20261022 | 20.70 | 42.76 | 10.27 | 9.06 | 44.63 | 37.24 | 70.26 | 4332/3668 |
| final_r100_s100_c0_20261023 | 20.01 | 35.59 | 8.34 | 16.11 | 38.62 | 30.26 | 70.37 | 4349/3651 |
| final_r100_s100_c0_20261024 | 21.95 | 40.73 | 10.72 | 14.39 | 42.75 | 33.81 | 68.90 | 4329/3671 |
| final_r100_s25_c1_20261022 | 19.00 | 39.91 | 9.08 | 8.02 | 42.87 | 27.57 | 75.50 | 6412/1588 |
| final_r100_s25_c1_20261023 | 21.20 | 36.89 | 9.53 | 17.17 | 39.28 | 25.08 | 78.32 | 6404/1596 |
| final_r100_s25_c1_20261024 | 22.24 | 42.84 | 8.23 | 15.64 | 42.93 | 32.93 | 71.83 | 6402/1598 |
| final_r25_s0_c0_20261022 | 13.55 | 30.47 | 4.69 | 5.50 | 33.56 | 44.32 | 42.93 | 8000/0 |
| final_r25_s0_c0_20261023 | 14.00 | 33.53 | 5.85 | 2.61 | 36.49 | 46.71 | 46.81 | 8000/0 |
| final_r25_s0_c0_20261024 | 14.72 | 31.02 | 5.89 | 7.25 | 33.97 | 46.13 | 44.29 | 8000/0 |
| final_r25_s0_c1_20261022 | 16.01 | 35.94 | 7.53 | 4.57 | 39.82 | 40.84 | 54.87 | 8000/0 |
| final_r25_s0_c1_20261023 | 13.40 | 31.62 | 4.67 | 3.90 | 35.21 | 45.64 | 43.35 | 8000/0 |
| final_r25_s0_c1_20261024 | 13.46 | 31.52 | 5.57 | 3.28 | 33.36 | 36.97 | 42.62 | 8000/0 |
| final_r25_s50_c0_20261022 | 15.37 | 34.94 | 5.97 | 5.19 | 37.79 | 40.50 | 52.67 | 5346/2654 |
| final_r25_s50_c0_20261023 | 14.37 | 35.37 | 2.64 | 5.11 | 37.46 | 46.68 | 49.32 | 5348/2652 |
| final_r25_s50_c0_20261024 | 14.74 | 34.04 | 4.34 | 5.85 | 34.87 | 42.40 | 50.79 | 5352/2648 |
| final_r25_s50_c1_20261022 | 13.89 | 33.33 | 5.77 | 2.58 | 36.03 | 35.98 | 55.92 | 5346/2654 |
| final_r25_s50_c1_20261023 | 15.29 | 32.14 | 6.71 | 7.02 | 35.16 | 33.58 | 51.83 | 5348/2652 |
| final_r25_s50_c1_20261024 | 14.28 | 35.09 | 4.24 | 3.53 | 37.89 | 42.86 | 50.89 | 5352/2648 |
| final_r50_s0_c0_20261022 | 16.69 | 36.66 | 7.44 | 5.97 | 38.14 | 40.63 | 56.54 | 8000/0 |
| final_r50_s0_c0_20261023 | 17.62 | 34.97 | 9.20 | 8.71 | 36.48 | 31.61 | 65.24 | 8000/0 |
| final_r50_s0_c0_20261024 | 17.40 | 38.02 | 7.21 | 6.96 | 39.24 | 28.14 | 69.84 | 8000/0 |
| final_r50_s0_c1_20261022 | 16.09 | 35.60 | 6.60 | 6.08 | 37.79 | 47.38 | 50.16 | 8000/0 |
| final_r50_s0_c1_20261023 | 15.32 | 33.73 | 8.43 | 3.78 | 34.92 | 29.15 | 66.07 | 8000/0 |
| final_r50_s0_c1_20261024 | 16.79 | 38.75 | 4.02 | 7.60 | 41.28 | 41.47 | 60.10 | 8000/0 |
| final_r50_s100_c0_20261022 | 18.28 | 37.80 | 7.86 | 9.18 | 39.74 | 28.00 | 69.11 | 3999/4001 |
| final_r50_s100_c0_20261023 | 17.74 | 36.44 | 8.62 | 8.16 | 39.67 | 41.57 | 58.85 | 4004/3996 |
| final_r50_s100_c0_20261024 | 16.35 | 37.26 | 6.48 | 5.30 | 39.19 | 34.94 | 61.36 | 4000/4000 |
| final_r50_s100_c1_20261022 | 17.48 | 39.89 | 7.11 | 5.44 | 43.97 | 36.00 | 66.91 | 3999/4001 |
| final_r50_s100_c1_20261023 | 15.63 | 36.74 | 5.85 | 4.31 | 40.09 | 26.40 | 68.90 | 4004/3996 |
| final_r50_s100_c1_20261024 | 20.43 | 38.83 | 12.13 | 10.32 | 40.29 | 34.98 | 67.43 | 4000/4000 |
| repeat_final_r100_s25_c1_20261022 | 19.37 | 39.65 | 11.12 | 7.33 | 42.85 | 31.23 | 73.51 | 8000/0 |
| repeat_final_r100_s25_c1_20261023 | 23.75 | 39.09 | 15.00 | 17.17 | 41.21 | 33.64 | 68.80 | 8000/0 |
| repeat_final_r100_s25_c1_20261024 | 16.69 | 35.64 | 5.47 | 8.95 | 37.72 | 24.37 | 74.87 | 8000/0 |

### Errores y prioridades para el siguiente piloto

Las siguientes observaciones describen el test de desarrollo de la mezcla seleccionada; las causas propuestas requieren otra ablación. Las confusiones completas, incluyendo fondo, se conservan para cada semilla en `evaluation/<ejecución>/summary.json`.

- **Clase:** el AP medio menor del ganador corresponde a Madura (8.95 %). Priorizar revisión de correspondencia de apariencia, textura y color de capacho con ejemplos reales; no interpretar estas etiquetas como madurez interna validada.
- **Tamaño:** recall de localización con clase correcta, promedio entre semillas: 16-32: 35.5 % (n=46 instancias); 32-64: 63.4 % (n=410 instancias); >=64: 78.6 % (n=499 instancias). Es recall por estrato, no AP por estrato ni estimación de oclusión física.
- **Densidad:** recall de localización con clase correcta, promedio entre semillas: 1-7: 62.8 % (n=157 instancias); 8-22: 73.1 % (n=653 instancias); >22: 63.7 % (n=145 instancias). Es recall por estrato, no AP por estrato ni estimación de oclusión física.
- **Geometría y exposición:** el banco mantiene exceso de objetos diminutos y distinta mezcla de clases; las 389 imágenes proceden de cuatro plantas. Igualar actualizaciones no iguala exposición a reales ni a instancias. Ensayar cámaras y visibilidad por clase, y más plantas con menos vistas repetidas, sin agrandar órganos ni eliminar etiquetas visibles.
- **Fondos y maleza:** las escenas reales de plantas descuidadas contienen espacios abiertos, maleza y distractores. Su importancia causal no se aisló aquí. Próxima ablación: cruzar follaje del cultivo denso/ralo con maleza escasa/abundante, manteniendo el resto fijo y anotando cobertura real antes de ajustar.
- **Texturas e iluminación:** la revisión visual previa detectó vegetación virtual oscura, fondos más uniformes y diferencias en apariencia de capachos maduros/sobremaduros. Comparar materiales bajo luz neutra común y después bajo luz de campo separa hipótesis de material y exposición. Un aumento global de brillo no demuestra equivalencia de apariencia.
- **Validación futura:** repetir con nuevas plantas y sesiones separadas antes de afirmar generalización externa. No seleccionar la siguiente proporción por estos resultados de test; conservar una nueva evaluación independiente para el siguiente experimento.

### Evidencia del cierre

Auditoría, entradas por hash, comparaciones, diseños de remuestreo y gráfico: `C:\dev\SyntheticPlantGeneration\outputs\augmentation_pilot_20261022\synthetic_exploratory_extension\confirmation_evaluation_20261026`. Los pesos siguen en `training/<ejecución>/weights/best.pt`; `paired_comparisons.json` registra sus hashes y exposición por imágenes e instancias. Las duraciones guardadas son tiempo de pared y pueden incluir suspensiones; no se presentan como cómputo efectivo.

La revisión visual de curvas y muestras y la validación del grafo se documentan en el cierre del controlador. Esta posproducción no vuelve a entrenar, no ejecuta inferencia y no promueve modelos.

## Revisión final de curvas, muestras y matriz completa

Las tres mezclas ganadoras alcanzan su mejor AP de validación a 1.500 pasos. Los controles reales correspondientes lo alcanzan a 1.500/1.500/2.000 y las repeticiones a 2.000/2.500/1.000. Todos terminaron las 4.000 actualizaciones; se evaluó el mejor checkpoint según la regla congelada, no necesariamente el último. Después de esos máximos las curvas fluctúan y suelen caer: más pasos, por sí solos, no muestran mejora sostenida. Esta observación es compatible con sobreajuste o variabilidad del conjunto de validación, sin aislar su causa.

![Curvas de validación](../../outputs/augmentation_pilot_20261022/synthetic_exploratory_extension/confirmation_evaluation_20261026/validation_curves_review.png)

![Curvas de screening](../../outputs/augmentation_pilot_20261022/synthetic_exploratory_extension/confirmation_evaluation_20261026/screening_curves_review.png)

El gráfico automático `mixture_curves.png` solo conecta controles y proporciones finalistas evaluadas en test: las líneas no son una interpolación validada ni significan admisión geométrica. La figura de screening anterior sí muestra las 24 configuraciones con una semilla y selección por validación.

| Brazo de screening | Reales | Sintéticas | Proporción efectiva | AP50–95 validación (%) |
|---|---:|---:|---:|---:|
| r100_s0_c0 | 461 | 0 | 0.00 % | 23.670 |
| r100_s0_c1 | 461 | 0 | 0.00 % | 24.180 |
| r100_s25_c0 | 461 | 115 | 24.95 % | 23.184 |
| r100_s25_c1 | 461 | 115 | 24.95 % | 22.905 |
| r100_s50_c0 | 461 | 230 | 49.89 % | 23.460 |
| r100_s50_c1 | 461 | 230 | 49.89 % | 21.938 |
| r100_s100_c0 | 461 | 389 | 84.38 % | 24.664 |
| r100_s100_c1 | 461 | 389 | 84.38 % | 22.513 |
| r50_s0_c0 | 210 | 0 | 0.00 % | 19.758 |
| r50_s0_c1 | 210 | 0 | 0.00 % | 19.793 |
| r50_s25_c0 | 210 | 52 | 24.76 % | 18.333 |
| r50_s25_c1 | 210 | 52 | 24.76 % | 21.424 |
| r50_s50_c0 | 210 | 105 | 50.00 % | 20.477 |
| r50_s50_c1 | 210 | 105 | 50.00 % | 21.743 |
| r50_s100_c0 | 210 | 210 | 100.00 % | 22.838 |
| r50_s100_c1 | 210 | 210 | 100.00 % | 22.370 |
| r25_s0_c0 | 125 | 0 | 0.00 % | 15.535 |
| r25_s0_c1 | 125 | 0 | 0.00 % | 16.497 |
| r25_s25_c0 | 125 | 31 | 24.80 % | 16.630 |
| r25_s25_c1 | 125 | 31 | 24.80 % | 15.361 |
| r25_s50_c0 | 125 | 62 | 49.60 % | 17.866 |
| r25_s50_c1 | 125 | 62 | 49.60 % | 18.257 |
| r25_s100_c0 | 125 | 125 | 100.00 % | 15.797 |
| r25_s100_c1 | 125 | 125 | 100.00 % | 17.773 |

### Efecto de la receta clásica en controles reales

| Imágenes reales | Sin clásica, AP medio (%) | Con clásica, AP medio (%) | Δ media (puntos) | Δ por semilla (puntos) |
|---:|---:|---:|---:|---|
| 125 | 14.09 | 14.29 | +0.20 | +2.46 / -0.60 / -1.26 |
| 210 | 17.24 | 16.07 | -1.17 | -0.60 / -2.31 / -0.61 |
| 461 | 18.50 | 18.47 | -0.03 | -1.11 / +1.12 / -0.10 |

La receta de reflejo horizontal y HSV-valor no mejora uniformemente: con 210 reales baja en las tres semillas. La conclusión se limita a esta receta y este test de desarrollo, no a toda aumentación clásica.

### Qué muestran las predicciones

Se inspeccionaron cuatro ejemplos de la semilla 20261022 elegidos por extremos de diferencia de F1 por imagen entre mezcla y repetición, incluyendo clases minoritarias. Esta selección se declara en `review_metrics.json`: sirve para diagnóstico y no estima una frecuencia representativa de errores. Las figuras contienen todas las predicciones que superan el mismo umbral de validación (0,05806), cajas reales en blanco discontinuo y predicciones por clase en color.

- Fila 472, escena abierta con suelo, maleza y cuerdas: mezcla 5 TP / 25 FP / 0 FN; repetición 5 / 7 / 0. Recuperar todos los objetos anotados no evita falsas detecciones en el contexto. Los FP son respecto de las anotaciones existentes; esta revisión no adjudica posibles objetos sin anotar.
- Fila 111, frutos cercanos con hojas y tallos: mezcla 11 / 7 / 2 frente a repetición 8 / 18 / 5. Hay ejemplos favorables de localización/clasificación, pero no dominan todas las escenas.
- Fila 324, tres capachos amarillentos sostenidos en una mano: mezcla 1 / 5 / 2 frente a repetición 2 / 4 / 1. Persisten confusiones entre Pintona y Madura incluso cuando los objetos son grandes.
- Fila 393, capachos de apariencia variada y vegetación seca: mezcla 7 / 9 / 2 frente a repetición 5 / 13 / 4. La mejora de detección no elimina solapamientos de predicciones ni errores de clase.

![Muestras 472 y 111](../../outputs/augmentation_pilot_20261022/synthetic_exploratory_extension/confirmation_evaluation_20261026/prediction_review_1.png)

![Muestras 324 y 393](../../outputs/augmentation_pilot_20261022/synthetic_exploratory_extension/confirmation_evaluation_20261026/prediction_review_2.png)

![Confusiones](../../outputs/augmentation_pilot_20261022/synthetic_exploratory_extension/confirmation_evaluation_20261026/confusions_review.png)

La confusión usa emparejamiento por localización sin exigir clase para mostrar errores entre clases; sus diagonales pueden diferir de TP del emparejamiento que exige clase usado en precisión/recall. El color de la figura es logarítmico y los números son conteos medios por corrida, no porcentajes.

La mezcla eleva recall medio de 71,38 % a 75,22 % frente al control real con clásica, mientras precisión baja de 29,28 % a 28,53 %. En Madura, los falsos positivos por imagen suben de 1,66 a 2,84 al umbral común. No se reajustó ese umbral con test. AP colapsado de la mezcla 41,69 % frente a macro 20,81 % indica una dificultad importante de clasificación además de la localización, sin demostrar por sí solo su causa. No hay objetos <16 px en este test; no permite validar mejoras en ese estrato, aunque abunde en entrenamiento sintético.

### Prioridades aplicables al siguiente piloto

1. **Equivalencia de apariencia, empezando por Madura.** Preparar paneles de referencias reales de entrenamiento y materiales bajo luz neutra común; medir color/textura en regiones revisadas y separar color del capacho, iluminación y fondo. Ajustar parámetros solo después de comprobar esa correspondencia. La revisión humana de etiquetas y cualquier equivalencia normativa siguen siendo necesarias.
2. **Fondos y falsos positivos.** Incorporar vegetación acompañante, hojas secas, suelo y cuerdas como factores controlados; comparar uchuva rala/frondosa y maleza escasa/abundante manteniendo cámaras y clases. Los ejemplos apoyan investigar este factor, no certifican que la maleza cause el resultado agregado.
3. **Escala por clase y diversidad.** Corregir por cámara el exceso de cajas diminutas y el tamaño de Madura/Sobremadura; diversificar las cuatro plantas de origen manteniendo la arquitectura morfológica, sin agrandar órganos ni borrar instancias válidas. Densidad permanece descriptiva según la autorización del usuario.
4. **Exposición y controles.** Conservar repetición real, semillas emparejadas y presupuesto de pasos; estudiar por separado igualdad de cómputo e igualdad de exposición real. No fijar una nueva dosis óptima a partir de este test ni confundir el número de imágenes con aporte por instancias.
5. **Siguiente evaluación.** Validar con nuevas plantas/sesiones y negativos revisados. La auditoría adicional que el usuario indicó haber subido el 26/10 sigue pendiente de ruta/rama/enlace tras la búsqueda inicial; no se presenta el diagnóstico del 23/10 como esa nueva auditoría ni se inicia otra campaña en este cierre.

### Cierre técnico y conservación

Los tres controles añadidos terminaron a 4.000 pasos, ocho secuencias y 8.000 imágenes reales cada uno. Se verificó identidad de los procesos y al terminar no quedó entrenamiento activo. Fuentes, pesos, 24 screenings, 39 finales, semillas, aislamiento, selección y secuencias emparejadas quedaron auditados; los intentos incompletos anteriores permanecen en revisiones y recuperación. El entrenador congelado no cambió. El validador del grafo conserva sus diez errores preexistentes y no añade errores nuevos.

Las figuras de revisión se generaron exclusivamente a partir de métricas y predicciones persistidas, sin nueva inferencia. El informe automático y el suplemento anterior a esta revisión se conservan en `confirmation_evaluation_20261026/`. La ampliación autorizada se utilizó solo para terminar los pendientes; no hubo nuevos renders ni promoción del modelo.

Tiempos de los tres controles de repetición completos: 20261022: 15.99 min, 20261023: 15.39 min, 20261024: 15.25 min. Desde arranque del controlador hasta evaluación y complemento: 52.46 min de pared. Los tiempos históricos con suspensiones permanecen separados en los archivos de cada corrida.

![Cantidad de datos reales](../../outputs/augmentation_pilot_20261022/synthetic_exploratory_extension/learning_curves.png)

![Proporciones finalistas evaluadas](../../outputs/augmentation_pilot_20261022/synthetic_exploratory_extension/mixture_curves.png)

La segunda figura conserva el título automático «admitidas», que aquí significa ejecutadas por excepción autorizada: no aprobación geométrica. Solo muestra las proporciones finalistas, no toda la curva de dosis ni un óptimo nuevo seleccionado en test.
