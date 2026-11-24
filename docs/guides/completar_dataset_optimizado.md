# Completar el banco optimizado sin regenerar plantas

La continuación autorizada del 30/10 conserva las 144 vistas completas del
banco cerrado y produce 856 nuevas para alcanzar 1.000. Las 192 vistas
históricas excluidas, los benchmarks y los parciales no cuentan. Conserva
los veinte árboles admitidos y sus hashes; no cambia órganos ni dimensiones.

```powershell
.venv-training/Scripts/python.exe scripts/complete_optimized_dataset.py outputs/spatial_plant_pool_20261028 outputs/spatial_dataset_completion_20261030
```

El controlador crea una salida independiente, congela fuentes/entradas y
verifica las auditorías del pool antes de iniciar un único trabajador GPU.
No reabre los presupuestos históricos. Esta autorización tiene una meta de
1.000 imágenes, sin un nuevo límite temporal explícito; el reloj nativo
registra tiempo despierto y excluye suspensión. Las 18–22 horas son una
estimación de planificación, no un resultado ni un plazo garantizado.

Cada trabajador construye o reanuda una escena, guarda el checkpoint y
produce hasta 24 pares RGB/máscara/etiquetas. Una escena sólo se contabiliza
después de verificar su cierre geométrico. Los commits por vista permiten
recuperar un prefijo tras interrupción sin inventar una escena terminada.
La identidad nativa PID/creation_tick protege los locks y la adopción de
trabajadores huérfanos; los ticks se conservan como cadenas. El watchdog de
dos horas activas protege cada trabajador iniciado por el controlador y no
constituye un presupuesto global autorizado. Un huérfano adoptado requiere
también supervisión de progreso.

La captura usa dos escenas que comparten geometría, Cycles/OptiX persistente
y máscara Workbench exacta. Conserva 960×720, doce muestras, denoising y
todos los capachos visibles válidos, incluso diminutos. Luz de campo,
difusa y sombra se equilibran entre profundidades; se alternan hilos y
tutorado horizontal. Doce árboles por escena, cuatro hileras y suelo
natural conservan la receta admitida. Se exige cero cruces duros auditados,
suelo a 1 mm y orientación/unión válidas; proximidades y hoja–hoja siguen
como advertencias/ocupación blanda. Contexto y flores no tienen una
certificación física exhaustiva.

No editar fuentes congeladas durante ejecución. Una revisión técnica debe
detener únicamente propietarios verificados, archivar fuentes/lock/logs,
registrar la nueva cadena de hashes y conservar presupuesto, checkpoints
y pares comprometidos. La revisión `validation_cache_20261030` evita
releer informes de decenas de MB por cada vista: valida una vez por escena
y llamada, manteniendo el cotejo geométrico individual. Las vistas sin
objetivos visibles quedan preservadas como negativas excluidas.

```powershell
.venv-training/Scripts/python.exe scripts/report_dataset_completion.py outputs/spatial_dataset_completion_20261030
.venv-training/Scripts/python.exe scripts/report_dataset_completion.py outputs/spatial_dataset_completion_20261030 --final
```

El informe verifica máscara, identidad, clase, píxeles, cajas y YOLO; publica
índice combinado y galería. El cierre exige exactamente 1.000 vistas y
queda en `awaiting_user_sample_review`. Este flujo no inicia entrenamiento:
hay que mostrar muestras al usuario y revisar la política de pequeños del
consumidor antes del siguiente piloto. Vistas del mismo árbol no son
muestras biológicas independientes. Pruebas puras:
`tests/test_dataset_completion.py`.

## Variedad de cielos autorizada el 30/10

`capture_skies.py` distribuye cielo azul despejado, despejado con bruma y
cubierto entre las tres profundidades. Cada escena de 24 vistas producida
íntegramente con esta revisión contiene ocho de cada tipo; la última escena
parcial y la primera con prefijo previo pueden diferir. Las vistas históricas no
se reescriben. `blender_capture_skies.py` compone la atmósfera procedural
sin nubes con el paisaje lejano del panorama existente. Conserva el campo
bajo el horizonte y mezcla la transición por dirección del rayo; no agrega
imágenes externas ni geometría. Cielo visible e iluminación comparten el
mismo modelo atmosférico y orientación solar; el cubierto conserva la
aproximación difusa del perfil previo. No es un simulador meteorológico.

La primera vista baja mostró que una transición angular demasiado alta
retenía una franja del cielo antiguo. `panorama_silhouette/2` limita la
transición a la cercanía del horizonte y protege las siluetas oscuras con
luminancia del HDR congelado (mezcla entre 0,20 y 0,38 lineales). Son
umbrales de ingeniería específicos de ese panorama, no una segmentación
semántica general. Los metadatos distinguen explícitamente el cielo
analítico compartido en los despejados de la aproximación de luz cubierta.

La densidad de aerosol, ángulo del sol y elevaciones diurnas son
`engineering_heuristic`, no mediciones. Se registran tipo de cielo,
semilla/versión, parámetros efectivos y procedencia en cada vista. La semilla
de captura no regenera plantas, cámaras ni etiquetas. Las clases y materiales
permanecen iguales. La revisión queda en `revisions/sky_diversity_20261030`;
fuentes/lock previos y presupuesto quedan preservados.

