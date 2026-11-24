# Diagnóstico de omisiones y siguiente experimento de detección

La maleza confirmada por el usuario agrava la oclusión y la confusión con hojas, tallos y flores, pero no explica por sí sola el resultado. La evidencia apunta a cuatro problemas: fuerte dependencia del tamaño del capacho, desajuste entre entrenamiento y video, clasificación de apariencia débil y una mezcla sintética desequilibrada por tamaño y número de instancias. ArUco falla en una ruta independiente de YOLO, principalmente antes del filtrado geométrico; hay ejemplos de oclusión, recorte y deformación del papel, además de una limitación corregible de umbralización.

Este diagnóstico conserva el piloto congelado. Las nuevas pruebas son posteriores a la evaluación y no convierten los videos en un holdout externo intacto. No hubo entrenamiento nuevo ni cambios en los originales.

## Qué se midió

Se reutilizaron las predicciones guardadas de 94 imágenes test, las curvas de las 20 épocas y las etiquetas de ambos conjuntos de entrenamiento. Se ejecutó además una prueba CPU de ArUco sobre 132 fotogramas elegidos cada tres segundos de los tres videos. Las salidas están en `outputs/union_real_pilot_20261022/diagnosis_v1/`; el procedimiento está en `scripts/diagnose_union_pilot.py`.

El diagnóstico de tamaño usa el lado menor de la caja después de escalar el lado mayor de la imagen a 960. Las correspondencias son uno a uno, ordenadas por confianza, IoU ≥0,5 y sin exigir coincidencia de clase, con la confianza congelada 0,248248. Son medidas sobre el test anotado, no recall de los videos.

| Tamaño de la caja | Objetos test | Localizados real | Localizados mixto |
|---|---:|---:|---:|
| 16–32 px | 46 | 8; 17,4 % | 10; 21,7 % |
| 32–64 px | 410 | 228; 55,6 % | 186; 45,4 % |
| ≥64 px | 499 | 435; 87,2 % | 390; 78,2 % |

El test no contiene objetos menores de 16 px bajo esta definición. Por tanto, la evaluación agrupada apenas representa ese extremo difícil. Las vistas amplias del video muestran capachos pequeños sin caja, pero sus tamaños y recall necesitan anotación exhaustiva para cuantificarse. Los dos aciertos adicionales de la mezcla en el grupo pequeño no compensan su pérdida en los demás grupos; solo hay 46 objetos en ese estrato.

## Principales causas de las omisiones

**Escala y dominio de captura.** En el entrenamiento real, la mediana del lado menor es 56 px. Hay fotografías cercanas con capachos grandes y detalle de nervaduras; los videos presentan vistas amplias de 1280×720, maleza, hojas secas, iluminación variable y movimiento. La inferencia completa a 960 reduce esos videos a una escala de 0,75 antes del padding. La relación entre tamaño y omisión está medida; atribuir una fracción exacta de las omisiones del video a escala, desenfoque u oclusión todavía requeriría etiquetar esos factores.

**Fondo difícil y oclusión.** En las vistas inspeccionadas aparecen cajas sobre zonas foliares y capachos visibles omitidos. La maleza aporta distractores y puede ocultar contorno y textura. No hay imágenes completamente negativas en el entrenamiento utilizado; sí hay píxeles de fondo dentro de las imágenes positivas. Falta una colección explícita de negativos difíciles, revisados para asegurar que no contienen capachos sin anotar. Tampoco se midió qué proporción del entrenamiento reproduce la maleza observada, por lo que no se le asigna un porcentaje causal.

**Clasificación de apariencia.** El AP50–95 colapsado del real es 42,99 %, frente a 18,65 % macro de tres clases. Pintona alcanza 40,33 %, Madura 7,43 % y Sobremadura 8,20 %. El 76,2 % de las instancias de entrenamiento es Pintona. Hay un problema de localización y otro de clasificación; localizar una caja no garantiza distinguir apariencia, especialmente cuando el capacho ocupa pocos píxeles. Las etiquetas describen el capacho, no madurez interna validada.

**Sobreajuste compatible con las curvas.** El mejor AP50–95 de validación real fue 0,23102 en la época 6, frente a 0,19619 en la 20. Entre esas épocas, la pérdida de clasificación train bajó de 1,477 a 0,440 y la de validación subió de 1,687 a 2,185. El mixto también retrocedió desde su mejor época 14. El entrenamiento sí actualizó parámetros y completó 4.615 pasos por brazo; la evidencia no apunta a un entrenamiento inactivo. Añadir épocas sin cambiar los datos no es la intervención prioritaria.

