# Piloto disperso con tutorado superior: intervención del 23 de septiembre

Implementación en la rama `codex/sparse-overhead-pilot`, partiendo de un árbol
de trabajo limpio en `codex/new-real-dataset`. No se entrenó ni evaluó ningún
detector sobre datos reales. No se instalaron dependencias.

## Implementación

- Preset de cuatro escenas 6 × 6, con morfología propia por planta, tutorado por
  hilos, contexto de papa y dos alturas por tres distancias.
- Grados sintéticos explícitos 0–6; agrupación del usuario verde/pintona/madura/
  sobremadura. No se promueven a madurez real validada.
- Cajas YOLO/COCO y máscaras COCO RLE emparejadas del capacho visible, además de
  una derivación monoclase compatible con la comparación histórica.
- Dos placas por arbusto, 72 IDs `DICT_4X4_100`, transformaciones métricas,
  evaluación IPPE y selector de diccionario compatible en PC/Android.
- Supervisor de Blender con un proceso, reserva de memoria, techo temporal y
  preservación de fallos. Exportación independiente y comprobación de máscaras.

## Hallazgos y límites

La paleta antigua repetía colores cada 200 instancias. Se sustituyó por una
paleta biyectiva hasta 4095 IDs, versionada; se rechaza mezclar versiones al
reanudar. La creación mediante operadores provocaba crecimiento del coste con
el tamaño de la escena: BMesh y la API de datos redujeron la construcción de
36 plantas a unos 33 segundos en esta máquina.

Los proxies de colisión no bastan para certificar las mallas. La primera
auditoría completa después de resolver proxies detectó 32 colisiones físicas.
La curvatura estética añadida en Blender se desactiva para este preset, los
contactos intencionales se limitan al nodo declarado y los hilos buscan
separación de capachos. La siguiente escena registró 7 colisiones físicas y
29 separaciones insuficientes. **No se declara aprobación física.** La salida
se identifica como material de inspección, con entrenamiento deshabilitado.

Se conservan los intentos v1–v3 y sus logs. La entrega vigente se genera bajo
`outputs/sparse_overhead_pilot_v4/`; su `INFORME.md`, `measured_summary.json` y
`exports/integrity_report.json` contienen el cierre medido. Los outputs no se
versionan. No se equiparan pruebas unitarias correctas con fidelidad visual,
ausencia de colisiones ni generalización científica.

## Verificaciones ejecutadas

- Núcleo: 160 pruebas correctas; pruebas adicionales pertinentes después de
  versionar la paleta y optimizar el exportador también correctas.
- PC: 10 pruebas de visión correctas, incluyendo reconocimiento de ID 71 y
  conservación del diccionario histórico. La prueba Tk de interfaz no pudo
  inicializar Tcl en el entorno local; se conserva el error y no se marca aprobada.
- Android: compilación debug, pruebas JVM y lint correctos; dos pruebas nuevas
  de selección de diccionario correctas. No se ejecutó validación física en teléfono.
- Fixture Blender de máscaras/oclusión: correcta en 22,2 segundos, salida
  independiente del fixture histórico. No sustituye la auditoría del cultivo.
- Grafo validado. Verificador de exportaciones comprueba igualdad píxel a píxel
  del RLE con la máscara maestra, cajas, clases, hashes y correspondencias.

## Corrección del pase de identidad

La inspección visual de las primeras exportaciones reveló mezclas de colores
por antialiasing EEVEE que generaban IDs espurios y cajas demasiado grandes.
La integridad RLE/caja había pasado porque utilizaba la misma máscara errónea.
Se conservan esas exportaciones como diagnóstico y se rehacen únicamente
las máscaras con Workbench sin antialiasing. Un primer intento también
mostró que el fondo del motor debía tratarse explícitamente: se utiliza
transparencia y se convierte alfa cero a ID 0. Los RGB permanecen inmutables.

La comprobación geométrica final pasó para 4491 instancias visibles, sin
excepciones por plano cercano. Las vistas de dron se ejecutaron a 0,440–0,493 m:
la regla del 50 % queda próxima a los 0,400 m del cosechador para estos arbustos
estimados bajos. No se afirma que esta escala haya sido medida en campo.

La entrega incluye verificación independiente de límites proyectados de
capachos desde los `.blend`, además de igualdad de RLE y máscara y revisión
de superposiciones. El informe de proyección registra cualquier excepción
por cruce del plano cercano, sin confundirla con una aprobación.

