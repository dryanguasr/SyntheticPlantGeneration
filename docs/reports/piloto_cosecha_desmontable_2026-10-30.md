# Preparación del piloto de cosecha desmontable

Fecha de referencia: 30 de octubre de 2026, Colombia.

Base inspeccionada: `74b43d205927fd66d5ecd9833f7de7eed27972b5` de
`dryanguasr/SyntheticPlantGeneration`. Este informe describe la intervención
implementada sobre esa base. El commit que contiene la entrega y sus pruebas
es el que versiona este documento; los experimentos nativos deben registrar
después su commit concreto y estado de trabajo.

## Dictamen

**El generador actual es utilizable para preparar un piloto pequeño de
interacción, siempre que la exportación separe explícitamente los cuerpos
cosechables de la planta estática.** La morfología proporciona asociaciones
entre nodo, pedicelo, cáliz y fruto, así como la geometría de referencia. Esa
información permite obtener puntos de corte y modelos reproducibles sin
inventar ubicaciones de frutos en el espacio.

La exportación visual o estática por sí sola no proporciona cosecha física.
La intervención añade cuerpos independientes, masa/inercia, colliders,
contrato de interacción y un robot de prueba. La aceptación de las uniones,
los contactos, el movimiento y el depósito sigue pendiente de Gazebo Harmonic.

## Auditoría del punto de partida

| Hallazgo | Implicación | Decisión para este piloto |
| --- | --- | --- |
| La arquitectura es morfológica y serializable | Se puede preservar identidad de órganos entre representaciones | Reutilizar `uchuva_lsystem` y sus proxies |
| Los proxies conservan posiciones de tallos, pedicelos y capachos | El corte puede definirse sobre el pedicelo existente | Convertir coordenadas a SI y conservar trazabilidad de nodo y órgano |
| La representación visual no especifica una unión cosechable | No basta con cargar la planta en Gazebo | Exportar cada unidad elegida como cuerpo dinámico independiente |
| Una planta estática no puede contener frutos dinámicos anidados sin revisar la herencia física | Un fruto puede permanecer estático después de un supuesto corte | Crear plantas y frutos como modelos hermanos del `world` |
| El presupuesto reproductivo se ajusta antes de la fase de cohortes | Esa fase puede añadir una unidad después del ajuste | Usar explícitamente `legacy_independent` en el escenario acotado; no declarar corregida la otra ruta |
| El cultivo y el robot no están calibrados con todas las medidas físicas | No corresponde extraer conclusiones sobre desempeño real | Etiquetar parámetros como `engineering_heuristic` |

La inconsistencia de conteo se observa en el orden de llamadas de
`grammar.py`: `_enforce_reproductive_unit_target` precede a
`_apply_literature_cohorts`; esta última puede reasignar estados fenológicos y
convertir flores en unidades con fruto/cáliz después del ajuste. Este cambio no modifica
la gramática ni el estudio de aumentación de imágenes.

## Implementación entregada

### Plantas e inventario

`src/uchuva_gazebo/harvest_plants.py` genera un grupo pequeño con semillas
deterministas. El escenario inicial solicita tres plantas y dos cuerpos
cosechables por planta. Los candidatos se filtran por lado de aproximación,
altura y separación conservadora respecto de la geometría rígida. La
generación falla si no se puede cumplir el número solicitado.

El archivo distingue entre frutos seleccionados dinámicos y otras unidades
visuales. Registra las exclusiones y su motivo. El fruto, el capacho y el
tramo distal del pedicelo viajan como un solo cuerpo; el tramo proximal queda
en la planta. El collider es una esfera conservadora, con inercia de esfera
y masa inicial explícitamente estimada. Las hojas no son obstáculos físicos.

La geometría está en metros: se usa la conversión de ocho unidades internas
por metro. La malla visual es ligera y derivada de los proxies; no pretende
reproducir el acabado visual de Blender ni demostrar fidelidad fotométrica.

### Acercamiento y extracción revisados geométricamente

`harvest_clearance.py` reconstruye los 713 colliders cilíndricos exportados y
revisa interpolaciones articulares con el brazo y el fruto retenido. La primera
retirada propuesta hacia afuera y arriba producía penetraciones nominales de
hasta aproximadamente 12 mm en una rama. Se reemplazó por una búsqueda finita
de salidas, conservando como obstáculos los demás frutos.

