# Mejora integral de localización de uchuvas — campaña en curso

## Contrato y estado

Campaña independiente: `outputs/integral_diagnosis_20261014`. No se sobrescriben
las campañas anteriores. Entrenamiento exclusivamente sintético, tres clases por
apariencia del capacho. El usuario autorizó sensores realistas: movimiento
relativo con ruido, deriva y desfase explícitos, corregido mediante ArUcos.
La pose exacta del simulador permanece en el evaluador. Sin límite global de
horas, un trabajo pesado GPU y reserva de RAM de 2 GiB; admisión inicial 6,5 GiB.

Objetivo sin garantía: más del 50 % de capachos observables localizados a 5 cm,
precisión de asociación al menos 90 %. No equivale a transferencia real.

**Estado:** auditoría inicial ejecutada; pruebas pequeñas de percepción en ejecución.
No se ha completado la mejora integral, ni hay una variante ganadora nueva.

## Evidencia inicial ejecutada

- Atlas de 60 referencias nuevas y 60 antiguas, únicamente de entrenamiento.
  Se inspeccionaron visualmente las diez hojas de contacto. Se marcaron tres
  vistas antiguas como redundantes: quedan 57 antiguas y 60 nuevas seleccionadas.
  `atlas/reviewed_manifest.json` conserva procedencia y clasificación de contexto.
- La muestra antigua está dominada por detalles y plantas parciales. Cuatro
  imágenes muestran capachos sostenidos en laboratorio; sirven para superficie,
  no para inferir arquitectura. La nueva muestra contiene bases, plantas enteras,
  hileras, tutorado, contraluz y capachos con pigmentación púrpura localizada.
- No se ha medido una distribución de 2–5 ejes basales. Muchas bases están
  ocultas; las miniaturas no permiten distinguir rebrotes de plantas vecinas.
  Se ampliaron tres referencias nuevas (índices 0, 3 y 51 del atlas). La primera
  muestra al menos tres ramas leñosas divergentes cerca del suelo; las otras dos
  tienen oclusión o desenfoque que impiden un recuento fiable. Esto respalda probar
  apertura basal, pero no estimar una distribución poblacional. Faltan el resto
  de ampliaciones y medidas normalizadas por escala.
- El SDF histórico tiene 1172 mapas de albedo, 1172 de rugosidad y cero de
  normales. El exportador copiaba solo los dos primeros tipos. Se añadió la opción
  `--normal-maps` dependiente de `--textures`, manteniendo el valor histórico por
  defecto. El fixture `fixtures/normal_maps_field` añade 1172 normales tangentes
  y reutiliza exactamente las mallas históricas. No está validado visualmente
  en Ogre2 ni se ha medido su efecto en detección.
- Recuento independiente de los cambios de identidad: 149754, de los cuales
  122317 ocurren entre cuadros consecutivos y 27437 tras huecos de detección.
  Coincide con el informe anterior. Esto valida contabilidad, no la corrección
  del emparejamiento de máscaras; faltan clips revisados individualmente.

## Cambios implementados para pruebas pequeñas

### Arquitectura

`basal_architecture.basal_scaffolds` crea una copia de la morfología y ensaya
2–5 ejes estructurales contando la continuación del eje raíz. Reordena los
segmentos nodales portadores de ramas hacia la base y acorta su longitud total;
no añade capachos, hojas ni subárboles. Conserva identidades y conexiones a nodos.
La longitud basal inicial de 15 cm es una heurística de longitud de arco, no una
altura vertical medida. Las direcciones exteriores son una propuesta inicial;
el ajuste contra anclajes reales y la auditoría geométrica siguen pendientes.

Se generaron tres controles (semillas 814140–814142) y variantes de 2–5 ejes.
La conservación de órganos, determinismo de entrada y serialización se probaron.
Los avisos de validación morfológica se conservan. No se promovió este ensayo a
la generación de datasets ni se afirma que simule desarrollo biológico.

### Percepción

El caché admite `--layout full|tiles` y `--input-size 640|960|1280`.
Los argumentos por defecto conservan el protocolo histórico de recortes 960.
Las variantes registran configuración distinta y rechazan reanudar un caché
incompatible. Se conservan propuestas débiles, máscaras exactas y descartes.

Se fijaron 60 imágenes públicas: doce bloques de cinco cuadros consecutivos,
distribuidos uniformemente por el recorrido, sin consultar verdad. Se comparan
full/960, full/1280, tiles/640 y tiles/960 con el mismo modelo y umbral histórico.
Este screening mide precisión/recall a IoU 0,5, clases colapsadas y coste. No
selecciona el ganador 3D: bloques tan breves no cumplen el soporte temporal.

El evaluador lee la verdad histórica por fotograma con memoria acotada y no la
expone al predictor. La siguiente ampliación deberá medir PR/AP, sensibilidad al
umbral y soportes multivista antes de seleccionar variantes o entrenar.

### Sensores

Contrato `relative-motion/1.0`: timestamps inicial/final, desplazamiento y vector
de rotación en el marco de la cámara anterior, covarianza 6×6 y fuente.
Rechaza campos adicionales, dimensiones inválidas, covarianzas no semidefinidas
positivas y tiempo no monótono. La rotación transforma cámara nueva → anterior.

Se implementó y ejecutó un adaptador privado del simulador que publica incrementos
relativos con tres niveles de ruido, deriva y desfase de 20 ms. Sus parámetros
son heurísticas de sensibilidad; no representan una IMU física calibrada. La
correlación temporal del sesgo solo se aproxima mediante covarianza marginal.
No publica origen mundial, máscaras ni identidades anatómicas.

El filtro `marker_motion_fusion.py` se inicializa exclusivamente con una pose
ArUco RGB, propaga movimiento relativo y rechaza innovaciones incompatibles.
Pasaron pruebas de marcos rotados, corrección, rechazo y discontinuidades. La
primera reproducción sobre 7972 cuadros detectó un error de integración: las
claves históricas son códigos decodificados pero sus poses ya son canónicas.
Se conserva `pose_fusion/INVALID.json`; sus estadísticas quedan invalidadas.
La reproducción corregida `pose_fusion_v2` usa la calibración pública para
normalizar las claves, sin volver a transformar la pose. La evaluación de
error de pose es exclusiva del evaluador; sigue
pendiente conectar estas poses a la triangulación y medir el efecto 3D.

## Continuidad y próximos pasos

### Muestras visuales solicitadas: dos, tres y cinco ramas

`balanced_examples_v1` contiene seis imágenes nuevas (con follaje y solo tallos),
tres morfologías y sus validaciones. El ensayo `balanced-basal-redistribution/0.1`
reparte conjuntos completos de nodos y subárboles del control 814140, conserva sus
711 nodos y 93 unidades reproductivas y añade 2/3/5 nodos de una base común.
Equilibra cargas por descendencia y longitudes estructurales relativas; conserva
identidades de órganos y conexiones nodales. No implementa todavía crecimiento,
competencia lumínica ni tutorado. Es una materialización exploratoria del objetivo
de equilibrio, no la integración final del contrato de presupuestos.

Pasó la prueba de conservación, unicidad de nodos, órdenes y conexiones padre,
sin mutar el control; validación con avisos conservada. La revisión visual muestra
copas más bajas/extendidas y agrupaciones foliares aún demasiado planas en zonas.
No aceptar para dataset sin corregir distribución vertical, tutorado y contrastar
densidad aparente con reales. Workbench usa colores de materiales para estructura,
no demuestra calidad de texturas. Se recuperó un error al escribir el manifiesto
(clave duplicada `count`), conservando las primeras imágenes y completando las
restantes mediante reanudación. La evaluación principal continuó en CPU.

### Heartbeat de las 21:21 de Colombia, 14 de octubre

Ambas reconstrucciones terminaron; full/1280 se evalúa y alcanzó 189/258 cuadros
al comprobarse. Se verificaron proceso y comando; sin espera de recursos.
El ejecutor reporta mínimo de 10,63 GiB libres durante esta evaluación.

Trabajo independiente: contrato experimental `scaffold-budget/1.0`. Distribuye
el presupuesto total de nodos descendientes entre 2–5 ejes con vigor comparable,
sin cambiar todavía ninguna morfología. El muestreo uniforme de cantidades y
jitter de vigor 0,85–1,15 son decisiones de cobertura experimental, no medidas
botánicas. Se prepararon doce repartos, tres semillas por cantidad, conservando
709 nodos (referencia del fixture, excluida base compartida). Dos pruebas pasan
conservación, determinismo, rechazo de cantidades inválidas y ausencia de un
eje dominante en esas propuestas. Integración en gramática, tutorado, competencia
de luz y contraste de densidad con reales siguen pendientes: no son doce plantas
nuevas ni una arquitectura ya corregida. `scaffold_budget_trials.json` lo declara.

### Heartbeat de las 21:11 de Colombia, 14 de octubre

Terminó la inferencia tiles/640 (258/258) y el supervisor encadenó seguimiento
a las 21:07:57 de Colombia, sin esperar al heartbeat. Se verificó el proceso
61396 por comando; guardó las 258 observaciones y sigue en ajuste geométrico.
Ese contador no significa que el mapa ya esté terminado. No se observó espera.

Se añadió al final de la cola una auditoría de comparación: mismos timestamps y
denominadores para las cuatro variantes, huella idéntica de detecciones e IDs
para los dos cambios de pose respecto a full/1280. Falla explícitamente si esas
condiciones no se cumplen, preservando el diagnóstico. Separa efecto de percepción,
frecuencia de pose y fusión; no convierte el screening a 1 Hz en evaluación final.

### Heartbeat de las 21:01 de Colombia, 14 de octubre

Tiles/640 avanzó de 169 a 219/258 al inicio de la revisión, con identidad del
proceso comprobada y GPU instantánea del 35 %. No hubo espera ni recuperación.
Se mantiene la frecuencia de diez minutos mientras progresa esta etapa.

Se extrajo y reforzó el contrato de poses públicas en `public_pose_stream.py`:
rechaza campos inesperados (incluidos datos verdaderos), IDs no canónicos,
tiempo no monótono, discordancias de ID/timestamp y rotaciones inválidas.
Tres pruebas pasaron, incluidos rechazos de verdad inyectada, reflexión y
duplicados; ambos archivos públicos reales validaron sus 7972 cuadros.
El tracker conserva el camino histórico por defecto. Esto verifica el límite
de entrada, no demuestra por sí solo el aislamiento de toda la cadena.

### Heartbeat de las 20:51 de Colombia, 14 de octubre

Tiles/640 avanzó de 88 a 155/258 resultados al comenzar la comprobación. Proceso
verificado por identidad y comando, sin espera declarada y mínimo de RAM libre
observado por el ejecutor de 9,18 GiB. No se reinició ni duplicó trabajo.

Se añadió entrada opcional de poses públicas a `track_continuous_predictions.py`,
con validación de timestamps, códigos canónicos, fuente y rotaciones; el camino
histórico conserva su valor por defecto. Pasaron cuatro pruebas históricas de
seguimiento y compilación. La nueva ruta requiere aún su ejecución/evaluación.

Se preparó un control visual desde las mismas poses RGB originales usadas por
la fusión v3. Esto evita comparar solamente ArUco a 1 Hz contra fusión alimentada
con ArUco a 30 Hz, confundiendo frecuencia y fusión. Quedan en cola seguimiento
y evaluación tanto del control como de v3 nominal, con las mismas detecciones
full/1280 a 1 Hz y el mismo algoritmo. Ninguno recibe verdad. La comparación es
diagnóstico de desarrollo, no selección final ni garantía de mejora 3D.

### Heartbeat de las 20:41 de Colombia, 14 de octubre

La inferencia tiles/640 continúa con progreso comprobado (77/258 al inicio de
la comprobación frente a ocho anteriormente). Se verificó PID, línea de comando
y una lectura de GPU del 16 %. No se detectó cola vacía ni espera de memoria.
Full/1280 terminó inferencia y seguimiento de los 258 cuadros.

Se preparó `sequence_evaluator` exclusivamente para el evaluador: misma auditoría
de códigos anatómicos de origen y visibilidad recalculada sobre los 258 cuadros.
El conjunto no visible en este subconjunto no se interpreta como completamente
oculto durante el vuelo original de 30 Hz. Las dos evaluaciones de máscaras y
mapas quedan encadenadas tras la reconstrucción pendiente, con fondo fuera del
denominador e intrusiones conservadas como errores. No se cambia el predictor.
Se mantiene heartbeat de diez minutos: este intervalo tuvo trabajo avanzando,
sin evidencia que justifique aumentar la frecuencia.

### Frecuencia de supervisión e inactividad

Por solicitud del usuario, el heartbeat pasa de una hora a diez minutos. Debe
registrar causas verificables de inactividad y ajustar entre cinco y quince
minutos tras observar al menos tres etapas. No sustituye el encadenamiento del
supervisor ni justifica crear carga artificial. Se mantienen un trabajo pesado
GPU y 2 GiB de RAM libres. La siguiente caída consultada ocurrió con inferencia
tiles/640 activa: se verificó el proceso y crecimiento de cinco a ocho resultados
guardados. GPU instantánea 0 % entre inferencias no demuestra proceso detenido;
el posprocesamiento de máscaras y escritura también consumen tiempo.

### Diagnóstico solicitado del equilibrio basal

Se generaron imágenes diagnósticas en `basal_balance_diagnostic`, sin modificar
las morfologías del ensayo. La geometría de tallos se extrajo con Blender en CPU;
los trazados muestran puntos de sus curvas por grupo de descendencia. Se midieron
las tres semillas 814140–814142, excluyendo los dos nodos de base compartida.
El eje principal conserva 90,4 %, 85,3 % y 91,7 % de los nodos con descendencia.
Las longitudes de las ramas basales son solo 26,7–36,7 % de la continuación
principal. El problema es estructural, no perspectiva de cámara.

**Decisión:** no aceptar `basal-scaffolds/1.0` como arquitectura representativa
de ramas principales aproximadamente equivalentes. El ensayo trasladaba ramas
laterales pequeñas y conservaba la dominancia del eje original. Hace falta una
base común con ejes de vigor y presupuesto de crecimiento comparables, con
variación natural, implementada en la morfología. No corregirlo estirando mallas
en Blender. Mantener parecido el total de órganos para aislar el cambio. La
equivalencia aproximada procede de la observación del usuario, no de una
distribución botánica medida. Las imágenes y medidas anteriores se conservan.

### Continuación tras consulta por inactividad — 14 de octubre, noche de Colombia

La cola terminó y el supervisor quedó vivo esperando revisión. GPU 0 %, unos
12 GiB de RAM libres: no era falta de recursos. La continuidad automática cubría
solo etapas ya preparadas; se reconoce esa limitación y se añadieron trabajos.

La fusión v3 nominal reduce la mediana de posición de cámara de 6,17 a 5,31 cm
y P95 de 16,31 a 11,52 cm en cuadros con observación visual. La mediana angular
empeora de 0,96 a 1,11 grados. No equivale a mejora de capachos ni a selección
final. Su efecto 3D sigue pendiente.

Se inspeccionaron los dos acercamientos basales de tallos: las conexiones bajas
son visibles y la variante abre hacia los lados. Falta evaluar el resto de vistas,
espacio de tutorado, colisiones y equilibrio de vigor antes de aceptarla.

Nueva secuencia de desarrollo: 258 RGB a aproximadamente 1 Hz, seleccionados
por timestamps públicos sobre todo el recorrido. Se encolan full/1280 y tiles/640,
cada una seguida por el mismo seguimiento histórico y reconstrucción. Los datos,
pesos y umbral son iguales; se cambia percepción. No reemplaza el seguimiento
final de 5 Hz ni es evaluación reservada. `prepare_integral_sequence.py` registra
selección y procedencia; no lee máscaras o poses verdaderas.

### Comprobación de continuidad — 15 de octubre, 00:45 UTC

Screening completo (cuatro variantes, 60 imágenes cada una). Tiles/960 obtuvo
17,39 % de recall, frente a 17,76 % tiles/640 y 17,14 % full/1280. Son diferencias
pequeñas en esta muestra correlacionada; no equivalen a superioridad 3D.

Se revisaron las seis vistas estructurales: la variante basal abre y desplaza
la copa, pero follaje y poco contraste de tallos impiden validar sus conexiones
bajas. No se acepta para integración todavía. Se encolaron ocho vistas de tallos,
incluidos acercamientos basales; son diagnóstico geométrico, no fotométrico.

La fusión v2 empeoró: en cuadros visualmente observados, error mediano de posición
de cámara 6,17 cm con ArUco y 99,83 cm con fusión nominal. No confundir error de
cámara con error de capacho. Se conserva como resultado negativo. La propagación
sin caducidad y el rechazo de correcciones tras deriva son hipótesis a comprobar.
La siguiente ablación v3 cambia solo la duración máxima desde una actualización
visual aceptada: 0,5 s (heurística). Al vencer, descarta el componente y solo una
nueva observación ArUco puede reiniciarlo. Mantiene ruido, cámaras y datos.

El supervisor terminó sin cierre de campaña; su PID 51748 fue reutilizado por
`node_repl.exe`. Se verificó nombre/línea de comando, se preservó el candado como
`continuation_stale_20261015_0045.lock` y se relanzó sin detener procesos ajenos.
Cola nueva: reproducción v3, evaluación v3 y diagnóstico de tallos. El estado
anterior `awaiting_verified_next_stages` no se contabiliza como ejecución.

### Comprobación de continuidad — 14 de octubre, 23:45 UTC

Las cuatro inferencias terminaron: 60 imágenes por variante, 240 en total.
Se comprobaron procesos del supervisor/evaluador y avance del resultado parcial
durante la revisión. La evaluación completó full/960, full/1280 y tiles/640;
sus recalls a IoU 0,5 y umbral histórico son respectivamente 7,44 %, 17,14 % y
17,76 %. No son métricas de localización 3D ni justifican seleccionar ganador.
La cuarta evaluación y las vistas estructurales siguen en cola/ejecución.

El campo `evaluation_seconds` del screening mide tiempo de reloj y puede incluir
suspensión: tiles/640 registra unos 8897 s mientras el ejecutor acumulaba unos
654 s efectivos para toda la etapa. No usar ese campo para comparar coste de
cómputo sin repetir una medición controlada. Se conserva el dato original.
La reproducción corregida de pose terminó los tres niveles sobre 7972 cuadros
cada uno; su evaluación geométrica permanece pendiente en la cola.

Supervisor: `scripts/continue_continuous_study.py --root outputs/integral_diagnosis_20261014`.
Lee `continuation_queue.json` entre trabajos y usa `run_effective_job.py` para
exclusión, memoria, logs y contabilidad sin suspensión. La cola actual termina
con `evaluate_perception_screening`, seis vistas estructurales comparables y
la evaluación de pose corregida `evaluate_pose_fusion_v2`;
después requiere la siguiente revisión
científica antes de agregar trabajos. Un estado `awaiting_verified_next_stages`
no significa un trabajo pesado activo. El heartbeat horario debe continuar la
implementación, no limitarse a esperar una cola vacía.

Pendientes en orden de dependencia:

1. Ampliaciones originales y comparación a escala de vuelo; clips de identidad.
2. Revisión espacial/visual basal y material A/B en Gazebo, cámaras idénticas.
3. Completar screening y ampliar las mejores alternativas a secuencias útiles
   para 3D; no escoger por recall 2D únicamente.
4. Evaluar la fusión ArUco/movimiento ruidoso, integrarla en triangulación y
   ampliar las pruebas de aislamiento y consistencia de incertidumbre.
5. Rutas referencia, doble altura y órbitas/arcos seguros; comparar a igual tiempo
   y sobre la unión observable, además del inventario total.
6. Entrenamientos 960 completo, 960 mixto y 1280 mixto; mismo preentrenamiento,
   particiones y presupuesto. `mask_ratio=2` es una ablación separada.
7. Integración de cambios respaldados, congelación y evaluación sobre seis
   morfologías nuevas. Reserva preliminar: 914140–914145, todavía sin generar;
   hay que comprobar disjunción contra inventarios completos, no solo búsqueda
   textual preliminar, antes de abrir la evaluación.
8. Informe final, métricas, resultados negativos y videos verificados.

La preparación se recuperó de dos incidencias: búsqueda de semillas demasiado
amplia (acotada a inventarios, pendiente validación completa) y denegación de
enlaces duros (se copiaron solo los 60 RGB de prueba). Ninguna alteró originales.

### Recuperación de evaluación, 14 de octubre 21:34 Colombia
La evaluación tiles640 fue detenida por la protección de RAM (mínimo 1,513 GiB). Se conserva el intento en sequence_evaluation/tiles_640_memory_failed1 y todos los resultados de inferencia y seguimiento. Se limita la descompresión a 16 máscaras por bloque; se comprobó igualdad exacta de IoU en tres tamaños de bloque y dimensiones no múltiplos de ocho. El nuevo intento repite únicamente evaluación, manteniendo reserva de 2 GiB. El ensayo full1280 terminado localizó 24/388 (6,19 %) con precisión de asociación 82,35 %; es desarrollo a 1 Hz y no una comparación directa con el vuelo histórico a 30 Hz.

### Supervisión 14 de octubre, 21:41 Colombia
El reintento alcanzó 77/258 diagnósticos (29,8 %) antes de otra parada por RAM: mínimo 0,986 GiB. Se preserva como tiles_640_memory_failed2. Tras detenerse, WSL ocupaba 14,65 GiB y el sistema seguía con memoria libre escasa; no se establece causalidad exclusiva del evaluador. Nueva admisión conservadora de 8 GiB para esta evaluación, reserva durante ejecución intacta de 2 GiB; ningún proceso ajeno detenido. Prueba persistente test_packed_evaluation verifica igualdad exacta con bloques parciales y bits de relleno. La repetición afecta solo a evaluación, no inferencia ni seguimiento.

### Supervisión 14 de octubre, 21:51 Colombia
El evaluador tiles640 volvió a avanzar: 154/258 cuadros al comienzo de la comprobación. Se verificaron líneas de comando del evaluador y 17,22/17,14 GiB libres en dos mediciones; el teleférico confirmó pausa y se solicitó estimación de su siguiente pico antes de autorizar reanudación. El resumen full1280 registra 364 objetos no localizados; 334 tienen al menos una trayectoria rechazada por soporte temporal insuficiente, 54 por falta de pose y 45 por soporte geométrico insuficiente. Son categorías solapadas de rechazo, no causas únicas demostradas: la fragmentación y la cadencia de 1 Hz requieren comparación controlada. Evidencia guardada en loss_summary.json.

### Supervisión 14 de octubre, 22:01 Colombia
Terminó tiles640: 258/258 cuadros, 21/388 localizaciones correctas, precisión de asociación 73,53 %, un duplicado y cuatro ArUcos incorrectos. Full1280 tiene 24/388, 82,35 %, un duplicado y un ArUco incorrecto. Aunque tiles640 alcanza recall2D 16,80 % frente a 16,52 %, no mejora las localizaciones 3D en esta secuencia. Comparación provisional hasta auditoría de entradas. El supervisor encadenó sin esperar heartbeat el control visual (23/388, 81,25 %) y el seguimiento con fusión v3, observado avanzando a 168/258. RAM libre 12,78 GiB, sin nuevos fallos. Teleférico confirmó una única carga headless, RSS inicial 3,475 GiB y guardas preventivas; no equivale a pico final. Se mantiene heartbeat 10 min: las tres últimas etapas encadenadas duraron aproximadamente 573, 133 y 180 segundos activos sin espera al heartbeat, por lo que no hay evidencia para acelerar su frecuencia.

### Referencias basales aportadas por el usuario, 14 de octubre
Se conservan cinco originales con hashes en outputs/integral_diagnosis_20261014/user_basal_references; son referencias de desarrollo, no entrenamiento real ni holdout. Las vistas 1 y 5 muestran separación baja de ejes estructurales con continuación ascendente y apertura oblicua, tramos basales relativamente despejados y follaje distribuido a lo largo de las ramas. Las uniones ocurren en una región basal, no necesariamente en una única estrella simétrica. Vistas 2 y 3 permiten revisar conexiones nodales, pedicelos curvos y ramificaciones secundarias; vista 4 aporta distribución vertical y apariencia de capachos/hojas. No hay escala física ni certeza de que las cinco fotos sean plantas independientes.
Corrección del ensayo basal: evitar copas bajas y aplanadas; generar 2–5 ejes de vigor comparable (rango solicitado, no distribución botánica inferida), con alturas y orientaciones variables, conexión nodal baja y crecimiento ascendente antes y después de la apertura hacia tutorado. Evitar pisos horizontales de hojas y sectores radiales idénticos. Comparar agrupación interior y apertura exterior como patrones aparentes; estas fotos no demuestran causalidad por competencia lumínica. No contar exactamente los ejes ocultos ni convertir proximidad al suelo en centímetros sin escala. El ensayo balanced_examples_v1 sigue sin aceptación para dataset. Las siguientes muestras deberán incluir vista frontal/lateral y estructura sin hojas con encuadre comparable a referencias 1 y 5.

### Quince muestras ascendentes para selección visual del usuario
Solicitud explícita: cinco imágenes por variante antes de continuar desde su elección. Se generan tres aperturas estructurales A vertical, B intermedia y C abierta, cinco semillas de desarrollo 814140–814144, con conteos 2/3/4/5/3, misma cámara y órganos entre alternativas emparejadas. Implementación pura ascending_basal_pilot.py: mantiene paquetes nodales y conecta ejes a nodos basales separados; cada eje retiene una longitud sustancial, evita dividir la altura de un tronco entre todas las ramas, orienta secundarios ascendentes y varía orientación foliar. Parámetros de longitud, radio y ángulos son heurísticas de ingeniería, no medidas de las fotos. No se simula mecánica del tutorado ni competencia de luz.
Prueba automatizada cubre conservación de órganos, identidad nodal, parentesco/orden, determinismo, invariancia de longitudes entre aperturas y ausencia de mutación del original para 12 combinaciones. Grafo validado. Los informes morfológicos conservan advertencias; no es aprobación botánica ni de colisiones. Las muestras Workbench son para forma, no calidad fotométrica. Persisten follaje compacto y apariencia de hojas poco fiel; no pasar a dataset. Salidas ascending_basal_review_v1, galería con identificadores A1–C5; selección de arquitectura pendiente del usuario.

### Corrección del usuario: apertura curvada
Durante la generación el usuario señaló que las ramas eran demasiado rectas y que la apertura real parece parabólica. Se conserva ascending_basal_review_v1 como intento recto, no candidato aprobado. curved_basal_pilot.py codifica una apertura ascendente de curvatura progresiva en los entrenudos del árbol morfológico, sin deformar únicamente Blender. Es una aproximación visual, no una ley botánica ni un ajuste cuantitativo. Se añaden nodos geométricos sin órganos para muestrear la curva y se conservan nodos reproductivos y sus conexiones.
El primer muestreo fijo de cuatro subdivisiones excedió el límite angular del intérprete en una combinación; se detuvo únicamente el render propio identificado y se conservó curved_basal_review_v2. La versión revisada usa subdivisión proporcional a longitud (mínimo cuatro), probada en doce combinaciones y con prueba persistente de puntos sobre parábola, límite angular, conservación de órganos y conexiones. Tanda vigente: curved_basal_review_v3, quince muestras con semillas emparejadas y tres intensidades de curvatura, pendiente de revisión humana. No sustituye la calibración posterior de tutorado, colisiones o densidad.

