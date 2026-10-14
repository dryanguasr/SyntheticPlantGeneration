# Reanudación con presupuesto de ejecución efectiva

El usuario aclaró que las doce horas excluyen suspensión. El cierre previo
por fecha absoluta fue incorrecto para ese criterio y queda superado, sin
borrar `run.json`, `closure.json`, capturas, fallos ni pesos técnicos.

## Contabilidad

`effective_budget.json` reserva una hora estimada de actividad anterior,
con incertidumbre de diez minutos. La sesión reanudada comienza a las
11:17:29 de Colombia. Se cuenta preparación, análisis y ejecución activos;
los trabajos contenidos en una sesión no se cobran otra vez. Los trabajos
fuera de una sesión se contabilizan por separado. El reloj Windows
`QueryUnbiasedInterruptTime` excluye suspensión/hibernación del sistema.
Al esperar una decisión del usuario se cierra la sesión activa; no se
consume presupuesto en esa espera. Una continuación debe abrir otra sesión
sin reiniciar el presupuesto global.

Los trabajos son exclusivos, tienen timeout, guardan sus fuentes en ZIP y
vigilan una reserva de RAM de 4 GiB. Esto conserva la reserva exigida en el
plan científico. No se rebajaron los umbrales geométricos ni de máscaras.

## Avance geométrico comprobado

La reparación anterior usaba transformaciones que no reproducían exactamente
el intérprete Blender. Se corrigió el cálculo de posiciones de prueba y la
orientación absoluta de capachos. También se incluyeron ápices, márgenes de
separación y pedicelos de flores. Los ajustes siguen expresados en la
morfología: no se eliminaron órganos ni se desligaron de nodos.

| Auditoría técnica de semilla 420100 | Intersecciones pendientes | Márgenes incumplidos |
| --- | ---: | ---: |
| Transformaciones corregidas | 6 | 251 |
| Inclusión de ápices y grupos reproductivos | 0 | 241 |
| Búsqueda con márgenes | 0 | 5 |
| Corrección de capacho restante | 0 | 4 |
| Inclusión de pedicelos de flores | **0** | **0** |

La última auditoría es `repair_flower_margins/mesh_audit.json`. Su aprobación
se refiere a los órganos de la planta aislada que audita el generador;
mantiene la tolerancia explícita hoja/hoja. No certifica contactos con todo
el contexto, botánica real, ni las otras 23 morfologías preparadas.
La prueba de conservación verifica determinismo, identidades, nodos,
dimensiones de entrenudos y conexiones de ramas.

## Capturas y formato de segmentación

Se produjeron diez RGB y máscaras de la primera morfología aprobada:
`cycle_01/pilot_420100/`. Las seis vistas de revisión son 0, 2, 4, 5, 7 y 9,
incluyendo los fallos. La galería está en `cycle_01/review.html`.

- Encuadre completo de planta con margen: 10/10.
- ArUco decodificado desde RGB: 8/10; la proyección por sí sola no certifica
  decodificación ni ausencia de oclusión.
- 527 observaciones de instancias entre imágenes, **no 527 capachos
  independientes**.
- Imágenes que pasan todos los polígonos a IoU ≥ 0,98: **0/10**.

Las oclusiones dividen capachos pequeños en componentes. Un único polígono
con puentes añade píxeles y falla el umbral. Las imágenes completas se
rechazan para la exportación estándar; no se eliminan instancias visibles.
La aclaración posterior del usuario confirmó que las máscaras visibles son
la referencia. La consulta sobre polígonos fue un bloqueo innecesario del
agente: se conserva la máscara exacta mediante el cargador adaptado y la
exportación poligonal queda limitada a imágenes compatibles. Las pruebas
preservan componentes separados y huecos; no se vuelve a pedir confirmación.
El entrenamiento principal requiere además el lote completo y aprobado.

