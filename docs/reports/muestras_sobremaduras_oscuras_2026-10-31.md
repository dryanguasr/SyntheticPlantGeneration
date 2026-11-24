# Muestras de sobremaduras: oscurecimiento y contracción visible

## Propósito y límites

Tanda pequeña solicitada por el usuario para decidir si autoriza extender el piloto. No amplía el banco de503 imágenes ni inicia entrenamiento. Conserva las20 plantas admitidas y todos los ejemplos históricos, incluyendo las sobremaduras pajizas.

La observación del usuario y el análisis exploratorio de train motivan manchas proximales, tonos marrones, coberturas oscuras extensas y formas secas/comprimidas. La oscuridad también aparece en Pintona y Madura. Las muestras enriquecen deliberadamente los extremos para revisión; sus frecuencias no son una distribución estimada del cultivo ni una calibración fisiológica. Los parámetros numéricos son `engineering_heuristic_for_visual_approval`.

Se separan dos verificaciones: superficies nuevas en copias de dos vistas de cultivo con geometría y anotaciones conservadas, y contracción sobre capachos huecos aislados. Estas últimas no certifican compatibilidad con un fruto interior ni admisión física de una planta contraída. La **reabsorción fisiológica no se establece ni se simula**; se representa una hipótesis visual de secado, reducción de tamaño y compresión.

## Contrato reproducible

`calyx_darkening_review.py` define un plan puro con cobertura proximal, intensidad, marrón y contracción independientes. `blender_calyx_darkening_review.py` interpreta la superficie sin cambiar geometría. El intérprete de las muestras aisladas utiliza la deformación pura preexistente, preservando el polo de unión al pedicelo. La extensión proximal es una coordenada de material, no un porcentaje de superficie lesionada.

Semilla20261031. Los scripts `prepare_calyx_approval_samples.py`, `render_calyx_approval_samples.py` y `report_calyx_approval_samples.py` separan entradas congeladas, render y revisión. Las imágenes quedan exclusivamente en `outputs/calyx_approval_samples_20261031`, con planes, hashes y trazabilidad hacia las vistas originales. Los recortes comparativos contienen píxeles reales del render, sin retoque.

La lámina compara Madura con una pequeña marca basal, Sobremadura actual, deterioro leve/intermedio/extenso/casi total y una variante seca/decolorada. Todas las columnas mantienen escala de cámara común para observar la reducción. Los cambios de textura, color y forma son propuestas para aprobación, no nuevas etiquetas de madurez interna.

## Comprobaciones

Tres pruebas puras verifican reproducibilidad, extensión de manchas y presencia opcional de manchas en las otras clases. Se verifica geometría completa antes/después de las vistas de cultivo, cámara original, máscara exacta, instancias y YOLO. Los capachos aislados comprueban malla cerrada y unión proximal fija. La fracción RGB L*<35/45 de ejemplos visibles se registra como oscuridad bajo esa iluminación, nunca como necrosis, pigmentación intrínseca o reabsorción.

Se conservan los locks históricos de136 fuentes de generación y1999 archivos de entrenamiento, presupuesto, pausa,20 árboles y sus auditorías. La revisión de Codex y la autorización humana son estados distintos; la extensión y el entrenamiento permanecen pendientes de decisión del usuario.

## Resultado de la ejecución y revisión de Codex

Se produjeron cuatro RGB nuevos: dos vistas de cultivo de `scene_027` y dos láminas con siete capachos cada una, procedentes de dos morfologías. Las dos vistas conservan exactamente las máscaras PNG, instancias y YOLO originales y la geometría completa. Las14 mallas aisladas tienen cero aristas no manifold; el error máximo del polo proximal es1,27e-7cm por redondeo. Pasaron siete pruebas puras entre el modelo de contracción y el nuevo plan de manchas. Se verificaron de nuevo las fuentes protegidas,20 árboles/admisiones, presupuesto y pausa. No se añadió ninguna imagen al banco ni se entrenó.

Inspección visual: la compresión y la reducción de tamaño se perciben con la cámara común; se distinguen estados claros, marrones y muy oscuros, junto a una variante decolorada. En varios grados intermedios el borde de la mancha todavía parece una banda demasiado uniforme; los estados muy negros pierden contraste de venas bajo sombra. Es una propuesta para revisión del usuario, no una declaración de realismo o eficacia. Las proporciones de L* de los recortes ilustran además por qué oscuridad RGB y área de una mancha no son intercambiables.

