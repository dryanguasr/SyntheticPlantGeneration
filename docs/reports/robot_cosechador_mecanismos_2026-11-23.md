# Cosechador CAD: mecanismos e interferencias

## Estado de esta continuación

El perfil articulado de referencia 09 conserva las 239 piezas físicas y los
18,2498786605 kg calculados por el CAD. Las revisiones locales posteriores
recalculan explícitamente la masa de la pieza modificada y la inercia de su
conjunto rígido. La masa no procede de una pesada del prototipo. Los
ensayos históricos siguen conservados; sus PASS no validan el nuevo modelo.
La misión de tres objetivos V8 y su vídeo permanecen **NO EJECUTADOS** mientras
fallen las pruebas del mecanismo completo. No se han movido plantas, frutos ni
ramas, ni ampliado las tolerancias de aceptación.

## Interferencia que requiere revisión del diseño

Inventor evaluó los sólidos de `Gripper y engranaje:1` y `Eslabon L:1` del
ensamblaje `gripper/Gripper ensamble.iam`. La postura cero es la guardada en
el CAD. Las demás posturas siguen la rama cinemática continua del mecanismo
de cuatro barras reconstruido a partir de sus pivotes; se aplican a copias
temporales sin modificar los documentos o restricciones originales.

El ángulo de la tabla corresponde al incremento del engranaje conductor de
la pinza, **no** al ángulo absoluto de la mordaza ni a una articulación del
brazo. Los dos engranajes giran en sentidos opuestos.

| Incremento conductor | Separación mínima CAD | Volumen común CAD |
|---|---:|---:|
| 0 rad / 0° | 1,804884 mm | 0 mm³ |
| 0,04 rad / 2,2918° | 0,744487 mm | 0 mm³ |
| 0,065 rad / 3,7242° | 0,107660 mm | 0 mm³ |
| 0,070 rad / 4,0107° | 0 mm | 0,018335 mm³ |
| 0,100 rad / 5,7296° | 0 mm | 6,617663 mm³ |

4,0107° es la **primera muestra positiva del barrido**, no una estimación
exacta del instante inicial de contacto. El intervalo anterior acota la
transición entre 3,7242° y 4,0107°. El volumen común positivo es una
interferencia de sólidos, independiente de la proyección o la oclusión visual.
Estos datos no demuestran cómo se deformaría una pieza fabricada.

Evidencia local privada, excluida de Git:

- `outputs/real_harvester_validation/gripper_native_interference_01/result.json`:
  cinco pares de sólidos en postura cero, sin interferencia.
- `outputs/real_harvester_validation/gripper_native_envelope_01/result.json`:
  21 posturas, 105 pares inspeccionados y hashes de los originales inalterados.
- `outputs/real_harvester_validation/gripper_brep_motion_010.json`:
  transformaciones rígidas que reproducen cada postura del barrido.
- `outputs/real_harvester_validation/gripper_collision_geometry_01/result.json`:
  extracción adicional de las dos piezas y del cuerpo común nativo en 0,
  0,07 y 0,10 rad, con teselación de 1 µm para las figuras. Se verificaron
  inalterados los hashes de 162 documentos originales. A 0,10 rad, el
  centroide del volumen común está en `[27,11138; 2,00116; 0,11093]` mm,
  expresado en el marco local del ensamblaje de la pinza.

El usuario solicitó imágenes para determinar el arreglo. Cualquier cambio
posterior de forma, montaje o flexibilidad deberá quedar como revisión
explícita. No se ha excluido del cálculo la pareja que se interpenetra.

La sección comparativa está en
`outputs/real_harvester_validation/gripper_collision_section_02/seccion_comparativa.png`
y en SVG en el mismo directorio. La sección es el plano Y = 2 mm del marco
CAD, con idéntico encuadre X/Z y escala en ambas posturas. El rojo procede del
cuerpo de intersección calculado por Inventor, no de una estimación visual.
Se observa el borde de la orejeta del eslabón alrededor del pasador entrando
en la pared inclinada de la carcasa. `section_geometry.json` conserva los
contornos, las fuentes y sus hashes; el script reproducible es
`scripts/render_cad_interference_section.py`.

## Resultados independientes ya observados