## Continuidad

Revisar los objetos listados en cada `mesh_audit.json`, corregir conflictos
residuales en morfología y recorridos de hilos y repetir las auditorías sin
relajar umbrales. Revisar visualmente separación, forma y cobertura antes de
aprobar una campaña. El presupuesto de entrenamiento sigue pendiente.

El test histórico solo permite contrastar localización colapsando las cuatro
clases. Clasificación por estado y segmentación en el dominio real necesitan
nuevas anotaciones. Las vistas de cada escena deben permanecer juntas al crear
particiones; este piloto de inspección no las asigna.

Procedimiento reproducible: [guía del piloto](../guides/piloto_cultivo_disperso.md).

## Revisión solicitada: copas densas y placas de una sola cara

El usuario rechazó la baja densidad **intraplanta** de la entrega v4 y autorizó
48 imágenes para observar frente y reverso en cada escena (3 distancias × 2
alturas × 2 caras × 4 escenas). Se conserva la separación de 1,4 m y 1,8 m
entre plantas e hileras, y todos los 36 arbustos por escena.

Referencias inspeccionadas únicamente de `train` en
`outputs/new_real_dataset/captura_20260912_v6/images/train/`:
`54b14999deb5ce89_f000014626.jpg` muestra las copas completas y el tutorado;
`b5a8301471dcca22_f000002383.jpg`, `5d41efddf01cd412_f000016991.jpg` y
`00feba219f5ac1d8_f000000871.jpg` muestran hojas, ramificación y solapamientos.
Las fotos distinguen plantas separadas de copas individualmente frondosas.
No permiten deducir un conteo exacto de hojas ni escala métrica calibrada.

La revisión amplía ramificación y nodos, la superficie foliar y el intervalo
de inclinación descendente de las hojas. El primer ensayo de mayor número de
hojas seguía mostrando láminas de canto; se conserva como diagnóstico.
Los parámetros nuevos están separados del preset histórico `trained_trellis`
y declarados `manual_initial_guess`. El ajuste se hace en morfología, sin
copiar hojas flotantes ni añadir frutos desligados de sus axilas.

Las placas incorporan 3 mm de respaldo opaco con reverso liso. No se usan
filtros de visibilidad dependientes de la cámara. La prueba aislada sobre RGB
con OpenCV detectó exclusivamente ID 0 desde el frente e ID 1 desde atrás.
Ambas caras conservan el plano impreso de referencia para sus transformaciones.

La búsqueda exhaustiva de poses tardó 150,2 s para una sola planta de ensayo.
Para la revisión visual densa se mantienen ocho iteraciones de resolución
local y la auditoría global de mallas; se declaran omitidas la búsqueda
exhaustiva posterior y las microelevaciones. No se interpreta esta omisión
como aprobación física. Se conserva el bloqueo de entrenamiento.

La entrega corregida se prepara en `outputs/sparse_overhead_pilot_v7/`.
Los intentos intermedios v5/v6 y la comparación aislada se conservan.
`density_comparison.json` registra los conteos y proporciones efectivamente
obtenidos; `INFORME.md` e `exports/integrity_report.json` registran el cierre
cuando la ejecución completa termina. La muestra visual sigue pendiente de
aceptación humana; no se declara equivalencia fotográfica.

