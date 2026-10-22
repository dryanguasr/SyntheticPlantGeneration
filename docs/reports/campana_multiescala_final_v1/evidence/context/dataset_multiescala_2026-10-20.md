# Dataset multiescala — 20 de octubre de 2026

El usuario autoriza retomar desde la generación de datos con tomas cercanas, intermedias y lejanas y distintos ángulos, manteniendo los arbustos, evitando fugas y usando aumentación nativa de Ultralytics. La campaña de vuelos de hilera cancelada permanece cancelada; no se reanuda su órbita ni su cola PiP.

Raíz nueva: `outputs/multiscale_dataset_20261020`. Se reutilizan sin modificar los JSON V181 aprobados, intérprete y materiales congelados de `frozen_field_pilot_20261019`. El entorno conserva suelo, cielo, vecinos, soportes y marcador. Solo cambia la cámara. El generador congelado sigue identificado por su manifiesto SHA256; la campaña nueva tiene su propio manifiesto. No se realizan barridos de colisiones ni refinamientos de plantas.

## Capturas y controles

384 imágenes de 1280×720: 192 train, 96 validación, 96 prueba de desarrollo. Cada planta recibe 48 poses: distancias de 1,2/2,2/3,6 metros al punto de mira, ocho azimuts y dos elevaciones (0/18 grados). Estas distancias son heurísticas de ingeniería; no distancias medidas a la superficie del follaje. Se comprueba que la cámara no esté en las cajas expandidas de las mallas de las plantas, sin modificar geometría; cualquier ajuste angular determinista se registra por captura. No es una certificación de vuelo físico.

Tres primeras capturas train revisadas visualmente y verificadas: máscaras raster, paleta, clases, IDs, hashes y ausencia de ediciones geométricas. Capachos objetivo visibles: 68/72/22; elegibles por el criterio 100 píxeles y lado8: 56/50/4. Mediana de área visible: 936,5/209/26 píxeles. La vista lejana incluye un vecino delante del objetivo; es un caso difícil válido, no evidencia de que todos los objetos lejanos sean segmentables. El área visible no es una tasa de oclusión. Estos datos no constituyen todavía una auditoría del dataset completo.

El exportador conserva negativos vacíos y todas las máscaras originales. Recortes de entrenamiento/validación de640×640, stride448, desde la imagen completa, sin ROI basada en verdad ni selección HSV. Hasta1600 recortes train; entrada960. Evaluación posterior sobre las mismas imágenes completas para modelo anterior y nuevo; confianza0,25 e IoU0,5. Reportar todos los casos y los de tamaño elegible por distancia, clase y partición. No ocultar objetos pequeños para inflar la métrica. El criterio100px/lado8 es de ingeniería, no un límite universalYOLO.

## Separación y linaje

- Train: C01–C04, semillas814200–814203.
- Validación: C06–C07, semillas814205–814206.
- Prueba de desarrollo: C09–C10, semillas814208–814209.

Vecinos clonados, todas las vistas, recortes y aumentaciones heredan la partición del JSON fuente. Auditar disjunción de SHA256, semillas, imágenes y procedencia de recortes. No incorporar imágenes de la campaña cancelada que mezcla plantas de validación y prueba. Semillas reservadas914140–914145 intactas.

Las ocho plantas comparten un grafo de89ejes. La disjunción es por instancia/semilla/escena, no por familia topológica. La prueba ya fue inspeccionada históricamente: nuevas vistas no la convierten en holdout externo. No ajustar configuración ni selección con sus resultados.

Inicialización prevista: peso final del piloto congelado, SHA256 `79c3dad74e7cf9caab3c82a3e37ea72235352568d7dfacbd5c9e8284cb190073`. Auditoría del linaje V161→V177→V184→V186→V192→final no encontró backprop con las plantas actuales de validación/prueba; sí existe dependencia histórica de decisiones de desarrollo. Conservar esa limitación y todos los resultados negativos.

## Aumentación nativa y entrenamiento

El cargador anterior hacía reflejo/brillo manuales e ignoraba los parámetros nativos de aumentación. Nuevo adaptador `scripts/multiscale_native_augmentation.py`: llama realmente RandomHSV y RandomFlip de Ultralytics8.4.114, con imagen, cajas y raster de IDs sincronizados. Se preservan componentes desconectados y huecos; ninguna conversión a polígonos. Seis pruebas CPU verifican llamadas nativas, alineación, reproducibilidad, negativos y ausencia de aumentación en validación.

