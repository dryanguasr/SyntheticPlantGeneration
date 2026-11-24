# Continuación hasta 1.000 imágenes: registro de ejecución

Estado: **en ejecución; no se han completado 1.000 ni iniciado entrenamiento**.

El usuario autorizó completar el banco con la captura optimizada y seguimiento
horario, conservando las plantas y mostrando muestras antes del piloto.
Salida independiente: `outputs/spatial_dataset_completion_20261030`.
Se reutilizan 144 vistas históricas verificadas y se solicitan 856 nuevas;
192 vistas descartadas permanecen excluidas. Los veinte árboles admitidos
conservan órganos, dimensiones y hashes. Sus pérdidas históricas de frutos,
hojas y proxy L×W permanecen estrictamente por debajo del 5 % por árbol.

La estimación emparejada previa fue 18,58 horas activas adicionales, con
margen de planificación de 20–22 horas. Se mantienen calidad de render,
anotaciones completas, condiciones visuales variables y admisión física.
La campaña actual tiene parada por cantidad y no reinicia presupuestos
históricos. El resultado del benchmark no demuestra utilidad del detector.

La primera escena nueva es la 015. Tras once pares comprometidos se preservó
el prefijo y su checkpoint para corregir la lectura repetida de auditorías
grandes en el verificador. Revisión explícita
`revisions/validation_cache_20261030`: propietarios detenidos verificando
PID y creación nativa, fuentes/lock/logs preservados, presupuesto idéntico.
También se conserva como negativa excluida una eventual vista sin objetivo;
no se eliminan objetos ni etiquetas visibles. Seis pruebas de contratos
pasaron, incluida máscara/clase/YOLO sobre una vista real del banco histórico.

Sólo las escenas cerradas y pares con hashes cuentan. `state.json`,
`combined_index.json`, `review_summary.json` y `review.html` son las fuentes
operativas de progreso y muestras. Los prefijos en curso se informan aparte.
Al cierre se documentarán cantidades efectivas por profundidad, tutorado,
luz y clase; exposición de plantas e instancias; tiempo nativo; controles
de integridad y brechas visuales. Las primeras muestras son provisionales
hasta que la escena complete su guardia geométrica de cierre.

El siguiente piloto requiere revisión humana de muestras. No se presupone
fotorealismo, independencia entre vistas ni mejora de entrenamiento.

En las tres muestras iniciales cercanas/intermedias/lejanas de la escena 015,
la correspondencia máscara–instancia–clase–caja–YOLO pasó con 318, 1.194 y
2.091 capachos visibles respectivamente. Son exposiciones de anotaciones,
no frutos independientes. La inspección muestra sombreado oscuro en la vista
cercana, repetición de hojas/maleza y una transición visible al fondo
panorámico; el terreno lejano conserva bandas relativamente uniformes.
Estas brechas se documentan sin modificar las plantas ni declarar
fotorealismo. La iluminación es una condición de captura registrada y no
una medición agronómica. El cierre físico/geométrico de escena sigue pendiente.

## Revisión de cielos del 30/10

El usuario pidió incluir cielos sin nubes y mayor variedad de iluminación.
Se preservó el prefijo existente y se registró
`revisions/sky_diversity_20261030`, con sus propietarios comprobados,
fuentes y lock anteriores, autorización y presupuesto idéntico. La nueva
captura alterna azul despejado, despejado con bruma y cubierto, con luz
directa/difusa/suave acorde y elevaciones solares diurnas variables.
Las atmósferas sin nubes son procedurales; no se descargaron nuevos assets.
El paisaje bajo el horizonte procede del panorama ya congelado y la mezcla
superior queda descrita en los metadatos. No son mediciones meteorológicas.

Dos pruebas puras pasaron para reproducibilidad, cobertura de tres cielos
por profundidad y coherencia de receta. Una regresión renderizada en
Blender comparó los tres cielos, comprobando azul en el hemisferio superior,
igualdad del paisaje inferior y geometría intacta. La primera versión del
fixture detectó signo invertido de la normal de mundo en Cycles; se corrigió
antes de congelar fuentes y reanudar, conservando también esa evidencia.
Las seis pruebas de continuidad también pasaron. El seguimiento horario
debe informar `sky_coverage.json` y verificar muestras nuevas de producción,
separando pruebas pequeñas, prefijos y escenas realmente cerradas.

La primera vista de producción etiquetada como despejada (015/014) pasó la
auditoría de 1.956 cajas/máscaras/etiquetas, pero su cámara baja dejó visible
una franja de nubes del panorama anterior. Se preservó y registró esa
limitación. La subrevisión `horizon_01` usa la luminancia inspeccionada del
HDR para proteger las siluetas oscuras y reemplazar las nubes cercanas al
horizonte; volvió a pasar el fixture. `metadata_01` distingue el modelo
analítico compartido de los despejados y la aproximación difusa del cubierto,
sin cambios adicionales del render. Ambas conservan presupuestos, plantas,
checkpoints y pares completos; no se eliminó el resultado intermedio.

