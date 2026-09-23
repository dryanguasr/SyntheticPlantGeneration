# Curación de nuevas capturas reales — 22 de septiembre de 2026

Estado actualizado y ejemplos: [informe para continuar desde Chat](nuevas_imagenes_revision_chat_2026-09-23.md). Las secciones siguientes conservan el historial de cada versión.

## Resultado ejecutado

Entrega para revisión: `outputs/new_real_dataset/captura_20260912_v2/index.html`.
Estado **provisional**. No se entrenó ningún modelo ni se generaron etiquetas.
Los originales y el dataset histórico permanecen separados e intactos.

El inventario final contiene 667 fotografías, 26 videos (58,003 minutos estimados)
y un DOCX de referencia. La extracción terminó sin incidencias registradas de
lectura/decodificación. Se conservaron 7.615 candidatos, de los cuales 6.438 se
propusieron para etiquetado y 1.177 quedaron en reserva recuperable.

| Partición | Imágenes propuestas | Porcentaje | Grupos propuestos |
|---|---:|---:|---:|
| Train | 4.501 | 69,91 % | 17 |
| Val | 976 | 15,16 % | 10 |
| Test | 961 | 14,93 % | 10 |
| Total | 6.438 | 100 % | 37 |

La selección contiene 665 fotografías y 5.773 frames. El número de imágenes no
equivale al número de observaciones independientes; las escenas de un mismo
video permanecen juntas. Estos 37 grupos aún requieren confirmar límites de
área/planta y relaciones entre dispositivos.

## Procedimiento y trazabilidad

Se usaron las bibliotecas ya disponibles, sin instalar dependencias. La primera
ejecución técnica se conserva como `captura_20260912_v1`; la entrega v2 reutiliza
sus candidatos inmutables, selecciona representantes por semejanza directa,
reserva sondeos intermedios sin cambio suficiente a resolución reducida y añade
correcciones/propuestas visuales. No se eliminó material de reserva.

El sondeo adicional usa reducción por promedio de área para evitar aliasing de
texturas finas. La reserva adicional conserva los candidatos sobremuestreados
de la primera pasada; no se presentan como descartes por mala calidad.

La revisión visual exploratoria inspeccionó fotogramas al 10/50/90 % de cada
video, una muestra de fotos por dispositivo y muestras de la exportación.
Se registró una corrección adicional de 270 grados horarios en cinco clips
Snapchat: sus metadatos dejaban el paisaje de lado. Una de esas copias quedó
completamente en reserva; se verificó visualmente la orientación de ejemplos
exportados de las cuatro fuentes seleccionadas restantes.

Se propusieron relaciones conservadoras entre cuatro videos tardíos de detalle
y entre dos clips DJI consecutivos con posibles plantas compartidas. Estas
observaciones **no son validación humana de independencia**. Su evidencia y
alcance están en `visual_observations.json` y `source_review.csv`.

La auditoría perceptual produjo 2.459 pares: 2.366 proceden de la misma fuente,
17 son coincidencias exactas y 76 son relaciones entre fuentes pendientes de
revisión. Los pares pendientes ya fuerzan agrupación conservadora; no se
distribuyen sus extremos entre splits. La ausencia de otros pares detectados
no demuestra ausencia de filtraciones semánticas por plantas repetidas.

Cada imagen conserva identificador, fuente y hash de origen, frame/tiempo de
decodificador cuando aplica, resolución, giro adicional, grupo y split. La
entrega incluye manifiestos CSV/JSONL, galerías, reservas, tablas de revisión y
un informe de cobertura. `parent_version.json` conserva procedencia y hash del
código usado para preparar la v2.

## Verificaciones realizadas y pendientes

- Verificación de integridad aprobada sobre las 6.438 imágenes exportadas:
  hashes, dimensiones, correspondencia con la selección y ausencia de cruces
  entre splits para grupos propuestos y coincidencias exactas conocidas.
- Once pruebas de curación aprobadas, incluyendo video con tasa variable,
  orientación, recomprensión, cambios de origen, continuidad temporal, revisión,
  exportación reanudable, bloqueo de congelación e integridad de metadatos.
- Cuatro pruebas del grafo de contexto aprobadas; validador del grafo aprobado.
- Escalas, calidad y grupos siguen pendientes. Los ceros de presencia revisada
  por escala no significan ausencia de capachos pequeños en las imágenes.

La entrega no está congelada ni habilitada para entrenamiento. Primero deben
revisarse las relaciones entre fuentes y las escalas, recuperar reservas útiles
y confirmar cobertura en cada split por número de grupos independientes. Si
faltan planos lejanos identificables, corresponde una nueva captura; duplicar
imágenes o confiar en detecciones del modelo anterior no resuelve esa ausencia.

Los estudiantes pueden comenzar por las galerías y tablas de revisión siguiendo
el [protocolo de uso](../guides/nuevo_dataset_real.md). Los cambios deben realizarse
en una versión nueva con `fork-review`, preservando esta entrega.

## Continuidad

Si el tiempo lo permite, evaluar integración con el histórico en un experimento
posterior, con auditoría de coincidencias y métricas separadas por dominio y
tamaño de instancia. No se mezclaron conjuntos en esta tarea. La nueva captura
corresponde a una sola jornada; no prueba generalización entre fechas o fincas.


## Revisión v3: exclusión de flexómetros

Por solicitud del usuario se excluyeron 13 fotografías con flexómetro visible,
identificadas mediante revisión visual del asistente. Se revisaron las 667
fotografías en hojas de contacto y se ampliaron los casos dudosos. En videos
se inspeccionaron 1092 candidatos muestreados aproximadamente cada tres segundos;
no se encontraron casos en ese muestreo, que no equivale a una revisión exhaustiva.

