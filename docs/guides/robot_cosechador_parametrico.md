# Robot cosechador: configuración, CAD y pruebas

El robot se describe mediante `robot-spec/1.0` en JSON. El resolvedor produce
un `ResolvedRobot` inmutable en SI con hash de contenido. SDF, FK/IK, límites,
marcos, colisiones, contrato y auditoría consumen ese mismo resultado.
El perfil del robot es independiente del cultivo, mundo y objetivos.

El contrato actual del cosechador admite brazos revolutos; rechaza un brazo
prismático antes de exportar sus campos en radianes. Las articulaciones
prismáticas pasivas y de mordaza mantienen sus coordenadas en metros.
La tarea IK debe recibir el estado auxiliar observado cuando éste afecte la
cadena, y la comprobación de colisiones usa ese mismo estado. Las poses y
dimensiones de obstáculos externos deben ser válidas antes de admitir una
postura. La [corrección del PR 1](../reports/correcciones_revision_pr1_2026-11-24.md)
documenta los casos negativos y las regresiones.

## Preparar una revisión

```powershell
python scripts/prepare_robot_model.py --profile proxy_v1 --output outputs/robot_proxy_nuevo
python scripts/prepare_robot_model.py --profile proxy_v1 --overrides configs/robots/overrides/proxy_arm_length_040.json --output outputs/robot_longitud_nueva
python scripts/prepare_robot_model.py --profile proxy_v1 --overrides configs/robots/overrides/proxy_arm_mass_2kg.json --output outputs/robot_masa_nueva
python scripts/prepare_robot_model.py --profile proxy_v1 --overrides configs/robots/overrides/proxy_shoulder_effort_30.json --output outputs/robot_actuador_nuevo
```

Usar salidas nuevas. `robot_resolved.json` contiene los valores efectivos;
`robot_contract.json`, los nombres y capacidades; `model.sdf`, la descripción;
`preparation_report.json`, hashes y comprobaciones. Preparar XML no ejecuta
Gazebo: el reporte conserva `NO EJECUTADO` para las pruebas nativas.
Un perfil incompleto produce un bloqueo concreto y no genera un robot ficticio.

Los ejemplos anteriores alteran el proxy geométrico y son ensayos de software,
no revisiones del CAD ni mediciones de hardware. El adaptador histórico de
`HarvesterConfig` mantiene los paquetes anteriores identificados por su contrato.

## Cómo modificar parámetros

Un override contiene una ruta JSON Pointer, `value` y `provenance`. La ruta debe
estar declarada en `parameter_metadata` con una clase de actualización. Ejemplo:

```json
{
  "/parameters/upper_arm_mass_kg": {
    "value": 2.0,
    "provenance": {
      "status": "estimado",
      "source": "Ensayo controlado del proxy, no balanza",
      "revision": "ejemplo-1",
      "method": "Duplicar la masa para estudiar la respuesta dinámica"
    }
  }
}
```

Si procede de una balanza, usar `medido` e identificar instrumento, fecha,
componente pesado, unidad, precisión y registro. Los estados aceptados son
`medido`, `derivado_de_CAD`, `ficha_tecnica`, `estimado` y `pendiente`.
La incertidumbre desconocida se conserva como desconocida, nunca como cero.

