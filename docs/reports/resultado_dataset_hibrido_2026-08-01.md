# Resultado del dataset sintético y entrenamiento híbrido

Fecha de corte: 2026-08-01  
Semilla de entrenamiento: `20260731`  
Arquitectura: YOLO26n, una clase (`calyx`), imágenes de 640 px  
Render sintético: `standard_eevee`; Cycles desactivado

## Resultado ejecutivo

Se completó la cadena solicitada:

1. escena de cultivo con competencia lumínica estratificada, tutorado tipo
   trípode invertido, copa densa, microseparación hoja–capacho y fondo verde
   procedural con formas semejantes a *Lolium perenne*, kikuyo y malezas;
2. dataset sintético original de 100 imágenes, generado sin reutilizar píxeles
   del dataset natural;
3. matriz de proporciones natural/sintético con validación y test únicamente
   naturales;
4. calibración espacial aprendida sin consultar el test natural;
5. selección por validación de una interpolación entre el checkpoint natural y
   el checkpoint híbrido.

El modelo final obtuvo `0.690636653` mAP50–95 en el test natural, frente a
`0.682706171` del baseline natural completo. La diferencia es
`+0.007930482` absoluta, aproximadamente `+1.16 %` relativa. Por tanto, el
target operativo de igualar o superar el dataset natural completo se alcanzó
en esta corrida.

## Artefactos principales

- Blend de revisión:
  `outputs/current_review/uchuva_fidelity_competition_seed_025.blend`.
- Dataset sintético original:
  `outputs/datasets/uchuva_original_synthetic_seed_1000_v1/`.
- Copia derivada calibrada en escala:
  `outputs/datasets/uchuva_original_synthetic_seed_1000_v1_scale_calibrated/`.
- Comparación visual de escala y luminancia:
  `outputs/datasets/uchuva_original_synthetic_seed_1000_v1_scale_luminance_calibrated/comparison_contact_sheet.jpg`.
- Checkpoint ganador:
  `outputs/experiments/checkpoint_interpolation_scale80_seed_1000_v1/interpolated_checkpoints/natural_hybrid_alpha_045.pt`.
- Reporte máquina-legible del ganador:
  `outputs/experiments/checkpoint_interpolation_scale80_seed_1000_v1/checkpoint_interpolation_result.json`.

## Dataset sintético original

| Propiedad | Resultado |
|---|---:|
| Imágenes | 100 |
| Split | 80 train / 10 val / 10 test |
| Cajas de capacho aceptadas | 368 |
| Previews | 100 |
| Colisiones físicas | 0 |
| Capachos abiertos | 0 |
| Frutos que debían estar ocultos pero resultaron visibles | 0 |
| Instancias reproductivas desconocidas | 0 |
| Renders Cycles | 0 |

La escena y el dataset usan EEVEE normal. Las oclusiones visuales sin
interpenetración continúan permitidas; la separación hoja–capacho puede elevar
la lámina hasta 4.5 mm sin mover el nodo de origen del pecíolo.

## Calibración espacial

El análisis inicial mostró que los capachos sintéticos eran demasiado pequeños
en el encuadre. La copia calibrada usa recortes y redimensionado conjuntos de
imagen y etiqueta. Los factores se ajustaron con `train+val` naturales y
`train` sintético; el test natural no se leyó.

| Banda de área de caja | Natural train+val | Sintético train calibrado |
|---|---:|---:|
| Menos de 1 % del cuadro | 15.03 % | 15.18 % |
| Entre 1 % y 5 % | 50.72 % | 50.00 % |
| Al menos 5 % | 34.25 % | 34.82 % |
| Objetos por imagen | 2.795 | 2.800 |

Los acercamientos seleccionados fueron `1.35×`, `1.95×` y `1.20×` para
escenas cuya mediana de caja pertenecía respectivamente a las bandas pequeña,
media y grande. Una caja se conserva solo si al menos 75 % de su área original
permanece visible.

## Experimentos sobre el test natural fijo

Todos los valores siguientes son mAP50–95 sobre las mismas 133 imágenes
naturales de test y 480 cajas. El baseline se entrenó con 1061 imágenes
naturales; `+N` indica una adición al entrenamiento natural completo.

| Estrategia | mAP50–95 | Delta frente al natural |
|---|---:|---:|
| Natural completo | 0.682706 | 0.000000 |
| Sintético original, +80 | 0.668219 | −0.014487 |
| Presupuesto fijo 75 % real / 25 % sintético | 0.665086 | −0.017620 |
| Presupuesto fijo 50 % / 50 % | 0.632931 | −0.049775 |
| Presupuesto fijo 25 % real / 75 % sintético | 0.618077 | −0.064629 |
| Sintético original, +10 | 0.665880 | −0.016826 |
| Sintético original, +20 | 0.666300 | −0.016406 |
| Sintético original, +40 | 0.668414 | −0.014292 |
| Sintético con luminancia calibrada, +80 | 0.667146 | −0.015560 |
| Preentrenamiento sintético y ajuste natural | 0.673291 | −0.009415 |
| Sintético calibrado en escala, +80 | 0.677963 | −0.004743 |
| Sintético calibrado en escala, +40 | 0.670448 | −0.012258 |
| Mezcla +80 y cierre natural con LR 0.001 | 0.660403 | −0.022303 |
| Interpolación 55 % natural / 45 % híbrida | **0.690637** | **+0.007930** |

La calibración de luminancia aislada no mejoró el detector. La calibración de
escala sí redujo aproximadamente dos tercios de la brecha de la mezcla `+80`.
Reducir la dosis a 40 no ayudó. Un cierre natural con tasa `0.001` fue demasiado
agresivo y se conserva como resultado negativo.

## Selección del checkpoint final

Se interpolaron en espacio de pesos el baseline natural y el mejor checkpoint
entrenado con 1061 imágenes naturales más 80 sintéticas calibradas en escala.
Los coeficientes híbridos candidatos fueron 0.15, 0.30, 0.45, 0.60, 0.75 y
0.90. La selección usó exclusivamente el mAP50–95 de validación natural.

| Peso híbrido | mAP50–95 de validación |
|---:|---:|
| 0.15 | 0.693254 |
| 0.30 | 0.700683 |
| **0.45** | **0.701680** |
| 0.60 | 0.700222 |
| 0.75 | 0.697950 |
| 0.90 | 0.695670 |

Solo después de fijar `alpha_hybrid=0.45` se evaluó ese checkpoint interpolado
en test. Sus métricas finales fueron:

| Métrica | Natural completo | Modelo final |
|---|---:|---:|
| mAP50–95 | 0.682706 | **0.690637** |
| mAP50 | 0.923015 | **0.924321** |
| mAP75 | **0.783972** | 0.783419 |
| Precisión | **0.926570** | 0.879691 |
| Recall | 0.843750 | **0.879167** |

El incremento procede principalmente de mayor cobertura/recall, con una
reducción de precisión. El mAP75 queda prácticamente igual al baseline.

## Alcance de la conclusión

El resultado prueba el target operativo para esta partición, arquitectura y
semilla. No debe presentarse aún como una mejora estadística general:

- se ejecutó una sola semilla de entrenamiento;
- durante el desarrollo se consultó el mismo test para comparar estrategias,
  aunque cada selección interna usó validación;
- el modelo final combina un checkpoint natural y uno entrenado con datos
  híbridos; no es el resultado directo de una sola proporción fija;
- la confirmación rigurosa requiere repetir varias semillas y reservar un nuevo
  conjunto natural de captura que no haya participado en esta iteración.

El dataset natural original permaneció inmutable durante toda la cadena.
