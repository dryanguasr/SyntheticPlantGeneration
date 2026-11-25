# Mecanismos CAD cerrados en Gazebo Harmonic

> Desde el 25-11-2026, la guía operativa vigente y el desarrollo del robot
> están en [Robot-Cosechador](https://github.com/dryanguasr/Robot-Cosechador/blob/main/docs/guides/mecanismos_cerrados_cad_gazebo.md). Esta copia conserva el contexto histórico de SPG.

El adaptador conserva las articulaciones móviles y sus ejes CAD. La articulación
que cerraría el ciclo pasa a un cuerpo auxiliar, situado en el mismo marco que
su cuerpo físico. Se divide la masa y cada componente del tensor de inercia,
con el mismo centro de masa; la suma conserva la inercia original. Las mallas,
colisiones y sensores permanecen en el cuerpo original. `ClosedLoopSystem`
reúne ambos cuerpos mediante `components::DetachableJoint` fijo.

En gz-physics 7.8 esta ruta usa `SplitAndWeldLink` y `WeldJointConstraint` de
DART. La creación directa de una segunda articulación padre mediante SDF sigue
rechazada. No se asignan coordenadas a las articulaciones pasivas, no se mueve
ningún cuerpo por teletransporte y no se sustituye el mecanismo por un PID.
La implementación primaria está en
[JointFeatures.cc de gz-physics 7.8](https://github.com/gazebosim/gz-physics/blob/gz-physics7_7.8.0/dartsim/src/JointFeatures.cc#L431-L477).

## Solver y paso de integración

Con DART 6.13.2 es necesario declarar PGS para los mecanismos que cambian de
orientación. Dantzig dejó de cerrar el mecanismo oblicuo en la prueba conservada
`outputs/real_harvester_validation/gripper_gears_rotated_01`. El mismo mecanismo
con PGS pasó, sin ampliar las tolerancias, en `gripper_gears_rotated_pgs_01`.
Este comportamiento coincide con el
[fallo de restricciones redundantes documentado por Gazebo/DART](https://github.com/gazebosim/gz-physics/issues/719).

```xml
<physics name="100us" type="ignored">
  <max_step_size>0.0001</max_step_size>
  <real_time_factor>1</real_time_factor>
  <dart><solver><solver_type>pgs</solver_type></solver></dart>
</physics>
```

La selección del solver forma parte de la configuración reproducible. El éxito
de un mecanismo alineado con Y global no valida su comportamiento en otra pose.

## Contrato del cierre

```xml
<plugin filename="libUchuvaClosedLoopSystem.so" name="uchuva::ClosedLoopSystem">
  <closure name="lower_eye">
    <body>carrier</body>
    <auxiliary>carrier_closure_aux</auxiliary>
  </closure>
</plugin>
```

Los cuerpos deben coincidir al inicializarse. El sistema rechaza referencias
ausentes, nombres duplicados y marcos inicialmente separados. La articulación
móvil conserva su nombre, tipo, eje, límites y amortiguamiento. El helper puro
`src/uchuva_gazebo/closed_loops.py` aplica la transformación a un XML SDF; el
exportador del robot representa además esos auxiliares en su contrato canónico.

## Transmisión pasiva del gripper

El CAD contiene `Rotación:1`, entre `Engranaje recto2:1` y `Engranaje recto1:1`,
con `Ratio.Value=1` y `ForwardDirection=false`. La pasada de lectura
`outputs/real_harvester_cad/inventory_motion_01/cad_inventory.json` conserva esos
valores y el hash del ensamblaje. Su estado global es parcial porque esa pasada
usó el directorio original sin el rodamiento Content Center regenerado; esto
no se presenta como una nueva validación completa de referencias.
La API oficial describe el sentido en
[RotateRotateConstraint.ForwardDirection](https://help.autodesk.com/cloudhelp/2024/ENU/Inventor-API/files/RotateRotateConstraint_ForwardDirection.htm).

La convención de los dos ejes Gazebo es +Y común del CAD: el engranaje externo
se expresa como `q_follower = -q_driver`. Harmonic no ofrece mimic bilateral
nativo en DART; por ello `GearCouplingSystem` representa una transmisión
torsional de rigidez finita, declarada `engineering_heuristic`, con:

```text
e = q_follower - ratio*q_driver - offset
R = k*e + c*de/dt
tau_driver = ratio*R
tau_follower = -R
U = 0.5*k*e²
P = -dU/dt - c*(de/dt)²
```

El par de cada articulación se aplica como dos torques opuestos sobre sus links
hijo y padre, mediante `Link.AddWorldWrench`, usando el eje actualizado en mundo.
Así, `JointForceCmd` queda exclusivamente bajo el motor: la transmisión no es
otro actuador, no prescribe posiciones y no comparte ni queda recortada por el
comando limitado del PID. La telemetría del acoplamiento identifica los torques
internos y su balance energético por separado.

```xml
<plugin filename="libUchuvaGearCouplingSystem.so" name="uchuva::GearCouplingSystem">
  <driver>gripper_left_driver</driver><follower>gripper_right_follower</follower>
  <ratio>-1</ratio><offset>0</offset>
  <stiffness_nm_rad>100</stiffness_nm_rad>
  <damping_nms_rad>0.03</damping_nms_rad>
  <maximum_step_s>0.0001</maximum_step_s>
  <robot_spec_sha256>HASH_CANONICO</robot_spec_sha256>
  <topic>/harvester/gear_couplings/gripper</topic>
</plugin>
```

Estos parámetros pertenecen al fixture de topología. Las masas e inercias CAD
reales requieren su propia validación de estabilidad antes de admitirlos como
configuración del robot. El plugin rechaza un paso mayor que el declarado.

## Evidencia y reproducción

`native_loops_01` conserva cuatro casos: suspensión y un lado del gripper con
cierre físico, junto a sus controles abiertos. Los máximos errores de los pines
son 0.000696 mm y 0.002145 mm, respectivamente, frente a 1 mm y 0.5 mm.
Cada cierre exige cuatro articulaciones observadas y coincidencia completa de
los cuerpos auxiliares; no basta la salida cero del servidor.

`gripper_gears_02` añade ambos lados y un único motor con transmisión mediante
torques internos. `gripper_gears_rotated_pgs_01` repite con orientación oblicua:
ocho articulaciones observadas y error máximo de relación de 0.0001152 rad,
frente a 0.001 rad. El control sin transmisión conserva los dos lazos físicos
y pierde la relación angular, tal como debe ocurrir. Se preservan tanto el
primer ensayo con `JointForceCmd` compartido (`gripper_gears_01`) como el fallo
oblicuo Dantzig; ninguno reemplaza la evidencia final del adaptador.

```bash
bash scripts/build_harvest_plugin.sh outputs/real_harvester_plugin_build_v5
python3 scripts/probe_cad_native_loops.py --output outputs/native_loops_new \
  --plugin-dir outputs/real_harvester_plugin_build_v5 \
  --suspension-fixture outputs/real_harvester_validation/suspension_loop_03 \
  --gripper-fixture outputs/real_harvester_validation/gripper_loop_02
python3 scripts/probe_cad_gripper_gears.py --output outputs/gripper_gears_new \
  --plugin-dir outputs/real_harvester_plugin_build_v5 \
  --model-rotation-rpy 0.3 0.4 0.2 --solver pgs
```

Las pruebas usan directorios nuevos, congelan protocolo y binarios y registran
hashes, comandos y telemetría nativa. Son mecanismos aislados con propiedades de
fixture explícitas: no demuestran agarre sobre fruto, resistencia de dientes,
corte de pedicelo, desempeño del brazo ni calibración del hardware.

## Control de apertura y cierre

`scripts/harvest_gripper_control.py` ofrece `move_gripper(pilot, targets,
phase=...)`. Si se omite `targets`, exige el mapa explícito
`robot_task.gripper_open_positions`; no inventa una apertura predeterminada.
Sólo publica la posición del único driver PID, con la velocidad de referencia
de su configuración. Las posiciones pasivas opcionales del mapa son criterios
de observación y nunca órdenes a esas articulaciones.

La finalización exige posición a 0.01 rad del objetivo y velocidades nativas
de todo el mecanismo menores o iguales a 0.01 rad/s durante 0.2 s. El plazo
es fijo: 12 s simulados, con 300 s máximos de espera de reloj. Se rechazan
estados incompletos, no finitos, fuera de límites o con antigüedad superior a
0.1 s, hashes distintos y controladores competidores. Cada referencia queda
registrada con `kind=gripper_position`, fase y velocidad declarada. Estos
contratos pasan seis pruebas unitarias; no equivalen a aceptación física de
una apertura concreta ni sustituyen la admisión geométrica de su trayectoria.

El banco `probe_cad_gripper_contact.py` exige `--open-reference-rad` explícito
y restringe su entrada a `(0, 0.06]` rad debido a la interferencia CAD observada
desde +0.07 rad. Este límite del ensayo no es un tope medido de hardware. El
testigo tiene pedicelo de 1.4 mm y cuerpo esférico de 32 mm separado del plano
de agarre: los contactos esperados son con el pedicelo. El retenedor posterior
sigue siendo ideal, por lo que contacto y compatibilidad con retención se
informan separados de fuerza de agarre o de corte.

`cad_gripper_contact_02` ejecutó el perfil `mechanisms_candidate_09` con los
OBJ derivados admitidos y referencia de +0.04 rad. El resultado fue FAIL:
el hueco observado permaneció aproximadamente entre 0.325 y 0.420 mm y no se
creó el testigo ni se emitieron ARM/CUT. Los residuos de cierre y engranaje
estuvieron dentro de sus umbrales, pero hubo velocidades de hasta 1.48444 rad/s
y mensajes de desbordamiento de la tabla de contactos ODE. El campo histórico
`plateaus` de ese intento conservó etiquetas del barrido separado y no describe
sus órdenes reales; para reproducirlo se conservan `commands.jsonl`, las poses,
coordenadas nativas y el script congelado. Las versiones posteriores omiten
esas etiquetas en el ensayo guiado por contactos. Este fallo no valida apertura,
agarre ni retención.

## Colisiones cóncavas dinámicas

`scripts/probe_dynamic_concave_mesh.py` valida el backend DART/ODE con una U
cerrada, cóncava y triangulada, que tiene masa y cae 50 mm bajo gravedad antes
de llegar al tope físico de su banco. No es un modelo estático. Una esfera debe
caer dentro de la cavidad; un testigo sobre la pared debe permanecer arriba.
Un bloque convexo con el mismo contorno exterior sirve como control que sí
rellena el hueco. La prueba añade testigos hechos de malla triangular y repite
con orientación oblicua.

`outputs/real_harvester_validation/dynamic_concave_mesh_04` pasó 9/9 casos con
1.728–1.803 contactos nativos por caso. La altura del testigo respecto a la U
es aproximadamente 0.055 m en el hueco y 0.215 m sobre la pared, con error
inferior a 0.000010 m frente al criterio congelado de 0.002 m. Esto verifica
contacto malla–primitiva y malla–malla dinámicos sin convertir la cavidad en
una envolvente convexa; no sustituye la auditoría de interferencias del robot.

El primer intento, `dynamic_concave_mesh_01`, falló porque el OBJ de fixture no
incluía normales: DART descartó el submesh y el backend terminó por señal. Las
mallas CAD reparadas ya tienen normales explícitas auditadas. El intento 02
observó el movimiento esperado, pero no observó el tópico de contactos y siguió
clasificado FAIL. En este sistema, el tópico se configura dentro de
`<sensor><contact><topic>`, según
[Contact.cc de Gazebo Sim](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/contact/Contact.cc).
El intento 03 validó cinco casos con esfera; el 04 amplió a nueve incluyendo
malla–malla. Se conservan todos los intentos.

El control adicional `dynamic_mesh_winding_controls_01` mantiene exactamente
las posiciones de los vértices. Con la malla válida, la esfera queda a
0.0549999 m sobre el origen de la U. Invertir una sola faceta del piso, sin
cambiar sus normales almacenadas, permite atravesar el piso y termina a
−0.400 m: FAIL conservado como testigo de entrada corrupta. Invertir solamente
la normal `vn`, manteniendo el orden geométrico, produce el mismo resultado
correcto que la malla válida. Por ello las normales son necesarias para cargar
el OBJ en este backend, pero no reparan el orden de sus triángulos. Las mallas
de colisión y la auditoría deben compartir la misma orientación geométrica.

```bash
python3 scripts/probe_dynamic_concave_mesh.py \
  --output outputs/dynamic_concave_mesh_new \
  --plugin-dir outputs/real_harvester_plugin_build_v5
```

`scripts/probe_mesh_collision_masks.py` conserva la topología y el compilador
de máscaras del banco primitivo y sustituye las superficies por cajas OBJ
cerradas. En `mesh_collision_masks_01` pasaron seis casos: superficies malla
contra esfera y contra cubo de malla, con pareja excluida, requerida y externa.
La pareja excluida tuvo cero contactos y el testigo llegó a 0.20 m; las parejas
requerida y externa tuvieron 1.714 contactos y quedaron a 0.60 m. La tolerancia
congelada fue 5 mm. Esto verifica las máscaras también dentro del mismo
esqueleto con `self_collide=true`; no autoriza exclusiones nuevas ni sustituye
los contactos pieza por pieza del CAD.

## Diagnóstico de tangencias y referencia de fuerza

`probe_cad_gripper_contacts.py` añade observación a **cada** colisionador de
la pinza y conserva cada mensaje recibido en `contacts.jsonl.gz`. El banco
mantiene la muñeca fija, sostiene q=0 durante 0.2 s y solicita +0.04 rad con
rampa externa de 0.2 rad/s. Dura 1.2 s, con paso de 0.0001 s y solver PGS.
No crea fruto ni ejecuta un corte; `OBSERVED` significa adquisición completa,
no aceptación física. Los dos sensores de una pareja pueden duplicar su
registro, por lo que sus cuentas no son impulsos únicos.

En `cad_gripper_all_contacts_01`, DART/ODE observó contactos desde el primer
paso entre la tapa `part_99` y los eslabones `part_104`/`part_106`, incluso en
q=0. El máximo de profundidad reportada fue 1.147 mm; el conductor apenas
alcanzó 0.001842 rad. La consulta BRep independiente de Inventor encontró
tangencia sin intersección volumétrica en q=0 y +0.04 rad. Algunos contactos
ODE tienen normal dentro del plano de esa tangencia. Esto distingue el atasco
numérico del banco de la interferencia real carcasa–eslabón a mayor apertura.

El control separado `cad_gripper_no_contact_01` retiró las colisiones de la
pinza en un perfil con SHA distinto, manteniendo masas, juntas y ganancias.
Llegó a 0.039914 rad; no admite su uso en cosecha. Su resultado original FAIL
por comparación de texto ANSI permanece intacto y `startup_verification.json`
documenta la verificación posterior del detector. Persistió un pico pasivo de
1.32055 rad/s, por encima del límite original de 1 rad/s.

`analyze_cad_gripper_coupling.py` documenta una aproximación lineal local de
dos grados de libertad, con las inercias CAD y la amortiguación implícita de
las juntas. Omitir esta última produce un diagnóstico de inestabilidad
incorrecto para ese modelo reducido. Incluirla da radio espectral 0.9995501;
esta estimación no garantiza la estabilidad de los cierres discretizados ni
de los contactos nativos.

El PID de posición estándar deriva el error entre pasos. Un salto de objetivo
de 0.002 rad, con D=0.01 y paso de 0.0001 s, solicita aproximadamente 0.2 Nm
antes del límite de 0.02 Nm. El controlador opcional
`uchuva::JointPositionForceSystem` conserva P/I/D y los límites configurados,
limita la referencia **en cada paso físico** y usa la velocidad medida para
el término D. Sólo escribe `JointForceCmd` del actuador; el engranaje conserva
sus pares internos separados. No escribe posiciones ni velocidades físicas.
El término integral conserva el clamp `i_min`/`i_max` de `gz::math::PID`.

Su estado `joint-position-force/1.0` publica a 100 Hz el objetivo, referencia,
coordenada y velocidad medidas, esfuerzo previo y posterior al límite,
saturación y comandos rechazados. Las ventanas acumulan los máximos por paso
de velocidad, esfuerzo, esfuerzo sin limitar y velocidad de referencia; no
se pierden los picos por muestrear a menor frecuencia. Los comandos no finitos
o fuera de límites se rechazan sin alterar el último objetivo válido. El
reset vuelve a la referencia inicial explícita, sin mover la junta.

La revisión de detectores conserva perfiles separados. FCL registró contactos
reales pero falló físicamente: error de engranaje 0.002673 rad y profundidad
reportada 2.163 mm. El mensaje de depuración `geometry ... couldn't be created`
**no demuestra que una malla se haya descartado**: Gazebo puede incorporarla
después mediante `AttachMeshShape`. Véanse el
[cargador de mallas de Gazebo Sim](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/physics/Physics.cc)
y el [informe oficial sobre ese aviso](https://github.com/gazebosim/gz-physics/issues/985).
Ningún detector se admite únicamente porque desaparezcan los contactos de
tangencia: deben pasar los controles de concavidad y máscaras, además del
banco CAD con sus criterios originales.

Bullet pasó los nueve controles dinámicos en `dynamic_concave_bullet_01` y
los seis controles de máscaras en `mesh_masks_bullet_01`. En el mismo CAD,
desaparecieron los contactos espurios de tangencia y el conductor alcanzó
aproximadamente +0.04 rad; persistió un pico pasivo de 1.3204 rad/s con el
controlador previo. Cambiar únicamente a la rampa nativa redujo ese pico a
1.0564 rad/s, todavía FAIL frente al límite de 1 rad/s.

La observación a 10 kHz en `cad_gripper_bullet_highrate_01` encontró alternancia
de velocidad cada 100 microsegundos incluso con referencia cero: un ciclo a
5 kHz de aproximadamente ±0.296 rad/s. `analyze_cad_gripper_tree.py` deriva
por diferencias finitas la matriz de inercia de las ocho coordenadas del
árbol, incluyendo los cuerpos auxiliares. La masa condensada coincide con
el cálculo independiente del cuatro barras. Comparar proyección con masa y
masa aumentada muestra que el margen del modo rápido depende del orden de
integración; ambos son modelos ideales y no reproducen las iteraciones PGS.
El informe `cad_gripper_tree_dynamics_02.json` conserva matrices, convergencia,
hipótesis y ajustes descriptivos de las muestras nativas.

Se preregistró el candidato de amortiguación del engranaje C=0.012 N·m·s/rad
con K=100 N·m/rad. No cambiaron P/I/D del motor, paso de 0.0001 s, masas,
colisiones, fricción ni tolerancias. El modo rápido calculado tiene módulo
0.433 con proyección de masa; al no contar el amortiguamiento implícito,
el tamiz conservador sigue siendo estable. En el ensayo nativo a 10 kHz
desapareció el ciclo alternante; esto es evidencia del candidato numérico,
no una calibración de rigidez o amortiguación del engranaje real.

`cad_gripper_bullet_ramped_c012_02/independent_audit.json` registró un PASS
histórico **del banco aislado entre 0 y +0.04 rad**, posteriormente invalidado
en su cobertura temporal conjunta como se explica abajo: 120 conjuntos de poses, máximo
residuo traslacional 1.179e−7 m, rotacional 1.686e−5 rad, error de engranaje
1.975e−6 rad y velocidad máxima de todas las juntas 0.5672 rad/s. El auditor
compara el esfuerzo con `JointForceCmd` observado independientemente y verifica
que el seguidor no recibe órdenes de motor. Su asociación inicial entre
poses y coordenadas usaba la fase equivocada del instante físico.
El primer intento conserva FAIL por carecer de la última
observación de junta; el segundo añade un único paso de observación al final,
sin ampliar tolerancias. La validación del robot completo y de la revisión
CAD para apertura mayor sigue siendo un ensayo separado.

El banco de contacto final usa un testigo explícito de pedicelo de **3.6 mm**
de diámetro, derivado de los proxies V8 congelados. El cuerpo y su masa son
un fixture declarado; no se convierte una visual del pedicelo del cultivo en
una colisión real. La apertura mayor de +0.06 rad exige certificado geométrico
PASS cuya malla revisada esté en el perfil y cuyo intervalo cubra la orden.
Al observar contacto en ambas gomas, el único controlador mantiene como
referencia la posición medida del conductor. El latch sigue siendo ideal;
no se valida fuerza de agarre, fractura de pedicelo ni el prototipo físico.

## Preflight de los tres objetivos V8 congelados

`scripts/preflight_cad_v8_reach.py` conserva el manifiesto C4, sus identificadores
y sus coordenadas. Usa la ventana **provisional de comisionamiento ±15°** del
perfil, altura de base 0.296218017078388 m y permite traslación XY/yaw. No busca
una solución moviendo la planta ni amplía los límites del robot. La búsqueda
de posición/dirección acepta 0.03 rad de error angular; no ejecuta colisiones,
rutas ni dinámica. Cada candidato se contrasta con la FK canónica completa.

En `cad_v8_current_reach_03`, el objetivo `plant_001` tiene un candidato con
error posicional 3.153e−7 m y angular 0.010655 rad. `plant_000` conserva
NO_CANDIDATE_IN_SAMPLED_SEARCH: su mejor compromiso tiene error 5.821e−5 m
y 0.030554 rad, ligeramente fuera del criterio. Esto no demuestra imposibilidad
global del primer objetivo.

Para `plant_002`, la identidad exacta de los tres ejes pitch y las rotaciones
fijas del perfil permiten reducir la dirección a la suma de esos tres ángulos
y el roll; yaw de base y brazo no cambian su componente vertical. Una cobertura
de 1.024 celdas con cota angular Lipschitz produce un error angular mínimo de
0.093147 rad para el mejor signo del pedicelo, superior a 0.03 rad. Se conserva
EXCLUIDO **bajo esa ventana provisional y base nivelada**. El cálculo usa doble
precisión y un margen numérico declarado; no es aritmética de intervalos
formalmente verificada ni una afirmación sobre los topes del prototipo real.

La misma cota sólo implica una condición necesaria: habría que sumar al menos
0.063147 rad de salidas de las ventanas actuales entre las juntas que cambian
la inclinación para eliminar esa exclusión angular. No es una recomendación
de ampliar límites ni basta para alcanzar la posición, evitar colisiones o
garantizar movimiento mecánico. El objetivo permanece intacto y no se omite.

## Recorridos comunicados por el usuario y nuevo preflight

El usuario indicó «Tentativamente, todos 180° aprox» para las cinco juntas del
brazo. `cad_arm_range_revision_01.json` y `_02.json` registran **180° totales por
junta**, no ±180°. El intervalo exploratorio −90°/+90° conserva el cero CAD;
su centrado es una estimación todavía sin confirmar. No cambia la pinza,
ruedas, juntas pasivas, ganancias, esfuerzos, velocidades ni criterios de
aceptación. `prepare_cad_arm_range_revision.py` usa el resolvedor canónico y
comprueba que sólo cambien los diez extremos de rango y su procedencia.

El preflight `cad_v8_tentative180_reach_02` encuentra soluciones de posición y
dirección para los tres objetivos intactos. Al exigir además el margen
articular preregistrado de 0.025 rad quedan 22, 21 y 19 candidatos. La auditoría
`cad_v8_tentative180_static_03` revisa los tres de mayor margen por objetivo
con todas las colisiones CAD y vegetales: **ninguno de esos nueve pasa 4 mm**.
En el primer objetivo limita el chasis contra vegetación u otro fruto; en los
otros dos, la carcasa `part_98` contra el fruto objetivo. No se exceptúan los
frutos ni se trasladan plantas. Este muestreo no prueba imposibilidad global;
tampoco admite rutas continuas o dinámica. El perfil de esta búsqueda
conserva una revisión CAD anterior, identificada en sus hashes; no se
transfiere aceptación a revisiones posteriores.

## Contacto efectivo frente a proximidad de Bullet

El banco `cad_gripper_final_contact_01` usa el perfil común con rangos
exploratorios y la revisión CAD cuyo sobre operativo nominal pasó su auditoría
geométrica. Observó apertura de 5.996 mm para un testigo de pedicelo de 3.6 mm,
velocidad máxima de 0.564 rad/s, error de engranaje de 5.175e−6 rad y residuo
de cierre menor de 2.360e−7 m. La auditoría de fuerza debe declarar
`control_groups=('gripper',)` porque el brazo no está físicamente presente en
este banco. La auditoría por defecto sigue exigiendo todos los controladores
del robot completo.

La revisión de los datos crudos encontró un defecto del criterio de contacto
del banco: DART 6.13.2 conserva puntos del manifold Bullet con profundidad
negativa. Su conversión es `penetrationDepth = -m_distance1`, y Gazebo copia
esa profundidad sin cambiar su signo; son puntos de proximidad separada,
no contacto superficial. Véanse las fuentes versionadas de
[DART](https://github.com/dartsim/dart/blob/v6.13.2/dart/collision/bullet/BulletCollisionDetector.cpp#L631)
y [Gazebo Physics](https://github.com/gazebosim/gz-physics/blob/gz-physics7_7.8.0/dartsim/src/SimulationFeatures.cc#L262).
El registro izquierdo de ese ensayo tiene 46.777 puntos, todos negativos.
Por ello `independent_scope_audit.json` conserva **FAIL de contacto**, aunque
el control de la pinza y la compatibilidad del latch ideal pasan sus criterios
separados. La cobertura conjunta de mecanismos quedó después invalidada por
la corrección temporal descrita abajo. El resultado original permanece intacto.

`probe_cad_gripper_contact.py` ahora exige el par exacto goma–pedicelo, al
menos una profundidad finita no negativa y el instante nativo del mensaje
de contacto, reciente y no futuro. Conserva todos los puntos crudos, incluidos
los negativos; no modifica colisiones ni parámetros físicos. El auditor
`audit_cad_gripper_contact.py` vuelve a comprobar poses y coordenadas nativas,
mandos pasivos, contacto previo a ARM y transición del latch; guarda hashes
de evidencias y fuentes consumidas. Esta corrección exige repetir el banco,
no convertir retrospectivamente el ensayo anterior en PASS.

El segundo banco `cad_gripper_final_contact_02` conserva el mismo SHA de robot,
paso y parámetros. Abre 5.996 mm y pasa control y límites, pero conserva
**FAIL**: el contacto efectivo es unilateral y el guard impide ARM/CUT.
La izquierda registra profundidad máxima −55.7 µm y fuerza nula; la derecha
sí registra profundidad no negativa y hasta 0.396 N. No se desplaza el testigo
ni se reduce fricción para obtener aceptación.

`diagnose_cad_pedicel_contact.py` contrasta esos registros con las mismas mallas
y las poses medidas. Encuentra puntos interiores al cilindro finito en caras
de ambas gomas. El informe declara la diferencia temporal entre las últimas
muestras y la invariancia observada de la pose del testigo. El replay estático
`replay_bullet_pedicel_contacts.cc` usa la biblioteca Bullet instalada: el
cilindro conserva radio 1.8 mm y margen automático 0.18 mm. La selección de
DART clasifica la goma como no convexa. Con su dispatcher estándar, el replay
mundial reproduce una profundidad negativa del registro con diferencia menor
de 3e−11 m; expresar la misma geometría relativa alrededor del origen cambia
el signo. Esto demuestra sensibilidad del contacto pequeño al cálculo nativo;
no demuestra fallo del CAD o falta de fuerza del actuador. Registrar GImpact
explícitamente produce otras profundidades grandes y no se adopta como arreglo.
Los dos intentos y las comparaciones se conservan; sigue pendiente validar
dos contactos efectivos con una representación geométrica equivalente.

Las consultas estáticas adicionales de `cad_pedicel_geometry_diagnostic_02`
normalizan las distancias al cambiar sólo la escala de las coordenadas de la
consulta. A escala 10 y 100, Bullet recupera profundidades de aproximadamente
0.722/0.650 mm, compatibles con la geometría; esto diagnostica sensibilidad
numérica y **no propone cambiar unidades del modelo físico**. La biblioteca
ODE instalada reconoce ambos contactos con profundidades máximas 0.721812 y
0.650289 mm e invariancia de marco mejor que 1e−16 m. FCL con cilindro analítico
también reconoce ambos, pero ese replay no reproduce la teselación de 16
segmentos ni el postprocesamiento que DART aplica con FCL. En la postura
abierta medida, ambos detectores dan cero contactos. Son consultas aisladas;
no heredan aceptación de dinámica ni resuelven por sí solas las tangencias
internas tapa–eslabón.

Se evaluó además una partición de la goma en 49 celdas convexas mediante
`partition_cad_pad_mesh.py`. Un núcleo de visibilidad comprobado con aritmética
racional permite descomponer en tetraedros y fusionar sólo uniones exactamente
convexas. Se conservan los 124 triángulos externos, el volumen y los vacíos;
no se toma una envolvente convexa global. La prueba geométrica pasa, pero el
replay de Bullet a escala SI sigue sin detectar correctamente ambos contactos.
Por ello **la partición no se incorpora al robot**. Su certificado sólo prueba
equivalencia geométrica, no una mejora de la física.

## Corrección de fase temporal de la auditoría

La observación posterior por paso físico verificó que el timestamp del
`PosePublisher` corresponde a `RobotTelemetry.measured_after_step_time`,
no a `commanded_before_step_time`. Este último sigue siendo correcto para
comparar el esfuerzo del controlador publicado en PreUpdate. Son dos
contratos diferentes; no se emparejan por cercanía.

Los registros anteriores de 100 Hz tienen poses en 0.0100, 0.0200… s y
coordenadas medidas en 0.0101, 0.0201… s. Por ello no contienen ninguna pareja
exacta para auditar simultáneamente pose y coordenada. El nuevo
`cad_gripper_bullet_ramped_c012_02/independent_temporal_audit_03.json` conserva
FAIL y `joint_pose_coverage=NOT_OBSERVED`; el PASS histórico permanece como
registro del error de auditoría, no como aceptación vigente. Lo mismo se
aplica a `cad_gripper_final_contact_02/independent_temporal_audit_02.json`.
El control de fuerza y sus máximos por paso conservan sus comprobaciones
independientes. La nueva adquisición debe alinear los observadores antes de
afirmar cobertura completa de mecanismos; no se reconstruyen poses mediante FK.

## Control de giro experimental

`scripts/prepare_cad_base_feedback.py` prepara la revisión
`configs/robots/cad_base_feedback_revision_01.json`. La realimentación usa
poses del modelo de Gazebo y estima la velocidad angular sobre 0,1 s. Su
ganancia proporcional de 1,5 es una estimación para el ensayo. Los límites
de orden angular (0,3 rad/s), aceleración (0,4 rad/s²) y par de rueda
(6,5 N·m) siguen en el perfil. El comando cero aplica la rampa de parada.
Las poses vencidas o inválidas impiden emitir una nueva orden de movimiento.
El auditor vuelve a calcular la referencia, los límites y las rampas desde
las poses registradas. Las poses ideales de Gazebo no calibran la odometría.

## Verificación de holgura en el corte V8

`scripts/bound_cad_v8_cut_clearance.py` usa el perfil resuelto, sus mallas de
colisión de muñeca y el paquete V8 congelado. El script compara los centros y
radios del manifiesto con las esferas del SDF y cubre ambos sentidos del eje
del pedicelo y los 360° de giro alrededor de él. La cota superior incluye
el error admisible de posición, la inclinación y el intervalo entre muestras.
Si esa cota queda por debajo de los 4 mm requeridos, la postura de corte
falla incluso permitiendo mover libremente la base del robot. El resultado
depende del marco de corte y de la esfera conservadora del capacho del perfil
evaluado. Este análisis tampoco sustituye la auditoría de los mecanismos
internos, la trayectoria o el contacto de las gomas.

El dominio de posición del análisis es la precisión de planificación de
10 µm alrededor del punto de corte. La tolerancia de 20 mm de la guarda de
Gazebo cumple otra función y no define una zona física de filo. El análisis
con `--edge-envelope` permite estudiar la envolvente nominal de los dos
filos a lo largo de la carrera CAD sin ajustar esos criterios.

## Prueba de funcionamiento con la pinza inmovilizada

Para ensayar el brazo y el chasis mientras se resuelve el contacto de las
mordazas, `prepare_cad_fixed_gripper_diagnostic.py` deriva un perfil con las
ocho articulaciones de la pinza fijas en la postura CAD de referencia. El
preparador compara el SDF resultante con el anterior y comprueba que conserve
masas, inercias, visuales, colisionadores, máscaras y poses de montaje. Las
cuatro restricciones de la suspensión y los controles del brazo y el chasis
se mantienen. El resultado usa la pinza como carga rígida del brazo.

En WSL, ejecutar el preparador con el SHA canónico del perfil de origen.
Usar directorios de destino nuevos en cada ensayo.

```bash
python3 scripts/prepare_cad_fixed_gripper_diagnostic.py \
  --profile outputs/real_harvester_validation/cad_base_feedback_candidate_01/profile.json \
  --asset-root outputs/real_harvester_validation/cad_base_feedback_candidate_01/assets \
  --expected-source-sha256 f4f1b8bdb9e4e4a8171ed6203be2661efd1a51474de9cfaf667d08e132ccbef9 \
  --output outputs/real_harvester_validation/pinza_fija_derivacion_nueva

python3 scripts/probe_cad_mobility.py \
  --experiment integrated_arm --start-height 0.298218017078388 \
  --max-step-size 0.0001 --wall-timeout 1800 \
  --profile outputs/real_harvester_validation/pinza_fija_derivacion_nueva/profile.json \
  --asset-root outputs/real_harvester_validation/pinza_fija_derivacion_nueva/assets \
  --plugin-dir outputs/real_harvester_plugin_build_v8 \
  --output outputs/real_harvester_validation/pinza_fija_ensayo_nuevo
```

El ensayo incorpora tres fases de brazo bajo gravedad, con consignas de
+0,08 rad, −0,08 rad y retorno a origen. Sigue la secuencia original de
avance, frenado, giro y frenado. Se comprueban los límites de esfuerzo y
velocidad, el seguimiento en las fases de brazo y los cierres de suspensión
observados. El perfil diagnóstico deja el agarre, corte y cosecha pendientes.

Para grabar una demostración breve con el perfil fijo de referencia,
`scripts/cad_v8_function_demo.py` prepara un paquete aparte. Verifica el
manifiesto V8 y mantiene las mallas y poses del cultivo. En esa escena
los tres frutos objetivo son estáticos. La cámara nativa observa dos
movimientos del hombro, su retorno y un avance corto por el corredor.

```bash
python3 scripts/cad_v8_function_demo.py \
  --profile outputs/real_harvester_validation/cad_fixed_gripper_diagnostic_01/profile.json \
  --asset-root outputs/real_harvester_validation/cad_fixed_gripper_diagnostic_01/assets \
  --plant-package outputs/harvest_pilot_v8_c4_gui \
  --acceptance-lock configs/robots/cad_v8_acceptance_lock.json \
  --plugin-dir outputs/real_harvester_plugin_build_v8 \
  --output outputs/real_harvester_validation/pinza_fija_video_paquete_nuevo
python3 scripts/cad_v8_function_demo.py --run \
  --package outputs/real_harvester_validation/pinza_fija_video_paquete_nuevo \
  --output outputs/real_harvester_validation/pinza_fija_video_ensayo_nuevo
```