| Cambio | Lugar canónico y propagación | Pruebas afectadas |
| --- | --- | --- |
| Montaje del brazo | Transformación del joint fijo de montaje; actualizar su procedencia. Regenerar posiciones, colisiones y contrato | Landmarks, FK, holguras, estabilidad y alcance |
| Longitud de eslabón | Parámetro geométrico y sus `derived_values`. En CAD congelado requiere nueva exportación con firma coincidente | Integridad de malla, dimensiones, FK/IK y workspace |
| Rueda o ancho de vía | Dimensiones de rueda, poses articulares y parámetros de conducción vinculados a los mismos valores | Avance, giro, parada, fricción y autocontactos |
| Motorreductor | Actuador, transmisión y límites efectivos; diferenciar eje motor y salida de transmisión | Saturación, velocidad y seguimiento con carga |
| Masa o batería | Masa, CoM y tensor en el marco del link; incluir desplazamiento del componente mediante ejes paralelos | Gravedad, estabilidad y esfuerzo requerido |
| Cámara | Sensor, marco de montaje y marco óptico; intrínsecos, tasa y rango explícitos | Pose/FOV/imagen o profundidad observados |
| Gripper | Joints, carrera, relación, cuerpos de colisión, `tcp`, `grasp_center` y `cut_point` | Apertura/cierre, hueco de captura, FK, guardas e interferencias |

Las rutas concretas de arrays dependen del perfil: localizar el elemento por
`name` y registrar su JSON Pointer en `parameter_metadata`. No modificar a mano
el SDF ni un valor generado por `derived_values`: cambiar su parámetro origen.
El resolvedor rechaza overrides de valores derivados y mallas obsoletas.

`runtime` identifica sólo cambios con interfaz soportada y registro temporal;
no hace que el resolvedor modifique un Gazebo en marcha. `model_regeneration`
exige reconstruir paquete y planes. `cad_reexport` exige una nueva revisión de
geometría; el override aislado se rechaza. Desplazar un conjunto rígido puede
permitir regeneración, pero fabricar un soporte distinto requiere CAD nuevo.

## Incorporar una revisión CAD

1. Inventariar revisiones y copiar los IAM/IPT con sus referencias. Conservar
   originales privados fuera de Git y comparar SHA256 antes/después.
2. Ejecutar el [exportador Inventor](exportacion_cad_inventor_robot.md). No
   sustituir V3 por el STEP V2. Las piezas estándar recuperadas de biblioteca
   o fabricante requieren un registro de sustitución, no identidad inventada.
3. Relacionar ocurrencias con conjuntos rígidos y links. Las matrices CAD ya
   llevan traslaciones en metros. Distinguir postura del ensamble de cero de
   encoder; comprobar ejes, signos, límites y los montajes entre subensambles.
4. Derivar visuales, colisiones e inercias por separado. Mantener aberturas de
   gripper/cesta. Comprobar masa, CoM, transformación de tensor y datos ausentes;
   el material macizo del CAD no acredita relleno o componentes internos.
5. Cambiar revisión, hashes y enlaces de evidencia en un perfil nuevo. Preparar
   con `--asset-root` explícito; todas las mallas se verifican antes de copiarlas.
6. Comparar landmarks y postura cero, validar SDF y ejecutar las pruebas
   geométricas/dinámicas antes de promover resultados de cosecha.

`prepare_cad_inspection.py` permite inspeccionar las ocurrencias exportadas en
un mundo estático, conservando cada raíz CAD independiente. La opción
`--allow-partial-inspection` muestra faltantes y nunca habilita un perfil físico.
El desplazamiento entre conjuntos de esa lámina es presentación, no un montaje.

## Control y evidencia nativa

El brazo usa PID de posición por fuerza y las ruedas PID de velocidad por
fuerza. No usar seguimiento cinemático ideal para validar actuadores. Las
ganancias pertenecen al controlador; torque, velocidad y transmisión al modelo
físico; timestep y opciones del backend al experimento.

`RobotTelemetrySystem` toma `JointForceCmd` después de los controladores en
PreUpdate (prioridad 100) y observa posición, velocidad y wrench transmitido en
PostUpdate. Los comandos no son torque de motor medido. El wrench es una
respuesta mecánica simulada en el marco de la articulación. Las ventanas
registran picos y pasos saturados, con banderas explícitas de disponibilidad.

