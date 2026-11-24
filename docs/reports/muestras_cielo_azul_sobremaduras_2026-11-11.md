# Muestras de cultivo con mayoría de cielo azul y pocas Sobremaduras

El usuario autorizó unas pocas escenas para revisar cielos azules, iluminación variada y las nuevas texturas de Sobremadura antes de ampliar el dataset o reanudar el piloto. Se preparan cuatro capturas de dos escenas de cultivo previamente admitidas, conservando sus plantas, disposición, cámaras y geometría. Tres configuraciones son azul despejado y una despejada con bruma. Se mantienen960×720, Cycles/OptiX,12 muestras y denoising; son vistas de aprobación aisladas, fuera del journal del banco.

El plan puro independiente varía elevación, azimut y tamaño angular del sol. La atmósfera y el pequeño ajuste de saturación del cielo analítico alimentan tanto la iluminación ambiental como el fondo de cámara. Se mantiene la corrección de horizonte `aligned_horizon_matte/3` y el paisaje inferior. Los coeficientes ópticos y las horas solares implícitas son `engineering_heuristic`; no equivalen a meteorología medida. La presencia visual de azul se debe comprobar en los renders.

La asignación local de apariencia propone3% de Sobremaduras por escena, con tope5% de instancias visibles en cada vista y algunos ejemplos suficientemente grandes para inspección. Son cuotas de esta pequeña revisión, no prevalencias botánicas ni una política definitiva de entrenamiento. Las restantes unidades se distribuyen entre Pintona/Madura sin quitar órganos. Las Sobremaduras recorren cinco grados de la textura gris/venosa reciente. No se aplica contracción a las plantas admitidas: el secado aquí es óptico. Todos los IDs y máscaras deben coincidir con el checkpoint; sólo las clases de las etiquetas nuevas cambian para corresponder a la apariencia nueva. Las etiquetas originales no se modifican.

El renderizador exige admisión física previa (cero cruces duros, suelo y orientación válidos), hashes exactos del checkpoint, geometría íntegra antes/después, máscara idéntica y las mismas cajas/píxeles/instancias. Las proximidades/hoja-hoja y límites de contexto/flores conservan su política anterior. Los resultados se preservan en `outputs/blue_sky_sparse_samples_20261111`; el banco de503 imágenes y las20 plantas permanecen intactos, al igual que pausa, fuentes y presupuestos históricos. No se inicia entrenamiento ni se reanuda el piloto.

## Recuperaciones preservadas y variación de luz

El primer intento de la vista amplia detectó cinco píxeles de borde distintos tras descomponer la matriz serializada de cámara. Su RGB/máscara, fallo, fuentes y lock se archivaron en `revisions/camera_channel_recovery_01`; no se admitió esa pareja. La pose se recupera ahora ejecutando el mismo muestreador con la semilla, índice y lista de objetivos originales, conservando sus canales de ubicación/Euler. La máscara se valida antes de renderizar RGB.

Se preservó otra preparación en `revisions/bulk_guard_recovery_02`, deteniendo sólo el propietario verificado por PID y creation tick. La guardia utiliza la función completa `binary_geometry_digest` que ya empleaban las capturas originales: todos los vértices, loops/topología, curvas y transformaciones, sin muestreo ni tolerancia. Se compara exactamente con las huellas de producción originales y se mantiene el SHA del checkpoint y la admisión histórica. No se relajan cruces, orientación, unión ni suelo.

Las dos tomas completas de la escena027 mostraron luz azulada en sombra. Se conservan para representar ese caso; la preparación de028 se archivó en `revisions/front_lit_complement_03` antes de renderizar nuevas parejas, para complementar con sol frontal y relleno blanco de120/80 W. La configuración local y sus fuentes/lock anteriores están preservados. Las condiciones de las primeras dos tomas no cambian. Se continúa hasta las cuatro muestras previstas, no una nueva campaña ni un cambio de las plantas/texturas. La interpretación de color bajo estas luces debe revisarse en los RGB, no deducirse sólo del nombre del cielo.

## Resultado y revisión de Codex

Se completaron cuatro parejas RGB/máscara/YOLO: tres azul despejado y una despejada con bruma, en dos disposiciones de cultivo admitidas. Las cuatro cámaras, máscaras de ID, cajas y píxeles por instancia coinciden exactamente con sus capturas fuente. Las etiquetas locales reflejan las nuevas apariencias y no sustituyen las originales. Los hashes de fuentes, pausa, presupuestos, locks históricos, árboles y admisiones del pool de20 se verificaron al terminar. No hubo ampliación del banco de503 imágenes ni entrenamiento. Ambos renderizadores terminaron; los intentos previos y preparaciones interrumpidas se conservaron fuera de las muestras completas.

| Vista fuente | Cielo | Distancia al foco | Sobremaduras visibles / total | Fracción |
|---|---|---:|---:|---:|
| 027/021 | Azul, lateral | 3,82 m | 65 / 1913 | 3,40% |
| 027/010 | Azul, sombra/contraluz | 1,17 m | 20 / 558 | 3,58% |
| 028/008 | Azul, frontal | 1,23 m | 33 / 1010 | 3,27% |
| 028/010 | Bruma, relleno suave | 0,83 m | 12 / 368 | 3,26% |

Los conteos incluyen capachos diminutos; no se aplicó un filtro adicional de entrenamiento. Las vistas no son plantas independientes nuevas. Pasaron las dos pruebas del plan puro y la compilación de los cuatro módulos/scripts nuevos. El grafo conserva exactamente los diez errores históricos de localizadores y no añade regresiones.

Codex inspeccionó los cuatro RGB, la lámina conjunta y cuatro recortes ampliados de grados distintos. Se observa azul en el fondo de las tres tomas despejadas, con distinta dirección/dureza de luz; los primeros planos incluyen menos cielo. La vista con bruma conserva tonos más neutros y permite distinguir progresión desde venas y tejido amarillo residual. Sin embargo, las Sobremaduras avanzadas/decoloradas adquieren una dominante azul excesiva en algunas tomas despejadas, también visible en sombras de suelo/follaje. La nueva textura funciona mejor en el detalle aislado que bajo estas condiciones. La evidencia señala un problema pendiente en el equilibrio de iluminación/interpretación cromática; no se ha aislado su causa con un ensayo emparejado, por lo que no se atribuye definitivamente sólo al cielo o al material.

Estas cuatro muestras cumplen las guardias físicas y de anotación, pero no justifican todavía ampliar con esta configuración cromática ni prueban utilidad de entrenamiento. La recomendación de Codex es corregir esa dominante antes de una tanda grande. Estado `awaiting_user_sample_review`, sin aprobación humana ni reanudación del piloto. Galería `outputs/blue_sky_sparse_samples_20261111/review.html`, lámina `sample_overview.png` y detalles `overmature_crops.png`.