Configuración inicial: hsv_h=0, hsv_s=0, hsv_v=0,1, fliplr=0,5. Se evitan cambios de tono que alteren la clase de apariencia del capacho. Mosaic/mixup/copy-paste y afines deshabilitados en este primer piloto de raster exacto. La diversidad física de escala y ángulo procede de nuevas capturas, no de ampliaciones ni deformaciones. Los reflejos pueden invertir el ArUco: se usan solo para reconocimiento de capachos, nunca para poses/localización.

Entrenamiento de10épocas únicamente tras controles completos y `training_readiness.json` aprobado con hashes del protocolo, manifiestos raster y parches, comprobación de aumentación e inicialización. Batch1,nbs1,warmup0,AdamW0,0002,workers0,cacheFalse,plotsFalse; verificar pasos reales y cambios de parámetros, validación batch1. Máximo un trabajo GPU, admisión6,5GiB y parada3GiB para mantener reserva2GiB. No iniciar entrenamiento durante renders. Después comparar modelo anterior y nuevo sobre vistas completas, con métricas por escala y ejemplos representativos; no volver al refinamiento de plantas.

## Continuidad

`dataset_queue.py` ejecuta bloques de12 capturas, valida cada escena, exporta raster y prepara recortes; termina en auditoría previa al entrenamiento. El heartbeat debe continuar las etapas listas y no repetir controles completos ni relanzar procesos existentes. Preparar vuelos posteriores solo después de evaluar el nuevo modelo, sin reabrir la campaña cancelada automáticamente.

El validador de `repository_context_graph.json` se ejecutó y detectó10 referencias textuales rotas en documentos de gobernanza/guías preexistentes. No se modificaron esos documentos ni se declaró que esa validación pasara. No es un fallo de las máscaras o de esta generación.

## Avance verificado — 21 de octubre, 07:12 UTC

La generación y exportación finalizaron: 384 vistas completas (192 train, 96 val, 96 prueba de desarrollo), 71.098 observaciones de capachos y 1.728 recortes de640×640 (1.152 train y576 val). No hay vistas ni recortes completamente vacíos; no se excluyeron negativos, pero esta muestra carece de negativos de imagen completa. No confundir fondo dentro de las imágenes con ejemplos negativos completos.

`split_integrity_audit_v1.json` pasó868.156 comprobaciones: fuentes/semillas y clones separados, cero duplicados entre particiones por archivo o contenido de píxeles y equivalencia exacta de cada recorte RGB/máscara con su original. `current_dataset_loader_check_v1.json` verificó12 muestras nuevas por distancia/partición/extremos de densidad, clases, cajas y llamadas reales a aumentación nativa. El validador reducido puede perder máscaras de algunos objetos diminutos; ninguno de los elegibles comprobados desapareció. Las métricas finales deben usar los raster originales.

Se revisaron visualmente18 vistas completas train/val, elegidas por fracción baja/mediana/alta de capachos objetivo elegibles, con sus máscaras y vecinos. Galería: `outputs/multiscale_dataset_20261020/scale_review_v1/index.html`. Mediana del área objetivo train:564,5/182/70 píxeles en cerca/intermedio/lejos; cobertura del criterio100px/lado8:81,0%/65,4%/37,2%. En val:80,1%/64,4%/33,8%. Es descripción del tamaño visible, no porcentaje de oclusión ni rendimiento del detector. No se ajustaron configuraciones con prueba. Se conservan casos difíciles donde un vecino de primer plano oculta al objetivo.

`training_readiness.json` quedó aprobado con hashes del protocolo, manifiestos, comprobación nativa y peso inicial. `train_stage_v1.py` inició el entrenamiento a07:10 UTC con proceso real21720 y controlador42176 (identidades comprobadas; estos PID son evidencia puntual, no prueba futura de ejecución). Primera lectura:86 lotes y82 pasos reales del optimizador,14,68GiB libres; las diferencias de parámetros se registrarán al cerrar cada época. Configuración real:10 épocas, batch1, nbs1, warmup0, AdamW0,0002, workers0 y cuatro hilos. El CLI del entrenador no acepta --workers; el valor0 está fijado dentro del código comprobado. El controlador conserva fuentes y limita RAM también en validación. El heartbeat horario se actualizó para no repetir generación ni auditorías, comprobar avances reales y continuar a evaluación de vistas completas.

La topología D compartida, la prueba históricamente inspeccionada, la ausencia de negativos completos y la apariencia sintética aproximada siguen siendo limitaciones. Las clases continúan describiendo capachos, no madurez interna. No se cambió ninguna planta ni se reanudó la campaña de vuelos cancelada.

