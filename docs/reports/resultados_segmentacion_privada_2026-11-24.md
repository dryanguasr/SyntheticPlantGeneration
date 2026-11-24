# Resultados de los pilotos de segmentación de capachos

**Corte editorial del 24 de noviembre de 2026.** La serie de fotografías reales y la comparación de aumentación completaron 18 corridas cada una. Este informe reúne las métricas agregadas y el protocolo que las originó. Es una base para redactar el estudio y planear su repetición con anotaciones humanas depuradas.

## Protocolo compartido

- Cada corrida partió de los mismos pesos YOLO26n-seg y usó 960 px, lotes de dos, 4.000 actualizaciones AdamW y 8.000 exposiciones de imagen. Se aplicó un decaimiento de pesos de 0,0005 y una tasa de aprendizaje lineal de 0,0002 a 0,000002 por actualización. Las semillas fueron 20261022, 20261023 y 20261024. El volteo horizontal y la ganancia de brillo de 0,9 a 1,1 se fijaron por semilla y posición.
- Se conservaron 88 fotos de validación y 94 de desarrollo histórico, repartidas en cuatro y seis grupos de captura respectivamente. Los pesos de cada campaña se sellaron antes de evaluar desarrollo. Las 94 fotos ya se consultaron en campañas previas y sustentan una lectura exploratoria.
- Las referencias de entrenamiento son máscaras privadas revisadas a partir de RGB y borradores de MobileSAM. El detector que guio las propuestas ya había visto el conjunto histórico de entrenamiento. Las clases Pintona, Madura y Sobremadura describen el aspecto visible del capacho. Las regiones sin resolver quedaron fuera de la supervisión allí donde carecían de una etiqueta válida. La evaluación conserva sus referencias históricas.
- El AP50–95 de máscaras se promedia entre los umbrales de IoU de 0,50 a 0,95. El AP macro da igual peso a las tres clases. El AP sin clase evalúa la localización de máscaras ignorando la etiqueta de apariencia. Las tablas informan porcentajes, desviación estándar muestral entre semillas y AP macro de cada semilla en el orden indicado. Las diferencias se expresan en puntos porcentuales y se calculan antes de redondear.

## Serie de 20 a 461 fotografías reales

Las seis cohortes fueron acumulativas. El corpus final contiene 5.610 máscaras con clase, incluidas 145 Sobremaduras, además de 3.289 máscaras no resolubles y 772 regiones excluidas de la pérdida. Comprende las 50 imágenes asignadas a revisión cruzada con etiquetas preparadas para este piloto.

Con presupuesto fijo, entre 20 y 461 fotos el AP macro subió 13,22 puntos en validación y 5,84 en desarrollo. En desarrollo, el salto de 160 a 461 añadió 0,38 puntos macro. El AP de Sobremadura alcanzó su valor medio más alto en 160 fotos, con 9,55 %. Con 461 fotos, los modelos acertaron entre 9 y 13 de las 58 referencias Sobremadura y omitieron entre 22 y 34 por semilla. Estos recuentos usan el umbral elegido en validación para cada corrida y un IoU de máscara de al menos 0,50.

### Validación

| Fotos | Máscaras con clase | Macro ± DE | Pintona | Madura | Sobremadura | Sin clase | Macro por semilla |
|---:|---:|---:|---:|---:|---:|---:|---|
| 20 | 355 | 14,90 ± 1,65 | 29,40 | 14,50 | 0,80 | 31,32 | 16,63 / 13,33 / 14,73 |
| 40 | 758 | 17,21 ± 0,88 | 31,58 | 18,38 | 1,67 | 32,70 | 17,12 / 18,14 / 16,38 |
| 80 | 1.530 | 20,37 ± 0,51 | 35,80 | 21,19 | 4,11 | 36,01 | 20,21 / 20,94 / 19,96 |
| 160 | 3.355 | 24,84 ± 1,39 | 37,46 | 23,96 | 13,11 | 38,14 | 23,66 / 26,37 / 24,49 |
| 320 | 4.326 | 27,41 ± 1,12 | 39,24 | 25,43 | 17,56 | 40,83 | 28,62 / 27,22 / 26,40 |
| 461 | 5.610 | 28,12 ± 1,57 | 39,48 | 25,78 | 19,09 | 41,30 | 29,87 / 27,63 / 26,85 |

### Desarrollo histórico

