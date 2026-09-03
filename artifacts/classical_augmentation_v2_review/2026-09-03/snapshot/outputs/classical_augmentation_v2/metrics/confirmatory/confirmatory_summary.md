# Confirmación Classical Augmentation v2

Selección realizada exclusivamente sobre `val`; `test` no fue consultado.

| Escenario | mAP50-95 media | Δ vs E0R | Signos + | Δ recall operacional | Peor Δ recall por tamaño | Tiempo medio (s) | Suma de rangos |
|---|---:|---:|---:|---:|---:|---:|---:|
| V2-E7 | 0.5461 | 0.0182 | 10/10 | -0.0150 | -0.0526 | 7829.2 | 5 |
| V2-E6 | 0.5452 | 0.0169 | 5/5 | -0.0183 | -0.0591 | 2866.4 | 10 |
| V2-E3 | 0.5308 | 0.0025 | 3/5 | -0.0649 | -0.1697 | 1408.2 | 15 |
| V2-E0 | 0.5429 | 0.0149 | 10/10 | -0.0390 | -0.0797 | 6702.0 | n/a |
| V2-E0R | 0.5279 | 0.0000 | 0/10 | 0.0000 | 0.0000 | 1864.5 | n/a |

## Decisión confirmatoria predeclarada

| Escenario | Candidato fuerte | Extender a 10 | Caso A | Caso B |
|---|---:|---:|---:|---:|
| V2-E3 | False | False | False | False |
| V2-E6 | False | False | False | False |
| V2-E7 | False | False | False | False |

## Métrica operacional seleccionada en val

| Escenario | Precisión | Recall | F1 | FP medios | FN medios | Corridas con P≥0.98 | Fallbacks |
|---|---:|---:|---:|---:|---:|---:|---:|
| V2-E7 | 0.9821 | 0.4967 | 0.6475 | 4.2 | 231.0 | 10/10 | 0 |
| V2-E6 | 0.9823 | 0.5050 | 0.6640 | 4.2 | 227.2 | 5/5 | 0 |
| V2-E3 | 0.9811 | 0.4584 | 0.5980 | 4.0 | 248.6 | 5/5 | 0 |
| V2-E0 | 0.9821 | 0.4728 | 0.6259 | 4.0 | 242.0 | 10/10 | 0 |
| V2-E0R | 0.9820 | 0.5118 | 0.6719 | 4.3 | 224.1 | 10/10 | 0 |
