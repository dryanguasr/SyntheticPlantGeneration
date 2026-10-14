# Estudio retrospectivo: vídeo continuo de una hilera con cultivo de fondo

## Estado y alcance

Campaña cerrada el 12 de octubre de 2026, según `study_complete.json` y
`continuation_status.json` de `outputs/continuous_row_20261008`. El objetivo
científico no se alcanzó. Véase la [evaluación final](evaluacion_video_continuo_2026-10-08.md).
El resto de este documento conserva el protocolo y el registro inicial de
preparación; sus pendientes describen aquel momento, no el estado vigente.
Los experimentos anteriores se conservan. El usuario retiró el límite temporal;
se contabiliza ejecución efectiva sin imponer el presupuesto anterior.

Seis plantas objetivo, semillas 520300–520305, proceden de geometrías previamente
inspeccionadas. Doce plantas de contexto, semillas 620800–620811, usan el mismo
modelo morfológico y tutorado diagonal. Las tres hileras contienen seis plantas
cada una. La separación inicial de 6 m es una elección de ingeniería pendiente
de comprobar con envolventes y cámaras, no una recomendación agronómica.
La configuración pública identifica los marcadores objetivo 0–11; los de fondo
son 12–35. Los roles se declaran explícitamente, sin inferirlos del orden.

## Protocolo autorizado

RGB y máscaras originales sincronizados a 30 Hz, 1280 × 720; ejecución de Gazebo
más lenta que tiempo real permitida. Sin interpolar capturas ni conservar solo
cinco pares por segundo. Recorrido por las dos caras con giro hacia la planta
terminal, corredores libres entre obstáculos individuales y separación de 15 cm.
Comprobar diez segundos técnicos y un giro antes del recorrido completo.

Se mantienen los pesos del ciclo 4 y tres clases de apariencia del capacho.
Inferencia posterior en todos los fotogramas con recortes nativos de 960 píxeles,
20 % de solapamiento y cobertura completa. Caché recuperable con máscaras
comprimidas, propuestas desde confianza 0,001, confianza operativa histórica,
origen por recorte y supresión entre recortes. La ausencia de propuesta no
permite distinguir pérdidas internas de la red o de su NMS; esa causa permanecerá
no determinada cuando no exista evidencia adicional.

Comparación sobre las mismas capturas: protocolo histórico a 1 Hz, seguimiento
histórico por fotograma y conciliación offline por fotograma. Esta última debe
usar soporte temporal, forma, apariencia y geometría; impedir fusiones de objetos
que coexisten y recalcular geometría tras fusionar. Ajuste limitado a 30 vistas
separadas al menos 0,2 s, ocho apoyos iniciales, paralaje de 3°, reproyección de
3 píxeles y sensibilidad máxima de 3 cm, comprobando el resto de las vistas.

El estimador solo recibe RGB, timestamps y calibración pública. Las máscaras,
identidades y poses del simulador pertenecen exclusivamente al evaluador.
El fondo no entra en los denominadores objetivo, pero su atribución errónea al
mapa objetivo permanece como intrusión. No es un holdout independiente.

## Implementación y verificación inicial

- Generación reproducible de doce morfologías de fondo y cola secuencial de
  auditoría/reparación en Blender, ensamblado, exportación y envolventes.
- Roles explícitos; planificación contra cajas individuales y cápsulas de
  tutorado. No usar `bound_exterior_flight_physics.py`: cerraría los corredores.
- Selector de pares con modo explícito sin reducción; validación de frecuencia,
  archivos originales, resolución y discontinuidades. Compatibilidad histórica
  de 5 Hz preservada por defecto.
- Orientación dinámica hacia la planta, reducción de traslación entre 10° y 20°,
  límites de velocidad y aceleración angular. Ejecución real aún por verificar.
- Caché independiente de inferencia por fotograma, recuperable sin repetir los
  fotogramas completos, con hashes de modelo, imágenes y máscaras.
- Ajuste multivista acotado y fusión con reajuste conjunto. Cuatro pruebas pasan:
  ruido y rechazo de observación discordante, soporte temporal, poco paralaje,
  fusión posterior y prohibición de fusión de objetos simultáneos.
- Cuatro pruebas de captura/navegación/presupuesto y tres pruebas históricas de
  contabilidad pasan. Estas pruebas no certifican todavía la simulación.

## Continuidad

La primera auditoría (620800) finalizó en 1.007,94 s efectivos, con aceptación
`passed`, cero colisiones físicas y 362 intersecciones foliares toleradas y
registradas como ocupación blanda; no equivalen a oclusión medida. La segunda
auditoría arrancó automáticamente. No extrapolar esta aceptación a las once
geometrías restantes.

Se añadieron seguimiento por máscaras con flujo inverso y apariencia, tres
protocolos temporales sobre una caché común, observaciones conciliadas con
referencias explícitas a máscaras, evaluador por IoU de máscaras y catálogo de
pérdidas. Una prueba integrada confirma que un objeto contextual incorporado al
mapa objetivo reduce la precisión 3D y permanece fuera del denominador objetivo.
Se prepararon diagnósticos privilegiados con poses del simulador, correspondencias
anatómicas, centroides visibles y centros geométricos proyectados; sus resultados
se etiquetarán separadamente del estimador desplegable.

