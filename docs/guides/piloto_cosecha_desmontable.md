# Piloto de uchuvas desmontables en Gazebo

## Objetivo y estado de entrega

Preparar un escenario pequeño y reproducible en el que un carro 4WD con brazo
de cinco grados de libertad se acerque a una uchuva, sitúe su herramienta en el
pedicelo, solicite el corte, retire el conjunto fruto-capacho y lo deposite en
una cesta. El modelo botánico procede del generador morfológico del proyecto.
El robot es provisional y sus interfaces están separadas de las plantas.

**El ciclo ideal de corte, retención, transporte y depósito cuenta con ejecución
nativa auditada en Gazebo Harmonic 8.14.0.** El alcance, las correcciones, los
intentos fallidos y los resultados por experimento están en el
[informe de validación nativa](../reports/piloto_cosecha_desmontable_validacion_gazebo_2026-10-31.md).
La entrega inicial no había compilado ni simulado el piloto; su informe se
conserva como antecedente. Generar XML válido, resolver IK en Python o recibir
un acuse de corte no demuestra retención ni depósito físico.

El alcance es deliberadamente mecánico: se emplean las posiciones conocidas del
simulador. No se atribuye al piloto detección visual, elección agronómica de
madurez, planificación general entre obstáculos ni transferencia al robot real.
Las ramas son rígidas; el follaje y las mordazas son visuales. La retención se
representa con una unión fija ideal, y el corte con una condición geométrica.
No se modelan fuerzas de fractura, tijeras deformables ni daño de la fruta.

## Qué se genera

La configuración inicial `configs/harvest_pilot_v1.json` prepara tres plantas,
con semillas reproducibles, y selecciona dos unidades cosechables por planta.
La selección usa geometría y separación conservadora de colisiones; los frutos
mantienen sus nodos y pedicelos originales. Si una configuración no ofrece
suficientes candidatos válidos, la preparación debe fallar con el diagnóstico
en lugar de colocar frutos arbitrariamente.

Son plantas pequeñas para una prueba técnica, no una réplica calibrada de un
cultivo adulto. Las posiciones, masas, fricción, dimensiones del robot y ganancias
de control son `engineering_heuristic`. El inventario conserva esa procedencia
y deja la madurez agronómica sin afirmar.

| Artefacto del paquete | Función |
| --- | --- |
| `harvest.sdf` | Mundo, suelo, cesta, plantas, frutos dinámicos, robot y plugins |
| `manifest.json` | Configuración, inventario de unidades, procedencia y parámetros de aceptación |
| `morphologies/` | Morfologías serializadas que originaron las plantas |
| `meshes/` | Mallas visuales ligeras de hojas y capachos |
| `robot_contract.json` | Nombres, articulaciones, marcos, límites y temas del robot provisional |
| `ros_gz_bridge.yaml` | Puente opcional para inspección e integración con ROS 2 |
| `runs/<utc>-<pid>/` | Resultados separados de cada ejecución nativa |

La conversión de escala es explícita: ocho unidades internas del generador
equivalen a un metro en la salida SDF. Los colliders de tallos y pedicelos se
mantienen separados de las mallas visuales. Cada fruto cosechable es un modelo
dinámico propio, hermano del arbusto dentro del `world`; no está anidado en el
modelo estático de la planta.

El pedicelo seleccionado se representa por dos tramos: el proximal queda en la
planta y el distal acompaña al fruto. El punto de corte se obtiene sobre el
pedicelo de la morfología. La esfera de colisión del cuerpo cosechable engloba
conservadoramente el capacho y tiene masa e inercia positivas.

La preparación también ejecuta una búsqueda acotada de retiradas. Comprueba
interpolaciones articulares del brazo y el volumen del fruto retenido frente a
los colliders exportados y los otros frutos. Algunas unidades admiten salida
recta; otras requieren salir de lado o variar la altura antes de replegar el
brazo. `manifest.json`, en `mission`, conserva el plan, los candidatos
rechazados y los mínimos geométricos. El umbral nominal es 4 mm: esta revisión
muestreada no sustituye la comprobación de errores de seguimiento y contactos
en Gazebo. La base toma una ruta por detrás de la cesta para evitar atravesarla.

El robot mantiene `self_collide=true`, requerido por las limitaciones
documentadas de las uniones desprendibles [6]. Sus diez links usan máscaras de
colisión disjuntas: las autocolisiones del proxy están explícitamente
desactivadas por pares de links, mientras que plantas, frutos, suelo y cesta
usan la máscara `65535`. Así se conserva la interacción con el entorno y se
habilita la colisión entre frutos que han pasado por la herramienta. La
configuración de máscaras se comprueba sin Gazebo; su efecto tras adjuntar y
desprender debe verificarse nativamente [10-11].

