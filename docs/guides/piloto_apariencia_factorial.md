# Piloto factorial de apariencia: contrato y ejecución

Versión `appearance-factorial/1`, autorizado el 26 de octubre de 2026. Campaña
independiente: `outputs/appearance_factorial_20261026`. El piloto anterior cerrado,
sus fuentes congeladas y sus resultados se conservan. Esta guía describe código
implementado; el estado de ejecución se informa por separado en
[el informe de calibración](../reports/calibracion_apariencia_2026-10-26.md).

**Cierre del 27/10/2026:** no se obtuvo ninguna vista sintética admitida. Se
completaron dos screenings y seis controles reales finales, con tres semillas
por receta. El factorial y sus repeticiones quedaron bloqueados por generación.
Los resultados y límites están en el [informe final](../reports/piloto_apariencia_factorial_2026-10-26.md).
No se reabre esta campaña para generar nuevas escenas con fuentes distintas.

## Planta independiente de la captura

`trained_trellis_audit_v2` deriva de `trained_trellis` con política
`architecture_driven`. El desarrollo adulto utiliza presupuestos nodales y de eje
ya existentes, identificados como heurísticos, sin establecer una cuota de frutos.
La cámara no modifica nodos, entrenudos, ramificación ni órganos. Las cohortes
asignan estados a unidades existentes y pueden conservar cero unidades. La ruta
histórica mantiene su comportamiento para compatibilidad explícita.

Después de la revisión humana de la primera galería, los candidatos nuevos son
`trained_trellis_bush_audit_v3` (desarrollo nodal adulto también en laterales) y
`trained_trellis_bush_pose_audit_v4` (además, rango de inserción foliar 30–80° y
marco ortogonal local). Son hipótesis explícitas, no medidas de campo. La pose
v4 conserva exactamente órganos y tamaños de v3. Se mantienen v2/v3 para
reproducir las galerías anteriores. El perfil efectivo identifica el preset y
su `plant_parameters_sha256`; el banco congela `banks/plant_contract.json` y
rechaza cambios después de la revisión.

La revisión estructural posterior encontró la copa v4 demasiado estrecha. El
candidato `trained_trellis_broad_crown_audit_v5` desarrolla más los laterales,
separa la escala foliar adulta del vigor del eje y usa un marco local 3D para
ramas y hojas. Conserva el eje principal de v4 y el rango foliar base; los factores
por orden sí cambian, de modo que no se afirma igualdad de tamaño efectivo de
todas las hojas. Son hipótesis de ingeniería pendientes de revisión visual y
auditoría física, sin cuotas reproductivas ni dimensiones dependientes de cámara.
El detalle y las referencias de entrenamiento están en
[la revisión de copa](../reports/revision_copa_ramificada_2026-10-26.md).

El usuario autorizó proceder con entrenamiento después de la galería v6 y pidió
plantas más verdes y más amarillas con todas las apariencias de capacho. La
autorización y el perfil efectivo quedan congelados en `review_lock.json` y
`revisions/training_authorized_heterogeneity_20261026/`. Esa aprobación cubre la
familia de variaciones solicitada; no afirma revisión humana individual de cada
planta nueva ni verdad agronómica de sus clases.

La revisión v6 (`trained_trellis_lower_crown_audit_v6`) separa el inicio de
ramificación vegetativa del inicio reproductivo. Permite laterales desde nodos
inferiores sin garantizar su cantidad ni imponer un mínimo de frutos. Conserva
las dimensiones y reglas de v5 restantes; sigue siendo una hipótesis de ingeniería.
La corrección de contactos modifica poses nodales serializadas, nunca cámaras,
tamaños, clases ni cantidad de órganos. Primero se ajustan ejes con conflictos o
separaciones insuficientes comprobados en malla; después hojas y pedicelos, con
refinamiento angular local. Cada intento conserva árbol de entrada, historial,
fuentes y auditorías. La reconstrucción completa desde JSON decide la admisión;
la puntuación proxy y la convergencia de búsqueda no la sustituyen. Los intentos de
refinamiento usan pasos de 3, 1 y 0,25 grados sin ampliar el límite acumulado
de giro respecto a la pose generada. La selección entre intentos de una misma
planta usa auditorías geométricas, nunca el render ni métricas del detector.
La limpieza y reparación revisadas deben incorporarse al banco antes de lanzarlo;
una galería de cuatro plantas no admite automáticamente las escenas futuras.

