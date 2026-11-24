# Diagnóstico de Sobremadura en el piloto115

**La caída observada se explica por un cambio en los errores de clasificación y en el orden de confianza, con más falsos positivos y pérdidas de confianza en algunos capachos reales. No es una omisión uniforme ni hay evidencia de que la geometría de las cajas empeore en general.** El origen de aprendizaje más plausible es una representación sintética estrecha y dominante de la clase, junto a diferencias de escala/dominio y límites de anotación. Son hipótesis; no se ejecutó una ablación causal.

Se analizaron las predicciones congeladas de seis modelos sobre las mismas94 fotos de desarrollo (58 cajas Sobremadura). No hubo inferencia nueva, entrenamiento, modificación de labels ni renders. La generación y su automatización permanecen pausadas; el seguimiento del piloto ya estaba eliminado.

## Qué cambia por semilla

Umbral común0,076076, fijado previamente sólo con val. TP/FP/FN son respecto a las anotaciones, con asignación de confianza e IoU≥0,5 dentro de la clase. AP se reproduce con los flags nativos del evaluador original y no depende de escoger este umbral operativo.

| Semilla | AP real → mezcla (%) | TP real → mezcla | FP real → mezcla | FN real → mezcla |
|---|---:|---:|---:|---:|
| 20261022 | 11.43 → 11.27 | 10 → 16 | 18 → 53 | 48 → 42 |
| 20261023 | 11.17 → 10.43 | 19 → 14 | 73 → 42 | 39 → 44 |
| 20261024 | 13.00 → 11.63 | 12 → 17 | 48 → 83 | 46 → 41 |

En las semillas22 y24 aumentan los TP, pero los FP crecen mucho más. En23 disminuyen los FP, a costa de perder TP. Por tanto, ajustar un único umbral no explica ni resuelve la caída de AP50–95 medio de11,87 a11,11%. No se retocó el umbral con el test.

## Atribución de errores observados

Sobre las tres semillas se cuentan174 apariciones de las mismas58 cajas reales, no174 objetos independientes:

| Medida al umbral fijo | Real | Mezcla |
|---|---:|---:|
| Sobremadura correctamente detectada | 41 | 47 |
| Sobremadura sin TP de su clase | 133 | 127 |
| Sobremadura atribuida a Pintona, diagnóstico por objetivo | 38 | 60 |
| Sobremadura atribuida a Madura, diagnóstico por objetivo | 15 | 7 |
| FP Sobremadura sobre otra clase anotada | 97 | 115 |
| FP Sobremadura sin solapamiento relevante con una etiqueta | 25 | 45 |
| FP por caja con IoU0,1–0,5 | 6 | 7 |
| FP por duplicación/asignación | 11 | 11 |

De los41 TP reales,27 siguen siendo TP,7 pasan a confusión con Pintona,2 con Madura y5 quedan por debajo del umbral. A la vez aparecen20 TP nuevos: el deterioro convive con mejoras.

Los estados por objetivo usan el mejor solapamiento de las predicciones no correctas para explicar por qué falta un TP. No equivalen a una matriz global de asignación sin clase. Las categorías FP son disjuntas: duplicado, otra clase anotada, localización parcial, o fondo/no anotado. Un FP métrico sobre una zona sin etiqueta puede ser un capacho real omitido por política; no se certifica como fondo biológico sin revisión humana.

## Ranking y cajas

La precisión de Sobremadura empeora en parte del rango de recall y la caída se observa en diversos IoU; no es sólo el umbral0,076. Los recortes muestran cajas bien colocadas cuya clase o confianza cambia de forma perjudicial.

Entre los27 pares que siguen siendo TP en ambos modelos, las medianas de IoU son 0.922 y0.929. Esta comparación está condicionada a acertar en ambos; no permite afirmar igualdad geométrica de todos los errores. Tampoco respalda atribuir la caída a un deterioro general de las cajas.

![Curvas de precisión/recall e IoU](../../outputs/reviewed_augmentation_115_20261031/diagnostics/sobremadura_20261031/precision_recall.png)

## Ejemplos comparados

Los casos se eligieron para inspeccionar errores: primero regresiones presentes en más semillas y luego una nueva predicción Sobremadura de confianza alta sobre otra clase anotada. No son una muestra aleatoria ni prueban frecuencia. Cada par conserva foto y región idénticas. Verde: etiqueta; rojo: candidato seleccionado. Un rojo discontinuo está por debajo del umbral y se muestra sólo para diagnosticar la pérdida de confianza.

### Fila113: conserva la caja, pierde la confianza de clase

En la semilla23 el control emite Sobremadura0,100, además de Pintona0,478 para la misma zona. La mezcla reduce Sobremadura a0,019 y eleva Pintona a0,748. Las cajas del objeto conservan IoU≈0,95. El control también era ambiguo: no se oculta su predicción competidora ni se presenta como un clasificador inequívocamente correcto. La pérdida de Sobremadura se repite en la semilla24.

![Confusión y caída de confianza](../../outputs/reviewed_augmentation_115_20261031/diagnostics/sobremadura_20261031/error_pair_1.png)

### Fila183: omisión al umbral común

