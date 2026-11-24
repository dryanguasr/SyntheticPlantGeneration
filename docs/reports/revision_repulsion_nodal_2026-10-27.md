# Revisión del crecimiento nodal y de los cruces de mallas

## Alcance

Intervención solicitada el 27 de octubre de 2026: corregir las intersecciones
desde el árbol del arbusto, conservar frutos y follaje, priorizar movimientos
descendentes y presentar escenas físicamente auditadas antes de otro piloto.
No se ha iniciado una nueva campaña de entrenamiento.

Los artefactos de revisión pertenecen a
`outputs/nodal_repulsion_review_20261027/`. La campaña factorial cerrada, sus
resultados negativos, controles reales y fuentes archivadas permanecen aparte.
Los intentos fallidos de esta intervención también se conservan.

## Intervención implementada

La política experimental v8 mantiene la arquitectura y carga emergente de v7.
Las cámaras, luces, materiales y objetivos de cajas no participan en la búsqueda
de espacio. Se serializan las direcciones efectivas de entrenudos, pecíolos y
pedicelos; los intérpretes geométrico y de proxies consumen el mismo contrato.
Los adaptadores históricos que pueden ignorar esas direcciones o activar sólo
una parte de la planta rechazan explícitamente estos árboles.

La búsqueda recorre inserciones de abajo hacia arriba y prueba bajar antes de
subir. Conserva identificadores, topología, estados y dimensiones nominales por
hash. Una corrección de rama lleva consigo todas sus hojas, pecíolos, pedicelos,
flores, frutos interiores, cálices y ejes descendientes. Se mantienen tanto los
órganos visibles como los que no producen una anotación en una captura.

Los proxies sólo orientan la búsqueda. La retroalimentación posterior utiliza
mallas evaluadas y puede coordinar inserciones de capachos que se bloquean
mutuamente. Los contactos temporales siguen rechazados; no se presenta un
checkpoint de búsqueda como una escena aceptada.

Se añadieron dos movimientos locales de pares de entrenudos. El primero mueve
la inserción sobre la intersección de las dos esferas de longitud, manteniendo
ambos extremos fijos. El segundo permite una contraflexión que mantiene las dos
longitudes y la dirección de crecimiento del extremo distal, con una pequeña
reducción de la distancia entre los extremos. Esa reducción se debe a la
postura, no a acortar entrenudos o reducir órganos. Evita exigir un traslado
lateral de toda la copa para separar un contacto local.

La metáfora de repulsión no representa una fuerza magnética ni una biomecánica
calibrada. Las amplitudes de búsqueda son hipótesis de ingeniería. La ampliación
experimental de movilidad del pedicelo de 75° a 150° y, en una búsqueda, 180° se registra con motivo y
hash; no cambia el eje independiente del capacho ni constituye una distribución
botánica medida. Las máximas excursiones efectivamente utilizadas fueron
74,81° y 114,48° en las dos realizaciones admitidas, respectivamente. El techo
de búsqueda no equivale al ángulo final aplicado a cada órgano.

En la realización 2026102600 se aplicó además una restauración hacia la gravedad
a dos de sus 330 capachos: de 19,90° y 9,58° desde abajo a 0°. Se conservaron
los valores originales y se registraron los adaptados por separado. Esta ruta
sólo puede reducir la inclinación original; rechaza una rotación lateral o un
aumento del alejamiento de la vertical. No cambia dimensiones ni semántica.

## Observaciones comprobadas durante la revisión

- Una realización conserva 909 hojas y 330 frutos; otra, 762 hojas y 274 frutos;
  la tercera, 1.122 hojas y 408 frutos. Son tres semillas declaradas, sin
  seleccionar arbustos de menor carga para conseguir una admisión.
- La primera búsqueda redujo los contactos estimados, pero dejó cruces reales.
  En la primera realización, una pasada de mallas pasó de 312 a 14 cruces; por
  tanto, esa pasada no era admisible.
- Los residuos incluían grupos de capachos vecinos y contactos con el propio
  tallo. En una realización se llegó a un único cruce entre el capacho del nodo
  principal 12 y el entrenudo que llega a ese nodo. Mantener fija la postura del
  tallo principal excluía precisamente ese grado de libertad.
- Ese capacho tiene longitud nominal de 4,648 cm, radio nominal de 1,884 cm y
  pedicelo de 1,346 cm. Son parámetros de esa realización sintética, no
  mediciones de una planta real. Explican por qué una orientación descendente
  por sí sola no evita que la envolvente alcance el tallo.
- Se detectaron costes cuadráticos ajenos a la biología: consultas de propiedad
  de escenas por objeto, eliminación individual de miles de objetos y pares
  invariantes de módulos rígidos. Se sustituyeron por comprobación de pertenencia
  e índices espaciales en bloque, preservando las mismas exclusiones físicas.