La configuración predeterminada encuentra seis trayectorias con umbral de
separación de 4 mm. Cuatro objetivos usan salida horizontal; otro necesita una
pequeña elevación y el último una salida lateral con elevación. El mínimo
muestreado del fruto retenido es aproximadamente 5,14 mm y el del robot frente
al entorno, 11,23 mm. Son resultados de geometría nominal; no incluyen errores
de seguimiento ni garantizan separación continua. El manifiesto conserva las
muestras, mínimos y candidatos rechazados. La cesta y el tránsito de la base
se comprueban adicionalmente durante la ejecución nativa.

### Robot sustituible

`src/uchuva_gazebo/harvester_robot.py` produce un carro dinámico 4WD con brazo
de cinco articulaciones: giro de base, hombro, codo, inclinación y giro de
muñeca. Las ruedas añaden cuatro articulaciones motrices. Incluye
`DiffDrive`, controladores de posición del brazo, publicación de articulaciones,
cinemática directa/inversa del proxy y un contrato de marcos y temas.

La herramienta se representa con una carcasa y mordazas visuales; la
retención la realiza el sistema de interacción. Las dimensiones, masas,
límites y ganancias son hipótesis de ingeniería. Sustituir el robot final
requiere cambiar su descripción y el adaptador cinemático/controlador; las
plantas y el mecanismo de uniones dependen de identidades y del TCP, no de
las longitudes del brazo provisional.

La revisión cruzada detectó que desactivar `self_collide` para todo el robot
era incompatible con el comportamiento de contacto documentado para hijos
desprendidos. Se habilitó a nivel de modelo y se conservaron desactivadas las
autocolisiones del proxy mediante una máscara distinta por link. Los colliders
del entorno y de los frutos usan `65535` para incluir todos esos bits. El
contrato del robot declara esta simplificación. La revisión física debe
verificar especialmente el contacto entre frutos sucesivos en la cesta; las
pruebas puras de máscaras no certifican ese contacto.

### Corte y retención

`gazebo/harvest_system/HarvestSystem.cc` implementa un sistema C++ para
`gz-sim8`. Conserva una única unión por fruto y separa la solicitud de
eliminación de la creación de la retención en la herramienta. Esa secuencia
responde al orden de actualización del motor físico: crear y eliminar en
el mismo paso puede introducir temporalmente dos padres.

El sistema verifica identidad, estado, disponibilidad de herramienta,
proximidad del punto de corte, proximidad del centro del fruto, velocidad
relativa y tiempo de estabilidad. Registra acuses y resultados separados.
Publica poses, estados y residuos de posición, y bloquea la interacción
tras errores o reset. No altera poses ni desactiva gravedad para simular
éxito. La creación de una restricción se identifica como evidencia de ECM,
complementada por observación geométrica; no se presenta como medición de
fuerzas de sujeción.

### Preparación, ejecución y aceptación

Los puntos de entrada definidos para la entrega son:

| Script | Responsabilidad |
| --- | --- |
| `scripts/prepare_harvest_pilot.py` | Generar paquete SDF, mallas, morfologías, manifest y contrato del robot |
| `scripts/build_harvest_plugin.sh` | Configurar y compilar únicamente el plugin del proyecto |
| `scripts/run_harvest_pilot.py` | Ejecutar smoke o cosecha, controlar el proxy y guardar evidencia de cada corrida |
| `scripts/audit_harvest_pilot.py` | Volver a evaluar resultados guardados |

`src/uchuva_gazebo/harvest_validation.py` exige evidencia observada: estabilidad
inicial, rechazo de órdenes indebidas, integridad temporal, ausencia de
desprendimientos no solicitados, movimiento real de base y fruto, retención
con poco deslizamiento y reposo del fruto liberado dentro de la cesta. El
puente ROS es opcional y la cámara está desactivada por defecto.

## Qué queda demostrado y qué está pendiente

| Nivel | Estado de esta entrega | Límite de interpretación |
| --- | --- | --- |
| Inspección de arquitectura y API | Realizada sobre código del proyecto y fuentes oficiales | No equivale a ejecutar Gazebo |
| Código de generación, contrato, cinemática y auditoría | Implementado y con pruebas puras para el cierre de la entrega | No certifica el motor físico |
| Compilación de C++ contra Harmonic instalado | Pendiente de máquina nativa | No afirmar compatibilidad de compilación hasta registrar su salida |
| Validación `gz sdf -k` | Pendiente de máquina nativa | Parsear XML con Python no prueba todo el contrato SDF |
| Creación/transferencia/retirada de uniones en DART | Pendiente | La API revisada orienta la implementación; se necesita comprobar su efecto |
| Retención, estabilidad y depósito | Pendiente | Ni la orden ni el estado lógico bastan para aprobar |
| Video y revisión de contactos | Pendiente | Complementa la telemetría y permite detectar artefactos visibles |
| Percepción, flexibilidad, fuerzas y Sim2Real | Fuera de este piloto | No atribuir estos resultados a la entrega |

