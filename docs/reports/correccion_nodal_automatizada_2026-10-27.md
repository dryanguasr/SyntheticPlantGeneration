# Corrección nodal automatizada de uchuva — 27 de octubre de 2026

## Alcance y estado

Revisión de generación independiente de las campañas de entrenamiento cerradas.
El usuario autorizó automatizar las correcciones de postura, continuar con la
tercera candidata y explorar semillas adicionales conservando frutos y follaje.
La parada es el primero de cinco horas efectivas de trabajo o veinte arbustos
nuevos físicamente admitidos. No se inicia otro piloto antes de mostrar y revisar
estos resultados.

Estado de este documento: **búsqueda terminada; revisión visual humana pendiente**.

**Resultado al cierre: 0 arbustos nuevos admitidos de 9 semillas distintas; parada por límite de tiempo efectivo. No se inició otro piloto.**
Los artefactos están en `outputs/nodal_controller_automation_20261027/`.

## Método congelado

El controlador secuencial y un trabajador Blender por semilla conservan la
arquitectura v8, las dimensiones nominales, clases y órganos de cada árbol. La
huella anatómica excluye únicamente los nuevos registros de postura; protege el
resto de atributos y la topología. El primer caso reutiliza la mejor postura
anterior de la tercera candidata, comprobando el original y sus hashes; las
siguientes semillas se generan con el orden y las revisiones de cola declarados.

La búsqueda alterna descenso de hojas, coordinación de pedicelos, movimientos
de ramas y articulaciones locales de dos entrenudos de longitud fija, ordenados
desde los nodos bajos. Puede abrir contactos provisionalmente para escapar de
un bloqueo, pero sólo conserva como mejor resultado un estado reconstruido por
completo. La dirección del capacho es independiente del pedicelo. Si se activa
restauración gravitatoria, sólo puede acercar su eje original a la vertical
hacia abajo; no añade una rotación lateral para esquivar otro órgano.

El presupuesto acumulado usa el reloj de Windows que excluye suspensión e
incluye implementación y pruebas. Hay subpresupuestos de exploración por
candidata y una reserva de verificación. No se reinicia el consumo con cada
proceso ni se cuentan dos veces los árboles previamente admitidos.

## Comprobaciones previas

Pasaron ocho pruebas puras del controlador y una prueba real en Blender de
articulación local: los vértices de todos los órganos y tallos coinciden con
una reconstrucción independiente, con la tolerancia de la prueba, y coinciden
los recuentos de cruces. Los dos ejemplos admitidos en la revisión previa
volvieron a pasar de extremo a extremo por el nuevo trabajador:

| Semilla de regresión | Hojas conservadas | Frutos/capachos conservados | Cruces | Proximidades |
|---|---:|---:|---:|---:|
| 2026102601 | 762 | 274 | 0 | 200 |
| 2026102600 | 909 | 330 | 0 | 247 |

Ambos mantuvieron suelo de 1 mm, orientación y unión proximal válidas, sin
errores morfológicos. **No cuentan como árboles nuevos**. La primera regresión
precede una revisión del comprobador de integridad de configuración; se
conservaron ambos locks y fuentes. La segunda y la cola nueva usan el lock
definitivo que comprueba también perfiles y configuración.

## Interpretación y límites

Un inventario puro adicional de ocho semillas, sin render ni admisión física,
produjo 827–1.349 hojas y 296–490 frutos por árbol. Tras los ensayos concentrados
en árboles de unas 1.045–1.122 hojas se congeló una preferencia por las semillas
2026102708 y 2026102709, de 827/874 hojas y 296/327 frutos, seguida del extremo
2026102710 si quedaba tiempo. Se regeneran intactas mediante el mismo preset;
no se podan ni redimensionan los árboles existentes. La cola quedó definida
antes de su evaluación física en `seed_queue.json` y `seed_queue_rationale.json`.