La auditoría de esta revisión usa el mismo criterio estricto del banco: sólo
hoja–hoja permanece como ocupación blanda. La nueva comprobación de terreno usa
mallas evaluadas, unidades físicas y frutos internos incluso ocultos, además de
hojas, tallos, flores y cálices. Los trabajadores de generación limpian también
objetos ocultos entre reconstrucciones. Esto corrige residuos de escenas, sin
eliminar órganos del árbol ni modificar su visibilidad en RGB. Los límites de
cobertura y resultados se documentan en
[la revisión de contactos](../reports/revision_contactos_y_ramas_bajas_2026-10-26.md).

Los árboles nuevos guardan parámetros efectivos, hash canónico, política de carga,
conteos reproductivos por etapa y ajustes de continuidad radial en la inserción.
El orden 3 usa la reducción proporcional declarada entre órdenes previos; un orden
habilitado sin rango produce error. La validación distingue integridad,
plausibilidad y geometría, usando parámetros de la etapa. Los árboles históricos
sin snapshot declaran esa ausencia. `measured_local` conserva trazabilidad como
alias histórico, sin certificar mediciones inexistentes.

Geometría y proxies comparten el contrato de deformación. Las envolventes finales
se calculan sobre geometría evaluada; una AABB no prueba contención física ni
oclusión. El banco exige auditoría final sin intersecciones inválidas, conservando
los contactos permitidos y los intentos rechazados. No se eliminan órganos para
obtener encuadres o superar una auditoría.
La admisión declara como excepción las intersecciones hoja–hoja tratadas como
ocupación blanda; los contactos con maleza y residuos no tienen auditoría
exhaustiva. `accepted.json` registra esos límites: no constituye certificación
física integral de una escena ni simulación de deformación.

## Banco heterogéneo autorizado

Objetivo: 24 árboles nuevos y reproducibles, dos por escena, en 12 escenas. Se
mantiene el preset v6; cambian sus semillas, no la arquitectura en función de la
cámara. Se muestrean tres estratos de follaje —verde, mixto y amarillento— con
objetivo de ocho plantas por estrato. Las decisiones de hoja sana/senescente y
el ajuste de tono/saturación son hipótesis de ingeniería. Los estados de capacho
usan otro flujo aleatorio y no dependen del follaje. Se asignan las tres clases
a unidades ya existentes cuando hay al menos tres cálices; nunca se añaden
órganos para completar esa cobertura. Los cuatro bancos comparten todas estas
decisiones, por lo que el factorial no identifica por separado su efecto.

Cada escena repara poses angulares, conserva anatomía y se reconstruye desde
los árboles guardados. La política previa se conserva en los intentos históricos.
Antes del primer entrenamiento se registró la versión
`mesh_intersections_block_positive_gaps_descriptive/1`: los márgenes positivos
entre órganos se describen como advertencias; los cruces de mallas auditados
siguen bloqueando la escena. El terreno conserva el margen de 1 mm y el
contrato ampliado que incluye frutos internos. Hoja–hoja continúa como ocupación
blanda. Esta revisión de ingeniería sigue a la autorización de proceder tras
la galería que informó tres márgenes positivos, sin atribuir al usuario la
selección explícita de un umbral numérico ni una certificación física integral.

La revisión operativa 2.3 reparte el tiempo de búsqueda por tipo de órgano:
120/240 segundos para hojas/unidades reproductivas en el primer ciclo y
60/120 en los siguientes, manteniendo los totales previos de 360/180 segundos.
Se detectó que una planta con 452 frutos agotaba los dos primeros presupuestos
en reproducción y no alcanzaba una sola pasada de hojas. El intento se conservó;
los árboles adaptados completos se importan como entradas con hashes, comparación
contra la regeneración exacta y firma anatómica/clases coincidentes. No se reutiliza
una escena aceptada ni se mezcla una corrida de entrenamiento de otro protocolo.
La revisión cambia el reparto de búsqueda, no sus umbrales ni los órganos.