Revisión visual adicional: algunas copas C de curved_basal_review_v3 excedían el encuadre fijo. Se preserva ese intento y se regenera la tanda completa como curved_basal_review_v4 con escala ortográfica 22 común a las quince plantas (antes 16), misma orientación. La ampliación de cámara evita comparar recortes incompletos. Se mantiene pendiente la selección humana.


### Concavidad interior solicitada y control de poses (15 octubre UTC)
El usuario aclara que la curvatura debe ser cóncava hacia el interior, suave desde el nodo basal. Se incorpora una opción inward en el modelo morfológico: pendiente radial inicialmente mayor y decreciente con altura, hasta una tangente casi vertical. No implica que la punta cruce hacia el centro ni representa una ley botánica medida. Se mantienen perfiles anteriores y semillas emparejadas. Tanda en cola curved_basal_review_v5_inward: tres variantes, cinco imágenes por variante. Dos pruebas pasan, incluyendo los doce casos de 2–5 ejes con curvatura de signo negativo desde el primer segmento, parábola integrada, conservación de unidades reproductivas y límite del intérprete. Render y revisión visual pendientes; ninguna variante aceptada para dataset.

Comparación de desarrollo sobre 258 cuadros: full1280 24/388 localizaciones correctas, tiles640 21/388, control visual 23/388, fusión v3 0/388. La fusión tiene poses en 237 cuadros frente a 234 del control; no basta explicar el fallo por menor cobertura. No se acepta la fusión. Se prepara una ablación pública que conserva exactamente todas las poses RGB y añade únicamente componentes propagadas ausentes (1025 adiciones en la fuente de 7972 timestamps). Seguimiento y evaluación encadenados sin nueva inferencia, resultados separados gap_pose_v1. Rechazos se cuentan por trayectoria/marcador, no como causas exclusivas por fruto. No se cambia el umbral geométrico ni se consulta verdad para generar poses.

Tanda curved_basal_review_v5_inward completada: 15/15 PNG verificados y revisión visual de los tres paneles, sin recorte de copas. Render 222,61 segundos efectivos, salida 0; RAM libre mínima 10,90 GiB. Galería y paneles entregables. Selección humana pendiente, follaje compacto y forma foliar aún no corregidos.

El usuario selecciona A2 de curved_basal_review_v5_inward como referencia preferida, pendiente de definir geometría. Exige conservar jerarquía de ramas y ramificaciones sucesivas, no solo bifurcación basal. Solicita pausar el heartbeat hasta aviso explícito; no reanudar automáticamente.

### Tanda jerárquica solicitada tras A2
Se generan H1–H5: 2/3/4/5/3 ejes basales y 3/3/3/3/4 niveles sucesivos. Los ejes basales tienen una salida lateral intermedia y dos hijas terminales; niveles superiores bifurcan en el extremo. Direcciones aproximadamente opuestas con variación reproducible, concavidad interior suave, grosor decreciente respecto al segmento padre. Geometría definida en hierarchical_basal_pilot.py, no en Blender. Se reutilizan órganos nodales de desarrollo hasta el presupuesto disponible; densidad y arquitectura varían conjuntamente, no es ablación de eficacia. Una yema singular del contrato enumera una hija; la lista child_axes y parent_node_id conserva ambas conexiones de las bifurcaciones. Esto requiere ampliar el contrato de yemas antes de integración productiva. Diez renders completos y cinco paneles revisados, sin recorte; se observan extremos demasiado alineados en altura y cruces proyectados, sin validación física de intersecciones. Prueba de parentesco, orden, radios, bifurcaciones, determinismo y anclaje de órganos pasa para 2–5 bases. Grafo validado. Heartbeat permanece pausado y no hay aceptación para dataset.

### Preferencias de copa, tutorado y brillo
Variante optativa canopy-preference-review/0.1: ejes basales uniformes 3–5, probabilidad inicial ajustable de cuatro niveles 0,20 (tres 0,80), elección de ingeniería para concretar la preferencia del usuario. Atenuación probabilística de hojas interiores según radio normalizado por seis bandas de altura, manteniendo hojas y capachos en sus nodos; no simula irradiancia. En algunas ramas elegibles se modifica suavemente la curvatura alrededor del 45–60% de la altura original, hacia el exterior; no simula fuerzas ni contactos reales del tutorado. Las cinco semillas de prueba resultaron 4/5/3/4/4 bases y 3/3/4/3/3 niveles; las probabilidades no imponen cuotas por tanda. Pruebas de reproducibilidad, extremos de probabilidad, anclaje y límites angulares pasan. Materiales optativos de hoja/capacho preservan mapas y remapean rugosidad a 0,85–0,98, especular reducido. Workbench desactiva su brillo de estudio: esa vista no valida materiales PBR ni Gazebo. Render optativo --preferences preparado, aún no ejecutado ni inspeccionado; heartbeat pausado.

Muestras canopy_preference_review_v1 generadas y revisadas: cinco plantas, diez vistas, paneles P1–P5. Render completado en 50,31 s, salida 0, RAM libre mínima 12,21 GiB. Encuadres completos; brillo de estudio reducido. Persisten puntas desnudas y follaje escaso en algunas muestras. No validación PBR/Gazebo ni mecánica del tutorado. Selección pendiente; heartbeat pausado.

### Ajuste a nueva referencia de follaje
Referencia original conservada con hash en foliage_reference. P4/P5 preferidas por usuario; nuevo modulo foliage_reference_pilot mantiene geometría y unidades reproductivas, rellena nodos exteriores y terminales con hojas de identidad única. Hojas ovado-cordadas más anchas, orientación adulta 95–135 grados y terminal 80–125; tamaño terminal 0,8–1,0 del template. Parámetros de ingeniería, no medición botánica. Dos pruebas Cycles OptiX de P4/P5 precedieron la tanda foliage_material_variants_v3: cinco plantas, diez vistas verificadas y revisadas. Rugosidad remapeada 0,85–0,98 preservando mapas, normales 0,75 y microrelieve 0,018; luz difusa. Persisten falta de arrugado e irregularidad, venación y color de capachos distintos. R3 con cinco bases y cuatro niveles alcanza 1128 hojas y se considera exceso visual, no variante aceptada. R1/R2: 413/424 hojas; R4/R5: 342/349. Intersecciones y biomecánica no validadas. No selección de dataset ni transferencia real. Prueba de anclaje, reproducibilidad y conservación de ramas/capachos pasa.
El usuario revocó la coordinación entre proyectos: no consultar ni enviar mensajes al teleférico o RL+IL para recursos; eliminado ese bloque del heartbeat, que permanece pausado.


### Revisión de seis referencias de campo y relieve foliar (15 octubre UTC)

Se revisaron las seis fotografías aportadas (todas de campo), priorizando la sexta, y las cinco láminas del atlas nuevo (60 miniaturas) más dos del antiguo (24 miniaturas). Esto no equivale a revisar exhaustivamente todos los originales del dataset. La versión previa acumulaba hojas en planos horizontales y carecía de subdivisión transversal de la lámina. Se prueba una malla transversal optativa, con abombamiento entre nervaduras e inclinaciones más diversas, sobre las semillas de P4/P5; las cantidades y conexiones se conservan. Los parámetros son heurísticas visuales, no mediciones botánicas. El acabado de capachos y la validación de intersecciones continúan pendientes. Heartbeat pausado y coordinación externa revocada.

Se revisaron también originales del atlas nuevo 16, 25 y 53. El usuario precisó que todas las ramas terminales deben terminar en hoja: se impone en el último nodo, independiente de la probabilidad de relleno, y se prueba en semillas con tres y cuatro niveles. La variante visual de campo usa material verde en el 85 % de los capachos como heurística de aproximación a la sexta referencia; conserva el estado histórico y la madurez del fruto, y registra la sustitución de apariencia. No es un conjunto válido para entrenamiento fenológico sin reconciliar antes ese contrato.


### Trabajo nocturno autorizado, 14 octubre 23:44 Colombia

Usuario autoriza tres horas de refinamiento, hasta el 15 octubre 02:44 Colombia, y luego pilotos pequeños de dataset y segmentación con dron. Se reactiva el heartbeat existente cada diez minutos, sin coordinación externa. Nuevas correcciones: follaje basal variable (las bases peladas eran ejemplos para mostrar estructura), ápice foliar acuminado y nervaduras de capachos más oscuras que las foliares. Se implementan como variante optativa 0.6, con hojas en nodos basales, perfil cordado acuminado y oscurecimiento mediante la máscara existente de nervaduras del capacho. No se asigna madurez del fruto a partir del color. Hoja terminal sigue obligatoria. Estado y transición en overnight_refinement.json. Fallo histórico audit_pose_reprojection_v1 identificado como KeyError marker_id; recuperación pendiente antes de reanudar esa cola.

El usuario autoriza explícitamente sustituir parámetros elegidos a tanteo si aumenta la fidelidad frente a imágenes del dataset. P4/P5, cantidades de ejes, niveles, ángulos y densidades son referencias iniciales, no restricciones rígidas. Comparar varias vistas y registrar antes/después y justificación; preservar conexiones nodales, reproducibilidad e independencia de madurez y apariencia.

### Revisión nocturna, 15 octubre 00:00 Colombia
Diez vistas de cinco variantes v6 terminadas (309,3 s, salida 0, RAM libre mínima 11,79 GiB), decodificadas y revisadas en paneles. Se conserva la concentración excesiva de copa alta. Alternativa v7 optativa: una hija secundaria nace en nodo 4–9 en vez del extremo; otra conserva continuación terminal. Conserva órganos, longitudes y direcciones para aislar distribución de alturas; reconstruye el enlace de yema trasladado. Pruebas de determinismo, conexiones y grosor decreciente pasan en tres/cuatro niveles. Es heurística de desarrollo, no aceptación de colisiones. Se generan dos semillas emparejadas con vistas frontal, detalle y lateral.

### Supervisión 15 octubre 00:05 Colombia
V7 completó seis vistas en 125,6 s, salida 0, RAM libre mínima 10,01 GiB. Revisión de ambas plantas en frontal/detalle/lateral conserva escalonamiento como candidato; persiste superficie foliar demasiado lisa. Se registra distribución de alturas de inserción nodal por cuartiles, explícitamente distinta de densidad proyectada. Iniciada ablación v8 con relieve 1,8 veces mayor, mismos órganos, cámaras, materiales y arquitectura. Heartbeat reducido a cinco minutos: últimas etapas 70/309/126 segundos y aproximadamente 319 segundos entre fin de v7 y activación de revisión; no se atribuye todo ese intervalo a uso CPU/GPU nulo.

### Supervisión 15 octubre 00:12 Colombia
V8 terminó seis renders en 148,9 s, salida 0, RAM mínima libre 6,80 GiB; revisadas todas las vistas. El relieve 1,8x es excesivo en varias hojas; siguiente prueba 1,35x. Se corrige el ápice de la malla foliar optativa: un vértice único sustituye la fila coincidente de anchura cero. Auditoría Blender de seis casos (dos siluetas, tres relieves) pasa: coordenadas finitas, UV en rango, caras de área positiva, aristas usadas por máximo dos caras y ápice único. No valida intersecciones entre órganos.


### Supervisión 15 octubre 00:17 Colombia
V9 terminó seis vistas en 122,54 s, salida 0, RAM libre mínima 4,67 GiB. Revisadas ambas vistas de detalle y las cuatro vistas completas/laterales. Relieve 1,35x retenido como candidato frente a los pliegues excesivos de 1,8x; no constituye aceptación para dataset. Se lanza prueba pequeña v10 con semilla de desarrollo 814146 (cuatro niveles), conservando materiales, cámaras y escalonamiento; se inspeccionará la densidad antes de modificar la regla foliar. Comprobados procesos propios ausentes y lock ausente antes del lanzamiento; admisión 6,5 GiB y reserva 2 GiB. Sin coordinación con otros proyectos.


### Supervisión 15 octubre 00:23 Colombia
V10 completó tres vistas en 138,95 s, salida 0, mínimo libre 4,57 GiB. Inspección frontal, lateral y detalle confirma capas foliares excesivamente compactas en cuatro niveles. Ensayo v11 emparejado conserva semilla, ramas, cámaras, materiales y órganos reproductivos; reduce inserciones foliares próximas según distancia sobre el eje / longitud de hoja (0,55, heurística no calibrada). Conserva hojas basales y terminales, priorizando las distales. Cinco pruebas pasan, incluyendo determinismo, coordenadas, conexiones nodales y conservación reproductiva. No es corrección de colisiones ni simulación de competencia lumínica. Grafo válido: 151 nodos, 260 relaciones.


### Supervisión 15 octubre 00:28 Colombia
V11 terminó tres vistas en 144,95 s, salida 0, mínimo libre 8,31 GiB. Revisadas las tres y nuevamente la sexta referencia de campo: menor apilamiento foliar, de 1191 a 446 hojas, conservando 107 unidades reproductivas. Mayor visibilidad no demuestra por sí sola fidelidad; persisten regularidad angular, detalle superficial insuficiente y diferencia de nervaduras. Se conserva sólo como candidato y se inicia v12 para comprobar la misma regla en dos plantas de tres niveles (814144/814145), emparejadas con v9. Antes de iniciar: ningún proceso propio de render/supervisor, lock ausente y 12,60 GiB libres.


### Supervisión 15 octubre 00:33 Colombia
V12 completó seis vistas en 96,47 s, salida 0 y RAM libre mínima 10,03 GiB. Revisadas las seis: separación 0,55 elimina demasiado follaje en tres niveles, con extremos y siluetas excesivamente abiertos. Se rechaza como regla universal; v13 compara 0,25 con las mismas dos semillas, cámaras y materiales. Conteos reproducibles guardados en visual_review.json. Antes del lanzamiento no había procesos propios ni lock; 12,11 GiB libres. Continúa pendiente diagnosticar estructuras finas angulares y reconciliar contratos antes de dataset.


### Supervisión 15 octubre 00:38 Colombia
V13 terminó seis vistas en 100,47 s, salida 0, RAM libre mínima 10,98 GiB. Revisadas todas: 0,25 conserva mejor volumen que 0,55, sin aceptar aún para dataset. Diagnóstico de pecíolos en semilla 814144: longitudes 2,011–5,198 cm en modelo; mediana 3,604 frente a lámina mediana 9,058 cm. Todos los desplazamientos clearance_lift son cero. Estos valores no son medidas reales. V14 ensaya factor 0,6 conservando orientación, láminas, nodos y reproducción; heurística visual explícita, no corrección demostrada. Seis pruebas pasan y grafo válido. Antes de lanzar no había proceso propio ni lock y había 16,08 GiB libres.


### Supervisión 15 octubre 00:43 Colombia
V14 terminó seis vistas en 92,37 s, salida 0, mínimo RAM libre 13,88 GiB. Revisadas todas; no hay mejora clara de rigidez con pecíolos 0,6, no se adopta. Inspeccionados albedo y normales leaf_healthy: mapas 512x512 con poco relieve entre venas. V15 retorna a geometría v13 y añade bump celular UV optativo (escala22, fuerza0,45, distancia0,015), preservando normales existentes. Es hipótesis visual no calibrada, no venación anatómica ni textura aceptada para Gazebo. Proceso anterior ausente, lock ausente y 16,14 GiB libres antes de iniciar.


### Supervisión 15 octubre 00:48 Colombia
V15 terminó seis vistas en 92,36 s, salida 0, mínimo libre 13,61 GiB; todas revisadas. Relieve fino visible en detalle y sutil en planta completa; candidato, no venación anatómica validada. V16 aplica configuración a otras semillas de desarrollo 814149/814150, sin tocar reserva. Antes de lanzar: proceso propio ausente, lock ausente, 15,73 GiB libres. Auditoría de contrato registra nodos con varias hijas en branch_contract_audit_v1.json: child_axes conserva ambas, pero branch_id singular no puede enumerarlas. Pendiente contrato compatible y pruebas antes de integración; no se modifica durante el render activo.


### Supervisión 15 octubre 00:53 Colombia
V16 completó seis vistas en 92,41 s, salida0, mínimo libre13,59GiB. Revisadas todas; consistencia visual del candidato en dos morfologías adicionales, aún regularidad de hojas y venación simplificada. Contrato branch_junction_contract/1.0 enumera todas las hijas por nodo desde child_axes y parent_node_id, sin cambiar geometría ni redefinir una bifurcación como múltiples yemas. branch_id histórico permanece referencia singular, no topología completa. Se actualiza tras escalonar ramas; pruebas verifican todas las conexiones y conservación al serializar/cargar en tres/cuatro niveles. Siete pruebas foliares y una jerárquica pasan; grafo válido. Integración de consumidores aún pendiente. V17 comprueba superficie en cuatro niveles (semilla814146, separación0,55), emparejado con v11. Proceso anterior y lock ausentes;15,81GiB libres antes del trabajo.


### Supervisión 15 octubre 00:58 Colombia
V17 terminó tres vistas en 58,30 s, salida0, mínimo libre13,63GiB; todas revisadas. Árbol de ejes idéntico al de v11, confirmando comparación de superficie sin cambio de órganos. Relieve candidato se mantiene en cuatro niveles; disposición foliar regular aún pendiente. V18 compara luz lateral con estudio amplio en semilla814144 frente a v15, conservando morfología y materiales. Luz es heurística sin calibración radiométrica; no se interpreta un cambio de sombras como mejora geométrica. Antes de lanzar: sin procesos propios/lock,15,95GiB libres.


### Supervisión 15 octubre 01:03 Colombia
V18 terminó tres vistas en 46,31 s, salida0, mínimo libre14,06GiB; todas revisadas. Luz lateral enfatiza relieve y oscurece copa; se conserva como control, no como mejora geométrica. Auditoría identifica recorte de senescencia a0,18 en piloto, suprimiendo material senescente a partir de0,22. Fuentes originales:227/588 hojas en semilla144 y215/629 en145 superan ese umbral; no son medidas de campo. V19 conserva estados foliares originales (también plantillas de relleno), sin cambiar geometría ni reproducción; ocho pruebas pasan. Es prueba de apariencia, no validación de distribución fenológica real. Consulta inicial de posiciones sobre fuente sin direcciones resueltas falló; se repitió auditoría mediante recorrido del árbol, sin alterar resultados. Antes del lanzamiento no había proceso propio/lock y15,81GiB libres.


### Supervisión 15 octubre 01:08 Colombia
V19 terminó seis vistas en94,36s, salida0, mínimo libre13,44GiB; todas revisadas. Estados originales revelan salto verde/amarillo completo a senescencia0,22; no aceptado como representación visual. V20 conserva estados y mezcla albedos existentes en11 niveles según senescencia, con normales/rugosidad verdes preservados. Es interpolación de apariencia heurística, no modelo calibrado de envejecimiento ni equivalencia fenológica. Selección optativa conserva comportamiento histórico cuando faltan materiales graduados. Nueve pruebas pasan, grafo válido. Antes de iniciar: ningún proceso propio ni lock,15,62GiB libres.


### Supervision 15 octubre 01:13 Colombia
V20 completo seis vistas en 92,36 s, salida 0, minimo libre 13,808 GiB; todas revisadas. Gradacion evita salto amarillo uniforme, conservada como candidato de desarrollo. Auditoria local de 267 hojas: error angular mediano 4,995 grados y maximo 46,958 entre insercion solicitada e interpretada (sin clearance lift). Variante optativa v21 proyecta azimut al plano normal del eje antes de aplicar angulo; helper puro compartido por Blender y proxies de colision. Dos pruebas de marco y nueve foliares pasan; no equivale a validar colisiones o distribucion botanica. Antes del piloto: sin procesos propios ni lock, 15,87 GiB libres. Integracion completa con consumidores y aceptacion para dataset pendientes.


### Supervision 15 octubre 01:22 Colombia
V21 seguia activo al inicio: cuatro vistas guardadas, proceso Blender identificado, 13,92 GiB libres. Se intento abrir detalle aun no escrito; tras finalizar se revisaron las seis vistas. Termino en 96,37 s, salida0, minimo libre13,915 GiB. Correccion angular conserva apariencia general; no demuestra gran mejora visual y persisten apilamiento foliar y tallos finos angulares. V22 transfiere candidato combinado a semillas de desarrollo814149/814150; comparacion con v16 no atribuye cambios exclusivamente al marco, porque tambien incluye color graduado y estados originales. No se inspeccionan semillas reservadas ni se acepta todavia para dataset.


### Supervision 15 octubre 01:27 Colombia
V22 termino seis vistas en90,34s, salida0, minimo libre14,039GiB; todas revisadas. Persiste apilamiento de hojas en capas. V23 ensaya dispersion azimutal de140 grados a cada lado de direccion radial frente a85 en piloto original, con flujo aleatorio independiente y semillas814144/145; se compara con v21. Es hipotesis visual de orientacion, no modelo de competencia luminica calibrado. Conserva cantidades, tamanos, insercion, conexiones y reproduccion. Diez pruebas pasan, grafo valido. Antes del trabajo: sin procesos propios ni lock,15,858GiB libres. Intervalo desde fin de v22 hasta activacion06:27:30:102s de espera de revision; no se atribuye a suspension.


### Supervision 15 octubre 01:32 Colombia
V23 completo seis vistas en92,39s, salida0, minimo libre14,096GiB; revisadas todas y nuevamente sexta foto de campo. Mayor variedad proyectada pero capas persisten; no se adopta aun. V24 controla rango85 con mismo flujo aleatorio de v23 (140); comparar contra v21 mezclaba amplitud y realizacion aleatoria. Auditoria de alcance de validacion guardada: semilla144 tiene2903 advertencias; geometric_collision y visual_occlusion no evaluadas, fenologia legacy_not_evaluated. Esto no constituye aceptacion geometrica ni fenologica. Antes de lanzar: sin procesos propios/lock,15,734GiB libres. Fin-v23 a heartbeat:65s de espera de revision, sin inferir suspension.


### Supervision 15 octubre 01:37 Colombia
V24 completo seis vistas en96,36s, salida0, minimo libre13,619GiB; todas revisadas. Control85 y variante140 no muestran ganador claro; no se adopta140. Se inicia auditoria CPU de contactos conservadores sobre cuatro morfologias guardadas, sin modificarlas; informes distinguen conflictos, holguras y solapamiento blando, sin afirmar interseccion de mallas ni oclusion de camara. Se guarda hash de entradas y progreso por planta. Grafo valido. Antes de iniciar no habia procesos propios/lock y habia15,640GiB libres. Intervalo fin-render a heartbeat84s de espera de revision. GPU libre durante diagnostico geometrico justificado.

V25 guardo4/4 informes: conflictos conservadores185/185 para144 y160/160 para145, invariantes al rango angular. Solapamientos blandos140 frente85:1665/1700 y2289/2069; no mejora consistente. Proxima prioridad: localizar pares rigidos y confirmar geometria; estos conteos no son intersecciones de malla confirmadas.


### Supervision 15 octubre 01:42 Colombia
V25 confirmado completado. En semilla144 hay168 pares calyx/stem que involucran 12 capachos distintos; no contar pares como objetos afectados. Se inicia v26 con mallas reales de morfologia guardada v24/814144, sin regenerar ni modificar arquitectura. Auditoria existente completa de contactos, cache BVH64; material no cambia geometria. Una planta aislada sin tutorado, por lo que no constituye validacion de escena completa. Antes: sin trabajos propios ni lock,15,644GiB libres. Grafo valido. GPU puede permanecer libre porque esta fase calcula contactos en CPU.

V26 termino sin fallo de ejecucion, pero resultado geometrico INVALID:1767 objetos auditados,120 pares clasificados como colision fisica,445 intersecciones blandas foliares,183 violaciones de holgura. No son conteos de organos unicos. Oclusion visual no medida. Se bloquea aceptacion de esta variante para dataset hasta diagnostico y correccion de poses/conexiones; no borrar ni reemplazar resultados.


### Supervision 15 octubre 01:47 Colombia
Auditor dependia del patron axis_node_N para reconocer conexiones, incompatible con IDs del piloto jerarquico. Se agregan nodos extremos explicitos a segmentos/apices y se consultan para uniones de ramas y peciolos/pedicelos. Fallback historico preservado para objetos sin etiquetas nuevas; no exime capachos ni nodos ajenos. Tres pruebas pasan. V27 repite auditoria de misma morfologia guardada, sin cambios de forma; es correccion del auditor, no mejora geometrica. Se conservan v26 y su clasificacion. Grafo valido; sin procesos propios/lock y15,367GiB libres antes de lanzamiento.

V27 fallo TypeError por firma de tag_annotation_object aun sin campos nuevos. Blender devolvio0; se detecto log y ausencia de entregable, no se acepta estado completed. Firma ampliada con campos opcionales y prueba de escritura;4 pruebas pasan. Retry1 preserva fallo original y agrega --python-exit-code1. Geometria2085 objetos reconstruida; auditoria en curso.

Retry1 completo32,28s, salida0 y entregable verificado. Pares fisicos tras corregir topologia: 113 frente120; geometria identica, no presentar reduccion como reparacion geometrica. Estado invalid.


### Supervision 15 octubre 01:53 Colombia
Se registra topologia de61 pares tallo/tallo para diagnostico independiente. V28 prueba reparador local existente sobre unidades reproductivas de una sola planta: angulos y longitud de pedicelo limitada1,5x; conserva nodo, identidad y estados. Excluye hojas del objetivo local porque se repararian aparte, pero auditoria final incluye todas las hojas; no interpretar exito local como validez completa. Guarda checkpoint cada10 cambios, morfologia final separada y reconstruye todo antes de auditoria. Entrada v24 intacta. Consulta de procesos tuvo timeout de revision automatica; unico reintento exitoso: sin procesos propios/lock,15,622GiB libres. No se considera fallo de la campaña ni se contacto otro proyecto.


### Supervision 15 octubre 01:58 Colombia
V28 confirmado vivo por linea de comando, RAM libre14,85GiB, log crecio de4 a15 unidades evaluadas y checkpoint guardado. Contador no equivale a15/51: el reparador omite unidades sin conflictos iniciales y no hay denominador fiable de busquedas. Triage de61 pares semanticamente stem/stem:18 parentales cerca de union,6 parentales remotos,13 entre ejes no parentales y24 con peciolos/pedicelos u otros adjuntos. Proximidad topologica no exime penetraciones; se conserva informe para diagnostico posterior. No se altera codigo del ensayo activo ni se lanza otro trabajo pesado.


