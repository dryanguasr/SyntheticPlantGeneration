# Refinamiento de venas de Madura, pigmentación entre venas y secado

## Alcance y comparación

El usuario pidió reforzar las venas de las Maduras, suavizar la retícula de las Sobremaduras, aumentar la pigmentación del tejido entre venas y añadir textura de secado. Se conserva la pausa del banco/piloto, las503 vistas previas y20 plantas admitidas. Las nuevas imágenes se generan sólo para revisar esta hipótesis visual; no modifican clases ni se incorporan al entrenamiento.

Se reutilizan los16 recortes reales de train documentados en `outputs/calyx_diffusion_review_20261111/real_comparison.json` (ocho Madura, ocho Sobremadura). La comparación es intencional y descriptiva, sin afirmar prevalencia o independencia de plantas. Las fotos no son una secuencia temporal y las sombras no equivalen a pigmento ni opacidad intrínseca. La referencia sintética inmediata es `revisions/profile_interpretation_03` de esa misma revisión, preservada íntegramente.

## Cambios opt-in en las texturas

El nuevo módulo `calyx_dry_refinement.py` hereda los estados geométricos anteriores y conserva el origen proximal de la reacción/difusión. Aumenta el transporte lateral y la acumulación lenta del pigmento en el tejido contiguo, manteniendo transporte/activación preferentes en la red venosa y crecimiento irreversible. No se generan manchas como fuentes remotas independientes. Los coeficientes siguen siendo `engineering_heuristic`, sin edad fisiológica o concentración química calibrada.

En Madura se refuerzan específicamente las venas de primer orden con un tono oscuro violáceo/café; el tejido claro mantiene la misma base y las venas menores no se refuerzan al mismo nivel. En Sobremadura, el peso cromático de la venación fina disminuye al acumularse pigmento, mientras el fondo intervascular se oscurece. La jerarquía deja visibles las nervaduras principales sin convertir todo el órgano en una rejilla oscura.

Los mapas de secado añaden fibras y pliegues cortos no periódicos, pequeñas variaciones claras y mayor rugosidad. El relieve de la retícula fina disminuye con el pigmento y se sustituye parcialmente por microrelieve de papel seco. Se generan normales por grado, en lugar de usar un único mapa normal para todos. Son aproximaciones ópticas en color/normales/rugosidad: no se añaden pelos físicos, huecos transparentes ni desplazamiento de malla. Se conservan las ganancias cromáticas y la luz del perfil congelado.

La raíz nueva es `outputs/calyx_texture_refinement_20261111`; los assets previos no se sobrescriben. La separación se mantiene entre el estado puro, preparación offline de mapas, intérprete Blender y revisión. La contracción continúa en capachos huecos aislados, con compatibilidad del fruto interior pendiente; en las vistas de cultivo cambian únicamente materiales.

## Comprobaciones antes de iluminar

Los mismos píxeles de la red permiten comparar los albedos anterior/nuevo. L* se calcula nominalmente desde sRGB de la textura, antes de las ganancias del perfil: no es una medición de pigmentación o reflectancia real.

| Región de textura | L* medio anterior | L* medio nuevo |
|---|---:|---:|
| Madura, venas principales | 42,1 | 18,7 |
| Madura, tejido entre venas | 75,1 | 75,0 |
| Sobremadura avanzada, venas secundarias | 35,3 | 39,9 |
| Sobremadura avanzada, tejido entre venas | 53,2 | 45,2 |

Estas mediciones corroboran la dirección del ajuste bajo un denominador emparejado. No comparan grupos de órganos reales ni demuestran naturalidad. La media de pigmento simulado P tampoco representa un porcentaje de superficie lesionada o una edad.

Cuatro pruebas nuevas verifican contraste jerárquico de Madura con tejido claro retenido, reducción del contraste reticular tardío, mayor pigmento intervascular sin fuentes remotas ni reversión, y reproducibilidad del microrelieve/conservación de los grados geométricos. Las escenas de cultivo exigen cámaras, geometría y anotaciones idénticas a sus referencias; el detalle de secado usa checkpoints aislados anterior/nuevo con la misma cámara e iluminación.

## Resultado y revisión visual de Codex

Se completaron seis RGB nativos de Blender: dos láminas de órganos, dos vistas de cultivo y dos detalles emparejados anterior/nuevo. Las láminas contienen catorce capachos huecos cuyos estados, límites y volúmenes no cambian. Las dos vistas de cultivo conservaron exactamente geometría, cámaras, máscaras, instancias y etiquetas YOLO. El par de detalle conserva exactamente malla, cámara e iluminación. No se añadieron imágenes al banco ni se inició entrenamiento.

Codex inspeccionó las láminas, una vista de cultivo, la comparación con recortes reales y el detalle ampliado. En Madura las venas principales resultan más oscuras sin oscurecer el tejido claro contiguo. En Sobremadura la retícula fina pierde protagonismo al cubrirse el tejido intervascular, con progresión proximal más amplia y regiones distales claras conservadas. El detalle emparejado confirma que esa diferencia procede de las texturas. Sin embargo, el nuevo acabado seco aún se ve más liso y marrón que los ejemplos reales avanzados, que incluyen aspereza, pubescencia y tonos grisáceos/violáceos. El microrelieve añadido sigue siendo sutil en el render. La dirección solicitada mejora, pero la naturalidad y equivalencia con los datos reales siguen siendo parciales y no están calibradas.

La galería es `outputs/calyx_texture_refinement_20261111/review.html`; `real_before_refined.png` compara reales/anterior/nuevo y `dry_detail_comparison.png` muestra el par controlado. Se verificaron de nuevo las fuentes y los artefactos protegidos durante la composición. El validador del grafo conserva exactamente los diez errores preexistentes de localizadores, sin regresiones. Se mantienen las503 imágenes históricas, las20 plantas y la pausa. Estado: `awaiting_user_visual_review`; la revisión de Codex no constituye aprobación humana ni autoriza ampliar el piloto.