Los tutores rígidos individuales se colocan detrás de la envolvente evaluada
con 0,7 BU de margen heurístico, antes de seleccionar cámaras. El primer intento
con tutores cercanos al tallo produjo 20 cruces y fue conservado por completo.
El tutorado de fondo y las manchas de maleza varían por escena; el fondo sigue
siendo procedural y más simple que un campo real. El contexto queda idéntico
dentro de cada cuarteto B/L/T/LT.

Las cámaras eligen un cáliz existente mediante una semilla, preferentemente de
la clase de la referencia real, y usan proporciones y tamaños de entrenamiento.
La distancia física queda entre 0,6 y 40 BU: la diferencia respecto al objetivo
se registra. La selección determinista aproxima clase × tamaño y reparte vistas
entre escenas, sin usar validación o test ni exigir igualdad geométrica. Todas
las anotaciones visibles válidas permanecen, incluso fragmentos de un píxel.

`report_appearance_bank.py` mide la brecha por clase, tamaño, densidad, brillo y
saturación, con referencias exclusivamente de entrenamiento. Sus flags son
criterios descriptivos de ingeniería, no pruebas de significación ni puertas de
admisión. El informe propone sopesar brechas mediante las dosis 46/115/230 y los
controles real/B/repetición. Cambiar el peso de pérdida por dominio o instancia
se mantiene como hipótesis futura; la receta del entrenador continúa congelada.

La recogida de candidatos reserva tres horas activas para RGB antes de iniciar
nuevas escenas o cámaras. Si no alcanza el tiempo, se conservan menos escenas
y solo dosis completas; los árboles o vistas repetidos no cuentan como diversidad.

La secuencia completa se ejecuta con `scripts/execute_appearance_pilot.py`:
generación → diagnóstico → preparación de matriz → entrenamiento/evaluación.
Un controlador propio y un lock de GPU evitan duplicados. Conserva estados,
intentos, fuentes y presupuesto activo anteriores al reanudar. El primer
cuarteto se renderiza al terminar las máscaras de la primera escena para poder
inspeccionarlo durante la generación del resto.

## Calibración y revisión humana

Los perfiles de planta, cámara, iluminación y materiales son entradas explícitas.
Las semillas de componentes se derivan de forma determinista e independiente.
`profiles.json` es el candidato efectivo; los valores iniciales del módulo no
sustituyen ese archivo. No se reescribe código por sustituciones de texto.

Se mide exclusivamente entrenamiento real: 461 imágenes, usando los polígonos
originales cuando están disponibles, además de cajas para tamaño. La luminancia
calculada sobre RGB codificado no es reflectancia ni fotometría calibrada. El
contexto excluye los polígonos de capacho, pero incluye hojas, suelo y distractores.
No se reclasifican ejemplos ambiguos. La ilustración aportada se conserva como
referencia cualitativa y no valida madurez interna.

Cada ronda completa contiene 18 vistas focales (tres clases, tres luces y dos
materiales) y 32 contextuales (cuatro plantas, dos cámaras, cuatro bancos).
Las focales aplican una hipótesis de apariencia sobre el mismo ejemplar aislado;
su clase visible no reemplaza la fenología latente del árbol. Se admiten hasta
dos rondas completas. La primera prueba técnica adicional produjo dos imágenes,
conservadas como `smoke_01`, y no es un banco de entrenamiento.
La segunda ronda produjo 50 imágenes y se acompañó de cuatro comprobaciones
técnicas de pose foliar, separadas del factorial. Estas últimas mantienen la
cámara de la segunda ronda; sus máscaras cambian legítimamente por visibilidad.
No se mezclan con los cuatro bancos ni se usan como entrenamiento. Cada ronda
conserva sus propios `profiles.json`, `plants.json` y snapshot de fuentes.