Esto complementa la diversidad de la búsqueda, pero implica selección adaptativa
por morfología y no permite estimar una tasa uniforme de éxito. Los ocho árboles
del inventario no cuentan como válidos ni como ensayos físicos completos. Se
conservan todos los casos densos y fallidos anteriores. Esta revisión cambia
sólo el orden de semillas, no la física ni el presupuesto. La prueba de cola y
deduplicación eleva a diecisiete el total de pruebas puras; las siete pruebas
distintas en Blender permanecen sin cambios.

En el subramal residual de la tercera candidata, cuatro nodos consecutivos
tienen entrenudos nominales de 1,33–1,84 cm y pedicelos de 1,07–1,48 cm. Sus
capachos tienen longitudes nominales de 3,85–5,90 cm y radios de 1,59–2,07 cm.
En la postura conservada, las dos parejas implicadas tienen separaciones de
inserción esperadas de 10,7 y 14,2 mm según el intérprete y su escala. Son
**valores del modelo**, no mediciones de campo ni envolventes deformadas medidas.
Se conservaron con sus hashes en `packing_diagnosis.json`.

Estas relaciones sugieren un empaquetamiento exigente y justifican revisar la
coherencia entre desarrollo de órganos, separación nodal y pedicelo antes de
seguir modificando ángulos. No prueban por sí mismas colisión ni imposibilidad:
los tres cruces se verificaron separadamente sobre mallas evaluadas. No se
alteraron tamaños ni se eliminaron órganos para facilitar la admisión.

### Revisión del reparto temporal durante la ejecución

La tercera candidata terminó su primer tramo con 3 cruces, frente a los 16 de
su postura inicial conservada. Los dos primeros árboles nuevos terminaron sus
tramos iniciales de ocho minutos con 929 y 1.056 cruces, frente a 1.259 y 1.327
respectivamente. Ninguno se contó como admitido.

Se detuvo únicamente el padre verificado y se dejó terminar al trabajador
actual con sus fuentes originales. Se comprobó la ausencia de hijos antes de
congelar una revisión de controlador y configuración: hasta 30 minutos por
árbol nuevo, 15 para continuar la tercera candidata, ciclos con más tiempo para
hojas y reproducción, y búsqueda fina local tras bajar a 64 contactos o menos.
Este umbral sólo distribuye cómputo: la admisión sigue exigiendo cero cruces.
El contador global de cinco horas y todos los intentos previos se conservaron.
La continuación reutiliza el mejor árbol reconstruido con la misma anatomía;
no cuenta como una semilla nueva adicional.

La revisión también fija salida de error de Python en Blender, comprueba el
manifiesto de continuaciones y permite una vista diagnóstica de un rechazo,
rotulada por separado de las admisiones. No cambia dimensiones ni criterios
físicos. Los locks y fuentes anteriores están archivados en
`revisions/longer_per_seed_search/`.

### Corte combinatorio y reserva de auditoría

La semilla 2026102702 redujo 970 cruces a 28, pero el watchdog cortó su intento
durante la verificación final. Se detectó que el filtrado de dominios del
coordinador reproductivo comprobaba tiempo al entrar en la recursión, sin
comprobarlo dentro de un filtrado ancho. Se separó ese buscador en
`nodal_constraint_search.py`, con interrupción dentro del bucle y estado
`time_budget_exhausted` distinto de agotar los dominios discretos. No cambia
los candidatos, tolerancias ni criterios de colisión.

Se preservaron el intento y el checkpoint del siguiente árbol antes de detener
sus procesos identificados. La revisión congelada reserva tres minutos para
calificación, reconstruye el mejor estado de la semilla 2702 para completar
sus diagnósticos y permite continuar desde ese progreso. Pasaron cuatro pruebas
nuevas de búsqueda acotada, las ocho de control y cinco en Blender, incluidas
coordinación de dos/tres capachos y reconstrucción de todos los órganos.
El presupuesto global no se amplió; la evidencia está en
`revisions/bounded_constraint_search/`.

### Coordinación de cuatro nodos

La continuación con reserva temporal completa terminó auditada, conservando
23 cruces en la semilla 2026102702. Se preparó una familia adicional que mueve
cuatro entrenudos de forma conjunta, con inserciones alternadas a ambos lados
del rayo de crecimiento. Conserva sus cuatro longitudes, la anatomía, el eje
colgante de los capachos y el mismo límite angular de 35 grados respecto de la
entrada. No convierte órganos ni modifica su tamaño para despejar contactos.