Comparación posterior preparada en `evaluate_multiscale_v1.py`, `evaluation_protocol_v1.json` y `evaluation_readiness_v1.json`: ambos pesos se evaluarán con la misma inferencia exhaustiva640/stride448/entrada960 en192 vistas completas val/test, sin ROI de verdad ni selección HSV. La referencia histórica utilizaba384/stride256 y ROI RGB; las nuevas cifras compararán pesos dentro del mismo procesamiento actual y no replicarán las cifras históricas de extremo a extremo. Cada predicción se guarda por vista con hashes de RGB, pesos y configuración para reanudar sin repetir vistas terminadas. Se producen matrices todos/elegibles por distancia/partición, P/R/F1 a umbral fijo y18 ejemplos completos predeclarados. Pruebas CPU de emparejamiento, NMS, caché/corrupción y reporte con datos ficticios pasaron; no son resultados del detector. El controlador solo inicia esta evaluación tras comprobar entrenamiento completo y su puerta de integridad.

## Entrenamiento y evaluación terminados — 21 de octubre, 10:01 UTC

Diez épocas completas,11.520 lotes y11.513 pasos reales del optimizador; cambios de parámetros registrados en todas las épocas. RAM mínima observada14,10GiB en entrenamiento y14,03GiB en validación; el trabajo terminó sin error. Peso final SHA256 `9c660824319f2c436321d2545cf9b267348c7be64d7780a396d8382555eb05cd`.

La comparación terminó en192 vistas completas por modelo(96val+96prueba). `evaluation_delivery_audit_v1.json` verificó todos los cachés, hashes y768 recomputaciones del emparejamiento con máscaras nativas; coincidieron matrices y métricas. Las cuatro matrices y18 comparaciones de vistas completas se conservan en `native_evaluation_v1/comparison.html`. Se revisaron visualmente los ejemplos de validación000/049/095(cerca/intermedio/lejos), junto con ambas matrices de prueba para comunicar resultados, sin cambiar decisiones ni umbrales.

| Prueba de desarrollo | Referencia | Nuevo |
|---|---:|---:|
| Precisión global |67,83%|75,56%|
| Recuperación global |41,30%|49,57%|
| F1 global |51,34%|59,86%|
| F1 cerca |52,08%|64,86%|
| F1 intermedio |56,13%|62,13%|
| F1 lejos |46,86%|54,73%|
| F1 solo elegibles |68,38%|76,98%|

En validación, F1 global52,29→60,42% y F1 cerca52,52→65,53%. Los elegibles abarcan solo38,99% de las instancias visibles de prueba; su F1 condicional no sustituye el59,86% global. Resultados negativos: precisión lejos/elegibles baja2,39 puntos en validación y1,03 en prueba; pintona→madura baja838→538, pero madura→pintona sube172→297. La recuperación global49,57% aún es insuficiente para afirmar reconocimiento completo. Cerca mejora claramente, pero persisten omisiones de objetos pequeños y parcialmente tapados. El área visible no es una tasa de oclusión.

`detector_review_v1.json` aprueba la entrega técnica y permite preparar un vuelo diagnóstico nuevo y corto, sin promoción científica ni de producción. No reabrir las rutas canceladas ni modificar plantas/entorno. Mantener el modelo anterior para comparación y las reglas congeladas. La siguiente comprobación debe ser continuidad temporal, máscaras/identidades, aislamiento público/verdad y marcador realmente decodificado antes de ampliar vuelos.


## Vuelo diagnóstico nuevo de ocho fotogramas — 21 de octubre

Nueva raíz `outputs/multiscale_flights_20261021`, sin reabrir la campaña cancelada. Se renderizaron ocho fotogramas continuos a 4 fps, 8,75 cm de recorrido lateral sobre C06 con C07 y cuatro vecinos intactos. La construcción de escena se conservó literalmente; el adaptador solo cambia cámara y tiempos. El despeje conservador del segmento pasó antes del render. Tiempo de render 148,33 s, RAM libre mínima 11,56 GiB. No es una campaña de vuelo completa: el primer y último fotograma están separados por 1,75 s.

`smoke_validation_v1.json` verifica máscaras originales, paleta, clases, IDs estables, hashes y continuidad: 6.584 controles de píxeles y otros tantos de cajas. ArUco 8 realmente decodificado en 8/8 vistas: lado codificado 20 cm, marco 26,67 cm, sin cambios. Existe un único marcador común; C07 no tiene adquisición independiente. La primera aserción del validador asumía RGB; las máscaras originales son RGBA con alfa255. Se corrigió solo esa aserción y se conservó el intento fallido, sin alterar imágenes.

