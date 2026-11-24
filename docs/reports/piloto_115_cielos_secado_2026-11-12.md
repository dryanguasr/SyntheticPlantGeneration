# Piloto de 115 imágenes corregidas y tres semillas — 12 de noviembre de 2026

## Alcance autorizado y estado

El usuario autorizó 115 RGB nuevos con la corrección de dominante azul, pocas
sobremaduras y cielos variados, seguidos de seis entrenamientos nuevos:
sintética115+clásica frente a real+clásica con semillas 20261022/23/24. No se
amplía el banco de 503 imágenes, cuya generación sigue pausada. No se autoriza
expansión automática, publicación ni promoción de modelos.

Raíz local de evidencia: `outputs/daylight_augmentation_115_20261112/`.
La ejecución y la revisión técnica están **completadas**: 115 imágenes nuevas,
seis corridas nuevas y evaluación de las tres semillas. El AP macro sube sólo
0,87 puntos, mientras **Sobremadura cae 2,54 puntos y empeora en las tres
semillas**. No se recomienda ampliar cantidad todavía; la generación queda
pausada, pendiente de decisión del usuario. Los resultados de octubre se
conservan separados de los de esta ejecución.

## Banco y controles de captura

Se repiten exactamente las 115 posiciones de cámara seleccionadas en el piloto
anterior, sin la captura casi negra. Siete disposiciones originales usan doce
árboles en cuatro hileras, del mismo pool admitido de veinte árboles. Cada
estructura conserva hashes, órganos y dimensiones: no hay nueva poda,
contracción ni desplazamiento para simular el secado. Los parámetros de
contracción de las muestras aisladas no se aplican a estas plantas válidas.
Las pérdidas originales de frutos, hojas y proxy foliar L×W siguen siendo
estrictamente inferiores al 5 % por planta.

Las asignaciones buscan aproximadamente 3 % de sobremaduras por escena y
como máximo 5 % de los capachos visibles por imagen. Su pigmentación progresa
desde venas y pedúnculo; los grados de secado, aspereza y gris carbón son
apariencia, sin afirmar madurez interna del fruto ni prevalencia real medida.
Los 69 cielos despejados, 29 con bruma y 17 cubiertos son una elección de
ingeniería, con variación de iluminación independiente de la arquitectura.
La corrección cromática del ambiente conserva el cielo observado por cámara,
el horizonte y las texturas, pero calibra la cromaticidad de la radiancia que
ilumina. No equivale a una radiometría atmosférica intacta ni demuestra realismo.

Se conserva 960×720, Cycles/OptiX, doce muestras y denoising. Cada RGB es nuevo.
Las máscaras nativas históricas se reutilizan únicamente si coinciden **bit a
bit** cámara, geometría binaria, visibilidad e intrínsecos. Además se renderiza
una máscara nativa nueva por disposición y se exige SHA idéntico. Los 115 pares
se auditan por píxeles, IDs, cajas, clases y coordenadas YOLO. No se toleran
desviaciones ni se eliminan anotaciones pequeñas del RGB.

La admisión geométrica original exige cero cruces duros auditados, suelo a
1 mm y orientación/unión válidas. Proximidades son advertencias, hoja-hoja es
ocupación blanda y flores/contexto no tienen certificación exhaustiva. La
invariancia geométrica preserva esa evidencia estática; no certifica dinámica.

## Comparación emparejada

Se conservan los 461 train, 88 val y 94 test reales históricos y los pesos
`yolo26n.pt` originales. Cada corrida usa 4.000 actualizaciones, batch dos,
960 px y 8.000 exposiciones de imagen. El control real sustituye los slots
sintéticos por repeticiones reales, conservando posiciones originales reales,
RNG de aumentación y LR emparejados. No se agregan screenings ni otros brazos.

La receta, el entrenador y el evaluador conservan el protocolo del piloto
anterior; pruebas comparan la llamada de entrenamiento y las funciones de
evaluación. Ultralytics 8.4.114 aplica sus filtros nativos: ancho/alto >2 px
y área relativa tras transformación. Es detección, no segmentación; no existe
un corte adicional de 10 px ni un mínimo absoluto de máscara inventado.

Los seis pesos se congelan antes del test. El umbral operativo se elige sólo
en val del control real de la primera semilla. Se informarán AP macro y por
clase, colapsado, precisión/recall/confusión y tamaños/densidad, tres semillas,
media/DE y delta. Bootstrap común de 200 sorteos por seis grupos, condicionado
a tres clases y semillas fijas. El test fue consultado históricamente: es
desarrollo, no un holdout externo nuevo ni una afirmación confirmatoria.

Completar 4.000 actualizaciones por corrida no significa que `best.pt` conserve
la última: la selección por val puede elegir un checkpoint anterior. Se
separarán exposición de la corrida completa y del prefijo seleccionado; la
época recuperada del máximo único de CSV redondeado se marcará como inferida,
y una ambigüedad no se resolverá inventando una época.