### Supervision 15 octubre 02:03 Colombia
V28 termino242,84s, salida0, minimo libre14,548GiB;17 ajustes de pedicelo. Comparacion JSON excluyendo pedicelos demuestra igualdad del resto. Auditoria reconstruida: pares fisicos113->67, calyx/stem50->7, calyx/calyx2->0, stem/stem61->60, holguras179->153, intersecciones blandas445->440. Sigue INVALID. V29 renderiza morfologia reparada exacta mediante opcion saved-morphology; tres vistas y mismos materiales de revision para comprobar apariencia. Sin procesos propios/lock y15,481GiB libres antes de lanzar. Espera fin-v28 a heartbeat136s para revision; no suspension inferida.


### Supervision 15 octubre 02:08 Colombia
V29 termino48,35s, salida0, minimo libre13,737GiB; tres vistas revisadas. Silueta general conservada; persisten simplificaciones de venacion y distribucion foliar. V30 aplica reparador foliar existente a morfologia guardada v28; conserva organos, nodos y reproduccion, busca orientaciones y requiere reconstruccion/auditoria completa. Intersecciones hoja/hoja no son objetivo de esta busqueda y siguen informandose; no confundir correccion local con validez final. No modifica arquitectura de ramas. Antes: sin procesos propios/lock,15,554GiB libres. Fin-render a heartbeat125s para revision.


### Supervision 15 octubre 02:13 Colombia
V30 sigue activo con linea de comando confirmada; log avanza a78 busquedas foliares, RAM minima observada14,593GiB. No es porcentaje de267 hojas porque omite hojas sin conflictos iniciales. Mientras avanza, se confirma traceback historico audit_pose_reprojection_v1: falta marker_id en observaciones entregadas a triangulate. Se prepara correccion copiando identificador de referencia publica del objeto, version1.1 y salida exclusiva pose_reprojection_audit_v2.json; compilacion pasa, ejecucion pendiente tras refinamiento. Cola historica no reanudada ni resultados v1 reemplazados. Grafo valido.


### Supervision 15 octubre 02:18 Colombia
V30 activo y avanzando por archivos/log:131 busquedas al comprobar; checkpoint conserva267 hojas e identidades,120 cambios. Comparacion completa normalizando solo azimut, insercion, curl, twist y procedencia del ajuste confirma igualdad del resto de morfologia. Es checkpoint parcial, no aceptacion final. RAM libre14,989GiB, minima14,593GiB. Preparacion de transicion: generador de anotaciones existente no expone entrada de morfologia guardada en CLI; integrar candidato validado requiere ruta explicita, no asumir que otro render reproduce estas plantas. No arrancar gran lote ni usar apariencia verde como etiqueta de madurez.

V30 completo639,87s, salida0,140 ajustes foliares. Auditoria final: pares fisicos67->39, todos stem/stem; blandos440->155; holguras153->106. Sigue INVALID. Se encadena V31 tres vistas guardadas para verificar apariencia; sin proceso previo/lock y15,537GiB libres.

### Supervision 15 octubre 02:23–02:32 Colombia
V31 completo3/3 vistas,48,35s; revisadas todas, follaje conservado con hojas mas erguidas y algunas capas angulares. V32 prueba piso angular25 grados entre direccion inicial de hija y tangente parental; heuristica geometrica, no botanica medida. Cambia30 uniones conservando organos, dimensiones y conexiones;11 pruebas de follaje pasan y grafo valido. Auditoria26,24s, salida0, minimoRAM15,379GiB: fisicos39->31, holguras106->56, blandos155->205. Sigue INVALID; no aceptar por mejora de una sola metrica. V33 encadenado para tres vistas identicas desde JSON guardado, previa comprobacion sin procesos propios/lock y15,833GiB libres. Versiones anteriores intactas; no contacto con otros proyectos. Pendiente revisar fidelidad visual y contactos restantes antes de piloto de anotaciones.

### Supervision 15 octubre 02:32 Colombia
V33 completo3/3 vistas,46,29s, salida0 y minimoRAM13,697GiB. Revision de todas: puntas y acabado mate conservados, pero centro aun agrupado y hojas en capas; no demuestra mejora global de fidelidad. Desglose V32:16 pares stem/stem,14 stem/calyx y1 calyx/calyx. La apertura reintrodujo contactos reproductivos que V30 habia eliminado, por lo que31 frente39 no basta para aceptarla. V34 compara piso35 grados desde misma entrada V30 (no acumula cambios sobre25),42 uniones modificadas, sin cambiar dimensiones/organos. Antes de lanzar: ningun proceso propio, lock ausente,15,469GiB libres. Preparacion independiente: renderer conserva morfologia guardada y existe render_reproductive_annotations para futura prueba pequena; aun no se generaron etiquetas ni se acepto geometria invalida como dataset.
V34 completo24,25s, minimoRAM15,443GiB:28 fisicos(11stem/stem,16stem/calyx,1calyx/calyx),238 blandos,30 holguras. Continua INVALID; no aceptar apertura sola. Se encadena V35 reparacion local reproductiva y reconstruccion/auditoria completa, desde V34 versionado. Apariencia final aun pendiente, sin grandes lotes ni semillas reservadas. Se conserva reloj de transicion07:44:42Z.

### Supervision 15 octubre 02:37 Colombia
V35 completo52,32s, salida0,minRAM14,617GiB;6 ajustes de pedicelo. Auditoria fisicos28->17, holguras30->20, blandos238->241; invalido. Comparacion JSON completa salvo angulos,longitud y procedencia de pedicelos confirma identidad de todo lo demas; invariants.json guardado. Sin procesos propios ni lock al revisar,15,513GiB libres. Fin07:36:00 a heartbeat07:37:31:91s de espera para revision, no suspension inferida. V36 encadenado tres vistas;2/3 ya guardadas. Restantes fisicos incluyen uniones basales, cruces remotos y peciolos; requiere validacion completa antes de ampliar. Ventana de refinamiento termina07:44:42Z; se finalizara ensayo pequeno activo y se pasara a pilotos/contratos sin promover candidato invalido a lote de entrenamiento.
V36 completo46,29s,minRAM13,923GiB; tres vistas revisadas. Follaje y silueta conservados; apilamiento central y base relativamente vacia persisten. Se encadena V37 ajuste foliar/peciolos sobre V35 para contactos con capachos y tallos; conserva morfologia nodal. Al limite horario terminar ensayo activo y pasar a pilotos/validacion, sin prolongar busqueda estetica general.

### Supervision 15 octubre 02:42 Colombia
V37 proceso/linea de comando y lock33432 verificados; logs avanzaron y termino07:43:30Z en196,66s,70 ajustes foliares,minRAM14,928GiB. Auditoria completa17->7 fisicos,241->144 blandos,20->12 holguras. Sigue INVALID:5 contactos basales y2 cruces remotos. Comparacion integral salvo pose/procedencia foliar pasa; conexiones,identidades y estados conservados. Preparada opcion --annotation-smoke en renderer: exige morfologia guardada, produce mascara crisp de instancias de capacho por vista y contrato explicito diagnostico/no entrenamiento; proyeccion ortografica declarada sin matriz pinhole ficticia. Compilacion y grafo pasan; ejecucion aun pendiente. Esta prueba de exportacion no acepta la geometria restante ni apariencia como madurez.

### Supervision 15 octubre 02:47 Colombia
V38 completo58,32s,minRAM13,593GiB,3/3 pares revisados visualmente. Verificacion raster exacta pasa: paleta sin colores ajenos, pixeles y bbox coinciden;26/29/26 instancias visibles. Esto no es recall del modelo ni cobertura fisica. Geometria aun7 contactos; excluido entrenamiento. Campo historico occlusion_proxy es no-llenado de caja, NO oclusion medida. Recuperacion audit_pose_reprojection_v2 completa6,24s: RGB32/32 refits, fusion0/32,gap32/32; compatibilidad con estimacionesRGB seleccionadas, no exactitud absoluta. Errorv1 preservado; no repetir cola. V39 encadenado inferencia full960 pesos existentes sobre3 RGB aislados de mascaras/morfologia. Identificadores ordinales no son tiempos de vuelo; piloto ortografico no sustituye dron. Antes sin procesos propios/lock,15,735GiB libres.

### Supervision 15 octubre 02:52 Colombia
Sin proceso propio/lock al inicio,15,405GiB libres. Evaluador separado nuevo: correspondencia uno-a-uno por confianza,IoU mascara>=.5,agnostico clase,denominador cualquier instancia con pixeles visibles. Full960:19/81(23,46%recall),precision22,62%;full1280:7/81(8,64%),precision11,67%. No81 frutos unicos: tres vistas de una planta con geometria aun invalida, no vuelo ni transferencia real. 1280 no aceptado como mejora. V41 completo14,24s,minRAM13,765GiB; se encadenaV43 tiles640/20%solapamiento. Grafo valido con evaluador registrado. Diagnostico de11150 poses publicas emparejadas: discrepancia centros mediana4,306cm,p90 10,608cm;rotacion mediana1,500grados,p90 3,099. Son diferencias entre estimaciones, no error contra verdad ni prueba causal. Historicos preservados; sigue pendiente diagnosticar fusion y preparar captura con dron.

### Supervision 15 octubre 02:57 Colombia
V43 completo22,24s,minRAM13,024GiB;tiles64016/81 aciertos(19,75%recall,17,20%precision). V45 completo14,24s,minRAM13,200GiB;tiles96015/81(18,52%,15,15%). Cuatro condiciones terminadas3/3cada una;full960 sigue mayor recall en muestra, no seleccion definitiva. FinV43 a heartbeat58s de revision, no suspension. Se genera contrato semantico GazeboV47 desde JSON exacto y se prepara V48 exportacion real de una planta con mallas,UV,albedo,rugosidad,normales e identidades individuales. Sin marcadores ni vuelo: ensayo de assets, no trayectoria ni seguridad. Materiales de revision no equivalen aun al shader Gazebo;7 contactos siguen bloqueando aceptacion. V48 arrancado versionado, sin otros trabajos propios activos;preserva campañas.

### Supervision 15 octubre 03:02 Colombia
V48 completo36,26s,minRAM15,270GiB. Validacion estatica:41mallas824185triangulos,todos con UV;indicesOBJ y rutas validas;35referencias de cada albedo/rugosidad/normal;33identidadescalyx coinciden con JSON fuente. No confundir33capachos con todas las unidades reproductivas. WSL denego consulta en sandbox; acceso escalado permitido,Ubuntu24.04,sin procesosGazebo coincidentes. No fallo de simulacion. V49 captura real breve con check_gazebo_field,particion aislada,admision8GiB,reserva2GiB y timeout600s; dos camaras, NO vuelo controlado. Persisten7contactos y diferencia de shader; no aceptacion de entrenamiento. Finexport08:01:14 a heartbeat08:02:32:78s de revision, no suspension.

### Supervision 15 octubre 03:07 Colombia
V49 completo24,26s,minRAM12,576GiB;SDF valido,2/2RGB recibidos,simulador cerrado y lock ausente. Revision visual rechaza encuadre: planta diminuta en overview y casi fuera de drone_camera; transporte exitoso no significa captura util. V50 versiona SDF y manifiesto, reutiliza mallas/texturas por rutas absolutasWSL y cambia solo camaras. Envolvente medida en mallas[-.478,-.491,0] a[.526,.338,1.125]m,ajuste por esfera yFOVvertical con15%margen. Escala del modelo no equivale a dimension real calibrada. Captura repetida limitada,particion aislada. No vuelo/controlador,marcadores ausentes;7contactos y shader pendientes. RAMlibre14,461GiB antes de retry. FinV49 aheartbeat125s de espera de revision,no suspension.
V50 completo24,26s,minRAM12,737GiB;2/2vistas revisadas,planta completa con margen. No aceptacion fotometrica: sombreado foliar marcado. V51 ablacion controlada elimina solo35elementosnormal_map delSDF,conserva geometria,UV,albedo,rugosidad,camaras y luces;captura versionada en curso. No se adopta automaticamente ausencia/presencia de normales por preferencia visual.

### Supervision 15 octubre 03:12 Colombia
V51 completo20,23s,minRAM12,581GiB;2/2vistas revisadas,sinGazebo/lock al consultar,RAM14,527GiB. Diferencia A/B normales muy pequena:5600/1228800 y3747/1228800pixeles cambian,maxcanal2/255;media canal.001723/.001171 sobre imagen completa(no ROI). No demuestra mejora de fidelidad ni que normales expliquen sombreado marcado. Originales preservados. V52 inferencia960 sobre4RGB realesGazebo,on/off ydosvistas,soloRGB,IDsordinales no tiemposvuelo. Sin mascarasverdaderas de estasvistas,aun no medir recall. Siguiente: revisar predicciones y validacion de captura/control; legacy prepare_neo_flight usa estado exacto delsimulador,no reutilizar como estimadorpublico.

### Supervision 15 octubre 03:17 Colombia
V52 completo20,31s,minRAM13,190GiB;4/4archivos verificadoshash. Predicciones aceptadas15overview/20frontal tantoon comooff;no implica aciertos. Fin08:15:14 aheartbeat08:17:32:138s de revision,no suspension. Sinproceso/lock,RAM15,660GiB. Nuevo capturador acotadoV53 agrega sensorespanopticos colocados comoRGB,espera6frames y conserva solo pares con timestamp exacto;buffer2s,timeout120s,termina solo servidor propio. Dosvistas estaticas,no vuelo. Compilacion ygrafo pasan. Mascaras reservadas al evaluador,no alestimador. Captura versionada encadenada;7contactosgeometricos siguen impidiendo entrenamiento aceptado.
V53 completo22,25s,minRAM12,681GiB:2/2 pares RGB/panopticos con timestamp exacto1s. Decodificacion nativa confirma solo etiquetas0/1 y29/27instancias visibles; incluye fragmentos de1pixel. RGB identicos pixel a pixel aV52,permiten reutilizar inferencia sin GPU adicional. V54 emparejamiento por confianza,clase agnostica,IoUmascara>=.5:6/29 overview y9/27 frontal;total15/56 apariciones(26,79%recall),15/35predicciones(42,86%precision). Son dos vistas de una planta con organos repetidos,no56capachos unicos ni localizaciones3D. Siguiente: preparar piloto acotado con marcadores publicos y corredor seguro;7contactos y fallo de fusion siguen pendientes. No aceptacion de entrenamiento ni cierre de campaña.

### Supervisión 15 octubre 03:26 Colombia
Preparación pequeña de vuelo con una planta y marcador0 DICT_4X4_100, lado15cm(heurística). V55 rechazado por encuadre en3/3estaciones a y=-2,6m; preservado. V56 usa y=-3,2m,recorrido lateral50cm y3estaciones;3/3encuadres planificados pasan, margen conservador52,52cm incluyendo esfera dron,terreno y AABB de planta/marcador. El controlador físico usa estado exacto privadamente; no se entrega esa telemetría al estimador. Calibración pública contiene ID/tamaño/diccionario/cámara, no poses mundiales. Etiqueta capacho1 preservada, sin reclasificación fenológica. GPU sin Blender/Python propios y sin gz sim al comprobar;RAM15,73GiB. Lanzado drone_short_v56 con admisión8GiB/reserva2GiB,5Hz y límite450s del ensayo. Pendientes: avance real, margen ejecutado, decodificación ArUco y pares de captura. No aceptación geométrica:7contactos siguen pendientes; no sensor público ruidoso implementado en este piloto aún.

### Supervisión 15 octubre 03:31 Colombia
V56 completó3/3estaciones,10,608s simulados;60,38s del trabajo guardado(50,65s runtime),mínimoRAM11,974GiB;sin error. Margen ejecutado mínimo50,48cm. Fin08:30:06 aheartbeat08:31:02:56s de revisión, no suspensión. Sin procesosgz ni lock al consultar. V57 verifica54/54pares exactos legibles,0excluidos,ArUco0 decodificado54/54;vídeos onboard160/160 ychase159/159cuadros decodificados. Revisión visual de muestra central:planta y marcador completos,apariencia estilizada,detalle foliar pendiente. Copia pública contiene soloRGB,tiempos ycalibración sin pose mundial. V58 inferencia full960 encadenada sobre54RGB;avance comprobado15/54archivosNPZ. EvaluadorV59 preparado,solo se ejecuta al terminar inferencia. No confundir54apariciones temporales coninventario único;no entrenamiento aceptado,7contactos pendientes. No localización3D todavía.

### Supervisión 15 octubre 03:36 Colombia
V58 completo54/54,102,40s,minRAM12,863GiB,sinfallo. Fin08:34:37 aheartbeat08:36:02:85s de revisión,no suspensión. V59 verifica hashes de máscaras y empareja por confianza IoU>=.5:60/1522apariciones TP,recall3,942%,precision6,445%(931predicciones aceptadas). Apariciones repetidas,no inventario único. No comparar como ablación controlada conV54:distancia,resolución ycamara distintas. V60 usa únicamente RGB/calibración pública:IPPE sin refinamiento37/54poses estimables,17ambiguas;subpixel50/54,4ambiguas. No prueba exactitud absoluta. V61 seguimiento óptico/asociación y triangulación robusta iniciados en CPU desde predicciones cacheadas yposes públicas;sin máscarasverdaderas ni telemetría exacta. Candidatos provisionales,no conciliados ni evaluados3D. Se mantiene reserva2GiB y entrenamiento bloqueado por7contactos.
El primer lanzador V61 no dejó proceso,lock ni archivos; causa no establecida. Reintento de lanzamiento versionado launch_retry1 con stderr explícito y acceso escalado, evitando duplicado. No contar primer intento como ejecución efectiva.

### Supervisión 15 octubre 03:41 Colombia
V61 falló tras guardar54/54observaciones:TypeError por clave observations duplicada al serializar fit. RecuperaciónV62 renombra input_observations y reutiliza JSONL completo sin repetir seguimiento/inferencia.246trayectorias con pose:13candidatos estimados,199conmenos3observaciones,24sin geometría consistente,10rechazos reproyección. V63 evaluador privado transforma marco ArUco(xderecha,yarriba,zafuera) a mundo según plano normal-Y;matching de cardinalidad máxima a<=5cm:4objetos distintos/33inventario total(12,12%),4/13candidatos. No usar33como unión observable certificada ni4/13como precisión de asociación. Candidatos no conciliados;centro máscara aproximado frente a centro capacho. Sin procesosPython/Blender propios al comprobar. V64 encadena recortes640 solapamiento20% sobre mismos54RGB/pesos/umbral para aislar resolución;no nuevo vuelo,no reentrenamiento. EvaluadorV65 preparado. Campaña pendiente,7contactos y fusión no resueltos.

### Supervisión 15 octubre 03:46 Colombia
V64 completo54/54,164,49s,minRAM13,221GiB,sinfallo. Fin08:45:33 aheartbeat08:46:02:29s revisión,no suspensión. V65evalúa455/1522apariciones correctas(29,895%recall),precision43,919%(455/1036),IoU>=.5. Mejora frente full96060/1522(3,942%) en mismosRGB,pesos,umbral;una planta,no transferencia ni conclusión general. V66 full1280 encadenado,23/54NPZ guardados al comprobar;mínimoRAM13,534GiB. V67evaluador preparado. V68 adaptador privado existente aplicado a telemetría delpiloto:52incrementos relativos por escala low/nominal/high;timestamp continuo,marco cámara previa,covarianza válida no nula,contrato estricto sin mundo.20msdesfase yruido/deriva heurísticos,no IMU calibrada. Primer frame anterior al desfase excluido antes de formar incrementos;no rellenar con pose exacta. V69 seguimiento desde recortes preparado con corrección de campo duplicado;pendiente ejecutar y evaluar3D.7contactosgeométricos yfallo fusión siguen pendientes.

### Supervisión 15 octubre 03:51 Colombia
V66 completo54/54,96,38s,minRAM13,094GiB,sinfallo. V67:447/1522apariciones TP,recall29,369%,precision45,015%(447/993);tiles640455/1522,29,895%/43,919%,164,49s. Full1280 casi igual en este piloto,menor coste medido;no selección definitiva. Fin08:48:44 aheartbeat08:51:02:138s revisión,no suspensión. V69 seguimiento tiles640 iniciado,38/54observaciones verificadas al revisar,sinfallo. V70 fusión piloto sobre52incrementos públicos por nivel:45correcciones aceptadas,3rechazadas,4sin pose visual;mediana reproyección marcador low5,420px,nominal9,116px,high13,565px;máximos10,329/15,770/22,399px. Covarianza visual heurística2cm/2grados,no calibrada. Inconsistencia detectada,no fusión validada ni explicación demostrada del fallo histórico. Mantener comparación RGB-only;diagnosticar covarianza,convención ytiempo antes de integrar. V71evaluador3D de recortes preparado para trasV69.7contactosgeométricos permanecen.

### Supervisión 15 octubre 03:56 Colombia
V69 completo54/54,88,37s,minRAM15,519GiB;230trayectorias conpose,19trianguladas,172insuficientes,27sin geometría consistente,12rechazos reproyección. V71evaluador:3/33inventario total a<=5cm frente4/33full960;3/19candidatos,no precisión asociación. Mejora2D no se traduce automáticamente en3D;no seleccionar por recall solamente. Fin08:53:20 aheartbeat08:56:02:162s revisión,no suspensión. Sin procesos propios ni lock;V72tiles960 encadenado54RGB para completar4condiciones, evaluadorV73preparado. V74diagnóstico público reinicia pose visual cada incremento:47pasos comparables,mediana discrepancia esquinas0,985/1,799/3,373px(low/nominal/high),menor que fusión acumulada5,420/9,116/13,565px. Visualsola mediana reproyección0,0227px,máxima0,177px;no exactitud absoluta. Evidencia sugiere componente acumulativa;causa no demostrada. Covarianza visual sin correlación rotación/posición,desfase yambigüedad siguen hipótesis. No ajustar contra verdad ni integrar fusión aún. Siguiente:evaluarV72,aislar covarianza con prueba pública yresolver contactos antes entrenamiento.

### Supervisión 15 octubre 04:01 Colombia
V72completo54/54,128,43s,minRAM12,884GiB,sinfallo;V73tiles960448/1522TP,recall29,435%,precision43,118%(448/1039). Cuatro condiciones piloto completas,no campaña completa. V75 prueba aislada pública usa covarianza6x6 por Jacobiano de proyección en coordenadas canónicas;ruido esquina0,5px supuesto,conserva correlación traslación/rotación,ningún ajuste con verdad.52poses/nivel,48correcciones aceptadas,0rechazos;mediana reproyección0,210/0,191/0,201px low/nominal/high,máximos1,685/3,174/6,197px. No certificar calibración ni extrapolar a histórico. V76/V77 mismas asociaciones tiles640,fusión nominal:19candidatos,9/33inventario a<=5cm. Control soporte temporal común48cuadros:V78/V79 fusion27candidatos12/33;V80/V81 visual20candidatos5/33. Mismas227trayectorias con pose en comparación común;esto aísla mejor efecto pose. Huecos propagados reducen resultado9vs12,no aceptar automáticamente. Inventario33 no observablecertificado;ninguna fracción candidatos equivale a precisión asociación;sinconciliación. Siguiente:extraer covarianza a módulo con pruebas y auditar sensibilidad/consistencia histórica antes de integrar;resolver7contactos previo entrenamiento. SintrabajoGPU activo,operación actual análisisCPU/pruebas pequeñas.

### Supervisión 15 octubre 04:06 Colombia
Sintrabajos propios ni lock al inicio,RAM15,69GiB. Covarianza de proyección extraída a marker_motion_fusion.marker_projection_covariance:valida inputs,profundidad,rotación,intrínsecos;SVD falla ante degeneración,preserva correlaciones ydocumenta ambigüedad/no calibración.6/6pruebas pasan(fusión5,contrato1);grafo válido151/260. V82 reproduce V75 numéricamente(low/nominal/high medianas0,210/0,191/0,201px). Replay histórico añade opción explícita --projection-covariance,sin cambiar default:deshace relación canónica solo para recuperar esquinas del marcador decodificado yrota covarianza6x6 de vuelta,posescanónicas no retransfomadas. V83 replay histórico público versionado lanzado convida ancla0,5s;no GPU ni re-inferencia,verdad excluida. Revisar resultado ycompatibilidad de observaciones antes adopción. Sigue pendiente7contactos yresto campaña.

### Supervisión 15 octubre 04:11 Colombia
V83 completo3/3perfiles7972/7972cuadros cadauno,50,30s,minRAM15,591GiB;sinproceso/lock trasfinal. Nominal11007/11150correccionesvisuales aceptadas,1058marcador-cuadrospropagados,42anclasexpiradas. Fin09:10:22 aheartbeat09:11:03:41s revisión,no suspensión. V84 mismo soporte/detecciones/identidades de32objetos controlRGB:covarianza proyección23/32refits,mediana fracciónresiduo<=3px0,9583;fusiónvieja0/32,controlvisual32/32. V85 limita poses fusionadas a cuadros donde el marcador fue observado:24/32,mediana1.0. Por tanto huecos explican solo parte del problema residual;8objetos aún fallan. Son objetos seleccionados porcontrolRGB,compatibilidad no exactitud verdadera ni prueba independiente. Se preservan V83-V85 ylista fallos. No integrar como sustitución aprobada todavía. OperaciónCPU de diagnóstico,no esperaRAM ni GPU bloqueada. Próximo:inspeccionar rechazos porobjeto y separación de residuos/covarianza, además7contactosgeométricos pendientes antes entrenar.

### Supervisión 15 octubre 04:16 Colombia
Sinprocesos propios ni lock al iniciar;actividad es diagnósticoCPU, no esperaRAM. V86 examina todas las ternas de los8rechazos con mismo soporte visual/fusionado yumbrales intactos.7objetos:56u84ternas porobjeto,todasrechazadas porparalaje fusionado0,870–1,062grados;visual3,305–3,598grados. No interpretar paralaje visual como real:puede incorporar ruido de pose,requiere evaluación independiente. Octavo objeto:816ternas;fusión752estimables y64rechazos reproyección frentevisual420/395(+1paralaje);refit conjunto sigue fallando reproyección, por tanto no es ausencia de terna viable. No relajar3grados ni forzar resultados. robust_triangulate ahora registra hypothesis_outcomes al rechazar todas hipótesis;misma decisión/mismosumbrales.12/12pruebas(localización8,conciliación4) pasan;grafo151/260válido. Próximo:comparar paralaje con referencia privada solo evaluador yrevisar vista residual deloctavo;mantener controlRGB yvariantefusionada separadas.7contactosgeométricos ycampaña completa pendientes.

### Supervisión 15 octubre 04:21 Colombia
Sinproceso propio ni lock;diagnósticoCPU. V87evaluador privado interpola telemetría exacta al timestamp RGB(sin desfase artificial) yrota rayos de centroides detectados. En7casos rechazados,baseline máximo6,08–7,72mm yparalaje0,0667–0,2469grados,frente3,3–3,6grados visuales. Evidencia de paralaje visual espurio porerrorpose;rechazo fusionado bajo3grados es coherente con falta de movimiento,no regresión demostrada. No enviar posesprivadas alestimador ni usarpara ajustarumbrales. Centroides/IDs siguen estimados,no prueba correspondencia correcta. Octavo objeto baseline1,943m,paralajeprivado44,907grados. V88 DLT con18vistas:visual residuosmáx7,121px,fusion4,281px;fusion supera3px en últimas2vistas(3,087/4,281). Fallo no falta paralaje;revisar estabilidad soporte/refit sin eliminar datos arbitrariamente.32/32controlvisual no debe convertirse en objetivo absoluto de mejora dado7casosespurios. Siguiente:diagnóstico delrefit robusto/observaciones finales,despuéscontactosgeométricos pendientes antesentrenamiento. Campaña no cerrada.