| Ensayo | Estado | Alcance |
|---|---|---|
| `fk_cad_control_01` | PASS, 11/11 | Revisión de control del brazo con mecanismos congelados; no valida el robot articulado completo. |
| `native_loops_01` | PASS | Cierres nativos de suspensión y pinza; controles con cierre desconectado fallan como se esperaba. |
| `gripper_gears_rotated_pgs_01` | PASS | Banco de engranajes rotado con PGS; error máximo 0,000115151 rad frente a 0,001 rad. |
| `dynamic_concave_mesh_04` | PASS, 9/9 | Contactos dinámicos en cavidades cóncavas con esfera y malla, también rotadas. |
| `mesh_collision_masks_01` | PASS, 6/6 | Parejas excluidas, requeridas y externas entre mallas/primitivas; tolerancia original de 5 mm. |
| `cad_gripper_contact_02` | FAIL | No alcanzó la apertura solicitada de 0,04 rad; velocidad nativa máxima 1,48444 rad/s. |
| `video_preflight_01` | PASS técnico | 32 imágenes RGB nativas codificadas y decodificadas; inspección estática, sin cosecha. |

En `cad_gripper_contact_02` los cierres y la relación de engranajes quedaron
dentro de sus umbrales, pero la pinza no abrió. Los sensores de las gomas no
observaron contactos; no llegó a crearse el testigo de pedicelo ni a ejecutarse
ARM/CUT o retención. No se atribuye este atasco a la interferencia de 4,01°:
el comando de ese banco era menor y el ángulo observado apenas avanzó. Falta
identificar las parejas internas involucradas en el atasco dinámico. Esa
identificación se completó después en los ensayos causales descritos abajo.

La representación de colisiones conserva la concavidad del CAD. La revisión
de orientación y cierre de mallas admite 87/87 activos de colisión en
`collision_asset_admission_06.json`. Las reparaciones derivadas están
identificadas por hash; las mallas visuales y los CAD originales se conservan.
El único ajuste de coordenadas es una normalización explícita de costura de
hasta 5 nm en una malla de colisión; no es una modificación del diseño.

## Reproducción y límites

La guía [Mecanismos cerrados CAD en Gazebo](../guides/mecanismos_cerrados_cad_gazebo.md)
describe los bancos, la observación nativa y los fallos conservados. El archivo
`configs/robots/cad_v8_acceptance_lock.json` mantiene las fuentes, identidades y
criterios de aceptación de V8. El grabador nativo preparado no transforma un
ensayo estático en un vídeo de misión.

La integración completa aún requiere estabilidad, apertura útil, límites
articulares, contactos y seguimiento observados en el mismo paquete físico;
después, planificación viable sin modificar los objetivos, ciclo individual
y misión. Los avances de bancos aislados no permiten omitir esas etapas.

Durante la preparación de las figuras pasaron 72 pruebas `test_robot*.py`,
97 pruebas `test_harvest*.py` y 11 pruebas de mecanismos, cierres y refinamiento
de colisiones. El validador del contexto informó 158 nodos y 267 relaciones
válidos. `v8_invariance_02.json` verificó los seis hashes del cultivo, los tres
objetivos, sus poses y el manifiesto congelado. Son comprobaciones de software
e integridad y no sustituyen las pruebas físicas pendientes.

## Continuación con la carrera corta del prototipo

La fotografía y la declaración del usuario se registran en
[observaciones del prototipo](../references/real_harvester_prototype_observations_2026-11-23.json).
Los **8 mm rígidos y 6 mm flexibles son aproximados**; no se convierten en
mediciones calibradas ni en una relación entre consigna del servo y ángulo.
En el CAD, q = 0,084810927651 rad da 8,390804 mm entre L1/L2 y 6,006657 mm
entre gomas. Los portagomas y las cuchillas son otras parejas de superficies.

La copia `clearance_revision_03` modifica únicamente L1. Conserva el agujero,
los ejes, las poses, L2 y los 162 archivos originales. Retira 4,516497 mm³
(5,555291 mg según la densidad CAD), sin validación de resistencia. El
integrador `apply_cad_part_revision.py` verifica el agregado de inercia previo
y sustituye únicamente la geometría 104 y la inercia de su mordaza. Las
88 mallas resultantes pasan la admisión geométrica; esto no valida la física.

El barrido revisado contiene 90 posturas y 900 evaluaciones BRep, sin
intersecciones volumétricas. La pareja carcasa/L1 tiene una separación mínima
de 0,127712 mm y cota continua nominal de 0,081971 mm: **no cumple la reserva
de diseño de 0,200 mm**. Se conserva ese fallo; originó un ajuste local
adicional, manteniendo el ligamento mínimo de 1,900 mm al agujero. Las dos
parejas tapa/L permanecen tangentes; cero distancia no prueba solapamiento ni
cumplimiento de un margen. Ninguna de estas cifras constituye PASS de los
4 mm operativos ni autoriza excluir enlaces completos de las colisiones.