La cola de continuación alcanza la prueba técnica a 30 Hz y la prueba del giro,
con validaciones separadas. El vuelo completo requiere revisión visual registrada
y congelación de configuración. El generador de vídeos usa cada PNG una sola vez
y exige decodificación completa y concordancia del número de fotogramas.
Todo ello está implementado, pero su ejecución integrada sigue pendiente.

### Recuperación por memoria (8 de octubre, 18:45–18:48 UTC)

La auditoría 620801 se detuvo al bajar la memoria libre a 3,88 GiB. El registro
fallido y sus checkpoints se conservaron. Se identificó retención de datablocks
en los ensayos locales: borrar el objeto temporal no liberaba su malla o curva.
`_remove_pose_objects` libera ahora datos sin usuarios, preservando los compartidos;
su prueba unitaria pasa. No modifica la geometría ni las reglas botánicas.

La cola usa `background_audit_620801_resume1`, carpeta `620801_resume1`, partiendo
del checkpoint de hojas y conservando la reparación reproductiva anterior.
`run.json` indica esa carpeta para el ensamblado. Se reinstalaron ambos
supervisores; el trabajo está en admisión de recursos, esperando 6,5 GiB libres
antes de lanzar Blender. La espera se registra separada, con cero ejecución
efectiva. Hay una ejecución externa de Blender y consumo de WSL; no se detuvieron
ni modificaron procesos ajenos. No confundir este estado con una auditoría activa.

Las etapas técnicas y del giro ya están en `continuation_queue.json`. Después de
revisar las capturas, `freeze_continuous_study.py` exige revisión visual y puertas
técnicas aprobadas. Las etapas posteriores deben añadirse con estos programas:
`export_localization_public.py`, `cache_continuous_predictions.py`,
`track_continuous_predictions.py` (los tres protocolos),
`audit_localization_truth.py`, `evaluate_continuous_study.py`,
`diagnose_continuous_geometry.py`, `render_continuous_videos.py` y
`report_continuous_study.py`. Las rutas convencionales son `public`, `predictions`,
`estimates/<protocolo>`, `evaluation/<protocolo>`, `privileged` y `presentation`.
La auditoría de anatomía requiere las mallas completas `field_full`.

`check_continuous_pipeline.py` está al inicio de la continuación y ejecutará la
batería integrada cuando haya memoria suficiente; las pruebas matemáticas y de
captura ya ejecutadas pasaron. `verify_continuous_isolation.py` repite el estimador
offline denegando rutas privadas mediante un audit hook de Python y exige un mapa
idéntico; este replay aún no se ha ejecutado. El reporte exige esa comprobación.
Los recortes nuevos mantienen un stride nativo de 768 píxeles y rellenan el borde,
para que el solapamiento solicitado no se convierta en 66,7 % al desplazar el
último recorte de una imagen de 1280 píxeles. La supresión entre recortes conserva
su evidencia y puede fusionar propuestas de clases distintas solo con IoU >0,8.

El generador del reporte exige los hashes congelados y vídeos verificados.
La habilidad PDF fue leída y su marcador de inicio ejecutado correctamente una
vez; falta generar el documento, renderizarlo con Poppler e inspeccionar todas
las páginas. No se ha generado todavía el PDF ni ningún vídeo final.

`run_localization_queue.py` ejecuta la preparación inicial. El supervisor
`continue_continuous_study.py` lee `continuation_queue.json` entre trabajos para
encadenar inmediatamente las etapas verificadas que se añadan. Los fallos
requieren diagnóstico; no se borran resultados ni se reintentan silenciosamente.
Un solo trabajo pesado; reserva de RAM de 4 GiB. El heartbeat horario
`continuidad-video-30-fps-uchuvas` está activo. Las esperas del supervisor no
consumen ejecución efectiva.

## Pendientes antes de cerrar

1. Aprobar las doce auditorías; ensamblar, simplificar y revisar visualmente las
   tres hileras, preservar siluetas y capachos y verificar los 36 códigos.
2. Verificar geometría del arco, giro ejecutado mirando la planta y captura
   técnica a 30 Hz; congelar configuración para el vuelo completo.
3. Verificar integración de seguimiento por máscaras y conciliación offline,
   comparadores sobre caché común, aislamiento y cruces/oclusiones difíciles.
4. Ejecutar vuelo completo, auditoría anatómica panóptica y análisis por fotograma.
5. Evaluación 2D/3D, intrusiones de fondo y diagnóstico privilegiado separado;
   catálogo de pérdidas con evidencia y causas no determinadas explícitas.
6. Vídeo principal y diagnóstico a 30 fps, mapa y observaciones, PDF académico
   con figuras y referencias primarias; verificar decodificación completa.

No declarar éxito, transferencia real, tiempo real ni ausencia de duplicados
antes de disponer de resultados. No cerrar la campaña con pendientes.

## Referencias metodológicas

