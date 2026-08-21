# Resultados preliminares — tripleta clásica completa

Fecha: 2026-08-17  
Commit: `29e69ca0e45615dbf0d0385ec66957d004de3493`  
Protocolo: YOLO11n, semilla 1, 50 épocas, 640 px, batch 8, workers 4, AdamW, AMP desactivado, orden E0→E1→E2.  
Hardware: NVIDIA GeForce RTX 4050 Laptop GPU, 6 GB.  
Entorno: Python 3.12.13, PyTorch 2.12.1+cu130, CUDA 13.0, Ultralytics 8.4.114.

## Resultado principal

Con esta única semilla, E0 (datos naturales) fue el mejor modelo global. E2 (aumento suave) quedó cerca y obtuvo la mayor precisión, pero perdió recall. E1 (aumento fuerte) fue claramente inferior, sobre todo en mAP50-95.

Los checkpoints se seleccionaron exclusivamente por mAP50-95 de validación. Después se evaluó una sola vez cada `best.pt` sobre el mismo conjunto test de 109 imágenes y 311 instancias.

## Validación en el mejor checkpoint

| Condición | Mejor época | Precisión | Recall | mAP50 | mAP50-95 |
|---|---:|---:|---:|---:|---:|
| E0 natural | 15 | 0,851 | 0,802 | 0,867 | 0,602 |
| E1 fuerte | 11 | 0,827 | 0,772 | 0,848 | 0,587 |
| E2 suave | 13 | 0,872 | 0,746 | 0,858 | 0,600 |

## Evaluación test de `best.pt`

| Condición | Precisión | Recall | mAP50 | mAP50-95 | Δ mAP50 vs E0 | Δ mAP50-95 vs E0 |
|---|---:|---:|---:|---:|---:|---:|
| E0 natural | 0,868 | **0,823** | **0,905** | **0,624** | — | — |
| E1 fuerte | 0,863 | 0,813 | 0,885 | 0,569 | -0,019 | -0,056 |
| E2 suave | **0,879** | 0,797 | 0,893 | 0,615 | -0,012 | -0,010 |

Interpretación preliminar:

- E0 conserva la mejor cobertura y calidad de localización.
- E2 intercambia recall por precisión: +0,011 en precisión y -0,026 en recall frente a E0. Su mAP50-95 queda sólo 0,010 por debajo de E0.
- E1 no aporta ventaja en esta semilla. La caída de 0,056 en mAP50-95, mucho mayor que su caída de 0,019 en mAP50, sugiere peor ajuste fino de las cajas a IoU estrictos.
- Los tres mejores checkpoints aparecen temprano (épocas 11–15). Después las pérdidas de entrenamiento siguen bajando sin mejora sostenida en validación, compatible con sobreajuste/meseta.

## Tiempos reales

| Condición | Tiempo de pared | Segundos | Imágenes train | Lotes/época |
|---|---:|---:|---:|---:|
| E0 | 14 min 51 s | 891,0 | 1.062 | 133 |
| E1 | 32 min 29 s | 1.948,8 | 2.124 | 266 |
| E2 | 28 min 24 s | 1.704,1 | 2.124 | 266 |
| Tripleta completa | 75 min 58 s | 4.557,8 | — | — |

E1 y E2 usan el doble de imágenes y pasos de optimización por época que E0. Por tanto, esta comparación mantiene fijo el número de épocas, no el presupuesto de cómputo ni el número total de actualizaciones.

## Integridad y reproducibilidad

- Cada corrida contiene 50 filas de resultados, `best.pt`, `last.pt`, checkpoints periódicos y `args.yaml`.
- SHA-256 de `best.pt`:
  - E0: `E03C2CC612AA14A7C407D1B40494B7354760A8EE478E4B88C47F590B4DF4EBD4`
  - E1: `336AA92CDDD1D4BBA30D1D05E13726974DC3A2EFD3218A47E9E4E5B4F4EEB6AA`
  - E2: `446D0B604E62DAEBC2E28704978BAF9701784661695661E96C64C34A3429C85F`
- El test es byte a byte el mismo en las tres condiciones, según la auditoría previa.
- No hubo OOM, imágenes corruptas, labels inválidos, fallos de checkpoint ni reanudaciones.

## Límites

1. Es una sola semilla; las diferencias no tienen intervalo de confianza ni prueba de significancia.
2. E1/E2 siguen siendo datasets precalculados sin receta, parámetros o semillas de transformación. No puede atribuirse causalmente el resultado a una magnitud concreta de oclusión o iluminación.
3. El entorno ejecutado usa Ultralytics 8.4.114, no la versión 8.4.66 declarada en la entrega.
4. El orden fue fijo E0→E1→E2. Aunque no apareció una penalización temporal sistemática para E2, una campaña multisemilla debe contrabalancear el orden.
5. El conjunto test ya se consultó para este reporte preliminar. No debería volver a usarse para escoger hiperparámetros o recetas.

## Próximo paso recomendado

Antes de gastar 30 semillas, ejecutar una réplica piloto de 5 semillas con orden contrabalanceado y reportar media, desviación estándar, intervalo de confianza y diferencias emparejadas. Si se conserva el patrón actual, E1 debe descartarse o rediseñarse; E2 merece continuar como única candidata clásica frente a E0.
