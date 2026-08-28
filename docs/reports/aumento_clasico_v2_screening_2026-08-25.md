# Classical Augmentation v2 — screening de 3 semillas

## Estado

Screening completo: 9 escenarios × 3 semillas × 30 épocas (27/27 corridas).
La selección se hizo únicamente con `val`; `test_consulted=false` en el
resumen reproducible. El checkpoint se escogió por mAP50-95 de validación.

Fuente numérica: `outputs/classical_augmentation_v2/metrics/screening/screening_summary.json`.

## Resultados agregados

| escenario | mAP50-95 media ± DE | precisión | recall | recall @ P≥0.98 | tiempo activo medio (s) |
|---|---:|---:|---:|---:|---:|
| V2-E0 | 0.547897 ± 0.010135 | 0.877243 | 0.693090 | 0.535948 | 763.7 |
| V2-E0R | 0.549690 ± 0.003421 | 0.881140 | 0.726813 | 0.543210 | 737.2 |
| V2-E2 | 0.547263 ± 0.008987 | 0.882470 | 0.709153 | 0.543936 | 1153.7 |
| V2-E3 | 0.544523 ± 0.013622 | 0.891373 | 0.707543 | 0.586057 | 1207.1 |
| V2-E4 | 0.533023 ± 0.009622 | 0.880300 | 0.688373 | 0.565723 | 1164.4 |
| V2-E5 | 0.553297 ± 0.006936 | 0.904027 | 0.722300 | 0.577342 | 2855.7 |
| V2-E6 | 0.555490 ± 0.011417 | 0.872987 | 0.720093 | 0.562092 | 1143.0 |
| V2-E7 | 0.556020 ± 0.011515 | 0.917827 | 0.702463 | 0.586783 | 49456.7* |
| V2-E8 | 0.534770 ± 0.005546 | 0.900960 | 0.687727 | 0.539579 | 1187.5 |

`*` El tiempo de V2-E7 está contaminado por una suspensión del equipo; no se
interpreta como coste computacional normal.

## Selección para confirmación

La regla fijada antes de observar los resultados usa suma de rangos no ponderada
en mAP50-95 medio, delta emparejado frente a V2-E0R, número de semillas con
delta positivo, delta de recall operacional y peor delta por tamaño. Los tres
finalistas son:

1. **V2-E7** — rango 6; delta mAP50-95 vs E0R = +0.006330; 2/3 semillas positivas.
2. **V2-E3** — rango 15; delta = −0.005167; mejora operacional media +0.042847.
3. **V2-E6** — rango 16; delta = +0.005800; 2/3 semillas positivas.

Se mantienen como controles **V2-E0** y **V2-E0R**. Estos resultados son
screening, no evidencia confirmatoria: ningún escenario satisface todavía el
criterio de mejora real de 4/5 semillas.

## Lectura provisional

V2-E7 tiene el mejor mAP50-95 medio, pero su ventaja es pequeña y no consistente
en las tres semillas; V2-E6 ofrece una señal similar con menor coste observado.
V2-E3 destaca en recall a precisión ≥0.98 y en estratos de dificultad, aunque
su mAP50-95 medio queda por debajo de E0R. V2-E4 y V2-E8 quedan claramente por
debajo de ambos controles en mAP50-95 y no se promueven.

La confirmación debe ejecutarse con la misma receta, datos, protocolo y regla de
checkpoint, a 5 semillas y 50 épocas, sin consultar `test` para seleccionar.