El flujo óptico parte del registro de [Lucas y Kanade (1981)](https://publications.ri.cmu.edu/an-iterative-image-registration-technique-with-an-application-to-stereo-vision-ijcai).
Las convenciones de pose y las soluciones IPPE para cuadrados se documentan en
[OpenCV, Perspective-n-Point](https://docs.opencv.org/4.13.0/d5/d1f/calib3d_solvePnP.html).
La decodificación usa la implementación de [ArUco de OpenCV](https://docs.opencv.org/4.13.0/d5/dae/tutorial_aruco_detection.html).
El cálculo de AP usa la API instalada de [Ultralytics](https://docs.ultralytics.com/reference/utils/metrics), cuya versión debe conservarse en el informe final.
Estas fuentes sustentan métodos, no la precisión del cultivo simulado.


## Supervisión del 8 de octubre, 20:10–20:21 UTC

La recuperación 620801_resume1 terminó aprobada tras 2710,27 s de espera
inactiva por RAM y 324,54 s de ejecución; la espera no se contabiliza.
620800 también aprobó. Las auditorías 620802 y 620803 terminaron sin
intersecciones físicas, pero cada una incumple una separación entre ramas
(20,273 y 22,102 mm frente al umbral de ingeniería de 24 mm). 620804
terminó sin intersecciones físicas y con dos separaciones insuficientes
entre una rama y un pedicelo/capacho. Ninguna de estas tres está aprobada.

Se prepararon revisiones morfológicas versionadas: azimut +5° y −5° en las
ramas vecinas de 620802/620803, y +15° en la rama que interfiere con el
capacho de 620804. La comprobación de cápsulas no deja conflictos de ejes;
no sustituye la auditoría completa de mallas, especialmente para el capacho.
Se verificó que las dos primeras revisiones preservan nodos, órganos y
entrenudos. Se conserva cada intento anterior.

`initial_queue_recovery.json` programa las tres reparaciones y sus auditorías
completas después de las auditorías iniciales, seguidas de selección
condicionada a aprobación, ensamblado y exportación versionados. El supervisor
solo admite esta recuperación explícita del fallo previsto de ensamblado;
cualquier otro fallo requiere diagnóstico. La selección rechaza auditorías
pendientes sin modificar run.json; comprobación negativa ejecutada.

Se reinició únicamente el supervisor en espera para cargar esa recuperación.
La cola inicial y Blender no se interrumpieron. Se verificaron por CIM los
procesos propios: cola 49540, supervisor nuevo 49508 y Blender 57824,
auditando 620805 con avance de registros y mínimo de RAM libre 10,17 GiB.
Pasaron 28 pruebas enfocadas, la compilación de los scripts modificados y
la validación del grafo (151 nodos, 260 aristas). Los vídeos y la captura
completa siguen pendientes de las auditorías y pruebas técnicas.


## Supervisión del 8 de octubre, 21:10 UTC

Procesos reales verificados: cola 49540, supervisor 49508, wrapper 52288 y
Blender 67368. La auditoría 620807 avanza en reparación foliar, con registros
recientes y contador efectivo creciente; mínimo libre observado 9,95 GiB.
La espera del supervisor no es un segundo trabajo de Blender.

620806 aprobó la auditoría completa. 620805 terminó sin intersecciones
físicas, pero el capacho de axis_0_0_branch_9_branch_2_node_4 queda a
6,3615 mm de axis_0_0_branch_9_internode_6, frente al umbral de ingeniería
de 22 mm. Se preservó el intento y se preparó una revisión de azimut +15°
en la rama reproductiva: conserva nodos, órganos y entrenudos y no deja
conflictos de cápsulas de ejes. Esto no demuestra todavía la separación del
capacho: la revisión repetirá reparación local y auditoría completa de mallas.

Se añadió 620805_axis_revision1 a la recuperación persistida mediante escritura
atómica, conservando la cola anterior. No se detuvo ni duplicó el trabajo
activo. Hay tres plantas aprobadas y cuatro revisiones pendientes de auditoría;
620807–620811 aún requieren finalizar sus comprobaciones iniciales.
Se corrigió el estado obsoleto de memory_recovery.json para reflejar que
620801_resume1 ya aprobó; la evidencia del fallo original se conserva.


## Supervisión del 8 de octubre, 22:08 UTC

Las doce auditorías iniciales terminaron. Las revisiones 620802–620805
aprobaron sus auditorías completas con cero intersecciones físicas y cero
incumplimientos de separación. También aprobaron 620809 y 620810: nueve
plantas de fondo tienen ahora una versión aprobada.

El ensamblado original falló a las 22:05:12 UTC y la recuperación automática
ejecutó correctamente las cuatro revisiones conocidas. El segundo ensamblado
se detuvo a las 22:07:37 UTC por la auditoría pendiente de 620807. Se comprobó
que no quedaban procesos propios ni locks activos antes de reanudar. Las
últimas auditorías mostraron separaciones insuficientes de tallos en 620807,
620808 y 620811, sin intersecciones físicas. Se conservan ambos fallos.

Se prepararon revisiones morfológicas conservando nodos, órganos y entrenudos:
620807 gira una rama +5°; 620808 gira dos ramas +5°/−5°; 620811 gira cuatro
ramas +5° (dos pares adicionales proceden del control conservador por cápsulas,
no de un rechazo de mallas). Todas eliminan los conflictos del control de ejes,
pero aún requieren auditoría completa. Una primera búsqueda limitada a los
dos pares de mallas de 620811 se interrumpió porque omitía esos otros pares
conservadores; no produjo una variante aceptada ni alteró Blender.

La recuperación revision2 se activó preservando la cola y selección anteriores.
El supervisor 26844 inició Blender 54832 a las 22:11 UTC para 620807_axis_revision1,
con unos 10 GiB libres. Encadenará las tres auditorías, selección condicionada
a aprobación, ensamblado, exportación y pruebas técnicas. No se han generado
aún el vuelo completo ni los entregables finales.


## Supervisión del 8 de octubre, 23:10 UTC

Las doce plantas de fondo tienen auditoría aprobada. Se ensamblaron y
exportaron las tres hileras y se preparó el recorrido. La prueba técnica
technical_30hz se detuvo a las 22:24:57 UTC sin capturas: el supervisor
detectó 3,6488 GiB libres y solicitó detener Gazebo (mínimo registrado
3,5104 GiB). Gazebo tenía 4.635 GiB RSS, por debajo de su límite separado
de 10 GiB: la causa fue la reserva del host, no ese límite del proceso.
No se encontraron procesos propios supervivientes. La espera posterior
no se contabiliza como ejecución.

La escena simplificada aún contiene 9.247.866 triángulos. Se añadió al
simplificador la selección mediante instance_roles: únicamente mallas
exclusivas de plantas background pueden reducirse; las de target y las
compartidas de tutorado se copian byte a byte. Se conservarán órganos,
materiales y envolventes con el control de escala ya existente; su aspecto
requiere inspección visual. La nueva cola incluye verificación SHA-256 de
todos los archivos objetivo, reducción real del número de triángulos, nueva
exportación, planificación y prueba técnica antes de avanzar.

Se preservó flight completo como flight_memory_failed1 (movimiento dentro
del estudio, sin borrar contenido), para reconstruir flight con el fondo
aligerado y mantener las rutas del contrato. Los dos primeros intentos de
simplificación fallaron al clasificar el soporte y su malla compartida; ambos
se preservan. Se corrigió la selección conservadora: cualquier malla que
no sea exclusivamente background permanece intacta. field_lod_memory3
está ejecutándose en Blender 69512, supervisor 58620, con más de 10 GiB
libres. El grafo de contexto validó (151 nodos, 260 aristas); la reducción
y la prueba de captura aún no se presentan como completadas.


## Supervisión del 9 de octubre, 00:10 UTC

La reducción exclusiva del fondo terminó correctamente: 9.247.866 →
4.598.386 triángulos, conservando los 53.206 órganos. La cola se había
detenido en la verificación SHA-256 porque el comprobador intentaba buscar
`support` dentro del inventario de plantas. Se corrigió esa selección para
verificar también los soportes; el intento fallido se conserva.

La comprobación versionada verify_background_memory_lod2 aprobó: 441 mallas
de plantas objetivo y soportes coinciden byte a byte con las anteriores.
Esto valida preservación de archivos, no todavía la apariencia del fondo
ni la captura. No se repitió la simplificación ya terminada.

Se reanudó el supervisor 22060 y se verificó por CIM la ejecución del
agrupador de contexto 68920 bajo wrapper exclusivo 52824. La cola continúa
con exportación binaria, preparación del recorrido y nueva prueba técnica
a 30 Hz. La inspección visual, el giro, el vuelo completo y los entregables
finales siguen pendientes. El tiempo detenido entre etapas no es ejecución.


## Supervisión del 9 de octubre, 01:16 UTC

La segunda prueba de Gazebo falló a las 00:13:15 UTC sin imágenes: mínimo
libre del host 1,85 GiB, con solicitud de parada por reserva. Se preservó
como flight/technical_memory_failed1. No había procesos propios activos
al iniciar esta supervisión. La reducción de geometría no bastó.

Se comprobó cgroup v2 y se ensayó un scope de usuario de systemd exclusivo
para simulación, sin alterar límites globales ni trabajos ajenos. La prueba
technical_30hz_cgroup1 mantuvo inicialmente 3 GiB residentes y usó swap,
pero también sufrió un pico de RAM del host (mínimo 1,75 GiB). Se conserva
en flight/technical_cgroup_failed1. No se atribuye definitivamente el pico
al controlador gráfico; es una hipótesis motivada por la diferencia entre
memoria residente del proceso y caída de memoria libre del host.

Se habilitó selección explícita del renderizador: el comportamiento histórico
sigue siendo d3d12; UCHUVA_RENDER_DRIVER=llvmpipe activa software con cuatro
hilos y registra el backend en result.json. La prueba technical_30hz_software1
mantiene resolución 1280×720, sensores a 30 Hz, máscaras e identidades.
El scope inició con MemoryHigh=3 GiB / MemoryMax=4 GiB / swap máximo 3 GiB.
Con memoria libre suficiente, se ajustó solo ese scope en ejecución a
4/5/3 GiB para reducir paginación; el cambio exacto está registrado en
software_memory_runtime_adjustment.json y la prueba del giro lo heredará.
La protección de al menos 4 GiB libres en el host sigue activa.

La prueba por CPU continúa inicializando: contador efectivo creciente,
proceso de Gazebo y scope reales comprobados, carga posterior de mallas de
marcadores en el log y mínimo libre observado 6,37 GiB durante esta prueba.
Todavía no se han validado fotogramas ni 30 Hz efectivos. Las 28 pruebas
enfocadas pasaron y el grafo validó (151 nodos, 260 aristas). No se declara
resuelto el consumo de memoria antes de completar la captura técnica.


## Supervisión del 9 de octubre, 02:12 UTC

La prueba CPU technical_30hz_software1 también se detuvo por RAM a las
01:24:16 UTC: 249,56 s efectivos y mínimo libre 3,215 GiB, sin fotogramas.
Se conserva en flight/technical_software_failed1. La hipótesis de que bastaba
con cambiar de controlador no quedó confirmada. En WSL se identificó un
entrenamiento humanoidrl de otro proyecto, que no se detuvo ni modificó.

Se añadió admisión de memoria por etapa al wrapper y supervisor: las próximas
pruebas de Gazebo esperarán 14 GiB libres, conservando la admisión general
de 6,5 GiB para las otras etapas. Es un margen de ingeniería tras los picos
observados, no garantía de éxito. Sigue activa la protección de 4 GiB durante
el trabajo. La próxima prueba usa software, cgroup 4 GiB suave / 5 GiB máximo
y hasta 3 GiB swap. No se modificó la resolución ni la frecuencia de sensores.

Se verificaron procesos reales: supervisor 4592 y wrapper 4020 esperando.
El trabajo technical_30hz_software2 registra waiting_for_memory, pid null,
unos 11,16 GiB libres y cero tiempo de ejecución. No hay Gazebo ni Blender
propios trabajando en esta espera. Arrancará automáticamente al disponer
de 14 GiB; la espera queda excluida del consumo. Compilación y grafo de
contexto validados. Los entregables permanecen pendientes.


## Reanudación solicitada por el usuario, 8 de octubre, 21:27 Colombia

El usuario liberó RAM y pidió arrancar. Se midieron 13,4 GiB libres: se
ajustó la admisión conservadora de 14 a 13 GiB, manteniendo la reserva
durante ejecución de 4 GiB y cgroup 4/5/3 GiB. El intento software2 se
canceló antes de lanzar, con cero ejecución; su espera se conserva.
Se inició technical_30hz_software3 y se verificó Gazebo real PID 467 en
WSL y scope activo. La captura aún debe superar las validaciones.


## Supervisión del 8 de octubre, 22:21 Colombia

El proceso CPU seguía vivo, pero tras 1720 s efectivos no había imágenes.
La presión de memoria del cgroup indicaba ~45 % de tiempo de espera y
swap de 3 GiB saturado, sin OOM. Con unos 8 GiB libres en el host, se
aumentó exclusivamente el scope del experimento a MemoryHigh=6 GiB y
MemoryMax=7 GiB, conservando swap máximo 3 GiB y reserva del host 4 GiB.
El ajuste queda en software3_memory_runtime_adjustment.json.

La presión instantánea bajó a 2,06 % y empezaron a guardarse RGB y máscaras.
Se inspeccionó RGB 0.png: planta objetivo y ArUco completos, plantas de fondo
y tutorado visibles. Es revisión parcial, registrada aparte; no se habilitó
la congelación visual del estudio ni se declaró validación a 30 Hz. La
captura técnica sigue avanzando y el giro heredará estos límites de memoria.


## Supervisión del 9 de octubre, 09:01 Colombia

La captura técnica continúa con Gazebo PID 467 y escrituras RGB recientes
verificadas. A las 14:02 UTC había 125 RGB (4,09 s simulados) y 124 máscaras
en una lectura mientras el escritor seguía activo; no son métricas finales
de sincronización. La presión instantánea de memoria bajó a 0 %, el scope
usaba 5,31 GB y el host conservaba unos 6,23 GiB libres. Se mantiene el
trabajo existente, sin reinicios ni duplicados. El contador efectivo continúa
en torno a 1900 s y no se reemplaza por el tiempo de calendario transcurrido.
La validación y el giro permanecen en la cola automática.


## Captura técnica aprobada, 9 de octubre, 09:07 Colombia

Gazebo terminó la prueba de 10,045 s simulados: 305 pares RGB/máscara
sin exclusiones ni errores de escritura. La validación se detuvo al intentar
serializar un bool de NumPy. Se convirtió explícitamente cada comprobación
a bool nativo sin modificar sus condiciones. La reevaluación aprobó todos
los controles, con intervalo mediano 0,03333332 s y ningún intervalo perdido.
Se preservó el fallo del verificador y se reanudó la cola con nombre versionado.
El margen mínimo ejecutado fue 0,4326 m. Esta prueba técnica no es el vuelo
completo; máscaras anatómicas, giro, análisis y entregables siguen pendientes.


## Supervisión del 9 de octubre, 09:59 Colombia

La prueba del giro arrancó automáticamente tras 1432,08 s de espera por
RAM, excluidos de ejecución. Procesos reales comprobados: supervisor
39232, wrapper 61712 y WSL 64364. Avanza con 863 RGB observados, 28,45 s
simulados y 10 de 39 puntos alcanzados. El host tenía unos 4,63 GiB libres
y el mínimo registrado era 4,15 GiB; la protección de 4 GiB sigue activa.
Se inspeccionó RGB 28446655288.png: planta terminal centrada, silueta
completa y marcador visibles durante el arco inicial; fondo presente. Es
una observación parcial, no aprobación de todo el giro. No se interrumpió
la captura; al terminar se ejecutarán los validadores en cola.


## Giro completo y arranque del vuelo, 9 de octubre, 12:09 Colombia

El giro terminó los 39 puntos en 109,55 s simulados, con 3320 pares exactos
a 30 Hz y sin intervalos faltantes. Pasaron captura y máscaras. El margen
mínimo fue 0,4136 m y el error máximo hacia la planta durante el arco
3,654°. El ArUco objetivo no se decodificó en 853 de 2838 cuadros del arco;
esto se conserva separado de la orientación y deberá analizarse en el informe.

El primer validador rechazó station_framing: 27 muestras de telemetría entre
0,175 y 1,085 s incumplían el margen durante estabilización. Todas las demás
muestras, incluido el arco entero, pasaron. La misión ya declaraba siete
segundos de initial_hold_seconds. Se revisó explícitamente el alcance de la
comprobación de estaciones en versión 1.1 para comenzar después de ese hold,
conservando todos los incumplimientos de arranque en el informe y el resultado
v1 original. Esto es una revisión de criterio durante desarrollo retrospectivo,
no una prueba independiente ni cumplimiento del margen durante el arranque.
Se comprobó que la nueva separación conserva y rechaza fallos posteriores
a la estabilización. No se excluyó ninguna muestra del arco.

Se inspeccionaron seis RGB representativos de la captura corta y del giro
por ambas caras. Se registraron iluminación estilizada y aliasing de hilos
como limitaciones. visual_review.json y experiment_lock.json congelan la
configuración antes del recorrido reportado. El supervisor 43588 inició el
vuelo completo (WSL 65920, wrapper 34632), tras comprobar memoria suficiente.
Se añadieron a la cola las validaciones y todo el análisis posterior, hasta
la generación del informe. La inspección visual de todas las páginas del PDF
y el cierre verificado permanecen como controles posteriores pendientes.

### Parada de RAM del vuelo completo y recuperación
El primer vuelo completo se detuvo el 9 de octubre a las 17:30 UTC por la protección de RAM del host (mínimo 3,872 GiB). Conservó 696 pares RGB/máscara, 22,96 s simulados y 2/51 puntos; no constituye un recorrido completo. Se preservó en flight/full_memory_failed1. La reejecución versionada capture_full_row_30hz_memory_retry1 mantiene la configuración científica congelada y exige 14 GiB libres al inicio, con protección de 4 GiB durante el trabajo. Reinicia el recorrido; no empalma capturas ni contabiliza espera de memoria como ejecución. No se detuvieron procesos ajenos.

El usuario autorizó reducir la reserva de RAM a 2 GiB. Se parametrizó la protección (4 GiB por defecto para otras campañas), se fijó 2 GiB para este estudio y 11 GiB para admitir el vuelo (13 GiB originales menos 2 GiB). La espera del intento memory_retry1 fue cancelada antes de iniciar, con consumo efectivo cero; se conserva su registro. Configuración científica y límites internos de Gazebo intactos.

### Vuelo completo finalizado
El intento con reserva de 2 GiB terminó el 9 de octubre a las 21:18 UTC (16:18 Colombia): 51/51 puntos, 263,06 s simulados y 7972 pares sincronizados. Pasaron integridad a 30 Hz sin intervalos faltantes, máscaras nativas y orientación; el margen mínimo ejecutado fue 0,3596 m. Se mantienen las incidencias de encuadre durante estabilización inicial. El supervisor encadenó exportación RGB pública y auditoría anatómica, activa con avance de cache a 4800 fotogramas al consultar. La inferencia, conciliación, métricas finales, videos anotados e informe siguen pendientes.

### Auditoría anatómica e inferencia por fotograma
La auditoría terminó correctamente a las 22:30:51 UTC del 9 de octubre y el supervisor inició inmediatamente cache_full_native_predictions. En la supervisión de las 23:11 UTC, el registro alcanzaba 960 de 7972 fotogramas y el proceso real seguía activo. No son todavía métricas de desempeño; la conciliación y evaluación quedan posteriores. Se mantiene la reserva autorizada de 2 GiB.

### Recuperación de inferencia
Se detectó ausencia de los procesos de inferencia y supervisor, con último avance registrado de 6060/7972 cuadros. Causa de terminación no determinada; no se atribuye a RAM sin evidencia. Se preservó el registro original y su consumo efectivo, se marcaron los procesos desaparecidos y se preparó cache_full_native_predictions_resume1, reutilizando predicciones completas mediante verificación SHA256 existente. No se cambió la configuración científica.

### Inferencia terminada y comparación de seguimiento en marcha
La inferencia recuperada terminó correctamente el 10 de octubre a las 21:36:56 UTC (16:36 Colombia). El supervisor encadenó y completó seguimiento y evaluación histórica a 1 Hz, e inició seguimiento histórico por fotograma a las 21:48 UTC. En la supervisión siguiente el registro alcanzaba 1000 fotogramas con proceso real activo. La conciliación offline y la comparación final todavía están pendientes; no se presenta el baseline como resultado final.

### Seguimiento histórico completo y evaluación
El seguimiento histórico por fotograma finalizó a las 23:04 UTC del 10 de octubre con 7972 fotogramas y mapa guardado. El supervisor inició su evaluación inmediatamente; a las 23:53 UTC el registro de máscaras alcanzaba 2000 fotogramas, con proceso real activo. La variante offline y sus métricas siguen pendientes.

### Inicio de variante offline
La evaluación histórica por fotograma terminó correctamente a las 02:05 UTC del 11 de octubre. El supervisor inició track_offline_every_frame. En la supervisión de las 02:57 UTC el archivo de observaciones seguía creciendo, con seguimiento por máscaras más lento que el histórico. No se ha completado aún el ajuste geométrico ni la fusión global; no se reporta porcentaje global de conciliación.

### Aceleración CUDA autorizada
Se añadió comparación exacta de máscaras empaquetadas en PyTorch CUDA a petición del usuario, sin dependencias nuevas. OpenCV carece de CUDA: extracción de puntos y flujo óptico siguen CPU. IoU exactas en 35 pares aleatorios y 576 pares reales, identidades iguales en cuatro cuadros y 28 pruebas existentes aprobadas. Benchmark de esta operación: CPU 0,126 s; CUDA 0,037 s; no representa aceleración total. Intento CPU y congelación original preservados. Se reinicia solo seguimiento por ausencia de checkpoint; inferencia completa reutilizada. La verificación aislada reproduce el backend elegido. Timeout operativo de seguimiento/replay ampliado a siete días para evitar el límite de 24 horas en una campaña sin tope global.

### Flujo óptico CUDA con recuperación del prefijo
Se añadió LK piramidal disperso por lotes en PyTorch CUDA, dos reducciones de pirámide y 20 iteraciones, con comprobación ida/vuelta. No es equivalente bit a bit a OpenCV: en 300 puntos de imágenes del vuelo, mediana de diferencia 0,0103 px y P95 0,0399 px; todos válidos en ambas implementaciones. Pruebas de traslación conocida y movimiento cero aprobadas. Extracción de esquinas limitada al área de cada máscara con margen 4 px, sin diferencias en 129 comparaciones representativas. Cuatro cuadros de prueba: 0,17–0,35 s tras el primero; no es benchmark de todo el recorrido. Se conservaron observaciones completas del intento previo, sus IDs y poses en recovery/flow_cuda_prefix.jsonl. La continuación reconstruye únicamente movimiento reciente con CPU sin reasignar identidades del prefijo. Diagnósticos internos de rechazos del prefijo, no guardados por la versión anterior, quedan explícitamente no disponibles. La variante es híbrida por cambio de backend a mitad de secuencia y se identifica así; no se reutiliza como ensayo independiente. Fuentes y congelaciones originales preservadas.

Verificación de recuperación completada: los 173 cuadros del prefijo conservan exactamente detecciones, IDs y poses al comparar JSON. Se observó el cuadro 174 generado después de la recuperación con flujo CUDA. Evidencia: flow_cuda_prefix_verification.json.

### Parada de memoria y velocidad sostenida
El 11 de octubre a las 04:22 UTC, la protección de 2 GiB detuvo flujo CUDA; mínimo del host 1,636 GiB. Se conservaron 384 observaciones. Entre verificación del prefijo (174 cuadros a 04:11:38) y última escritura (384 a 04:22:43), 210 cuadros/665 s: 3,17 s/cuadro, muy por encima de la prueba corta. No se atribuye toda la presión del host al estimador sin evidencia. Se acotaron los lotes CUDA a 256 puntos y la recuperación mantiene el cambio de backend en el cuadro 173. Se exige 10 GiB al arrancar este intento, conservando la reserva de ejecución de 2 GiB. Prefijos, intento fallido y congelación previa preservados.


### Recuperacion del 11 de octubre, memoria de mascaras

El seguimiento CUDA se detuvo a las 10:51 UTC por memoria libre de 1,119 GiB; quedaron 3197 observaciones completas, preservadas en offline_every_frame_flow_cuda_memory_failed2. Se identificaron 3475 trayectorias distintas en las ultimas 62 observaciones: las mascaras densas persistentes son un contribuyente importante al consumo. Se cambia exclusivamente su representacion a un bit por pixel, sin perdida, reduciendo ocho veces ese almacenamiento (no necesariamente la RAM total). Pasaron 28 pruebas, paridad de IoU CPU/CUDA, recuperacion de flujo y roundtrip de dimensiones no multiplo de ocho. El intento packed_resume3 conserva el prefijo, la reserva de 2 GiB, el modelo y los umbrales. Revision retrospectiva registrada y congelaciones anteriores preservadas.


### Segunda comprobacion de memoria, 11 de octubre 12:05 UTC
El intento packed_resume3 alcanzo 3382 cuadros (+185 nuevos); los 3197 anteriores permanecen identicos. La proteccion detuvo el proceso con minimo de RAM libre 1,273 GiB. La compresion persistente no basto. Antes de parar, la GPU registraba 5877 MiB usados, mientras las transferencias IoU cargaban todas las trayectorias activas. Se acotan las transferencias a 32 pares y el asignador CUDA al 50 % de VRAM, sin alterar mascaras ni asociaciones; esto limita recursos, no garantiza una aceleracion. Pasaron 28 pruebas y las comparaciones exactas CPU/CUDA. Se agrega telemetria de memoria CUDA para comprobar el efecto. Fallo conservado en offline_every_frame_packed_memory_failed3; nuevo intento bounded_resume4 con 3382 cuadros de prefijo y reserva de 2 GiB.


### Optimizacion exacta autorizada, 11 de octubre
El usuario solicito acelerar sin alterar resultados. Se conservaron 4569 cuadros y el intento bounded4 tras detener solo su trabajador verificado. Se eliminan normas y compresiones repetidas: filtro rectangular necesario antes de la misma norma escalar, reutilizacion de candidatos y empaquetado de cada mascara nueva una sola vez. Dos pruebas con 3500 trayectorias conservaron matrices de puntuacion, identidades y rechazos exactamente; esa parte paso de 0,46/0,92 s a 0,04/0,05 s. Ocho cuadros reales con flujo CUDA conservaron IDs, cajas, mascaras y rechazos, de 2,477 a 1,947 s (21,4 % menos tiempo en prueba corta, no velocidad sostenida). Se omite decodificar mascaras antiguas no usadas durante recuperacion. Mantiene reserva 2 GiB, lotes y limite de VRAM previos; no aumenta prioridad ni cambia pesos, precision numerica o umbrales. Congelacion anterior y resultados preservados.


### Seguimiento completo, 11 de octubre
Se verificaron 7972 observaciones completas y sus timestamps en el mismo orden que las capturas publicas. Ultima escritura: 19:42:43 UTC (14:42:43 Colombia). El proceso continua en el bloque posterior de geometria/conciliacion; todavia no existe map.json. Actividad de CPU comprobada, pero este bloque no expone contador de progreso y no se le atribuye porcentaje ni plazo. La evaluacion, videos e informe siguen pendientes.


### Conciliacion terminada y evaluacion en marcha
El 11 de octubre a las 20:33:21 UTC (15:33 Colombia) termino correctamente track_offline_cuda_exact_fast5, con mapa, observaciones conciliadas y procedencia guardados. El supervisor encadeno evaluate_offline_every_frame inmediatamente. En la comprobacion de las 21:09 UTC la evaluacion de mascaras superaba 2100 fotogramas con procesos reales activos. No se presentan aun metricas finales de calidad; siguen pendientes evaluacion completa, aislamiento, diagnosticos, videos y reporte.


### Evaluacion completada y comprobacion de aislamiento
La evaluacion offline termino el 11 de octubre a las 22:42:23 UTC (17:42 Colombia). Resultado registrado: 62/388 capachos objetivo visibles localizados correctamente (15,98 %), precision 3D 32,98 %, precision de asociacion 48,94 %, 15 duplicados y 35 asignaciones al marcador incorrecto. No alcanza el objetivo del piloto. No se modifican parametros con estas metricas. El supervisor inicio la repeticion con acceso a verdad bloqueado; reutiliza el prefijo publico conservado, por lo que no constituye una repeticion independiente desde cero. Diagnosticos, videos, informe y verificacion final pendientes.


### Verificacion de aislamiento aprobada
El 12 de octubre a las 07:11:22 UTC (02:11 Colombia) termino la repeticion: mapa identico y ningun intento de acceso a rutas privadas bajo el audit hook de Python. No es una barrera de seguridad del sistema operativo ni una auditoria del entrenamiento; reutiliza el prefijo conservado. El supervisor inicio inmediatamente los diagnosticos con verdad privilegiada, exclusivos del evaluador y separados del desempeno desplegable. Videos e informe pendientes.


### Videos en generacion
El 12 de octubre a las 07:42:11 UTC (02:42 Colombia) terminaron los diagnosticos privilegiados y el supervisor inicio ambos videos anotados. A las 08:33 UTC el log supera 6400/7972 cuadros. El cierre de codificadores y la decodificacion completa siguen pendientes; no se entregan archivos en escritura como videos terminados.


### Cierre verificado, 12 de octubre
Ambos videos se decodificaron completos: 7972 cuadros a 30 fps cada uno, sin interpolacion ni duplicacion. El informe fallo inicialmente por una importacion ausente de cv2; se corrigio y se reutilizo reportlab ya disponible en el runtime, sin instalar dependencias. Se preserva el intento fallido y se registra la recuperacion. Las cinco paginas del PDF final se renderizaron e inspeccionaron visualmente. Mapa, observaciones, catalogo de perdidas y reporte se conservaron con hashes en study_complete.json. No quedan entregables pendientes. El objetivo cientifico no se alcanzo: 62/388 capachos localizados, precision de asociacion 48,94 %. La conciliacion redujo duplicados de 78 a 15 pero bajo las localizaciones correctas de 73 a 62 frente al seguimiento historico por fotograma. No se afirma transferencia al cultivo real.

### Vista exterior sincronizada, 14 de octubre
Se añade una composición del diagnóstico existente con una miniatura exterior. La escena exterior se reconstruye desde `field_batched/field.sdf`, con su geometría OBJ y colores; no es una segunda cámara registrada durante el vuelo. El dron se representa mediante un símbolo ampliado para legibilidad, situado mediante interpolación de la telemetría ejecutada en el timestamp de cada captura original, con flecha de orientación. La trayectoria planificada no sustituye la ejecutada. Los cuadros anteriores a la primera muestra de telemetría usan la primera pose y su número queda registrado. La composición conserva el orden y número de cuadros del diagnóstico, sin recalcular inferencia, asociaciones ni métricas. La telemetría se usa exclusivamente para esta visualización retrospectiva.
La miniatura utiliza iluminación de estudio y el color medio de los mapas de albedo para que el contexto sea legible a tamaño reducido; no pretende reproducir fotométricamente la cámara de Gazebo. La vista principal conserva todas las anotaciones del diagnóstico, salvo el área cubierta por la miniatura superior derecha. La tasa final es 30 fps y mantiene la misma correspondencia por índice con el diagnóstico original, incluida la diferencia ya documentada entre duración codificada y tiempo de simulación.

Composición final verificada: 7972 cuadros a 30 fps, decodificación completa sin errores. Inspección visual de muestras de salida, giro y entrada a la segunda cara. Archivo: outputs/continuous_row_20261008/presentation/exterior_inset/diagnostico_con_vista_exterior.mp4.