La revisión de copa completó un diagnóstico estructural de ocho vistas:
cuatro `crown_v4_control` y cuatro `crown_v5_candidate`, con cámara, luz,
materiales y contexto fijos. No constituye una tercera ronda completa ni un
banco de entrenamiento. Los cambios de arquitectura pueden cambiar máscaras y
conteos; no se exige aquí la invariancia que corresponde a B/L/T/LT. El informe
de copa registra mayor extensión lateral y follaje, truncamiento superior en
tres cámaras conservadas y bases poco ramificadas en algunos ejemplares.
Persisten intersecciones cáliz–tallo, cáliz–cáliz y tallo–tallo; v5 no está
admitido físicamente. Falta la revisión humana antes de congelar el siguiente banco.

La aprobación humana debe identificar la galería y el hash exacto del perfil.
`review_lock.json` exige `approved=true`, `human_review="approved"`,
`profiles_file` y `profiles_sha256`. No debe generarse ese lock a partir de una
revisión automática. Cambiar los perfiles invalida la aprobación anterior.
La aprobación visual no exime la auditoría física ni las pruebas del banco.

## Banco común y matriz

| Banco | Luz | Materiales |
|---|---|---|
| B | Anterior | Anteriores |
| L | Candidata aprobada | Anteriores |
| T | Anterior | Candidatos aprobados |
| LT | Candidata aprobada | Candidatos aprobados |

B se renderiza sobre las mismas plantas corregidas. No reutiliza imágenes del
piloto histórico. El objetivo son 24 plantas nuevas en 12 escenas y como máximo
480 cámaras candidatas. Se seleccionan hasta 230 vistas comunes, estratificadas
por escena y orientadas a la distribución conjunta clase/tamaño del entrenamiento.
Las máscaras de candidatos se generan antes de los cuatro RGB seleccionados.
La maleza, tutorado y fondo deben conservarse dentro de cada comparación.

Se mantienen todas las instancias visibles válidas, incluidos fragmentos pequeños.
Los cuatro bancos comparten IDs, geometría, cámara, máscara, clases y etiquetas,
con hashes comprobados. Tamaño y densidad se reportan descriptivamente; no se
restauran los umbrales geométricos retirados por el usuario. Esto no autoriza
intersecciones físicas. Solo se habilitan dosis completas disponibles de 46,
115 y 230 vistas únicas, anidadas. No se duplican imágenes para simular diversidad.

Screening: 24 mezclas (cuatro bancos × tres dosis × dos recetas) y dos controles
reales nuevos; 2.000 actualizaciones, semilla 20261022, validación cada 500.
Por receta se elige la dosis del mejor L/T/LT por validación; desempate por dosis
menor y después L, T, LT. B no decide la dosis.

Confirmación: B/L/T/LT a esa dosis y real, por receta y tres semillas: 30 corridas.
La mejor variante nueva por media de validación de cada receta recibe tres
controles de repetición: seis más, total 36. Todas usan 4.000 actualizaciones desde
`yolo26n.pt`, semillas 20261022/23/24. La repetición conserva las ocho secuencias
de 1.000 posiciones y cada muestra real original; sustituye solo las sintéticas.

Resolución 960, batch y `nbs` 2, AdamW, LR inicial 0,0002, calendario lineal por
actualización efectiva hasta 0,01 del LR inicial. Clásica: reflejo horizontal 0,5
y variación de valor HSV 0,1; las demás transformaciones, incluidas las opcionales
de Albumentations, quedan desactivadas. Las decisiones se siembran por semilla,
época, posición y componente para emparejarlas entre variantes. Una actualización
omitida por AMP invalida el intento; no se cuenta como completada.

## Ejecución y recuperación

Comandos con el entorno existente, desde la raíz del repositorio:

```powershell
.venv-training/Scripts/python.exe scripts/prepare_appearance_pilot.py --root outputs/appearance_factorial_20261026 --stage references
.venv-training/Scripts/python.exe scripts/prepare_appearance_pilot.py --root outputs/appearance_factorial_20261026 --stage trees
.venv-training/Scripts/python.exe scripts/run_appearance_calibration.py --root outputs/appearance_factorial_20261026 --attempt round_01
.venv-training/Scripts/python.exe scripts/report_appearance_calibration.py --root outputs/appearance_factorial_20261026 --attempt round_01
```