## Entorno de ejecución

El objetivo es **Ubuntu 24.04, Gazebo Harmonic / `gz-sim8`**, con ROS 2 Jazzy si
se desea utilizar el puente. El piloto se comunica directamente por Gazebo
Transport y no exige iniciar ROS para correr la prueba mecánica. La combinación
Jazzy-Harmonic está documentada por Gazebo [1]. En Windows, ejecutar estos
comandos dentro de la distribución WSL donde está instalado Gazebo.

Antes de instalar nada, inspeccionar el entorno existente:

```bash
gz sim --versions
cmake --version
g++ --version
python3 -c "from gz.transport13 import Node; from gz.msgs10.stringmsg_pb2 import StringMsg; print('Gazebo Transport Python disponible')"
```

Para una instalación Harmonic mediante los paquetes de OSRF, los paquetes de
desarrollo y Python utilizados por el piloto son los siguientes [2-4]:

```bash
sudo apt update
sudo apt install cmake g++ make libgz-sim8-dev libgz-plugin2-dev libgz-transport13-dev libgz-msgs10-dev python3-gz-transport13 python3-gz-msgs10
```

El repositorio oficial de paquetes de Gazebo debe estar configurado previamente,
según la guía de instalación de Harmonic [5]. No es necesario recompilar Gazebo.
Si la máquina usa paquetes `ros-jazzy-gz-*-vendor`, identificar primero qué
prefijo de bibliotecas está activo y seguir la guía ROS/Gazebo [1]; no combinar
prefijos de distintas versiones para resolver un error de CMake. El script del
proyecto compila solamente su plugin y no instala paquetes del sistema.

Usar el Python del sistema que puede importar `gz.transport13` y `gz.msgs10`.
Un entorno virtual aislado puede ocultar los paquetes instalados por APT; en
ese caso usar `/usr/bin/python3` en los comandos siguientes o crear el entorno
con acceso a los paquetes del sistema. La preparación geométrica no importa
las bibliotecas nativas de Gazebo.

## Preparar, compilar y ejecutar

Todos los comandos siguientes se ejecutan desde la raíz del repositorio.

Las pruebas que no requieren Gazebo se ejecutan con:

```bash
PYTHONPATH=src:. python3 -m unittest discover -s tests -p 'test_harvest*.py' -v
python3 scripts/validate_repository_context_graph.py
```

La búsqueda geométrica añade varias decenas de segundos a esta suite y a la
preparación del paquete, según el equipo. No se generan renders.

### 1. Generar el paquete y comprobar SDF

```bash
python3 scripts/prepare_harvest_pilot.py --output outputs/harvest_pilot
gz sdf -k outputs/harvest_pilot/harvest.sdf
```

Revisar `manifest.json`: semillas, número de plantas y objetivos, escala,
unidades excluidas, separación inicial y parámetros físicos. La validación
`gz sdf -k` debe ejecutarse en la máquina con Gazebo: la lectura del XML con
Python no sustituye al validador de SDFormat.

La cámara está desactivada por defecto. La ejecución de servidor no necesita
renderizar imágenes. Para preparar también el sensor RGB:

```bash
python3 scripts/prepare_harvest_pilot.py --output outputs/harvest_pilot_camera --camera
```

La cámara permite una extensión posterior; el controlador del piloto sigue
utilizando poses conocidas del simulador. No cambiar esa etiqueta experimental.

### 2. Compilar el sistema de corte y retención

```bash
bash scripts/build_harvest_plugin.sh outputs/harvest_plugin_build
```

El directorio es opcional; ese es el valor de uso previsto. Verificar que se
produzca `libUchuvaHarvestSystem.so` y conservar la salida de compilación. Si
CMake no encuentra `gz-sim8`, resolver la instalación/prefijo antes de continuar.
No reinterpretar una biblioteca ausente como una prueba de simulación aprobada.

### 3. Prueba inicial sin cosecha

```bash
python3 scripts/run_harvest_pilot.py outputs/harvest_pilot --plugin-dir outputs/harvest_plugin_build --mode smoke
```

