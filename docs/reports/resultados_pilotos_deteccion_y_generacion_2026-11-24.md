# Resultados de detección, generación y revisión de capachos

Corte editorial del 24 de noviembre de 2026. Resume los experimentos del 21 de octubre al 13 de noviembre. Los AP de este informe corresponden a **detección por cajas** salvo que se indique otro alcance. Pintona, Madura y Sobremadura describen la apariencia visible del capacho.

## Datos y comparaciones de detección

La auditoría de la exportación anotada examinó 673 imágenes y 7.005 instancias. Encontró ocho grupos de duplicados exactos entre particiones y 25 cruces internos de polígonos en 22 imágenes. La versión depurada agrupó secuencias y posibles copias, excluyó esas 22 imágenes y separó ocho copias exactas. Quedaron **461 imágenes de entrenamiento, 88 de validación y 94 de desarrollo**. Las 94 de desarrollo contienen 955 objetos anotados, de los cuales 806 son Pintonas, 91 Maduras y 58 Sobremaduras. Dos de los seis grupos concentran 73 imágenes. Este conjunto ya se había consultado durante el desarrollo del proyecto y no establece independencia entre sesiones.

| Campaña y contraste | Control macro | Tratamiento macro | Δ macro | Δ Sobremadura |
|---|---:|---:|---:|---:|
| Unión depurada, 22/10 · mezcla de 384 reales y 96 sintéticas | 18,65 % | 18,06 % | −0,59 pp | +0,44 pp |
| Extensión exploratoria, 26/10 · 461 reales y 115 sintéticas con clásica frente a real con clásica | 18,47 % | 20,81 % | +2,34 pp | +5,44 pp |
| Misma extensión · mezcla seleccionada frente a repetición real con clásica | 19,94 % | 20,81 % | +0,88 pp | — |
| Factorial de apariencia, 27/10 · controles reales con y sin clásica | 19,17 % | 19,14 % | −0,03 pp | −1,10 pp |
| Banco revisado, 31/10 · 115 sintéticas con clásica frente a real con clásica | 18,83 % | 20,89 % | +2,07 pp | −0,76 pp |
| Cielos y secado, 12/11 · 115 sintéticas nuevas con clásica frente a real con clásica | 18,83 % | 19,70 % | +0,87 pp | −2,54 pp |

AP50–95 en las 94 fotos de desarrollo. Los deltas publicados se calculan antes del redondeo. La primera comparación usa una semilla y las demás, tres semillas por brazo. Las filas responden preguntas distintas y cada contraste conserva su propio control. El AP macro promedia clases, mientras el AP colapsado mide localización sin exigir que coincida la clase.

**Unión depurada y video real.** Ambos brazos partieron de YOLO26n, usaron 960 px, lote de dos y completaron 4.615 actualizaciones en 20 épocas. El AP colapsado pasó de 42,99 % a 39,21 %. A confianza común elegida en validación, la precisión micro pasó de 43,58 % a 51,20 % y la recuperación de 62,51 % a 53,61 %. Los tres videos procesados a 5 fps carecían de anotación exhaustiva para medir AP externo. Los desplazamientos respecto a ArUco se expresaron en imagen y normalizados por el tamaño aparente del marcador. Quedaron pendientes el origen, la calibración de cámara y la profundidad necesaria para errores XYZ en centímetros. Los conteos por fotograma y la duración de pistas son descriptivos.

**Piloto geométrico inicial.** Se hicieron seis cribados y 18 confirmaciones reales, con 125, 210 y 461 fotos agrupadas y cada tamaño con y sin aumentación clásica. Los 18 brazos sintéticos previstos quedaron bloqueados por tamaño o cantidad. El conjunto completo real obtuvo 18,50 % sin clásica y 18,47 % con clásica. Con 210 fotos, los valores fueron 17,24 % y 16,07 % y con 125, 14,09 % y 14,29 %. Los ajustes de cámara no cerraron la brecha de tamaños exigida por el protocolo original.

**Extensión exploratoria.** El cierre consolidó 24 cribados, 18 finalistas sintéticos, 18 controles reales y tres de repetición. La mezcla seleccionada por validación mejoró macro frente a real con clásica en las tres semillas. Frente a repetición real, los deltas fueron −0,36, −2,56 y +5,55 pp. Madura perdió 0,81 pp frente a real con clásica y 1,59 pp frente a repetición. El intervalo descriptivo por grupos de la diferencia macro fue de +1,29 a +3,42 pp frente a real con clásica y de −0,67 a +2,81 pp frente a repetición. No se aisló un beneficio consistente del contenido sintético frente a repetir fotos reales.

**Factorial de apariencia.** La calibración produjo dos galerías de 50 imágenes y cuatro comprobaciones de pose adicionales en la segunda ronda. El factorial quedó bloqueado por admisión física. En cinco intentos completos con diez árboles se registraron de 423 a 1.261 intersecciones y ninguna escena admitida. De los 26 cribados se completaron dos reales. De las 36 confirmaciones se completaron seis reales. El efecto de luz, textura e interacción quedó sin evaluar. Entre los controles, la clásica elevó el AP colapsado de 40,68 % a 41,85 % y, al umbral común de validación, el recall micro de 56,75 % a 60,35 %, con una reducción de precisión micro de 44,90 % a 41,73 %.

## Generación y calibración de apariencia