El paquete público contiene únicamente ocho RGB, tiempos, intrínsecos y dimensiones físicas del marcador. La inferencia nueva usa el peso multiescala y exactamente el mismo procesamiento640/448/960, sin máscaras ni poses verdaderas. Sus cachés se verificaron antes del seguimiento CPU con MaskTracker congelado. No se repitió inferencia para evaluar ni para asociar identidades.

En esta muestra, incluyendo vecinos, P/R/F1 global = 73,62/46,07/56,67%; elegibles = 64,33/87,76/74,24%. Hay 711 observaciones elegibles de 2.544 visibles; los conteos incluyen la misma instancia en varios fotogramas. Las dos matrices están en `flights/smoke_C06/evaluation_private_v1`. La evaluación verificó orden, cajas, clases, confidencias y hashes de cada predicción contra las observaciones del tracker. No se calculó precisión exclusiva de C06.

Resultado negativo de seguimiento: 162 cambios de ID entre 1.019 pares de la misma instancia emparejada por máscara IoU>=0,5 en fotogramas adyacentes, sin exigir igualdad de clase. Solo 47,73% de los 2.135 pares conjuntamente visibles tuvieron emparejamiento en ambos fotogramas. En elegibles, 33 cambios entre 556 pares. No son IDF1/HOTA/MOTA, y la tasa condicional no incluye reidentificación tras omisiones. Se conservan 1.258 omisiones espaciales y 114 confusiones de clase en la matriz global.

Se inspeccionaron las vistas completas superpuestas0/7 y la matriz global; el agente evaluador inspeccionó ambas matrices. El detector mejora frente al anterior, pero el seguimiento aún fragmenta identidades. No hay localización3D ni videos finales PiP nuevos, ni promoción científica. Siguiente paso acotado: diagnosticar las asociaciones guardadas y realizar un único replay CPU instrumentado, con parámetros idénticos y comprobación de IDs sin cambios; después preparar rutas nuevas. No hacer barridos ni retocar plantas para resolver este fallo.

`tracking_failure_diagnosis_v1.json` conserva el diagnóstico de asociaciones sin reinferencia: 32 de los 33 cambios elegibles coinciden con rechazos `competing_tracks`, y el restante con `ambiguous_box_match`. No hay duplicados fuertes en 157.854 pares de máscaras, aunque aparece una silueta partida en la costura x=640. Un capacho cambia91→221→265→312→358→432→469 conservando clase pintona y máscaras consecutivas IoU0,764–0,941. La retención2s supera la duración1,75s del clip y ningún track puede caducar; la competencia de candidatos antiguos es una hipótesis pendiente de instrumentación, no una causa demostrada. El siguiente experimento está predeclarado y aún no ejecutado: una única reproducción CPU con scores, manteniendo exactamente IDs y parámetros. El heartbeat horario quedó actualizado para continuar desde este punto sin repetir el entrenamiento ni la inferencia, y sin convertir el diagnóstico en barridos indefinidos.


## Reproduccion instrumentada y tres fragmentos nuevos - 21 de octubre, 11:05 UTC

Se completo una unica reproduccion CPU de las ocho predicciones existentes: 44,20 s, minimo libre16,94GiB, ocho trazas, IDs y rechazos exactamente iguales al baseline. No hubo reinferencia ni cambios de parametros. El recibo `validation_only_competitor_trace_v1/completion.json` verifica equivalencia; su resumen privado tiene SHA256 `b8478e66683c002c909754cb4f88134689f77a48e1d148dda4756db2e33bd432`.

En27de32 cambios elegibles por competencia, el ID previo propuso la deteccion correcta y compitio con IDs antiguos no vistos en el fotograma anterior; en5de32 competian IDs recientes. Ninguno de esos32 IDs anteriores se habia desviado a otra deteccion. Ejemplo: track432 puntua0,9668 y compite con seis candidatos antiguos de0,5-1,5s. El rechazo por competencia esta registrado, sin afirmar que una correccion no ensayada lo resuelva. El cambio elegible restante procede de dos fragmentos en la costura x640: scores0,70582 y0,67677, margen0,02905 menor que0,08. Se preserva el resultado negativo; no se hicieron barridos ni variantes del tracker.

Se prepararon rutas nuevas en `multiscale_flights_20261021/route_pilot_v1`, con protocolo y hashes previos al render. Son tres fragmentos frontales de12fotogramas a4fps (videos3s; primer-ultimo2,75s): legacy lateral0,275m, vertical cercano0,60m y arco frontal30grados (~0,628m). Las tres comprobaciones conservadoras de despeje pasaron. No son cobertura completa de hilera ni ambos lados; C07 sigue sin marcador propio y no se finge su adquisicion. El controlador serial iniciado11:15UTC enlaza render, controles/exportacion publica, inferencia congelada640/448/960, seguimiento, evaluacion privada y PiP. El estado vivo esta en `route_pilot_v1/stage_state_v1.json`; un PID registrado no sustituye comprobar identidad y avance.

