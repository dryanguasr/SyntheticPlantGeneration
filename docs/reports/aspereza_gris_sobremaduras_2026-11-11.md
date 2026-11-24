# Sobremaduras: aspereza y tonos grisáceos

El usuario solicitó intensificar la aspereza y los tonos grisáceos sin perder la pigmentación progresiva desde las venas. Esta revisión es sólo visual: conserva el banco de503 imágenes,20 plantas y el piloto pausados. Los resultados se generan por separado en `outputs/calyx_ash_drying_20261111`; las muestras anteriores permanecen intactas.

## Método y límites

El nuevo módulo puro `calyx_ash_drying.py` reutiliza exactamente el solver, la red venosa y los estados de forma de `calyx_dry_refinement.py`. No cambia la activación proximal, la acumulación irreversible ni el transporte preferente por venas. El tejido ya pigmentado recibe una desaturación progresiva y un leve matiz frío, con variaciones pequeñas e irregulares. Se compensa en los mapas horneados el sesgo amarillo del perfil de albedo existente, sin cambiar dicho perfil. El operador cromático conserva la luminancia del pigmento antes del render, salvo el moteado fino documentado.

El intérprete Blender conserva mallas y alfa, así como la mezcla difusa transmitida previa. Añade relieve óptico de papel seco, microgranulado no periódico y normales por grado; no añade pelos físicos ni modifica siluetas. El color y el relieve son `engineering_heuristic`, sin calibración de reflectancia, fisiología o edad. La contracción sigue limitada a capachos huecos aislados y no certifica compatibilidad con el fruto interior.

Las referencias son los mismos16 recortes de entrenamiento (ocho Madura y ocho Sobremadura) ya documentados, sin usar nuevas imágenes de test. Son órganos distintos y no una secuencia temporal ni una escala física común. Oscuridad, sombra y pigmentación intrínseca no se consideran equivalentes.

Tres pruebas puras comprueban identidad del solver y de los grados geométricos, conservación de Madura y tejido no pigmentado, y disminución del cromatismo tras las ganancias congeladas sin borrar el contraste de luminancia. La comparación nativa debe mantener cámara, malla e iluminación emparejadas. La revisión de Codex se registra separada de aprobación humana; no autoriza entrenamiento ni ampliación.

## Resultados ejecutados y comparación

Se completaron cuatro RGB nativos de Blender: dos láminas con catorce capachos huecos y dos macros emparejadas anterior/nueva. Los catorce estados mantienen forma, límites, volumen, unión y topología de la revisión anterior. El detalle conserva exactamente malla, cámara e iluminación. No se renderizaron nuevas escenas de cultivo ni se incorporaron imágenes al banco. La preparación y el informe verificaron los locks históricos, las20 plantas y sus admisiones, así como la pausa y el presupuesto intactos.

Los42 mapas de Pintona/Madura (color, normales y rugosidad de siete grados por clase) conservaron sus hashes exactos. Las estadísticas de todos los campos de difusión coinciden con las anteriores. El rango medio entre canales lineales tras aplicar las ganancias nominales desciende de0,213 a0,059 en la textura avanzada; es una comprobación de desaturación de mapas, no una medida de semejanza con las fotos ni de pigmento real. Pasaron las tres pruebas nuevas y las cuatro anteriores; los cinco archivos Python nuevos compilaron correctamente. El grafo conserva exactamente los diez errores previos de localizadores, sin regresiones.

Codex inspeccionó la lámina inicial, la macro emparejada y el panel reales/anterior/nuevo. El cambio avanzado es gris carbón, con matiz frío tenue y una superficie más granulada. Permanecen regiones distales amarillentas, nervaduras principales y el avance proximal/intervascular. El gris se acerca más al ejemplo real avanzado que el marrón previo; la transición intermedia permanece visible y Madura no cambia. La aspereza aún es más fina y regular que en las fotos reales y no reproduce la pubescencia física ni toda su heterogeneidad gris/violácea. No se afirma equivalencia fotométrica, naturalidad completa o eficacia de entrenamiento.

Las muestras están en `outputs/calyx_ash_drying_20261111/review.html`, con `real_before_refined.png`, `dry_detail_comparison.png` y `shape_comparison.png`. Las muestras anteriores se preservan. Estado `awaiting_user_visual_review`; banco y piloto permanecen pausados, con503 imágenes y20 plantas históricas, sin nuevos entrenamientos.