| Fotos | Máscaras con clase | Macro ± DE | Pintona | Madura | Sobremadura | Sin clase | Macro por semilla |
|---:|---:|---:|---:|---:|---:|---:|---|
| 20 | 355 | 10,63 ± 0,91 | 28,67 | 2,18 | 1,03 | 30,48 | 10,85 / 9,63 / 11,40 |
| 40 | 758 | 11,34 ± 0,80 | 30,03 | 3,20 | 0,77 | 31,69 | 12,15 / 10,55 / 11,30 |
| 80 | 1.530 | 13,39 ± 0,66 | 32,25 | 5,46 | 2,46 | 34,05 | 14,04 / 13,41 / 12,71 |
| 160 | 3.355 | 16,09 ± 0,85 | 31,59 | 7,14 | 9,55 | 33,97 | 16,38 / 16,76 / 15,13 |
| 320 | 4.326 | 16,35 ± 0,58 | 33,90 | 9,32 | 5,83 | 36,84 | 15,95 / 17,02 / 16,09 |
| 461 | 5.610 | 16,47 ± 0,38 | 33,55 | 8,73 | 7,13 | 36,42 | 16,08 / 16,49 / 16,84 |

## Aumentación sintética y fotogramas reales

Cada brazo conservó la primera exposición de cada una de las 461 fotos. Las exposiciones nuevas sustituyeron repeticiones. Los brazos sintéticos usaron el mismo banco de 115 vistas. El brazo de encuadre priorizó repeticiones de vistas de tamaño y densidad más cercanos a los reales, con las mismas posiciones y reparto por escena que el de 240 sin priorización.

Se sellaron 28 de 120 fotogramas candidatos. Los cuatro grupos de captura proceden del mismo predio y día. Sus 872 máscaras resueltas se reparten en 859 Pintonas, 10 Maduras y 3 Sobremaduras. Se registraron además 551 instancias inciertas y 11 regiones de exclusión. El brazo de fotogramas se evaluó por separado del sintético.

| Brazo | Exposiciones de imagen sustituidas sobre 8.000 | % de instancias expuestas de la fuente añadida |
|---|---:|---:|
| Sólo real | 0 | 0,00 |
| Sintética baja | 120 | 50,30 |
| Sintética media | 240 | 67,44 |
| Sintética alta | 600 | 84,43 |
| Sintética media con encuadre | 240 | 62,07 |
| Real con fotogramas | 458 | 13,44 |

La dosis de 240 sin priorización mejoró en las tres semillas en desarrollo, tanto en AP macro (+1,42 puntos de media) como en Sobremadura (+1,34). En validación ganó 1,87 puntos de macro y 1,63 en Sobremadura. En esa partición, la mejora de AP de Sobremadura se concentró en una semilla. Al umbral operativo compartido, la sensibilidad de Sobremadura pasó de 41,15 % a 39,06 % en validación y de 18,39 % a 19,54 % en desarrollo.

Priorizar encuadre produjo +0,29 puntos de AP macro en validación y −0,14 en desarrollo respecto a la misma dosis sin priorizar. Mantuvo la dosis de imágenes y expuso alrededor de un 21 % menos de máscaras sintéticas. La dosis alta perdió 1,63 puntos de Sobremadura en validación frente al control real. Los fotogramas mostraron un efecto modesto y dependiente de la partición, con −0,20 puntos macro en validación y +0,92 en desarrollo.

### Validación

| Brazo | Macro ± DE | Pintona | Madura | Sobremadura | Sin clase | Macro por semilla |
|---|---:|---:|---:|---:|---:|---|
| Sólo real | 28,12 ± 1,57 | 39,48 | 25,78 | 19,09 | 41,30 | 29,87 / 27,63 / 26,85 |
| Sintética baja | 28,24 ± 1,11 | 40,37 | 25,77 | 18,57 | 41,87 | 29,23 / 27,03 / 28,45 |
| Sintética media | 29,99 ± 1,62 | 40,34 | 28,90 | 20,72 | 41,78 | 30,20 / 28,26 / 31,49 |
| Sintética alta | 28,24 ± 2,09 | 39,84 | 27,40 | 17,46 | 41,38 | 30,04 / 25,94 / 28,73 |
| Sintética media con encuadre | 30,28 ± 0,26 | 39,81 | 29,52 | 21,51 | 41,70 | 30,55 / 30,05 / 30,23 |
| Real con fotogramas | 27,92 ± 1,11 | 39,68 | 25,50 | 18,56 | 41,49 | 28,36 / 26,66 / 28,73 |