## Diagnóstico nativo de contactos, control y giro

ODE genera contactos tapa/L desde q = 0, aunque Inventor no encuentra volumen
común: máximos de 1,1468 mm y fuerzas de hasta 2370,6 N por observación de
contacto. Los mensajes repetidos por sensores no se suman como fuerza neta.
FCL también falla en el mecanismo; sus mensajes iniciales de construcción no
demuestran ausencia de mallas, porque Gazebo usa después `AttachMeshShape`.
Bullet pasó nueve controles de concavidad y seis de máscaras/contacto; esto
admite ensayar ese detector, no transfiere PASS al robot completo.

El nuevo controlador por esfuerzo limita la referencia en cada paso físico
y deriva la velocidad medida. Conserva un único escritor `JointForceCmd` y
publica esfuerzo solicitado/limitado, saturación, rechazo de órdenes y máximos
por ventana. La auditoría contrasta el esfuerzo con el observador independiente
del mismo paso, sin emparejar por tiempo aproximado. Un estado inicial aún
no disponible se registra explícitamente y nunca cuenta como cobertura lista.

La observación a 10 kHz detectó una oscilación alternante de 5 kHz incluso
con consigna cero. El análisis de inercias y la prueba causal justifican probar
amortiguación del engranaje de 0,012 en lugar de 0,030 N·m·s/rad, manteniendo
K = 100 N·m/rad, los PID, 100 µs de integración y todos los límites. En el
banco `cad_gripper_bullet_ramped_c012_01` de 1,2 s, el conductor alcanza
0,039915 rad, el máximo articular es 0,567553 rad/s y el error de engranajes
1,975·10⁻⁶ rad. Sigue siendo un banco parcial, anterior a la carrera de 6 mm
y al candidato integrado definitivo.

El protocolo completo `cad_mobility_mesh_repaired_09` conserva FAIL: avanza
0,193424 m, pero gira sólo 2,231·10⁻⁶ rad y presenta velocidades excesivas
en la pinza. El ensayo aislado con límite estimado de 6,5 N·m gira 0,209822
rad, todavía por debajo de 0,250 rad. La revisión PI 04 se deriva de las
cargas desiguales observadas en las ruedas y sigue pendiente de prueba en
el candidato común. La capacidad de 6,5 N·m es una hipótesis de simulación,
no un par continuo demostrado del motor instalado.

Los registros antiguos no se sobrescriben. Los nuevos protocolos conservan
el código de salida nativo antes de cualquier posprocesado y recogen un paso
adicional de observación para emparejar la pose final con su respuesta física;
no prolongan las fases de movimiento ni cambian los umbrales. La misión V8
y el vídeo de cosecha permanecen **NO EJECUTADOS** hasta superar estas etapas.

## Corrección CAD final y nueva evidencia de rango

`clearance_revision_05` cumple los criterios geométricos previamente fijados:
150 posturas, 1.500 evaluaciones BRep sin volumen común; separación mínima
observada de 0,205000 mm y cota continua de **0,202874988 mm ≥ 0,200 mm**.
Retira 4,950059592 mm³ de L1 y mantiene un ligamento geométrico de
**1,905 mm ≥ 1,900 mm**. La masa agregada cambia en −6,088573 mg según el
material CAD. Originales, L2, agujeros, montajes y ejes permanecen intactos.

El análisis de puntos más próximos identificó una arista frontal que no
quedaba cubierta por el primer plano de corte. La revisión final usa dos
biseles locales y conserva los intentos anteriores. La prueba de las dos
interfaces tangentes usa `SurfaceBody.PreciseRangeBox`: `RangeBox` aproximada
no bastaba para demostrar los semiespacios. Las caras comparten el plano
Y = 3,500 mm y la cinemática nominal conserva ese plano; se certifica ausencia
de volumen común, nunca una separación positiva ni una exclusión de contacto.

Evidencia: `gripper_revised_operating_envelope_03/operating_envelope_admission.json`
(SHA256 `4cba28a57b41e1178f2009bd1b6109fcbbfc2f2a6e70700c12ad2657813aac1f`)
y `gripper_correction_section_02/seccion_comparativa.png`, bajo
`outputs/real_harvester_validation/`. El PASS es **sólo de geometría nominal
CAD**; no demuestra resistencia, funcionamiento del prototipo ni cosecha.