**Seguimiento frágil.** La mediana fue una observación por track en los seis casos modelo/video. La asociación IoU a 5 fps es vulnerable al movimiento entre fotogramas y a las omisiones del detector. Esto explica parte de la discontinuidad temporal, pero el tracker no causa las omisiones originales de YOLO porque se ejecuta después de la detección.

## Por qué la mezcla no produjo una mejora global

| Propiedad de entrenamiento | Real del brazo mixto | Sintético del brazo mixto |
|---|---:|---:|
| Imágenes | 384 | 96 |
| Instancias | 3.828 | 14.003 |
| Instancias por imagen | 10,0 | 145,9 |
| Mediana del lado menor a 960 | 57,9 px | 7,5 px |
| Cajas con lado menor <16 px | 2,46 % | 83,45 % |

La mezcla era 80/20 por imágenes, pero 21,5/78,5 por instancias. Esto no equivale automáticamente a esos porcentajes de gradiente, porque la función de pérdida también normaliza y asigna objetivos. Sí demuestra que el experimento añadió una población muy densa de objetivos diminutos y redujo las imágenes reales distintas de 461 a 384. El presupuesto de actualizaciones fue igual, pero la exposición real no lo fue.

La muestra sintética inspeccionada presenta suelo relativamente despejado y vegetación de apariencia simplificada, frente al fondo de maleza y hojas secas del cultivo real. Es evidencia cualitativa de diferencia de dominio, no una auditoría visual exhaustiva de los 96 renders. La validez raster y botánica no implica semejanza estadística con las capturas reales.

El descenso macro de 0,59 puntos no demuestra que todos los sintéticos perjudiquen: solo se ejecutó una semilla. Madura y Sobremadura mejoraron ligeramente su AP, mientras Pintona empeoró. Para aislar el aporte sintético hace falta controlar escala, densidad, exposición real y presupuesto; este ensayo mezcló esos efectos. Ese desajuste debió comprobarse antes de entrenar y debe convertirse en un control de admisión del próximo brazo sintético.

No se deben borrar etiquetas pequeñas dejando sus capachos visibles como fondo. Se pueden seleccionar vistas o recortes que aumenten su escala y conservar todas las anotaciones válidas; los casos ambiguos requieren adjudicación o un mecanismo explícito de regiones ignoradas.

## Por qué casi no aparecen ArUco

YOLO reconoce las tres clases de capacho; los ArUco se decodifican con OpenCV. Mejorar YOLO o aumentar sus datos no arregla automáticamente esta segunda ruta. El tamaño físico y la calibración se necesitan para pose métrica, **no para leer un ID en la imagen**. Su ausencia no justifica las escasas detecciones de marcadores.

| Video | Frames examinados a 5 fps | Con candidato bruto | Con marcador tras filtros |
|---|---:|---:|---:|
| 125180 | 929 | 61 | 56; 6,0 % |
| 125181 | 502 | 30 | 26; 5,2 % |
| 125182 | 536 | 4 | 2; 0,37 % |

Los filtros reducen 95 a 84 fotogramas con marcador. La mayor pérdida ocurre antes de esos filtros, no por exigir un lado mínimo de 20 px. Son porcentajes de cobertura sobre todo el video, **no recall sobre marcadores visibles y legibles**: incluyen frames sin marcador, con recortes y con oclusión. No se ha anotado el denominador correcto para medir ese recall.