Esta etapa observa que los frutos permanezcan unidos, que el robot y las
entidades estén disponibles, y que se rechacen identificadores desconocidos y
órdenes improcedentes desde lejos. Deben quedar telemetría, eventos, registro de
Gazebo y resultado de aceptación en el directorio de ejecución indicado por
el programa. Resolver cualquier fallo antes de avanzar a una cosecha.

### 4. Un ciclo completo

```bash
python3 scripts/run_harvest_pilot.py outputs/harvest_pilot --plugin-dir outputs/harvest_plugin_build --mode harvest --max-targets 1
```

La evidencia debe mostrar desplazamiento real del carro, aproximación del TCP,
corte autorizado, fruto que acompaña a la herramienta, liberación y reposo
dentro de la cesta. Las poses observadas del modelo son las que cuentan para
aceptar esos pasos; los comandos enviados son únicamente una referencia.

### 5. Todos los objetivos y revisión visual

```bash
python3 scripts/run_harvest_pilot.py outputs/harvest_pilot --plugin-dir outputs/harvest_plugin_build --mode harvest --max-targets 6
python3 scripts/run_harvest_pilot.py outputs/harvest_pilot --plugin-dir outputs/harvest_plugin_build --mode harvest --max-targets 1 --gui
```

La primera orden corresponde a los seis objetivos de la configuración inicial.
Si se cambia su número, ajustar `--max-targets` al inventario generado. La opción
`--gui` añade la inspección visual; conservar un video corto del ciclo completo
con sus identificadores de ejecución y artefactos. El video complementa la
auditoría de telemetría y no sustituye sus criterios.

Para una vista de inspección sin cambiar el mundo físico, añadir
`--gui-config configs/harvest_pilot_gui.config` junto con `--gui`. El ejecutor
copia esa configuración a la salida y registra su SHA-256. Incluye los plugins
de captura y video de Gazebo. El servicio `/gui/screenshot` permite guardar la
cámara nativa cuando la captura de ventanas de WSLg desde Windows no funciona.

Cada ejecución usa por defecto un subdirectorio nuevo
`outputs/harvest_pilot/runs/<utc>-<pid>`. La opción `--output RUTA` permite fijar
el directorio de resultados. No superponer dos procesos sobre la misma salida.
Para repetir una prueba, iniciar una ejecución nueva: el botón de reset de
Gazebo bloquea deliberadamente este plugin con un mensaje que pide reiniciar
el proceso.

### 6. Volver a auditar resultados guardados

```bash
python3 scripts/audit_harvest_pilot.py outputs/harvest_pilot outputs/harvest_pilot/runs/ID_DE_LA_EJECUCION
```

Sustituir `ID_DE_LA_EJECUCION` por el directorio real que informó el ejecutor.
La auditoría utiliza la telemetría y los eventos guardados. Si faltan muestras,
hay coordenadas no finitas, se reinició el tiempo de simulación o falta alguna
condición de aceptación, el resultado debe permanecer fallido o no observado.
El informe distingue `PASS`, `FAIL`, `NO OBSERVADO` y `NO EJECUTADO`. Coteja
comandos y acuses en orden y exige estabilidad del depósito al final del
registro: un fruto que estuvo estable pero salió después no aprueba.
La comprobación de separación entre esferas es geométrica y muestreada; no
equivale a una validación de fuerzas de contacto.

El manifiesto preparado conserva `native_validation: pending_gazebo`; no se
reescribe después de una misión porque sus hashes deben permanecer estables.
La aceptación nativa corresponde al `audit.json` de cada ejecución.

## Contrato del mecanismo de cosecha

El plugin `uchuva::HarvestSystem`, cargado desde `UchuvaHarvestSystem`, recibe
`gz.msgs.StringMsg` en `/harvest/command`. Publica JSON dentro de `StringMsg` en
`/harvest/state` y `/harvest/events`.

| Orden | Condición y resultado |
| --- | --- |
| `arm ID` | Requiere fruto unido, herramienta disponible, TCP cerca y velocidad relativa baja; prepara la operación sin añadir una segunda unión |
| `cut ID` | Requiere `ARMED`, guardas válidas y tiempo estable; solicita retirar la unión con planta |
| `release ID` | Requiere fruto retenido; solicita retirar la unión con herramienta |
| `disarm` | Cancela una preparación todavía no cortada |

La transición normal es `ATTACHED → ARMED → CUT_PENDING → HELD →
RELEASE_PENDING → RELEASED`. `RELEASED` expresa que no hay retención; el depósito
se evalúa posteriormente por posición y velocidad. Un fallo de configuración,
entidad desaparecida, residual excesivo o reset produce `ERROR` y `ready=false`.