### Supervisión 15 octubre 04:26 Colombia
Se revisa robust_triangulate:elige soporte por hipótesis yrefit finalpuede cruzar límite3px;V88documenta reproyección residual,no se cambia algoritmo/umbral para rescatar un objeto. Se retoma bloqueo geométrico. V89 pruebaaislada desdeV37:4entrenudos base1,75→3,5cm conradios~1cm;ningún órgano,radio,identidad,conexión niotraslongitudes cambia(comparaciónJSON íntegra comprobada). Es hipótesis ingeniería,no medida botánica ni adopción. AuditoríaBlender completa acotada lanzada con6,5GiBadmisión y2GiBreserva;sin campaña grande ni entrenamiento. Revisar contactos antes de rendercomparativo;originalV37preservado. Campaña pendiente.
V89 terminó24,24s,minRAM15,364GiB:1767objetos auditados,6contactos físicos frente7V37. Desaparecen5contactos basales,pero aparecen otros cruces ycontacto pecíolo-capacho;violaciones separación12→32,intersecciones blandas144→180. No aceptar como mejora integral ni entrenamiento;estado inválido. Revisar variante más localizada que no desplace copas completas. No queda ejecución pesada activa.

### Supervisión 15 octubre 04:31 Colombia
SinprocesoPython/Blender ni lock al iniciar. V90pruebaaislada parte deV37(original,sin separaciónV89):radio base×0,8 ytope de radio inicial basal×0,8 en4ejes,conservando radios menores posteriores.36segmentos cambian radio;comparaciónJSON verifica ningún cambio enotroscampos/órganos/topología ni ejes centrales. Se comprueba radio no creciente por eje ycada hija menor queparental en nodo. Hipótesis ingeniería para distinguir grosor de ubicación,no parámetro botánico validado ni adopción estética. AuditoríaBlender1767objetos prevista,guardada conreserva2GiB,admisión6,5GiB;sin gran campaña. Revisar conteos y aspecto antes adoptar. Fusión permanece experimental y se preservan evidencias privadas únicamente evaluador.

V90 terminó en26,27s efectivos,0s espera registrada,minRAM15,187GiB:1767objetos,6contactos físicos,144intersecciones blandas y12violaciones separación. Solo desaparece contacto axis45/axis67;persisten4basales y2remotos. No adoptar:reducción de grosor insuficiente y revisión visual pendiente. Siguiente:inspeccionar geometría real de encuentros y exclusiones de contacto por conexión antes de otro ajuste localizado;no relajar validación ni entrenar con esta variante. Campaña integral pendiente.

### Supervisión 15 octubre 04:38 Colombia
V91:2/2vistas reales Blender Workbench de baseV37 sin alterar geometría;solo ocultación de resto ycolores diagnósticos, no materiales finales.12,24s efectivos,0s espera guardada,minRAM15,220GiB,sin fallo. Revisión visual:cuatro salidas oblicuas insertadas en base corta ygruesa,con solapamiento local;las vistas no prueban por sí solas legitimidad de todos los contactos. Auditor ya excluye segmentos incidentes por IDs explícitos node_start/node_end;no es ausencia general de exclusión parental. Contactos base_segment2/axis1 ybase_segment3/axis23 alcanzan más allá del segmento incidente;contactos entre primeros segmentos de ejes vecinos también requieren localización. No ampliar excepciones globales ni reducir radios indiscriminadamente. Siguiente:medir posición de triángulos en contacto respecto al nodo para separar unión local de cruce remoto ydefinir reparación justificada. Original7contactos sigue inválido;V90seis,ninguno aprobado entrenamiento. Sin campaña grande ni consulta de semillas reservadas.

### Supervisión 15 octubre 04:43 Colombia
V92 completo7/7pares,8,21s efectivos,minRAM15,358GiB,sinfallo. BVH trianguladoepsilon0 ysegmento-triángulo confirman intersecciones en todos;no son solo tolerancia. Contactos base/primer eje:distancia a salida hasta2,907 y2,765cm (fracción axial0,84/0,73 delprimersegmento). Entre ejes vecinos:solape próximo a salida deleje superior yentre0,37–0,66 delsegmento inferior. Dos cruces remotos interiores confirmados. Método no cubre casos coplanares;no usa vértices de triángulo como si fueran puntos de intersección. No cambiar exclusiones. V93 prueba intermedia desdeV37:4longitudes base1,75→2,5cm;otroscampos íntegros verificados,metadatos heuristic/notaccepted. Objetivo reducir desplazamiento de copas respectoV89(3,5cm),sin asumir mejora antes auditoría. Guardadmisión6,5GiB/reserva2GiB.

V93final24,25s,minRAM15,210GiB,1767objetos:13contactos físicos,172blandos,31separación;rechazada. Elimina3contactos entreejesbasales pero conserva2base/eje ycrea cruces remotos. La respuesta no es monótona con separación:V37=7,V93=13,V89=6. No continuar barrido ciego de longitud basal. Próximo:corrección local de trayectoria de unión con extremos posteriores preservados,representada en morfología yvalidada aguasabajo;no excepción global del auditor. Campaña pendiente.

### Supervisión 15 octubre 08:14 Colombia
Últimojob V93final09:45:54Z;sin procesosPython/Blender nilock al recuperar. Windows LastBootUpTime04:53:44Colombia:hubo arranque posterior,pero duración de suspensión/apagado ycausa no inferidas. Intervalo no contabilizado como ejecución. RAMlibre17,54GiB. V94 diagnóstico de viabilidad únicamente en intérprete:desplazamiento radial0,8cm*sin(pi*t)^2 en cuatro primeros tramos basales,extremos comprobados inmóviles;órganos/restoescena no cambiados. No define arquitectura objetivo ni se exporta a dataset. Si mejora,requerir contrato morfológico yconsumidores coherentes antes adopción. Auditoría completa ydosvistas encadenadas bajo guard/reserva2GiB;no dependencias ni cambios enproducción.

V94 completo36,02s efectivos,minRAM11,992GiB,1767objetos y2/2vistas revisadas. Contactos físicos7→2:desaparecen5basales,quedan exactamente2remotos originales;blandos144sin cambio,separación12→16. Evidencia de viabilidad local con extremos fijos,NO aceptación. Seis puntos POLY producen codos visibles;materiales diagnósticos yresto oculto. Distancias insuficientes permanecen(base2/axis1_0:0,00847unidades frente0,024requeridas). Próximo comprobar curva suavemente muestreada yseparación antes extensión contractual morfológica;posterior integración debe mantener coherencia de colisiones/Gazebo/exportación. Ningún candidato usado para entrenamiento.

### Revisión visual solicitada por usuario: V95
Tres renders Cycles reales(whole/detail/side),misma planta814144,V37+deformación diagnósticaV94 exacta,apariencia mate/nervaduras oscuras/cellrelief/gradedcolor delpilotoV38.30,17s,minRAM13,416GiB. No son3plantas independientes. JSONguardado conservaV37;intervention.json documenta4curvasmodificadas,manifestdeclara divergencia diagnóstica/no dataset. Comparación con referencia05silueta y06detalle:corrección basal casi imperceptible aescala completa;no afirmar mejora general porresolver contactos. Persisten hojas planas/horizontales repetidas,centro concentrado ybase relativamente desnuda,capachos redondeados conretícula poco ramificada frente reales. Encuadre/iluminación no calibrados,no métrica de fidelidad. Se entregan3vistas yreferencias originales sin retoques.

### Supervisión 15 octubre 08:20 Colombia
No procesosPython/Blender al inicio,RAM14,79GiB. V96 diagnóstico aislado aumenta6→33muestras en4curvas basalesV94,misma amplitud0,8cm yextremos;interpola la trayectoriaoriginal ymuestrea término sin² para distinguir discretización de forma. No cambia morfología ni candidato aprobado. Auditoría ydos vistas encadenadas,guardreserva2GiB.

V96completo18,17s,minRAM14,220GiB:1767objetos,2contactos físicos144blandos16separación,igualV94.2vistas revisadas:menor facetado pero flexión cerrada persiste;no atribuir todo a resolución. Circunradio de ternas consecutivas registrado en curvature.json como diagnóstico numérico,no umbral botánico ni prueba de autointersección. No adoptar ni ampliar contrato por esta prueba;reparación debe controlar curvatura/grosor además de contactos externos. Campaña yentrenamiento pendientes.

### Cambio explícito de prioridad del usuario: fidelidad visual
No centrar continuidad únicamente en colisiones basales. V97 desdeV37:267hojas nodales y33capachos,identidades/topología preservadas,curvatura basal diagnóstica no aplicada. Inclinación foliar112–145grados(terminal95–127),azimut exterior convariación±65grados respecto posición nodal aproximada;escala exterior1,08–1,20/interior0,85–1,0,relieve0,14–0,19,curl−0,16. Capachos longitud×1,30/radio×0,96/punta0,20;frutos ymadurez intactos. Todos valoresheurísticos,prueba visual combinada,no ensayo causal aislado ni entrenamiento aprobado. Se elimina elevación de reparación yse reorientan hojas deliberadamente;colisiones pendientes no son prioridad exclusiva. Render3vistas conmisma iluminación/materiales quecomparadorV95.

V97 comparación inspeccionada:hojas más caídas yrelieve mayor,capachos laterales alargados;centro aún excesivamente apilado yvarios capachos se perciben redondos segúnorientación. No declarar fidelidad conseguida. Invariantes verifican mismosnodos/IDsfoliares ytodos campos reproductivos exceptoenvoltura cáliz intactos. Sin nuevoentrenamiento;colisiones no reauditadas. Próxima prioridad visual:disminuir apilamiento central ymejorar perfil distal/nervaduras,concomparación antes/después.

### Supervisión 15 octubre 08:28 Colombia
V98 desdeV97:176hojas interiores escaladas/reorientadas;267IDs yhojas terminales preservados,capachos sin cambio. Cociente suma largo×ancho0,7317,proxy,no área superficial ni oclusión.3/3renders40,20s,minRAM10,659GiB,sin fallo. Revisión frenteV97 yreferencias:centro menos apilado,órganos mejorseparados visualmente,pero copa global más delgada;no asumir que aclarar siempre mejora similitud ni adoptar como óptimo. Parámetros guardados con trazabilidad;colisiones pendientes. Próximo priorizar perfil/nervaduras capachos ybalance follaje concomparaciones,evitar retorno exclusivo a base.

### Correcciones usuario: orientación, luminosidad y textura V99
DesdeV98:33pedicelos62–72grados bajo horizontal;267hojas sinrelieve geométrico(surface_relief_ratio0,curl0,twist±7). Conserva caída general existente;detalle fino mapas normal0,40 ybump celular0,18/distancia0,003. CalyxalbedoSCREEN0,38 concolorclaro conservando textura,nervaduras yroughness;sin emisión ni cambio madurez. Heurísticas visuales,no medicionesbotánicas. Revisión de hoja superior incluye distancia origen lámina a centro anillo extremo pecíolo en coordenadasmundiales;no basta asociaciónJSON. Render3vistas solicitado, advertenciascolisión siguen pendientes.

V99falló antesrender IndexErroralbedo sinlink;preservado. V100recuperación materialconstante/texturado:3/3renders38,21s,minRAM10,920GiB. Inspección:capachos másverticales/claros,hojas sincorrugación geométrica;acabado cálizdemasiadouniforme aún,no acabadofinal. V101verificación realBlender267/267cadenas:raízlámina/extremopecíolo max1,1944e-5cm,nodo/extremopecíolo max1,2014e-5cm,0pecíolosfaltantes. Hoja másalta axis59_node11 conectada;apariencia flotante puede deberse a vista decanto ypecíolofino,no desconexión demostrada. Estos números validan continuidadposicional,no colisiones ni asociaciónvisual inequívoca conhojaseñalada. No etiquetar colorcapacho como madurezfruto. Próximotexturas/nervaduras/variacióncolor sinvolver a geometríarizada.

### Supervisión 15 octubre 09:14 Colombia
Prioridad materiales V102,misma morfologíaV99/V100 y267hojas sin relieve geométrico. Aclarado tejido aleatorizado porobjeto0,24–0,43,variaciónespacial suave yreaplicación máscara nervadurasdespués delaclarado(exponente0,58,coloroscuro0,055/0,035/0,035). Valores heurísticos,no madurez. Motivo:SCREENanterior aclaraba también venas. Sin nuevasmallas,poses ni etiquetas.3renders comparablesguardreserva2GiB.

V102terminó3/3renders38,21s,minRAM10,387GiB,sinfallo. Detalleinspeccionado frenteV100:retícula capachos másvisible manteniendo tejido claro ycaída;no se afirma fidelidad final,variación sigue limitada yhojas aún tienen apariencia lisa. Geometríaidéntica aV100,por tanto comprobacionesposicionales anteriores aplican,pero no sustituyen auditoría completa. Próximo:texturas foliares finas yrevisión variasvistas/referencias,seguida comprobación anotacionespequeña;mantener prioridadesusuario ycampañapendiente.


### Supervisión 15 octubre 09:19 Colombia — V103
Prueba foliar solo material: máscara UV existente de nervaduras, mezcla clara0,32 y bump0,22/distancia0,002, sin desplazar malla. Corregidos metadatos heredados que declaraban intensidades distintas a las ejecutadas. Tres renders completados36,19s efectivos,0s espera registrada,minRAM11,059GiB,sin fallo. JSON morfológico idéntico aV102. Comparación visual whole/detail: cambio muy leve, no demostrar mejora ni adoptar. Persisten láminas de aspecto plano y distribución superior angular; no compensar con rizado geométrico. comparison.json registra diferencias de píxeles (no métrica de fidelidad). Siguiente verificar materiales efectivamente asignados y señal UV a escala de órgano antes de aumentar intensidades. Campaña y validación física pendientes.


### Supervisión 15 octubre 09:26 Colombia — V104/V105
Auditoría Blender V104:267/267 hojas con UV y material graduado realmente conectado al shader V103; cuatro materiales usados (74/91/65/37 hojas), máscara512×512. No es un fallo de asignación. Máscara inspeccionada: venas principales/secundarias dominantes, retícula de órdenes altos tenue. V105 aísla la hoja de mayor área y compara material anterior/nuevo sobre idéntica malla, cámara y luz;2/2renders18,17s efectivos,minRAM11,711GiB,0s espera registrada,sin fallo. Textura fina sí visible a esta escala,pero V103 apenas modifica apariencia y no resuelve parecido de lámina. No adoptar. El aislamiento oculta otros órganos solo para diagnóstico;no representa planta ni dato de entrenamiento. Siguiente:control independiente del contraste de señal débil de venación de órdenes altos, manteniendo primarias y geometría,primero escala órgano,luego planta completa si aporta. No alterar malla para simular textura. Campaña integral pendiente.


### Supervisión 15 octubre 09:31 Colombia — V106/V107
Máscara de nervaduras existente con exponente0,35,mezcla0,55,bump0,30/distancia0,004:eleva señal tenue sin sustituir texturas ni desplazar vértices. Intensidad NO equivale a orden anatómico;no se afirma aislamiento exacto de terciarias/cuaternarias. V106 dos renders de órgano18,17s,minRAM12,213GiB:retícula fina ahora perceptible,manteniendo nervaduras principales. Encadenado inmediatamente V107 tres vistas de planta36,19s,minRAM11,766GiB,espera guard0,000809s,sinfallos. Revisadas frontal/detalle/lateral:beneficio a escala general pequeño;persisten láminas de silueta rígida ydistribución angular superior. JSON idéntico aV102 comprobado. Material provisional,no entrenamiento aprobado. Próximo evaluar abombado global suave/caída ydistribución exterior sin introducir textura geométrica rizada;posterior smoke de anotaciones. Mantener pendientes colisiones ycampaña científica.


### Supervisión 15 octubre 09:36 Colombia — V108
Prueba morfológica acotada sobreV99 conmaterialV107:92hojas marcadas terminales pasan a130–150grados ypecíolo×0,75. Semilla814252,heurística visual,no intervalo botánico medido. No cambiar malla foliar ni texturageométrica;resto decampos incluidos cáliz/fruto/topología comprobados intactos.3/3renders36,19s,minRAM12,007GiB,0s espera,sinfallo. Frontal muestra másláminas terminales de frente ymenos apariencia flotante;vista lateral conservaapilamiento yformas rígidas. No afirmar solución final ni mejora botánica cuantificada.267pecíolospresentes;máxima distancia raízlámina/extremopecíolo 1.228781230931777e-05cm (continuidadposicional,noauditoría colisión). Conservar provisional ymostrar comparación. Próximo revisar abombado suave/caída global yencuentros angulares,sin microcorrugación geométrica;campaña yvalidación pendientes.


### Supervisión 15 octubre 09:41 Colombia — V109
Comprobación de anotaciones sobreV108/materialV107:3RGB y3máscaras de instancia reales,46,21s efectivos,minRAM11,605GiB,0s espera,sinfallo de render. Auditor externo inicial falló por tratar ID0fondo como unidad reproductiva;corregido sin repetir renders yregistrado. Conteos de píxeles/cajas/paleta/IDs contra morfología válidos:28/28/33capachos visibles porvista,89apariciones repetidas deuna planta,no89instanciasúnicas. Máscaras/RGB900×1000. Es prueba de contrato raster,NO validación física ni aceptación entrenamiento. Advertencia del esquema heredado:occlusion_proxy=1−relleno máscara/caja,no oclusión;excluir de consumo. Madurez es metadato sintético latente,apariencia sobrescrita no habilita objetivos de madurez. Siguiente mantener prioridad visual ypreparar contrato estricto de instancias sin campos engañosos antes consumo dataset;campaña ysemillas reservadas siguen pendientes.


### Supervisión 15 octubre 09:46 Colombia — V110/V112
Exportador reproducible local V110 genera contrato por lista permitida:3vistas,89apariciones,33IDs únicos;hashesRGB/máscaras/fuentes,conteos contrastados contra píxeles. Excluye maturity,calyx_state,reproductive_stage,occlusion_proxy. Solo evaluador diagnóstico,no entrenamiento aceptado. Revisión visual referencias03/06 evidencia verde foliar más frío que oliva uniforme delrender;sin calibración de luz/cámara no inferir color físico. V111 pruebaalbedo multiplicativo(.72,1,1.12),factor.65 falló IndexError materialconstante antes de imágenes;preservado. V112 maneja materialconstante/texturado:3renders40,19s,minRAM12,563GiB,sinfallo. Geometría ymadurezsin cambios. Detalle muestra follaje menosamarillo;no resuelve silueta plana ni abombado interveinal. Variante provisional;revisarwhole/side antesadopción. Campaña pendiente.


### Supervisión 15 octubre 09:51 Colombia — V113
Revisadas frontal/lateralV112:tono másverde persiste,pero no corrige rigidez. V113 restaura mitad de reducción dimensionalV98 en53hojas conproxyexterior≥0,4;154hojas interiores intactas,267total,poses/frutos/topología conservados. Cociente suma largo×ancho1,03663,no área real ni oclusión.3renders36,19s,minRAM11,649GiB,0s espera,sinfallo;detalle/lateral inspeccionados. Cambio decopa pequeño,no evidencia suficiente de mejor fidelidad;no adoptar poracumular iteraciones. Próximo dejar ajustes mínimos de color/tamaño sobreuna solaplanta:diagnóstico silueta foliar ytramos expuestos demasiado rectos,contraste con referencias ysegundo ejemplar de desarrollo antesgeneralizar. Semillasreservadas intactas,campañapendiente.


### Supervisión 15 octubre 09:56 Colombia — V114
Segundo ejemplar de desarrollo814145 desdeazimuth_control_v24:298hojas,30capachos,94terminales. Transferencia acotada de inclinaciónfoliar112–145/terminal130–150,pecíoloterminal×0,75,curl0/twist±7/relievegeométrico0,pedicelo62–72,cálizlongitud×1,30/radio×0,96/punta0,20 ymaterialV112. No replica reparacionesV37 ni cambiosdimensionalesV97/V98;no comparación causal integral contra814144.3renders38,20s,minRAM11,219GiB,0s espera,sinfallo. Frontal/detalle revisados:láminas planas apiladas yextremos angulares reaparecen;material yorientación de capachos transferibles visualmente,pero fidelidad morfológica aúninsuficiente.298pecíolos presentes,distancia raíz/extremo máxima 1.228781230931777e-05cm. Próximo diagnóstico transversal deforma foliar ydistribución nodal endossemillas,evitar más ajustes mínimos decolor. Evaluaciónreservada intacta,campaña pendiente.


### Supervisión 15 octubre 10:01 Colombia — V115/V116
Diagnóstico realBlender en ambas semillas:565/565hojas tienen solo2vértices porsección transversal aldesactivar surface_relief;no existe control independiente de abombado global. Mediana sag/longitud0,01880 y0,02397;la fórmula reduce flexión cuando dirección severticaliza. No sonmedicionesbotánicas. V116 diagnóstico de viabilidad exclusivamentegeométrico:8subdivisionestransversales,descenso suave de bordes0,06*ancho*u²*sin(pi*t),sin términosperiódicos de textura;raíz/línea central preservadas,UVrecalculadas. No se integraenarquitectura ni dataset:geometry_diagnostic.json declara divergencia delcontrato.3renders38,20s,minRAM11,149GiB,0s espera,sinfallo. Detalle inspeccionado:algunasláminas con sombreado másredondeado,efecto moderado;revisiónfrontal/lateral,segundaplanta yvalidaciónpendientes. Si aporta,formalizar controlmorfológico compartidoantesadopción;no reactivar corrugación fina. Campaña pendiente.


### Supervisión 15 octubre 10:06 Colombia — V117
V116 frontal/lateral revisadas:mejor sombreado transversal local,no cambio radical decopa. Revisión de implementación detecta que punto medio entrebordes asimétricos no equivale a línea delnervio;corrige afirmación anterior de preservación exacta. V117 interpola cada mitad desde _leaf_centerline_point yconserva raíz;aserciones ejecutadas en298láminas de814145:centro error<1e-10,UVfinita0–1.3renders40,19s,minRAM11,153GiB,0s espera,sinfallo. Detalle/lateral inspeccionados:curvaturaamplia visible sinrizado periódico,pero persisten apilamiento yextremos rectos. Sigue diagnóstico intérprete,NO nuevo modelo botánico ni dataset. Antesadopción requiere parámetro morfológico compartido,consumidores yvalidación;sin aceptación por solo render. Campaña pendiente.


### Supervisión 15 octubre 10:11 Colombia — V118/V119
Auditoría distribución ambas plantas:terminal_leaf es bandera de zona distal(i≥8),no extremoúnico;92/94frente48terminal_endpoint cadauna. Aclaración delalcanceV108:inclinó zonasdistales. Mediana distancia axial entre hojas/largo medio0,508/0,388;29/54pares condistancia<0,5largos yazimut<30grados. Proxies,no colisión/oclusión ni ley botánica. V119 experimento acotado sobreV108/materialV112:azimut+75grados en29hojas delsegundo miembrodepares alineados;identidades/número preservados,no usar arco diagnósticoV117 paraevitar mezclar efectos.3renders40,21s,minRAM10,927GiB,0s espera,sinfallo. Detalle revisado:cambia superposición local,pero similitud global no demostrada;frontal/lateral pendientes antesadopción. Contrato deforma ycampaña pendientes.


### Supervisión 15 octubre 10:16 Colombia — contrato V120
V119 frontal/lateral revisadas:sin beneficio global claro, no adoptar giro fijo75. Formalizado control optativo transverse_arch_ratio en Leaf,default0 compatible con archivos históricos;helperpuro leaf_surface separa arco amplio de microtextura. Intérprete usa campo morfológico yrechaza combinarlo concorrugación legacy;validación advierte rango fuera0–0,2(heurístico). Tres pruebas puras pasan:asimetría/centro/raíz/punta/topología,invalidosincluidoNaN,serialización. Reconstrucción Blender298hojas pasa conratio0,06,ninguna conserva malla de2vértices transversales. scripts/export_gazebo_field llama intérpretecompartido;esto es inspección estática,no exportaciónGazebo ejecutada. Grafocontexto actualizado;no cambia presetni entrenamiento. Pendiente igualdad demallas contraV117,regresiónrender/anotaciones ycolisiones. Campaña pendiente.


### Supervisión 15 octubre — V121/V122
Integración del arco amplio: tres RGB y tres máscaras de814145 completadas en46,20s efectivos, mínimo RAM11,709GiB y0s espera del guardián. Primer lanzamiento restringido no produjo job ni Blender; se verificó ausencia y memoria antes de recuperación mediante ejecución autorizada. No se atribuye duración a suspensión. Verificación independiente de paleta y conteos:20/22/19capachos visibles por vista,61apariciones y27identidades únicas; exportación estrictamente de instancias excluye madurez y occlusion_proxy. V122 reconstruye fórmula V117 sobre bordes legacy y compara298mallas integradas: error máximo 2.9802322387695312e-08 unidades de escena, tolerancia1e-6;UV finitas0–1. Frontal revisada:abombado amplio sin corrugación periódica, pero persiste aspecto apilado de copa;no se declara fidelidad resuelta. Exportación Gazebo ejecutada y auditoría física del arco siguen pendientes;campaña y aceptación para entrenamiento pendientes.


### Supervisión 15 octubre — V123/V124/V125
Exportación real de una planta814145 con arco:38mallas,716942triángulos,298hojas y30identidades de capacho. Verificación de índices OBJ, coordenadas finitas y134referencias SDF a recursos pasa.26,19s efectivos, mínimo13,164GiB RAM libre;no suspensión verificada. No es ejecución Gazebo y los materiales exportados son texturas base:el shader de revisiónV112 no se transfiere íntegro. Auditorías Blender completas de1815objetos, variante y baseline misma planta:135contactos físicos cadauna. Diferencia de pares nuevos=0, retirados=0. No atribuir estos contactos al arco ni confundirlos con oclusión. Comparación detallada enarch_contacts_v124/comparison.json. Detalle visualV121 revisado:capachos claros y colgantes,pero hojas aún apiladas;no aceptación para entrenamiento. Siguiente:distribución nodal y reconciliación de materiales antes de evaluar nuevo aspecto con dron;campaña pendiente.


### Supervisión 15 octubre — V126
Prueba aislada de distribución: fase aleatoria por eje, alternancia nodal180 grados y jitter±40, heurística no medida. Conserva298hojas, dimensiones, nodos, inclinación y materiales deV121. Tres renders38,19s, mínimo11,959GiB RAM y0s espera;sinfallo. Comparadas frontal/detalle/lateral contraV121 y referencias03/06:dispersa algunas superposiciones, pero no mejora global convincente;no adoptar.298conexiones verificadas, máximoerror raíz/pecíolo 1.2036781326982013e-05cm. Inspección del intérprete identifica siguiente cuestión:pecíolo recto y lámina comparten orientación inicial;flexión gravitacional decrece al verticalizar hoja. Preparar diagnóstico de postura longitudinal manteniendo conexión nodal y microtextura en material. Campaña pendiente.