Pasaron cuatro pruebas puras adicionales y una prueba de Blender que obligó
a ejecutar un movimiento real de cuatro nodos y comparó todos los vértices con
la reconstrucción completa. Se repitió también la regresión del modo de dos
nodos. Son 16 pruebas puras y 6 pruebas distintas en Blender en total. Esto
valida el contrato geométrico de la familia nueva, no su convergencia general
ni su realismo botánico. Las fuentes previas y la revisión probada están en
`revisions/four_node_refinement/`; el contador de cinco horas sigue intacto.

### Cobertura de ventanas anteriores al contacto

La inspección de la tercera candidata encontró cero propuestas legales de
cuatro entrenudos empezando en dos de los nodos implicados, pero doce
propuestas empezando un nodo antes. El controlador amplía ahora la selección
a ventanas de la misma rama que comienzan hasta tres nodos antes del contacto,
con el orden desde abajo y los límites anteriores intactos.

Una regresión en Blender aisló un contacto únicamente en un nodo interior y
exigió que la corrección comenzara en su nodo anterior; pasó y todos los
vértices coincidieron con una reconstrucción completa. La prueba general de
cuatro nodos también pasó. Son siete pruebas distintas en Blender y dieciséis
puras. Esta comprobación valida cobertura y coherencia, no asegura aceptación
de cualquier semilla. Fuentes e intentos anteriores permanecen en
`revisions/upstream_nodal_windows/`. El trabajador dispone de una solicitud
temporal propia para evitar suspensión automática durante su ejecución.

Admisión significa cero cruces de las categorías auditadas, suelo válido,
orientación válida y anatomía intacta. La excepción hoja–hoja y las advertencias
de proximidad permanecen explícitas. No es una certificación exhaustiva de
flores, contexto o terreno irregular. Los rangos de exploración son heurísticas
de ingeniería, no parámetros botánicos medidos ni una distribución natural
validada.

La galería utiliza cámaras calculadas a partir de cada copa original, sin
reencuadrar el resultado para ocultar defectos. Son vistas de diagnóstico con
suelo plano; no prueban semejanza fotométrica con el dataset ni utilidad de
aumentación. Toda revisión visual humana sigue pendiente. No hay métricas de
detector nuevas en esta intervención.

El procedimiento y contratos están descritos en
`docs/guides/controlador_repulsion_nodal.md`.

<!-- AUTOMATIC_NODAL_RESULTS -->

## Resultados finales de la automatización

La cola terminó por **límite de tiempo efectivo**, con **0 arbustos nuevos admitidos** de 9 semillas con intentos registrados y 16 intentos terminados o preservados. 8 semillas tienen al menos una auditoría final completa; las demás sólo cuentan como parciales. Los dos ejemplos anteriores no están incluidos en el objetivo.

Reloj efectivo acumulado: 5.0002 h; tope autorizado: 5 h. Incluye implementación, pruebas, búsqueda y vistas dentro de la ejecución; excluye suspensión. No se reinició el presupuesto. No se entrenó ningún detector ni se inició otro piloto.

