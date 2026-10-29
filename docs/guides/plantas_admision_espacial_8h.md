# Plantas con admisión espacial: ejecución de ocho horas

**Nueva autorización del 29/10:** tras revisar el suelo gris, el usuario pidió
tierra, hojarasca y vegetación irregular y amplió la ejecución hasta alcanzar
1.000 pares completos de esta variante o consumir ocho horas efectivas
adicionales desde la autorización, lo primero que ocurra. Se conserva el reloj
acumulado y el presupuesto anterior mediante `authorized_budget_revision.json`;
no se vuelve a generar el pool de veinte plantas ni se entrena. Las 192 vistas
de contexto abierto/suelo gris se preservan como calibración, excluidas del
banco activo. La revisión vigente es `earthen_floor_v5_20261029`, con fuentes
y configuración congeladas. Las secciones siguientes documentan la secuencia
histórica y sus límites originales; esta autorización posterior gobierna el
presupuesto vigente. El [contrato reutilizable](generador_actual_y_contrato_gazebo.md)
describe cómo iniciar otras campañas y exportar árboles admitidos a Gazebo.

**Actualización del 29/10:** el usuario pidió seguimiento cada hora y cambiar
de fase al completar veinte plantas válidas. El supervisor independiente
`handoff_spatial_dataset.py` vigila ese umbral continuamente, detiene sólo
procesos propios identificados y congela veinte árboles auditados. Después
`render_spatial_dataset.py` puede generar el nuevo dataset con el tiempo que
reste del **mismo** presupuesto de ocho horas; no hay reinicio ni ampliación.
Si no se llega a veinte, no se inicia el dataset. El entrenamiento permanece
fuera del alcance. La autorización posterior está en `phase_policy.json` y
`revisions/20plant_dataset_20261029/`, separada de las fuentes congeladas de la
fase de plantas. El contrato inicial siguiente describe esa fase anterior.

El usuario sustituyó la solicitud de dataset y piloto por obtener tantas
plantas físicamente válidas como sea posible en ocho horas efectivas. No hay
objetivo de parada en veinte ni autorización vigente en esta ejecución para
crear un banco de entrenamiento o entrenar. La raíz independiente es
`outputs/spatial_plant_pool_20261028/`; su presupuesto registra la fecha UTC
real de inicio. Las campañas cerradas y la revisión de la tercera candidata
permanecen preservadas.

## Contrato de reducción

`spatial_admission.py` trabaja con hojas completas —lámina, nervio y pecíolo—
y unidades reproductivas completas —pedicelo, fruto y capacho—. Nunca omite
ejes ni nodos. Las flores quedan fuera de los candidatos de eliminación.
Los conflictos proceden de la auditoría completa de mallas evaluadas, con
identidades resueltas desde las etiquetas de los objetos; un choque entre
órganos fijos no puede solucionarse mediante esta admisión.

Cada presupuesto se calcula sobre el árbol original, antes de cualquier
omisión: pérdida de frutos estrictamente menor del 5 % y pérdida de hojas
estrictamente menor del 5 %. El máximo entero es `(N-1)//20`, de modo que
en veinte órganos no se permite retirar uno. No se reinicia el presupuesto
al reiterar una corrección ni se acumulan planes sobre árboles ya reducidos.
Además se exige perder menos del 5 % de la suma nominal `largo*ancho` foliar;
es un proxy de envolvente, no área superficial medida ni oclusión.

La cobertura de conflictos usa restricciones forzadas, una propuesta voraz y
búsqueda acotada con cotas de matching. Se registra si se pudo demostrar
minimalidad; una cobertura factible no se presenta siempre como óptima.
La selección no utiliza cámara, apariencia, clases, validación ni test de
un detector. Si no se encuentra cobertura dentro de ambos límites, continúa
la corrección de postura o se rechaza la candidata.

## Regeneración y auditoría

`worker_spatial_pool.py` conserva la búsqueda nodal desde abajo, movimientos
de hojas antes de ascensos, articulación de dos/cuatro entrenudos y capachos
colgantes. En cada reconstrucción evalúa si los cruces restantes tienen una
cobertura admisible. Cuando la encuentra, regenera la morfología con el plan
explícito, antes de construir geometría, y reproduce las posturas de los
órganos retenidos. No elimina objetos después de renderizar ni fragmenta
anotaciones. Las dimensiones de los supervivientes no cambian.