Las imágenes muestran hierbas cruzando el código y el borde negro, hojas parcialmente fuera de campo y papel curvado. Esos daños dificultan extraer el cuadrilátero y decodificar sus celdas. OpenCV separa esas etapas de la estimación de pose y permite configurar las ventanas de umbralización. [Documentación de OpenCV](https://docs.opencv.org/5.0/tutorials/objdetect/aruco_detection/aruco_detection.html).

La prueba controlada mantuvo los filtros geométricos y examinó los mismos 132 frames:

| Variante | Frames con marcador utilizable |
|---|---:|
| DICT_4X4_50, ventana máxima 23, resolución original | 7/132 |
| Mismo diccionario, ventana máxima 153 | 9/132 |
| Mismo diccionario y ventana 23, imagen a mitad de tamaño | 9/132 |
| DICT_5X5_1000, configuración original | 0/132 |
| DICT_6X6_1000, configuración original | 0/132 |

Las dos recuperaciones corresponden al ID 3 en 125180, aproximadamente a 12 s, y al ID 8 en 125182, aproximadamente a 33 s; se inspeccionaron sus imágenes. Las ventanas grandes y la reducción de escala recuperan los mismos frames. Esto confirma una limitación de parametrización en algunos casos, pero la ganancia es pequeña. No hay evidencia de que cambiar a 5×5 o 6×6 sea la solución. Los IDs recuperados son compatibles con 4×4; todavía conviene contrastar el diccionario y los bordes con el archivo original de impresión.

Procesar solo a 5 fps también limita la adquisición y el flujo óptico ante movimientos rápidos. Es una hipótesis razonable para discontinuidad, no una magnitud medida en esta prueba. El seguimiento propagado debe seguir separado de una decodificación nueva.

## Siguiente experimento propuesto

**Primera pregunta: cuánto recall se recupera aumentando la escala efectiva sin volver a entrenar.** Comparar el peso real congelado con dos modos: imagen completa a 960 y la misma imagen completa más recortes sistemáticos de 640×640, stride 448, cada uno a 960, con fusión global de duplicados. En un video de 1280×720, los recortes duplican la escala efectiva del objeto frente a la imagen completa. La geometría de recortes debe cubrir también los bordes; no se eligen regiones mirando la anotación. El método de inferencia por recortes está documentado por [Ultralytics](https://docs.ultralytics.com/guides/sahi-tiled-inference); se puede utilizar la infraestructura existente del repositorio sin instalar dependencias.

1. Preparar un banco de 120 frames, 40 por video, seleccionados uniformemente en el tiempo antes de mirar predicciones. Anotar todos los capachos visibles, clases dudosas explícitas, cajas, oclusión y distractores. Revisar por Karen y Caroline. No introducir esos frames en entrenamiento.
2. Fijar recortes, fusión y confianza con validación real agrupada. Evaluar una sola vez los dos modos en el banco anotado. Medir recall espacial por tamaño, AP colapsado y por clase, falsos positivos por frame, duplicados y latencia. Comparar recall a igual presupuesto de falsos positivos, no simplemente bajar el umbral y contar más cajas.
3. Criterio inicial de ingeniería: buscar al menos +10 puntos de recall para objetos menores de 32 px sin aumentar los falsos positivos por frame respecto al control, y publicar el coste de latencia. Si la mejora no aparece, priorizar cambio de datos sobre ampliar el número de recortes.

Los tres videos actuales son evidencia diagnóstica ya inspeccionada. Para afirmar generalización se necesita otra captura/sesión reservada; separar frames vecinos de estos mismos clips no crea independencia.

**ArUco se ensaya en paralelo lógico como problema independiente.** En los mismos frames, anotar presencia, ID cuando legible, cuatro esquinas y estado: completo, ocluido, truncado o ausente. Comparar configuración original con una variante congelada multiescala/ventana amplia, sin cambiar de diccionario a ciegas. Añadir segmentos contiguos a los 29,97 fps originales para medir adquisición, gaps y estabilidad de esquinas. Reportar recall condicionado a visibilidad, IDs falsos, tiempo hasta adquisición y disponibilidad observada frente a propagada. No contar una propagación como detección nueva.

En la siguiente captura, montar los marcadores planos sobre soporte rígido, con margen blanco y sin hierbas delante del borde/código; mantener el cuadrado entero en campo y registrar el archivo de impresión. Medir el lado negro y calibrar cámara para la fase métrica posterior. Esta intervención despeja la referencia, sin eliminar artificialmente toda la maleza del escenario que debe afrontar el detector de capachos.

**Después del ensayo de escala**, preparar un entrenamiento real con recortes alineados con la inferencia y negativos difíciles de maleza, hojas y flores de capturas de entrenamiento distintas de los videos evaluados. Mantener vistas completas para contexto y todas las etiquetas válidas. Solo entonces repetir el brazo sintético, igualando distribuciones de tamaño/densidad y documentando exposición real. Un control con repetición de datos reales debe acompañar las actualizaciones adicionales del brazo sintético; así se puede distinguir el efecto de más cómputo del aporte de imágenes nuevas. La comparación confirmatoria necesita varias semillas y una sesión externa.

## Evidencia conservada

- `diagnosis_v1/detector_diagnosis.json`: tamaños, correspondencias por estrato y curvas de entrenamiento.
- `diagnosis_v1/marker_probes.json`: cada frame y resultado de las cinco variantes, incluidos candidatos rechazados.
- `diagnosis_v1/marker_probe_summary.json`: conteos de adquisición e IDs.
- `diagnosis_v1/125180_360_wide_recovered.jpg` y `125182_989_wide_recovered.jpg`: recuperaciones inspeccionadas.
- El informe y los pesos del piloto original permanecen sin cambios.
