# Controlador acotado de corrección nodal

Esta ruta implementa la revisión autorizada el 27 de octubre de 2026. Su salida
son árboles y escenas de diagnóstico físico; no inicia un banco de entrenamiento
ni otro piloto de aumentación. Mantiene el contrato morfológico y los criterios
de admisión de `repulsion_nodal_uchuva.md`.

## Ejecución y presupuesto

`scripts/run_nodal_automation.py --root CARPETA` consume una configuración,
perfiles visuales, fuentes congeladas y `budget.json`. El reloj es
`QueryUnbiasedInterruptTime`: excluye suspensión, sin usar fechas de pared para
estimar cómputo. El presupuesto incluye implementación y pruebas desde el inicio
registrado; no vuelve a cero al arrancar un trabajador. Los intervalos excluidos,
si existen, se unen para no descontarlos dos veces. Un reinicio del reloj exige
recuperación explícita del consumo; nunca se interpreta como presupuesto nuevo.

La primera condición cumplida detiene la cola: cinco horas efectivas o veinte
árboles nuevos admitidos, con semillas y firmas anatómicas distintas. Los dos
árboles previamente admitidos son regresiones y no cuentan hacia ese objetivo.
El orden inicial fue la tercera candidata conservada, semilla 2026102602, y
2026102700 con sus semillas consecutivas. Una cola explícita de diversidad en
`seed_queue.json`, congelada tras un inventario de arquitecturas sin evaluación
física, permite representar estratos morfológicos aún no ensayados. Se conserva
el historial de todos los rechazos y no se interpreta la búsqueda adaptativa
como una tasa de éxito uniforme del generador. Cada candidata tiene un subpresupuesto para evitar que una
sola agote toda la exploración. El primer caso puede utilizar su mejor postura
anterior, tras comprobar el hash y la anatomía del árbol original.

Una única carga Blender corre a la vez, con PID, fecha nativa de creación,
comando y archivos por intento. El padre posee el proceso que detiene. Durante
la ejecución solicita temporalmente evitar suspensión automática; libera esa
solicitud al terminar, sin modificar la configuración energética permanente.
Un fallo operacional detiene la cola conservando evidencia. Un rechazo físico
terminado correctamente permite pasar a la siguiente semilla.

`nodal_constraint_search.solve_ordered_domains()` comprueba el corte temporal
dentro del filtrado de dominios y distingue timeout de agotamiento discreto.
No devuelve una asignación parcialmente comprobada. La reserva de calificación
debe cubrir también la reconstrucción y auditoría de un último estado
provisional; al recuperarlo se vuelve a auditar, nunca se convierte un
checkpoint en admisión por su nombre o por su recuento anterior.

Las continuaciones explícitas se congelan en `continuations.json`, con árbol
original, postura inicial, motivo y hashes por trabajo. Conservan la carpeta
del intento previo. Una semilla admitida tras varios intentos cuenta una sola
vez. Un nuevo reparto temporal exige dejar terminar o preservar el trabajador,
comprobar ausencia de hijos y archivar fuentes y configuración anteriores antes
de volver a congelar; no permite reiniciar el reloj acumulado.

## Correcciones automáticas

`scripts/worker_nodal_automation.py` coordina las búsquedas puras y de malla.
Las hojas se prueban separadas de la reproducción para evitar inanición de una
categoría. Las inserciones se recorren de abajo hacia arriba, priorizando
descenso antes de ascenso. Los movimientos que abren espacio provisionalmente
no equivalen a una admisión.

`blender_nodal_local_repair.repair_local_nodal_contacts()` identifica los nodos
implicados a partir del informe físico. Ensaya contraflexión y articulación de
dos entrenudos de longitud fija; el modo `four_nodes` añade una postura
alternada de cuatro entrenudos con las mismas longitudes y límites angulares.
La primera y tercera inserción se desplazan a lados opuestos del rayo de
crecimiento, y el extremo distal permanece en ese rayo. La selección de
propuestas cubre cada familia y su intervalo angular, priorizando descensos.
Para un contacto interior también se prueban ventanas que comienzan hasta
tres nodos antes: empezar necesariamente en el nodo que colisiona puede dejar
sin propuestas una articulación que sí admite un movimiento conjunto anterior.
Conserva los órganos y traslada conjuntamente
sus descendientes. Las pruebas usan mallas evaluadas, índices espaciales y curvas
reconstruidas. La caché acelera la búsqueda, pero no sustituye la reconstrucción
independiente de todo el árbol. Los capachos mantienen un eje independiente del
pedicelo; su restauración gravitatoria sólo reduce su inclinación previa hacia
abajo, sin voltearlos lateralmente para esquivar contactos.

Se conserva el mejor estado completamente reconstruido y auditado. El criterio
ordena primero cruces físicos y después advertencias de proximidad. Un cambio
provisional peor nunca sustituye ese estado. Los archivos de historia,
ajustes y checkpoints permiten examinar intentos sin convergencia.