Después del análisis de alcance con ±15°, el usuario indicó «Tentativamente,
todos 180° aprox» para las cinco articulaciones del brazo. Se registra como
recorrido total aproximado; −90° a +90° respecto a la postura CAD es un
**centrado provisional**, no una calibración. La revisión explícita conserva
las tolerancias, las plantas y la carrera corta de la pinza. La búsqueda con
ese nuevo rango encontró posturas de posición/dirección para los tres objetivos;
eso no aprueba su margen, sus colisiones, su trayectoria ni el seguimiento.

## Primer ensayo integrado de giro

`cad_turn_integrated_01` conserva el protocolo de 6 s y todos sus umbrales.
La ejecución terminó por el presupuesto de 900 s reales, con sólo 2,75 s
simulados. El proceso respondió al cierre con código 0, pero el registro
`native_timeout` impide tratarlo como finalización normal. La auditoría
independiente conserva **FAIL** por cobertura incompleta: sólo se observaron
0,067184 rad de giro y no se alcanzó la fase de parada.

Hay además un fallo físico independiente de ese tiempo insuficiente: en la
ventana (0,0101; 0,0201] s, el eslabón corto derecho de la pinza alcanzó
**1,538579 rad/s**, por encima de 1 rad/s más la tolerancia original de
0,03 rad/s. El banco aislado no había mostrado ese pico. Se investiga su
relación con el asentamiento inicial de 2 mm; la coincidencia temporal por
sí sola no prueba la causa. No se modifica la altura inicial ni el límite
para ocultarlo. Los cierres y engranajes conservan errores pequeños en el
tramo observado, pero esa cobertura no basta para aprobar el protocolo entero.

La primera entrega de código y documentación quedó en el commit local
`e97ff56`, sin push, PR ni merge. Los CAD, vídeos y registros
grandes siguen fuera de Git.

## Contacto físico de las mordazas

La auditoría independiente corrigió una interpretación incorrecta del primer
banco `cad_gripper_final_contact_01`: los mensajes de Bullet incluyen puntos
del manifold con profundidad negativa, todavía separados. Recibir un mensaje
del sensor no demuestra contacto físico. Se conservan el resultado y los
datos originales; el auditor exige ahora profundidad finita no negativa y
la pareja exacta goma/pedicelo antes de permitir ARM. La fuente temporal es
la del contacto nativo, no la llegada del último mensaje de articulaciones.

El segundo banco, `cad_gripper_final_contact_02`, terminó normalmente a
3,5001 s y conserva **FAIL**. Abrió aproximadamente 5,996 mm; pasó el control
por esfuerzo en el ámbito explícito de la pinza y no superó su límite de
velocidad (máximo 0,563724 rad/s). La goma derecha registró 21.988 puntos
no separados; la izquierda ninguno de 38.103, con separación mínima
reportada de 55,666 µm y wrench nulo. La guarda impidió ARM y CUT: la retención
ideal no se ejecutó en esta repetición. El banco aislado no cubre los
controladores del brazo ni admite el robot completo.

El contraste de estas observaciones con las superficies CAD sigue pendiente
de resolver. No se atribuye todavía el fallo a falta de fuerza, al prototipo
ni a un descentrado; no se desplaza el testigo ni se modifica la fricción
para obtener contacto.

## Agrupación de colisiones y rendimiento

`cad_grouped_collision_candidate_01` concatena superficies pertenecientes al
mismo conjunto rígido: 231 colisionadores pasan a 40. Conserva todos los
264.902 triángulos, las 239 piezas visuales, las masas e inercias, los marcos,
las máscaras y los controles. Las 18 mallas de pinza/muñeca protegidas y los
cuatro neumáticos no se agrupan. El manifiesto conserva la correspondencia
entre piezas, caras y fuentes; no hay simplificación geométrica.

El banco `cad_collision_grouping_benchmark_01` ejecutó ambos modelos durante
0,1 s simulados con los mismos 100 µs por paso. En el intervalo común de
observación, la agrupación aceleró el cálculo físico 23,37 veces; incluyendo
carga, el tiempo total pasó de 32,021 a 5,135 s. El pico del eslabón corto
derecho persiste: 1,543543 frente a 1,543424 rad/s. La representación agrupada
requiere nuevas pruebas físicas: conservar las superficies no demuestra que
el algoritmo de contacto distribuya exactamente igual sus fuerzas.