### Desarrollo histórico

| Brazo | Macro ± DE | Pintona | Madura | Sobremadura | Sin clase | Macro por semilla |
|---|---:|---:|---:|---:|---:|---|
| Sólo real | 16,47 ± 0,38 | 33,55 | 8,73 | 7,13 | 36,42 | 16,08 / 16,49 / 16,84 |
| Sintética baja | 16,80 ± 0,55 | 34,58 | 8,45 | 7,37 | 37,61 | 16,24 / 17,33 / 16,82 |
| Sintética media | 17,89 ± 0,83 | 35,23 | 9,98 | 8,47 | 38,20 | 17,13 / 17,77 / 18,78 |
| Sintética alta | 17,12 ± 0,52 | 34,48 | 9,23 | 7,64 | 37,47 | 16,69 / 17,70 / 16,97 |
| Sintética media con encuadre | 17,75 ± 0,20 | 35,36 | 9,33 | 8,58 | 38,35 | 17,54 / 17,79 / 17,93 |
| Real con fotogramas | 17,39 ± 0,78 | 34,35 | 9,93 | 7,90 | 37,77 | 16,53 / 18,06 / 17,58 |

Las semillas se emparejaron por control. Para omisiones y confusiones se aplicó a cada brazo el umbral del control real de su semilla, ajustado en validación. Las medias de AP integran la curva completa de precisión y sensibilidad.

## Tamaño de objeto y límites de interpretación

Bandas por área de máscara a 960 px. Pequeña implica menos de 32² px, mediana entre 32² y menos de 96² px y grande desde 96² px. El siguiente AP de desarrollo histórico ignora la etiqueta de apariencia.

| Comparación | Pequeña | Mediana | Grande |
|---|---:|---:|---:|
| Serie real · 20 fotos | 3,19 | 30,71 | 58,08 |
| Serie real · 40 fotos | 4,37 | 31,17 | 59,19 |
| Serie real · 80 fotos | 3,58 | 32,70 | 63,19 |
| Serie real · 160 fotos | 4,50 | 32,17 | 63,63 |
| Serie real · 320 fotos | 2,82 | 34,18 | 66,26 |
| Serie real · 461 fotos y control real de aumentación | 2,85 | 33,75 | 65,06 |
| Sintética baja | 2,46 | 34,36 | 66,69 |
| Sintética media | 4,32 | 35,63 | 64,88 |
| Sintética alta | 2,64 | 35,14 | 64,26 |
| Sintética media con encuadre | 3,94 | 35,61 | 65,02 |
| Real con fotogramas | 3,31 | 34,73 | 65,12 |

Desarrollo tiene 50 instancias pequeñas, de las que una sola es Sobremadura. En validación, 45 de las 64 Sobremaduras pertenecen a un mismo grupo de captura. Las cifras desagregadas en esos casos tienen soporte limitado. Las semillas estiman variación de entrenamiento sobre referencias compartidas. El alcance agrícola y la madurez interna del fruto quedan fuera de la evaluación.

Para la repetición con anotaciones adjudicadas, la opción prioritaria es contrastar el control real con la dosis de 240. El manifiesto de anotaciones se puede sustituir verificando identidad y dimensiones de los RGB. Conservar secuencias, referencias y umbrales permite atribuir mejor las diferencias a la fuente de anotación.

## Verificación y recuperación

Cada campaña auditó 18 corridas, 36 evaluaciones, 72.000 actualizaciones y 144.000 exposiciones. El comparativo de aumentación y fotogramas verificó pesos y checkpoints, las predicciones evaluadas y el recuento por fuente y clase frente a las secuencias selladas. El control real reprodujo las predicciones de validación de la serie de 461 fotos en las tres semillas.

La serie real retomó la primera corrida de 40 fotos desde 1.500 actualizaciones después de comprobar la equivalencia de los arreglos de entrada. Un intento inicial de 461 fotos falló antes del primer checkpoint debido al tipo de máscara devuelto por el asignador en un lote sin positivos. La corrección fue verificada y esa corrida volvió a partir de los pesos iniciales. En la segunda campaña, la segunda semilla de encuadre se recuperó desde un checkpoint de 3.500 actualizaciones. El comparativo registró 5 h 25 min de trabajo en los entrenamientos cerrados.