Conteos obtenidos en las 144 morfologías de la revisión: 35672 hojas frente a
8414 de v4 (4,24×), y 7059 ejes frente a 2112 (3,34×). Son conteos sintéticos;
no una estimación de número de hojas reales. La comparación usa las mismas
posiciones de cultivo. La prueba de transformaciones diferidas comparó 301
objetos visibles vértice a vértice sin diferencias; excluye las bayas ocultas
que el grafo de dependencias no evalúa de la misma forma que objetos visibles.
Se conservan los logs de los intentos iniciales del fixture, sin promoverlos
a prueba de equivalencia de todas las estructuras ocultas.
La ejecución inicial de la escena densa guardó el `.blend` de 36 plantas,
pero el supervisor detuvo la auditoría al quedar menos de 4 GiB libres
(pico observado 6,24 GB decimales de memoria del proceso). Se conserva
`resources_initial_attempt.json`. La continuación separa construcción,
auditoría y capturas en procesos Blender sucesivos. La caché de BVH está
limitada a 128 objetos, conservando todos los pares potencialmente relevantes
y los mismos umbrales. Un fixture de cinco esferas produjo idéntico informe
con caché completa y con solo dos objetos en caché, incluidas cuatro colisiones.
La escritura masiva de UV y su caché por topología redujeron un ensayo de tres
plantas de 37,9 a 17,4 s. No se redujo la resolución de las mallas. Las 164
pruebas de núcleo pasaron en 208,1 s; el fixture de geometría visible comparó
301 objetos sin diferencias después de aplicar las transformaciones diferidas.
La auditoría aislada también se detuvo a los 171,7 s por la reserva de 4 GiB,
con memoria estable del proceso (pico 4,86 GB). La reanudación usa una reserva
explícita de 2 GiB; el supervisor conserva el límite, los registros por intento
y el coste acumulado de los fallos. No se cerraron procesos ajenos.
La auditoría aislada de scene_00 terminó en 414,1 s (pico 4,89 GB), con
1.746 colisiones físicas y 1.153 separaciones insuficientes. El incremento
de densidad aún no constituye una escena físicamente aceptada. El primer
RGB se detuvo a los 83,3 s al alcanzar 11,73 GB de RAM y agotar la reserva
de 2 GiB. Se conserva el intento y se deriva una copia agrupada para render
con los mismos órganos, dejando intacta la escena auditada.
La agrupación con operadores se interrumpió por coste temporal. La copia
directa inicial falló en el fixture por usar materiales temporales del grafo
evaluado; se corrigió resolviendo los materiales originales. La prueba de
24 polígonos conserva posiciones, UV y materiales. Se difiere la actualización
global hasta terminar todos los grupos: 47.437 objetos pasan a 6.912 en
64,7 s, sin fusionar capachos. El primer RGB completo y máscara terminan
en 138 s (incluye copia y guardado), con pico 8,87 GB; la siguiente vista
termina en 66 s y 5,78 GB. La escena original auditada queda intacta.

La primera captura agrupada de scene_03 se detuvo por techo temporal: el
registro saltó de 168 a 864 s y después de 873 a 5.461,4 s entre muestras.
No se atribuye una causa no observada a estos huecos; el último registro
conservaba 7,66 GB de RAM libre. El total de 5.467 s no representa cómputo
continuo demostrado. Los RGB parciales quedan en diagnostics y la escena
se reanuda desde capture_geometry.blend sin reconstrucción.

La comparación de la búsqueda de separaciones acotada con el informe
completo original de scene_00 no encontró ninguna diferencia. Después se
corrigió una categoría heredada: los cruces hoja-hoja de mallas no son
oclusiones visuales; se registran como ocupación blanda geométrica sin
validación física. Se repiten las cuatro auditorías con versión 0.3.0;
los informes anteriores quedan en diagnostics. RGB y máscaras no cambian.

## Cierre de la revisión v7

Se completaron 48 capturas: cuatro escenas de 36 plantas, ambas caras, tres
distancias y dos alturas. Se conservaron escenas originales y copias agrupadas
para render. Las 15.894 anotaciones pasaron la igualdad píxel a píxel de RLE
contra máscara maestra, cajas YOLO/COCO, clases, hashes y agrupación por escena.
Las cuatro clases tienen cobertura en cada escena: verde 4.601, pintona 6.775,
madura 2.271 y sobremadura 2.247 (conteos por vista, no frutos independientes).
El control geométrico verificó 24.997 instancias visibles y 1.440 rayos de
respaldo de placas; no hubo IDs detectados incompatibles con la cara.

Los fixtures Blender de transformaciones, caché/búsqueda acotada y unión de
mallas pasaron. La nueva clasificación hoja-hoja se comprobó con intersecciones
reales de mallas de control. Las cuatro auditorías nuevas conservaron exactamente
los conflictos rígidos, distancias y contactos cercanos anteriores: 7.171
colisiones físicas y 4.895 separaciones insuficientes. Las 32.186 intersecciones
geométricas con hojas se registran aparte como ocupación blanda no validada.
El piloto sigue siendo de inspección; no se entrenó ni evaluó el test histórico.

Artefactos locales: `outputs/sparse_overhead_pilot_v7/INFORME.md`,
`exports/contact_sheet_rgb.jpg`, `exports/integrity_report.json`,
`audit_classification_revision.json` y cuatro pares de archivos Blender.
El almacenamiento medido ronda 2,25 GiB con diagnósticos conservados. Los
huecos del monitor de scene_03 quedan explícitos para evitar interpretar
el tiempo transcurrido como cómputo continuo.