Antes de ejecutar se aclaro la politica objetivoC06: matching global primero; matches a vecinos ignorados; FP sin match se atribuyen aproximadamente por centroide dentro de la envolvente de mascaras visiblesC06, solo en evaluador. El subconjunto elegible no se rematchea. Este ajuste previo no usa resultados del vuelo. Protocolo SHA256 `9a9bf309e586335a3ff102a8685f4d42ffc2e4940443de14d7a707cf64e47842`. Se mantienen mascara nativa, umbrales, plantas, peso y marcador; la campaña cancelada permanece cerrada.


## Entrega de tres fragmentos nuevos — 21 de octubre, 11:43 UTC

La entrega acotada terminó: 36 fotogramas nuevos, inferencia pública congelada, seguimiento y evaluación privada; tres videos H264 a 4 fps con vista del dron, máscaras e IDs y recuadro externo sincronizado. Cada video dura 3 s (2,75 s entre primera y última muestra). Informe: `outputs/multiscale_flights_20261021/route_pilot_v1/comparison.html`. Incluye cuatro matrices por ruta, métricas globales y exclusivas de C06, y vistas completas 0/6/11 predeclaradas.

| Resultado exclusivo de C06 | Legacy | Vertical | Arco orbital |
|---|---:|---:|---:|
| Precisión | 76,80% | 62,41% | 66,86% |
| Recuperación | 58,44% | 65,02% | 64,52% |
| F1, todos los tamaños | 66,37% | 63,69% | 65,67% |
| F1, tamaño elegible | 67,42% | 68,83% | 70,92% |
| Cambios de ID / pares emparejados | 63/465 | 292/334 | 188/560 |
| Cobertura de pares consecutivos | 58,13% | 62,66% | 63,78% |
| ArUco realmente decodificado | 12/12 | 0/12 | 0/12 |

La evaluación global incluye vecinos: F1 49,75/59,08/58,85%. Su mejora en los acercamientos no demuestra mejora sobre C06. Los cambios de identidad son condicionales a emparejamientos espaciales en ambos fotogramas, no IDF1/HOTA/MOTA. El criterio elegible sigue siendo 100 píxeles visibles y lado mínimo 8 píxeles; no equivale a un límite universal de YOLO. La atribución aproximada de falsos positivos a C06 utiliza solo la envolvente privada del evaluador, nunca una ROI del estimador.

Se conserva un fallo demostrado de cámara: en vertical se elevaron cámara y punto de mira de 0,40 a 1,00 m sin variar la orientación horizontal. C06 pasó de 96 capachos visibles / 76.515 píxeles a 10 / 3.186, todos entre las filas 597–720 al final. El arbusto sale por debajo del encuadre; no atribuir este efecto al detector. La siguiente receta limitará el punto de mira a bandas de follaje reales y comprobará la proyección antes del render. No se regeneró ni cambió ninguna planta, y el fragmento negativo se conserva.

La auditoría aritmética independiente pasó 5.737 comprobaciones sin errores. Todos los trabajos guardados terminaron con código 0; RAM libre mínima 11,21 GiB. Los tres MP4 pasaron decodificación completa, H264/4 fps/12 fotogramas/3 s y vínculos de timestamps/hashes. Se inspeccionaron fotogramas PiP completos y matrices objetivo; no se afirma reproducción en navegador. El observador externo de legacy cortaba el proxy del dron: se corrigió únicamente su cámara en presentación v2, conservando v1 y sin repetir RGB, inferencia, seguimiento o métricas. El selector de entrega y el recibo visual vinculan explícitamente cada versión.

La revisión histórica de `audit_pose_reprojection_v1` quedó registrada sin reactivar la cola: faltaba `marker_id`; V2 reparó la interfaz, pero la fusión antigua obtuvo 0/32 reajustes y no acredita exactitud. Para reutilizar componentes, pasar lado codificado 0,20 m explícitamente, conservar `marker_id` y adaptar el ruido relativo a intervalos reales de 0,25 s; el exportador histórico asumía 0,5 s. Poses exactas y verdad permanecen privadas. No hay aún localización 3D en estas rutas.

