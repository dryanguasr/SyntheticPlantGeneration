# Cuantificación exploratoria de regiones oscuras en capachos de train

**Se midió oscuridad fotografiada, no pigmentación intrínseca ni necrosis.** Se usaron exclusivamente las363 anotaciones Sobremadura en170 imágenes de train, de siete grupos. No se leyeron píxeles ni labels de val/test. Hay116 controles Pintona y81 Madura escogidos en las mismas fotos, por proximidad/tamaño a un objetivo Sobremadura de referencia. No representan todos los ejemplares de esas clases ni son objetos biológicamente independientes.

## Qué se midió

Se convierte RGB de los JPEG a L* nominal0–100 asumiendo sRGB, sin calibración de cámara ni comprobación colorimétrica de los perfiles originales. Tres límites compartidos,25/35/45, describen oscuridad estricta a más amplia; no son umbrales botánicos ni fueron optimizados para clasificar. La fracción es número de píxeles bajo el límite dividido por el área analizada. Se calculan dos denominadores: elipse central geométrica de60% del ancho/70% del alto de la caja, y máscara automática aproximada de superficie visible.

La máscara usa GrabCut con fondo fuera de caja y una pequeña semilla central, a resolución máxima224px. Puede perder tejido oscuro o incluir hojas/vecinos. [La documentación de OpenCV](https://docs.opencv.org/4.x/d8/d83/tutorial_py_grabcut.html) advierte que se necesitan correcciones cuando la separación falla. No se presenta ninguna de estas máscaras como ground truth. Los porcentajes se conservan separados de las etiquetas.

## Resultados de Sobremadura

| Criterio L* | Mediana del área en máscara aproximada | Q25–Q75 | Mediana en región central |
|---|---:|---:|---:|
| <25 | 0.7% | 0.0–5.2% | 0.1% |
| <35 | 5.1% | 0.8–17.1% | 2.9% |
| <45 | 20.0% | 5.8–44.7% | 14.4% |

Con L*<35, el90% de cajas queda por debajo de35,8% de área oscura estimada. Con L*<45 ese percentil sube a70,1%. Hay180 casos en0–5%,101 en5–20%,67 en20–50%, 11 en50–80% y4 candidatos en≥80% usando las máscaras crudas a L*<35. A L*<45 aparecen 20 candidatos≥80%. La dependencia del umbral y de la máscara impide llamar a esos conteos prevalencia de manchas o deterioro.

Se inspeccionaron30 casos estratificados por oscuridad. Dos de los cuatro candidatos ≥80% a L*<35 son claramente problemáticos: una máscara minúscula de161px (`row_0358_box_001`) y una hoja oclusora incluida (`row_0577_box_006`). Los otros candidatos tampoco prueban pigmentación: la sombra puede oscurecer casi todo el órgano. Los fallos observados se conservan, no se corrigen modificando labels.

Como sensibilidad conservadora se excluyeron12 máscaras con alertas automáticas o problemas visuales, quedando351 provisionales; su mediana a L*<35 es4.7% y a L*<45,18.6%. No equivale a validar humanamente todas las restantes.

## Comparación con clases próximas

| Clase/subconjunto | Cajas | Mediana L*<35 en máscara aproximada | Mediana L*<45 |
|---|---:|---:|---:|
| Pintona | 116 | 12.5% | 32.9% |
| Madura | 81 | 5.3% | 16.8% |
| Sobremadura | 363 | 5.1% | 20.0% |

Las regiones oscuras no son exclusivas de Sobremadura y esta medida no aumenta monótonamente con la clase. Los capachos verdes pueden ser más oscuros de base; hay sombras, venas y oclusiones en todas las clases. En la comparación emparejada de regiones centrales de la misma foto, la mediana Sobre−Pintona es−6,0pp (116pares) y Sobre−Madura−1,4pp (81pares). No se interpreta como menos deterioro fisiológico.

El grupo `component_35` aporta266 de363 cajas Sobremadura (73,3%), y `component_2` otras69. Las observaciones pueden repetir plantas/órganos en fotogramas: son descriptores del train actual, no una estimación de frecuencia en cultivo.

![Distribuciones y sensibilidad](../../outputs/calyx_dark_regions_train_20261031/coverage_summary.png)

## Ejemplos con porcentajes

Se muestran seis Sobremaduras de train, seleccionadas para ilustrar desde poca oscuridad hasta casos extensos, no al azar. La última es un contraejemplo de oscuridad global: no se certifica como mancha. Verde: contorno estimado; magenta: píxeles L*<35.

![Ejemplos medidos](../../outputs/calyx_dark_regions_train_20261031/examples_quantified.png)

## Localización próxima al pedicelo

Las cajas originales no contienen orientación anatómica ni punto de unión. No se supone que arriba en la foto sea proximal para las363 cajas. En un ejemplo con pedicelo visible (`row_0297_box_000`) se estimó visualmente su dirección; no es una anotación humana validada ni un resultado poblacional.

En ese caso, la zona proximal definida como30% del recorrido proyectado de la máscara tiene77% de píxeles L*<35, frente a 32% en el resto. Al rotar la dirección estimada±15°, el valor proximal varía entre70 y80%. Sirve como ilustración de distribución espacial, no para calibrar una regla universal.

![Zona proximal ilustrativa](../../outputs/calyx_dark_regions_train_20261031/proximal_example.png)

## Consecuencia para el generador

Conviene variar de forma independiente la cobertura, la intensidad y la posición del oscurecimiento: mantener ejemplos claros y generar también manchas localizadas y coberturas extensas. Pintona y Madura pueden tener oscurecimiento proximal; no debe ser un marcador exclusivo de Sobremadura. El porcentaje de píxeles oscuros no se convierte directamente en severidad del modelo, tamaño, edad o reabsorción.

Antes de fijar distribuciones de pigmentación hacen falta máscaras visibles revisadas y atributos separados de sombra, manchas/venación, cobertura por hojas y punto proximal. Este análisis no modifica categorías, entrenamiento, plantas o imágenes; tampoco reanuda generación. Las503 imágenes/20plantas siguen preservadas y la campaña pausada.

Artefactos: `input_lock.json`, `measurements.json`, `summary.json`, `reviewed_summary.json`, máscaras/crops por objeto e `index.html`. Semilla20261031, scripts/versiones y hashes registrados; tres pruebas de fracción, umbral relativo y máscara geométrica pasaron.