Con la revisión final, la vista cercana 015/018 pasó la auditoría de 381
instancias y YOLO (error máximo de redondeo 4,45e-11). Su encuadre no muestra
cielo: demuestra continuidad de captura/anotación, no apariencia visible
de la skybox. El fixture sí comprueba el hemisferio y horizonte; la revisión
de producción debe incluir vistas amplias con cielo realmente visible.
La escena continúa pendiente de cierre geométrico. `sky_review.html`
selecciona sólo la versión corregida; `sky_coverage.json` cuenta parámetros
de captura y separa implementaciones y prefijos de escenas cerradas.

## Primer bloque cerrado: 30/10, 06:29 UTC

La escena 015 cerró 24 vistas nuevas con geometría intacta: el banco
combinado alcanzó 168/1.000 (144 heredadas y 24 nuevas). Los 24 pares
pasaron auditoría de píxeles/identidades/clases/cajas/YOLO. Las 130 fuentes
congeladas y las identidades nativas de ambos propietarios se verificaron;
la escena 016 continuaba en construcción/auditoría sin errores registrados.

La inspección visual de 015/020 (bruma) y 015/023 (despejado), ambas con
`panorama_silhouette/2`, muestra cielo sin nubes sobre el paisaje. En esas
muestras no se observa una costura dominante de horizonte; el follaje,
suelo y vegetación conservan repetición procedural. Se revisaron nuevamente
sus máscaras y etiquetas. Esta revisión de Codex no es aprobación humana
ni evidencia de utilidad de entrenamiento. Continúan el seguimiento horario
y la generación; no se ha iniciado el piloto de aumentación.

## Muestras recientes y estimación actualizada: 30/10 por la mañana

La consulta solicitada por el usuario encontró 335 imágenes verificadas
(144 heredadas + 191 nuevas), con la escena 023 aún en captura. Faltan 665
imágenes por cerrar y verificar; los pares del prefijo activo se conservan
aparte. Fuentes congeladas (130) e identidades de controlador/trabajador
se verificaron. Las muestras 022/020 (despejado/lejana), 022/016
(bruma/intermedia) y 022/021 (cubierto/cercana) pertenecen a una escena
cerrada y sus auditorías de píxeles y etiquetas pasaron.

Los seis bloques completos más recientes, escenas 017–022, tardaron
42,94–46,52 minutos por 24 vistas (media 44,82). La preparación y auditoría
promediaron 12,39 minutos por escena; captura más cierre, 81,07 segundos
por vista. Acreditando el tiempo ya transcurrido de la escena activa,
la estimación central restante es 20,48 horas efectivas, con margen de
planificación de 20–24 horas si se mantiene el rendimiento. No es un
intervalo de confianza ni incluye suspensión/espera de recursos. Esta
estimación de producción reemplaza la extrapolación del ensayo corto;
no se alteran presupuestos ni calidad. Cálculo persistido en
`remaining_estimate_20261030T1140.json` dentro de la campaña.

La vista amplia 022/020 revela un halo claro visible en la composición
de cielo y horizonte, que no resultaba dominante en las primeras muestras
015. Se conserva y documenta; no se presenta como fotorealismo logrado.
Antes de congelar un dataset para entrenamiento, revisar y reducir esa
franja con comparaciones de cámaras idénticas, conservando plantas y GT.
Esta observación no altera la admisión física de las plantas. No se editan
fuentes en caliente ni se inicia entrenamiento; las imágenes mostradas
son las capturas de producción sin retoque posterior.

## Corrección autorizada del halo y distancias continuas

El usuario autorizó corregir el halo y aplicar a futuras tomas una mezcla
aleatoria continua: 70 % cerca–medio y 30 % medio–lejos, sin modificar plantas
ni perder imágenes. Se detuvieron sólo controlador y trabajador propios con
PID/creación comprobados. Se preservaron 335 vistas ya verificadas y trece
pares del prefijo de escena 023: 348 pares completos en total contando los
144 heredados, además de parciales y negativos. Los prefijos no se presentan
como escenas cerradas. Revisión:
`revisions/horizon_matte_continuous_depth_20261030`.

La mezcla angular/fotométrica anterior dejaba píxeles del cielo HDR brillante
junto a la silueta. La nueva máscara se alinea exactamente con la proyección
del panorama y retira el cielo original. El paisaje derivado extiende color
limpio en esa zona para evitar que el filtrado vuelva a introducir blanco.
Se suaviza el borde, conservando el campo y sin tocar geometría de cultivo.
Un primer candidato sin suavizado eliminó el halo pero mostró escalones;
quedó archivado. También se preservó un intento de guardado de máscara
detectado por el fixture; se añadió verificación de píxeles tras guardarla.
Ningún diagnóstico se suma al dataset ni reemplaza las vistas existentes.

