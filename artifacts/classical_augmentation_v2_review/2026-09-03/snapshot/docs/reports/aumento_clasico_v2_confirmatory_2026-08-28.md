# Classical Augmentation v2 — confirmación y cierre

## Resultado ejecutivo

La campaña confirmatoria terminó con **40 corridas válidas** a 50 épocas. La
selección se realizó exclusivamente sobre `val` y ninguna de las tres recetas
confirmadas cumplió el criterio predeclarado de candidato fuerte. Por tanto, la
conclusión es negativa: **no se promueve una receta de aumento clásico v2**.

V2-E7 produjo la señal más clara en mAP50-95: mejoró frente a V2-E0R en las
10/10 semillas, con delta emparejado medio de +0.018161 e IC95%
[+0.011340, +0.024982]. Sin embargo, redujo el recall operacional medio en
0.015033 y degradó casos clave frente a V2-E0R: objetos pequeños −0.018041,
clusters −0.011765 y contacto con borde −0.028947. Esta última caída supera la
tolerancia predeclarada de 0.02 y hace que el Caso A sea falso. Tampoco cumple
el Caso B porque la mejora operacional no es positiva ni consistente.

Fuente numérica principal:
`outputs/classical_augmentation_v2/metrics/confirmatory/confirmatory_summary.json`.

## Integridad experimental

- Cohortes finales: V2-E0, V2-E0R y V2-E7 con semillas 1–10; V2-E3 y V2-E6
  con semillas 1–5.
- Cada `results.csv` contiene exactamente la secuencia 1..50, sin duplicados,
  y cada corrida conserva `weights/best.pt`.
- Los cinco datasets tienen auditoría `valid`. `val` y `test` permanecen
  idénticos entre escenarios: 133 imágenes y 459 objetos en `val`; 133
  imágenes y 480 objetos en `test`.
- V2-E0 usa 1062 imágenes naturales de entrenamiento. Los otros escenarios
  usan 1594 imágenes de entrenamiento, incluidas 532 derivadas únicamente de
  `train`.
- `test_consulted=false` tanto en el resumen confirmatorio como en el lock de
  selección.

Durante la campaña se detectó una doble ejecución que había intercalado épocas
en V2-E0 seed05 y V2-E3 seed05. Las carpetas contaminadas se preservaron fuera
de la matriz válida en
`outputs/classical_augmentation_v2/runs/confirmatory/quarantine_2026-08-27_duplicate_launcher/`.
Ambas corridas se reconstruyeron desde cero y la validación estricta impide que
un historial con épocas repetidas vuelva a contarse como completo.

## Resultados agregados en validación

| Escenario | n | mAP50-95 media ± DE | Precision | Recall | Recall @ P≥0.98 | FP medios | FN medios |
|---|---:|---:|---:|---:|---:|---:|---:|
| V2-E0 | 10 | 0.542873 ± 0.005999 | 0.855555 | 0.711238 | 0.472767 | 4.0 | 242.0 |
| V2-E0R | 10 | 0.527939 ± 0.007141 | 0.873383 | 0.693578 | 0.511765 | 4.3 | 224.1 |
| V2-E3 | 5 | 0.530772 ± 0.013198 | 0.863182 | 0.690854 | 0.458388 | 4.0 | 248.6 |
| V2-E6 | 5 | 0.545238 ± 0.004830 | 0.874970 | 0.705224 | 0.505011 | 4.2 | 227.2 |
| V2-E7 | 10 | 0.546100 ± 0.005294 | 0.853782 | 0.721319 | 0.496732 | 4.2 | 231.0 |

La precision, el recall y el mAP de las primeras columnas son métricas estándar
del mejor checkpoint escogido por mAP50-95 de `val`. Las métricas operacionales
usan para cada corrida el umbral escogido también en `val` bajo la regla
Precision ≥ 0.98. No hubo fallbacks: todas las 40 corridas alcanzaron ese nivel
de precisión.

## Evidencia emparejada y decisión

| Receta | Δ mAP50-95 vs E0R | Semillas positivas | Δ recall operacional | Peor delta clave | Caso A | Caso B |
|---|---:|---:|---:|---:|---:|---:|
| V2-E3 | +0.002478 | 3/5 | −0.064924 | −0.101961 (clusters) | no | no |
| V2-E6 | +0.016944 | 5/5 | −0.018301 | −0.028070 (borde) | no | no |
| V2-E7 | +0.018161 | 10/10 | −0.015033 | −0.028947 (borde) | no | no |

V2-E6 y V2-E7 mejoran mAP50-95 de manera consistente, pero no sin degradación
operacional relevante en los estratos difíciles. V2-E3 tampoco muestra
consistencia suficiente. En consecuencia:

- `selected_scenarios=[]`;
- el lock quedó sellado con SHA-256
  `e196445fe9903e3f7c4c7d41ca69ada9a1a303fe16b8e3a3522a409bd3c21d98`;
- el evaluador final registró
  `skipped_no_validation_selected_candidate`;
- **no se abrió ni evaluó `test`**.

El test se mantuvo fuera de la selección de esta campaña, pero ya había sido
consultado en trabajo histórico y no debe describirse como holdout virgen.

## Diagnóstico de tiempos

Las suspensiones del equipo hacen que varias duraciones de pared sean
observaciones contaminadas. Además, una corrida reanudada puede registrar solo
el tramo posterior a la reanudación. Por ello, la media no representa bien el
coste normal. Las medianas observadas por corrida de 50 épocas fueron:

| Escenario | mediana | rango observado | lectura |
|---|---:|---:|---|
| V2-E0 | 20.0 min | 16.2–693.3 min | outliers por suspensión |
| V2-E0R | 25.9 min | 6.2–87.2 min | mínimo parcial por reanudación |
| V2-E3 | 23.8 min | 21.5–25.9 min | cohorte más limpia |
| V2-E6 | 26.8 min | 23.1–95.8 min | dos corridas interrumpidas |
| V2-E7 | 31.8 min | 23.4–933.3 min | outlier severo por suspensión |

La última tripleta continua (seed10), ejecutada con CUDA, tardó 16.4 min para
V2-E0, 23.8 min para V2-E0R y 26.1 min para V2-E7. Esta tripleta es la mejor
estimación operativa del hardware actual. Para planificar campañas sin
suspensiones es razonable reservar **20–30 min por corrida de 50 épocas**, de
forma serial, más el resumen de predicciones. Las duraciones extremas no deben
interpretarse como coste intrínseco de las recetas.

## Conclusión científica

La campaña sí encontró una mejora repetible de mAP50-95 para V2-E6 y V2-E7,
pero no una mejora global defendible bajo el criterio fijado antes de observar
la confirmación. El aumento de mAP vino acompañado de menor recall operacional
en al menos un modo de fallo prioritario. La respuesta honesta es que, con este
dataset, protocolo y detector, **ninguna receta clásica v2 supera de manera
integral a los controles**.

No procede ajustar retrospectivamente las recetas ni sus umbrales usando estos
resultados. Una campaña futura debería plantearse como una hipótesis nueva y
usar otra partición de evaluación realmente no consultada si se desea una
afirmación externa más fuerte.