La prueba causal `cad_startup_wheel_feedback_causal_01` anuló únicamente las
ganancias del control de ruedas, sin tocar geometría, altura ni criterios.
El pico aumentó a 1,732429 rad/s; las ruedas sí registraron esfuerzo cero.
Por tanto, estos datos **no respaldan** retirar el frenado inicial como
corrección. El modelo productivo conserva las ganancias anteriores.

El protocolo integrado `cad_mobility_grouped_01` alcanzó 12,09 de sus 15 s
simulados antes del presupuesto de 600,122 s reales. Conserva **FAIL** por
timeout y por el pico inicial de la pinza. En las fases completas observó
0,193629 m de avance, 0,004758 rad de error máximo del brazo en reposo y
0,000113 m/s de velocidad residual tras la primera parada, dentro de sus
criterios originales. El giro acumuló 0,136371 rad en un tramo incompleto;
la parada final quedó **NO OBSERVADA**. No se extrapola ese giro a un PASS
ni se transfiere la validación aislada a la misión.

## Alcance y limitación del diagnóstico estático

`cad_v8_grouped180_reach_01` repite la búsqueda de posición y dirección con
la geometría final y los recorridos aproximados: encuentra candidatos para
los tres identificadores V8 originales. La búsqueda no certifica los topes
físicos, la trayectoria, el seguimiento ni las colisiones.

El barrido `cad_v8_grouped180_static_01` se interrumpió explícitamente y
conserva protocolo y diagnóstico de interrupción. Todos sus candidatos
usaban la misma postura nominal q = 0 de la pinza. El mínimo agregado de
autocolisión y entorno no puede superar 4 mm cuando incluye las interfaces
tapa/L, tangentes por diseño. Repetir más posturas del brazo no resuelve
esa limitación del contrato de admisión. Las intersecciones externas
observadas en los candidatos anteriores siguen siendo fallos, pero no una
prueba de inviabilidad global de los objetivos. Se necesita auditar las
interfaces mecánicas internas por pareja y dominio de movimiento; no se
han añadido exclusiones ni reducido el margen operativo de 4 mm.

## Corrección de la observación y diagnóstico del impulso

La adquisición por paso de `cad_startup_timestep_causal_01` detectó un error
en la auditoría previa: la pose nativa debe emparejarse con
`measured_after_step_time`, no con el instante previo del comando. El contraste
FK/pose da 0,280 µm RMS con el reloj correcto y 6,494 µm con el anterior.
Las publicaciones antiguas de 100 Hz están desfasadas un paso, por lo que
no permiten afirmar cobertura conjunta exacta de pose y articulaciones.
Los PASS históricos de esa cobertura quedan invalidados y se conservan;
los máximos nativos de velocidad y esfuerzo permanecen como evidencia separada.

El observador nuevo publica `robot-telemetry/1.1`, con su contrato temporal
explícito y una rejilla común de tiempo de simulación. El controlador publica
su esfuerzo previo en las mismas iteraciones. La auditoría exige igualdad
exacta; los registros 1.0 necesitan un adaptador explícito vinculado a su
fuente, sin reinterpretación automática ni emparejamiento por proximidad.
La compilación local v8 pasa las dos pruebas C++ de control y calendario.
Esto corrige la observación, no los fallos físicos de los ensayos anteriores.

Reducir el paso de 100 a 50 µs no elimina el pico: el eslabón derecho pasa
de 1,543424 a 1,520341 rad/s, ambos por encima de 1,03 rad/s. Los ocho picos
convergen dentro del 2 % preregistrado; no se activa la prueba condicional
de 25 µs. Durante el impulso, ambos engranajes giran en el mismo sentido,
contra la relación ideal −1. La transmisión elástica por esfuerzos limita
el error de posición, pero permite ese modo de velocidad impulsivo. Una
proyección inercial atribuye aproximadamente el 98 % de la energía reducida
a ese modo; es un análisis, no una corrección nativa ni un PASS.

La vía siguiente es comprobar una restricción recíproca de engranajes con
el backend instalado que la admite. Un motor que persigue la posición del
seguidor no sustituye una transmisión pasiva. Cualquier cambio de backend
requiere repetir cierres, colisiones, actuación y observación; no recibe
los resultados del perfil DART.

## Comprobaciones del 24 de noviembre

El nuevo banco cinemático `fk_cad_grouped180_01` pasó **11/11** casos, con
postura cero y desplazamientos de ±0,1 rad por articulación. Los máximos de
desacuerdo con las poses nativas fueron 1,175 µm y 2,557 µrad. La base estaba
fijada y se retiraron gravedad y colisiones para aislar la cinemática. El
perfil tentativo usa 180° totales por articulación centrados provisionalmente
en el cero CAD. Los extremos del recorrido real siguen sin medirse.