Los parámetros iniciales del sistema son heurísticos:

| Parámetro | Valor inicial | Interpretación |
| --- | ---: | --- |
| `cut_tolerance` | 0,02 m | Distancia máxima entre TCP y punto de corte |
| `capture_radius` | 0,12 m | Distancia máxima entre TCP y centro del cuerpo cosechable |
| `max_relative_speed` | 0,12 m/s | Límite de movimiento relativo observado |
| `stable_time` | 0,2 s | Permanencia en condiciones válidas antes del corte |
| `attachment_tolerance` | 0,01 m | Residual de posición tolerado para una unión solicitada |
| `startup_timeout` | 5 s | Tiempo simulado máximo para resolver entidades |

La zona de corte es una comprobación de distancia, no un sensor de contacto ni
una medida del esfuerzo del pedicelo. El radio de captura expresa una retención
ideal para este piloto. Cualquier ampliación de tolerancias debe justificarse
en el informe; no aumentarlas solamente para obtener `PASS`.

Los eventos incluyen `seq`, `sim_time`, `id`, `action`, `phase`, `accepted` y
`reason`. `phase="ack"` confirma la decisión sobre una orden y `phase="result"`
describe una transición posterior. Una unión creada en ECM no demuestra por sí
sola su eficacia física. El estado explicita la evidencia y publica el error
de posición entre el fruto y el padre de la unión.

La pose del robot y la del TCP usan `[x,y,z,qx,qy,qz,qw]`. La lista `fruits`
incluye `position`, `cut_position`, `relative_speed`, `stable_seconds`,
`joint_present`, `joint_parent`, `removal_pending` y `constraint_error_m`.
Después de `arm`, esperar al menos el tiempo estable exigido antes de `cut`.

La transferencia entre planta y herramienta ocupa dos etapas de simulación.
En `gz-sim8`, la física crea nuevas restricciones antes de eliminar las antiguas;
por ello el plugin espera a que desaparezca la entidad de la unión anterior.
No crea dos padres simultáneos ni mueve artificialmente el fruto. La topología
en árbol y las limitaciones de contacto al adjuntar están documentadas en las
fuentes oficiales [6-8].

## Matriz de aceptación nativa

| Prueba | Evidencia necesaria |
| --- | --- |
| Compilación y carga | Biblioteca generada; ausencia de error de carga; sistema publica estado |
| SDF | `gz sdf -k` aprobado para el paquete concreto |
| Reposo inicial | Todos los frutos unidos y sin deriva apreciable durante el intervalo de línea base |
| Identificador desconocido | Rechazo explícito y ausencia de cambios en los frutos |
| Orden desde lejos | Rechazo de preparación/corte y frutos aún unidos |
| Salir de la zona después de armar | Armar cerca, alejar el TCP y cortar; rechazo por distancia y unión con planta conservada |
| Corte válido | Un solo fruto transfiere su restricción; los demás permanecen unidos |
| Corte repetido | Segundo corte del mismo fruto rechazado |
| Retención | Fruto se desplaza con la herramienta, con error relativo pequeño y unión a herramienta observada |
| Depósito | Fruto liberado, completamente contenido en la cesta y con velocidad baja durante el intervalo exigido |
| Fruto contra fruto | Los cuerpos ya depositados interactúan con los siguientes, sin atravesarse ni ocupar el mismo volumen |
| Continuidad | Sin saltos grandes, valores no finitos, caídas iniciales ni vuelco del carro |
| Repetición | Nueva ejecución con los mismos parámetros reproduce el resultado y conserva artefactos separados |
| Reset | Aparece error explícito y se pide reiniciar; no se declara una nueva corrida válida |

La prueba de cortar después de alejar una herramienta ya armada verifica la
guarda geométrica específica de `cut`. Un corte rechazado antes de armar solo
verifica la guarda de estado. El auditor debe conservar esa distinción.
La revisión de contactos y cualquier ensayo adicional deben anotarse aparte
si todavía no forman parte del ejecutor automático.

## Sustituir el robot provisional

El brazo tiene cinco articulaciones: giro de base, hombro, codo, inclinación de
muñeca y giro de muñeca. Las cuatro articulaciones de rueda son actuadores
adicionales. El origen del modelo está al nivel del suelo; `+X` apunta hacia
delante, `+Y` a la izquierda y `+Z` hacia arriba. El TCP coincide con el origen
de `tool_link`.