La validación restaura los órganos omitidos en memoria y verifica la firma
anatómica completa del original. El plan, el inventario y la anatomía están
ligados por hash. Esto es una heurística de ingeniería de admisión espacial,
no un modelo medido de aborto floral o abscisión. La realimentación depende
de la postura auditada; no implica una simulación mecánica del crecimiento.

La admisión exige cero cruces duros en las categorías auditadas, suelo plano
válido con margen de 1 mm, orientación/unión de cálices válida y morfología
sin errores. Se conserva la excepción hoja–hoja como ocupación blanda y las
proximidades como advertencias. Flores y contexto no están certificados de
forma exhaustiva. La revisión visual humana de cada muestra queda pendiente.

## Controlador y alcance temporal

`run_spatial_plant_pool.py` mantiene un solo hijo Blender oculto, con PID y
creation tick registrados, y un watchdog de tiempo global y por candidata.
Usa `QueryUnbiasedInterruptTime`: excluye suspensión e incluye preparación,
pruebas y ejecución desde el inicio registrado. No modifica permanentemente
la política energética; solicita evitar suspensión sólo durante el proceso.
No hay entrada de entrenamiento ni de dataset en este controlador.

La cola empieza por tres posturas antes rechazadas (2026102702, 2703 y 2708),
que pueden producir nuevas admisiones, pero se registran como recuperaciones,
no como nuevas semillas. Después sigue un inventario de 64 semillas v8 nuevas,
ordenado por un proxy de coste anatómico original, y finalmente semillas nuevas
consecutivas hasta consumir el presupuesto. No se altera la arquitectura para
obtener ese orden. Esta planificación adaptativa busca rendimiento de cómputo;
no permite inferir una tasa de éxito uniforme de la población de plantas.
Los inventarios puros no cuentan como plantas admitidas.

Cada intento conserva original, posturas, plan, pérdidas, auditorías, fuentes
y resultado. Se cuenta una sola admisión por semilla y firma anatómica.
Las tres plantas previamente válidas de revisiones históricas quedan fuera
del contador nuevo. Si el proceso falla, se preserva evidencia y sólo se
recupera con fuentes compatibles, procesos propios identificados y tiempo
restante. El presupuesto nunca se reinicia.

La galería incremental está en `review.html`; `results.json` incluye también
rechazos y parciales. `closure.json` sólo aparece tras terminar. Ninguna
cantidad de plantas se declara anticipadamente lograda.

## Transición a dataset dentro del presupuesto restante

El supervisor tiene bloqueo exclusivo, identidad PID/creation tick y sus
propias fuentes congeladas. No modifica las fuentes de los trabajadores
activos. La revisión horaria del agente no sustituye al guardia de umbral.
Antes de detener la búsqueda se comprueban veinte admisiones únicas y sus
auditorías reales. Se preservan los resultados y cualquier vista parcial;
los árboles completos se copian y congelan en `dataset/inputs/`.

El renderizador prepara escenas de cuatro plantas admitidas, con suelo,
maleza, hojarasca y tutorado procedurales. El contexto se reexpresa sobre
suelo plano antes de construir plantas, manteniendo la condición de suelo
de sus auditorías previas. Las plantas sólo reciben colocación rígida;
no hay nueva poda ni cambio de órganos. Las escenas reconstruidas deben
volver a pasar malla, suelo y orientación. El contexto no se certifica
físicamente de forma exhaustiva, límite que permanece explícito.

Las cámaras alternan objetivos cercanos, medios y lejanos, sobre cálices
existentes. Las tres clases de apariencia y la variación de follaje son
independientes. Cada vista conserva RGB, máscara de instancia nítida y cajas
de todos los capachos visibles válidos, incluidos fragmentos de un píxel.
Sólo pares completos con hashes se incorporan a `dataset/manifest.json`.
Los rechazos, negativos candidatos y renders interrumpidos quedan fuera de
ese recuento, sin borrarse. No se duplican vistas para completar cantidad.

El objetivo de preparación es hasta mil imágenes de 960×720, o las que
permita el tiempo restante. Doce muestras Cycles con denoising y OptiX son
una elección de cómputo declarada en la fuente congelada, sin emisión en
órganos. No se asegura alcanzar mil ni se infiere eficacia para detectores.
El supervisor aplica el límite global también al hijo de render, recompone
el manifiesto desde los pares comprometidos y conserva las últimas vistas
parciales. No llama a ningún entrenador.