La corrección nodal permitió admitir **20 plantas**. Se cerraron 144 pares RGB, máscara y etiquetas completos en seis escenas y la captura posterior se pausó con 503 vistas frente a la meta de 1.000. El ensayo de optimización redujo el tiempo medio de tres capturas emparejadas de 110,3 a 58,2 s. Las máscaras coincidieron píxel a píxel y las diferencias RGB fueron de hasta un nivel de 255. La revisión de las primeras 500 vistas encontró 21 combinaciones de escena, 5.835 identidades visibles y 482.925 apariciones anotadas. Las primeras 100 vistas ya cubrían el 99,6 % de esas identidades. Los nuevos encuadres vuelven a observar los mismos órganos y el inventario no mide eficacia del entrenamiento. [Cierre de las plantas admitidas](plantas_admision_espacial_8h_2026-10-29.md) · [Auditoría de los pares de cultivo](dataset_cultivo_admitido_2026-10-29.md)

La auditoría de oscuridad tomó 363 Sobremaduras anotadas en entrenamiento y controles próximos de Pintona y Madura. En máscaras aproximadas, la mediana de superficie Sobremadura con L* <35 fue 5,1 % y con L* <45, 20,0 %. Con L* <35, los controles Pintona y Madura tuvieron medianas de 12,5 % y 5,3 %. La oscuridad fotográfica, el tejido seco y la pigmentación venosa se mantuvieron como atributos distintos. La muestra era dependiente de los grupos y los umbrales describían píxeles, sin calibración colorimétrica ni fisiológica.

Las revisiones de deterioro ensayaron pliegues y compresión en cálices aislados y desarrollaron texturas con pigmentación irregular que se extiende desde el cuello y las venas. Un control de iluminación sobre una carta gris redujo la relación azul/rojo de 3,43 a 1,15 tras ajustar la contribución ambiental. En el banco de noviembre se aplicaron cambios superficiales y de iluminación conservando la geometría admitida. Las 115 vistas nuevas usaron 69 cielos claros, 29 con bruma y 17 cubiertos. Estas observaciones corresponden a calibración visual e ingeniería, con independencia de los resultados del detector.

## Los dos pilotos de 115 imágenes

Cada piloto entrenó seis modelos, tres semillas por brazo, con 4.000 actualizaciones y 8.000 exposiciones de imagen por corrida. Se mantuvo la partición real, la resolución de 960 px, los pesos iniciales y la selección de checkpoints por validación. El brazo real empleó repeticiones emparejadas. Se evaluaron los pesos sellados sobre el mismo desarrollo histórico.

| Resultado | Real con clásica | Banco revisado, 31/10 | Banco con cielos y secado, 12/11 |
|---|---:|---:|---:|
| AP50–95 Pintona | 36,92 % | 40,12 % | 39,92 % |
| AP50–95 Madura | 7,70 % | 11,46 % | 9,86 % |
| AP50–95 Sobremadura | 11,87 % | 11,11 % | 9,32 % |
| AP50–95 colapsado | 38,65 % | 41,71 % | 41,00 % |
| Precisión micro fija | 34,67 % | 34,89 % | 38,65 % |
| Recall micro fijo | 62,34 % | 68,31 % | 63,70 % |

En el banco revisado, el delta macro fue positivo en las tres semillas y el AP de Sobremadura bajó en las tres. En el banco con cielos y secado, el delta macro fue positivo en dos de tres semillas y el descenso de Sobremadura volvió a observarse en las tres. Los intervalos de remuestreo por grupos del delta macro fueron de +0,40 a +5,03 pp y de −1,13 a +3,80 pp, respectivamente. Se condicionan a las semillas observadas y a la presencia de las tres clases.

La auditoría del piloto de octubre mostró que los checkpoints evaluados procedían de 1.500 a 2.500 actualizaciones. En esos prefijos, las exposiciones reales de Sobremadura bajaron de 10.232 a 6.956 y el 98,59 % de las apariciones de la clase en el brazo mixto fue sintético. En noviembre, Sobremadura representó el 3,93 % de las etiquetas del banco, pero el 90,23 % de las apariciones de esa clase durante las tres corridas mixtas completas fue sintético. El lado menor mediano a escala de 960 px después del filtro nativo fue 14 px en sintético frente a 100,51 px en real. La exposición y el tamaño visible son descriptores de los datos recibidos por el entrenador. No se midieron gradientes por dominio. En noviembre cambiaron conjuntamente textura, iluminación, cielos y asignaciones de clases, así que el contraste no identifica cuál causó el resultado.

## Diagnóstico y adjudicación pendiente

La galería de noviembre comparó cuatro familias y tres semillas a partir de 12 cachés de predicciones sobre las mismas 94 fotos. Incluía controles y tratamientos de campañas diferentes, con bancos y dosis distintos. Para la pareja de noviembre al umbral común, los verdaderos positivos de Sobremadura bajaron de 41 a 35 y los falsos positivos de 139 a 121 al sumar las mismas referencias sobre las tres semillas. El diagnóstico por objetivo atribuyó 38 Sobremaduras a Pintona en el control y 57 en la mezcla. Esos conteos no son objetos independientes y el diagnóstico por objetivo usa un emparejamiento distinto del conteo de verdaderos positivos por clase.

Se cribaron 144 regiones propuestas y se marcaron 17 candidatas para adjudicación humana, con seis anotadas Pintona, seis Madura y cinco sin caja cercana. La revisión no modificó las etiquetas ni estimó prevalencia de errores. Una comparación editorial debe distinguir sospechas visuales, anotaciones adjudicadas y predicciones. [Protocolo de auditoría ciega](../guides/auditoria_ciega_segmentacion.md)