Para introducir la versión final, sustituir el módulo de descripción del robot
o proporcionar un adaptador equivalente, actualizar `robot_contract.json` y
adaptar la cinemática/planificación del ejecutor. La IK analítica actual depende
de las longitudes y disposición del brazo provisional; no es un planificador
de colisiones ni un controlador universal de cualquier brazo.

Mantener el significado de `robot_model`, `tool_link`, la pose del TCP y los
temas del contrato, o actualizar sus enlaces explícitamente. Las identidades
de planta/nodo/pedicelo/fruto, el exportador botánico y el sistema de uniones
no necesitan depender de las dimensiones del nuevo chasis. La sustitución
requiere repetir la aceptación física, especialmente alcance, autocolisiones,
estabilidad de base, holgura del efector y depósito.

## Arbustos v8 completos y acabado visual

`configs/harvest_pilot_v1.json` conserva el escenario pequeño de la línea base.
La configuración `configs/harvest_pilot_v8.json` importa tres árboles admitidos
`trained_trellis_nodal_repulsion_v8` con fenología `literature_cohort_v1`, sin
reducir sus hojas ni capachos al presupuesto de frutos cosechables.

El intérprete histórico de esta rama no reconstruye las poses v8. Por eso
`scripts/export_admitted_harvest_sources.py` evalúa, en modo de lectura, el
intérprete del checkout fuente y congela un catálogo de proxies junto al JSON
morfológico original. Requiere las evidencias de admisión del árbol y verifica
sus identidades, escala y hashes. La admisión estática existente no sustituye
una nueva validación física de cosecha.

Ejemplo para los árboles locales utilizados, desde WSL:

```bash
python3 scripts/export_admitted_harvest_sources.py \
  --source-repo /mnt/c/dev/SyntheticPlantGeneration \
  --source-units-per-metre 10 \
  --plant-files \
    /mnt/c/dev/SyntheticPlantGeneration/outputs/spatial_plant_pool_20261028/plants/seed_2026102702/plant.json \
    /mnt/c/dev/SyntheticPlantGeneration/outputs/spatial_plant_pool_20261028/plants/seed_2026102703/plant.json \
    /mnt/c/dev/SyntheticPlantGeneration/outputs/spatial_plant_pool_20261028/plants/seed_2026102708/plant.json \
  --output outputs/harvest_v8_sources
python3 scripts/prepare_harvest_pilot.py \
  --config configs/harvest_pilot_v8.json --output outputs/harvest_pilot_v8_c1
```

Ambos comandos exigen destinos nuevos. Las fuentes grandes permanecen como
artefactos locales, fuera de Git; un clon de esta rama necesita esos árboles y
sus evidencias o los catálogos congelados. El paquete final copia los originales,
los catálogos y los PNG utilizados, y registra sus SHA-256. La conversión fuente
es explícitamente 10 unidades por metro; la salida SDF y las mallas están en SI.

`harvest_visuals.py` interpreta hojas curvas con dos caras, capachos con cinco
costillas y los materiales actuales del proyecto. Agrupa las superficies
estáticas por material para reducir el coste gráfico, conservando los cuerpos
de los frutos seleccionados y todos los segmentos rígidos. Es una interpretación
para Gazebo; no una copia exacta del render o de todas las mallas Blender.
La apariencia del cáliz no se convierte en madurez agronómica.

El robot incorpora carenados, neumáticos con dibujo y juntas visibles mediante
elementos visuales. Una prueba compara todo el SDF no visual antes y después:
masas, colisiones, articulaciones, TCP y controladores se preservan. La nueva
escena requiere repetir A0 y A1 antes de aceptar misiones más largas; los PASS
de la línea base no se transfieren automáticamente a los árboles densos.

La configuración v8 utiliza `batched_conservative_prisms` para las colisiones
estáticas. Cada cilindro original queda contenido en un prisma cerrado de doce
caras, con los mismos extremos; el radio de sus vértices es `r/cos(pi/12)`
(+3,53 %). Los 15.842 segmentos se agrupan en tres mallas, sin sustituir las copas
por envolventes convexas ni retirar ramas. Se declara esta aproximación física:
no es idéntica al contacto con cilindros analíticos. El perfil histórico conserva
sus cilindros analíticos.