### Supervisión 15 octubre — V127
Diagnóstico longitudinal aislado: z=-0,18*L*t² compartido por lámina y nervio; raíz y tangente inicial conservadas, sin corrugación periódica. Valor heurístico, no medición botánica; geometría downstream declarada engeometry_diagnostic.json, no integrada ni utilizable como dataset. Tres renders 40.19s efectivos, mínimoRAM 11.98GiB;sinfallo,0s espera.298conexiones presentes. Frontal/detalle/lateral comparadas conV121 y referencia04, además03/06 previamente revisadas:curva local más perceptible pero copa sigue estilizada y apilada. No adoptar automáticamente mayor flexión uniforme. Próximo:aislar silueta y detalle de hoja frente a campo a escala aparente similar, particularmente hombros basales angulares y uniformidad de láminas;evitar encadenar retoques globales sin evidencia de ganancia. Campaña pendiente.


### Supervisión 15 octubre — V128/V129
Dos hojas aisladas seleccionadas por área mediana/máxima, no por calidad visual, con geometríaV120 y materialesV112. V12820,17s,minRAM12,707GiB confirma que hay microtextura y venación fina;persisten hombros basales angulares y parche triangular superior. V129 reduce perfil basal mediante smoothstep hasta t0,18,solo diagnóstico:dosrenders22,18s,minRAM12,296GiB,sinfallos ni espera. Coinciden ambas identidades entreversiones. Mediana revisada:no resuelve silueta tipoescudo, no adoptar. La regla tampoco representa un seno cordado validado. Antes de otro cambio global, examinar contorno local sin iluminación para separar defecto de silueta y sombreado de arco. No cambios de producción ni aceptación para entrenamiento;campaña pendiente.


### Supervisión 15 octubre — V130: orientación invertida en la base foliar
Diagnóstico topológico identificó causa concreta del parche triangular oscuro:caras del abanico basal recorrían sus vértices al revés respecto a las franjas longitudinales. Antes, áreas orientadas XY del abanico−0,5/−0,75 frente+1 del cuerpo en fixture asimétrico. Corregidos tres caminos:lámina simple,arco amplio yrelievelegacy;solo orden de índices,sin alterar parámetros ni coordenadas base. Cuatro pruebas puras pasan,incluida coherencia de aristas compartidas. Auditoría Blender ejecutada enlos3modos:0aristas compartidas inconsistentes,normales basaleszpositivas. Dos renders20,16s,minRAM12,792GiB,sinfallos ni espera;identidadesmediana/máximacoinciden conV128. Mediana inspeccionada:desaparece parche basal oscuro. La silueta angular persiste y requiere diagnóstico separado;no es prueba de fidelidad botánica completa. ComoSolidify depende de normales,los contactos de malla evaluada deben revisarse después de esta corrección. Próximo regresiónplantaentera/máscaras;campaña pendiente.


### Supervisión 15 octubre — V131/V132
Regresión después de corregir orientación basal:3RGB+3máscaras en46,20s efectivos,minRAM12,072GiB,0s espera,sinfallo. Verificados conteos exactos,paleta,bboxes eidentidades contra morfología:20/22/19visibles,61apariciones y27IDs únicos. Cada máscara difiere en1píxel respectoV121;no afirmar identidad bitabit. Exportador de instancias excluye madurez/estadofenológico/occlusion_proxy. Auditoría mallas evaluadasV132:135pares físicos,0nuevos/0retirados respectoV124;persisten advertencias,no aceptación física. Frontal completa inspeccionada:corrección local de sombreado válida,aspecto global sigue estilizado. Siguiente diagnóstico pequeño con pesos existentes exclusivamente sintéticos ysoloRGB público;no entrenamiento ni aceptación delcandidato. Campaña pendiente.


### Supervisión 15 octubre — V133/V134
Piloto de inferencia conpesoscycle04 existentes exclusivamente sintéticos:3RGB públicos deV131,full960,confianza histórica0,146146 sin reajuste.16,16s efectivos,minRAM11,856GiB,0s espera,sinfallo. Verificados hashesRGB yarchivosNPZ;estimador recibió únicamenteRGB eidentificadores ordinales,no máscaras ni poses. Evaluador separado:16/61apariciones emparejadas aIoU≥0,5,37predicciones aceptadas,precisión0,4324 yrecall0,2623. Son3vistas ortográficas deunaplanta con objetos repetidos,no precisión de dron ni campo;no comparar causalmente conV40 deotra planta. Estratificación diagnóstica porpíxeles guardada en evaluation_winding_v134_diagnostics.json. No entrenamiento,clasesnuevas ni aceptación delcandidato. Revisar fallos por tamaño antes de más ajustes de inferencia;continúan geometría/materiales pendientes.


### Supervisión 15 octubre — V135
Auditoría CPU de propuestas retenidas,solo evaluador:61apariciones;14capachos≥500píxeles,todos en vista detalle. Solo1/14 tiene alguna propuesta conIoU≥0,5 incluso bajo umbral operativo;0/14 aceptados. En9/14 la misma identidad sí coincide en frontal o lateral. No demuestra causalidad por escala:visibilidad/encuadre también cambian. Inspección visualRGB/máscara detalle no muestra desregistro global evidente. Reducir confianza no resolvería13/14grandes con las propuestas disponibles;no se modifican umbrales. MejorIoU individual porverdad no es recalluno-a-uno;NMSinterno/pérdidas bajo suelo0,001 no observables. Mantener pesos/configuración congelados y no deformar plantas para satisfacer detector;volver a fidelidad morfológica mientras se preservan advertencias físicas/materiales. SinGPU ni nuevasimágenes,ninguna semilla reservada tocada;campaña pendiente.


### Selección humana — V136
Usuario cierra refinamiento y solicita muestras existentes. Cinco renders completos A–E, misma cámara/luz/materiales, dos arquitecturas con variantes de parámetros: A=V108, B=V113, C=V120, D=V99, E=V114. Solo corrección topológicaV130 compartida;no cambios nuevos de geometría. Archivos/hashes/procesos completos registrados en family_selection_v136/selection.json. Heartbeat actualizado y PAUSED para esperar elección humana. Campaña integral pendiente, no confundir pausa de selección con cierre de campaña.


## V137 — tanda solicitada sobre familia D (2026-10-15)

El usuario elige D y solicita reducir la apariencia de ramitas terminales y ampliar la variación amarilla del follaje y de los capachos. Se conserva la topología de `hanging_matte_v99_input/morphology.json` (semilla de desarrollo 814144). Sus 48 ejes sin hijos ya terminaban en hoja nodal: se acorta únicamente el pecíolo terminal a 0.45–0.8 cm, limitado además a 10% del largo de la lámina, como heurística visual pendiente de revisión. No se eliminan ejes ni se trasladan hojas fuera del nodo.

Cinco muestras reproducibles con semillas de parámetros 13700–13704; cámara y luz iguales. Se retiran del renderer de revisión el tinte verde global de hojas y el aclarado verde uniforme de capachos. Se reutilizan texturas existentes y la mezcla verde/senescente; sin añadir corrugación geométrica. Cada planta conserva 267 hojas y 33 capachos.

Se usa exclusivamente el contrato visual `segmentation_cycles/1.0`: pintona (grados de apariencia 0–4), madura (5), sobremadura (6). No se presenta esta agrupación como validación literal de la NTC ni como madurez agronómica del fruto. El estado latente del fruto permanece intacto; estas salidas son revisión visual, no datos aceptados para entrenamiento. Las proporciones muestreadas son heurísticas, no frecuencias botánicas medidas.

| Variante | Media solicitada de senescencia foliar | Pintona | Madura | Sobremadura |
|---|---:|---:|---:|---:|
| D1 | 0.16 | 21 | 8 | 4 |
| D2 | 0.38 | 12 | 15 | 6 |
| D3 | 0.67 | 5 | 20 | 8 |
| D4 | 0.87 | 4 | 8 | 21 |
| D5 | 0.52 | 11 | 11 | 11 |

Procedencia y entradas exactas: `outputs/integral_diagnosis_20261014/d_family_review_v137/selection.json` y `D1.json`–`D5.json`. No se tocan semillas reservadas. Comparación antes: `family_v136_D/814144_whole.png`. Render y comprobaciones finales pendientes al registrar la preparación. Campaña integral pendiente; heartbeat continúa pausado.


### V138 — corrección de continuación terminal tras revisar V137

V137 completó diez renders, pero la revisión visual mostró que el pecíolo corto no resolvía todo el tramo desnudo terminal. Se preserva V137 como comparación negativa. En las cinco entradas V138 se acorta además a un máximo total de 0.8 cm la secuencia final de entrenudos desde el último nodo con órgano previo hasta la hoja terminal, conservando todos los nodos y sus identidades. Se afectan 48 ejes terminales por muestra. Es una heurística visual explícita, no una longitud botánica medida. Se comprobó igualdad de identidades nodales/reproductivas y de estados latentes del fruto frente a D original. La mezcla de apariencia de V137 se conserva exactamente. No se modifica el generador global ni se congelan parámetros antes de la revisión humana.

V138 final: 5/5 muestras completas, seis PNG Blender (cinco plantas completas y un detalle D3). Las 267 conexiones hoja-pecíolo por planta pasan error <0.001 cm. Ver `d_family_review_v138/verification.json` para tiempos y memoria. Se conserva pendiente la aceptación por colisiones y el uso para entrenamiento. Se espera revisión humana; heartbeat pausado.


## V139 — caída terminal y apariencia del capacho, referencias nuevas

Solicitud humana: puntas finas caídas, continuidad con la hoja, venas opacas, manchas cafés en capachos sobremaduros; hojas amarillas poco frecuentes. Referencias adjuntas conservadas en `d_family_review_v139/reference_1.jpg` y `reference_2.jpg`. La primera muestra tejido claro y venación oscura; la segunda, tejido ocre/café irregular. Estas observaciones visuales no prueban mecanismos fisiológicos ni madurez del fruto.

Tres variantes D conservan 267 hojas y 33 capachos. Hojas amarillas: 8/267, 13/267 y 21/267. Mezcla pintona/madura/sobremadura: 16/12/5, 10/16/7, 8/14/11. Las distribuciones son heurísticas de revisión, no frecuencias medidas. En 48 ejes terminales se aplica deflexión progresiva registrada en morfología (75/105/130 grados nominales con variación; el intérprete limita la inclinación final a -35 grados), radio multiplicado por .72 y hoja terminal alineada a 8–18 grados del eje. No es una simulación mecánica calibrada.

Se detectó que `_bend_direction` reponía el límite ascendente entre segmentos; parámetro opcional `minimum_z` conserva el comportamiento previo por defecto y permite caída solo en ejes marcados `terminal_load_droop_v139`. Prueba Blender de vectores pasó: preserva descenso optativo y comportamiento predeterminado. Grafo válido 152 nodos/261 aristas.

Materiales: máscaras UV existentes con venas oscuras mates, menor luminosidad de venas en hojas amarillas; manchas procedurales cafés de color en capachos secos sin desplazar geometría. Madurez interna del fruto intacta. Seis renders Cycles completados, 267 conexiones hoja-pecíolo por muestra con error <0.001 cm. Ver `d_family_review_v139/verification.json`. Revisión visual confirma caída de extremos y capachos claros/cafés sobre follaje principalmente verde; sigue pendiente validación humana y de colisiones. No aceptado para entrenamiento. Heartbeat pausado, campaña integral pendiente.


## V140 — continuidad nodal y bifurcaciones tridimensionales

Usuario selecciona caída fuerte V139 D3. Se añade interpolación Bézier optativa por eje (`continuous_tangent_v140`), con tangente compartida en los extremos de entrenudos consecutivos. Mantiene posiciones nodales y caída progresiva; evita que la ondulación independiente por segmento produzca quiebres. Las bifurcaciones usan marco ortonormal local completo (`branch_frame_v140`) y ángulo respecto a la tangente parental; no una proyección de azimut horizontal que degenera en ramas horizontales. Para esta muestra, semilla 14003 y variación de azimut ±35 grados alrededor de la orientación previa, como heurística. No modifica comportamiento de plantas anteriores sin estas opciones.

Pruebas puras: norma y ángulo conservados para padres verticales, horizontales y descendentes, cuatro azimuts distintos. Auditoría Blender: 971 uniones del mismo eje, separación máxima 0, producto escalar mínimo entre tangentes 0.99999982; 267 conexiones foliares pasan. Dos renders completados. Los proxies históricos de colisión siguen siendo cuerdas y no certifican la nueva curva Bézier; aceptación por colisiones pendiente. Grafo validado. Entradas y renderer en `d_family_review_v140`, auditoría en `d_review_v140_D3/tangent_continuity.json`. Campaña pendiente y heartbeat pausado.


## V141 — 20 arbustos para auditoría final de la etapa visual

Solicitud explícita del usuario: generar 20 arbustos para auditar, cerrar mejoramiento y pasar al siguiente paso. Se congelan para esta tanda las decisiones D / caída fuerte / continuidad tangencial / bifurcaciones 3D / textura mate con capachos claros y cafés. No se añaden refinamientos estéticos durante la tanda.

Entradas B01–B20, semillas de desarrollo 814160–814179, disjuntas de las seis reservadas 914140–914145. Son 20 variantes reproducibles de parámetros de la misma topología D (89 ejes, 267 hojas, 33 capachos), no 20 arquitecturas generadas independientemente. Variación moderada de longitudes, tamaño foliar, azimut de bifurcación, apertura, caída fuerte, distribución foliar amarilla poco frecuente y mezcla de apariencia del capacho. Misma cámara e iluminación. Proporciones son heurísticas de muestreo visual, no distribuciones botánicas medidas. Madurez interna intacta. JSON de entrada y hashes en `shrub_audit_v141/selection.json`; copia de módulos relevantes en `source_snapshot`.

Plan de entrega: veinte RGB de planta completa y galería numerada con ampliación y notas de auditoría. Comprobar conexiones foliares y continuidad de ejes por muestra, tiempos y memoria reales. La auditoría visual cierra esta etapa cuando el usuario emita su decisión; no equivale a completar la campaña ni a aceptar datos para entrenamiento.

Siguiente paso tras la auditoría: piloto pequeño versionado RGB/máscaras/anotaciones, validación de identidad/UV/conexiones/colisiones de la geometría vigente y separación estimador/evaluador antes de piloto con dron. Revisar `audit_pose_reprojection_v1` antes de reanudar cola histórica; no repetir etapas completas. Mantener semillas reservadas intactas hasta congelación y validación de disjunción.

V141 entrega verificada: 20/20 RGB completos; 5,340 conexiones foliares y 19,420 uniones tangenciales comprobadas. Tiempo efectivo total 293.15 s; memoria libre mínima 11.41 GiB. Morfología valid_with_warnings; no aceptación por colisiones. Galería autónoma `shrub_audit_v141/galeria_auditoria.html` con 20 imágenes incrustadas, ampliación, notas y exportación de decisiones. HTML y sintaxis JavaScript comprobados; dos vistas generales estáticas para consulta. Pendiente auditoría humana, sin nuevos refinamientos automáticos.


## V142 — diez arbustos con bifurcaciones en Y, follaje bajo y mayor carga

Solicitud humana: limitar ramas largas sin bifurcación, desviar ambas salidas en Y, follaje denso desde abajo, muchas más uchuvas y estados variados. Entradas C01–C10, semillas de desarrollo 814200–814209; no se usan las seis reservadas.

Se adelantan las primeras bifurcaciones y se limita el recorrido acumulado entre bifurcaciones a 18 cm en ejes basales y 14 cm en órdenes superiores; los terminales también se limitan a 14 cm. Son umbrales de ingeniería para esta comparación, no datos botánicos medidos. Se mantienen las cuatro salidas basales del armazón común. Las 80 bifurcaciones del ramaje tienen dos salidas en lados opuestos: rama hija + continuación desviada, o dos ramas hijas al final. La morfología guarda `y_fork_continuations_v142`; el intérprete conserva el comportamiento previo cuando no existe ese registro. La continuidad tangencial se exige en nodos sin bifurcación; en Y el cambio es intencional.

Hojas: 388 por muestra, frente a 267 anteriores, incorporadas en nodos bajos de órdenes 1–3. Frutos con capacho: 75,83,91,99,107,115,123,131,139,147; solitarios en axilas con hoja, evitando añadirlos en nodos ya reproductivos o de bifurcación. Identidades, pecíolos, pedicelos y enlaces nodales se conservan/reasignan de forma explícita. Nuevos frutos proceden de plantillas sintéticas con estados latentes variados. Se muestrea aparte la apariencia pintona/madura/sobremadura con textura clara o café; no se deduce la madurez del fruto del color del capacho. Hojas amarillas infrecuentes.

Fallo conservado: primer intento C01 falló por sintaxis antes de construir la escena; corregido y registros de reintento `_r1` separados. Se auditan en Blender separación nodal, direcciones de ambas salidas y oposición radial de cada Y. Los conteos de frutos incluyen los ocultos. La mayor carga requiere aceptación posterior de colisiones; esta tanda sigue siendo de revisión visual, no entrenamiento aprobado.

V142: 10/10 plantas completas verificadas, 800 bifurcaciones Y y 3,880 conexiones foliares. Tiempo efectivo 163.63 s, RAM libre mínima 11.17 GiB. Galería y vista general listas. El detalle C05 con cámara histórica quedó mal centrado debido a la menor altura; se conserva como negativo y se prepara encuadre corregido sin modificar la planta.


## Aprobación visual V142 — 15 octubre 2026

El usuario acepta las versiones actuales por ahora y solicita recordar el siguiente paso del plan. Se cierra el refinamiento visual abierto y se adopta V142 C01–C10 como baseline visual de desarrollo. Esto no acredita aceptación física, etiquetas ni entrenamiento. Próximo: validar geometría efectiva y contrato de anotaciones/materiales, piloto sintético pequeño, percepción y recorrido con dron, seguimiento/localización con sensores relativos ruidosos y evaluador separado; después comparar entrenamientos y evaluación reservada tras congelación. No se inicia una ejecución pesada en este turno de consulta. Se mantienen intactas las semillas reservadas y pendiente la campaña integral.


## Continuación autorizada y heartbeat horario — V143 (2026-10-15)

El usuario autorizó continuar después de aceptar visualmente V142 C01–C10. Se reactivó la automatización existente con frecuencia horaria y selección dinámica de la siguiente tarea lista; se notifican cambios relevantes y fallos, no sondeos rutinarios. La campaña integral sigue pendiente.

Se ejecutaron tres auditorías Blender de malla evaluada, secuenciales y con reserva RAM de 2 GiB: C01, C05 y C10. Los tres procesos finalizaron con código 0, pero las tres validaciones físicas resultaron inválidas: 98, 102 y 137 pares respectivamente. Desglose capacho/tallo: 80/66/90; capacho/capacho: 6/21/37; tallo/tallo: 12/15/10. No son conteos de plantas ni de oclusión visual; esta última no se mide aquí. Las uniones legítimas deben verificarse localmente, sin eximir todos los contactos entre órganos emparentados. No se modificó la apariencia aprobada ni se aceptaron estas muestras para entrenamiento.

El fallo histórico audit_pose_reprojection_v1 fue revisado: KeyError de marker_id. Existe recuperación pose_reprojection_audit_v2.json versión 1.1 sobre 32 objetos; se conserva el fallo y no se repite la etapa. La compatibilidad de reproyección no demuestra exactitud frente a verdad.

Siguiente trabajo independiente: piloto diagnóstico pequeño de UV, materiales, identidades, RGB y máscara sobre C05, marcado no apto para entrenamiento. Después, corregir contactos locales conservando conexiones y arquitectura aprobada; repetir solo comprobaciones afectadas. No encadenar entrenamiento ni piloto productivo con dron hasta superar sus puertas técnicas. Evidencia y dependencias: outputs/integral_diagnosis_20261014/technical_transition_v143/summary.json. Semillas reservadas intactas.


## Piloto técnico V144 — C05, 15 octubre 2026

Ejecutado Blender real con semilla 814204 y morfología exacta V142 C05: RGB y máscara de instancias 900×1000. Proceso 15524 finalizado código 0, 22.23 s efectivos y RAM libre mínima 11.35 GiB. Verificación: correspondencia biyectiva de 125 identidades reproductivas (107 capachos y 18 flores), 85 visibles, cero colores fuera de paleta y cero diferencias entre conteos de píxeles y anotaciones. Las 388 láminas y 107 capachos tienen UV finitas y materiales; las 388 nervaduras separadas de color sólido no tienen UV y se registran aparte. Inspección visual del RGB realizada, sin modificar la arquitectura aprobada.

El contrato bruto todavía incluye madurez latente y occlusion_proxy histórico (complemento del llenado de caja, no oclusión medida): permanece como diagnóstico privado, no datos de entrenamiento ni entrada del estimador. Falta exportar y verificar el enlace apariencia/clase/material y sanear el esquema. Cámara ortográfica de revisión, no piloto calibrado de dron. Persisten los fallos físicos V143; no se repitieron ni se dieron por resueltos. Próximo paso: enlace explícito de apariencia y saneamiento del contrato, seguido de corrección local de contactos con pedicelos conectados. Evidencia: outputs/integral_diagnosis_20261014/contract_v144_C05/verification.json. Campaña pendiente y semillas reservadas intactas.


## Contrato diagnóstico V145 — separación de apariencia y verdad

Sin repetir renders, se verificó el enlace de 107/107 capachos entre grado sintético, clase de apariencia, material solicitado y material registrado por Blender. Conteos: 37 pintona, 55 madura y 15 sobremadura. Las 18 flores quedan excluidas de esas clases, aunque se conservan en la paleta reproductiva. Exportación versionada en contract_v145_C05: estimator_inputs contiene exclusivamente RGB; evaluator_private contiene máscara, anotaciones de apariencia y verdad latente separada. Esta separación es un contrato de entrada, no aislamiento de permisos del sistema. Se sustituyó el ambiguo occlusion_proxy por visible_mask_bbox_fill_ratio; no se afirma medir oclusión. No se promueve a entrenamiento y permanece pendiente aceptación física V143.

Inspección estática previa a reparación: blender_pose_repair._rendered_node_frames reproduce una arquitectura anterior y omite el marco 3D V140, las continuaciones Y V142 y el límite de caída terminal. Ejecutar directamente esa búsqueda podría reubicar órganos usando anclajes incorrectos. Siguiente paso concreto: reconciliar anclajes con geometría real y comprobar igualdad, después prueba acotada de pedicelos conectados y auditoría tras reconstrucción completa. No se ejecutó reparación con esos anclajes obsoletos. Semillas reservadas intactas; campaña pendiente.


## V146 — anclajes del reparador reconciliados con V142

Se corrigió _rendered_node_frames en blender_pose_repair.py para reproducir el marco de bifurcación 3D, los giros de continuación Y y la caída terminal fuerte del intérprete vigente. Se preservó copia anterior en frame_audit_v146. No se modificó la morfología aprobada ni se movieron órganos.

Validación ejecutada en Blender sobre C01/C05/C10: 1060 nodos por muestra, 3180 posiciones coincidentes exactamente y productos escalares de dirección mayores de 0.9999998 respecto al segmento construido. El replay anterior divergía hasta 6.428/4.623/5.380 unidades de escena respectivamente; son errores del reparador, no colisiones ni unidades métricas. Proceso 34844 terminó código 0 en 14.23 s, RAM libre mínima 12.31 GiB. Evidencia frame_audit_v146/verification.json y script reproducible.

Siguiente: reparación local acotada en C05 con estos anclajes verificados, preservando orientación descendente, identidades y conexiones; auditoría de mallas tras reconstrucción y comparación visual. Persisten las colisiones de V143 y la prohibición de promover a entrenamiento. Campaña integral pendiente.


## V147 — reparación acotada de tres pedicelos C05

Ensayo aislado con copia versionada del reparador, anclajes V146 y tres capachos seleccionados de los contactos físicos V143. Búsqueda descendente (ángulo mínimo 55 grados) y extensión máxima 1.3 veces; heurísticas de ingeniería, no medidas botánicas. Se conservaron obstáculos pecíolos/tallos, excluyendo solo láminas de la puntuación local; la auditoría completa posterior incluye todas las geometrías.

Blender reconstruido: pares físicos 102 a 92, separaciones insuficientes 328 a 324; intersecciones blandas foliares 635 a 637, regresión conservada. Tres pedicelos ajustados; hojas, arquitectura, identidades y estados permanecen iguales tras normalizar ambos JSON mediante Plant.from_dict/to_dict. La primera comparación directa detectó valores predeterminados añadidos al serializar; se corrigió el comparador, sin ocultar cambios de parámetros. Proceso29756,66.30s y RAM mínima11.79GiB. No es aceptación física y no se promueve a entrenamiento. Se genera render real equivalente para inspección antes/después. Evidencia repair_v147_C05/verification.json, copias y objetivos en repair_trial_v147.

Render V147 completado código0 (18.22s, RAM mínima10.76GiB), comparado visualmente con V144: silueta y follaje conservados, desplazamiento localizado de capacho inferior visible. La revisión global no acredita ausencia de contactos. Siguiente ensayo debe considerar también la regresión de intersecciones blandas.


## V148 — prioridad física y piloto de segmentación preparado (15 octubre, Colombia)

El usuario insiste en no concentrar el trabajo solo en colisiones. Se explicita: las intersecciones blandas y las separaciones heurísticas no son objetivos de cero por sí solas. Se mantienen los controles de penetración rígida remota, conexiones, identidad, UV y etiquetas; no se eximen uniones sin evidencia local.

Ensayo dirigido a los tres capachos con mayor número de pares físicos restantes (7,6,6), sobre V147. Tras reconstrucción completa, pares físicos92→73, separaciones324→320, intersecciones blandas637→637. Comparación normalizada confirma cambios exclusivamente en tres pedicelos y su procedencia, sin alterar arquitectura ni hojas; revisión visual del nuevo candidato aún pendiente. Proceso14960 completó en50.28s, RAM libre mínima9.55GiB. No se acepta para entrenamiento.

Trabajo independiente completado: piloto de segmentación preparado en segmentation_pilot_v148/readiness.json, pesos existentes cycle04 verificados por SHA256, entradaRGB pública, resolución960, inferencia completa y evaluación privada por máscara/clase. No se lanzó sobre geometría aún no aceptada. El piloto se ejecutará al superar controles, sin otra aprobación general; debe usar RGB/máscara frescos de la misma morfología reparada, no mezclar las anotaciones antiguas. Las semillas reservadas permanecen intactas.


## V149 — contactos prioritarios y evaluador de segmentación