Siguiente paso en `next_full_routes_plan_v2.json`: un único preflight conjunto de despeje, encuadre y continuidad para rutas completas nuevas por ambas caras, sin otra cadena de smokes. Legacy recorre ambos arbustos; vertical hace cuatro barridos completos; órbita solo cubre sectores despejados. Los centros están separados 1,8 m y un radio de 1,2 m pasa a 0,6 m del otro centro en el arco interior: no prometer 360° antes de comprobarlo ni mover plantas para hacerlo posible. Congelar coordenadas, fases y duraciones antes de renderizar. El marcador común no permite adquisición independiente de C07. La campaña sigue pendiente; los clips no son una hilera completa ni promoción científica.

## Rutas completas nuevas congeladas e iniciadas — 21 de octubre, 12:21 UTC

El único preflight conjunto terminó con éxito en 26,18 s y RAM libre mínima 15,28 GiB. Construyó una vez la escena aprobada, comprobó 9.886 obstáculos evaluados, intersecciones exactas de segmentos contra AABB ampliadas 20 cm, continuidad y encuadre por fase. El constructor literal mantiene SHA256 `6fbf1f73…`; no hubo cambios de plantas, suelo, cielo, vecinos, materiales ni marcador. El protocolo nuevo `full_routes_v1/protocol.json` quedó congelado con SHA256 `86dabc5a22a59aa53207547e565bd9408a05e3dac8c47df037d11aff71b78026`. La propuesta y los sectores bloqueados se conservan.

| Ruta | Fotogramas a 4 fps | Duración de video | Inspección | Tránsito |
|---|---:|---:|---:|---:|
| Legacy | 178 | 44,50 s | 10,00 s | 32,75 s |
| Vertical | 167 | 41,75 s | 8,50 s | 31,50 s |
| Órbita parcial | 282 | 70,50 s | 21,25 s | 47,50 s |

Cada ruta añade 1,75 s de adquisición/retorno al marcador común. Los presupuestos son diferentes; los resultados deben separar inspección de tránsito. Legacy conecta lateralmente ambos objetivos por delante y detrás, conservando límites completos proyectados de la planta. Vertical realiza cuatro barridos monótonos: C06 frente/reverso y C07 frente/reverso. El punto de mira de C06 recorre 0,162–0,641 m y el de C07 0,117–0,564 m, dentro del follaje real; la cámara comienza como mínimo a 0,25 m y se inclina hacia la banda baja. Se evita así el overshoot demostrado en el piloto sin alterar las plantas. Los centros de follaje proyectados al menos una vez cubren 99,78–100% por cara en vertical; esta proyección no garantiza visibilidad y no mide oclusión.

La órbita completa de 360° no pasó el criterio conservador: se conservan 180° transitables en C06 y 225° en C07. Postes, cuerdas y plantas vecinas bloquean el resto, incluyendo algunas columnas de acceso. Los trayectos llegan al reverso por un extremo exterior, con tránsito alto a 1,978 m cuando hace falta. No se retiraron obstáculos ni se relajó el margen. El esquema revisado está en `full_routes_v1/route_preflight_overview_v1.png`.

La preparación pasó 12 controles CPU de pipeline, 10 de sensores relativos, 8 de preflight y 3 fixtures de encuadre externo. Una revisión independiente añadió el hash del mapping privado a la validación, y detectó un delimitador antiguo en el extractor PiP: se corrigió antes de ejecutar, comprobando igualdad literal del constructor. El manifiesto final fija 133 entradas. La validación del grafo del repositorio encontró 10 localizadores textuales antiguos faltantes en otros documentos; se registra como pendiente ajeno a esta etapa, sin ampliar el alcance ni afirmar que pasó.

Se inició `full_routes_v1/run_full_delivery_stage_v1.py`: el proceso real del controlador es 38116, la cola 3360 y el primer Blender 24160, comprobados junto con sus comandos y parentesco. Son una instantánea, no prueba futura de ejecución. Los primeros recibos RGB/máscara avanzan y la RAM mínima observada del render supera 11 GiB. Los PID adicionales corresponden a lanzadores del entorno virtual, no a trabajos duplicados. La cola ejecuta serialmente captura en bloques de 12, validación/exportación pública, inferencia congelada640/448/960, seguimiento y evaluación privada. El controlador continúa después con sensores relativos y recuadros externos en bloques de20, composición y decodificación H264; aún no hay videos finales ni métricas de estas rutas.

El adaptador de sensores usa el intervalo real de 0,25 s: ruido heurístico de 2,5 mm y 1 mrad por incremento, independiente, sin sesgo ni deriva correlacionada. Exporta únicamente incrementos ruidosos en `sensors_public`, separado de poses exactas y recibos privados. ArUco codificado20cm, marco26,67cm, ID8 común frontal; C07 no tiene marcador propio. La exportación no equivale a localización: esa etapa deberá usar decodificaciones RGB reales, preservar marker_id y pasar0,20m explícitos, sin relajar gates de paralaje/reproyección. La campaña permanece pendiente y la cancelada no se reabrió.