La entrega `outputs/new_real_dataset/captura_20260912_v3` conserva 6425 imágenes:
4490 train, 976 val y 959 test. Ninguna imagen conservada cambia de split.
Los originales y la entrega v2 permanecen intactos. `exclusion_audit.json`
registra los 13 identificadores y orígenes; los manifiestos conservan las
exclusiones, que ya no aparecen en la galería ni en las carpetas de entrega.
`preserved_splits.json` mantiene la asignación por grupos y queda protegido
por las firmas de exportación. Continúan pendientes las revisiones científicas
de grupos, calidad y escalas de v2; la entrega sigue siendo provisional.


## Revisión v4: reducir redundancia entre frames

La entrega `captura_20260912_v4` conserva 5004 imágenes: 4352 frames de video y las 652 fotografías seleccionadas de v3. Pasaron a reserva recuperable 1421 de los 5773 frames previamente seleccionados (24,6 %). Distribución: train 3480, val 741 y test 783. Todos los orígenes de video antes representados permanecen representados y ninguna imagen conservada cambia de split. Las 13 exclusiones por flexómetro permanecen excluidas.

Se compararon correspondencias ORB y transformaciones de escala/rotación/traslación con hasta tres representantes recientes del mismo video. Cada reserva tiene un representante directo conservado. No se usó una separación temporal fija, un detector ni un umbral absoluto de nitidez. Los umbrales geométricos y fotométricos son heurísticos; no equivalen a una garantía de diversidad de objetos. `redundancy_audit.json` conserva parámetros y decisiones; `redundancy_pairs.csv` permite recuperar los casos.

El asistente revisó visualmente 28 pares, cubriendo un caso por video con reservas y seis casos de solapamiento próximo al límite. Fue una muestra, no una revisión exhaustiva. La prueba pequeña conserva cambios grandes de zoom y escenas diferentes mientras identifica un desplazamiento leve. Continúa pendiente la revisión humana de escalas y grupos.

`images/` entrega resolución original y `images_640x640/` contiene las mismas imágenes seleccionadas en PNG de 640 × 640, reutilizando exactamente los bytes de v3. La galería principal ahora muestra solo la selección; las reservas permanecen en los manifiestos y candidatos.


## Revisión v5: presupuesto de 2400 imágenes

A solicitud del usuario, `captura_20260912_v5` reduce la entrega a 2400 imágenes: 1680 train, 360 val, 360 test. Conserva las 652 fotografías y 1748 frames, con los mismos splits y todos los orígenes previamente representados. Los 2604 frames adicionales retirados permanecen como reservas. `budget_selection.json` registra cuotas por origen y la selección determinista. Las cuotas proporcionales dentro de cada split se basan en los frames de v4; dentro de cada video se prioriza distancia visual respecto a los representantes ya seleccionados. No se utilizó un detector ni resultados del test.

La reducción por presupuesto no garantiza cobertura de escalas de capachos: se mantienen pendientes la revisión humana de grupos y escalas y el carácter provisional. Las imágenes originales y las PNG de 640 × 640 se entregan en carpetas paralelas, conservando las versiones previas.


## Revisión v6: selección visual sin presupuesto

Ante la redundancia restante, el asistente revisó las 2400 imágenes de v5 en hojas de contacto, incluyendo fotografías y frames. La primera pasada dejó 606 representantes; una segunda revisión visual dejó 496. Se ampliaron los 36 pares consecutivos más próximos según un descriptor de apariencia (sin componente temporal) y se retiraron otros ocho representantes redundantes. Se comprobaron visualmente las ocho nuevas adyacencias. El descriptor solo priorizó la revisión; no decidió un umbral automático de descarte.

La entrega `captura_20260912_v6` conserva **488 imágenes**: 337 train, 73 val y 78 test; 360 frames y 128 fotografías. No se aplicaron cuotas por video ni meta numérica. Se priorizaron cambios de encuadre, distancia aparente, perspectiva, iluminación y oclusión; se reservaron ráfagas y tomas con escasa aportación visual adicional. Los 1912 elementos retirados de v5 siguen disponibles como reservas recuperables. Todos los grupos propuestos y orígenes de video presentes en v5 siguen representados; cada imagen conserva su split. Las exclusiones anteriores, incluidos flexómetros, siguen vigentes.

La selección exacta y el hash del manifiesto padre se versionan en [el registro de revisión](../reviews/real_dataset_visual_selection_2026-09-22.json). `visual_selection_review.json` y `diversity_validation.json` acompañan la entrega. Los registros ORB y de presupuesto copiados corresponden a etapas anteriores, no al criterio final de v6. Se entregan originales orientados en `images/` y las mismas imágenes en PNG 640 × 640 con relleno en `images_640x640/`.

La revisión se realizó sobre miniaturas y ampliaciones de estas, no sobre cada original a resolución completa. Es una curación visual del asistente, no validación humana de escalas o grupos. Conservar planos generales no demuestra por sí solo cobertura suficiente de capachos pequeños. La entrega continúa provisional; deben revisarse escalas y relaciones entre capturas antes de congelarla. No se usaron resultados del detector ni se modificaron las versiones previas.

La validación v6 aprobó hashes, dimensiones/orientación, correspondencia de los 488 originales y 488 PNG con sus manifiestos, preservación de los 37 grupos propuestos y 23 videos representados y ausencia de cambios de split. No hay grupos propuestos ni duplicados exactos conocidos cruzados. El grafo de contexto también fue validado. Estas verificaciones estructurales no resuelven las relaciones visuales aún pendientes entre capturas.
