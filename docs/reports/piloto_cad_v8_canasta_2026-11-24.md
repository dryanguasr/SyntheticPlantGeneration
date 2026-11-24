# Verificación del piloto CAD V8 con canasta

El objetivo de entrega era una misión continua con nueve frutos depositados.
La toma de diagnóstico muestra el modelo CAD, el movimiento del robot y los
arbustos. El resultado de cosecha de esa toma es **0 de 9**.

## Evidencia reproducible

| Etapa | Resultado observado | Evidencia local en `outputs/real_harvester_validation/` |
|---|---|---|
| Integridad V8 | Pasó la verificación del manifiesto histórico, fuentes y poses. Se conservaron tres plantas con 1.027 capachos. | `cad_v8_demo_payload_video_package_01/manifest.json` |
| Preparación del robot | SDF validado. Las posiciones, dimensiones, masas y centros de masa de las adiciones son estimaciones. La caja blanca quedó entre los travesaños del bastidor, con 36,725 mm de separación del CAD de base. El diseño de carrera corta conserva las mallas externas y sustituye el mecanismo de una mordaza por una guía prismática accionada. | `cad_v8_demo_robot_internal_electronics_01/derivation.json`, `electronics_relocation_validation.json` |
| Guardas nativas aisladas | Pasaron las siete órdenes positivas y negativas auditadas, incluida una caída observada tras liberar el fruto del fixture. Alcance de banco ideal, separado del CAD y de la misión V8. | `jaw_guard_native_01_independent_audit.json` |
| Brazo y suspensión con carga | La muñeca alcanzó 0,322302 rad/s con límite de aceptación de 0,330. El retorno del brazo y la suspensión pasaron en ese banco. La mordaza alcanzó 12,768 mm/s con máximo admisible de 5,5 mm/s en la transición inicial de asentamiento. | `cad_payload_arm_jaw_02/result.json`, `cad_payload_arm_jaw_02_audit_02` |
| Diagnóstico de inicialización | Aumentar la amortiguación de la mordaza conservó el pico inicial. Inicializar el mismo robot en apoyo tangente con gravedad completa redujo el pico de la prueba corta a 0,892 mm/s. | `cad_payload_jaw_startup_01/result.json` y prueba corta con apoyo |
| Secuencia de brazo y mordaza | Con la primera colocación interna de la caja, la secuencia de 16 s pasó 27 de 27 comprobaciones en una auditoría independiente. Se separó el movimiento de la mordaza del brazo, con las mismas ganancias y límites. El máximo de giro de muñeca en las colas de asentamiento fue de 0,007706 rad/s frente a 0,010. | `cad_payload_arm_jaw_sequential_01_audit_01/result.json` |
| Movilidad de la primera caja interna | La base avanzó 193,576 mm, giró 0,317795 rad y se detuvo dentro de las tolerancias. Fueron 17 de 17 comprobaciones para esa revisión, anterior a los herrajes añadidos. | `cad_payload_mobility_supported_01/result.json` |
| Inferencia RGB | ONNX móvil, segmentación del ciclo 3 y segmentación multiescala obtuvieron 0 de 6 coincidencias a confianza 0,25 e IoU 0,5. La máscara nativa sí confirmó las seis observaciones en tres vistas. El alcance es el conjunto de captura con los objetivos históricos. | `harvest_rgb_tournament_report_01/summary.json` |
| Toma parcial | 81 cuadros RGB nativos, 1.280 × 720, 10 fps, 8,1 s. El MP4 con rótulo conserva la toma y muestra el contador real. La revisión filmada precede al cambio de colocación de la caja de electrónica. | `cad_v8_demo_payload_video_01/piloto_v8_previa_parcial.mp4`, `result.json` |
| Montaje de accesorios | La caja se retrasó 50 mm y mantiene 5 mm de separación respecto de las baterías. Caja y canasta se apoyan sobre rieles, separadores y abrazaderas en los travesaños CAD 119 y 117. Se contrastaron las caras de contacto en q0. El soporte añade 216,2 g estimados. La masa total simulada es de 21,1661 kg. | `cad_v8_demo_robot_supported_payloads_01/derivation.json`, `support_geometry_validation.json`, `payload_mates_validation.json` |
| Primer plano final | 31 cuadros RGB nativos en el perfil con fijaciones, a 1.280 × 720 y 10 fps. El montaje de presentación dura 7,9 s e incluye tres capturas congeladas y rotuladas de detección simulada de un diagnóstico separado. | `cad_v8_demo_mounted_video_01/native_mission.mp4`, `piloto_v8_previa_con_fijaciones.mp4`, `presentation.json` |
| Brazo y mordaza con fijaciones | La repetición secuencial de 16 s pasó las 27 comprobaciones del banco nativo con el perfil final y su auditoría independiente. La muñeca de inclinación alcanzó 0,320674 rad/s frente a 0,330. La mordaza alcanzó 5,209 mm/s frente a 5,5. | `cad_payload_arm_jaw_supported_final_01/result.json`, `cad_payload_arm_jaw_supported_final_01_audit_01/result.json` |