Ensayo de ocho capachos con más contactos rígidos restantes, sobre V148: tras reconstrucción completa, pares físicos73→44, separaciones320→312, intersecciones blandas637→635. Solo cambiaron parámetros de ocho pedicelos y procedencia; identidad, arquitectura, hojas y estados preservados según comparación normalizada. No se exige cero intersecciones blandas ni cero separaciones heurísticas. Contactos restantes por semántica: {'stem/stem': 15, 'calyx/stem': 15, 'calyx/calyx': 14}. Proceso37668 terminó código0 en144.46s efectivos, RAM mínima10.13GiB. Revisión visual y máscara de la última versión aún pendientes; no se promueve a entrenamiento.

Avance independiente hacia percepción: evaluador privado preparado en segmentation_pilot_v148/evaluate.py. Usa apariencia del capacho, emparejamiento por confianza uno-a-uno con IoU≥0.5 y misma clase; excluye flores y reporta ocultos y visibles diminutos por separado. Pruebas controladas con máscaras2×2 verifican rechazo de clase incorrecta y no reutilización de verdad por duplicados. No son métricas de un modelo ejecutado. Al superar controles, ejecutar inferencia preparada con los pesos existentes y este evaluador, sin otra aprobación. Campaña pendiente; reservas intactas.


## V150 — revisión explícita de los 44 contactos

Petición humana: distinguir uniones naturales y evitar prolongar esta etapa. Se reconstruyó V149 en Blender y se inspeccionaron los 44 pares mediante mallas evaluadas, topología declarada y BVH con epsilon cero. Los44 mantienen intersección y ninguno comparte nodo de conexión declarado entre sus dos objetos. Esto descarta dependencia exclusiva de la tolerancia, pero no mide profundidad de penetración. Cinco pares eje/eje corresponden a corona basal entre nodos vecinos: candidatos a tejido continuo que requieren validación local; no se certifican ni se eximen automáticamente. Los otros39 son contactos no asociados a una unión de esos órganos (29 con capachos y10 entre tallos/pecíolos/pedicelos).

Se inicia V151 como una pasada acotada sobre35 capachos implicados para evitar múltiples tandas de tres, conservando dirección descendente, hojas y arquitectura. El piloto de segmentación permanece preparado y se encadena cuando pase la puerta física y se regeneren RGB/máscara coherentes. Evidencia contacts_v150 completado código0 en14.42s, RAM mínima11.23GiB; detalle en contact_review_v150/contacts.json.


V151 alcanzó480s y el supervisor falló con TimeoutExpired al esperar cierre. Se verificó ausencia del PID17400 antes de continuar; registro histórico preservado y reconciliación separada. Se auditó una sola vez el checkpoint guardado, sin repetir búsqueda: {'physical_collision_count': [44, 34], 'clearance_violation_count': [312, 300], 'soft_occupancy_intersection_count': [635, 635]}. Recuperación27380 completada código0 en62.71s, RAM mínima11.66GiB. No se aceptó para entrenamiento ni se lanzó inferencia sobre geometría no aprobada. Próximo: contactos restantes y corona basal local; evitar repetir búsqueda completa.


## V152/V153 — RGB, máscaras y contrato actualizados

Se regeneraron RGB y máscara de instancias desde el checkpoint V151 exacto, sin reutilizar etiquetas de una geometría anterior. Blender31296 completó código0 en70.67s, RAM mínima10.20GiB. Verificación de píxeles y paleta sin diferencias;495 superficies texturadas con UV finitas,388 conexiones foliares y80 uniones Y. Exportación privada V153 verifica107/107 materiales y clases de apariencia,18 flores excluidas y madurez interna separada; estimador recibe soloRGB. Inspección visual: silueta/follaje conservados y cambios localizados de capachos. No se ejecuta aún inferencia:34 pares físicos siguen pendientes de aceptación.

Se corrigió un fallo de lanzamiento propio: la reconciliación V151 había quedado entre los registros de trabajos y el contador de presupuesto la interpretaba como trabajo sin awake_elapsed_seconds. Se trasladó intacta a repair_v151_C05/supervisor_reconciliation.json; no se alteraron tiempos ni presupuestos. El render posterior completó correctamente. Próximo paso: revisión física local de corona basal y contactos remotos, sin repetir búsqueda completa; contrato de percepción fresco listo para encadenar al pasar la puerta.


## V154 — piloto de segmentación ejecutado con criterio de vista externa

Nueva autorización humana: no aplazar por contactos fuera de la vista externa. Se muestrearon intersecciones triangulares y se trazaron rayos en la dirección ortográfica exacta del render:27/34 pares sin muestras expuestas,7 con muestras expuestas. Es evidencia de oclusión de los puntos muestreados desde una cámara, no garantía de todas las vistas ni prueba de validez física. No se certificó ninguna unión natural nueva. Los7 expuestos se conservan como limitación y se marcan sus instancias; render visual aprobado sin cambios, controles RGB/máscara/identidad/material pasan. Se acepta exclusivamente prueba diagnóstica de percepción; entrenamiento y geometría física no aceptados.

Inferencia real con pesos sintéticos cycle04, RGB solo, resolución960: proceso6328 completó código0 en28.45s, RAM mínima10.57GiB. Evaluador privado, mismas clases verificadas en el modelo, IoU≥0.5 y coincidencia de clase:13TP,28FP,71FN; precisión31.7%,recobrado15.5% sobre84 capachos visibles. Por clase: pintona8/27 recuperados, madura1/47, sobremadura4/10. Se mantienen los resultados negativos, las instancias pequeñas y la estratificación por contactos expuestos en segmentation_pilot_v154/verified_summary.json. No son resultados de dron ni prueba independiente.

Siguiente: diagnosticar localización frente a confusión de apariencia y tamaño, comparar teselas nativas con los mismos pesos y RGB. No retomar búsqueda geométrica abierta. Campaña integral pendiente; reservas intactas.


## V155 — comparación de teselas y diagnóstico de error

Inferencia real secuencial, mismo RGB y pesos cycle04, teselas nativas640 frente a imagen completa960 existente. Proceso33020 completado código0 en26.46s, RAM mínima7.65GiB. El resultado empeora:9/84 TP con clase correcta (precisión21.95%,recobrado10.71%) frente a13/84 (31.71%,15.48%). Se conserva el negativo y no se sustituye el baseline full960. No hubo modificación de planta ni entrenamiento.

Evaluador privado adicional separa localización y clase con emparejamientos uno-a-uno independientes: full960 localiza25/84 sin exigir clase, teselas18/84. Entre los capachos de apariencia madura localizados en full960,6 se predicen pintona,4 sobremadura y solo1 madura. Los25 capachos con menos de64 píxeles visibles no se localizan en ninguna variante. Esto muestra errores de escala y de clasificación; no demuestra madurez interna ni generalización a campo.

Siguiente: piloto pequeño de cámara perspectiva/dron con mayor tamaño proyectado de órganos, misma morfología/materiales aprobados, contrato de cámara y separación público/privado verificados; inferencia full960 y diagnóstico por clase. Evitar otra búsqueda estética o comparación indiscriminada de teselas. Evidencia reproducible diagnose_segmentation_v155.py y segmentation_tiles_v155/comparison.json. Campaña pendiente; reservas intactas.


## V156 — observación perspectiva y resultado negativo

Cámara perspectiva45mm,sensor36mm,HORIZONTAL,900×1000; objetivo y posición de cámara modificados para mayor ocupación de imagen, sin cambiar morfología ni materiales. Proyección pinhole verificada frente a Blender sobre1610 puntos, error máximo0.0000381px. Poses exactas permanecen privadas. No es calibración física ni recorrido de dron ejecutado. RGB/máscara nuevos con conteos de píxeles coherentes;107 materiales/clases verificados. Inspección visual realizada. Los contactos físicos pendientes siguen como limitación; las27 oclusiones de cámara ortográfica no se transfieren a perspectiva.

Inferencia real full960 con mismos pesos:6/80 capachos visibles con clase correcta,37predicciones aceptadas (precisión16.22%,recobrado7.5%);14/80 localizados sin exigir clase. Apariencia madura:0/40correctos;8localizados se confunden como pintona5 o sobremadura3. Aunque aumentaron los objetivos de≥256píxeles de25 a35, el resultado no mejora. Cambiaron proyección, encuadre y punto de vista a la vez: no atribuir causalmente todo al tamaño. Render44344 completó32.29s RAMmínima6.78GiB; inferencia32732 completó20.34s RAMmínima8.35GiB.

Siguiente: revisar representación de clase madura y dominio de materiales contra procedencia del entrenamiento cycle04 antes de más barridos de cámara; mantener negativos y baseline full960. Después recorrido diagnóstico multivista acotado. Sin entrenamiento nuevo ni evaluación reservada; campaña pendiente.


## V157 — procedencia y pérdida de supervisión en entrenamiento existente

Auditoría de los 180 rásteres de cycle04: hashes y conteos por instancia correctos, sin solapamiento de semillas train/val ni uso de 914140–914145. Train contiene 140 imágenes y 7800 instancias: pintona5592, madura1114, sobremadura1094; las tres clases están presentes en todas las imágenes. Val contiene40 imágenes y2222 instancias. La clase madura sí tuvo ejemplos; su proporción en train es14.28%, frente a50% de los80 capachos visibles del piloto perspectiva. Esto identifica un cambio de distribución, no demuestra la causa del fallo.

Hallazgo técnico reproducido con la transformación real del entrenador (letterbox960, vecino más cercano y mask_ratio4 confirmado en args.yaml):896/7800 objetivos de entrenamiento pierden todos sus píxeles en la rejilla de supervisión, aunque conservan caja y clase;145/1114 son de apariencia madura. En val desaparecen211/2222. Ensayo CPU sobre los mismos rásteres: ratio2 reduce los vacíos a196 en train y40 en val; ratio1 a26 y7. No equivale a mejora de inferencia comprobada ni elimina por completo el problema. Antes de reentrenar se necesita política explícita para objetivos que desaparecen, con contabilidad y pruebas; no ocultar estos objetivos del denominador de evaluación nativa.

La procedencia final confirma entrenamiento nuevo de60 épocas y SHA de manifiesto coincidente; protocol.json conserva texto previo desactualizado que decía entrenamiento pendiente. Se priorizaron completion.json y training/experiment.json sin reescribir evidencia histórica. El entrenamiento uchuva es sintético con inicialización general COCO declarada. No se entrenó ni se alteró aspecto, etiquetas o umbrales. La diferencia de materiales sigue siendo hipótesis pendiente de comparación controlada, no explicación demostrada.

Evidencia: training_audit_v157/audit.py, grid_ablation.py y audit.json. Siguiente: recorrido diagnóstico multivista acotado con modelo congelado y limitaciones explícitas; para el posterior experimento de entrenamiento, resolver supervisión diminuta y comparar ratio2/4 sobre datos elegibles. C05 diagnóstico no se promueve a entrenamiento. Campaña pendiente.


## V158 — piloto multivista acotado con modelo congelado

Se añadieron dos observaciones perspectiva a V156, cámara izquierda(4,-12.80625,6) y derecha(8,-10.77033,6), manteniendo distancia horizontal, objetivo(0,0,3.2), focal45mm, luces, materiales y morfología V151. Inspección visual de ambos renders realizada. Contratos por vista:107 asociaciones material/grado/clase verificadas, flores excluidas, RGB público y verdad privada; evaluador confirma píxeles de cada instancia contra máscaras. Error de reproyección menor de0.000047px. No se repitieron reparaciones geométricas.

Renders reales secuenciales:26.26s y18.23s; inferencias full960:8.24s y6.22s, todos código0. RAM mínima registrada6.697GiB. Resultados con clase correcta e IoU≥0.5: izquierda3/82, centro6/80 previo, derecha8/78. Apariencia madura:0 aciertos en las tres vistas. La unión de identidades privadas contiene94 capachos visibles distintos y11 detectados correctamente al menos una vez; esto es cobertura evaluada, no seguimiento estimado. Se preservan falsos positivos28/31/29 respectivamente. No atribuir mejora general a la vista derecha ni ampliar barridos de cámara para compensar el bajo rendimiento.

Son tres observaciones dispersas, no un vuelo continuo con sensores ni localización3D validada. La visibilidad de contactos de V154 no se transfiere a estas vistas; siguen siendo datos diagnósticos sin promoción a entrenamiento. Próximo trabajo: política explícita y pruebas de objetivos que desaparecen en la rejilla de supervisión, conservando denominadores nativos del evaluador; después experimento acotado sobre datos sintéticos elegibles. La ruta con sensores relativos ruidosos y seguimiento sigue pendiente. Evidencia multiview_v158/summary.json y scripts reproducibles. Reservas intactas y campaña pendiente.


## V159 — política experimental de supervisión sin borrar instancias

Rama codex/raster-supervision-v159. Se añadió opción explícita any_coverage al entrenador: remuestreo por área de cada máscara binaria nativa por separado; una celda es positiva si recibe área de esa instancia. Conserva identidades, cajas y clases; puede ensanchar contornos y solapar máscaras en rejilla gruesa. El auxiliar semántico admite una sola clase y resuelve empates por menor ID estable; esa limitación debe medirse en el experimento. Se requiere --technical; el comportamiento por defecto sigue siendo legacy_nearest. Validación no admite esta política: el evaluador nativo y sus denominadores permanecen sin modificaciones. No es una mejora predictiva demostrada.

Cinco pruebas CPU pasan: componentes/huecos, objetos diminutos vecinos, inversión horizontal, ausencia de ID, coherencia de clases/cajas y prohibición en validación. Primera ejecución falló por permisos del temporal del sandbox; repetición con temporal dentro de outputs pasó. Validador del grafo correcto152 nodos/261 aristas y diff sin errores de espacios. Auditoría completa CPU del conjunto train iniciada; PID26392 comprobado, 114s CPU y606MB aproximadamente al inspeccionarlo. Aún pendiente audit.json; no hay entrenamiento GPU nuevo. El primer intento de auditoría encontró canal singleton añadido por el wrapper de lectura de Ultralytics y se corrigió normalizando ese eje en el script diagnóstico. Próximo: recoger auditoría y prueba de entrenamiento pareada acotada sobre datos sintéticos elegibles, no sobre C05 diagnóstico.


## V160 — auditoría completa recogida y prueba pareada real de entrenamiento

V159 terminó en220.26s CPU:7800/7800 máscaras de train conservan soporte con any_coverage tanto ratio2 como4. Hay8553 y6276 celdas respectivamente compartidas por instancias (no necesariamente clases diferentes); no ocultar la expansión conservadora ni equipararla a más precisión. El antiguo defecto de soporte desaparece en esta transformación, pero su beneficio predictivo sigue sin demostrarse.

Se ejecutaron dos entrenamientos GPU secuenciales, legacy_nearest y any_coverage, ratio2 fijo, misma inicialización COCO SHA361fbfab…, semilla20261002, tamaño960,batch2 y2 épocas. Subconjunto verificado por hashes:4 imágenes train de420100/420101 y2val de420118, sin cruce ni semillas reservadas. Ambas ejecuciones terminaron código0, pérdidas finitas y pesos guardados; duraciones supervisadas34.26s/32.24s y RAM mínima8.40GiB. Ambas métricas de validación son0: prueba de funcionamiento, no comparación científica concluyente ni modelo para despliegue. No se utilizó C05 diagnóstico para entrenar.

Evidencia training_smoke_v160/protocol.json, summary.json, experiment.json y results.csv de cada ejecución. Próximo: prerregistrar comparación sobre train/val sintético existente completo, ratio2 y60épocas por brazo, evaluación con máscaras nativas y umbral fijo; cuantificar conflictos semánticos entre clases antes del lanzamiento. Mantener baseline cycle04, aspecto aprobado y campaña pendiente.


## V161 — comparación controlada prerregistrada e iniciada

Se revalidaron hashes de180 RGB y máscaras, disjunción train/val y ausencia de semillas reservadas. La cobertura ratio2 presenta3944 celdas compartidas entre clases de251131 celdas cubiertas(1.57%); se conserva esta limitación del desempate semántico por ID, sin confundirla con vacío de instancia. Prerregistro protocol.json:140 imágenes train/40val,60 épocas por brazo,960px,batch2,ratio2, misma inicialización y semilla; única intervención prevista política nearest/coverage. Igual número de ejemplos y épocas, no idéntico costo computacional. Selección principal last.pt tras60épocas, umbral externo0.25 e IoU0.5, máscaras nativas con denominadores completos. best.pt queda secundario; no ajustar el umbral al resultado.

Controlador secuencial oculto iniciado y comprobado por línea de comando:43972; primer trabajo real32696/runtime14528, salida de entrenamiento y archivos args/labels creados, reserva mínima2GiB y admisión6.5GiB. El intento inicial en sandbox no dejó proceso activo; se confirmó antes de iniciar el controlador persistente fuera de ese entorno. Cada brazo tiene límite operativo10800s; se detiene la secuencia ante fallo. No hay resultado nuevo de calidad todavía. Monitorizar archivos results.csv y procesos reales; después evaluación nativa de los dos modelos y vistas diagnósticas, preservando baseline y negativos. Campaña pendiente.


### V161 — seguimiento y preparación del evaluador nativo

Primer brazo legacy completó60/60 épocas (experiment.json presente). Segundo brazo coverage comprobado activo PID37860/runtime35824, GPU5524MiB/62%, RAM libre8.62GiB; results.csv avanzó de3 a4 épocas durante esta activación. Hay diferencia entre tiempo de pared y ejecución efectiva: no interpretar el intervalo del heartbeat como tiempo de GPU continuo. No se inicia otra carga GPU.

Se prepararon40 imágenes de validación como RGB/timestamps públicos, con manifiesto de máscaras privado separado. evaluate_native.py reutiliza el emparejamiento uno-a-uno IoU0.5, verifica hashes y conteos y mantiene todas las instancias nativas en el denominador; exige confianza0.25. Sintaxis comprobada, ejecución y verificación de resultados pendientes de finalizar el segundo entrenamiento. No se comparan todavía los brazos ni se promueven sus métricas internas a conclusión final.


### V161 — 29 épocas y controles del evaluador

Coverage avanzó de4 a29/60 desde la activación anterior; PID37860/runtime35824 siguen presentes y el supervisor acumula ejecución efectiva. Mínimo libre5.94GiB, por encima de reserva2GiB; lectura actual9.12GiB. La admisión6.5GiB es umbral de inicio, no motivo para interrumpir un trabajo sano al bajar transitoriamente de él. Primer brazo ya completado, sin segunda carga GPU.

Se añadió parámetro de manifiesto privado al evaluador diagnóstico para probarlo sin tocar los40 ejemplos reales del experimento. Cinco controles de integración pasan: hueco preservado, duplicado como falso positivo, clase equivocada como FP/FN, objetivo nativo de un píxel conservado y rechazo de archivo de predicción con hash alterado. Fixture y resultados en evaluator_test_fixture/ y evaluator_tests.json; no son resultados del modelo. La comparación predictiva sigue pendiente de60/60 y evaluación nativa.


### V161 — 44/60 y encadenamiento de evaluación

Coverage44/60, proceso real confirmado37860/runtime35824, RAM libre11.68GiB; no fallo constatado. Se preparó e inició controlador de evaluación PID42788 en estado explícito waiting_for_training_no_gpu_execution. Espera ambos trabajos completos sin error y liberación del lock; verifica60 épocas, usa last.pt, comprueba hash de pesos y40 predicciones antes de evaluar máscaras nativas. Cada inferencia mantiene admisión6.5GiB y reserva2GiB mediante supervisor existente, de forma secuencial. No es inferencia en marcha todavía. Cola y errores quedan en native_evaluation/queue_state.json, queue.log y queue.err; no relanzar duplicados. El seguimiento/localización y evaluación de vistas diagnósticas siguen pendientes.


## V161 — comparación final nativa y transferencia diagnóstica

Ambos brazos completaron60 épocas con pérdidas finitas; comprobados hashes last.pt y40 predicciones por brazo. Con confianza fija0.25 e IoU0.5 sobre2222 instancias nativas: legacy638TP/548FP/1584FN, precisión53.79%,recobrado28.71%; coverage743TP/388FP/1479FN, precisión65.69%,recobrado33.44%. Apariencia madura mejora33/315→40/315 aciertos, pero sigue débil. Precisión sobremadura baja81.10%→73.08%; no toda métrica mejora. Se conservan todos los objetivos nativos y los resultados negativos.

Costo efectivo supervisado:2582.34s legacy y9878.65s coverage (aproximadamente3.83 veces). Misma exposición a ejemplos/épocas, no costo equivalente. La política amplía contornos gruesos y resuelve conflictos semánticos por ID; esta comparación de una semilla de optimización no prueba generalización de campo.

Se ejecutaron además dos inferencias nuevas de4 vistas aprobadas, sin cambiar geometría, umbral o materiales. En orden ortográfica/centro/izquierda/derecha: legacy5/4/3/6TP; coverage9/6/4/3TP, con denominadores84/80/82/78. Mejora en tres vistas y retroceso en derecha. Apariencia madura coverage3/1/1/0 frente a legacy0/0/0/2. No sumar estas observaciones como plantas independientes ni promover un ganador universal. Los resultados históricos cycle04 usaban otro umbral: no compararlos directamente como ensayo controlado.

Evidencia comparison.json, native_evaluation y diagnostic_evaluation. Coverage queda candidato experimental congelado para piloto posterior, legacy conservado como comparador; no modelo final ni aceptación física/de entrenamiento del arbusto diagnóstico. Siguiente: recorrido corto con sensores públicos relativos ruidosos, seguimiento/localización y evaluación privada, conservando explícito el bajo recobrado; no reabrir búsquedas estéticas ni más barridos amplios de entrenamiento. Campaña pendiente y reservas intactas.


## V162 — seguimiento disperso y contrato de movimiento relativo

Se revisó la recuperación histórica pose_reprojection_audit_v2.json1.1 (32objetos) y el registro del fallo v1; no se reejecutó la cola antigua. Se ejecutó seguimiento CPU RGB/máscaras predichas sobre izquierda→centro→derecha, con separación asignada de1s por vista. Es prueba temporal dispersa de tres imágenes, no vuelo continuo ni telemetría física. Estimador sin poses ni verdad; mismo MaskTracker conservador existente.

Legacy produjo37 trayectorias,6 con observaciones en varias vistas; coverage35 y5 respectivamente. Evaluador privado con máscaras nativas e IoU0.5 sin exigir clase: dos trayectorias por brazo tienen al menos dos coincidencias verificables y mantienen identidad; no se observan mezclas en ese subconjunto. El resto no queda validado por ausencia de evidencia; cero mezclas observadas no equivale a seguimiento perfecto. Una trayectoria coverage tiene tres coincidencias de la misma identidad. Localización por vista legacy5/9/11 y coverage4/9/8; no confundir con métricas de clase correcta anteriores.

Adaptador del simulador exportó dos incrementos relativos ruidosos conformes a RelativeMotion; solo K y movimiento relativo son públicos, sin origen global. Conversión explícita1cm=0.08BU→0.125m/BU y marco cámaraOpenCV. Ruido reproducible5mm/0.002rad por incremento, heurística no calibrada; no modelo físico de IMU. Las poses exactas se leen únicamente en el adaptador y su procedencia queda privada. El seguimiento2D todavía no consume estos incrementos. Siguiente: triangulación en marco de primera cámara con movimiento público ruidoso y controles de paralaje/reproyección/profundidad; evaluación privada separada, sin introducir identidad verdadera en estimador. Evidencia tracking_v162; campaña pendiente.


## V163 — triangulación con movimiento público: rechazo conservado

Se integraron únicamente incrementos relativos ruidosos en marco de primera cámara, con origen/orientación iniciales arbitrarios. Estimador recibe pistas predichas, K y movimiento público; no recibe poses exactas ni identidades del evaluador. DLT mantiene criterios existentes:≥3 observaciones, paralaje≥3grados, profundidad positiva y error máximo≤3px. Sin ancla de marcador no se afirma localización absoluta; covarianza del movimiento aún no se propaga en esta prueba.

Resultado:0 hitos3D aceptados en ambos brazos. Legacy35/37 pistas carecen de3 observaciones y las otras2 fallan reproyección; coverage33/35 y2 respectivamente. En coverage los errores máximos son5.77 y4.37px. No se relajan umbrales ni se eliminan observaciones para fabricar aceptación. Centroides de máscaras visibles pueden cambiar con oclusión y no representan un punto físico estable; no atribuir causalmente el error solo al sensor.

Cuatro controles sintéticos del estimador pasan: recuperación de punto3D conocido, rechazo de2 vistas, rechazo de paralaje nulo y rechazo de correspondencia inconsistente. No existe precisión3D medible sobre hitos aceptados porque no hubo ninguno. Siguiente: seis cuadros intermedios adicionales en recorrido corto entre las vistas existentes, conservando aspecto/cámara, para disponer de mayor continuidad temporal y soporte; mismo modelo congelado y mismos controles. Es extensión pequeña diagnóstica, no vuelo físico ni evaluación reservada. Evidencia localization_v163/estimate.py, tests.json y resultados por brazo. Campaña pendiente.


## V164 — recorrido intermedio en generación

Se inició secuencia acotada de6 renders adicionales entre izquierda/centro/derecha, sobre arco de radio horizontal constante, misma focal, objetivo, luces y morfología guardada. Tres cuadros existentes se reutilizan, total previsto9 con intervalos asignados250ms; no simulación dinámica de dron. Primeros2 nuevos renders y contratos de107 capachos completados; primer RGB inspeccionado, aspecto conservado. Primer proceso Blender43056 verificado por identidad; ejecución93.65s, código0, mínimo libre10.13GiB. Los siguientes jobs son secuenciales con admisión6.5GiB/reserva2GiB.

Verificador CPU encadenado espera finalización de la ruta antes de contar píxeles de las9 máscaras y exportar8 incrementos relativos ruidosos; su espera no se declara ejecución de inferencia. No se promueve a entrenamiento ni se transfieren exenciones de visibilidad entre vistas. Después: inferencia únicamente de6 cuadros nuevos, conservación de3 caches previos por modelo y seguimiento/triangulación con los mismos controles. Estado de progreso y logs en route_v164; campaña pendiente.

## V164 — nueve vistas verificadas, seguimiento y primeras estimaciones 3D

Ruta terminada: nueve vistas y 963 comprobaciones de píxeles de capachos; ocho incrementos relativos ruidosos. Se infirieron solo los seis cuadros nuevos por cada modelo congelado V161, reutilizando los tres anclajes de cada brazo. Hashes de RGB, máscaras y modelos, configuración de inferencia y completitud verificados. Ejecuciones GPU secuenciales: legacy54.74s y coverage40.58s, mínimos libres9.26/9.33GiB. Aspecto y morfología aprobados sin cambios; ninguna promoción a entrenamiento.

Seguimiento RGB/máscaras sin verdad: legacy68 pistas,32 multivista; coverage54 y19. Evaluación privada IoU nativa≥0.5 sin exigir clase:20 y12 pistas con identidad repetida consistente, respectivamente. No se detectaron mezclas entre las coincidencias verificables; las observaciones sin coincidencia siguen sin validar. Hay fragmentación: varias pistas pueden representar el mismo capacho. Localizaciones correctas por vista legacy5/7/10/10/9/12/11/7/11; coverage4/6/2/7/9/5/7/9/8, sobre82/85/80/80/80/77/77/78/78 instancias visibles. Son observaciones repetidas de una planta, no muestras independientes.

