# Aumento clásico v2: entrenamiento smoke

Fecha local: 2026-08-21  
Estado: completado, 9/9 corridas válidas  
Propósito: comprobar de extremo a extremo el protocolo congelado y medir tiempos reales antes del screening multisemilla.

## Protocolo

- Modelo: YOLO11n preentrenado.
- Épocas: 8.
- Semilla: 1.
- Resolución: 640 px.
- Lote: 8.
- Workers: 4.
- Optimizador: AdamW (`lr0=0.001`, `lrf=0.01`, `weight_decay=0.0005`).
- `AMP=false`, `rect=true`, ejecución determinista.
- Todos los aumentos internos de Ultralytics desactivados.
- Validación real congelada: 133 imágenes, 459 objetos.
- Métrica reportada: mejor época de cada corrida según mAP50–95 de validación.

Cada carpeta válida contiene ocho filas en `results.csv`, `best.pt` y `last.pt`. No se utilizó el conjunto de test.

## Resultados preliminares

| Escenario | Mejor época | Precisión | Recall | mAP50 | mAP50–95 | Δ mAP50–95 vs. E0 |
|---|---:|---:|---:|---:|---:|---:|
| E0 | 7 | 0.84166 | 0.76253 | 0.85456 | 0.59482 | 0.00000 |
| E0R | 8 | 0.91884 | 0.71526 | 0.84130 | 0.57587 | -0.01895 |
| E2 | 8 | 0.86383 | 0.74633 | 0.85548 | 0.58221 | -0.01261 |
| E3 | 8 | 0.91003 | 0.74074 | 0.85746 | 0.58561 | -0.00921 |
| E4 | 8 | 0.88399 | 0.74728 | 0.84686 | 0.56638 | -0.02844 |
| E5 | 8 | 0.92625 | 0.74728 | 0.86241 | 0.60341 | +0.00859 |
| E6 | 8 | 0.88782 | 0.79316 | 0.88058 | 0.60912 | +0.01430 |
| E7 | 8 | 0.87541 | 0.77124 | 0.86968 | 0.60256 | +0.00774 |
| E8 | 7 | 0.83292 | 0.72767 | 0.83752 | 0.57299 | -0.02183 |

E6 es la mejor señal smoke: frente a E0 aumenta precisión (+0.04616), recall (+0.03063), mAP50 (+0.02602) y mAP50–95 (+0.01430). E7 mejora las cuatro métricas, aunque con menor margen. E5 mejora precisión, mAP50 y mAP50–95, pero reduce ligeramente recall. Estos resultados son diagnósticos de una sola semilla y ocho épocas; no justifican seleccionar un ganador.

## Tiempos medidos

| Escenario | Tiempo de pared | Imágenes train |
|---|---:|---:|
| E0 | 170.7 s (2:51) | 1062 |
| E8 | 307.7 s (5:08) | 1594 |
| E0R | 270.6 s (4:31) | 1594 |
| E7 | 250.2 s (4:10) | 1594 |
| E2 | 257.7 s (4:18) | 1594 |
| E6 | 298.2 s (4:58) | 1594 |
| E3 | 289.3 s (4:49) | 1594 |
| E5 | 297.7 s (4:58) | 1594 |
| E4 | 332.4 s (5:32) | 1594 |

El promedio de los ocho escenarios aditivos fue 288.0 s (4:48) por corrida. El tiempo acumulado válido fue 2474.4 s (41:14). La duración incluye inicialización, entrenamiento, validación final y escritura de artefactos.

## Incidente de energía y criterio de exclusión

Al iniciar E2, Windows cambió a batería y al plan `Silent`; la velocidad cayó de aproximadamente 7–10 a 1.0–1.3 lotes/s. El árbol de entrenamiento se detuvo, la carpeta parcial se conservó con el sufijo `interrupted_battery`, se restauró alimentación de red y el plan `Performance`, y E2 se repitió desde cero.

El intento parcial no tiene una corrida completa ni aporta métricas o tiempos a las tablas. El registro `execution_state.jsonl` conserva el evento para auditoría. Esto demuestra que el estado energético es una variable de infraestructura material y debe controlarse en la campaña larga.

## Decisión de puerta

La puerta smoke queda aprobada:

- 9/9 escenarios completaron ocho épocas;
- 9/9 produjeron `best.pt` y `last.pt`;
- no hubo fallos de carga, etiquetas corruptas ni errores de memoria;
- el conjunto de validación permaneció congelado;
- los tiempos bajo corriente y plan `Performance` son consistentes;
- no se tocó test.

Siguiente paso: ejecutar el screening de 3 semillas × 30 épocas para todos los escenarios. La clasificación smoke no debe usarse para seleccionar anticipadamente el top-3.
