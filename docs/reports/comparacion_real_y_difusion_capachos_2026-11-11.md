# Comparación real/sintética y revisión de las texturas por difusión

## Juicio sobre la tanda anterior

La consistencia era **parcial, insuficiente para dar por resuelta la brecha**. La revisión de Codex comparó ocho recortes etiquetados Madura y ocho Sobremadura de train con las láminas y recortes sintéticos de `calyx_vein_spread_review_20261111`. Las fotos son compatibles con la observación del usuario: venas oscuras y pigmentación proximal, con extensión desigual hacia el tejido vecino y hacia la punta. Las imágenes no constituyen una secuencia temporal de los mismos órganos ni permiten estimar velocidades de deterioro.

La selección fue intencional para inspección, con resolución y visibilidad diversas; no es una muestra de prevalencia ni16 plantas independientes. IDs, clases originales, cajas, rutas y hashes están en `outputs/calyx_diffusion_review_20261111/real_comparison.json`. No se leyeron val/test, se cambiaron etiquetas ni se consideró validado el mecanismo fisiológico.

| Aspecto | Referencias reales inspeccionadas | Tanda sintética anterior |
|---|---|---|
| Madura y fase inicial | En `row_0004_box_001`, `row_0256_box_001`, `row_0433_box_000`, venas primarias violáceas/café y cuello pigmentado sobre tejido verde/amarillo | Venas demasiado tenues/ocres y predominio de pajizo; contraste y color insuficientes |
| Sobremadura intermedia | `row_0297_box_000`, `row_0358_box_000`: halos que se ensanchan alrededor de venas y región proximal, con tejido claro intermedio | La dirección era compatible, pero los umbrales producían contornos y celdas claras demasiado recortados |
| Deterioro avanzado | `row_0096_box_001`, `row_0658_box_002`: pigmentación amplia, gris/café/violeta, superficie arrugada y pubescencia visible | Capa ocre relativamente uniforme o retícula muy regular; relieve y color no correspondían suficientemente |
| Casos ambiguos | `row_0438_box_000` tiene sombra global; `row_0616_box_001` está parcialmente ocluido; `row_0003_box_000` es lateral y desenfocado | Un área fotográficamente oscura no puede convertirse en una regla de negro uniforme u opacidad intrínseca |

Las otras Madura inspeccionadas son `row_0668_box_003`, `row_0289_box_001`, `row_0521_box_001`, `row_0285_box_004`; las otras Sobre, `row_0626_box_002`, `row_0313_box_037`. El oscurecimiento no es exclusivo de la etiqueta Sobremadura. No se supone que la parte superior de cualquier recorte sea proximal si no se ve la unión.

## Causa en la generación de texturas

El modelo anterior asignaba tiempos de llegada a todas las venas y aplicaba umbrales de shader. Eso reprodujo parte de la orientación, pero no una acumulación gradual del pigmento desde el cuello. Además, `_calyx_vein_fields` de la fuente histórica construye22 filas con `y=.09+fila*.074` y recorta sus nodos a `.94`: las10 últimas filas terminan acumuladas en esa coordenada. Es un defecto del entramado generativo que puede producir un trazo denso artificial. La fuente histórica congelada se conserva; la corrección es opt-in y se genera en otro directorio.

La revisión nueva construye las filas dentro del dominio desde el inicio, conserva cinco nervaduras principales alineadas con los lóbulos y usa una reticulación secundaria irregular, con conexiones variables. Los mapas de venas, color y normales proceden de ese mismo campo. Se sustituye el albedo y el normal correspondiente del material copiado, evitando superponer un patrón pigmentado a una red normal diferente. El color incorpora tonos violáceos/café y una base menos saturada, escogidos como hipótesis visual tras la comparación, sin medir albedo físico a partir de las fotos.

## Reglas de reacción y difusión

`calyx_diffusion_texture.py` implementa una activación A y pigmento acumulado P. Sólo el cuello proximal inyecta activación; su transporte es más rápido en la red venosa. El flujo espacial se calcula entre celdas vecinas, con U periódica y V sin flujo en sus extremos. La reacción local amplifica activación conectada a esa fuente, y el pigmento se acumula irreversiblemente donde llega. El tejido entre venas tiene una tasa más lenta; por tanto el patrón emerge desde la red y se ensancha sin generar manchas remotas como fuentes independientes.

