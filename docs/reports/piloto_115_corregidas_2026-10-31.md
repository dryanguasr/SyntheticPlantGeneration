# Piloto con 115 imágenes corregidas: ejecución autorizada

Estado: seis corridas y evaluación completadas; revisión técnica de Codex realizada. Generación pausada, sin ampliación ni promoción de modelos.
Raíz: `outputs/reviewed_augmentation_115_20261031`.

El usuario autorizó comparar sintética + clásica contra real + clásica con
tres semillas, conservando la pausa de generación y revisando resultados
antes de ampliar el banco. La autorización permite entrenar con la selección
propuesta; no se transforma en una certificación humana retrospectiva de todas
las etiquetas sintéticas. Las 503 imágenes generadas permanecen conservadas.

## Diseño congelado

- 115 vistas de `review_addendum.json`, versión de horizonte corregido y
  distancias continuas. Se excluye de esta selección la captura casi negra
  señalada durante la revisión, conservada en su ubicación original.
- 461 imágenes reales train, 88 val y 94 test con hashes; no se alteran splits.
- Seis corridas nuevas: dos brazos por semilla 20261022/20261023/20261024,
  4.000 actualizaciones efectivas cada una, batch2, 960px, AdamW, mismos pesos
  `yolo26n.pt` originales y LR lineal por actualización.
- Receta clásica: HSV_v0,1 y flip horizontal0,5. Sin mosaic, mixup, recortes
  geométricos aleatorios ni cambio de clases.
- Secuencia común de posiciones sobre 461 + 115 fuentes. El brazo real
  reemplaza cada posición sintética por una muestra real sorteada con semilla
  fija; no recibe imágenes sintéticas. Conserva las posiciones reales comunes,
  las decisiones de aumentación y el número de actualizaciones. Este es un
  control de exposición/repetición emparejado, sin un tercer brazo adicional.