Las referencias reales consultadas son únicamente `01_plano_general.jpg`,
`04_perspectiva_baja.jpg` y `06_plano_medio.jpg`, todas del grupo de desarrollo
`train` del manifiesto de ilustraciones. No tienen calibración común de
distancia/cámara con este piloto. Persisten contexto simplificado, ausencia
de cuerdas en el piloto aislado, suelo poco variado, nervaduras débiles y
orientaciones foliares poco naturales. La aprobación geométrica **no**
demuestra una mejora suficiente de fidelidad visual.

## Gazebo: diagnóstico del campo de 36 plantas

Las pruebas reutilizan el campo v4 anterior solo para diagnóstico técnico;
no materializan ni congelan el grupo nuevo de desarrollo. Las modificaciones
de contexto conservan sus 2.340 capachos individuales. Se verificaron por
comparación directa todos sus vértices y caras frente al campo fuente.

La reducción de contexto bajó de 5.824.267 a 3.160.374 triángulos. Una
comprobación ortográfica de tres copas obtuvo IoU 0,955–0,965 y diferencias
de cobertura inferiores al 2 %. Es una comprobación limitada de hojas de
contexto, distinta del umbral 0,98 para anotaciones de capachos.

El recorrido exterior revisado tiene margen geométrico mínimo estimado de
0,575 m. Las doce estaciones de dos caras exteriores pasan proyección de
los límites de malla y marcadores con margen del 5 %. Las otras diez caras
no se declaran accesibles. Falta verificar el encuadre y la separación
durante movimiento real simulado.

La agrupación de contexto, dos reducciones de detalle y el importador
alternativo no produjeron RGB: el control de memoria detuvo las pruebas.
La conversión posterior del contexto a GLB tampoco resolvió el bloqueo:
el trabajo terminó tras 32,3 segundos efectivos, con cero RGB y un mínimo
observado de 2,96 GiB libres durante la parada. Los capachos conservaron
sus OBJ originales; el aspecto del contexto convertido no pudo validarse.
El proceso observado alcanzó aproximadamente 8 GiB RSS y el host bajó de
la reserva de 4 GiB. Se conservaron los informes de fallo y solicitudes
de parada. No hay vuelo técnico aprobado, referencia fija ni video final.