```bash
bash scripts/build_harvest_plugin.sh outputs/real_harvester_plugin_build
python3 scripts/probe_robot_actuation.py --plugin-dir outputs/real_harvester_plugin_build --output outputs/probe_actuacion_nuevo
PYTHONPATH=src:. python3 -m unittest discover -s tests -p 'test_robot*.py'
PYTHONPATH=src:. python3 -m unittest discover -s tests -p 'test_harvest*.py'
python3 scripts/validate_repository_context_graph.py
```

El probe de actuación usa un péndulo de ingeniería identificado, no el CAD.
Comprueba carga, velocidad/esfuerzo y un actuador deliberadamente insuficiente.
Su PASS no valida el brazo real ni sustituye pruebas del perfil seleccionado.

La cosecha conserva corte/retención ideales. El nuevo contrato separa TCP,
agarre y corte; las guardas observan marcos y orientación. El origen del link
de soporte no es automáticamente ninguno de esos puntos. Cinco articulaciones
no garantizan una pose arbitraria de seis GDL. Una tarea inalcanzable queda
registrada sin mover frutos, ramas ni tolerancias.

Conservar tres arbustos y tres objetivos para V8, y seis para el manifiesto
histórico correspondiente. Tras smoke y un ciclo, ejecutar la misión completa
y sólo si pasa sus tres repeticiones independientes. Cerrar con evaluación
separada de CAD, prototipo, dinámica, sensores y cosecha. Nunca llamar calibrado
contra hardware a un modelo contrastado únicamente contra CAD.

## Paquete CAD extraído el 23 de noviembre

El importador `scripts/prepare_cad_robot.py` agrupa hojas físicas, aplica cada
transformación una sola vez y suma tensores en el centro de masa común mediante
Steiner. Conserva las excepciones de asignación del engranaje del encoder y la
polea de salida. Los cinco ejes usan el orden yaw–hombro–codo–pitch–roll observado
en el CAD. La postura guardada es q=0 de simulación, sin equivalencia acreditada
con el cero de los encoders.

```text
python scripts/prepare_cad_robot.py --inventory outputs/real_harvester_cad/export_winding_repaired_01/cad_inventory.json --appearance-inventory outputs/real_harvester_cad/inventory_appearance_01/cad_inventory.json --output outputs/robot_cad_nuevo
python scripts/probe_robot_parameters.py --profile outputs/robot_cad_nuevo/cad_diagnostic_frozen.json --asset-root outputs/robot_cad_nuevo --output outputs/parametros_cad_nuevo
```

El paquete produce dos perfiles distintos: `cad_nominal.json`, que conserva los
pendientes críticos, y `cad_diagnostic_frozen.json`, admisible para pruebas de su
alcance reducido. El segundo congela suspensión/pinza, usa cajas por pieza para
colisión y techos de esfuerzo estimados. No tiene capacidad `native_harvest`;
el preparador de misiones lo rechaza. `complete` en ese perfil significa que sus
entradas computacionales están completas, no que el robot esté validado.

`configs/robots/cad_diagnostic_assumptions.json` contiene el montaje estimado a
partir de la indicación del usuario y la foto del prototipo parcial: centrado
lateralmente y ligeramente hacia atrás. Las distancias, límites ±15°, ganancias,
fricción y capacidades diagnósticas llevan procedencia de estimación. Ninguno
se convierte en medido al generar el paquete.

La API pública está en `uchuva_gazebo.robot`: `resolve_robot`, `build_robot_sdf`,
`forward_kinematics`, `solve_task`, `collision_shapes` y `robot_contract`.
`solve_task` conserva residuales y comprueba colisiones de la postura resultante;
un rechazo conservador no demuestra inviabilidad global ni seguridad de una
trayectoria. Los estados de mecanismos articulados requieren su adaptador.

El diagnóstico de parámetros mueve el montaje, agrega una carga hipotética
de 1 kg con posición explícita, reduce un techo de actuación y rechaza una
longitud incompatible con CAD. Esa carga ilustra cómo incorporar una batería
cuando se conozcan sus propiedades; no representa una batería instalada.

