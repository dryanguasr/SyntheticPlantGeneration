# Revisión física mediante repulsión nodal

La ruta experimental `trained_trellis_nodal_repulsion_v8` deriva de v7.
Conserva su arquitectura, las cohortes y la carga reproductiva emergente. No
introduce cuotas de frutos ni modifica la planta para conseguir un encuadre.
La repulsión es una **heurística de ingeniería**, no una fuerza magnética ni un
modelo biomecánico calibrado.

## Contrato de crecimiento

`grammar.generate_morphology_tree()` ejecuta la búsqueda nodal antes de que
existan una cámara, luces o materiales. `resolve_growth=False` permite exportar
el árbol inicial para comparar la misma realización antes y después; ese árbol
queda marcado como pendiente. Los presets anteriores conservan su ruta.

Los ajustes se serializan en `provenance.nodal_growth_repulsion_v1`. Son
direcciones efectivas en el marco de la planta, independientes de los ángulos
iniciales. Los intérpretes de Blender y proxies leen el mismo contrato.
La longitud nominal de los entrenudos, las dimensiones de hojas, pedicelos,
frutos y cálices, sus identificadores y estados quedan protegidos por hash.
Cambiar la postura puede cambiar la envolvente y la deformación gravitatoria de
una hoja; no equivale a reducir su longitud o eliminarla.

Cada barrido ordena las inserciones por altura ascendente, orden de rama e
identificador. Prueba bajar antes que subir y después movimientos laterales.
Modificar un entrenudo desplaza su módulo distal completo, con hojas, pecíolos,
pedicelos, flores, frutos interiores, cálices y ramas descendientes. La base
permanece anclada. El cáliz conserva su eje independiente aproximadamente hacia
abajo; mover su pedicelo no gira lateralmente el capacho para esquivar contactos.

Las excursiones de búsqueda son hipótesis numéricas: 35° para entrenudos
laterales y para inserciones implicadas del tallo principal, 120° para hojas y
75° inicialmente para pedicelos respecto de su postura inicial. Una revisión
explícita con motivo y hash puede ampliar la exploración del pedicelo hasta
180°; no cambia por sí misma el eje colgante del cáliz ni demuestra plausibilidad botánica de
cada postura encontrada. El cono del cáliz de 0–25°
desde abajo proviene de la revisión anterior y tampoco es una medición local.
Estos números no son una norma botánica ni garantizan la factibilidad.

Una operación independiente de restauración gravitatoria puede reducir la
inclinación original de un capacho hacia la vertical descendente. Conserva su
azimut original y rechaza cualquier inclinación mayor o escape lateral. Guarda
las direcciones original y adaptada, la fracción de restauración y su condición
heurística. La orientación original no se sobrescribe ni se presenta como
medición real.

## De los proxies a las mallas

La búsqueda pura utiliza envolventes conservadoras y conserva sus informes,
incluidos los contactos pendientes. Su resultado **no certifica una escena**.
La segunda etapa reconstruye las mallas evaluadas y retroalimenta los mismos
grados de libertad del árbol. Si varios capachos se bloquean mutuamente, busca
posturas compatibles para todo el componente de inserciones.

Una pasada puede dejar temporalmente contactos con hojas desplazables para
desbloquear una estructura. El estado sigue rechazado hasta reparar esas hojas
y reconstruir todo desde el JSON. No se ocultan órganos, no se cambian máscaras
para excusar cruces y no se eliminan etiquetas ni instancias.

La admisión mantiene los criterios de la revisión anterior: cero cruces de
mallas auditados, suelo válido a 1 mm y correspondencia cáliz–pedicelo–gravedad.
Las separaciones positivas entre órganos se registran como advertencias bajo la
política previamente autorizada. Los solapamientos hoja–hoja siguen fuera del
rechazo duro; no se presentan como ausencia de colisión física verificada.
Flores y contexto no cuentan con una certificación exhaustiva de colisiones.

## Ejecución de una revisión pequeña

1. Preparar árboles declarando las semillas con
   `scripts/prepare_nodal_review.py`. Se conservan árbol inicial, checkpoints,
   validación, hash de anatomía y fuentes.
2. Ejecutar `scripts/repair_nodal_growth.py` con Blender en segundo plano.
   Los intentos permanecen en carpetas independientes. Un resultado sin cruces
   aún requiere la verificación completa del paso siguiente.
   Los contactos locales que persistan pueden revisarse con
   `scripts/review_local_nodal_joint.py`, utilizando el identificador del nodo
   del informe y `--mode counterbend`. La articulación de dos entrenudos
   conserva ambas longitudes y limita el desplazamiento transversal del extremo
   distal. Un candidato local sigue siendo provisional hasta volver a la
   reparación y auditoría completas; la semilla 2026102601 necesitó este paso.
3. Ejecutar `scripts/render_nodal_review.py` con el árbol inicial y el final.
   Reconstruye la escena, verifica mallas, suelo, orientación y conteos antes de
   producir la imagen final. La cámara deriva de la copa inicial y se conserva
   para la comparación antes/después. Un rechazo guarda evidencia y no produce
   una imagen presentada como admitida.
4. Reunir únicamente las escenas con admisión independiente mediante
   `scripts/report_nodal_review.py`. La galería y el manifiesto mantienen visibles
   las advertencias, conteos totales y revisión humana pendiente.

La revisión usa un suelo plano explícito para aislar el problema del arbusto;
no demuestra validez sobre terreno irregular. Las apariencias de capacho y del
follaje proceden de las configuraciones visuales anteriores, con asignaciones
independientes. Son hipótesis sintéticas y no etiquetas de madurez agronómica.

No se debe pasar un árbol con direcciones nodales explícitas a los adaptadores
históricos que ignoran ese contrato o activan sólo una parte de sus ramas.
Esas entradas fallan de forma explícita. La campaña cerrada y sus fuentes
archivadas permanecen separadas; esta revisión no inicia entrenamiento.

El árbol potencial se reproduce por semilla y parámetros. Una búsqueda cortada
por tiempo puede completar distinta cantidad de ajustes según el equipo; por
eso la evidencia reproducible de postura es el JSON final congelado, su registro
y sus fuentes, además de la semilla. La comparación visual conserva la cámara
del árbol original y no usa el test real para decidir la geometría.

## Verificación

`tests/test_nodal_repulsion.py` comprueba invariancia anatómica, serialización,
prioridad descendente, reversión en caso de fallo y protección ante rutas
históricas incompatibles. `tests/blender_nodal_repulsion_probe.py` compara los
vértices evaluados de ajustes aceptados con una reconstrucción independiente,
incluidos los órganos descendientes y ajustes conjuntos de capachos.