Para la revisión posterior se prepararon árboles con `--round round_02` y galería
con `--attempt round_02 --previous round_01`. La comprobación separada usa
`--attempt round_02_leaf_pose_check --structure-only`, seguida de
`scripts/report_appearance_pose_check.py --root outputs/appearance_factorial_20261026`.
No volver a ejecutar una ronda existente con perfiles distintos.

Los pasos de preparación preservan evidencia existente y rechazan entradas
incompatibles. Los pasos siguientes requieren aprobación humana verificable y
escenas admitidas; no ejecutarlos mientras el estado sea revisión pendiente:

```powershell
.venv-training/Scripts/python.exe scripts/render_appearance_bank.py --root outputs/appearance_factorial_20261026 --blender "C:/Program Files/Blender Foundation/Blender 5.1/blender.exe"
.venv-training/Scripts/python.exe scripts/run_appearance_campaign.py prepare --root outputs/appearance_factorial_20261026
.venv-training/Scripts/python.exe scripts/run_appearance_campaign.py run --root outputs/appearance_factorial_20261026
```

Presupuesto: 48 horas activas; como máximo 12 para render y dos reservadas para
evaluar/cerrar. Windows `QueryUnbiasedInterruptTime` excluye suspensión; el ledger
solo cobra los trabajos en ejecución. Espera de recursos, desarrollo del código
y revisión humana no consumen entrenamiento. Un lock del sistema evita dos cargas
GPU de esta campaña; la inhibición temporal de suspensión dura solo durante el
trabajo. No hay cambios permanentes de energía. Los intentos y logs se conservan.
Se verifican PID/identidad, fuentes, configuración, paquetes, datos y pesos antes
de reutilizar corridas. Se priorizan bloques completos con clásica; no se comparan
parciales como presupuestos equivalentes.

## Evaluación y límites

Antes de abrir otra vez el test se congelan selección por validación, pesos y
controles. Se reportan AP macro/por clase/colapsado, precisión, recall, confusiones,
tamaño/densidad, exposición por imágenes e instancias, semillas, media, dispersión
y diferencias emparejadas. Contrastes: contra B, real de igual receta y repetición;
efectos L−B, T−B e interacción LT−L−T+B. El bootstrap usa sorteos comunes por grupo
condicionados a las tres clases; seis grupos desiguales, selección previa y test
consultado históricamente impiden llamarlo validación externa independiente.

Una subida macro con deterioro de Madura se presenta como intercambio. No se
promueve automáticamente ningún modelo. Las correcciones no demuestran mejora
del detector hasta completar el experimento. Gazebo dinámico, cosecha y Springy
permanecen fuera del alcance.

Si no queda ninguna dosis físicamente admitida, se conservan las auditorías y
se completan únicamente los controles reales originales mediante
`scripts/complete_appearance_real_controls.py`: dos screenings y seis finales,
con el mismo entrenador, inicialización, semillas y recetas. Se congelan los
seis controles antes del test de desarrollo; no se elige un ganador sintético
ni se calculan efectos factoriales/repeticiones inexistentes. El cierre debe
declarar el bloqueo de generación y sus resultados negativos.

## Corrección botánica de orientación del 27 de octubre

El banco 2.6 utiliza `trained_trellis_pendulous_audit_v7`: eje colgante del
capacho independiente del pedicelo axilar, declarado en el árbol y conservado
durante reparación. El cono 0–25° desde abajo (moda 8°) es una heurística de
ingeniería sin medición local. Se mantienen conteos, dimensiones y cámara;
Blender, proxies y adaptación interpretan la misma postura. Antes de admitir
una escena se auditan dirección final y conexión pedicelo–cáliz, además de
intersecciones y suelo. V6 y sus intentos quedan archivados, sin reutilizar RGB
como si fueran equivalentes. Véase el [registro de evidencia](../reports/revision_capachos_colgantes_2026-10-27.md).
El marco transversal de 2.5 evita pérdida de precisión cerca de la vertical;
no cambia el cono angular ni las tolerancias del auditor. El intento 2.4 se
preserva y excluye; no se considera una escena aceptada.
La versión 2.6 añade los proxies de pedicelos florales de esta política: una
flor sin cáliz inflado sigue teniendo conexión axilar. No se crean cálices ni
se omiten contactos medidos; la ruta histórica conserva su comportamiento.