Cada OBJ de colisión lleva las identidades y dimensiones originales. El lector
reconstruye y coteja todos sus triángulos antes de evaluar trayectorias usando
los cilindros externos que contienen los prismas. Se mantiene el margen de
4 mm y el muestreo previo. Para analizar un paquete desde disco, pasar su
directorio como `mesh_root` a `rigid_cylinders` después de verificar los hashes.
El informe registra el fallo de rendimiento de la versión con 15.842 entidades
independientes, las pruebas de contacto y las ejecuciones de la representación
agrupada.

## Nota sobre el generador y trabajo futuro

El piloto reutiliza la morfología y sus proxies. No redefine la arquitectura
botánica ni usa el prototipo geométrico legado como fuente. La ruta inicial
selecciona explícitamente `legacy_independent`: en el generador actual el ajuste
del presupuesto reproductivo precede a la asignación por cohortes, y esta
última puede añadir una unidad. La inconsistencia del tope en esa otra ruta
debe corregirse y auditarse por separado; preparar este escenario no la resuelve.

Tras aceptar el mecanismo rígido, los siguientes incrementos razonables son
calibrar masa/tamaño y alturas con medidas de campo, incorporar percepción,
evaluar una herramienta con contactos y añadir pocas ramas flexibles en un
experimento separado. Cada incremento necesita nueva evidencia; el piloto
actual no demuestra aún las prestaciones de esos sistemas.

## Encargo concreto para Codex en la máquina con Gazebo

```text
En SyntheticPlantGeneration, lee AGENTS.md y esta guía. Conserva la arquitectura
morfología → exportación SI → plugin de interacción y el contrato modular del
robot. El objetivo es ejecutar y auditar el piloto ya implementado.

1. Registra commit, estado de trabajo, Ubuntu/WSL, versiones de Gazebo y Python.
   Verifica las dependencias nativas sin modificar otros proyectos.
2. Prepara outputs/harvest_pilot con la configuración inicial. Comprueba
   inventario, mallas y manifest. Ejecuta gz sdf -k sobre harvest.sdf.
3. Compila con scripts/build_harvest_plugin.sh y conserva el log. Resuelve los
   errores de API/compilación que se demuestren, sin sustituir la física por
   teletransporte ni retirar las guardas para pasar una prueba.
4. Ejecuta --mode smoke. Inspecciona logs, eventos y estabilidad inicial.
5. Ejecuta --mode harvest --max-targets 1 y vuelve a auditar sus artefactos.
   Comprueba el caso armar cerca → alejar TCP → intentar corte y el rechazo del
   corte repetido. Si esos casos requieren una extensión del auditor, añádela
   preservando el registro de poses y la separación entre orden y evidencia.
6. Solo cuando el ciclo individual pase, ejecuta los seis objetivos. Conserva
   una repetición con --gui y un video corto del corte-retirada-depósito.
7. Publica un informe de aceptación con PASS/FAIL por criterio y enlaces a los
   artefactos locales. Un acuse de corte no basta para aprobar retención; un
   estado RELEASED no basta para aprobar depósito. Registra resultados negativos.
8. Señala cualquier paso no ejecutado. No atribuyas percepción, realismo de
   fuerzas, ramas flexibles, madurez agronómica ni validación Sim2Real al piloto.
```

## Fuentes primarias

1. [Combinaciones ROS 2/Gazebo y paquetes vendor](https://gazebosim.org/docs/harmonic/ros_installation/).
2. [Instalación de la biblioteca Gazebo Sim 8](https://gazebosim.org/api/sim/8/install.html).
3. [Gazebo Transport 13: soporte Python, paquete e imports](https://gazebosim.org/api/transport/13/python.html).
4. [Paquetes oficiales gz-msgs](https://get.gazebosim.org/distributions/gz-msgs/releases/).
5. [Instalación binaria de Harmonic en Ubuntu](https://gazebosim.org/docs/harmonic/install_ubuntu/).
6. [Uniones desprendibles: topología y límites de contacto](https://gazebosim.org/api/sim/8/detachablejoints.html).
7. [Implementación DetachableJoint en gz-sim8](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/detachable_joint/DetachableJoint.cc).
8. [Orden de creación y retirada de restricciones en Physics.cc](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/physics/Physics.cc).
9. [Interfaces de plugins de sistema](https://gazebosim.org/api/sim/8/createsystemplugins.html).
10. [Lectura de filtros de contacto en DART / gz-physics7](https://github.com/gazebosim/gz-physics/blob/gz-physics7/dartsim/src/SDFFeatures.cc).
11. [Filtro de colisiones de DART / gz-physics7](https://github.com/gazebosim/gz-physics/blob/gz-physics7/dartsim/src/EntityManagementFeatures.cc).