La prueba de importador usa la opción incluida en Gazebo, sin instalar
dependencias; su selección está documentada en el código oficial de
[MeshManager de gz-common5](https://raw.githubusercontent.com/gazebosim/gz-common/gz-common5/graphics/src/MeshManager.cc).
No se promovió ese importador como mejora demostrada.

## Estado de continuidad

**Cero ciclos completos en este punto.** El presupuesto no está agotado.
El formato ya está resuelto; continúa la auditoría y generación del lote.
Se conserva Gazebo como entorno de vuelo y no se presenta un diagnóstico
técnico como un ciclo completo.

Se añadieron pruebas puras de decodificación panóptica, emparejamiento de
máscaras, duplicados y confusión de clases. El evaluador incorpora clases
colapsadas. La sincronización positiva, la atribución objetivo/fondo y la
estabilidad de identidad entre cuadros siguen sin validar. No existen
modelos comparables, ganador ni evaluación final reservada.

## Segunda reanudación: ejecución efectiva desde 18:22 UTC

La espera anterior no se cobró. Se abrió una nueva sesión de ejecución sin
reiniciar el saldo. Dos morfologías, 420100 y 420101, ya pasaron intersecciones
y separaciones. La reparación de 420101 tardó 518 segundos; la búsqueda
escalonada reubica primero órganos reproductivos y después hojas, pero
mantiene la auditoría final completa. Se incorporaron checkpoints parciales
que nunca sustituyen la aprobación final.

Se fijaron 180 imágenes por ciclo: 14 escenas de entrenamiento y cuatro de
validación, diez vistas cada una. Son subconjuntos de los grupos originales.
Los tres ciclos conservarán esas escenas, volumen y cámaras. Las capturas
exploratorias anteriores se preservan separadas en `captures`; el dataset
principal irá en `dataset_captures`, con cámara nivelada a 0,7 m, distancia
mínima 3,5 m y variación de luz determinista por semilla. No se asocia luz
a una categoría de capacho. El exportador exige el lote completo y rechaza
semillas de desarrollo/final.

Las pruebas RGB sin sensor de máscaras y sin texturas también excedieron
la reserva en el campo grande. La prueba sin follaje obtuvo 51 pares
sincronizados, pero es solo diagnóstico. Una prueba posterior con seis
arbustos completos y texturas pasó 51 pares durante 10 s, ArUcos RGB y
separación mínima ejecutada 0,705 m, dejando al menos 8,28 GiB libres.
No certifica todavía encuadre completo en todas las estaciones: el arranque
antiguo estaba fuera de la primera copa. La nueva ruta comienza frente a
la primera planta y deberá volver a verificarse.

Se fijó un escenario viable de una hilera con seis arbustos para desarrollo
y otro disjunto para cierre. Tras el filtro geométrico puro, las semillas
de desarrollo son 420202–420207; las finales son 420300, 420302, 420304,
420305, 420306 y 420308. Se escogieron las primeras seis sin conflictos
de ejes de cada grupo original, antes de evaluar modelos. Se conservaron
las exclusiones y la selección inicial provisional en los registros. Doce estaciones corresponden a dos
caras por arbusto; **no equivalen a doce caras de seis hileras**. La geometría
de cada arbusto y sus capachos individuales se conservan. El escenario final
no se renderiza ni se inspecciona antes de congelar el ganador.

## Observaciones del usuario para las próximas iteraciones

Sin interrumpir la corrida actual: retirar las plántulas geométricas de la
base o sustituirlas únicamente por una cobertura convincente de pasto o
maleza. Revisar primero su eliminación en vistas fijas. Los hilos deben
tirar diagonalmente hacia afuera y ser coherentes con la apertura de ramas
registrada en la morfología; la representación no implica tensión medida
ni una simulación mecánica validada. Aplicar desde el ciclo 2.

## Seguimiento horario y correcciones de continuidad

El heartbeat horario está activo en este chat. La primera comprobación verificó
Blender y el supervisor vivos; la segunda encontró el lote finalizado con tres
escenas rechazadas (420105, 420115 y 420121). Se conservan sus intentos.
La reparación empleaba triángulos de bucles, mientras que la auditoría completa
construía el BVH desde polígonos: se unificó el método sin relajar tolerancias.
Para una hoja aún atrapada se amplió la búsqueda de ángulos de inserción,
como heurística explícita que conserva identidad y unión nodal.
También se añadió reintento acotado ante bloqueos transitorios de lectura
de registros en Windows; errores persistentes siguen propagándose.
Los intervalos sin procesos entre comprobaciones se excluyen del presupuesto.
La exportación excluye los intentos incompletos, conserva sus archivos y
exige encuadre completo además de la auditoría geométrica.
Un controlador encadena exportación, medición de tres épocas, fijación del
presupuesto común y entrenamiento principal, sin usar métricas reales ni
resultados del escenario final. Aún no hay ciclos completos en este punto.

El lote principal ya contiene 180 imágenes (140 entrenamiento, 40 validación),
con 18 escenas aprobadas, encuadre completo 180/180 y máscaras canónicas
con IoU de ida y vuelta igual a 1. El marcador se decodificó en 82/180 RGB: es
una limitación registrada, no cobertura completa. Hay 7051 observaciones
pintona, 1389 madura y 1369 sobremadura; incluyen repetición entre vistas.
Las seis morfologías de desarrollo ya aprobaron su auditoría. Se exportó el
campo con capachos individuales; la simplificación del contexto preserva
sus triángulos y requiere revisión visual antes de aceptar el vuelo.

## Primer modelo y prueba de vuelo del grupo de desarrollo

El primer entrenamiento principal completó 60 épocas a 960 y batch 2, con
AMP, en 1344 segundos aproximadamente. En validación sintética: mAP50–95 de
máscaras 0,05005, mAP50 0,12058, precisión 0,15933 y recall 0,22111. El
umbral operativo seleccionado solo con esa validación es 0,10711.
El benchmark fijó 60 épocas para los tres ciclos por coste y memoria; ningún
resultado real ni final participó en esa decisión.
La prueba técnica del campo nuevo pasó 51 pares exactos durante 10 segundos,
incluida la comprobación de al menos 30 pares con objetivo completo y
su propio ArUco decodificado. Mantuvo al menos 7,98 GiB libres en el host.
La revisión del primer RGB confirma copas completas, pero sigue mostrando
un contexto simplificado y follaje rígido; no demuestra fidelidad real.
Se inició el recorrido completo y se encadenó su validación y evaluación.
Todavía no hay un ciclo completo ni una prueba de transferencia al cultivo.

## Cierre del ciclo 1 y cambio de encuadre solicitado

El ciclo 1 completó sus cuatro etapas: 180 imágenes, 60 épocas, vuelo de
254,558 s simulados con 17/17 puntos y margen mínimo ejecutado 0,555 m,
y evaluaciones sobre vuelo completo y referencia fija. En 84 imágenes de
la referencia: mAP50–95 de máscaras 0,000753, precisión 0,07353, recall
0,02916; 99,86 % de las observaciones tiene lado equivalente menor de
16 píxeles. Se conservan los resultados bajos y el diagnóstico.
El usuario pidió acercar la cámara para llenar el cuadro con planta y
ArUco. Esta autorización modifica la distribución de cámaras desde el
ciclo 2; se mantienen semillas, clases, volumen y presupuesto de entrenamiento.
Las primeras capturas anchas del ciclo 2 se guardan como controles y no
se agregan al dataset principal. La escena activa terminó antes de cambiar
el encuadre; se detuvo solo su coordinador para evitar más capturas obsoletas.
El nuevo ajuste usa vértices evaluados de Blender: la primera muestra pasa
de 3,5 m a 2,559 m y ocupa el 86 % de la altura con margen nominal del 7 %.
La ruta cercana deberá verificar margen ejecutado 5 % y separación 15 cm.
La referencia fija ancha no se reemplaza; ambos modelos se evaluarán también
en el mismo vuelo cercano. No se atribuirá aisladamente a apariencia una
mejora que incluya el cambio de cámara. La revisión automática rechazó una
propuesta con SciPy; se resolvió con bmesh incluido en Blender, sin instalar
ni añadir bibliotecas externas.

## Interrupción diagnosticada el 4 de octubre y pausa solicitada

No hay procesos de campaña activos. El último RGB se escribió el 3 de octubre
a las 22:02:48,583 (Colombia). Windows registró el inicio de instalación de
OpenAI.Codex a las 22:02:48,587 y su finalización a las 22:03:25,481.
La coincidencia temporal apunta a una interrupción por actualización de la
aplicación; el log no contiene una excepción de Blender ni una parada por
memoria (mínimo registrado 11,67 GiB libres). No es prueba de un fallo
interno del renderizador. Quedaron un lock y registros activos obsoletos.
El ciclo 1 permanece completo. El ciclo 2 cercano conserva 6 escenas
completas (60 imágenes), dos pares parciales de la escena siguiente y
un RGB sin su máscara. No comenzó el segundo entrenamiento.
Se preservó la evidencia, se excluyó la inactividad del presupuesto y se
pausó el heartbeat. No se ejecutó ningún trabajo de campaña durante este
diagnóstico. Esperar confirmación explícita del usuario antes de reanudar.

## Idea del usuario para un experimento posterior: ROI y recortes superpuestos

Registrada el 4 de octubre de 2026. Estado: propuesta pendiente; no se incorpora
automáticamente a la campaña actual ni modifica su protocolo de comparación.

Evaluar un procesamiento en dos etapas:

1. Detectar el arbusto completo para delimitar una región de interés (ROI).
2. Dentro de esa ROI, procesar recortes ligeramente superpuestos de la imagen
   original, en lugar de reducir la imagen completa a la resolución de entrada
   del modelo. Reproyectar las detecciones o máscaras a las coordenadas originales
   y resolver duplicados en los solapamientos.

Hipótesis del usuario: conservar más información espacial podría mejorar la
detección de frutos/capachos pequeños con ambos tipos de modelo. La mejora está
por comprobar. Se conserva la expresión «ambos tipos de modelo» sin asumir aquí
una pareja concreta de arquitecturas.

Para la prueba posterior, comparar imagen completa, ROI sin mosaico y ROI con
recortes sobre los mismos fotogramas y modelos. Definir tamaño y solapamiento
usando desarrollo; medir recall y precisión por tamaño aparente, calidad de
segmentación cuando aplique, errores en bordes, duplicados y latencia total,
incluyendo la localización inicial del arbusto. Registrar también las omisiones
de la primera etapa: un arbusto no localizado no debe desaparecer del denominador
de evaluación. Tamaño de recorte y porcentaje de solapamiento quedan pendientes.

## Continuidad del 4 de octubre: segundo entrenamiento y vuelo cercano
El usuario autorizó reanudar después de actualizar. El ciclo 2 completó 180 imágenes y 60 épocas desde los mismos pesos generales. mAP50-95 de máscaras en validación sintética: 0,180809; no equivale a una mejora confirmada en la referencia fija. Campo, envolventes de encuadre y LOD exportados. Un intento de inicio de WSL falló por acceso del sandbox; el reintento autorizado fuera del sandbox pasó los controles técnicos con 51 pares sincronizados, ArUco RGB, encuadre completo y separación mínima ejecutada de 0,399 m. Se inspeccionó el RGB cercano. El vuelo completo y las tres comparaciones quedan en ejecución; el ciclo 2 aún no está cerrado. La propuesta ROI y recortes permanece para un experimento posterior.


## Cierre del ciclo 2 e inicio del ciclo 3
El ciclo 2 superó todos los controles de cierre: 180 imágenes, 60 épocas, vuelo completo de 17 puntos y tres evaluaciones. En referencia fija retrocede de 0,000753 a 0,000708 mAP50-95 de máscaras; en el mismo vuelo cercano supera al modelo 1 (0,008186 frente a 0,001246). La mejora sintética de validación no se replica en la referencia común. Se conservaron la regresión, ejemplos y diagnóstico. El ciclo 3 cambia únicamente el rango de iluminación para ampliar sombra y contraste; conserva morfologías, cámaras cercanas, clases, tamaño del dataset e inicialización/presupuesto. Parámetros heurísticos, mejora visual aún no demostrada. Se revisaron seis vistas cercanas del ciclo 2; persisten follaje rígido y fondo simplificado. Iniciada generación y posterior entrenamiento del ciclo 3, con reserva de cierre intacta.


## Recuperación de escritura transitoria en el ciclo 3
La escena 18 se interrumpió por WinError 5 al reemplazar el JSON de seguimiento; las primeras 17 escenas completas se conservaron. Se recuperó el registro final desde su archivo parcial y se archivó el lock obsoleto después de comprobar que no había procesos vivos. El escritor atómico ahora reintenta durante un máximo de dos segundos los bloqueos PermissionError; persisten y se propagan los errores permanentes. Se verificaron recuperación transitoria, propagación y preservación del registro anterior. La sesión previa ya estaba cerrada: no se imputó el intervalo inactivo. Última escena reanudada, después seguirá el entrenamiento. Las seis vistas del ciclo 3 conservan silueta y cámara y son algo más oscuras; no demuestran por sí solas mayor fidelidad real.


## Tercer entrenamiento terminado
Ciclo 3: 180 imágenes válidas y 60 épocas completadas desde la inicialización general común. mAP50-95 de máscaras en validación sintética: 0,164228, inferior al 0,180809 del ciclo 2. Se inicia un nuevo vuelo técnico y completo sobre el mismo escenario y recorrido cercano: el cambio del ciclo 3 afecta solo a iluminación de entrenamiento, por lo que se reutilizan los activos de Gazebo y se capturan observaciones nuevas. Seguirán las comparaciones modelo 3/vuelo nuevo, modelo 3/referencia fija y modelo 2/vuelo nuevo. El ciclo continúa pendiente de evaluación y cierre; el escenario final permanece reservado.


## Tres ciclos completos y selección congelada
El modelo 3 gana con mAP50-95 de máscaras 0,000822 en la referencia fija; ciclos 1 y 2: 0,000753 y 0,000708. En el tercer vuelo cercano, modelo 3: 0,010637; modelo 2 sobre los mismos fotogramas: 0,008356. La mejora es pequeña en términos absolutos y no demuestra transferencia real ni significación estadística. Se guardaron diagnóstico, cierre del tercer ciclo y winner_selection.json antes de acceder a imágenes finales. Se omite el cuarto ciclo opcional para proteger auditorías geométricas, posibles reparaciones y evaluación final con las aproximadamente 2 h 58 min restantes. Iniciada auditoría de las seis morfologías finales congeladas; no se ajustarán pesos ni umbrales después de la selección.


## Evaluación final original cerrada e inicio del cuarto ciclo
La evaluación reservada terminó sin ajustes posteriores: modelo 3 mAP50-95 máscaras 0,012271, modelo 1 0,001768 en los mismos fotogramas. Esto mide Gazebo, no transferencia al cultivo. El cuarto ciclo inicia una prueba de inferencia aislada con el checkpoint 3 congelado: ROI por color/conectividad RGB (heurística explícita, todavía no detector aprendido), recortes de 640 píxeles a escala nativa con relleno, 20 % de superposición y NMS por máscara y clase. Se verificó cobertura completa de recortes y ausencia de ROI en RGB vacío. Las máscaras del evaluador se cargan después de inferir y no guían el recorte. Entrenamiento y vuelo propios del cuarto ciclo siguen pendientes; no presentar este sondeo como ciclo completo. Se evalúa primero en desarrollo y se conserva el final original como resultado cerrado.


## Cuarto ciclo: corrección del sondeo y comparación controlada
El sondeo tiled terminó la inferencia pero falló al serializar coordenadas int32 de las ROI; sus métricas quedan preliminares y el trabajo no se cuenta como evaluación completa. Se corrigió convirtiendo coordenadas a enteros nativos y se verificó el caso con una ROI no vacía. El cuarto ciclo conserva apariencia y las 180 imágenes del tercero, reexporta una versión independiente de máscaras exactas y reinicia el entrenamiento general durante 60 épocas. Esto evita atribuir a recortes un cambio simultáneo de dataset. Después se comparan imagen completa, ROI sin mosaico y ROI con recortes sobre la referencia fija. El vuelo nuevo sigue pendiente; la localización del arbusto continúa siendo una heurística RGB y debe describirse como tal.


## Comparación válida de inferencia del cuarto ciclo
Entrenamiento fresco de 60 épocas finalizado. Sobre la referencia fija: imagen completa mAP50-95 0,000822 / recall 0,02468 / mediana 0,097 s; ROI 0,003079 / 0,03291 / 2,195 s; recortes 0,029894 / 0,17382 / 2,215 s. Son resultados de desarrollo, sin prueba de transferencia real. Los pesos reproducen el ciclo 3 al conservar datos y semilla: la comparación aísla la inferencia. Primera etapa heurística RGB, no detector aprendido. Se aprobaron pruebas de cobertura hasta bordes, ROI serializable y vacía, y reproyección exacta de máscara al fotograma original. Iniciado vuelo nuevo del cuarto ciclo con comparaciones completa/ROI/recortes; aún pendiente de cierre. El umbral operativo proviene de validación sintética y no se reajustó usando estos vuelos.


## Validación del cuarto vuelo y recuperación de la evaluación
El vuelo nuevo alcanzó los 17 puntos, 259,658 s simulados y separación mínima 0,307845 m. La primera evaluación no arrancó porque el orquestador omitió crear segmentation_validation.json para el vuelo completo. Se corrigió la secuencia y el control pasó con 1.299 pares sincronizados. El directorio y log del intento fallido se preservaron; evaluación completa retomada en carpeta retry1, seguida de ROI y recortes. No se repitió el vuelo ni se cambiaron imágenes. La rama experimental verificada hasta ahora corresponde a segmentación; la intención exacta de ambos tipos de modelo continúa sin respuesta y no se declara evaluado un detector de cajas distinto.

