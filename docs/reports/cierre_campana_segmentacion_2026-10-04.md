# Informe de cierre: uchuvas, cuatro ciclos de segmentación

Cierre: 4 de octubre de 2026, hora de Colombia. Se ejecutaron tres ciclos originales y su evaluación final reservada, seguidos del cuarto experimento autorizado de ROI y recortes. La rama ejecutada es segmentación por instancia. No se evaluó un modelo independiente de detección con cajas; la expresión «ambos tipos de modelo» quedó pendiente de precisar.

## Resultado principal

Los recortes de 640 × 640 píxeles, con 20 % de solapamiento, mejoraron la segmentación en desarrollo. La ROI usa color y conectividad de vegetación desde RGB: es una heurística explícita, no un detector de arbustos aprendido. Los recortes se rellenan sin reducir su escala nativa. Las máscaras se reproyectan al fotograma original y los duplicados se filtran por IoU de máscara y clase.

| Ciclo | Imágenes | Épocas | mAP50–95 sintético val. | mAP50–95 referencia fija (imagen completa) |
|---|---:|---:|---:|---:|
| 1 | 180 | 60 | 0.050052 | 0.000753 |
| 2 | 180 | 60 | 0.180809 | 0.000708 |
| 3 | 180 | 60 | 0.164228 | 0.000822 |
| 4 | 180 | 60 | 0.164228 | 0.000822 |

El ganador original fue el ciclo 3, congelado antes de acceder a las imágenes finales. En el escenario final reservado obtuvo mAP50–95 de máscaras **0,012271**, frente a **0,001768** del ciclo 1. Ese cierre no se modificó después del cuarto experimento. El ciclo 2 había retrocedido en la referencia fija; ese resultado negativo se conserva.

## Cuarto ciclo: mismo modelo, distintas entradas

| Captura | Inferencia | mAP50–95 máscaras | Precisión | Recall | Mediana total (s/imagen) |
|---|---|---:|---:|---:|---:|
| Referencia fija | full | 0.000822 | 0.0844 | 0.0247 | 0.097 |
| Referencia fija | roi | 0.003079 | 0.1245 | 0.0329 | 2.195 |
| Referencia fija | tiles | 0.029894 | 0.4008 | 0.1738 | 2.215 |
| Nuevo vuelo cercano | full | 0.010613 | 0.2699 | 0.1208 | 0.091 |
| Nuevo vuelo cercano | roi | 0.005188 | 0.1696 | 0.0414 | 1.600 |
| Nuevo vuelo cercano | tiles | 0.052503 | 0.4255 | 0.2262 | 1.787 |

La ROI sin recortes empeoró en el nuevo vuelo. Los recortes mejoraron el recall, pero aún omiten la mayoría de los capachos. La latencia total incluye localización y fusión; no equivale al tiempo de red ni demuestra operación en tiempo real.

## Controles y alcance

- 18 escenas y diez vistas por ciclo: 140 imágenes de entrenamiento y 40 de validación. Grupos morfológicos disjuntos de entrenamiento, validación, vuelo de desarrollo y escenario final; variantes conservan su grupo.
- Tres clases por apariencia del capacho: pintona (incluye verdes), madura y sobremadura. No se interpreta la apariencia como madurez agronómica del fruto.
- Máscaras raster exactas, sin pérdida, como fuente de entrenamiento. Los polígonos incompatibles se conservaron como rechazo de compatibilidad; no sustituyeron las máscaras.
- Cada entrenamiento: pesos generales comunes, semilla 20261002, 60 épocas, 960, batch 2, AMP y AdamW. Umbral operativo seleccionado solo con validación sintética.
- Ciclo 4 reutiliza escenas del tercero sin alterar apariencia, con exportación versionada y entrenamiento fresco para aislar la inferencia. No es una mejora visual adicional.
- El predictor recibe RGB. La verdad, identidades y telemetría se usan exclusivamente para evaluación o presentación. Veinte pruebas locales pasaron, incluidas separación, máscaras, presupuesto, aislamiento y reproyección de recortes.
- El cuarto vuelo cubrió 17 puntos, 259,658 s simulados, 1.299 pares sincronizados y separación mínima 0,307845 m. Son seis arbustos y doce estaciones de observación en dos caras exteriores de una hilera, no doce caras de seis hileras.
- En el cuarto vuelo se decodificó algún ArUco en el 64,75 % de los fotogramas evaluados, incluidos tránsitos; no se afirma cobertura continua. Los controles de encuadre completo, margen del 5 % y ArUco propio pasaron en observaciones válidas.
- Se retiraron las plántulas geométricas y se orientaron los hilos hacia anclajes exteriores. Persisten follaje rígido y contexto simplificado; no hay validación humana de fidelidad ni simulación mecánica de tensión.
- No se entrenó con imágenes reales ni se demostró transferencia al cultivo. El escenario final original permanece separado de los ajustes del cuarto ciclo; no se reutilizó como holdout para seleccionar esa estrategia.