Se preservó un lanzamiento sin artefactos y un intento detenido por la guardia de reconstrucción de cámara antes de renderizar. La continuación utiliza directamente la matriz y el punto de mira registrados en la vista fuente, sin volver a sortear la cámara, y pasa la comparación exacta de máscaras. Los intentos, logs y fuente anterior permanecen archivados. El grafo conserva los mismos10 errores históricos de localizadores, sin nuevos.

La galería `review.html`, los resultados `context_result.json`/`organs_result.json`, los recortes y `review.json` quedan en la raíz de esta tanda. Estado: `awaiting_user_visual_review`. Sólo una nueva decisión del usuario puede autorizar extensión del piloto.

## Revisión solicitada: manchas irregulares y tejido visible

El usuario pidió eliminar la banda, conservar los grados de secado/compresión y evitar ejemplares totalmente opacos salvo evidencia en el dataset. Se revisaron otra vez los ejemplos reales `row_0297_box_000`, `row_0358_box_000`, `row_0096_box_001` y los candidatos oscuros de `review_page_4.png`. Conservan patrones de venación y zonas claras; el oscurecimiento casi global se confunde con sombra. Las fotografías no permiten certificar opacidad óptica intrínseca. No se usa ese extremo como licencia para generar un capacho negro uniforme.

La revisión `irregular_mottling_03`, material `irregular-calyx-mottling/2`, sustituye la frontera en Z por parches tridimensionales anisótropos que se solapan, con deformación de coordenadas y variación a dos escalas. La preferencia proximal procede de la posición de los parches; no hay un plano horizontal que corte la mancha. Para una misma semilla crecen los mismos parches entre grados. El sustrato original se multiplica y mezcla para conservar su venación, con ventanas más claras; la variante avanzada es moteada, sin reemplazo negro completo. Los coeficientes son heurísticos de revisión, no frecuencias o propiedades ópticas medidas en campo.

Se añade una pequeña contribución difusa transmitida para el aspecto papiráceo a contraluz. El alpha permanece en1 y no se crean huecos transparentes ni se retiran órganos o etiquetas. Esta aproximación visual no mide ni certifica la transmitancia real del tejido. Los parámetros de contracción, semilla geométrica y unión proximal se conservan respecto a la tanda anterior.

Las fuentes y dos imágenes de la primera prueba suave (`irregular_mottling_02`) se preservan, incluidas las fuentes sustituidas y un lock resuelto hacia sus snapshots. No se sobrescriben las muestras con bandas ni las imágenes del banco. El modelo puro y su intérprete Blender permanecen separados en `calyx_mottling.py` y `blender_calyx_mottling.py`. Cuatro pruebas nuevas comprueban variación alrededor de una misma altura, crecimiento continuo con semilla fija, conservación de los grados geométricos y ausencia de reemplazo total del sustrato.

Resultado revisado por Codex: cuatro RGB finales en `irregular_mottling_03` (dos láminas y dos vistas de cultivo), además de las dos pruebas suaves preservadas. Las14 muestras aisladas conservan exactamente los estados geométricos, dimensiones y volúmenes registrados en la tanda inicial; todas siguen cerradas y unidas al pedicelo. Las dos vistas de cultivo pasan las guardias de cámara/geometría y conservan máscara PNG, instancias y YOLO idénticos a sus originales. Se ven manchas difusas de expansión irregular, con venas y zonas claras en los casos avanzados; ninguna variante nueva usa el anterior reemplazo casi negro completo. La apariencia papirácea y las proporciones de pigmentación aún requieren aprobación visual, sin atribuir madurez interna o eficacia del detector.

Pasaron ocho pruebas puras en total (cuatro de moteado y cuatro de contracción). Se verificaron las fuentes actuales, los locks históricos136/1999,20 árboles/admisiones, presupuesto y pausa; no hay renders activos al entregar. El grafo conserva los mismos10 errores anteriores y cero regresiones. `latest_review.json` apunta a la revisión nueva, `review.html` muestra las escenas completas y `mottling_review.json` separa revisión de Codex de autorización humana. Las503 imágenes anteriores siguen preservadas; no se amplió el piloto ni se entrenó.