## Criterio de admisión y límites

Una escena final debe reconstruirse desde el JSON y volver a verificar cero
cruces de las mallas auditadas, suelo a 1 mm, correspondencia proximal
cáliz–pedicelo, orientación descendente del cáliz, validación por etapa y hash de
anatomía. Una imagen provisional o una reducción de cruces no satisface ese
criterio.

Se conserva la política anterior: las proximidades positivas interórgano son
advertencias y los solapamientos hoja–hoja no forman parte del rechazo duro.
No equivalen a ausencia de contacto físico verificada. Las flores y el contexto
no tienen certificación exhaustiva de colisiones. El suelo plano de estas
escenas de diagnóstico tampoco acredita comportamiento sobre terreno irregular.

La cámara de la comparación se determina a partir de la copa original y se
mantiene fija. La apariencia verde o amarillenta y las tres clases de capacho
son factores independientes de la corrección geométrica. Sus etiquetas son de
apariencia sintética, no de madurez agronómica real.

## Resultados de la revisión física

| Semilla | Follaje de revisión | Hojas conservadas | Frutos/capachos conservados | Cruces originales → finales | Advertencias de proximidad finales | Suelo y unión/orientación |
|---|---|---:|---:|---:|---:|---|
| 2026102601 | Verde | 762 | 274 | 1.021 → **0** | 200 | Válidos; 274 capachos comprobados |
| 2026102600 | Más amarillento | 909 | 330 | 1.038 → **0** | 247 | Válidos; 330 capachos comprobados |

También se conservaron las 37 y 45 flores, los 105 y 125 ejes y todos los nodos,
respectivamente. Los hashes de anatomía protegida son idénticos entre el árbol
original y el final de cada realización. La inclinación máxima final del
capacho es 23,39° y 23,90° desde abajo; todos permanecen dentro del cono
descendente original. La separación del suelo se volvió a comprobar a 1 mm,
incluidos los frutos interiores ocultos en RGB.

Cada imagen final procede de una reconstrucción nueva, después de guardar y
volver a leer el JSON. No es una imagen del estado provisional empleado por la
búsqueda. Las dos apariencias y las tres clases se asignaron a unidades ya
existentes y se mantuvieron iguales en cada comparación antes/después.

La tercera candidata, 2026102602, conserva sus 1.122 hojas y 408 frutos pero no
está admitida: se conserva una medición completa con 16 cruces y un estado
posterior auditado con 24. Sus checkpoints son desarrollo pendiente y no
aparecen en la galería de escenas admitidas. No se afirma que esa arquitectura
sea imposible ni que la aceptación de dos ejemplos estime una tasa general de
éxito del generador.

Galería local: `outputs/nodal_repulsion_review_20261027/gallery/index.html`.
El archivo `review_manifest.json` identifica los dos árboles distintos, las
imágenes y los hashes de sus auditorías. Cada carpeta de escena contiene
`admission.json`, los informes de malla, suelo, orientación y morfología, la
cámara, asignaciones de apariencia, fuentes archivadas, imágenes y `scene.blend`.

Las imágenes utilizan suelo plano de diagnóstico y fondo sencillo. Su
admisión física no demuestra semejanza de contexto, iluminación, textura ni
utilidad para el detector. Los tallos y posturas requieren revisión botánica y
visual humana; no se han convertido las hipótesis numéricas en mediciones de
campo. No se exportó ni entrenó un nuevo banco y no se promovió ningún modelo.

## Verificación de código y continuidad

Pasaron 137 pruebas puras: 14 de repulsión/serialización y restauración
gravitatoria, 98 de los contratos de auditoría anteriores, 19 de poses de ejes y
6 de orientación reproductiva. Pasaron 15 pruebas en Blender: 4 de integración
nodal, coordinación y limpieza privada, y las 11 regresiones anteriores de
reparación geométrica.

El validador del grafo conserva los mismos diez errores preexistentes de
localizadores: se compararon sus pares archivo/texto con el grafo archivado y
no apareció un error nuevo. Se verificaron sin cambios el cierre, manifiesto y
lock de entrenamiento de la campaña factorial cerrada, junto con sus tres
scripts de campaña archivados. Los intentos y fuentes de esta revisión se
mantienen separados.

Estado: **ejemplos físicos listos, revisión visual humana pendiente**. No se ha
iniciado otro piloto. Los casos que no converjan mantienen el rechazo físico;
no se completan dosis con clones ni se reducen sus órganos para admitirlos.

La implementación y sus comandos están descritos en
`docs/guides/repulsion_nodal_uchuva.md`. Las pruebas puras protegen anatomía,
serialización, prioridad y reversión ante fallos. Las pruebas de Blender comparan
los vértices y cruces de una actualización con una reconstrucción independiente.