Los conos y movilidades de búsqueda son `engineering_heuristic`, no mediciones
botánicas. El techo explícito de exploración del pedicelo no es un ángulo
observado ni una obligación de llevar cada pedicelo a ese extremo.

`nodal_chain_candidates.py` comprueba cuatro direcciones normalizadas y las
excursiones respecto de la entrada original. No incrementa los 35 grados de
exploración de los entrenudos ni modifica la carga reproductiva. El número de
ajustes por pasada es un límite de cómputo, no un límite de órganos del árbol.

## Admisión, imágenes y límites

Una admisión exige cero cruces de las categorías auditadas, suelo válido con
margen de 1 mm, orientación y unión proximal de los capachos válidas, ausencia
de errores morfológicos y la misma firma anatómica antes y después. Se conservan
cantidades, clases y dimensiones nominales de todos los órganos. Las
advertencias de proximidad y la excepción hoja–hoja siguen vigentes; no se
afirma una certificación exhaustiva de flores ni contexto.

La galería de revisión distingue admisiones independientes, rechazos y parciales,
con una tarjeta por semilla. Los dos ejemplos previos aparecen por separado y
no se suman al contador nuevo. Las vistas de rechazo conservan el nombre
`rejected_preview.png` y no son muestras aptas para entrenamiento. El render usa una cámara
calculada a partir de la copa original, no del resultado corregido, y verifica
que luz/materiales/cámara no cambien la geometría. La diversidad visual del
follaje es independiente de las clases sintéticas de apariencia del capacho.
El suelo plano y los fondos diagnósticos no demuestran equivalencia con campo.
La revisión humana de postura y apariencia queda pendiente antes de otro piloto.

Las pruebas `test_nodal_automation.py` cubren límites, contabilidad, integridad y
deduplicación. `blender_nodal_local_automation_probe.py` compara los vértices de
un ajuste local con la reconstrucción independiente, incluidos tallos y órganos.
`test_nodal_chain_candidates.py` y `blender_nodal_four_node_probe.py` verifican
longitudes, ancla distal, prioridad y una actualización real de cuatro nodos
frente a todos los vértices reconstruidos independientemente.
Los dos árboles previamente admitidos se verifican de extremo a extremo por el
nuevo trabajador, sin contarlos como nuevos.

El trabajador solicita también evitar suspensión automática sólo durante su
vida y libera la solicitud al salir. Esto protege una continuación mientras se
pausa el padre para revisar la cola; no cambia ajustes energéticos permanentes.

## Admisión reproductiva escasa y explícita

La revisión del 28/10 permite una pequeña reducción de frutos para resolver
contactos residuales especialmente difíciles. `generate_morphology_tree()`
acepta ahora `reproductive_space_plan` de forma optativa. Sin ese argumento la
ruta anterior conserva su comportamiento y secuencia aleatoria.

`reproductive_space.py` resuelve un conjunto mínimo de unidades reproductivas
que cubre los conflictos confirmados después de la búsqueda de posturas. Un
contacto con un tallo fijo sólo permite omitir la unidad reproductiva; un
contacto entre dos capachos admite escoger una de las dos unidades. Al
desempatar se preservan los índices nodales bajos. El techo de pérdida se
declara antes de aplicar el plan y provoca error si resulta insuficiente;
no determina una carga objetivo ni crea cuotas de fructificación.

El plan está vinculado por hash a la anatomía original y a su evidencia.
Se materializa en la morfología antes de construir geometría: se omite la
unidad completa, con pedicelo, fruto y cáliz, conservando nodo, hoja y rama.
No se borran objetos Blender ni etiquetas. El inventario completo de cada
omisión permite reconstruir en memoria la anatomía original y comprobar que
el resto no se modificó. La yema sin unidad aceptada registra la razón de
ingeniería; no se infiere aborto floral ni una probabilidad biológica medida.

`prepare_third_candidate_space_review.py` regenera sólo la semilla 2026102602
y reproduce las posturas anteriores de los órganos retenidos. El plan procede
de esa postura auditada, de modo que esto es realimentación espacial explícita,
no un generador autónomo que garantice nuevas semillas sin colisiones.
`audit_third_candidate_space_review.py` reconstruye ambos árboles, compara los
vértices mundiales y las caras orientadas de los órganos retenidos, incluidos
los frutos ocultos, y exige las auditorías de malla, suelo, orientación y
morfología antes de renderizar. La comparación geométrica canónica ignora
sólo el orden de enumeración de vértices/caras, sin redondeo ni tolerancia.

El lanzador `launch_third_space_review.py` mantiene un único hijo Blender con
identidad y salida registradas; no tiene cola de semillas ni entrenamiento.
La galería conserva la cámara y las asignaciones de clase anteriores. El
informe de esta candidata se guarda en
`docs/reports/tercera_candidata_admision_reproductiva_2026-10-28.md`.
