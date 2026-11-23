# Mecanismos CAD cerrados en Gazebo Harmonic

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

`cad_gripper_bullet_ramped_c012_02/independent_audit.json` obtuvo PASS **del
banco aislado entre 0 y +0.04 rad**: 120 conjuntos de poses medidos, máximo
residuo traslacional 1.179e−7 m, rotacional 1.686e−5 rad, error de engranaje
1.975e−6 rad y velocidad máxima de todas las juntas 0.5672 rad/s. El auditor
compara el esfuerzo con `JointForceCmd` observado independientemente, verifica
que el seguidor no recibe órdenes de motor y une poses/coordenadas por el
instante exacto. El primer intento conserva FAIL por carecer de la última
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