## Admisión geométrica

La criba del capacho completo mejoró al sustituir su esfera histórica por la
superficie cerrada en su pose V8 original. La evaluación de herramienta sola
obtuvo candidatos para tres, cuatro y dos frutos de los tres arbustos. La
evaluación de robot completo conserva el margen de 4 mm y un margen articular
de 0,025 rad. En la pasada completa con la primera caja interna se evaluaron
19 posturas de corte. Las 19 fallaron, 16 por tallos o pedicelos y tres por
capachos vecinos. El primer incumplimiento registrado más cercano al umbral
tuvo 3,9393 mm de separación. La repetición con ambas fijaciones volvió a
descartar las 19 posturas. El ciclo de un fruto y la misión de nueve quedaron
**NO EJECUTADOS**. El muestreo no agota todas las configuraciones posibles.

El replay del prisma nativo confirmó una intersección con la cuchilla del
objetivo `plant_000:axis_0_0_branch_2_branch_2_node_4_reproductive_unit`. La
variante con tramo terminal idealizado verifica el resto del tallo como
colisión rígida y comprueba el tramo virtual contra las demás superficies del
robot. En el diagnóstico de siete posiciones a lo largo del filo, todos los
casos mantuvieron 4 mm de holgura del capacho y del pedicelo proximal, pero los
soportes y la tapa quedaron por debajo de ese margen respecto al terminal.
También se registraron cruces triangulares con los eslabones L104/L106.
Otros candidatos del robot completo presentan interferencias con geometría V8
vecina. Esas comprobaciones son acotadas a los candidatos muestreados.

Evidencia geométrica en `cad_v8_demo_tool_screen_exact_baseline_01.json`,
`target_pedicel_contact_zone_diagnostic_02/result.json`,
`target_blade_site_screen_01/result.json` y
`target_blade_site_witness_01/witnesses.json`. La criba integral está en
`cad_v8_demo_candidates_06/selection.json`; la repetición con fijaciones está
en `cad_v8_demo_candidates_mounted_01/selection.json`.

## Demostración con contacto selectivo de la pinza

Se activó una excepción de contacto de los dedos CAD 104 y 106, las cuchillas
109 y 110 y las gomas 113 y 114 frente al cultivo. El perfil mantiene los
soportes, la carcasa, la muñeca, las poses V8 y el umbral de 4 mm. Las máscaras
de la escena se contrastaron con 4.186 parejas internas del robot. En una
prueba aislada con Gazebo y DART, una esfera de cultivo atravesó el dedo, el
soporte detuvo otra esfera de cultivo y un objeto ordinario conservó contacto
con el dedo. La prueba usa las máscaras emitidas sobre cuerpos de ensayo.
Evidencia en `finger_blade_crop_native_probe_02/result.json`.

Se evaluaron 115 posturas de corte para nueve candidatos V8 con la excepción
activa. Una resta con coma flotante generó siete rechazos aparentes justo en
el límite. Se corrigió la consulta acotada y se repitieron esas siete posturas
con los mismos 4 mm. Las siete incumplieron el margen por contactos de muñeca
o carcasa con ramas y capachos vecinos. Una comprobación independiente de una
de esas posturas encontró 3,280 mm entre la carcasa y el prisma nativo y una
intersección del chasis con el cultivo en la misma parada con el brazo recogido.
Ninguna de las 115 posturas pasó a ejecución de cosecha. Evidencia en
`cad_v8_demo_candidates_finger_blade_02/selection.json`,
`cad_v8_near_clearance_routes_02.json` y `cad_v8_full_body_approach_03/result.json`.

El montaje `rejected_approach_static_video_01/diagnostico_posturas_sin_corte.mp4`
contiene 93 cuadros de cámaras nativas en 9,3 s. Las dos posturas históricas
son fijas y están rotuladas con el contacto de los dedos omitido en la revisión
y el bloqueo de la muñeca. Se conservó el resultado de **0 de 9 frutos**. Los
dos procesos de captura terminaron con código −11 después del último cuadro.
El MP4 completo se decodificó y los resultados de los procesos permanecen en
`rejected_approach_static_video_01/video_evidence.json`.

## Muñeca y carcasa en la demostración

