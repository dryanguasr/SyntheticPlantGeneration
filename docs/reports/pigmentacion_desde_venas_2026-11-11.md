# Revisión de pigmentación originada en las venas del capacho

## Observación del usuario y alcance

El usuario corrigió la hipótesis visual: el oscurecimiento aparece primero en las venas y cerca del pedúnculo; se ensancha desde ellas hacia el tejido contiguo y progresa hacia las zonas distales. Se implementa esa observación como propuesta para revisión, conservando los grados de secado y compresión. No se afirma un mecanismo de quemadura, reabsorción fisiológica ni madurez interna del fruto.

El cambio sustituye el origen de las manchas. La red de venas procede de las máscaras UV existentes del mismo material; no se dibuja una red aleatoria superpuesta a las venas visibles. Las tasas, distancias y mezclas de color son `engineering_heuristic`, no tiempos o parámetros botánicos medidos. Se mantiene la restricción de evitar el reemplazo negro uniforme: el sustrato conserva textura, zonas claras y una respuesta papirácea difusa transmitida, sin huecos alpha.

## Modelo y registro de coordenadas

`calyx_vein_spread.py` contiene el plan puro y la propagación multiorigen. Cada píxel de vena recibe un tiempo inicial dependiente de su distancia proximal y de la señal de la máscara. Una búsqueda de llegada mínima se extiende al tejido vecino con costes positivos, favoreciendo el avance distal respecto al proximal. La red vascular se oscurece antes que el halo de tejido adyacente; ninguna isla de ruido inicia pigmentación por sí sola. La modulación cambia velocidades e intensidad, conservando el origen venoso.

La convención está comprobada en `blender_geometry.py`: el anillo0 está en el polo proximal y tiene UV v=0; v=1 apunta a la punta distal. PNG usa el orden vertical inverso. El campo envuelve U para atravesar la costura, sin envolver V entre pedicelo y punta. El intérprete mantiene V dentro del último medio texel para que una textura periódica no convierta accidentalmente la punta distal en región proximal.

`blender_calyx_vein_spread.py` lee el campo con el mismo vector UV del albedo original. Los canales del mapa derivado contienen llegada, máscara original de venas y modulación de intensidad. Se multiplican y mezclan las superficies previas; la geometría, silueta, unión y UV no se redefinen. Los tres mapas proceden de `calyx_transition_v1`, `calyx_straw_v1` y `calyx_straw_v2`, con hashes de máscara y mapa en el manifiesto. Se generan exclusivamente bajo la nueva raíz de revisión, preservando los assets originales.

## Reproducción y límites

La raíz es `outputs/calyx_vein_spread_review_20261111`. Preparación: `scripts/prepare_calyx_vein_review.py`; render: `scripts/render_calyx_vein_review.py` con modos `organs` y `context`; composición: `scripts/report_calyx_vein_review.py`. El plan, las fuentes y las entradas se congelan antes del render. Las revisiones anteriores de bandas y moteado se preservan.

La comparación de cultivo usa las cámaras y escenas guardadas de `scene_027_view_010` y `scene_027_view_007`, con la receta original y guardias exactas de geometría, máscara, instancias y YOLO. En esas vistas cambia únicamente el material. Los grados de contracción se siguen mostrando en capachos huecos aislados; compatibilidad con un fruto interior y admisión de plantas completas contraídas siguen pendientes. Se reutilizan los estados geométricos anteriores y sus mismas semillas, sin nueva poda ni cambios de órganos en las20 plantas admitidas.

Cinco pruebas puras comprueban: prioridad proximal y venosa sobre tejido vecino, continuidad por la costura U sin envolver V, rechazo de entradas sin venas, crecimiento monotónico y conservación de los grados de contracción, y avance vascular anterior al halo en la misma zona distal. La revisión de Codex no sustituye la aprobación del usuario. El banco de503 imágenes y el piloto permanecen pausados; no se inicia entrenamiento ni ampliación.

## Resultado y revisión de Codex

Se completaron cuatro RGB nuevos: dos láminas con siete grados/controles cada una y dos vistas de cultivo. La inspección muestra venas oscuras primero en la zona proximal, ensanchamiento ramificado alrededor de ellas y avance distal con zonas claras entre venas. Los grados avanzados conservan detalle y no usan un reemplazo negro uniforme. La naturalidad y distribución de estos estados siguen pendientes de la revisión del usuario; las dos morfologías comparten el campo registrado de cada preset para comparar los grados, sin estimar frecuencias poblacionales.

Los14 estados geométricos aislados, sus dimensiones y volúmenes coinciden con los de la tanda anterior; las mallas permanecen cerradas y unidas al pedicelo. Las dos vistas de cultivo conservan exactamente las máscaras PNG, instancias y YOLO originales, con cámara y geometría verificadas. En los tres mapas se comparó píxel a píxel el canal de venas con la máscara fuente: registro exacto. Las llegadas de los orígenes proximales son anteriores a las distales según la convención UV esperada.

Pasaron las cinco pruebas nuevas y las cuatro de contracción preexistentes. Se verificaron254 archivos congelados de esta revisión, las fuentes históricas136/1999,20 árboles/admisiones, presupuesto y pausa. El validador del grafo conserva exactamente los mismos10 errores previos, sin regresiones. Las fuentes y muestras anteriores se preservan. No quedó ningún render activo ni se añadió ninguna imagen al banco.

`review.html` contiene las escenas completas y comparaciones; `vein_review.json` registra las comprobaciones. Estado final: `awaiting_user_visual_review`. `outputs/calyx_approval_samples_20261031/latest_review.json` apunta a esta nueva revisión. La generación y ampliación del piloto siguen pausadas.