El banco `cad_gripper_final_contact_03` repitió el mismo SDF del intento 02
con el observador sincronizado. Se emparejaron 350/350 poses con posiciones
nativas. El mayor residual de cierre fue 0,120 µm y 25,162 µrad, y el mayor
error de engranajes, 50,514 µrad. La pinza abrió 5,996 mm y su velocidad máxima
fue 0,563980 rad/s. El control y los mecanismos pasaron en ese banco aislado.
El contacto bilateral conserva **FAIL**. Sólo la goma derecha registró puntos
no separados. La guarda impidió ARM y CUT, por lo que el latch quedó sin
ejecutar. La auditoría independiente está en `cad_gripper_final_contact_03`.

En un banco analítico, Bullet Featherstone transmitió esfuerzo en ambos
sentidos a través de su restricción de engranajes, sin un motor seguidor.
El mismo backend con la pinza CAD completa excedió límites articulares y
residuales de cierre. La prueba causal que anuló sólo las 18 máscaras de
colisión eliminó esa inestabilidad y redujo el coste. El conductor apenas se
movió aun con esos contactos deshabilitados, por lo que sigue pendiente
demostrar movilidad con la topología completa. El perfil principal conserva
sus colisiones. Activar contacto directo entre dientes también queda pendiente
por intersecciones de la teselación de ambos engranajes en la postura CAD.

`parameters_cad_final_01` aprobó los cuatro cambios de propagación estática
en el perfil agrupado. Verificó montaje, masa y centro de una carga hipotética,
un cambio de par del hombro que conserva los demás actuadores y el rechazo de
una longitud incompatible con la malla. El cálculo de gravedad del CAD
estima 7,120 N·m para el hombro en reposo. En el banco nativo de gravedad
`cad_shoulder_effort_native_01`, con base fija y sin colisiones, el perfil
nominal alcanzó un error máximo de 0,004750 rad en la ventana final. La
variante limitada a 6 N·m se saturó en 9.804 pasos y alcanzó 0,294681 rad de
error. El caso negativo confirma el efecto de cambiar un límite de esfuerzo
en simulación. Queda pendiente la respuesta del chasis con carga añadida.

El análisis `cad_v8_rigid_wrist_bound_02` verificó el SDF contra el manifiesto
V8 y calculó cotas superiores de holgura de **3,472 mm**, **2,891 mm** y
**0,554 mm**. Las tres quedan por debajo de los 4 mm exigidos. La cota cubre
los 360° alrededor del pedicelo y ambos sentidos, aun con la base libre.
Incluye el margen numérico de posición y la inclinación admitida. Se aplica
al marco de corte fijo del perfil y a la esfera de colisión de cada capacho.
La guarda de corte del simulador de 20 mm se conserva como criterio separado.
`v8_invariance_04.json` verifica las fuentes V8, las tres identidades y sus poses.

El barrido de 24 posturas con las mallas agrupadas confirmó interferencias
externas en todos los casos observados. Se guardaron por separado la holgura
interna del mecanismo y la del entorno. Los contactos internos conservan su
auditoría propia y no se convierten en exclusiones. En otro diagnóstico se
compararon las mismas posturas de la búsqueda cinemática con las mallas
visuales cerradas de los capachos. Sólo una de 62 posturas pasó el contraste
parcial muñeca–capacho con esa representación. El escenario original conserva
sus esferas y ese contraste no admite la trayectoria ni el contacto físico.

El STEP de la cuchilla contiene un filo recto de 24 mm, arista 146 entre
los vértices 119 y 120. El centro de los dos filos se separa unos 8,14 µm
del marco actual. Los ejes y la carrera CAD permiten acotar la envolvente
de puntos entre ambos filos sin elegir un nuevo centro de corte. La
primera cota con esa envolvente deja al tercer objetivo en **1,897 mm**
como máximo, aun permitiendo toda la carrera y el giro alrededor del
pedicelo. El refinamiento `cad_v8_rigid_wrist_blade_bound_02` deja también
los objetivos 1 y 2 por debajo de 4 mm en la teselación evaluada. El primer
objetivo queda muy cerca del umbral en este cálculo y la tercera cota es
la evidencia más clara del bloqueo de la misión de los tres objetivos.
Los cortes y el vídeo de misión permanecen **NO EJECUTADOS**.