Este contraste estima el efecto conjunto del banco nuevo. Texturas,
proporciones de clases y distribución de cielos cambiaron simultáneamente;
no atribuye causalidad a una sola corrección. La revisión final atenderá en
particular Sobremadura y Madura antes de recomendar cualquier ampliación.

## Evidencia y revisión pendientes

`bank/plan.json`, `source_lock.json`, `baseline.json`, asignaciones,
`prepared/*/native_mask_validation.json`, `views/*/pixel_audit.json` y
`sealed.json` registran la captura. `pilot/` contendrá el plan, lock de
entrenamiento, seis corridas, emparejamientos y evaluación. Las galerías son
revisión técnica de Codex; no equivalen a certificación humana individual.

La captura quedó cerrada en **115 RGB nuevos**, con 69 condiciones despejadas,
29 de bruma y 17 cubiertas; son configuraciones de captura, no afirmación de
cielo visible en cada cámara. Hay 41 vistas cercanas, 58 medias y 16 lejanas.
Los veinte árboles están presentes y tienen al menos una instancia visible;
son veinte fuentes morfológicas y siete disposiciones, no 115 plantas
independientes. Se preservaron las 503 imágenes históricas y su pausa.

Se auditaron de nuevo los **93.603 registros de instancias**: 44.872 Pintona,
45.053 Madura y 3.678 Sobremadura (3,93 % de las apariciones etiquetadas).
La fracción visible máxima de Sobremadura es exactamente 5 %, no estrictamente
menor. Los siete pases nativos nuevos tienen SHA idéntico a las máscaras
originales; las 115 cámaras, geometrías y etiquetas superan la auditoría exacta.
Se verificaron las 996 dependencias congeladas de captura y los locks
históricos, incluyendo las 1.999 entradas del piloto anterior.

Las llamadas de render acumularon 3.863,17 s (1,07 h); los 114 trabajadores,
incluyendo carga, validación y salida, 15.731,05 s (4,37 h). La ventana nativa
desde preparación hasta revisión fue 5,04 h despiertas, con ingeniería y
supervisión; suspensión excluida. No son medidas de tiempo de GPU puro.
El reciclado frecuente acotó memoria sin cambiar resolución ni muestreo.

Manifiesto SHA-256:
`22a906e9713a90e93d17af1c6731a33815f8c6f87337f3f8d07a4f70dd452fde`.
La revisión técnica visual cubrió los nueve grupos cielo/profundidad y seis
muestras recientes adicionales. Persisten repetición procedural, apariencia
sintética y oclusiones foliares de las cámaras originales. No se afirma
fotorealismo ni eficacia antes de medirla.

## Resultados efectivos

AP50–95 expresado en porcentaje; diferencias en puntos porcentuales (pp).
DE entre las tres semillas fijas, no error de generalización.

| Métrica | Real + clásica, media ± DE | Sintética115 + clásica, media ± DE | Delta medio |
|---|---:|---:|---:|
| Macro tres clases | 18,83 ± 0,89 | 19,70 ± 0,74 | +0,87 pp |
| Pintona | 36,92 ± 2,34 | 39,92 ± 1,25 | +3,00 pp |
| Madura | 7,70 ± 1,06 | 9,86 ± 0,60 | +2,16 pp |
| Sobremadura | 11,87 ± 0,99 | 9,32 ± 1,00 | **−2,54 pp** |
| Localización colapsada | 38,65 ± 3,03 | 41,00 ± 1,59 | +2,34 pp |

| Semilla | Macro real | Macro mixto | Delta macro | Sobre real | Sobre mixto | Delta Sobre |
|---|---:|---:|---:|---:|---:|---:|
| 20261022 | 17,92 | 19,26 | +1,34 | 11,43 | 9,77 | −1,66 |
| 20261023 | 18,87 | 20,55 | +1,68 | 11,17 | 10,02 | −1,14 |
| 20261024 | 19,70 | 19,29 | −0,41 | 13,00 | 8,18 | −4,82 |

El delta macro emparejado tiene DE 1,12 pp. Su intervalo descriptivo del 95 %,
con 200 sorteos comunes por seis grupos condicionado a las tres clases, es
**[−1,13; +3,80] pp**. El intervalo post hoc de Sobre con los mismos sorteos
es **[−6,87; +1,28] pp**. No prueban un beneficio general ni un daño
confirmatorio; sí justifican prudencia ante una clase prioritaria que retrocede
consistentemente en estas tres ejecuciones. Hay 94 imágenes test de desarrollo,
con 806 Pintona, 91 Madura y 58 Sobremadura anotadas, no un nuevo test externo.