## Legacy completo auditado; otras rutas en curso — 21 de octubre, 14:12 UTC

La primera ruta completa terminó captura, inferencia pública, seguimiento y evaluación privada: 178 fotogramas a 4 fps. La auditoría independiente pasó 284.009 comprobaciones y verificó 1.653 archivos por SHA256 sin errores. Recibo: `full_routes_v1/flights/legacy/evaluation_arithmetic_review_v1.json`. No se repitió ningún render, inferencia ni seguimiento; el controlador existente continúa vertical y después órbita.

En los 40 fotogramas de inspección legacy (10 s), la evaluación del objetivo actual C06/C07 da precisión 70,45%, recall 51,10% y F1 59,24%. F1 elegible es 73,78%, pero cubre solo el 36,85% de las observaciones verdaderas del objetivo. Hay 836 cambios de ID entre 1.653 pares consecutivos espacialmente emparejados; cobertura de pares 53,63%. Esto es fragmentación de identidad importante y no representa IDF1/HOTA/MOTA. Se conserva el negativo sin modificar el tracker ni hacer nuevos barridos de parámetros.

El agregado de todas las fases da F1 del objetivo 60,97% y F1 global con vecinos 54,78%; incluye 131 fotogramas de tránsito, cuatro de adquisición y tres de retorno, por lo que no sustituye la comparación de inspección. ArUco8 se decodificó en 80/178 fotogramas. La atribución del objetivo sigue siendo privada: matching global sin rematching favorable; los falsos positivos sin pareja usan centroide dentro de la envolvente visible del objetivo como aproximación.

Se revisaron visualmente las vistas completas de inspección 104/22/17, seleccionadas como peor/mediana/mejor por la regla predeclarada, además de ambas matrices objetivo. Las imágenes conservan vecinos, suelo y cielo; la densidad de IDs sobre vecinos dificulta su lectura individual. La selección describe los fallos observados y no prueba causas ni continuidad temporal. Recibo `preliminary_visual_review_v1.json`; entrega parcial `full_routes_v1/legacy_delivery_v1/index.html`. Todavía no hay comparación final de tres rutas, PiP completos revisados ni localización métrica. Las plantas, pesos, umbrales y campaña cancelada permanecen intactos. El estado y la memoria reales de esta activación quedan en `heartbeat_checks/20261021T141201Z.json`.


## Comparación parcial legacy–vertical — 21 de octubre, 11:20 (Bogotá)

Vertical completó 167 fotogramas, validación/exportación, inferencia, seguimiento y evaluación. Su primera auditoría aritmética pasó 266.543 comprobaciones, 1.554 archivos SHA256 y cero errores. El script de auditoría v2 solo corrige el nombre de ruta en una frase del recibo; conserva v1 y no cambia ningún cálculo. Entrega parcial verificada: `full_routes_v1/two_route_delivery_v2/index.html`, con cuatro alcances de matrices por ruta, matrices de inspección, selección peor/mediana/mejor predeclarada y vistas completas. No se repitieron inferencia ni seguimiento.

| Inspección del objetivo C06/C07 | Legacy | Vertical |
|---|---:|---:|
| Tiempo de inspección | 10 s | 8,5 s |
| F1 todos los tamaños | 59,24% | 69,91% |
| Precisión elegibles | 63,46% | 71,75% |
| Recall elegibles | 88,10% | 79,86% |
| F1 elegibles | 73,78% | 75,59% |
| Fracción de observaciones elegibles | 36,85% | 80,51% |
| Cambios ID elegibles / pares emparejados | 580/1054 | 1186/1447 |
| Cobertura de pares elegibles | 94,11% | 79,81% |

El seguimiento empeora: cambios condicionales elegibles 55,03% frente a 81,96%. No son IDF1/HOTA/MOTA. La mejora de detección global del objetivo no demuestra estabilidad temporal ni precisión 3D; las rutas tienen diferentes presupuestos, encuadres y observaciones. Se conserva el descenso del recall elegible y no se ajustan umbrales ni tracker. En toda la ruta, F1 objetivo 60,97%/65,97%; ArUco8 decodificado 80/178 frente a 30/167. C07 continúa sin marcador propio.