DLT conserva exactamente la función probada V163 (comparación AST): tres observaciones mínimas, paralaje≥3°, profundidad positiva y reproyección máxima≤3px. Ahora pasan7 pistas legacy y4 coverage;8/7 fallan reproyección y53/43 carecen de tres observaciones. De las aceptadas,6/7 legacy y4/4 coverage tienen al menos dos coincidencias privadas de la misma identidad. La pista legacy track_000037 pasa DLT pero no tiene ninguna coincidencia de máscara IoU≥0.5: resultado no validado, no prueba de objeto correcto. Las once estimaciones no son once objetos únicos entre brazos.

Las coordenadas están en marco arbitrario de primera cámara, usando solo movimiento público ruidoso. Pasar reproyección no mide exactitud 3D; aún falta contrastar un objetivo físico definido contra geometría privada. Centroides visibles cambian con oclusión; covarianza de movimiento no propagada. Nueve cámaras estáticas con intervalos asignados250ms no constituyen vuelo físico. Siguiente trabajo: evaluación privada del objetivo y error 3D de estas pistas, manteniendo los falsos positivos/no verificados y sin entregar verdad al estimador. Evidencia route_v164/summary.json y archivos por brazo. Campaña pendiente; semillas reservadas intactas.

## V165 — error 3D privado y definición del objetivo

Se reconstruyó únicamente la geometría guardada, sin renders ni cambios estéticos, y se exportaron107 centros de construcción del capacho y centroides de superficie de malla evaluada. Objetivo explícito: centro del capacho inflado, no centro del fruto ni punto de agarre. Hash del intérprete geométrico coincide con archivo de fuentes de V164; morfología idéntica en las nueve vistas. Transformación mundo Blender→primera cámara OpenCV con0.125m/BU verificada mediante origen y dos ejes. No ajuste de alineación a las predicciones; cámara exacta y asociaciones verdaderas se leen solo en evaluador.

De7 estimaciones legacy,6 tienen soporte de identidad repetida: error mediano al centro2.91cm, mínimo0.59cm, máximo9.63cm. Coverage4/4 con soporte: mediana3.60cm, mínimo1.25cm, máximo10.99cm. Son errores condicionales sobre subconjuntos distintos de una planta de desarrollo; no ranking universal ni precisión de campo. Legacy track_000037 permanece sin identidad verificada y error nulo explícito, excluido del resumen condicional, nunca convertido en acierto. Coincidencias parciales no verifican todas las observaciones de una pista. Centroide superficial alternativo produce errores similares, registrados individualmente.

Estos resultados confirman que reproyección baja no garantiza localización métrica precisa. Covarianza y sensibilidad al ruido aún pendientes. Exportación inicial falló por ensamblaje incorrecto del script (SyntaxError antes de construir escena); corregida localmente, compilada y reejecutada:6.20s, código0, mínimo10.47GiB libres. Se preservan ambos registros. Evidencia localization_v165/evaluation_private.json, evaluate.py y localization_v165_geometry/targets_private.json. Siguiente: sensibilidad al ruido público declarado con pistas fijas y mismos controles, sin seleccionar realizaciones por error privado; después revisar propagación de incertidumbre/fusión. Sin nuevos entrenamientos ni promociones; campaña pendiente.

## V166 — sensibilidad a realizaciones del ruido relativo

Prueba CPU acotada:20 semillas de sensor fijadas consecutivamente166000–166019, sin selección posterior por error; no son semillas de plantas ni reservas. Adaptador privado exportó160 incrementos ruidosos validados bajo el mismo modelo heurístico de V164 (desviaciones por250ms:2.5mm y0.001rad). Estimador separado consumió solo estos incrementos públicos, K y pistas predichas congeladas. Se reutilizó la función DLT V163 sin modificar umbrales. Sin nuevos renders, entrenamiento ni cambios de apariencia; archivos V164 preservados y hashes registrados.

En40 evaluaciones (20 por modelo), pistas aceptadas legacy4–11, mediana6; coverage2–7, mediana4. Errores condicionales al centro del capacho, solo cuando hay soporte de identidad: legacy mediana3.29cm, p95 12.91cm, máximo16.26cm (115 aceptaciones repetidas); coverage mediana3.72cm, p95 8.68cm, máximo10.97cm (87). Además16 aceptaciones legacy y2 coverage carecen de identidad verificable y se cuentan aparte; no se convierten en aciertos ni ceros de error. Estas cifras agrupan realizaciones repetidas y conjuntos de pistas variables, no plantas independientes ni precisión generalizable.

La sensibilidad confirma que los controles de reproyección/paralaje actuales no bastan para garantizar precisión métrica estable. No se selecciona una semilla favorable ni se promociona un modelo por estas cifras. Siguiente: revisar consistencia del reajuste robusto y propagación de covarianza en localization.py y marker_motion_fusion.py con controles sintéticos dirigidos; mantener DLT/V166 como comparación, sin inventar anclas de marcador ausentes. Evidencia sensitivity_v166/protocol.json, estimates.json y evaluation_private.json. Campaña pendiente.

## V167 — auditoría focalizada del reajuste robusto y covarianza

Pasan13 pruebas existentes (8 de localización y5 de fusión). En40 escenas sintéticas pequeñas con ruido de píxel y una correspondencia perturbada, las40 soluciones robustas aceptadas cumplen profundidad positiva, soporte declarado y reproyección≤3px después del reajuste final. La implementación ya llama a triangulate sobre el consenso final; no se demuestra un fallo que justifique modificarla en este ensayo. No se reemplazó el DLT de V164 ni se alteraron resultados previos.

Jacobianos de propagación contrastados por diferencias finitas con rotación/traslación no triviales: errores máximos2.63e-9 para estado y2.43e-8 para ruido expresado a izquierda en cámara anterior. La matriz G de MarkerMotionFusion corresponde a esa convención. El adaptador V164/V166 introduce perturbación rotacional a derecha: produce la misma distribución/covarianza con su ruido rotacional isotrópico independiente actual, pero no sería intercambiable con covarianza anisótropa o correlaciones arbitrarias. Ensayo anisótropo confirma diferencia; documentar convención antes de ampliar sensores.

Leave-one-out mide sensibilidad a observaciones, no propaga incertidumbre de pose ni constituye intervalo calibrado. V164 no tiene marcador visual: no inicializar MarkerMotionFusion con verdad para simular un ancla. Siguiente: diagnóstico aislado en marco de primera cámara, perturbaciones compartidas de movimiento según covarianza pública, pistas fijas, dispersión y frecuencia de rechazo; evaluar después contra verdad privada. No elegir realizaciones favorables. Evidencia audit_v167/check.py y results.json. Sin cambios de fuentes productivas, renders o entrenamiento; campaña pendiente.

## V168 — incertidumbre de movimiento usando solo entradas públicas

Diagnóstico CPU con64 perturbaciones compartidas (semilla1682026) de los ocho incrementos públicos V164;128 evaluaciones modelo-realización. Covarianza6x6 completa, ruido rotacional a izquierda en cámara anterior, mismo movimiento por realización para todas las pistas y ambos modelos. Se mantienen todas las122 pistas y64 resultados contabilizados por pista, incluidos rechazos. Estimador sin cámara verdadera ni etiquetas privadas; no se inicializó ningún marcador ficticio. Geometría, modelos y DLT permanecen iguales.

Entre las once pistas aceptadas originalmente, frecuencia de aceptación bajo perturbación:21.9–84.4% legacy y42.2–56.3% coverage. Radios percentil95 de desplazamiento respecto a estimación base, condicionados a aceptación, aproximadamente4.85–9.62cm y7.17–9.55cm. Son sensibilidad al movimiento, no intervalos de confianza: se perturba una medición ya ruidosa, se omite incertidumbre de máscara/identidad y el rechazo trunca la distribución.

Evaluación privada posterior: error al centro supera ese radio en1/6 pistas verificables legacy y1/4 coverage. La pista coverage con error10.99cm tiene radio7.39cm; la legacy que excede está prácticamente en el borde (9.632cm frente a9.623cm), sin interpretación estadística fuerte. La pista legacy sin identidad sigue sin error asignado. No se ajustó un umbral de aceptación a estos errores ni se promocionó una realización favorable.

Siguiente: una comparación acotada con consenso robusto sobre las mismas entradas, contabilizando observaciones descartadas y límites leave-one-out, con marco de primera cámara explícito. Después consolidar entregables del piloto y controles restantes del plan, evitando nuevos barridos de ruido. Evidencia uncertainty_v168/estimate.json y evaluation_private.json; campaña pendiente.

## V169 — comparación robusta y consolidación del piloto

Se ejecutó una comparación acotada de consenso robusto sobre las mismas pistas y movimiento público. Adaptador algebraico aislado copia las funciones existentes y renombra frame_id/position_first_camera_m; no afirma haber detectado marcador ni inicializa fusión con verdad. Umbrales3observaciones,3° y3px conservados. DLT V164 queda intacto como comparación.

Legacy pasa de7 a14 hipótesis aceptadas; coverage de4 a7. Evaluación privada volvió a emparejar todas las máscaras por cuadro y luego verificó únicamente las observaciones retenidas por consenso:11/14 legacy y7/7 coverage tienen al menos dos coincidencias de una identidad. Tres legacy quedan sin verificar. Mediana de error condicional2.81/3.06cm; máximos9.63/10.99cm. Se descartaron8/3 observaciones; sensibilidad leave-one-out no disponible en6/3 hipótesis, registrada como desconocida.

En la unión de96 capachos con al menos un píxel visible durante la ruta,9 legacy y6 coverage tienen identidad apoyada y error≤5cm:9.38%/6.25%. Es denominador diagnóstico que incluye instancias diminutas, no definición final de observabilidad. El aumento de hipótesis aceptadas no basta para declarar cumplimiento del objetivo (>50% observables a5cm y asociación≥90%). Los tres no verificados no son aciertos. Una sola planta de desarrollo no mide generalización.

Se consolidaron etapas y pendientes en robust_v169/pilot_ledger.json: RGB/máscaras, dos entrenamientos sintéticos controlados, seguimiento, error métrico, sensibilidad y comparación robusta ejecutados. Permanecen pendientes anclaje visual real del recorrido, observabilidad/robustez y evaluación final con disjunción. Siguiente trabajo preparado: piloto pequeño con ArUco visible en RGB, calibración pública de tablero y movimiento relativo ruidoso, preservando C05 aprobado. Confirmar detección visual antes de ampliar recorrido; sin nuevas búsquedas estéticas, entrenamiento o barridos de ruido. Cola histórica preparation-only no se interpreta como ejecución. Campaña pendiente y reservas intactas.

## V170 — anclaje ArUco obtenido desde RGB

Dos renders pequeños secuenciales Blender, sin modificar la morfología aprobada. Tablero físico mate construido por celdas geométricas DICT_4X4_50 ID8, cuadrado negro de20cm y margen blanco3.33cm (heurísticas de piloto). Sin composición sobre el RGB ni marcador invisible. Primera ubicación quedó parcialmente ocluida por hojas, inspeccionada visualmente: detector no devolvió marcador. Se conserva ese resultado negativo; se bajó únicamente el tablero para despejar la vista y se generó un segundo render versionado.

En el segundo RGB el detector identifica8. IPPE con criterios existentes acepta pose: RMSE reproyección0.0758px; alternativa3.3488px. Detector solo recibe RGB, K y tamaño/diccionario públicos. Evaluador privado independiente obtiene error traslacional1.60cm y rotacional0.083°. Se verificó igualdad exacta de morfología JSON con C05 y se inspeccionó el segundo render. No significa calibración física ni precisión de vuelo; tablero sin soporte mecánico modelado en esta escena diagnóstica.

Ejecuciones28.14s/18.20s, código0, mínimos libres11.34/11.38GiB. No se alteraron shaders/órganos para facilitar detección. Siguiente: cuatro vistas adicionales acotadas del tablero fijo, reutilizando centro para total5; detectar desde RGB, exportar movimiento relativo ruidoso y validar nuevas máscaras antes de inferencia/fusión. RGB con tablero requiere predicciones propias, no reciclado silencioso de caches previos. Evidencia marker_v170/detection_unoccluded.json y evaluation_private.json; ambas ubicaciones conservadas. Campaña pendiente.

## V171 — cinco vistas con marcador, fusión e inferencias nuevas

Se completaron cuatro renders RGB adicionales y cinco máscaras nuevas; RGB central V170 reutilizado tras comprobar mismo marco de cámara. Cinco morfologías idénticas,535 recuentos nativos de capachos y correspondencias material/apariencia validados. Tablero fijo; vista derecha inspeccionada y sin cambio del aspecto de planta. No promoción a entrenamiento ni aprobación física de contactos.

Detector RGB identifica ArUco8 en5/5 vistas. Fusión se inicializa con pose visual y acepta las cinco correcciones; solo consume tamaño/K públicos, esquinas RGB e incrementos relativos ruidosos (500ms, ruido a izquierda cámara anterior, semilla1712026). Covarianza de esquinas0.5px es heurística. Evaluador privado: error del centro de cámara1.50–2.00cm con pose visual y1.37–1.50cm fusionada; rotación fusionada0.058–0.099°. Son cinco vistas sintéticas de tablero ideal, no vuelo físico ni calibración real.

Tras validación se ejecutaron diez inferencias nuevas (cinco por cada modelo V161 congelado), secuenciales. Hashes RGB/máscaras y completitud comprobados, sin reutilizar predicciones del fondo previo. Propuestas aceptadas no equivalen a detecciones correctas; evaluación de capachos aún pendiente. Todos los jobs terminaron código0 y mínimo libre>10.99GiB. Se corrigió únicamente next_action obsoleto heredado en contratos nuevos para no regresar al ciclo de colisiones.

Siguiente: seguimiento de estas predicciones y triangulación en marco del marcador realmente decodificado, comparando poses visuales y fusionadas sobre las mismas observaciones. Evaluación privada de identidad retenida y capachos únicos a5cm. No hacen falta más renders ni entrenamiento para ese paso. Evidencia marker_route_v171/verification.json, poses_public.json, evaluation_private.json y prediction_verification.json. Campaña pendiente.

## V172 — localización anclada, comparación visual/fusión

Se reutilizaron las pistas V171 calculadas para el video solicitado (43legacy/34coverage); no se repitieron inferencias, seguimiento ni renders. Triangulación robusta en marco del ArUco8 realmente decodificado, comparando pose visual y fusionada sobre idénticas observaciones. Estimador consume únicamente predicciones y poses públicas. Evaluador privado empareja máscaras nativas por vista y restringe auditoría a observaciones retenidas por consenso.

Ambas modalidades aceptan7 hipótesis legacy,6 con identidad apoyada, y6 coverage, todas apoyadas. Error mediano condicional legacy1.368cm visual/1.427cm fusionado; coverage2.860/2.813cm. Máximos5.105/5.482cm y6.914/6.925cm. En ambos modos quedan5 capachos únicos legacy y4 coverage a≤5cm; una hipótesis legacy no verificable permanece explícita. Con soporte más exigente (≥3 coincidencias de una identidad y≥80% de observaciones retenidas emparejadas) quedan3/2. Ningún umbral ajustado por estos resultados.

Denominador diagnóstico:95 capachos visibles en al menos una vista, incluyendo diminutos; no definición final de observabilidad. La fusión mejora la pose de cámara del ensayo anterior, pero no aumenta aquí el número de capachos localizados. No comparar directamente este recuento de cinco vistas con las nueve vistas sin tablero como si fuera una ablación controlada. Campaña y objetivo>50% a5cm siguen pendientes.

El siguiente cuello de botella a estudiar es percepción/soporte multivista: estratificar por área visible nativa, cobertura de coincidencias por órgano y fragmentación de IDs sobre los archivos existentes. Mantener tamaños pequeños en el denominador y no llamar observable a todo lo detectado. Elegir después una intervención acotada de escala/recortes según evidencia, evitando nuevas vueltas de ruido/poses. Evidencia anchored_v172/estimates_public.json y comparison_private.json; no cambios estéticos ni promoción a entrenamiento.


## V173 — corrección acotada de tamaños foliares y preparación de entrenamiento

Solicitud directa del usuario: reducir extremos conservando arquitectura y comparar antes de entrenar con arbustos actuales. Script reproducible scripts/limit_review_leaf_sizes.py limita proporcionalmente láminas a12cm de largo y9cm de ancho; límites engineering_heuristic de revisión, no valores botánicos medidos. En C05 cambian39/388 hojas, máximo anterior18.57×15.09cm. Prueba de restauración demuestra igualdad exacta de todos los demás campos: ramas, nodos, orientaciones, pecíolos, frutos, colores y metadatos intactos. Versiones originales preservadas. Copias corregidas C01–C10 preparadas; C05 conserva reparación V151 más reciente. Las diez pasan validación morfológica con advertencias.

Render Blender real V173 con misma cámara y configuración que V171f4, inspeccionado junto al original; disminuye la hoja amarillenta inferior sin cambiar estructura. Comparación HTML en leaf_limit_v173/comparison.html. Render y máscaras20.24s, mínimo libre11.49GiB. Controles388 conexiones foliares,495 superficies texturizadas con UV finitas,80 bifurcaciones sin separación,107 correspondencias material-identidad-clase;388 nervaduras sin UV usan material no texturizado. Cámara privada idéntica. No se afirma ausencia global de colisiones por estas comprobaciones.

Auditoría focalizada de34 pares rígidos conocidos, con rayos perspectiva desde la cámara actual sobre geometría evaluada:26 ocultos en muestreo y8 expuestos. No equivale a auditoría exhaustiva ni visibilidad desde todas las vistas. Se preservan resultados y C05 continúa diagnóstico, sin promoción a entrenamiento. Preparado training_preflight_v174.json: selección por semilla, separación de validación y desarrollo, controles de hashes y reservas, clases de apariencia sin madurez interna. Próximo: candidatos C01/C07 con controles de geometría evaluada y exposición, seleccionando muestras aptas sin abrir otra reparación general. No ha comenzado un nuevo entrenamiento; campaña pendiente. Validador de grafo pasa152nodos/261aristas.


## V174 — admisión técnica de C01/C07 corregidos

Dos auditorías Blender de mallas evaluadas y dos revisiones de exposición perspectiva, secuenciales, sin reparar ni modificar arquitectura. C01:98 pares rígidos residuales,85 ocultos en el muestreo y13 expuestos; C07:171,145 ocultos y26 expuestos. No son aumentos respecto a C05: son plantas distintas. Contactos naturales reconocidos por el auditor se registran aparte. Exposición por muestreo de intersecciones no demuestra gravedad perceptual ni visibilidad en todas las vistas; no se interpreta como ausencia exhaustiva de defectos. No se promueven cuadros completos a entrenamiento. Cuatro jobs terminados código0, memoria libre mínima13.39GiB; PID reales y logs conservados, sin trabajos pendientes ni PIDnull presentados como ejecución.

Para avanzar sin otra reparación general, siguiente prueba acotada: factibilidad de recortes que excluyan conservadoramente las proyecciones completas de objetos en contactos rígidos residuales y contengan capachos. Si existen ventanas aptas, producir dos pares diagnósticos RGB/máscara y conservar todas las instancias visibles de cada recorte; no borrar etiquetas, rellenar defectos ni usar madurez interna. Separar por semilla y verificar hashes antes del smoke de entrenamiento. Si no hay ventanas aptas, registrar el resultado negativo y elegir una corrección localizada o un candidato distinto. Protocolo actualizado en leaf_limit_v173/training_preflight_v174.json. Reservas intactas; entrenamiento nuevo no iniciado y campaña pendiente.


## V175 — recortes aptos, entrenamiento pequeño y comparación negativa

Petición directa: comprobar recortes y entrenar si pasan. Factibilidad Blender proyectó límites completos de objetos involucrados en todos los contactos rígidos residuales (también ocultos), con margen4px. Existen8 ventanas C01 y6 C07 sin intersección; se usó esta política conservadora, no la alternativa de parches de triángulos calculada. Arquitectura y apariencia no modificadas. Dos renders reales RGB/máscaras nuevos con cámara fija; controles de conexiones, UV de superficies texturizadas, bifurcaciones, identidad-material-clase, correspondencia de píxeles y morfología normalizada por Plant pasaron. La comparación inicial de JSON bruto detectó campos opcionales ausentes; normalización por el esquema confirmó equivalencia sin cambios morfológicos.

Dataset8 recortes C01 (semilla814200,17 instancias) para entrenamiento y6 C07 (814206,11) para validación; sin ventanas superpuestas dentro de cada planta. Todas las instancias visibles se conservaron, incluso pequeñas/cortadas; áreas entrenamiento1–1087px y validación1–566px. Semillas separadas de cycle04 y reservas; hashes RGB únicos y disjuntos del dataset histórico. Aceptación limitada a segmentación sintética de estos recortes, no a física ni a cuadros completos. Truth de cámara/madurez interna ausente del manifiesto del entrenador; etiquetas son apariencia.

Ajuste YOLO26n-seg desde last.pt Coverage V161,12 épocas fijas,512px,batch2,AdamW lr1e-4,semilla1752026,supervisión any_coverage/ratio2. Se evalúa last.pt, no best.pt seleccionado por validación. Entrenamiento completado en53.89s (job64.36s), mínimo libre5.74GiB. Comparación externa nativa de máscaras con las mismas6 imágenes, confianza0.25 e IoU0.5 por clase: Legacy V161, Coverage V161 y nuevo V175 obtienen cada uno0TP/0FP/11FN. Recall0; precisión no definida porque no hay predicciones. No hay mejora demostrada y no se promueve el nuevo modelo. Resultado negativo conservado. El primer evaluador falló antes de ejecutar por codificación cp1252; corregido a UTF-8, segundo job terminó código0.

Galería comparison.html y comparison.png muestran referencia y tres modelos. Un solo arbusto por partición y recortes escasos no permiten inferir generalización; no es holdout final. Siguiente: aumentar moderadamente plantas/vistas de desarrollo con recortes aptos y capachos completos de mayor tamaño, medir rendimiento de selección antes de otro entrenamiento, mantener pequeñas instancias y congelar partición; no ajustar umbrales mirando C07 ni regresar a reparación general. Estado crop_training_v175/summary.json; campaña pendiente, reservas intactas.


## V176 — ampliación acotada de recortes actuales

C02/814201 para entrenamiento y C08/814207 para validación de desarrollo, separados antes de inferencia. Dos auditorías de mallas evaluadas, dos comprobaciones de factibilidad y dos renders RGB/máscaras nuevos, sin cambios de arquitectura ni reparaciones generales. Selección exige un capacho con caja proyectada completa de al menos256px² y lado mínimo12px (heurística de selección, no dato botánico); excluye objetos completos de todos los pares rígidos residuales con margen4px, incluidos ocultos. Se mantienen todas las instancias visibles en cada recorte admitido, también pequeñas y cortadas.

Verificados contratos de morfología normalizada, conexiones, UV texturizadas, identidad-material-clase, píxeles de máscaras y disjunción de semillas/hashes con V175 y cycle04. Estas pruebas no aceptan cuadros completos ni física. Calidad nativa por partición: [{"split": "train", "crops": 4, "instances": 14, "native_area_min": 60, "native_area_median": 326.0, "native_area_max": 735, "under16": 0, "at_least256": 8}, {"split": "val", "crops": 3, "instances": 6, "native_area_min": 96, "native_area_median": 287.5, "native_area_max": 1111, "under16": 0, "at_least256": 4}]. Seis jobs código0, mínimo libre 10.481769561767578GiB. Reservas intactas.

Próximo: unir recortes admitidos V175/V176 respetando separación por planta, comprobar cobertura de clases y congelar protocolo pequeño antes de otro entrenamiento; comparar pesos previos con mismo umbral fijo y máscaras nativas. No se inició nuevo entrenamiento ni se promueve modelo. Campaña pendiente. Evidencia crop_expansion_v176/summary.json.


## V177 — entrenamiento combinado de recortes actuales

Se combinaron V175/V176:12 recortes/31 instancias C01–C02 para entrenamiento;9/17 C07–C08 para validación de desarrollo. Clases presentes en ambas particiones (train pintona10,madura14,sobremadura7;val8,6,3), hashes y máscaras nativas revalidados, partición por semilla y reservas intactas. Sin nuevos renders ni cambios de arquitectura. Ajuste de12 épocas desde Coverage V161, mismos hiperparámetros/semilla1752026 que V175; se usa last.pt fijo, no best seleccionado. Entrenamiento completado; comparación externa de Legacy/Coverage V161, V175 y V177 sobre idénticas9 imágenes, confianza0.25 e IoU nativa0.5 por clase.

Resultados: {"legacy_v161": {"tp": 0, "fp": 0, "fn": 17, "precision": null, "recall": 0.0}, "coverage_v161": {"tp": 0, "fp": 0, "fn": 17, "precision": null, "recall": 0.0}, "current_v175": {"tp": 0, "fp": 0, "fn": 17, "precision": null, "recall": 0.0}, "current_v177": {"tp": 0, "fp": 0, "fn": 17, "precision": null, "recall": 0.0}}. Estratos por área visible y contacto con borde registrados en evaluation.json, todos los tamaños en denominador; precisión indefinida cuando no hay predicciones. No promoción automática ni afirmación de generalización con dos plantas de validación. Siguiente: auditoría de supervisión/entrada y distribución de confianza solo en entrenamiento, sin modificar umbral operativo ni ajustar contra C07/C08. Campaña pendiente. Evidencia crop_combined_v177/summary.json y comparison.html.


## V178 — auditoría de entradas reales y corrección del preprocesado

Solicitud explícita: diagnosticar antes de volver a entrenar. Se verificaron los 12 RGB de entrenamiento, 31 instancias, hashes de imágenes/máscaras, correspondencia clase-ID, máscaras tras reducción, colación y tensores RGB; las clases cargadas en los cuatro checkpoints son 0 pintona, 1 madura, 2 sobremadura. Los pesos se identificaron por SHA256 en input_audit_v178/audit.json. Las clases expresan apariencia del capacho, no madurez interna.

Fallo confirmado: RasterDataset usaba INTER_AREA y la inferencia estándar INTER_LINEAR. En los mismos recortes, pesos y confianza0.25, cambiar únicamente el tensor recupera 7 propuestas de Coverage V161 y34 de V177, frente a0 con LINEAR; propuestas no equivalen a aciertos. El control positivo de cuadro completo también devuelve propuestas: los modelos no están vacíos. Las máscaras inspeccionadas se alinean con capachos y todas las instancias de entrenamiento sobreviven la reducción. No se encontró intercambio RGB/BGR ni cambio de clases/pesos.

Corrección: entrenamiento futuro usa INTER_LINEAR como LetterBox estándar; un predictor explícito INTER_AREA permite evaluar checkpoints históricos sin modificarlos. Siete pruebas pasan, incluidas igualdad píxel a píxel de entrenamiento/inferencia y compatibilidad histórica. Se conserva la política independiente de remuestreo de máscaras. El diagnóstico inicial falló solo por comparar tamaños960/512; se corrigió y reejecutó exitosamente, preservando ambos registros. La prueba causal queda congelada en execution_jobs/input_v178_scale_sources.zip; el script diagnóstico ahora declara AREA explícitamente para ser reproducible tras el cambio del cargador.