`tests/test_capture_skies.py` verifica reproducibilidad y cobertura por
profundidad. `scripts/check_capture_sky_background.py`, ejecutado en Blender,
renderiza tres casos y verifica hemisferio superior, conservación del paisaje
inferior y geometría. `scripts/report_capture_skies.py ROOT` guarda
`sky_coverage.json`, separando escenas cerradas y prefijos pendientes.

## Horizonte sin contaminación y distancias continuas

La revisión `horizon_matte_continuous_depth_20261030` sólo se aplica a
capturas futuras. Conserva vistas previas, prefijos, árboles y presupuesto.
`horizon_matte.py` separa el cielo conectado a la parte superior del HDR
por columnas, dentro de una banda del horizonte; extiende color de paisaje
limpio hacia los texels retirados y limpia dos filas del borde. Un filtro
horizontal de tres columnas y una transición vertical de dos píxeles
evitan un contorno escalonado. La máscara y el paisaje comparten exactamente
la proyección y rotación del panorama original, sin la antigua mezcla
angular que retenía una franja brillante del cielo anterior.

`scripts/prepare_capture_horizon_assets.py` genera paisaje EXR y máscara PNG
con hashes; son derivados locales del HDR CC0 ya disponible. No modifica
árboles, materiales de órganos ni anotaciones. Los parámetros de separación
son heurísticas de ingeniería para este panorama, no segmentación general.
El controlador prepara y congela estos assets al crear una campaña nueva;
una continuación referencia el manifiesto explícito en su configuración.

`continuous_capture_distance.py` sortea un 70 % de tomas uniformemente
entre las referencias cerca–medio y un 30 % entre medio–lejos. Las
referencias conservan el cálculo previo de encuadre para cada capacho
objetivo (48/24/10 píxeles de referencia, límites 2–100 BU); ninguna de ellas
regula la carga o tamaño de órganos. La semilla de distancia es independiente
de arquitectura, objetivos e iluminación. Se conserva la orientación/azimut
y pequeña variación de apuntado de la receta previa.

Cada vista registra intervalo sorteado, referencias, distancia física al
centro del objetivo, distancia al punto de apuntado, semilla y versión.
El 70/30 es probabilístico y se comprueba sobre las nuevas vistas aceptadas;
no se fuerza reetiquetando las imágenes históricas. Las etiquetas gruesas
`near/middle/far` son descripciones posteriores para compatibilidad; no
equivalen a los dos intervalos del sorteo. El resumen incluye estos
intervalos y su proporción real de forma separada.

Pruebas: `tests/test_capture_distance_horizon.py`, fixture de los tres cielos
y `scripts/preview_capture_revision.py` sobre cámara/luz originales. El
diagnóstico emparejado queda fuera del contador de 1.000. Antes de reanudar,
se comprueban las vistas conservadas y sus hashes. Las comparaciones
actualizadas deben distinguir el cambio de fondo del cambio de distancia.

## Pausa para revisión de diversidad

`pause_requested.json` con `active=true` impide arrancar el controlador y
lo detiene entre bloques si ya se ejecutaba. La pausa del 30/10 se solicitó
cuando el último bloque había cerrado503 vistas: se preservaron y se
evaluaron las primeras500 según `review_500_lock.json`, sin selección estética.
No modificar el presupuesto ni recortar el índice a500 para ocultar las
tres adicionales. Los parciales siguen separados de vistas cerradas.

La revisión se ejecuta sin Blender ni entrenamiento con
`assess_dataset_diversity.py`, `review_diversity_candidates.py` y
`summarize_diversity_structure.py`. Sólo se usa entrenamiento real como
referencia. Hashes perceptuales, escala, densidad y cobertura son
descriptores, no pruebas de independencia ni de eficacia del detector.
Una toma casi negra se conserva y se señala fuera de las propuestas de
piloto; no se borran etiquetas ni imágenes.

Antes de reanudar hace falta una nueva decisión del usuario; conservar y
archivar la pausa cuando se libere explícitamente. No basta ejecutar otra
vez el comando para continuar. El seguimiento automático queda PAUSED.
El informe de la decisión es
`docs/reports/diversidad_banco_500_2026-10-30.md`.

## Piloto autorizado con 115 corregidas

La autorización posterior permite seis entrenamientos (dos brazos, tres
semillas) sin liberar `pause_requested.json`. El controlador independiente
`scripts/reviewed_augmentation_pilot.py prepare` congela la selección115,
datos/pesos/fuentes y receta; `run` ejecuta y recupera corridas seriales.
Nunca invoca Blender ni el controlador de generación. Tras la evaluación
queda pendiente revisar curvas/predicciones y decidir cualquier ampliación.
El diseño y la interpretación del filtro nativo de tamaños están en
`docs/reports/piloto_115_corregidas_2026-10-31.md`.

Cierre del piloto115: seis corridas verificadas, revisión técnica completa.
Ganancia macro exploratoria+2,07pp con caída Sobremadura−0,76pp;
no ampliar automáticamente. Generación y su seguimiento siguen pausados.
La decisión posterior requiere revisar el informe del31/10.
