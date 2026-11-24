# Tercera candidata: diagnóstico y admisión reproductiva — 28/10/2026

**Semilla 2026102602 admitida en la auditoría física estática: 0 cruces, 1122 hojas y 405 frutos/capachos.** Se omiten 3 unidades completas (0.735 % de los frutos originales), ninguna hoja. No se prueban otras semillas ni se inicia entrenamiento. Revisión visual humana pendiente.

## Por qué persistían los tres contactos

Una reconstrucción nueva del árbol preservado reprodujo los tres cruces:

- Un capacho cruza su propio tallo en el nodo 9 del eje principal.
- Dos parejas de capachos se cruzan en los nodos 1–2 y 3–4 de un ramal de orden 3.

La asignación de cohortes propone cálices completos sin admisión espacial. El generador reduce los entrenudos por orden, edad y vigor, mientras el pedicelo y el capacho se muestrean por otras reglas. En ese ramal los entrenudos nominales son de 1,33–1,84 cm, los pedicelos de 1,07–1,48 cm y los capachos de 3,85–5,90 cm de largo. Son valores del modelo, no medidas de campo. Las proporciones no prueban una intersección; ésta se confirmó separadamente en las mallas evaluadas.

La búsqueda angular de longitud fija dejó estos tres conflictos dentro de sus límites y presupuesto. No se ha demostrado que sea imposible conservar los 408 frutos con otra geometría o una búsqueda diferente.

## Corrección antes de construir la geometría

Se añade una admisión explícita y optativa en la gramática. Recibe conflictos verificados, ligados por hash a la anatomía original y a la evidencia. Un solucionador puro busca el conjunto mínimo de unidades que cubre esos contactos, preservando los índices nodales bajos al desempatar. El 1 % es un techo de reducción permitido para esta revisión; no impone una carga reproductiva ni una cuota global a las plantas.

La semilla se regenera con los parámetros originales: primero se verificó que recupera exactamente la anatomía anterior. Antes de materializar la geometría se omiten estas unidades propuestas:

- `axis_0_0_branch_11_branch_0_branch_1_node_2_reproductive_unit`
- `axis_0_0_branch_11_branch_0_branch_1_node_4_reproductive_unit`
- `axis_0_0_node_9_reproductive_unit`

Se omite cada unidad completa —pedicelo, fruto y capacho— en el árbol, manteniendo nodo, hoja y estructura de la rama. La yema queda sin unidad reproductiva aceptada, con procedencia explícita. Es una decisión de ingeniería, no una simulación ni una medición de aborto floral. No se borran objetos Blender ni fragmentos de anotaciones.

La cámara, luz, materiales y clases visuales de los órganos retenidos se conservan respecto de la vista anterior. Las posturas se reproducen desde el mejor árbol preservado. El plan procede de esa postura auditada: es una regeneración asistida por realimentación, no un modelo autónomo que garantice plantas sin contactos desde cualquier semilla. La generación histórica sin plan conserva su comportamiento.

## Verificación independiente

| Comprobación | Resultado |
|---|---|
| Cruces duros auditados, antes → después | 3 → 0 |
| Hojas | 1122 → 1122 |
| Frutos/capachos | 408 → 405 |
| Flores | 56 → 56 |
| Ejes / nodos | 154 / 1122, conservados |
| Objetos retenidos con vértices mundiales y caras orientadas idénticos | 5969 |
| Objetos de las unidades omitidas | 9, ausentes en la reconstrucción |
| Suelo plano, margen requerido 1 mm | valid |
| Orientación colgante y unión proximal | valid, 405 capachos |
| Errores de morfología | 0 |
| Advertencias de proximidad | 234 |
| Intersecciones hoja–hoja de ocupación blanda | 208 |

Se verifica la identidad de las 405 instancias de cáliz y de los 405 frutos, incluidos los ocultos. Los IDs omitidos no permanecen en RGB ni en los objetos anotables. La comparación canónica conserva exactamente coordenadas y caras orientadas, sin redondeo ni tolerancia; no exige el mismo orden interno de índices de bmesh. El primer intento de comparación por índices se preservó tras detectar ese reordenamiento. Dos fixtures de Blender verifican que se ignoran sólo las permutaciones, que se detecta un desplazamiento de 1e-10 y que se conserva la orientación de las caras. No se generó un banco de entrenamiento ni se exportó una nueva partición YOLO.

La admisión conserva el alcance anterior: hoja–hoja se tolera como ocupación blanda y la proximidad es advertencia. No certifica todas las flores ni el contexto, terreno irregular, mecánica o plausibilidad botánica. Cero cruces auditados tampoco demuestra realismo fotográfico o utilidad para el detector.

## Muestras

Antes, rechazado por tres cruces:

![Antes](../../outputs/nodal_controller_automation_20261027/plants/seed_2026102602_retry03/rejected_preview.png)

Después, misma cámara y órganos retenidos idénticos:

![Después](../../outputs/third_candidate_generation_fix_20261028/passed_fixed_camera.png)

## Pruebas y continuidad

Pasaron nueve pruebas nuevas de admisión pura: cobertura mínima, contactos compartidos, límites de reducción, evidencia e identidades inválidas, alteración del plan, conservación reversible de la anatomía, serialización y ruta explícita de la gramática. Pasaron también las catorce regresiones puras de repulsión nodal. La prueba integral en Blender reconstruyó el antes y el después, comparó todos los órganos retenidos y ejecutó las auditorías de malla, suelo, orientación y morfología.

Se conservan las fuentes de entrada y de esta revisión, el plan, la evidencia y los árboles. Los resultados anteriores cerrados permanecen intactos. La validación del grafo mantiene los diez errores preexistentes de localizadores; la comparación con el grafo archivado separa regresiones nuevas.

Para una próxima revisión del modelo conviene contrastar espacio nodal, pedicelo y crecimiento del capacho de forma conjunta antes de fijar el volumen adulto. Aquí se demuestra sólo la admisión de esta candidata con una reducción acotada; no una tasa de éxito para otras plantas. El siguiente ensayo permanece pendiente de mostrar y revisar este arbusto.
