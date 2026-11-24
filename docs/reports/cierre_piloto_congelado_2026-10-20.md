# Cierre del piloto congelado — 20 de octubre de 2026

Piloto acotado completado como experimento diagnóstico. No se demuestra el objetivo científico global ni se promueve el modelo a producción. Generador, entorno y protocolo conservan los 546 hashes congelados. No se modificaron plantas para esta evaluación.

Se completaron 280 imágenes estáticas, entrenamiento de 10 épocas y comparación frente a V186 sobre las mismas 80 vistas completas; además, tres recorridos continuos de 120 fotogramas a 2 Hz. Los videos muestran máscaras e IDs predichos, no identidades verdaderas.

## Seguimiento

| Vuelo | Precisión | Recuperación | F1 | Cambios ID / pares consecutivos | Tasa |
|---|---:|---:|---:|---:|---:|
| flight_val_a | 74.00% | 51.37% | 60.64% | 8409 / 20162 | 41.71% |
| flight_val_b | 73.18% | 49.35% | 58.95% | 8292 / 21119 | 39.26% |
| flight_test | 76.26% | 50.60% | 60.84% | 9560 / 27006 | 35.40% |

Los cambios se cuentan solo cuando la misma identidad verdadera se empareja por clase e IoU ≥ 0,5 en dos fotogramas consecutivos. No es IDF1 y excluye las omisiones. Hay fragmentación importante; no se afirma seguimiento estable.

## Localización 3D

| Vuelo | Estimador | Tracks evaluados | Mediana cm | P90 cm | Máximo cm | Cálices únicos / visibles | Cobertura |
|---|---|---:|---:|---:|---:|---:|---:|
| flight_val_a | visual_pose | 163 / 182 | 4.93 | 21.91 | 69.65 | 137 / 630 | 21.75% |
| flight_val_a | fused | 176 / 199 | 7.14 | 20.00 | 39.78 | 146 / 630 | 23.17% |
| flight_val_b | visual_pose | 201 / 232 | 8.77 | 37.00 | 271.05 | 164 / 637 | 25.75% |
| flight_val_b | fused | 234 / 262 | 6.97 | 23.38 | 52.54 | 179 / 637 | 28.10% |
| flight_test | visual_pose | 207 / 250 | 3.44 | 30.16 | 131.73 | 178 / 775 | 22.97% |
| flight_test | fused | 213 / 248 | 6.98 | 24.38 | 122.87 | 182 / 775 | 23.48% |

`visual_pose`: marcador realmente decodificado; `fused`: marcador y movimiento relativo ruidoso. ArUco 8 fue decodificado en los 360 fotogramas. Las poses exactas y la geometría privada no entraron en el estimador. Se revisó la recuperación histórica de reproyección v2; no se reactivó la cola histórica.

Error respecto al centro de la caja mundial de la malla evaluada del capacho, no respecto al centro del fruto interno. Evaluación condicional: solo tracks con una identidad verdadera única entre sus emparejamientos nativos; se retienen exclusiones por mezcla o falta de correspondencia. Hay casos con soporte verdadero de un solo fotograma; el soporte puede incluir observaciones descartadas por la triangulación. Los errores no representan todos los objetos ni una garantía métrica. La cobertura usa como denominador los cálices visibles al menos un píxel en cualquier fotograma.

La fusión no mejora uniformemente: aumenta la mediana en validación A y prueba; mejora en validación B. Persisten errores grandes y cobertura baja. No se seleccionó ni ajustó el estimador usando prueba.

## Límites y conservación

- Entrenamiento exclusivamente sintético; prueba de desarrollo inspeccionada históricamente, no holdout externo. Semillas disjuntas, pero topologías no independientes. Las seis semillas reservadas siguen intactas.
- ROI RGB heurística, no detector aprendido. Los parches no añaden detalle óptico.
- Aproximadamente la mitad de los objetos visibles se omite; las cifras de error 3D son condicionales y la cobertura ronda 22–28 %.
- El aspecto del capacho no demuestra madurez interna del fruto.
- La incertidumbre por leave-one-out no es un intervalo de confianza calibrado.
- Se preservan pesos, datos, logs, resultados negativos y antecedentes, incluidos V182 y V185. No se repite refinamiento ni entrenamiento.

## Evidencias

Raíz de evidencias: `outputs/frozen_field_pilot_20261019`.
- `flight_results.json`: resumen de los tres vuelos.
- `flights/*/evaluator_private/localization_error.json`: errores por track y exclusiones.
- `flights/*/evaluator_private/evaluation.json`: correspondencias y cambios de identidad.
- `flights/*/predictions/tracking_2fps.mp4`: videos completos.
- `native_evaluation/comparison.html`: comparación estática con V186.
- `training_runs/training/execution_summary.json`: pasos reales y memoria.
- `closure_verification.json`: verificación de cierre.