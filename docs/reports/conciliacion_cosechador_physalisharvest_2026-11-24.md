# Conciliación del cosechador digital y PhysalisHarvest

Este documento conserva el corte inicial de conciliación. La revisión posterior,
la autorización de fusión del usuario y los avances de todos los frentes se
registran en [la continuidad de integración](integracion_avances_locales_2026-11-24.md).

Fecha de corte: **24 de noviembre de 2026**. Este informe documenta la
centralización en la rama de revisión
[`codex/integracion-physalisharvest-20261124`](https://github.com/dryanguasr/SyntheticPlantGeneration/tree/codex/integracion-physalisharvest-20261124)
de SyntheticPlantGeneration. No
autoriza ni registra una fusión a `main`, una instalación de dependencias o
una prueba física con motores.

## Fuentes y alcance

| Fuente | Corte identificado | Qué aporta |
| --- | --- | --- |
| Repositorio principal | [`ec0d3a19f7a87ad5a7366ff75127be0dbd9a64f9`](https://github.com/dryanguasr/SyntheticPlantGeneration/tree/ec0d3a19f7a87ad5a7366ff75127be0dbd9a64f9) | Base `origin/main` inspeccionada al iniciar la conciliación |
| Avances locales del cosechador | `codex/gazebo-real-harvester-parametric`, `0bcb8a83e3885fe192e0e996bda0cf9e94834528` | Modelo paramétrico, CAD, cinemática, validación y avances V8 preservados en Git local |
| PhysalisHarvest, `main` | [`0c423be793ba2145674da0a49ab7e46d8bf1f119`](https://github.com/amayadiegoalejandro05/PhysalisHarvest/tree/0c423be793ba2145674da0a49ab7e46d8bf1f119) | Arquitectura objetivo, contratos propuestos y verificadores |
| PhysalisHarvest, `feat/2WD` | [`99661effc9baf9ad68e382f1e106e3811d98a578`](https://github.com/amayadiegoalejandro05/PhysalisHarvest/tree/99661effc9baf9ad68e382f1e106e3811d98a578) | Implementación del banco ROS 2, firmware y herramientas |
| PhysalisHarvest, corte incorporado | [`fix/2wd-bench-scripts`, `114ce5690e7bf024d57ce2c815b7f3afd1d82e38`](https://github.com/amayadiegoalejandro05/PhysalisHarvest/tree/114ce5690e7bf024d57ce2c815b7f3afd1d82e38) | Banco completo y correcciones de descubrimiento de herramientas como tests |

Se revisaron los árboles y archivos de esos cortes. Las ramas `feat/arm`,
`feat/locomotion` y `feat/vision` apuntaban a
`58cc3ee789659d31d10d8f5f404414534c275f4d`: contenían reservas documentales,
sin implementaciones adicionales de sus subsistemas. La ausencia de código
en esas ramas no permite concluir que no exista trabajo fuera del repositorio.

La integración conserva los cambios locales de otras campañas fuera de su
alcance. Un archivo no rastreado no se considera respaldado por Git hasta
incorporarlo explícitamente; no se retiraron materiales suponiendo lo contrario.

La rama se preparó desde el corte estable del cosechador de 18 commits y se
concilió con `origin/main` en `ec0d3a19f7a87ad5a7366ff75127be0dbd9a64f9`,
sin conflictos de fusión. Las ediciones concurrentes posteriores de scripts
y C++ para demos de vídeo en el checkout original `harvest-pilot` **no se
incluyen**. Su existencia no se presenta como avance subido ni validado.

## Arquitectura conciliada

La arquitectura botánica sigue en `src/uchuva_lsystem/`. `robot_spec.py` y
`robot.py` son la descripción y API canónicas del modelo digital; el SDF es
una interpretación de ese modelo. El contrato y adaptador puros se ubican en
`src/uchuva_gazebo/physalisharvest.py`, acompañados del verificador
`scripts/check_physalisharvest_integration.py`.

El snapshot íntegro de Diego se preserva en `contributions/physalisharvest/`.
Se incorporó mediante `git read-tree --prefix=contributions/physalisharvest/`
desde la referencia fija del corte seleccionado. El registro de procedencia
del proyecto principal está en `contributions/physalisharvest.provenance.json`,
fuera del árbol original importado.
Sus dos paquetes reales son `bench_2wd` y `bench_2wd_drv8833`, ambos bajo el
área de locomoción. El workspace se puede seleccionar directamente con
`colcon --base-paths`; no se duplican sus paquetes en otro workspace del
repositorio principal. La [guía de integración](../guides/integracion_physalisharvest.md)
explica su revisión y uso opcional en un entorno ya disponible.

| Dimensión | Compatibilidad al corte | Condición o límite |
| --- | --- | --- |
| Separación de responsabilidades | Compatible a nivel de arquitectura | Percepción propone, manipulador evalúa, base ejecuta su control; el simulador no redefine morfología |
| Unidades | Compatible en los contratos inspeccionados | Metros y radianes; conservar unidades explícitas y procedencia |
| Preservación de código externo | Compatible con atribución separada | Snapshot con SHA y términos originales; sin relicenciar bajo MIT |
| Modelo de robot | Compatible mediante perfiles separados | `RobotSpec` canónico; banco físico 2WD y proxy virtual de cuatro ruedas son plataformas distintas |
| Observación ArUco | Compatible mediante adaptación explícita | Marco óptico, tiempo, valores finitos y estados inválidos conservados |
| ArUco → objetivo botánico | Incompatible como equivalencia directa | Un marcador superficial no es el centro de la baya, el cáliz ni un punto de corte |
| Marcos óptico/base/mundo | Pendiente | Falta transformación calibrada y vigente; no cambiar `frame_id` sin transformar coordenadas |
| ROS 2 → Gazebo Transport | Pendiente | Ruedas reciben Double por articulación; cmd_vel/odometry del contrato no tienen endpoint nativo. Faltan adaptación Twist/controlador, odometría y puente |
| Tiempo ROS/físico/simulado | Pendiente | Relojes y captura deben verificarse; el controlador del banco usa tiempo de pared para caducidad |
| Estado `ARRIVED` → llegada global | Incompatible como equivalencia directa | El banco usa Z ≤0,50 m frente a la cámara, sin odometría ni referencia global de llegada |
| Brazo físico y efector | Pendiente | No hay implementación ejecutable de brazo en los cortes remotos inspeccionados |
| Cosecha RGB autónoma | Pendiente y no demostrada | Asociación de identidad del piloto asistida por simulador; diagnóstico RGB 0/6 |
| ROS 2 y dobles de firmware | Build y pruebas locales aprobados | Dos paquetes y mensajes locales; firmware y USB con mocks. Cámara, puertos y motores no ejecutados |

Los [contratos ROS 2 generales de Diego](https://github.com/amayadiegoalejandro05/PhysalisHarvest/blob/0c423be793ba2145674da0a49ab7e46d8bf1f119/docs/interfaces/contratos-ros2.md)
se declaran propuestas sujetas a acuerdo. El contrato experimental del banco
DRV8833 sí tiene productores y consumidores concretos, pero no se convierte
por esa razón en el contrato definitivo de cosecha.

## Avances del modelo digital y límites V8

Los resultados siguientes proceden del
[informe V8 preservado](piloto_cad_v8_canasta_2026-11-24.md).
Son evidencia histórica de simulación recuperada para esta conciliación;
no se ejecutó de nuevo la misión al redactar este documento.

- El núcleo paramétrico conserva perfiles, unidades, hashes, cinemática,
  límites, colisiones, marcos de herramienta y comprobaciones de control.
  Preparar un SDF o superar pruebas de software no calibra el robot físico.
- Una prueba aislada con chasis estacionado confirmó **un fruto depositado**
  en la canasta. Conserva telemetría y vídeo locales; el tiempo se agotó durante
  la recogida del brazo. No equivale a una misión continua de nueve frutos.
- El paquete candidato reúne **nueve rutas**, tres por arbusto. La misión
  dinámica completa seguía pendiente de admisión con carga y velocidad de
  muñeca. Los ensayos de muñeca registraron fallos que no deben ocultarse.
- Bajo la política estricta, las **19 posturas** de corte muestreadas fueron
  rechazadas por interferencias. Ese resultado es distinto de la política
  ampliada que exceptúa **19 geometrías** de muñeca, carcasa y pinza frente al
  cultivo. La excepción modifica el modelo de contacto y limita su realismo;
  no demuestra que esas intersecciones sean físicamente válidas.
- ONNX móvil y dos modelos de segmentación obtuvieron **0 de 6 coincidencias**
  a confianza 0,25 e IoU 0,5 en el diagnóstico. La máscara nativa confirmó las
  seis observaciones, pero esa información privilegiada no es percepción RGB
  desplegable ni evidencia de madurez del fruto.

Las poses V8, el contacto idealizado de corte/retención y las excepciones
deben acompañar cualquier presentación del depósito. Las tomas estáticas o
parciales rotuladas 0/9 no se reinterpretan como nueve cosechas exitosas.

## Desajustes documentales preservados del aporte

La inspección del [código del controlador](https://github.com/amayadiegoalejandro05/PhysalisHarvest/blob/114ce5690e7bf024d57ce2c815b7f3afd1d82e38/ros2_ws/src/robot_locomocion/bench_2wd_drv8833/bench_2wd_drv8833/controller.py)
y del firmware encontró textos históricos que no describen exactamente ese
corte. Una tabla aún presenta XYZ cero como estado genérico, aunque el
publicador distingue Z −1/−2/−3. La guía contiene una frase antigua de firmware
sin PWM, mientras el sketch usa LEDC a 1 kHz. Otro párrafo afirma que toda
observación inválida desarma, pero el controlador conserva armado al pausar.

Se conserva el snapshot original y se registran aquí las discrepancias.
El adaptador no debe deducir una consigna ni una confirmación física a partir
de esas frases. Una revisión futura del aporte requiere actualizar documento,
código y pruebas conjuntamente, manteniendo trazabilidad de la versión.

## Procedencia, licencias y dependencias externas

PhysalisHarvest corresponde al macroproyecto del semillero SEIMA,
Universitaria Agustiniana, y al repositorio de Diego Alejandro Amaya Celis.
Se conservan sus declaraciones institucionales y atribuciones originales.
La licencia general y la titularidad institucional siguen pendientes; el
[`package.xml` del banco](https://github.com/amayadiegoalejandro05/PhysalisHarvest/blob/114ce5690e7bf024d57ce2c815b7f3afd1d82e38/ros2_ws/src/robot_locomocion/bench_2wd_drv8833/package.xml)
lo declara expresamente. La licencia MIT del repositorio principal se limita
al código original al que resulte aplicable, sin relicenciar este aporte.

El snapshot no incorpora automáticamente el antecedente externo Astra, SDK,
calibración específica del dispositivo, CAD original, mallas, pesos o resultados
de `outputs/`. Las herramientas citan el antecedente Astra en
`7b4cd1b50ddecae7ea30494160e519d9e4191038` y una calibración con hash específico.
Preservar esa referencia no sustituye disponer de archivos autorizados ni
comprobar otro sensor. No se instalaron dependencias nuevas para centralizarlo.

## Registro de verificación de esta sesión

La revisión posterior del corte inicial encontró defectos no cubiertos por
las pruebas de esta tabla. El [registro de correcciones del PR 1](correcciones_revision_pr1_2026-11-24.md)
conserva sus causas, cambios y verificaciones nuevas. Los resultados iniciales
se mantienen como evidencia histórica; no certificaban los casos negativos
añadidos después de la revisión.

Se ejecutaron comprobaciones nuevas el 24 de noviembre de 2026. Las cifras
siguientes corresponden a esta rama aislada, sin repetir misiones V8. Ninguna
dependencia se instaló para obtener estos resultados.

| Comprobación | Resultado nuevo | Evidencia local o comando |
| --- | --- | --- |
| Integridad del snapshot | PASS, 107 archivos | `python scripts/verify_physalisharvest_snapshot.py`; manifiesto versionado de procedencia |
| Regresión robot, cosecha, CAD e interfaz Gazebo | PASS, 307 tests; 0 fallos, errores u omisiones | `outputs/physalisharvest_validation/python_tests.{json,log}`; patrones `test_robot*.py`, `test_harvest*.py`, `test_cad*.py`, `test_gazebo_interfaces.py` |
| Mecanismos, pinza fija, reparación de malla y holguras | PASS, 19 tests adicionales | `test_closed_loop_adapter.py`, `test_fixed_gripper_diagnostic.py`, `test_inventor_mesh_repair.py`, `test_resolved_clearance_sampling.py`, `test_static_calyx_refinement.py`; `supplementary_tests.log` |
| Adaptador de observación y plan de interfaces | 10 tests PASS | `PYTHONPATH=src python3 -m unittest discover -s tests -p test_physalisharvest.py -v` |
| Verificadores originales de Diego | PASS, 22 tests | `python -m unittest discover -s contributions/physalisharvest/tests -v` |
| Puente USB original con puerto simulado | PASS, 6 tests | `python -m unittest discover -s contributions/physalisharvest/firmware/bench_2wd/tools/test -v` |
| Firmware DRV8833 con mock C++ | PASS, programa de contratos | Compilado con `c++ -std=c++17` y el include `drv8833_ros/test`; ejecutable en `outputs/physalisharvest_validation/firmware_mock` |
| Conversión SI y transformaciones CAD | PASS | `tests/test_inventor_export_helpers.ps1`, sin abrir Inventor |
| Plugins de Gazebo | Build correcto de cinco bibliotecas; 3/3 CTests PASS | `outputs/physalisharvest_validation/native_build/`: logs y hashes `build_provenance.json` |
| Paquetes ROS 2 | Build correcto de `bench_2wd` y `bench_2wd_drv8833`; 6/6 tests PASS | `outputs/physalisharvest_validation/ros_ws/{build.log,pytest.log,pytest_results.xml,run_ros_validation.sh}` |
| CLI offline y mapa de contexto | PASS | `check_physalisharvest_integration.py --profile proxy_v1 --output outputs/physalisharvest_validation/integration_proxy_final.json`; grafo: 160 nodos, 268 relaciones |
| Nueva misión V8, cámara, serial y motores físicos | NO EJECUTADOS | No se atribuye la evidencia histórica a esta sesión |
| Fusión a main y revisión humana | Pendientes del usuario | Rama entregada para revisión, sin fusión automática |

Entorno de la regresión Linux: Ubuntu 24.04 bajo WSL, Python 3.12.3.
Compilación nativa: GCC 13.3, CMake 3.28.3, Gazebo 8.14. ROS 2 Jazzy ya estaba
instalado; se cargó `/opt/ros/jazzy/setup.bash`. Los verificadores y el mock USB
también se ejecutaron con el Python 3.12 existente del checkout principal.
Los tests ROS probaron nodos reales con mensajes locales y tuberías de prueba;
no conectaron el controlador a un puente serial físico.

Los comandos de build están en la guía y en
`scripts/build_harvest_plugin.sh`; los tests nativos se ejecutan con
`ctest --test-dir outputs/physalisharvest_validation/native_build --output-on-failure`.
Para los tests ROS se cargó el `local_setup.bash` del build y se ejecutó pytest
explícitamente sobre los dos archivos originales `test_transport.py` y
`test_ros.py`, con caché y logs bajo `outputs/`.
Los logs y binarios generados permanecen locales; este informe versionado
conserva resultados y límites, no los presenta como validación humana.

La revisión cruzada del adaptador detectó que `cmd_vel`/`odometry` eran sólo
declaraciones del contrato paramétrico. Se corrigió el inventario para exponer
los endpoints por rueda reales y probar esa distinción. El resultado no
instala un puente ROS/Gazebo ni crea órdenes PWM a partir de metros por segundo.

## Decisión de integración

El resultado previsto es una rama con los avances centralizados, un contrato
comprobable y la matriz de compatibilidad visible. La arquitectura admite una
conciliación por capas; la integración operativa completa aún depende de TF,
tiempos, puente ROS 2/Gazebo, ejecución de brazo y validaciones físicas.
El usuario revisará la suficiencia de esta compatibilidad antes de decidir
la fusión a `main`. Los resultados negativos, las licencias pendientes y las
capacidades no ejecutadas forman parte de esa revisión.
