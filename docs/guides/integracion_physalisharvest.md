# Integración del cosechador y PhysalisHarvest

> Desde el 25-11-2026, la guía operativa vigente y el desarrollo del robot
> están en [Robot-Cosechador](https://github.com/dryanguasr/Robot-Cosechador/blob/main/docs/guides/integracion_physalisharvest.md). Esta copia conserva el contexto histórico de SPG.

Esta integración centraliza el modelo digital y el banco experimental de Diego
en **SyntheticPlantGeneration**, mediante la rama de revisión
[`codex/integracion-physalisharvest-20261124`](https://github.com/dryanguasr/SyntheticPlantGeneration/tree/codex/integracion-physalisharvest-20261124). No fusiona
automáticamente a `main`, no instala dependencias ni habilita motores.

La [conciliación del 24 de noviembre](../reports/conciliacion_cosechador_physalisharvest_2026-11-24.md)
identifica los cortes de origen, la evidencia y las condiciones pendientes.
Para el modelo digital, consultar también
[robot paramétrico](robot_cosechador_parametrico.md) y
[piloto V8](piloto_cad_v8_canasta.md).

## Un único lugar para cada responsabilidad

```text
src/uchuva_lsystem/                         arquitectura botánica y morfología
src/uchuva_gazebo/robot_spec.py              descripción canónica del robot
src/uchuva_gazebo/robot.py                   API pública del modelo digital
src/uchuva_gazebo/physalisharvest.py         contrato y adaptación puros
src/uchuva_gazebo/robot_sdf.py               interpretación en Gazebo
contributions/physalisharvest/              corte externo íntegro y atribuido
  ros2_ws/src/robot_locomocion/              bancos ROS 2 de Diego
  firmware/bench_2wd/                       firmware y herramientas del banco
docs/                                      acuerdos y evidencia del proyecto
outputs/                                   resultados locales fuera de Git
```

La morfología de la planta continúa siendo la fuente botánica. El contrato
`robot-spec/1.0` produce un `ResolvedRobot` en SI, con hash y procedencia;
SDF, cinemática y auditoría consumen esa misma descripción. Cambiar una medida
del robot requiere modificar su parámetro canónico y regenerar los derivados.

El aporte de Diego conserva estructura, autoría y términos originales bajo
`contributions/physalisharvest/`. El registro de procedencia está fuera del
snapshot, en `contributions/physalisharvest.provenance.json`, para preservar
íntegros los originales. No copiar sus paquetes a otro `ros2_ws/src`
ni crear un segundo modelo del robot a partir del firmware. Las carpetas
`robot_brazo`, `robot_interfaces` y `robot_percepcion_decision` del corte
externo son reservas documentales, no paquetes implementados.

## Qué se incorpora del repositorio de Diego

El corte de referencia es
[`fix/2wd-bench-scripts`, `114ce5690e7bf024d57ce2c815b7f3afd1d82e38`](https://github.com/amayadiegoalejandro05/PhysalisHarvest/tree/114ce5690e7bf024d57ce2c815b7f3afd1d82e38).
Contiene dos bancos:

- `bench_2wd`: recepción de coordenadas y diagnóstico sin actuadores.
- `bench_2wd_drv8833`: recepción ArUco, control experimental, monitor y sesión,
  junto con firmware ESP32/DRV8833 y puente USB en Windows.

La rama `main` de Diego, al corte
[`0c423be793ba2145674da0a49ab7e46d8bf1f119`](https://github.com/amayadiegoalejandro05/PhysalisHarvest/tree/0c423be793ba2145674da0a49ab7e46d8bf1f119),
contiene arquitectura y verificadores, pero no esos paquetes ejecutables.
Los bancos se preservan como trabajo externo, con sus pruebas y sus límites;
su presencia en este repositorio no demuestra una ejecución nueva.

## Contrato del banco y traducción

El [contrato externo](https://github.com/amayadiegoalejandro05/PhysalisHarvest/blob/114ce5690e7bf024d57ce2c815b7f3afd1d82e38/docs/interfaces/bench-2wd-drv8833.md)
y su código describen observaciones de superficies de marcadores ArUco.
El adaptador puro `physalisharvest.py` sirve para inspeccionar compatibilidad y
validar esas observaciones sin importar ROS 2, abrir puertos ni actuar.
`build_integration_plan(resolved_robot)` deriva el plan del contrato canónico;
`normalize_astra_point(...)` valida una observación con reloj de mensaje y
reloj actual declarados, ambos compatibles. Rechaza campos adicionales de
verdad del simulador, marcos erróneos, tiempos inválidos y datos no finitos.

El contrato actual del cosechador usa un brazo revoluto y rechaza un brazo
prismático antes de emitir campos en radianes. Las coordenadas prismáticas de
la mordaza y los mecanismos pasivos siguen en metros. El solver y el auditor
deben compartir el estado auxiliar observado; la apertura y el cierre se
criban también en posiciones intermedias de la mordaza.

| Campo o recurso | Semántica que se conserva |
| --- | --- |
| `PointStamped` | XYZ en metros, con marco y tiempo explícitos |
| `astra_depth_optical_frame` | X derecha, Y abajo, Z axial hacia delante |
| ID 0 | `/bench_2wd/drv8833/aruco_target` |
| Otros IDs de `DICT_4X4_50` | El mismo nombre con sufijo `_id_<ID>` |
| Z −1, −2, −3 | Inválido, marcador ausente y visible sin profundidad, respectivamente |
| Muestra válida | Componentes finitas y Z positivo; no convertir estados en puntos geométricos |
| Edad al ingresar | Hasta 250 ms; adelanto máximo de 30 ms |
| Inicio y seguimiento | Inicio hasta 180 ms; retención de la última lectura hasta 450 ms |
| QoS de observación | Mejor esfuerzo, volátil, profundidad 1 |
| `state` | Texto de estado; fiable, profundidad 10 |
| `enable` | Solicitud `SetBool`; aceptación de la solicitud, no llegada física |

No convertir automáticamente coordenadas ópticas a `base_link`, `world` u
`odom`. Hace falta una transformación calibrada y vigente. Tampoco identificar
una superficie ArUco con el centro del cáliz, la baya o el punto de corte.
El valor `ARRIVED` del banco expresa el umbral Z ≤0,50 m respecto de la cámara;
no acredita llegada a una coordenada global ni una medida de frenado.

El modelo digital usa **Gazebo Transport** para estados articulares y
referencias por articulación. En los perfiles que declaran `drive.joints`, las ruedas reciben
`gz.msgs.Double` por `/harvester/drive/<joint>/cmd_vel`, en rad/s; el
`DriveReferenceController` calcula esas referencias con límites y signos.
`/harvester/cmd_vel` y `/harvester/odometry` permanecen como nombres declarados
en el contrato histórico, sin endpoints nativos en este runtime. El plan los
marca `contract_only_no_native_endpoint`: falta un adaptador de Twist al
controlador y una fuente de odometría observada. No basta remapear nombres
ni configurar un puente genérico. Tipos ROS 2 propuestos, TF, reloj, QoS y
arbitraje operativo deben verificarse antes de una integración funcional.

## Verificar este corte sin hardware

Desde la raíz del repositorio, con un intérprete Python disponible:

```powershell
python scripts/verify_physalisharvest_snapshot.py
python scripts/check_physalisharvest_integration.py --help
python scripts/check_physalisharvest_integration.py --profile proxy_v1 --output outputs/physalisharvest_revision/integration.json
python scripts/validate_repository_context_graph.py
```

El verificador de integración inspecciona el corte y su contrato; leer su
reporte completo y distinguir errores, advertencias y pruebas no ejecutadas.
Sus resultados no equivalen a compilar ROS 2, simular una misión o medir el
robot físico. El [informe de conciliación](../reports/conciliacion_cosechador_physalisharvest_2026-11-24.md)
debe registrar los comandos realmente ejecutados en esta sesión. Usar una
salida nueva para cada revisión. Para una observación guardada, la CLI admite
`--point-json`, `--now-ns`, `--message-clock-domain`, `--now-clock-domain` y
`--topic`; consultar `--help` antes de preparar esos datos. El plan no instala
un puente ROS ni publica comandos.

Si **ya existe** un entorno Ubuntu 24.04/Jazzy con las dependencias del banco,
la entrada canónica del proyecto compila y consulta los nodos desde una única
instalación externa al snapshot. Funciona desde Python en Windows/WSL o Linux:

```powershell
python scripts/physalisharvest_ros.py compilar --dry-run
python scripts/physalisharvest_ros.py compilar --output-root outputs/physalisharvest_ros
python scripts/physalisharvest_ros.py estado --output-root outputs/physalisharvest_ros --dry-run
python scripts/physalisharvest_ros.py estado --output-root outputs/physalisharvest_ros
python scripts/physalisharvest_ros.py monitor --output-root outputs/physalisharvest_ros
```

`--output-root` es el mismo en compilación y lanzamiento; sus subdirectorios
`build`, `install` y `log` permanecen bajo `outputs/`. El lanzador verifica los
107 archivos originales y exige `install/setup.bash` antes de ejecutar un nodo.
`--dry-run` muestra el comando y si existe la instalación sin iniciar procesos.
`estado` espera mensajes reales del tópico de estado: no inicia un controlador.
Se puede cancelar con Ctrl+C o pasar `-- --once` para leer un solo mensaje.
`--domain-id` y `--distro` permiten seleccionar el dominio y WSL explícitamente.

Las acciones `recibir`, `fuente` y `controlador` invocan los nodos originales;
`fuente` consume su entrada estándar, sin abrir una cámara. Los argumentos
originales del nodo se pasan después de `--`. `armar` y `parar` invocan el
cliente de sesión original; el armado sigue siendo una acción explícita con
sus confirmaciones. Este lanzador no abre puerto serie, inicia la Astra ni
sustituye el puente físico. Las consultas no arman motores.

Los lanzadores y GUI históricos bajo `contributions/physalisharvest/` conservan
su ruta interna `ros2_ws/install`. No corresponden a esta instalación externa:
usar la entrada canónica para estos comandos ROS, sin copiar paquetes ni
modificar los originales para ajustar sus rutas.

La conciliación inicial compiló ambos paquetes y ejecutó seis pruebas ROS
con mensajes locales y tuberías simuladas. La corrección posterior volvió a
compilarlos mediante esta entrada y verificó `estado -- --once` con un
publicador local de prueba. No se probó cámara, serie ni motor. Para repetir
las pruebas originales, cargar el `install/local_setup.bash` de la instalación
seleccionada y ejecutar `python3 -m pytest` sobre `bench_2wd/test/test_transport.py`
y `bench_2wd_drv8833/test/test_ros.py`, usando sus rutas dentro del snapshot.
El [registro de correcciones](../reports/correcciones_revision_pr1_2026-11-24.md)
conserva la evidencia y sus límites.

## Dependencias y materiales que no viajan con el corte

No se integran automáticamente el SDK OpenNI, el repositorio externo de la
Astra, su calibración, CAD, mallas, pesos, capturas ni resultados en `outputs/`.
El banco cita un antecedente Astra fijado a
[`7b4cd1b50ddecae7ea30494160e519d9e4191038`](https://github.com/amayadiegoalejandro05/astra-rgbd-ros2-integration/tree/7b4cd1b50ddecae7ea30494160e519d9e4191038).
La calibración es específica del sensor: no inventarla ni reutilizar su hash
como garantía de calibración de otra cámara.

La licencia institucional de PhysalisHarvest sigue pendiente; la licencia MIT
del código original de SyntheticPlantGeneration no relicencia el snapshot.
Mantener atribuciones, procedencia y advertencias al distribuirlo.

## Revisión antes de fusionar

La revisión debe comprobar que los hashes del aporte son trazables, que las
pruebas puras pasan y que la separación botánica/robot/simulador se mantiene.
Las interfaces ROS 2 operativas requieren acuerdo de visión, brazo y
locomoción, transformación espacial y reloj verificados y ensayos de rechazo,
caducidad, parada y realimentación.

El ensayo V8 conserva un depósito aislado observado en simulación, nueve
rutas candidatas pendientes de misión dinámica y una variante con 19
geometrías exceptuadas frente al cultivo. La inferencia RGB de tres modelos
dio 0/6 coincidencias en el diagnóstico registrado. Ninguno de esos hechos
demuestra cosecha autónoma con percepción desplegable.

La rama se entrega para revisión del usuario. Fusionarla a `main` es una
decisión posterior a esa revisión, con los resultados negativos y las
limitaciones visibles. Las ediciones concurrentes posteriores de demos de
vídeo en el checkout original del cosechador están fuera de este corte y no
deben confundirse con avances incluidos o verificados en esta rama.