Reevaluación compatible: mismos9 recortes C07/C08,17 instancias, confianza0.25, IoU nativa0.5 con clase. Legacy V161, Coverage V161 y V175:0TP/0FP/17FN; V177:0TP/2FP/17FN. Por tanto el fallo de preprocesado es real pero no explica por sí solo el fracaso de validación. La evaluación V177 anterior se conserva como resultado bajo preprocesado incompatible. No se promueve ningún modelo, ni se inicia otro entrenamiento. Evidencia y comparación: input_audit_v178/corrected_evaluation/.

Siguiente: cuantificar aciertos y errores de máscara/clase en entrenamiento con preprocesado compatible y aislar sensibilidad a escala/contexto exclusivamente en C01/C02 antes de fijar otro protocolo. No ajustar umbrales contra validación ni volver a barridos de colisiones. Reservas intactas; campaña pendiente.


## V179 — diagnóstico sobre plantas completas solicitado por el usuario

La selección de recortes sin contactos sesgó V178 hacia esquinas y no permite concluir ausencia global de detecciones. Se evalúan tres cuadros completos actuales C05/C07/C08 con hojas limitadas, sin nuevos renders, entrenamiento ni selección según predicciones. Todas las257 instancias visibles se conservan. Entrada960 cuadrada, INTER_AREA compatible con pesos históricos, confianza0.25 e IoU nativa0.5 por clase. Resultados: {"legacy_v161": {"tp": 15, "fp": 37, "fn": 242, "precision": 0.28846153846153844, "recall": 0.058365758754863814}, "coverage_v161": {"tp": 16, "fp": 29, "fn": 241, "precision": 0.35555555555555557, "recall": 0.0622568093385214}, "current_v175": {"tp": 24, "fp": 145, "fn": 233, "precision": 0.14201183431952663, "recall": 0.0933852140077821}, "current_v177": {"tp": 19, "fp": 190, "fn": 238, "precision": 0.09090909090909091, "recall": 0.07392996108949416}}. Comparación en full_view_diagnostic_v179/comparison.html. Prueba de desarrollo diagnóstica: no valida contactos, física ni generalización real. Los cambios de contexto y escala impiden atribuir las diferencias respecto de los recortes a una sola causa. Campaña pendiente.


## V180 — historial visual para nueva selección humana

El usuario observa divergencia visual y solicita cinco arbustos por cada diez versiones para decidir un punto de retorno. Galería de originales conservados:24 secciones,90 apariciones y83 imágenes únicas. Bloques numéricos de diez con hasta cinco muestras distribuidas y casillas faltantes explícitas; V41–90 no contiene una tanda completa Blender equivalente. Las vistas de un mismo arbusto no se presentan como plantas independientes. Se añaden primeras propuestas basales, familias V136 A–E, cinco variantes D V138, cinco muestras V141, cinco originales aprobados V142 y los mismos cinco IDs actuales V173–176. Hashes y rutas en visual_history_v180/manifest.json. No se regeneraron plantas históricas con el código actual.

La inspección de paneles V142/actual confirma un cambio visible de encuadre/proyección; no es una comparación causal controlada de geometría. Las notas distinguen cambios de cámara, reparaciones locales C05 y límite foliar V173. Se mantiene selección pendiente antes de entrenamiento, restauración o nuevas modificaciones. No se declara ninguna familia ganadora ni se descarta el juicio visual humano.


## V181 — retorno a V142 y piloto sintético de cultivo

El usuario solicita conservar V142, corregir sólo colisiones necesarias y externamente visibles con mínima modificación, formar cultivos y preparar un piloto exclusivamente sintético. Se copian originales C01/C02/C03/C04 para entrenamiento, C06/C07 para validación y C09/C10 para prueba de desarrollo. Cuatro hileras pequeñas de dos plantas;48 vistas previstas,32/8/8 por partición. Mismas topologías D compartidas: no son familias botánicas independientes ni un nuevo holdout externo. Reservas914140–914145 intactas.

Se reutiliza exactamente la lógica de materiales del renderer V142 (copia y SHA en protocolo); pequeñas variaciones de paleta por semilla de escena e iluminación de cultivo se registran por separado. No se aplican reparación V151 ni límite foliar V173. Hay suelo y tutorado, sin las plántulas geométricas rechazadas por el usuario. Dos previews iniciales con plántulas se conservan fuera del dataset en preview_with_seedlings_superseded.

Primera escena:207 contactos rígidos;34 muestreados expuestos desde la primera cámara, mayormente menores de2px. Se seleccionan cuatro capachos por extensión visible>=4px como criterio de revisión, no umbral físico. Búsqueda acotada de24 poses por órgano, ángulos pequeños, sin nuevos pares rígidos. Sólo dos pedicelos cambian4grados; permanecen idénticos los campos no pedicelares. Auditoría posterior203 contactos; no se exige cero global ni se afirma aceptación física. Las intersecciones visibles restantes requieren revisión del RGB, no reparaciones automáticas generales.

Captura1280×720 Cycles16 muestras, máscaras de instancia sin antialias y oclusores completos, clases por apariencia del capacho. El exportador conserva todos los fragmentos visibles en uint16 y verifica hashes, paleta, conteos y disjunción. No recorta esquinas ni oculta etiquetas para eludir contactos. Dataset no se admite a entrenamiento sin finalizar controles y revisión visual. Cola secuencial con una GPU pesada y guardas de memoria; scripts y protocolo versionados.


### V181 — captura completa y revisión previa al entrenamiento
48/48 RGB/máscaras completos; cuatro trabajos terminaron con código 0. Particiones 32/8/8 con semillas disjuntas y sin las seis reservadas. 4596 observaciones de instancia: train 2743, val 826, test 1027. Las clases describen apariencia del capacho. Ver field_pilot_v181/dataset_review/index.html y actual_input_audit.json.

Auditoría del cargador real: igualdad exacta RGB con LetterBox INTER_LINEAR, clases y cajas finitas, píxeles/cajas coincidentes con raster uint16 sin pérdida. La supervisión any_coverage a 960/ratio2 conserva todos los objetivos de train. Resultado negativo: nearest reducido elimina 60 fragmentos val/test; evaluación final obligatoria contra máscaras nativas. Primer intento del auditor corrigió singleton HxWx1 de imread; datos sin cambios.

Revisión visual de panorámicas de todas las vistas y hojas ampliadas de contactos: admitidas únicamente para piloto de reconocimiento; contactos localizados conservados como limitación, no certificados naturales ni físicamente válidos. Dos pedicelos ya cambiados cuatro grados registrados correctamente en metadata; ninguna nueva reparación. Arquitectura V142 conservada, sin plántulas de base. Fondo sencillo y topología D compartida limitan generalización. Entrenamiento no iniciado; siguiente paso piloto pequeño con comprobación de pesos y comparación justa frente al modelo anterior.


### V182 — piloto solicitado y comparación nativa (resultado negativo)
YOLO26n-seg desde inicialización general COCO, adaptación de uchuva exclusivamente sintética; 12 épocas, 32 imágenes, 960 px, batch1, ratio2 any_coverage, AdamW. No es fine-tuning desde V177. Entrenamiento terminado código0, 332.1s; mínimo RAM libre del guard8.23GiB. Clases y hashes inicial/final comprobados.

Comparación independiente sobre las mismas16vistas completas (8val/8test) y raster uint16 original. Confianza0.25; matching uno-a-uno por clase con IoU máscara0.50; todos los tamaños incluidos. V177 usa INTER_AREA histórico y V182 INTER_LINEAR; last.pt fijado antes de evaluar. V177 val:112TP,375FP,714FN,P22.998%,R13.559%,F1 17.060%; test139TP,417FP,888FN,P25%,R13.535%,F1 17.562%. V182:0predicciones;826FN val y1027FN test. Precisión indefinida sin predicciones (JSON0por convención), recall/F1cero. No AP.

Evidencia: field_training_v182/{protocol.json,trained_weights_audit.json,evaluation.json,metrics.csv,comparison.html}. Guardados máscaras predichas y resultados por vista/clase; muestra prefijada view003. No se promueve V182. Pérdidas bajaron pero no se demostró reconocimiento; no atribuir causalidad exclusivamente a las12épocas sin diagnóstico de optimizador. Siguiente: diagnóstico train-only de gradientes/pasos AMP y sobreajuste pequeño antes de reentrenar, considerar arranque desde pesos sintéticos anteriores. No retocar geometría ni ajustar sobre test. Campaña pendiente.

Verificación evaluador: sintaxis y prueba de matching (duplicado, clase errónea, TP y FN) aprobadas. Validador del grafo reportó10localizadores no resueltos en guías/gobernanza ajenas a esta modificación; se registra sin alterar esos documentos.


### V183 — diagnóstico de optimización y sobreajuste, 18 de octubre de 2026

Se usaron exclusivamente train_a_view_003 y train_b_view_003 (156 instancias). Las particiones de validación y prueba no se usaron para ajustar. Cada brazo procesó 80 lotes: 40 épocas de dos imágenes, 960 px, batch 1, any_coverage ratio 2, AdamW LR constante 0.001, sin warmup, decaimiento ni aumento. Esta configuración controlada no reproduce todos los parámetros históricos de V182.

Hallazgo histórico: batch 1 con nbs 64 y warmup de tres épocas en V182 permite reconstruir solo nueve intentos de optimización en 384 lotes. La versión instalada coincide con el registro (Ultralytics 8.4.114); los pasos AMP efectivos históricos no se registraron y no se pueden afirmar retrospectivamente.

Medición nueva: hook posterior del optimizador, gradientes finitos, escala AMP y diferencias float32 de los parámetros en memoria antes/después de cada intento. El control V182 con acumulación 64 tuvo un intento, omitido por gradientes no finitos: cero parámetros actualizados. V182 con acumulación 1 tuvo 80 intentos, cinco omitidos y 75 ejecutados. V177 con acumulación 1 tuvo dos omitidos y 78 ejecutados. Cada paso efectivo modificó 426 tensores entrenables, incluyendo model.0.conv.weight; cada paso omitido produjo delta exactamente cero. Esto distingue optimización real de cambios de buffers BatchNorm o redondeo de checkpoints.

Evaluación nativa a confianza 0.25 e IoU 0.50, SOLO sobre las dos imágenes ajustadas: V182 inicial/control 0 TP y 156 FN; V182 corregido 92 TP, 32 FP, 64 FN (P 74.19%, R 58.97%); V177 inicial LINEAR 31 TP, 90 FP, 125 FN; V177 ajustado 87 TP, 31 FP, 69 FN (P 73.73%, R 55.77%). AREA histórico da 31 TP y 89 FP para V177 inicial. Los totales raw/EMA coinciden en esta prueba; no se atribuye el fallo a EMA. V182 inicial tuvo confianza máxima cercana a 0.018 y cero TP incluso a umbral 0.01: no era solo un umbral visual.

Conclusión: el presupuesto expresado únicamente en épocas ocultó muy pocos intentos de actualización; AMP puede consumir los pocos intentos iniciales. Las entradas permiten aprender cuando hay pasos efectivos. Partir de V177 es viable, aunque no superó al V182 corregido en estas dos vistas. No se afirma generalización ni superioridad global de una inicialización. No se repitió el entrenamiento completo ni se promocionaron checkpoints sobreajustados.

Corrección localizada en train_raster_segmentation.py: --nominal-batch-size explícito (piloto técnico por defecto igual a batch), --warmup-epochs (técnico por defecto cero), --weights, --no-amp y contador de pasos realmente ejecutados. Protocolo principal histórico preserva nbs 64/warmup 3 y exige corrida técnica para modificarlo. Ningún cambio de arbustos. Los 96 archivos RGB/máscara originales conservaron hashes. Siete pruebas del raster aprobaron al usar TEMP dentro del workspace; primer intento falló por permisos de TEMP externo. El grafo conserva diez localizadores no resueltos ya documentados. Evidencia en overfit_diagnosis_v183/{protocol.json,baseline.json,results.json,summary.json,comparison.html}, trazas por brazo y snapshot del guard.

## V184–V185: repetición corregida y alternativa ROI (18 de octubre, en ejecución)

Autorización: repetir el piloto completo sin cambiar arbustos y comparar con V177;
si la vista amplia es insuficiente, entrenar vistas cercanas y probar ROI/parches.
V184 parte de V177, 12 épocas, 32 vistas de entrenamiento, 960 px, batch=nbs=1,
warmup=0, máscaras raster any_coverage/2. Se conserva el checkpoint final y se
cuentan pasos realmente ejecutados mediante post-hook; cada época compara los
parámetros en memoria, evitando confundir serialización FP16 con aprendizaje.
Las 8 vistas de validación y 8 de prueba mantienen máscaras originales y todos
sus fragmentos visibles, sin filtrado por tamaño. Comparación fija: confianza
0,25, IoU de máscara por clase 0,50; P/R/F1, no AP. V177 conserva INTER_AREA;
el modelo nuevo usa INTER_LINEAR, igual que su entrenamiento.

Se predeclara como criterio técnico exploratorio P<0,50 o R<0,50 en validación
para activar V185; la prueba no decide parámetros. V185 usa parches nativos
384x384 solapados (paso 256), propuestos exclusivamente desde RGB. La ROI es
una heurística HSV de vegetación, NO un detector de arbusto aprendido. Se
compara sobre las imágenes completas y máscaras originales, incluyendo todo
objeto omitido por la ROI. Las predicciones vuelven a coordenadas globales y
se suprimen duplicados por solapamiento de máscaras sin consultar la verdad.
Los parches preservan exactamente RGB/IDs; son encuadres cercanos de imágenes
1280x720, NO nuevos renders de mayor resolución ni nuevo detalle óptico.
261 parches train y 60 val conservan separación por semillas; test no entra en
entrenamiento. Se prevén 2 épocas (522 lotes) desde V184 si se activa la rama.
La campaña integral continúa pendiente. No se modificó geometría.

Controles: 4 pruebas de ROI/coordenadas pasan. El validador del grafo conserva
10 referencias textuales preexistentes no resueltas en documentación ajena a
este cambio. Estado ejecutable: field_training_v184/continuation.json; resultados
finales se escribirán en summary.json, sin anticipar aceptación del modelo.

## 19 de octubre: comparación V184 completa y V185 provisional; cierre explícito de refinamiento

V184 completó12épocas y381actualizaciones reales, con cambios en memoria verificados por época.
Evaluación original nativa (confianza0,25; IoU de máscara por clase0,50):
- Validación826instancias: V177112TP375FP714FN, P22,998% R13,559% F117,060%; V184270TP208FP556FN, P56,485% R32,688% F141,411%.
- Prueba de desarrollo1027instancias: V177139TP417FP888FN, P25,0% R13,535% F117,562%; V184295TP303FP732FN, P49,331% R28,724% F136,308%.
Se activó ROI/parches por recuperación de validación menor que el criterio exploratorio0,50.
V185 se interrumpió durante época2 al bajar RAM libre a0,804GiB; no completó el piloto. Se conservó y evaluó el checkpoint de época1 (255pasos reales; checkpoint epoch=0). No se repitió entrenamiento para esta revisión.
V185 PROVISIONAL: validación355TP181FP471FN, P66,231% R42,978% F152,129%; prueba450TP234FP577FN, P65,789% R43,817% F152,601%.
Las16vistas son completas y las96imágenes/máscaras originales conservan sus hashes. La ROI es heurística RGB y los parches reutilizan1280x720 nativos; no son nuevos renders cercanos. Evaluación parcial no implica promoción de modelo.
Galería conjunta: field_closeup_v185/comparison.html. Estado: field_training_v184/summary.json.

Instrucción del usuario reafirmada: no volver al refinamiento visual de arbustos. Heartbeat horario actualizado y ACTIVE; preservar V142/V181, resolver memoria mediante prueba acotada, completar el nuevo piloto y avanzar al recorrido/seguimiento/localización según controles. No reabrir barridos de colisiones ni repetir etapas validadas. Campaña integral pendiente.


## 19 de octubre: V186 completo, memoria y transición a seguimiento

Prueba de 64 lotes: 60 actualizaciones reales. Liberar únicamente caché CUDA no usada entre lotes mantuvo el máximo asignado en 3,103 GiB. Se repitió el protocolo completo V185 desde V184, sin reutilizar pesos de la prueba: 2 épocas, 522 lotes y 516 pasos reales; 442 y 437 tensores cambiaron en cada época. No se cambiaron geometría, etiquetas, supervisión ni hiperparámetros de optimización.

La validación final heredada todavía bajó RAM libre a 1,826 GiB, aunque el proceso terminó: se conserva explícitamente esta violación de reserva; no se confunde con los 16,995 GiB mínimos medidos solo durante entrenamiento. Sin repetir entrenamiento, se validó el checkpoint con batch 1, sin gráficos internos y liberación de caché por lote: guard mínimo 18,067 GiB (60 parches). La configuración segura queda incorporada al wrapper para futuras ejecuciones. No se atribuye causalidad exclusiva a gráficos frente a batch/caché, porque cambiaron conjuntamente en esa prueba.

Evaluación nativa fija, mismas 16 vistas: validación 371 TP, 115 FP, 455 FN (P 76,34%, R 44,92%, F1 56,55%); prueba 450 TP, 133 FP, 577 FN (P 77,19%, R 43,82%, F1 55,90%). Frente a V185 parcial mantiene 450 TP en prueba y reduce FP de 234 a 133. Umbrales invariables, sin ajuste usando prueba. Se aceleró NMS mediante rechazo por cajas disjuntas y áreas almacenadas; selección idéntica al algoritmo anterior en 30 pruebas aleatorias.

96 archivos RGB/máscaras y los 8 JSON de plantas conservan sus hashes. Galería: field_memory_recovery_v186/comparison.html. Recuperación histórica de reproyección revisada: versión 1.1, 32 objetos, marker_id presente; no repetir. Preparado field_tracking_v187/readiness.json para 8 vistas consecutivas con las mismas plantas, marcador realmente decodificado y verdad aislada del estimador. No se promueve modelo a producción: recuperación aún limitada. Campaña integral pendiente; refinamiento visual cerrado.


### 19 de octubre: recorrido consecutivo V187 y seguimiento

Ocho fotogramas a intervalos simulados de 0.5 s, arco continuo de -7 a +7 grados, misma iluminacion y plantas C06/C07 V181 sin cambios. No se repitieron barridos de colisiones. Marcador fisico ArUco 8 decodificado en 8/8 RGB. Pasaron 2200 comprobaciones de pixeles nativos, identidades estables, hashes de plantas y lista permitida del paquete publico; siete incrementos relativos con ruido, verdad exacta aislada en evaluador. El primer verificador rechazaba entradas de flores sin pixeles: se corrigio exclusivamente esa distincion semantica; no se editaron mascaras.

V186 congelado, ROI HSV y parches originales, confianza 0.25: 269 TP, 91 FP, 494 FN; P74.72%, R35.26%, F147.91%. Seguimiento: 25 cambios de ID en 183 pares de coincidencias correctas consecutivas; medida condicionada a detecciones emparejadas, no IDF1. Resultado negativo conservado, sin promocion. Video completo a 2 fps en field_tracking_v187/predictions/tracking_2fps.mp4. RAM minima libre: render15.69GiB, inferencia17.37GiB, ambos exit0. Siguiente: poses de marcador realmente decodificado, fusion relativa y localizacion3D; evaluacion privada. Campana pendiente.


### 19 de octubre: localizacion V188 con entradas publicas

Marcador8 realmente decodificado y correccion aceptada en8/8 vistas. Se reutilizaron los umbrales de IPPE, fusion y triangulacion robusta sin ajustarlos con verdad. Sin entrenamiento, renders adicionales ni cambios de plantas. Triangulaciones:44 visuales y45 fusionadas;81 trayectorias sin tres observaciones. Error privado del centro de camara: mediana2.03cm visual /2.18cm fusionada, maximo2.98/2.59cm; la fusion no mejora la mediana. Estos errores son de camara sintetica, no de frutos ni precision fisica. Falta comparar los puntos3D con centros geometricos reales exportados solo al evaluador. Ver field_localization_v188/summary.json y track_support_private.json. Campana pendiente.


### 19 de octubre: error 3D privado V189

Se exportaron238 centros de cajas envolventes de mallas evaluadas de capacho, exclusivamente al evaluador; no son centros internos de fruto ni centroides de mascara visible. Plantas V181 sin cambios, sin render ni barrido de colisiones; RAM minima13.71GiB. Estimaciones V188 congeladas. Evaluacion condicionada a35 trayectorias con identidad unica (34 capachos);3 solo tienen una coincidencia nativa de respaldo. Se excluyen explicitamente2 trayectorias fusionadas mixtas y8 sin coincidencia. Error visual mediano1.67cm,p90=7.13cm,max16.52cm; fusionado mediano1.36cm,p90=6.64cm,max17.19cm,30/35 por debajo5cm. La fusion mejora mediana pero empeora el maximo; no significa precision de toda la poblacion ni promocion robotica. Preparado V190: comparacion controlada de seguidor de cajas existente frente al de mascaras, mismas detecciones y poses, validacion solamente, sin busqueda de parametros. Campana pendiente.


### V191: diagnostico solicitado de omisiones y confusion

Mismas8 vistas V187, pesos V186 y arbustos intactos. Candidatos predeclarados: confianza0.10 con parches384; parches256/stride192 manteniendo confianza0.25. Baseline P74.72/R35.26/F147.91; confianza0.10 P68.99/R45.48/F154.82; parches256 P67.45/R33.94/F145.16. No promocion automatica: vistas correlacionadas. Omisiones geometricas201/201 bajo25px,181/279 entre25-99px,53/283 entre100-399px. No se confunde area visible con tasa de oclusion.57/58 confusiones pintona-madura en grados3/4; grado4 usa apariencia straw_v0, cercano al straw_v1 del grado5. Evidencia de frontera visual dificil, no demostracion de causa unica ni autorizacion para cambiar etiquetas. Menor confianza aumenta las confusiones58→71 aunque recupera TP269→347; parches pequenos descartados. Ejemplos deterministas por cuantiles de area, identidades distintas, y vista completa4 antes/despues en detector_diagnosis_v191. Reserva RAM minima11.85GiB. Siguiente: auditar balance de grados en entrenamiento y preparar ajuste pequeno de casos dificiles, manteniendo test sin seleccionar parametros. V190 queda preparado, no ejecutado, por prioridad de diagnostico solicitada.


### V192: ajuste pequeno de transiciones solicitado por el usuario

Desde V186:2 epocas,80 parches train (64 priorizados por coocurrencia grados3/4 y5,16 contexto),lr0.0002; todas las instancias/etiquetas originales retenidas.160 lotes,156 pasos efectivos,432 tensores cambiados cada epoca. Verificados96 hashes RGB/mascaras y8 JSON de plantas; no reservas ni prueba usados. RAM minima10.54GiB. Misma confianza0.25, parches384→960 e IoU0.5.

En8 vistas V187 correlacionadas: V186 P74.72/R35.26/F147.91; V192 P76.66/R37.88/F150.70. Pintona→madura58→51. Subconjunto predeclarado >=100px visibles y lado caja>=8px nativos:283 observaciones; P67.94/R62.90/F165.32→P70.00/R66.78/F168.35. Predicciones emparejadas a objetivos pequenos se ignoran, no son FP. Prototipos medidos240x240 para entrada960, strides deteccion8/16/32; el criterio equivale a lado5 celdas de prototipo y area39 celdas aproximadamente, no limite teorico universal. Tres mejoras y persistencias/regresiones representadas con seleccion determinista en evaluation/ejemplos_antes_despues.jpg. Dos matrices comparativas en confusion_all.png y confusion_eligible.png. Mejora modesta de desarrollo, sin promocion ni afirmacion de generalizacion. Campana pendiente.


### V193: contexto de cultivo solicitado, sin cambiar arbustos

El fondo anterior tenia suelo con bump pero color casi uniforme, cielo constante y vecino fuera del encuadre. Dos muestras nuevas:4 vecinos adicionales con identidad propia, suelo procedural marron/verde multiescala y cielo atmosferico. JSON y materiales vegetales intactos; vecinos solo del split validacion, sin plántulas geometricas. Mascaras nativas verificadas en ambos encuadres, incluidos vecinos:390 y299 instancias visibles. RAM minima7.78GiB. Primeros intentos fallaron por API de cielo Blender5.1 (NISHITA y dust_density eliminados); conservados logs, no contados como renders validos pese a primer exit0. Reintento explicito python-exit-code1 correcto.

Son muestras de entorno, no prueba de fotorrealismo: horizonte plano y cobertura verde procedural aun simplificados. No se entreno con validacion. Antes/despues misma camara en field_environment_v193/antes_despues.jpg; RGB/mascaras en view_000_rgb_masks.jpg y view_001_rgb_masks.jpg. Proximo piloto debe preservar splits y anotar todas las plantas vecinas; mantener referencias V186/V192. No reiniciar refinamiento botanico.


### 19 de octubre: diagnostico de cierre y presupuesto sin refinamiento

Estimacion solicitada, no nueva ejecucion. Pilotos existentes confirman tiempos de computo cortos: V192146.5s entrenamiento160lotes; V18781.7s para8RGB/mascaras y22.2s seguimiento; V19360.3s dos vistas/seis plantas (incluye construccion). El status.json de14octubre esta obsoleto como lista operativa: no reabrir arquitectura ni colisiones completadas. Falta congelacion global, control V190 y validacion detector, recorridos representativos, disjuncion real de semillas, reserva final y reporte. Objetivo >50% observables a5cm y >=90% precision de asociacion no demostrado. El diagnostico actual34 capachos localizados sobre union138 visibles no sustituye definicion de observabilidad;29 tienen al menos una trayectoria a<=5cm.

Cierre acotado de campaña actual:4-8h de trabajo/ejecucion continua, aproximadamente una jornada, con entorno actual congelado y6recorridos reservados cortos (~60cuadros cada uno); puede concluir resultado negativo. No incluye garantizar objetivo ni nueva campaña ambiental. Siguiente piloto congelado:200train+40val+40test y3vuelos×120cuadros=640renders;800-1600parches×10epocas, estimado6-12h. Campaña mayor1200/200/200+6×300=3400renders,20epocas:24-48h orientativas, mas si sube resolucion/densidad. Medir20renders/100lotes antes de comprometer escala. Fuente y supuestos en campaign_remaining_estimate_20261019.json. No se lanzo trabajo ni se consumieron semillas reservadas para estimar.


## Cierre autorizado — 19 octubre 2026

Campaña cerrada como diagnóstico, no como objetivo científico alcanzado. Véase [cierre y sucesor congelado](cierre_diagnostico_piloto_congelado_2026-10-19.md). Los resultados negativos quedan conservados. Continuidad operativa: `outputs/frozen_field_pilot_20261019/state.json`.