El umbral común, elegido sólo en val real de la primera semilla, fue
0,076076. A ese umbral la precisión micro media global pasa de
34,67 ± 1,34 % a 38,65 ± 3,86 %, y el recall de 62,34 ± 4,63 % a
63,70 ± 4,48 %. Ese agregado no representa por sí solo a Sobremadura:

| Semilla | Sobre real TP / FP / FN | Sobre mixto TP / FP / FN |
|---|---:|---:|
| 20261022 | 10 / 18 / 48 | 11 / 24 / 47 |
| 20261023 | 19 / 73 / 39 | 14 / 60 / 44 |
| 20261024 | 12 / 48 / 46 | 10 / 37 / 48 |

Las filas repiten las mismas 58 verdades en cada semilla: no son 174 objetos
independientes. La confusión con emparejamiento agnóstico, separada de los TP
por clase de la tabla, registra 46 asignaciones Sobre→Pintona en los controles
y 70 en los mixtos al sumar las tres semillas. No se deben mezclar ambos
procedimientos de emparejamiento como si sus diagonales fueran iguales.

Localización operativa a IoU ≥0,5, sin exigir clase correcta y con el mismo
umbral; promedio de tres semillas sobre los mismos objetivos de desarrollo:

| Estrato real | Objetivos por semilla | Recall localizado real | Recall localizado mixto |
|---|---:|---:|---:|
| Lado mínimo 16–32 px | 46 | 30,43 % | 24,64 % |
| 32–64 px | 410 | 53,82 % | 54,07 % |
| ≥64 px | 499 | 85,50 % | 87,64 % |
| Densidad 1–7 objetivos/imagen | 157 | 77,07 % | 73,89 % |
| 8–22 objetivos/imagen | 653 | 69,47 % | 71,82 % |
| >22 objetivos/imagen | 145 | 59,77 % | 58,85 % |

El resultado agregado no implica una mejora uniforme por escala o densidad.
Estos cortes describen las evaluaciones guardadas, sin elegir otro umbral ni
modificar el test o el entrenamiento después de observarlos.

## Qué muestran las curvas y los ejemplos revisados

Se inspeccionaron `pilot/evaluation/curves.png`, las cuatro escenas reales de
`prediction_examples.png`, la curva precisión-recall de Sobre y tres pares
de errores recuperados de las predicciones guardadas. No hubo inferencia ni
entrenamiento adicional para ese diagnóstico.

La pérdida de entrenamiento continúa bajando, pero la validación alcanza
máximos intermedios y luego fluctúa o cae. Los checkpoints elegidos, inferidos
de máximos únicos de CSV y contrastados con fitness, son:

| Semilla | Control real | Mixto |
|---|---:|---:|
| 20261022 | 2.000 actualizaciones | 2.000 |
| 20261023 | 2.000 | 2.000 |
| 20261024 | 2.500 | 3.000 |

Las seis corridas sí completaron 4.000. Comparar pérdidas absolutas entre brazos
no identifica por sí solo una causa: la densidad de etiquetas difiere mucho.

Ejemplos concretos, seleccionados para ilustrar regresiones y no su frecuencia:

- **Fila real 113, semilla 20261023:** capacho oscuro etiquetado Sobre. El
  control lo clasifica Sobre con 0,100; el mixto lo localiza correctamente pero
  lo clasifica Pintona con 0,928. La regresión también aparece en 20261024.
- **Fila 183, semilla 20261022:** capacho seco claro etiquetado Sobre. El control
  da 0,496; el mixto conserva una predicción Sobre de 0,051, por debajo del
  umbral común. También retrocede en 20261024.
- **Fila 364, semilla 20261024:** un capacho etiquetado Madura, con región
  proximal oscura, recibe Sobre 0,669 en el mixto. No se cambia su etiqueta:
  el caso ilustra que oscurecimiento y clase no se corresponden unívocamente.

El descenso de AP Sobre ya existe a IoU 0,5; no se limita a exigir cajas muy
precisas. Las curvas de ranking/confianza y los casos muestran confusiones y
pérdida de confianza además de fallos de localización. No demuestran qué
parámetro del generador causó cada error de aprendizaje.

## Exposición: pocas por escena no equivale a pocas durante aprendizaje

Cada corrida tuvo 8.000 exposiciones de imagen y 4.000 actualizaciones; total
48.000 exposiciones y 24.000 actualizaciones nuevas. Conteos tras aumentación
y filtros nativos, reconstruidos exactamente desde las secuencias guardadas:

| Semilla y brazo | Imágenes reales / sintéticas | Instancias reales / sintéticas |
|---|---:|---:|
| 20261022 real | 8.000 / 0 | 82.341 / 0 |
| 20261022 mixto | 6.412 / 1.588 | 65.743 / 1.074.467 |
| 20261023 real | 8.000 / 0 | 82.265 / 0 |
| 20261023 mixto | 6.404 / 1.596 | 65.498 / 1.080.369 |
| 20261024 real | 8.000 / 0 | 82.756 / 0 |
| 20261024 mixto | 6.402 / 1.598 | 65.631 / 1.079.881 |