La variante ampliada omite 19 geometrías frente al cultivo. Se incluyeron los
dos conjuntos de muñeca y carcasa y las piezas CAD 111 y 112 «Mordaza blanda»
como componentes de los dedos. Los 4 mm para las demás piezas, las parejas de
autocontacto y las poses V8 se conservaron. Gazebo reprodujo el filtro de la
carcasa frente a la máscara del cultivo y mantuvo el contacto con la máscara
del antebrazo en cuerpos de prueba. Véase `wrist_crop_native_probe_01/result.json`.

Con la política ampliada, cuatro frutos del primer arbusto, nueve del segundo y
cuatro del tercero tienen al menos una posición estática admitida para el corte.
Las posturas consolidadas están en `cad_v8_wrist_admitted_cut_01.json`. Las
primeras rutas de prueba encontraron interferencias del fruto sostenido con
tallos vecinos en la retirada y, en otro candidato, una transferencia sin
trayectoria admitida hasta la canasta. Estos resultados se refieren a los
recorridos muestreados y conservan sus parejas e identidades V8.

El refinamiento por superficie resuelve algunos rechazos de la esfera
envolvente. En una retirada del arbusto central, la envolvente daba 1,676 mm
entre el fruto retenido y un vecino. El cáliz cerrado original dio 5,258 mm con
el mismo umbral de 4 mm. Véase `held_calyx_lazy_pair_001_01/result.json`.

La primera prueba dinámica se inició con el chasis estacionado frente al
segundo arbusto. Gazebo alcanzó 1,8513 s simulados y el estado del fruto seguía
siendo `ATTACHED` cuando se agotó la espera de asentamiento en tiempo real.
Se preservaron la telemetría y los 19 cuadros RGB en
`cad_v8_stationary_trial_native_01/`.
Un segundo intento con la GPU mantuvo el paso de 0,1 ms y perdió telemetría
antes del corte. El ensayo aislado con paso de 0,5 ms conservó fuerzas,
límites de movimiento y guardas de corte. El plan de ese fruto del segundo
arbusto pasó la comprobación densa de aproximación, retirada con fruto y
trayectoria hasta la apertura de la pinza sobre la canasta. Véanse
`cad_v8_stationary_trial_exact_waypoints_refined_01.json` y
`cad_v8_stationary_trial_exact_held_refined_01.json`. Ambas comprobaciones
usan la geometría V8 original y conservan los 4 mm.

Gazebo confirmó corte y retención de ese fruto en el ensayo de 0,5 ms. Una
inversión de muñeca durante la prueba negativa alcanzó **0,334616 rad/s**
frente al límite de **0,330 rad/s**. El banco aislado con referencia de pitch
reducida y paso de 0,5 ms alcanzó 0,407703 rad/s. El banco con los controles
originales y paso de 0,2 ms alcanzó 0,342333 rad/s. Los dos bancos quedan
registrados como `FAIL` en `cad_v8_wrist_pitch_rate_probe_01/` y
`cad_v8_wrist_integrator_probe_02/`.

El resultado de corte llegó a 25,821 s simulados y el de liberación a 57,860 s.
La malla del capacho permaneció estable dentro del volumen de la canasta
durante los últimos 3,5 s observados. El ensayo aislado confirmó **un fruto
depositado**, con el chasis estacionado. El tiempo de ejecución se agotó
durante la recogida del brazo. La toma nativa contiene 635 cuadros. La
telemetría, el MP4 original y
la verificación independiente están en `cad_v8_stationary_trial_native_step_01/`.

El paquete `cad_v8_wrist_field_candidate_09/` reúne los nueve frutos fijados,
tres por arbusto. Sus trayectorias de brazo y los enlaces de chasis se
contrastaron geométricamente y el comprobador nativo de SDF aceptó el mundo.
El manifiesto conserva el filtro de 19 geometrías, los hashes de las pruebas
de cada arbusto y sus posiciones V8 originales. La misión dinámica de nueve
permaneció pendiente de admisión con carga y de velocidad de muñeca.

Las dos ediciones de `admitted_cut_static_video_01/` muestran tres de las posturas
en los mismos 93 cuadros RGB nativos. La edición anotada marca veinte
intersecciones geométricas de las piezas exentas. Se conservaron los 31 cuadros
de cada captura pese al código de salida −11 de Gazebo al terminar. Los dos
MP4 se verificaron por decodificación y se rotularon con **0 de 9 cosechas**.

## Reproducción

La [guía de operación](../guides/piloto_cad_v8_canasta.md) reúne los pasos de
preparación, la criba, los ensayos y el auditor. El control y los contactos
registrados son resultados de simulación. El montaje, la masa de la carga y
el funcionamiento de la pinza física requieren evidencia del prototipo.