## Artefactos

Raíz local: `C:\dev\SyntheticPlantGeneration\outputs\segmentation_cycles_20261002`. Resultados y errores anteriores preservados; no se generaron commits.

- Ciclo 1: [dataset y máscaras](C:/dev/SyntheticPlantGeneration/outputs/segmentation_cycles_20261002/cycle_01/dataset), [pesos](C:/dev/SyntheticPlantGeneration/outputs/segmentation_cycles_20261002/cycle_01/training/weights/best.pt), [entrenamiento](C:/dev/SyntheticPlantGeneration/outputs/segmentation_cycles_20261002/cycle_01/training/experiment.json).
- Ciclo 2: [dataset y máscaras](C:/dev/SyntheticPlantGeneration/outputs/segmentation_cycles_20261002/cycle_02/dataset), [pesos](C:/dev/SyntheticPlantGeneration/outputs/segmentation_cycles_20261002/cycle_02/training/weights/best.pt), [entrenamiento](C:/dev/SyntheticPlantGeneration/outputs/segmentation_cycles_20261002/cycle_02/training/experiment.json).
- Ciclo 3: [dataset y máscaras](C:/dev/SyntheticPlantGeneration/outputs/segmentation_cycles_20261002/cycle_03/dataset), [pesos](C:/dev/SyntheticPlantGeneration/outputs/segmentation_cycles_20261002/cycle_03/training/weights/best.pt), [entrenamiento](C:/dev/SyntheticPlantGeneration/outputs/segmentation_cycles_20261002/cycle_03/training/experiment.json).
- Ciclo 4: [dataset y máscaras](C:/dev/SyntheticPlantGeneration/outputs/segmentation_cycles_20261002/cycle_04/dataset), [pesos](C:/dev/SyntheticPlantGeneration/outputs/segmentation_cycles_20261002/cycle_04/training/weights/best.pt), [entrenamiento](C:/dev/SyntheticPlantGeneration/outputs/segmentation_cycles_20261002/cycle_04/training/experiment.json).

- [Video del cuarto vuelo con recortes](C:/dev/SyntheticPlantGeneration/outputs/segmentation_cycles_20261002/cycle_04/evaluation_current_tiles/segmentation.mp4).
- [Video de la evaluación final original](C:/dev/SyntheticPlantGeneration/outputs/segmentation_cycles_20261002/final_evaluation_model3/segmentation.mp4).
- [Comparación visual de seis vistas](C:/dev/SyntheticPlantGeneration/outputs/segmentation_cycles_20261002/cycle_03/six_views_comparison.jpg).
- [Registro de cambios, fallos y recuperaciones](C:/dev/SyntheticPlantGeneration/docs/reports/reanudacion_ciclos_segmentacion_2026-10-03.md).

Los videos son presentaciones a 5× de los fotogramas muestreados a 1 Hz; la inferencia se evaluó sobre los originales. Se conservaron interrupciones por actualización, bloqueos de escritura, restricciones de acceso a WSL y errores de orquestación/serialización. No se presentaron esos intentos como ciclos completos.

## Pendientes fuera de la rama ejecutada

Entrenar y validar un localizador aprendido de arbustos; evaluar el modelo de detección con cajas que se identifique; contrastar fidelidad con revisión humana y medir transferencia con datos reales independientes. No se sustituyen esos pendientes por el éxito del prototipo de segmentación.