Tras el filtro nativo quedan 4.723 etiquetas reales en 461 imágenes y 77.719
sintéticas en 115: medias de **10,25 frente a 675,82 etiquetas por imagen**.
Hay 363 Sobre reales y 3.356 sintéticas retenidas. Su lado mínimo mediano a
960 px es **100,51 px real frente a 14,00 px sintético**; 53,43 % de las Sobre
sintéticas retenidas siguen por debajo de 16 px, frente a 0,55 % de las reales.
16 px es aquí un descriptor de tamaño, **no un nuevo corte de entrenamiento**.
El filtro nativo >2 px no iguala estas distribuciones ni garantiza venas visibles.

En los tres mixtos completos se acumulan 139.700 apariciones Sobre sintéticas
y 15.132 reales: **90,23 % de las apariciones Sobre son sintéticas**, aunque
sólo representen 3,93 % del banco por número de etiquetas. Los controles suman
18.875 Sobre reales; el mixto reduce su exposición real 19,83 %. En los prefijos
de los checkpoints elegidos son 10.232 reales en controles frente a 8.841 reales
y 81.785 sintéticas en mixtos (−13,59 % de exposición real Sobre). Son
apariciones de etiquetas, no órganos independientes ni pesos de gradiente.

## Interpretación y decisión

**Observado:** la tanda técnica es válida, Pintona/Madura y localización
colapsada mejoran en promedio, pero Sobre empeora en las tres semillas, el
beneficio macro no es estable y persisten brechas muy grandes de escala y
densidad. La mejora visual no se tradujo en una mejora de la clase buscada.

**Hipótesis pendientes:** demasiadas instancias diminutas pueden aportar poca
señal venosa útil; el predominio de apariciones sintéticas y la menor exposición
real pueden influir; falta representar toda la variedad real, incluido secado
claro y tejido oscuro con venas verdes. Estas explicaciones no se identifican
causalmente con este contraste, que cambió conjuntamente texturas, proporciones
de clases, cielos e iluminación. No se atribuye el resultado sólo a manchas,
cielos azules, aspereza o cantidad de Sobremadura.

**No escalar a más imágenes todavía.** Antes de otra ampliación, priorizar una
selección pequeña de encuadres con Sobre de tamaño informativo comparable al
train real y menor brecha de densidad, conservando plantas y anotaciones; revisar
la cobertura de secado claro/oscuro en train y la consistencia de etiquetas;
y separar factores en un siguiente contraste autorizado. No se ejecutó ninguna
de esas intervenciones ni se impuso un filtro nuevo por cuenta propia.

## Integridad, tiempos y entrega

Se comprobaron las 2.142 entradas del lock de entrenamiento, 996 de captura,
los seis pares best/last y tres controles de secuencias, aumentación y LR.
Los seis modelos se congelaron antes del test; todos los procesos propios
terminaron. La revisión técnica de Codex está completada; la decisión humana
sobre ampliar permanece pendiente. No hubo publicación ni promoción.

Entrenamiento de modelos: **2,22 h activas**; evaluación automática, **56,30 s**.
Una corrida mixta tardó 46,10 min durante una etapa en batería, frente a
16,82 y 20,06 min en las otras mixtas; se observó alimentación de red y
recuperación posterior. No se alteró la receta para compensar el rendimiento.
Los presupuestos históricos conservan sus hashes y no se reiniciaron.

Artefactos locales principales dentro de la raíz de ejecución:

- `bank/review.html`, `review_summary.json`, `technical_review.json`,
  `pixel_reverification.json` y `sealed.json`.
- `pilot/evaluation/comparison.json`, `summary.json`, `curves.png` y
  `prediction_examples.png`; `evaluation_lock.json` y seis `completion.json`.
- `pilot/diagnostics/sobremadura/diagnosis.json`, `precision_recall.png`,
  `comparison_clear.png` y tres pares de errores.
- `pilot/diagnostics/exposure/exposure.json` con prefijos seleccionados y
  distribuciones; `final_summary.json` y `final_verification.json` con hashes.

Los SHA completos de best/last y del peso original están en esos manifiestos;
se conservan fuentes, capturas anteriores y resultados negativos. La generación
histórica sigue pausada y no existe ampliación automática.

El grafo se actualizó con esta ruta y sus diagnósticos. El validador conserva
exactamente los diez errores de localizadores ya registrados antes del trabajo,
sin regresiones nuevas; `graph_before.txt` y `graph_final.txt` son idénticos en
esa salida. Se preservaron los cambios locales ajenos, sin commit ni push.