Las pruebas nativas deben ejecutarse en WSL con el perfil exacto y su directorio
de mallas. Cada una guarda su protocolo antes de arrancar: `probe_robot_kinematics.py`,
`probe_cad_mobility.py`, `probe_robot_self_collision.py` y
`probe_robot_interaction_frames.py`. Un fallo de seguimiento no permite aumentar
tolerancias, y la concordancia FK por sí sola no acredita estabilidad dinámica.

## Revisiones de control y mecanismos

`configs/robots/cad_v8_acceptance_lock.json` conserva las plantas, los seis
hashes de entrada, los tres objetivos y los protocolos anteriores. Verificar
la integridad antes de preparar una misión nueva:

```text
python scripts/verify_cad_v8_acceptance.py --manifest outputs/harvest_pilot_v8_c4_gui/manifest.json
```

El ajuste `cad_control_revision_01.json` deriva el control del brazo de las
inercias y cargas gravitacionales del CAD. Por ejemplo, el hombro requiere
aproximadamente 7,12 N·m en la postura guardada, por encima del techo diagnóstico
anterior de 3 N·m. Los nuevos techos siguen siendo hipótesis de esfuerzo
disponible en simulación; no acreditan la capacidad continua del hardware.
`cad_drive_revision_02.json` añade acción integral limitada al control por
esfuerzo de las ruedas. Cada revisión conserva su resultado independiente.

`scripts/cad_mechanisms.py` separa portarruedas, amortiguadores, engranajes,
bielas y mordazas. Comprueba conservación de hojas CAD, masa, centro de masa,
tensor global y geometría en la postura de referencia. Las precargas de los
cuatro muelles se estiman por equilibrio y trabajo virtual, con procedencia
explícita. La espiral visual permanece rígida: su deformación no está modelada.

El campo opcional `closures` describe la partición de masa e inercia de un
cuerpo entre el link físico y un auxiliar coincidente sin geometría duplicada.
La articulación móvil pertenece al árbol SDF; `ClosedLoopSystem` solicita la
reunión física mediante una restricción fija nativa. Así se conserva el cierre
sin un segundo padre SDF ni teletransporte. La implementación se apoya en
[AttachFixedJoint de gz-physics 7.8](https://github.com/gazebosim/gz-physics/blob/gz-physics7_7.8.0/dartsim/src/JointFeatures.cc).
Cada cierre debe comprobarse con poses nativas; la FK del árbol por sí sola
también podría pasar aunque faltara la restricción de cierre.

`gear_couplings` modela la transmisión como acoplamiento elástico finito, con
ratio, rigidez, amortiguamiento y paso máximo explícitos. Un único PID acciona
el driver. El follower es pasivo. `GearCouplingSystem` aplica momentos internos
a los cuerpos y sus reacciones a los padres; no escribe `JointForceCmd`.
Por tanto el observador conserva la separación entre comando de actuador,
reacción del acoplamiento y wrench transmitido. La flexibilidad elegida y las
ganancias no son mediciones del engranaje real.

El campo `physics` identifica backend, solucionador y paso máximo. El contrato
1.1 publica esos requisitos y los mecanismos; el contrato histórico sin ellos
conserva su versión 1.0. Los lazos deben probarse inclinados además de alineados:
el [problema documentado de DART con lazos oblicuos](https://github.com/gazebosim/gz-physics/issues/719)
motivó ensayos separados con PGS. Cambiar el solucionador o el paso exige
repetir las pruebas del perfil exacto. Un timeout computacional es un resultado
incompleto, nunca un PASS de la parte que no llegó a ejecutarse.

La planificación CAD utiliza una altura de base explícita, transformaciones
completas de posición y dirección y una postura de transporte articular común.
La corrección durante ejecución parte del estado articular observado. No se
supone que una solución de cinco GDL admita cualquier orientación; cada objetivo
conserva sus residuales, obstáculos y rechazos. El corte y la retención siguen
siendo ideales aunque se ensayen los contactos de las mordazas por separado.