Los originales RGB, máscaras y labels no se editan. Se mantienen los filtros
nativos del entrenador instalado, Ultralytics8.4.114. `box_candidates` exige
ancho y alto **>2px**, relación de aspecto <100 y fracción de área conservada
tras transformación >0,10 para cajas o >0,01 cuando hay segmentos. Esa área
es **relativa**, no un mínimo absoluto de píxeles de máscara. `mask_ratio=4`
es reducción de máscara y tampoco define una superficie mínima universal.
El piloto sigue siendo de detección, con etiquetas de cajas; no se cambia
a segmentación ni se añade el umbral10px del diagnóstico. Referencia:
[Ultralytics data.augment](https://docs.ultralytics.com/reference/data/augment/).
El código instalado de aumentación y las versiones de paquetes se congelan.
La exposición efectiva después de las transformaciones se registra por brazo.

## Evaluación y límites

Se elige el checkpoint por AP de val real, con evaluación cada500 pasos.
Se congelan los seis pesos antes de evaluar el test de desarrollo. Un umbral
operativo común se obtiene sólo de val del control real de la primera semilla.
Se reportan AP50–95 macro y por clase, AP colapsado, precisión/recall,
confusión, tamaños y densidad. Bootstrap descriptivo:200 sorteos comunes por
grupos condicionados a las tres clases, manteniendo fijas las semillas.

El test ya fue consultado históricamente: no es una evaluación externa intacta
ni permite una afirmación confirmatoria. Se mostrarán diferencias por semilla,
media y desviación, junto con Madura y posibles intercambios entre clases.
Las 115 vistas reutilizan las mismas20 plantas; no son115 plantas independientes.
Los tamaños/densidad y el brillo siguen teniendo brechas documentadas frente
al train real. Una ganancia del piloto no certifica fotorealismo.

`reviewed_augmentation_pilot.py` mantiene seis trabajos seriales, verifica hashes
y procesos propios, preserva intentos interrumpidos y permite recuperar desde
pesos originales sin reutilizar resultados parciales como completos. Reutiliza
el entrenador de pasos exactos existente; no modifica campañas históricas.
El ledger nuevo conserva sólo el consumo del piloto; no reinicia presupuestos
de generación anteriores. El límite operativo heredado del helper (48h, reserva
de evaluación2h) es un tope técnico, no autorización para más brazos.

## Revisión al completar

El controlador produce `evaluation/comparison.json`, `report.md`, curvas y
ejemplos de predicciones y termina en `pilot_complete_pending_review`. Revisar
esos archivos y las comprobaciones de pares antes de presentar conclusiones.
No se amplía el banco ni se inicia otra dosis automáticamente. El seguimiento
de generación queda pausado durante y después del entrenamiento.


## Resultados reales del piloto

Todas las cifras de AP se expresan aquí en porcentaje; las diferencias, en puntos porcentuales (pp). AP es precisión media sobre el rango de IoU, no exactitud de clasificación.

| Semilla | Real + clásica | Sintética115 + clásica | Diferencia |
|---|---:|---:|---:|
| 20261022 | 17.92 | 21.81 | +3.89 pp |
| 20261023 | 18.87 | 19.93 | +1.06 pp |
| 20261024 | 19.70 | 20.94 | +1.24 pp |

AP macro50–95 medio ± DE: **18.83 ± 0.89** real frente a **20.89 ± 0.94** con sintéticas. Diferencia emparejada **+2.07 ± 1.59 pp**, positiva en las tres semillas.

| Clase | Real | Sintética115 | Diferencia media |
|---|---:|---:|---:|
| Pintona | 36.92 | 40.12 | +3.19 pp |
| Madura | 7.70 | 11.46 | +3.76 pp |
| Sobremadura | 11.87 | 11.11 | -0.76 pp |

Pintona y Madura mejoran AP en las tres semillas. **Sobremadura baja en las tres** (−0,16/−0,73/−1,38 pp); no se oculta ese intercambio tras la media macro.

Bootstrap descriptivo95% de la diferencia macro: **[+0.40, +5.03] pp**. Los200 sorteos comunes se condicionan a presencia de las tres clases y mantienen fijas las tres semillas. Se rechazó un sorteo sin todas las clases. Los seis grupos tienen25/48/15/3/2/1 imágenes: dos grupos concentran73 de94. El test contiene955 anotaciones (806 Pintona,91 Madura,58 Sobremadura). Este intervalo condicionado no sustituye una prueba en sesiones independientes ni demuestra significación confirmatoria.

## Localización, umbral operativo y estratos

| Medida, media de semillas | Real + clásica | Sintética + clásica |
|---|---:|---:|
| AP50–95 colapsando clases | 38.65 | 41.71 |
| Precisión al umbral común | 34.67 | 34.89 |
| Recall al umbral común | 62.34 | 68.31 |

El umbral0,076076 se obtuvo sólo en val del primer control real y se mantuvo fijo. El recall sube, con precisión media casi estable y variación entre semillas; en la tercera la precisión baja. La mejora de AP de Madura no implica que todos sus casos o su punto operativo mejoren.

Los estratos son descriptivos, con verdad real idéntica en los seis modelos. La fracción geométricamente localizada a IoU≥0,5 sube de53,82 a62,11% para tamaños32–64px (410 anotaciones), de85,50 a87,84% para≥64px (499), y de30,43 a34,78% para16–32px (46). No hay soporte aquí para afirmar un efecto en<16px. En densidad>22 sube de59,77 a67,36% (145 anotaciones); en1–7 baja de77,07 a75,80% (157). No son AP por estrato ni resultados independientes.

La matriz de confusión utiliza asignación geométrica voraz sin clase; precisión/recall utiliza emparejamiento con clase. Sus diagonales no son intercambiables. Persisten confusiones hacia Pintona y omisiones de las clases minoritarias; los JSON conservan cada matriz y predicción.

## Curvas y revisión visual de Codex

Se inspeccionaron las curvas de los seis modelos, cuatro pares de imágenes completas y recortes emparejados de los primeros casos con Madura/Sobremadura en el orden fijo del test, para las tres semillas. La selección de ejemplos no usa aciertos del modelo y no cambia la selección de checkpoints.

Los máximos de val aparecen entre1500 y2500 actualizaciones; entrenar hasta4000 no mejora monótonamente el AP, aunque la pérdida de entrenamiento disminuye. Se usaron los mejores checkpoints de val, no el último ni el mejor de test. Las pérdidas de dos dominios distintos no son directamente comparables como medida de calidad. En val, la diferencia media de los mejores checkpoints es+1,04pp (−1,07/+4,26/−0,06 pp por semilla), menos consistente que en test de desarrollo.

La fila9 ofrece un contraejemplo: el capacho etiquetado Madura sigue confundido con Pintona por los tres modelos mixtos; el control de la primera semilla sí lo predice Madura. En la fila43 los modelos mixtos de las semillas23/24 recuperan un caso Sobremadura que los controles confunden u omiten, aunque el AP agregado de Sobremadura disminuye. Estos casos ilustran errores residuales y variación; no estiman frecuencia ni validan agronómicamente las etiquetas.

![Curvas de las seis corridas](../../outputs/reviewed_augmentation_115_20261031/evaluation/curves.png)
![Casos minoritarios, semilla20261023](../../outputs/reviewed_augmentation_115_20261031/evaluation/minority_examples_20261023.png)

## Exposición, tiempos y verificación

| Semilla | Imágenes real/sintética en mezcla | Instancias real/sintética en mezcla | Instancias del control real |
|---|---:|---:|---:|
| 20261022 | 6412/1588 | 65743/1074467 | 82341 |
| 20261023 | 6404/1596 | 65498/1080369 | 82265 |
| 20261024 | 6402/1598 | 65631/1079881 | 82756 |

Cada corrida tuvo8000 exposiciones de imagen y4000 actualizaciones:24000 actualizaciones y48000 exposiciones en total. En los tres mixtos hubo19218 exposiciones reales y4782 sintéticas (19,93% de imágenes), con196872/3234717 apariciones de instancias reales/sintéticas tras el filtrado nativo (94,26% de instancias sintéticas). Son apariciones repetidas, no órganos independientes ni pesos del gradiente.

Consumo registrado: **8269.57s = 2.297h activas**:8201,14s de trabajos de entrenamiento y68,43s de evaluación. Los presupuestos históricos siguen intactos. No se generaron imágenes durante el piloto.

Se cotejaron las1999 entradas del lock de entrenamiento, las136 de generación, las20 plantas y admisiones, los503 pares preservados, inicialización original, mejores/últimos pesos, pasos, LR, secuencias y aumentaciones emparejadas. Los seis pesos quedaron congelados antes del test. Controlador y todos los hijos registrados terminaron. Se conservan pesos, logs, caches y resultados.

## Decisión después del piloto

**Hay una señal exploratoria favorable con115 imágenes, suficiente para justificar seguir investigando la mezcla. No justifica ampliar automáticamente a1000 ni promover un modelo.** El deterioro de Sobremadura, los pocos grupos de desarrollo, las mismas20 plantas y la cobertura angular limitada impiden convertir esta mejora en una afirmación de generalización.

Priorizar revisión de confusiones/apariencia Sobremadura y de la exposición efectiva por clase; luego una prueba congelada en sesiones realmente nuevas. Si se autoriza ampliar, favorecer diversidad de puntos de vista y dominios sobre más repeticiones de las mismas plantas. No se ejecuta ninguna de esas propuestas ni se cambia la política de etiquetas como parte de este cierre.

Generación y su seguimiento siguen pausados. La revisión técnica de Codex está completa; la decisión del usuario sobre cualquier ampliación queda pendiente. No se presenta como validación humana de las anotaciones ni como comparación factorial de luz/materiales.

Los resultados automáticos originales se preservan en `evaluation/report.md` y `evaluation/completion.json`; su marca inicial de revisión pendiente queda resuelta por `review_completion.json`, sin reescribir sus hashes. `evaluation/postrun_diagnostics.json` y `evaluation/reviewed_report.html` ofrecen estratos, curvas y ejemplos de las tres semillas.