## Toma continua con depósitos bajos

La toma usa los tres V8 inmóviles y comienza con el carro a 1,78 m del
primer arbusto y a 0,91 m de su primera parada. El primer capacho está a
0,474 m del suelo.
El movimiento guiado sigue cinco fases por fruto. El corte conserva sus
guardas nativas y los objetivos se preseleccionan por identificador V8. Los
desplazamientos entre paradas de un mismo arbusto bajaron en conjunto de
11,47 m a 2,06 m respecto a las salidas repetidas al pasillo.

Gazebo aceptó los nueve cortes y liberaciones. Se observaron los nueve
capachos completos dentro de la canasta al final del desplazamiento,
**3 + 3 + 3** a 561,992 s de simulación. Las poses nativas anteriores a
cada liberación dieron una separación de 104,2–109,5 mm entre la parte
inferior del capacho y el fondo. La velocidad del capacho con respecto a
la canasta fue cero a la precisión observada en esas muestras. La
caída por gravedad y los contactos entre frutos y canasta se simularon.

Se omitió la respuesta de contacto en el brazo, el chasis y las mallas
estáticas del cultivo, con la canasta activa. El barrido registró
intersecciones geométricas del brazo. También hubo un contacto nativo
entre capachos durante el transporte a t226,464 s. En esa muestra el
simulador registró 0,416 rad/s de pitch y 0,588 rad/s de roll. Las velocidades
de muñeca estimadas por diferencia de posiciones en muestras de 52 ms
se mantuvieron cerca de la referencia de 0,30 rad/s. La toma verifica el
resultado de cosecha con movimiento prescrito y deja la admisión por
fuerzas pendiente.

El paquete está en `cad_v8_continuous_take_package_02/`, con la ruta de
entrada en `cad_v8_simple_native_candidate_shortbase_01.json`. Los eventos,
la telemetría y el RGB de origen están en `cad_v8_continuous_take_native_01/`.
La edición con contador y la compacta están en
`cad_v8_continuous_take_editions_01/`. Ambas incluyen 6.745 fotogramas
en el mismo orden y se verificaron por decodificación completa. Duran
562,083 s y 265,548 s, respectivamente. Se conservaron estos archivos
locales fuera de Git. La regresión de cosecha en WSL pasó 100 pruebas.

## Repetición con codo arriba

Se conservaron los nueve identificadores y las poses, visuales y materiales de
los tres arbustos V8. Se eligieron otras posturas de corte y se usó el codo
arriba desde la marcha inicial hasta la salida final. La pinza baja hacia la
abertura de la canasta desde una posición elevada, libera el capacho y se
retira por encima del borde.

El barrido continuo cubre los 183 intervalos de la trayectoria, incluidos
los cierres y aperturas de mordaza. La cota inferior de holgura es de 4 mm
entre los 1.586 pares brazo–carro y en los pares internos de brazo incluidos
en la comprobación. Los cuerpos y exclusiones se tomaron del CAD nominal.
Se certificaron por separado las 38 maniobras de chasis frente a tallos bajos
V8 con una cota mínima de 6,85 mm.

El diagnóstico de los recorridos inmediatamente posteriores al corte
observó doce muestras de proximidad entre el capacho retenido y tallos
vecinos. Esas muestras corresponden al cultivo de la toma. El perfil mantiene
el movimiento guiado y la gravedad y los contactos de los frutos liberados.

El paquete certificado está en `cad_v8_elbow_up_full_package_01/` y la
ruta de entrada en `cad_v8_elbow_up_take_routes_shortbase_01.json`.
La corrida independiente está en `cad_v8_elbow_up_native_01/`.
Gazebo aceptó los nueve cortes y las nueve sueltas. La auditoría confirmó
**tres frutos de cada arbusto dentro de la canasta** tras el desplazamiento
final a 501,236 s. Las sueltas se observaron desde reposo, con 77,6–84,8 mm
entre el capacho y el fondo. Las velocidades máximas observadas de muñeca
fueron 0,300 rad/s en pitch y 0,209 rad/s en roll.

La auditoría nativa contrastó 9.640 muestras de 0,004 a 501,232 s. Certificó
4 mm de holgura y un margen de codo arriba de al menos 0,236 rad en todas
ellas. El intervalo máximo entre muestras fue de 0,052 s. La evidencia
queda en `native_arm_clearance.json` y `native_harvest_evidence.json`.

Los vídeos `cosecha_v8.mp4` y `cosecha_v8_compacta.mp4` conservan los
6.016 fotogramas de la toma y duran 501,333 s y 290,683 s. Las dos ediciones
pasaron decodificación completa. La regresión del subsistema de robot
en WSL pasó 117 pruebas.