| Semilla | Hojas | Frutos/capachos | Cruces iniciales → mejor → final | Proximidades | Resultado |
|---|---:|---:|---|---:|---|
| 2026102602 | 1122 | 408 | 16 → 3 → 3 | 244 | Rechazado |
| 2026102700 | 1069 | 382 | 1259 → 929 → 929 | 380 | Rechazado |
| 2026102701 | 1062 | 394 | 1327 → 1056 → 1056 | 439 | Rechazado |
| 2026102602 (continuación) | 1122 | 408 | 3 → 3 → 3 | 244 | Rechazado |
| 2026102702 | 1045 | 385 | 970 → 28 → — | — | Parcial sin admisión |
| 2026102703 | 1062 | 390 | 1001 → 1001 → — | — | Parcial sin admisión |
| 2026102702 (continuación) | 1045 | 385 | 28 → 28 → 28 | 390 | Rechazado |
| 2026102702 (continuación) | 1045 | 385 | 28 → 23 → 23 | 388 | Rechazado |
| 2026102602 (continuación) | 1122 | 408 | 3 → 3 → 3 | 243 | Rechazado |
| 2026102602 (continuación) | 1122 | 408 | 3 → 3 → 3 | 238 | Rechazado |
| 2026102702 (continuación) | 1045 | 385 | 23 → 16 → 16 | 379 | Rechazado |
| 2026102703 (continuación) | 1062 | 390 | 910 → 37 → 37 | 331 | Rechazado |
| 2026102708 | 827 | 296 | 812 → 53 → 53 | 306 | Rechazado |
| 2026102709 | 874 | 327 | 1248 → 698 → 698 | 361 | Rechazado |
| 2026102710 | 1349 | 490 | 1615 → 1589 → 1589 | 466 | Rechazado |
| 2026102704 | 1035 | 380 | 1208 → 1208 → — | — | Parcial sin admisión |

Los cruces iniciales de una semilla nueva corresponden a su primera reconstrucción después de la búsqueda por proxies. Los de una continuación corresponden a la postura preservada, no al árbol sin ajustes. Un parcial no tiene admisión ni se suma al total aunque conserve un mejor checkpoint.

Para todos los intentos con auditoría final se volvió a comprobar la igualdad de la firma anatómica entre original y resultado. Las admisiones se contrastaron con los cuatro informes independientes, no sólo con el estado escrito por el controlador. Fuentes actuales y versiones archivadas verificadas por hash.

**No se alcanzó una nueva admisión física.** La automatización y las regresiones no deben presentarse como una solución general del problema. Los rechazos muestran que el algoritmo, con estos presupuestos y restricciones, no completó la separación de órganos. No demuestran imposibilidad geométrica de los árboles.

## Muestras y artefactos

[Galería local por semilla](../../outputs/nodal_controller_automation_20261027/review_gallery.html), [resumen por intento](../../outputs/nodal_controller_automation_20261027/review_summary.json) y [manifiesto de archivos](../../outputs/nodal_controller_automation_20261027/review_manifest.json).

Cada carpeta conserva original, mejor postura, ajustes, fuentes identificadas, auditorías y, cuando terminó a tiempo, imagen. Las imágenes de rechazo se llaman `rejected_preview.png` y se presentan separadas de las admisiones. No son ejemplos aptos para entrenamiento.

![Convergencia por reconstrucciones, no por tiempo](../../outputs/nodal_controller_automation_20261027/convergence.png)

## Observaciones y próximos pasos

Observado: la tercera candidata redujo sus 16 cruces preservados a 3, y el reparto temporal corto resultó insuficiente para completar los dos primeros árboles nuevos. Los estados provisionales que aumentaron contactos no reemplazaron la mejor reconstrucción. Los límites angulares son hipótesis de ingeniería; una imagen sin cruces no valida por sí sola su postura botánica.

Se incorporó y probó la coordinación de dos y cuatro entrenudos. Su prueba de reconstrucción no demuestra convergencia general ni plausibilidad botánica. Como hipótesis posteriores quedan ampliar la coordinación cuando persistan bloqueos, distribuir cómputo según categoría y progreso, e incorporar evitación de contactos durante el desarrollo progresivo conservando la carga completa. Requieren pruebas nuevas; no se presentan como resultados ya obtenidos.

La revisión de copa, postura y apariencia debe preceder a cualquier nuevo piloto. El suelo plano, el fondo diagnóstico y la escala visual de estas muestras no equivalen a escenas reales de entrenamiento. No hay evidencia nueva sobre eficacia de iluminación o texturas para el detector.

## Validación y continuidad

Diecisiete pruebas puras del controlador, búsqueda acotada y cadenas, y siete pruebas distintas en Blender, pasaron; las dos regresiones anteriores conservaron sus auditorías. Las modificaciones de reparto temporal preservaron las fuentes de cada intento. El validador del grafo mantiene los diez errores preexistentes de localizadores, separados de cualquier regresión mediante comparación con el grafo archivado. No se alteraron las campañas cerradas.