El control23 reconoce el capacho pajizo etiquetado Sobremadura con0,480; la mezcla sólo conserva un candidato de esa clase con0,005, descartado al umbral común. En24 ocurre algo parecido (0,800 frente a0,007). No es necesario que el objeto desaparezca geométricamente para perder AP: también importa su lugar en el ranking de confianza.

![Omisión comparada](../../outputs/reviewed_augmentation_115_20261031/diagnostics/sobremadura_20261031/error_pair_2.png)

### Fila548: nueva confusión sobre una caja anotada Madura

La etiqueta es Madura. El control24 propone Pintona0,092 y la mezcla Sobremadura0,646. **Ambos fallan la clase anotada**; el segundo añade un FP Sobremadura de confianza alta. El aspecto pardo del capacho no permite por sí solo decidir que la anotación sea errónea ni inferir madurez interna. Es un caso prioritario para adjudicar criterios humanos de apariencia.

![Falso positivo respecto a otra clase anotada](../../outputs/reviewed_augmentation_115_20261031/diagnostics/sobremadura_20261031/error_pair_3.png)

## Posibles causas de aprendizaje: evidencia y límites

1. **Dominio sintético dominante dentro de Sobremadura.** Se reconstruyeron las exposiciones por clase usando las secuencias reales y el filtro geométrico nativo; las sumas coinciden exactamente con los seis logs. El control ve18875 apariciones Sobremadura reales; la mezcla ve15132 reales más1056777 sintéticas. Es decir, reduce19,8% la exposición real de esa clase y **98,59% de sus apariciones de Sobremadura son sintéticas**. No equivale al peso de gradiente ni demuestra causalidad; sí puede desplazar las claves de clasificación aprendidas.
2. **Escala y representación limitadas.** En las etiquetas crudas de train, el lado mínimo mediano de Sobremadura es100,5px real y7px sintético, normalizado a960. El contraste incluye instancias de fondo anotadas en sintético que la política real suele omitir. El filtro>2px nativo deja pasar numerosos objetos pequeños: no garantiza equivalencia de escala ni de detalle. No se borran cajas ni se cambia esa política durante este análisis.
3. **Cobertura de apariencia.** Los recortes de train muestran variación real de contorno, venación, color y reflejos; los sintéticos seleccionados son más regulares y predominantemente oliva/pajizos. El perfil congelado usa `calyx_straw_v2` para esta clase y declara `wear_fraction=0` y parámetros heurísticos. No representa por sí solo todo el espectro pajizo, pardo y oscuro que aparece en las etiquetas reales. Los ejemplos reales de train también incluyen amarillos/verdes: no se afirma que Sobremadura deba ser siempre marrón.
4. **Límites semánticos y pocos grupos.** El caso548 y la variación visual aconsejan revisar la definición y adjudicar desacuerdos; no se demuestra un error de etiqueta. La apariencia del capacho no es madurez agronómica validada. Sólo hay58 etiquetas de esta clase y seis grupos desiguales; no se puede identificar qué parte del descenso es estable fuera de ellos.

![Apariencia de entrenamiento](../../outputs/reviewed_augmentation_115_20261031/diagnostics/sobremadura_20261031/training_appearance.png)

La lámina usa la mayor caja Sobremadura de seis imágenes equiespaciadas por orden de fuente en cada dominio. Son recortes ampliados a una escala visual común, no una medición de realismo ni un resumen representativo de todas las instancias. No se escogieron por aciertos del detector.

## Incertidumbre del descenso

Reutilizando exactamente los200 sorteos por grupos del piloto, el intervalo descriptivo95% para la diferencia Sobremadura es**[−3,69,+4,74] pp**. Es post hoc, condicionado a las tres clases y con semillas fijas; incluye cero ampliamente. La caída fue negativa en las tres semillas sobre este test, pero no se demuestra un deterioro generalizable.

Al retirar `component_8` (23 de las58 cajas Sobremadura), la diferencia media pasa de−0,76pp a aproximadamente−0,002pp. Retirar `component_58` la lleva a−2,66pp. AP no es aditivo por grupo; esta sensibilidad muestra concentración y compensaciones, no una atribución causal del efecto.

## Decisión propuesta

**Mantener pausada la generación.** Antes de más imágenes, revisar humanamente los casos ambiguos y la definición de Sobremadura; ampliar cobertura de apariencia y escala antes que repetir la misma receta. Para verificar causas, un próximo experimento autorizado debería cambiar una sola cosa: exposición/dosis o representación de la clase, con controles emparejados y selección sólo en val. Este diagnóstico no fija hiperparámetros con el test ni autoriza reentrenamiento, nueva poda, clases nuevas o edición de las anotaciones.

Se verificaron las entradas congeladas de entrenamiento y la pausa de generación. Predicciones, pesos, métricas del piloto y RGB/labels originales siguen intactos. Las pruebas del diagnóstico cubren duplicados, confusión, localización y baja confianza. Artefactos: `diagnosis.json`, `additional_checks.json`, `plot_manifest.json` e `index.html` en la carpeta de diagnóstico. Los diez errores preexistentes de localizadores del grafo se distinguen de cualquier regresión.