Se revisaron las matrices de inspección vertical y las vistas completas 15/31/33 (peor/mediana/mejor), así como los finales de los cuatro barridos 17/33/82/112. El follaje alto sigue visible; parte de la banda baja queda fuera, como corresponde al barrido por bandas. Estas muestras no reproducen la salida casi completa del objetivo del fragmento antiguo; no prueban cobertura individual ni causalidad de errores. Los vecinos y materiales permanecen intactos.

El constructor del informe parcial falló después de escribir HTML por mezclar separadores Windows en claves de hashes. Se preservó íntegro en `two_route_delivery_v1` con `build_failure.json`, sin promoverlo; v2 normaliza las claves con as_posix y pasó 25 enlaces locales. Este fallo de presentación no afectó los datos, matrices ni controlador. La órbita avanza en un único Blender verificado; hubo un intervalo largo sin capturas, pero recuperó avance con el mismo proceso y sin reinicio. Causa del intervalo no establecida. Estado y memoria: `heartbeat_checks/20261021T162049Z.json`. Siguen pendientes órbita, tres videos PiP revisados y localización métrica; no se cierra ni promueve la campaña.


## Tres rutas completas evaluadas — 21 de octubre, 21:47 UTC

Terminó la órbita parcial: 282 fotogramas, validación, inferencia pública, seguimiento y evaluación privada. Su primera auditoría aritmética pasó 459.377 comprobaciones y verificó 2.589 archivos SHA256 en 6,16 s, sin errores. No se repitieron renders, inferencia ni seguimiento. Las tres rutas suman 627 fotogramas. La nueva entrega `full_routes_v1/three_route_delivery_v1/index.html` pasó 31 enlaces locales y conserva los informes anteriores. Incluye cuatro alcances de matrices por ruta, matrices del objetivo durante inspección, tránsito separado y nueve vistas completas seleccionadas por la regla predeclarada.

| Inspección del objetivo C06/C07 | Legacy | Vertical | Órbita parcial |
|---|---:|---:|---:|
| Tiempo de inspección | 10 s | 8,5 s | 21,25 s |
| F1 todos los tamaños | 59,24% | 69,91% | 69,80% |
| Precisión elegibles | 63,46% | 71,75% | 70,87% |
| Recall elegibles | 88,10% | 79,86% | 80,25% |
| F1 elegibles | 73,78% | 75,59% | 75,27% |
| Fracción de observaciones elegibles | 36,85% | 80,51% | 80,93% |
| Cambios ID elegibles / pares emparejados | 580/1054 | 1186/1447 | 2618/4272 |
| Cobertura de pares elegibles | 94,11% | 79,81% | 79,82% |

La órbita no aporta una mejora de F1 respecto al vertical en estas observaciones y consume más tiempo. El seguimiento conserva un negativo grave: cambios condicionales elegibles de 55,03%, 81,96% y 61,28%, respectivamente. No son IDF1/HOTA/MOTA, ni se comparan presupuestos o vistas idénticos. La evaluación de toda la órbita da F1 objetivo 66,69%, F1 objetivo elegible 75,89% y F1 global con vecinos 61,31%. ArUco8 se decodificó realmente en 43/282 imágenes; legacy y vertical dieron 80/178 y 30/167. Decodificar el marcador no acredita aún pose métrica de los capachos.

Se revisaron visualmente las vistas orbitales 163/22/214, peor/mediana/mejor de inspección según el plan, y ambas matrices del objetivo. El peor caso, C07 frontal, registra 57 aciertos, 45 FP y 40 FN: 38 observaciones sin pareja espacial y dos confusiones de clase. El mejor, C07 posterior, todavía tiene 10 FP y 29 FN. Las superposiciones muestran fragmentos entre hojas y cortes de follaje en los bordes de algunos encuadres cercanos; no se atribuye cada fallo a una causa sin correspondencia individual demostrada. El área visible no se interpreta como oclusión. En toda la inspección orbital hay 2.149 observaciones objetivo sin pareja espacial y 359 coincidencias de clase incorrecta; entre elegibles persisten 934 y 325. Falta de pareja puede ser ausencia de propuesta o IoU insuficiente, no necesariamente ausencia visual.

La cola de captura/inferencia/seguimiento/evaluación terminó a las 20:49 UTC. El mismo controlador continúa los sensores relativos y los renders externos seriales; no se ha iniciado otro. Los videos PiP completos siguen pendientes de composición y revisión visual. La localización 3D permanece sin ejecutar y sin métricas: requiere etapa separada con ArUco realmente decodificado y sensores públicos ruidosos. Plantas, entorno, pesos, clases y umbrales permanecen fijos; la campaña cancelada no se reabrió. No se cierra ni se promueve esta campaña.