La actualización numérica usa flujo conservativo por aristas, paso explícito con guardia de estabilidad, activación logística y acumulación proporcional a A·(1−P). Las constantes, paleta y pasos600/1400/2600/4200 son `engineering_heuristic`, sin unidades fisiológicas ni equivalencia con días de maduración. La idea se sitúa en el contexto de los modelos espaciales de reacción–difusión de [Turing,1952](https://doi.org/10.1098/rstb.1952.0012); el modelo concreto empleado aquí es una herramienta visual propia, no una reproducción del modelo de Turing ni una validación del proceso en uchuva.

La primera prueba dejó el pigmento demasiado confinado a las venas. Se preservan sus mapas, imágenes y fuentes. La revisión `revisions/tissue_leak_02` aumenta la acumulación lenta en tejido contiguo y usa un inicio proximal también en Madura. Se mantiene la textura papirácea, alpha1 y una pequeña contribución difusa transmitida, con zonas claras y detalle en lugar de un negro uniforme.

La comprobación posterior en la escena completa detectó otra desviación: el albedo horneado se conectaba directamente al BSDF y omitía las ganancias lineales por clase del perfil histórico. Bajo aquella iluminación el resultado quedaba demasiado pálido y violáceo. La revisión `revisions/profile_interpretation_03` conserva los mismos campos de difusión y restaura esas ganancias, tanto en la componente reflejada como en la difusa transmitida, sin modificar el perfil original. Las imágenes de la prueba anterior se preservan; no se toma su diferencia cromática como efecto exclusivo del nuevo patrón de pigmentación.

## Alcance y verificación

La raíz es `outputs/calyx_diffusion_review_20261111`. El modelo y la generación offline de mapas no requieren Blender; la preparación usa NumPy y Pillow ya existentes, sin instalaciones. El intérprete Blender está separado en `blender_calyx_diffusion_texture.py`. Las fuentes y mapas se congelan antes de renderizar; los assets originales y los informes anteriores se preservan.

Cuatro pruebas verifican ausencia de pigmentación espontánea sin fuente, prioridad proximal/venosa y acumulación irreversible, reproducibilidad del grafo y conservación de los grados geométricos, y rechazo de pasos inestables. La geometría de secado, compresión y unión usa los estados originales. Los controles físicos de las vistas de cultivo se conservan por geometría idéntica y se comprueban cámaras, máscaras, instancias y YOLO. La contracción sigue limitada a capachos huecos aislados, con compatibilidad del fruto interior pendiente. El banco de503 imágenes y20 plantas permanece pausado y no se inicia otro piloto.

## Resultado y juicio final de esta revisión

Se preservan seis RGB de pruebas intermedias y cuatro RGB finales en `revisions/profile_interpretation_03`: dos láminas y dos vistas de cultivo. La lámina `real_old_new.png` compara cuatro referencias de train con la propuesta anterior y la nueva; no son órganos emparejados ni una secuencia temporal. `real_review_sheet.png` conserva los16 recortes inspeccionados. Se verificaron los hashes de sus imágenes y labels originales y las clases de las cajas seleccionadas.

**Juicio de Codex: mayor coherencia espacial, pero consistencia visual todavía parcial.** La nueva evolución parte del cuello, resalta la red vascular y ensancha halos de forma más suave. Desaparecen las islas duras de la versión anterior y se corrige la acumulación artificial de filas. Aun así, el control Madura conserva venas primarias más tenues que varias referencias reales; algunos grados avanzados siguen leyendo como retícula marcada sobre un fondo relativamente claro. Persisten diferencias de pubescencia, tejido arrugado fino y variabilidad cromática. No se considera resuelta la brecha ni se recomienda interpretar estas imágenes como equivalentes a las reales. La aparición espacial es compatible con la descripción del usuario, mientras que el orden temporal sigue siendo una hipótesis aportada por su observación y no una medición longitudinal del dataset.

Pasaron las cuatro pruebas nuevas y las cuatro preexistentes de contracción. Los14 estados geométricos, dimensiones y volúmenes coinciden con los originales. Las dos vistas conservan cámaras, geometría, máscaras PNG, instancias y YOLO, y se verificó que el intérprete aplica las ganancias del perfil congelado. Se verificaron300 archivos de la revisión final, las fuentes históricas136/1999,20 árboles/admisiones y la pausa/presupuesto originales. El grafo conserva exactamente los mismos10 errores previos y cero regresiones. No queda ningún Blender activo al cierre.

La concentración simulada P y los pasos numéricos no son porcentajes de área pigmentada, valores L* de fotos ni edades de maduración. No se ajustó ni evaluó un detector. `comparison_review.json` registra la valoración, `review.html` contiene todas las muestras finales y el puntero `latest_review.json` conserva el acceso a la revisión vigente. Se mantiene el piloto pausado y no se amplía el banco.