La cámara usa referencias continuas derivadas del mismo encuadre anterior
para el objetivo seleccionado. La probabilidad 70/30 se aplica sólo a las
nuevas capturas; se informará su realización empírica, distancias y
dependencia por cielo. No hay cuotas reproductivas ni cambios de follaje.
Cinco pruebas puras comprueban continuidad, límites, reproducibilidad,
mezcla e independencia del cielo y ausencia de blanco antiguo en el
paisaje limpio. Dos pruebas de cielos y seis de continuidad también pasaron.
El fixture Blender de tres cielos pasó con los assets reales.

La estimación temporal anterior describe la receta previa de distancias.
Se debe actualizar tras bloques completos con la nueva distribución; no
se extrapolan como producción los renders de diagnóstico ni las pausas
de implementación. Presupuesto y meta de 1.000 permanecen intactos.

La comparación final a cámara/luz idénticas de 022/020 eliminó la franja
blanca y suavizó el borde. Pasaron el hash geométrico completo, la cámara
(error máximo 0), las instancias y YOLO exactos, y la máscara tanto por SHA
de archivo como píxel a píxel. El resultado diagnóstico está en
`paired_preview/result.json` y no se cuenta como nueva vista de producción.
La simulación de 10.000 sorteos dio 6.974 cerca–medio y 3.026 medio–lejos,
con distancias continuas únicas; no es el resultado aún observado del banco.

Antes de reanudar se verificaron los 204 pares nuevos comprometidos y los
144 heredados, junto con los hashes de los registros conservados. Quedaron
congelados 136 archivos de fuentes/entradas/assets en la revisión nueva.
No cambió el presupuesto. Se reanudó el mismo controlador desde el checkpoint
de la escena 023; los registros de vistas históricas no se reescribieron.
La validación del grafo mantiene los diez errores preexistentes de
localizadores, sin errores nuevos de esta intervención.

La primera toma nueva de producción, 023/013, ya usó la revisión:
distancia continua de 2,3599 m en el intervalo medio–lejos de su objetivo
(referencias 0,6535 / 1,3070 / 3,1369 m). Su máscara y YOLO pasaron con
533 instancias; el cierre de la escena seguía pendiente. Los 204 registros
anteriores comprometidos conservaron sus hashes tras reanudar. Esta muestra
no se presenta como comprobación del porcentaje final 70/30 con sólo una
observación; el resumen informará la proporción real conforme avance el banco.

## Estimación con dos bloques completos de la nueva receta: 30/10, 17:14 UTC

El banco alcanzó 407 vistas verificadas (263 nuevas + 144 heredadas), con
593 pendientes de cierre/verificación y 22 pares adicionales del bloque
en curso preservados aparte. Los dos primeros bloques íntegros con la nueva
receta, escenas 024 y 025, tardaron 64,85 y 68,18 minutos por 24 imágenes.
La media fue 66,51 minutos, incluyendo preparación y cierre; preparación
media 18,17 minutos y captura más cierre distribuido 120,87 s/vista.

Con ese rendimiento, acreditando los pares ya capturados del bloque activo,
la proyección central restante fue 26,44 horas efectivas; margen de
planificación 25–30 horas. Sustituye la estimación anterior de 20–24 horas
de la receta previa. Es una proyección preliminar condicionada a dos bloques,
no un intervalo de confianza ni una atribución causal del cambio de tiempos.
Pausas y esperas futuras prolongan el tiempo de pared. Se usan duraciones
persistidas por el controlador en cada job y su heartbeat, evitando restar
relojes de procesos distintos en esta proyección. El contraste temporal
observado por el monitor del 14:07 UTC queda conservado en su registro.

Las 136 fuentes/entradas/assets, los propietarios nativos y las 263 auditorías
de nuevos pares cerrados pasaron. Las 59 vistas nuevas continuas cerradas
incluían 48 sorteos cerca–medio y 11 medio–lejos; es la realización observada
del tramo inicial, no se fuerza ni reetiqueta para aproximar el 70/30.
La campaña sigue activa sin entrenamiento. Cálculo y supuestos en
`remaining_estimate_continuous_20261030T1714.json`.

## Estado posterior: pausa autorizada al umbral500

El usuario pidió detenerse y evaluar diversidad antes de decidir continuar.
Al recibir la instrucción ya había cerrado el bloque de503 vistas. Se
detuvieron únicamente propietarios verificados y se preservaron503 vistas
y parciales, sin reiniciar presupuesto. Una guarda de pausa impide reanudar
por accidente y el seguimiento quedó PAUSED. Se evaluaron las primeras500
en orden congelado; tres adicionales permanecen aparte de ese análisis.

El informe `diversidad_banco_500_2026-10-30.md` recomienda comprobar utilidad
con un piloto pequeño de46/115 vistas corregidas antes de producir otras500
de la misma receta. No se entrenó. La campaña de1.000 queda pendiente de
decisión, no cumplida ni cancelada; el estado operativo es
`awaiting_user_decision_after_diversity_review`.