La revisión de pares ya comprometidos se ejecuta con
`scripts/report_spatial_dataset.py RAIZ`: verifica hashes, cuenta profundidad,
instancias por clase, escenas y exposición de cada planta, y prepara una
galería real. No llama muestras independientes a vistas de los mismos árboles
ni confunde veinte plantas disponibles con veinte necesariamente observadas
en las imágenes que alcanzó a producir el presupuesto.

La revisión visual del primer bloque detectó un contexto demasiado abierto.
Se conservaron sus primeras 21 vistas completas y su fuente como variante
`four_plant_open_context_v1`. La continuación `eight_plant_rich_rows_v2`
usa ocho plantas en dos hileras, menor separación entre envolventes, tutorado
por hilera y centros adicionales de maleza; incluye un modo procedural de
campo abierto entre los modos anteriores. No cambia los árboles, las clases,
la iluminación LT ni los criterios de admisión. Cada escena vuelve a
auditarse antes de renderizar. La revisión se registra en
`revisions/rich_context_v2_20261029/`; `dataset/source_lineage.json` vincula las
vistas previas a su fuente archivada y las nuevas vistas registran su variante
y hash de fuente. Esta diversidad de contexto no es un contraste factorial
controlado ni una demostración de eficacia para entrenamiento.

## Sustitución del contexto por petición del usuario (29/10)

El usuario rechazó visualmente las escenas abiertas. Las 180 vistas completas
anteriores quedan preservadas físicamente, pero `dataset/excluded_views.json`
las excluye del manifiesto, los conteos y la galería activos. Sus fuentes se
archivan en `revisions/dense_rows_v3_20261029/`; no son datos de entrenamiento.

La revisión v3 compone doce árboles admitidos en cuatro hileras de tres, con
separación entre envolventes de 0,75 BU (heurística), vegetación entre filas y
dos tutorados: horizontal o cables superiores con hilos claros inclinados.
Los hilos se sitúan fuera de la envolvente de copa; no se simula tensión ni
se afirma sujeción a ramas. Las referencias visuales son las imágenes train
01 y 06 de `docs/reports/assets/nuevo_dataset_2026-09-23/`. Las plantas no
cambian: mismos árboles, dimensiones y órganos retenidos, sin nueva poda.

Se corrigió la omisión de `asset_dir`: las cuatro texturas/panorama CC0 ya
disponibles en `outputs/assets_cache/polyhaven/` se cargan explícitamente,
se verifican y se congelan por hash. El panorama agrícola se usa sólo para
rayos de cámara; la iluminación LT y la exposición se conservan. No se usan
píxeles de las fotos reales en los renders. La cámara mira desde la hilera
frontal hacia las posteriores; la diversidad de profundidad procede también
de geometría real adicional. Todos los capachos visibles válidos se anotan.

Cada nueva escena debe pasar el mismo auditor de cruces, suelo y orientación
antes del RGB. Las proximidades y hoja–hoja conservan la política anterior;
contexto y flores no están certificados exhaustivamente. El presupuesto
original de ocho horas no se amplía ni reinicia; el tamaño final depende del
tiempo restante. La revisión v3 está en ejecución, todavía sin aprobación
visual de sus resultados ni entrenamiento.

La revisión de las primeras tres vistas v3 confirmó el panorama y las capas
de plantas, pero la cámara en un extremo de la hilera dejaba demasiado suelo
vacío. V4 restringe los objetivos a las columnas interiores de las dos filas
delanteras y mira hacia las hileras posteriores; usa el material PBR agrícola
cargado en lugar del mosaico de pastura. Conserva las plantas y las auditorías.
Se renderizan doce vistas por escena (cuatro por profundidad), priorizando
varias composiciones y ambos tutorados dentro del tiempo restante. Las tres
vistas v3 completas quedan identificadas con su fuente archivada; no se
confunden con v4 ni con las 180 vistas descartadas. El intento004 se detuvo
antes de RGB por capacidad de anotación: ahora la selección de doce árboles
completos incluye flores y cálices en el máximo de 4095 IDs, sin podar órganos.

Primer control v4: escena006 con hilos admitida con cero cruces duros, suelo
válido y 3504 cálices orientados/unidos válidos. Se inspeccionaron sus primeras
tres vistas completas y se comprobaron los 610 capachos de la primera máscara
contra cajas y YOLO. Se observan hilos claros y varias capas de cultivo; siguen
visibles repetición de hojas/maleza y diferencias de color del suelo respecto
a train. No son una validación humana de realismo ni una prueba de utilidad
para el detector. La generación continúa dentro del presupuesto original.