### Cierre de verificaciones ejecutadas

En el entorno de preparación se ejecutaron:

```bash
PYTHONPATH=src:. python -m unittest discover -s tests -p 'test_harvest*.py' -v
PYTHONPATH=src:. python -m unittest tests.test_gazebo_field tests.test_gazebo_interfaces tests.test_repository_context_graph tests.test_repository_layout -v
python scripts/prepare_harvest_pilot.py --output outputs/harvest_pilot_final
python scripts/validate_repository_context_graph.py
```

Resultado: **55 pruebas del piloto aprobadas** y **17 regresiones existentes
aprobadas**. La preparación emitió tres plantas, seis cuerpos cosechables y
21 mallas; el plan aceptado contiene 3.453 muestras de geometría articular.
El grafo quedó válido con 152 nodos y 262 relaciones. También pasaron la
compilación sintáctica de Python, `bash -n` del lanzador de compilación y
`git diff --check`.

La referencia al directorio privado e ignorado `Dataset Original` se conserva
como entrada local opcional en el grafo; no se exige que un clon público lo
contenga para validar sus fuentes versionadas. No se crearon ni alteraron
datos de ese dataset.

El entorno carece de Gazebo y de CMake. La invocación del script de compilación
se detuvo correctamente con `Missing build prerequisite: cmake`. **El plugin
no fue compilado y la simulación no fue ejecutada.** Las pruebas del auditor
usan trazas artificiales etiquetadas como tales y no son evidencia nativa.

## Riesgos concretos que debe resolver la auditoría nativa

1. **Unión a planta estática y transferencia entre padres.** Confirmar que el
   fruto comienza fijo, que la primera restricción desaparece y que la nueva
   realmente lo retiene mientras la herramienta se mueve.
2. **Colliders y contacto.** Revisar separación inicial, interacción con tallos,
   carcasa, suelo, cesta y otros frutos cosechados. La restricción ideal no compensa penetraciones ni
   prueba que la herramienta real pueda entrar en el mismo espacio.
3. **Masas y control.** Confirmar estabilidad del carro, orientación de ejes,
   seguimiento de articulaciones y error del TCP con masas pequeñas.
4. **Guarda de corte después de armar.** Armar cerca, alejar el TCP y solicitar
   el corte. Su rechazo debe proceder de la condición geométrica, no solamente
   de estar en un estado previo a `ARMED`.
5. **Depósito.** Confirmar que el cuerpo liberado queda contenido y en reposo
   durante el intervalo de aceptación. `RELEASED` por sí solo no lo prueba.
6. **Repetibilidad.** Iniciar procesos nuevos, preservar semillas/configuración
   y registrar intentos fallidos. No usar reset como si restaurara este plugin.

El procedimiento ejecutable, los comandos completos y el encargo para Codex
están en [la guía del piloto](../guides/piloto_cosecha_desmontable.md). El próximo
informe debe indicar PASS/FAIL por criterio, versiones, commit, rutas de
resultados y pruebas no ejecutadas. Los fallos deben corregirse manteniendo
las guardas y la evidencia, sin sustituir movimiento físico por poses impuestas.

## Fuentes técnicas primarias

- [Gazebo Harmonic: bibliotecas y versiones](https://gazebosim.org/docs/harmonic/install/).
- [Gazebo con ROS 2](https://gazebosim.org/docs/harmonic/ros_installation/).
- [Uniones desprendibles y restricciones de topología/contacto](https://gazebosim.org/api/sim/8/detachablejoints.html).
- [Implementación del sistema DetachableJoint en gz-sim8](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/detachable_joint/DetachableJoint.cc).
- [Implementación física de gz-sim8](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/physics/Physics.cc).
- [Interfaces y ciclo de vida de plugins](https://gazebosim.org/api/sim/8/createsystemplugins.html).
- [API Python de Gazebo Transport 13](https://gazebosim.org/api/transport/13/python.html).
- [Lectura de máscaras en DART / gz-physics7](https://github.com/gazebosim/gz-physics/blob/gz-physics7/dartsim/src/SDFFeatures.cc).
- [Filtrado de contactos en DART / gz-physics7](https://github.com/gazebosim/gz-physics/blob/gz-physics7/dartsim/src/EntityManagementFeatures.cc).
