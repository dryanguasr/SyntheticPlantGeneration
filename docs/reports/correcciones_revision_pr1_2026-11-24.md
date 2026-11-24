# Correcciones de la revisión del PR 1

La revisión del corte `068f3d890c7d6a009033e5fd75f366dffeb207b6` encontró
cuatro defectos de software y una discrepancia entre la compilación y los
lanzadores ROS. Este registro corresponde a su corrección en
`codex/integracion-physalisharvest-20261124`. La fusión a `main` sigue pendiente
de revisión del usuario.

## Cambios y criterios de regresión

| Punto | Corrección | Regresión exigida |
| --- | --- | --- |
| Obstáculos inválidos | Comprobar geometrías, dimensiones, poses y separaciones antes de admitir una postura | Rechazar NaN, infinitos, dimensiones no positivas y cuaterniones inválidos; mantener el rechazo de obstáculos válidos que ocupan el robot |
| Estado auxiliar en IK | Compartir las coordenadas auxiliares observadas entre la FK del solver, el resultado y la comprobación de colisiones | Un montaje pasivo desplazado no puede producir éxito con residuales de la postura nominal; validar nombres, finitud y límites |
| Carrera de mordaza | Muestrear la coordenada prismática con el brazo y los demás auxiliares fijos en cierre y apertura | Rechazar una transición cuyos extremos cumplen el margen y cuyo punto intermedio lo incumple; comprobar también el fruto retenido |
| Unidades de brazo | Rechazar expresamente brazos no revolutos en el contrato actual del cosechador antes de emitir campos en radianes | Un perfil descriptivo prismático no genera un contrato o informe etiquetado en radianes; la mordaza prismática conserva metros |
| Lanzamiento ROS | Utilizar una entrada canónica fuera del snapshot, con un único directorio de compilación e instalación configurable | La compilación y los comandos de consulta usan el mismo setup; cubrir instalación ausente, rutas con espacios e inspección sin ejecutar hardware |

El modelo descriptivo puede conservar articulaciones prismáticas pasivas o
de mordaza. El contrato actual de brazo y su solver de tarea mantienen el
alcance de cinco ejes rotativos. Admitir un brazo prismático en ese contrato
requeriría una revisión explícita de unidades, campos y consumidores.

El muestreo de la mordaza conserva el umbral geométrico y la política de
contactos de la escena. Su resolución es una heurística de ingeniería
declarada; no certifica una trayectoria continua ni un contacto físico real.
Los planes históricos no se consideran automáticamente revalidados por
estas correcciones.

## Preservación y alcance

Los 107 archivos del aporte `PhysalisHarvest` permanecen intactos y con sus
términos originales. La entrada ROS del proyecto principal consume los nodos
preservados y mantiene sus protocolos. Las aplicaciones históricas Windows
con rutas internas a su workspace se conservan como referencia; no se
presentan como lanzadores del build externo.

No se instalaron dependencias, modificaron plantas o umbrales de aceptación,
ni ejecutaron cámara, serie, motores o una nueva misión de cosecha.
Los pendientes de TF calibrada, sincronización, puente ROS/Gazebo y validación
física siguen explícitos en el informe de conciliación.

## Verificación de esta corrección

La regresión conjunta ejecutó **367 pruebas**, con cero fallos, errores u
omisiones, en 85,93 s bajo Ubuntu 24.04/WSL y Python 3.12.3. Incluye 31 pruebas
añadidas: once de API/estado auxiliar, ocho de mordaza, tres de unidades y
nueve del lanzador. Se incluyen controles válidos y casos negativos; no se
afirma que todos los controles válidos fallaran en la versión anterior.

| Comprobación nueva | Resultado | Evidencia local |
| --- | --- | --- |
| Regresión conjunta de robot, cosecha, CAD, interfaces e integración | 367 PASS; 0 fallos, errores u omisiones | `outputs/pr1_fix_validation/regression.{json,log}` |
| Regresiones de API contra el corte anterior `068f3d8` | Detectan los defectos originales; las mismas pruebas pasan con la corrección | `outputs/pr1_fix_regressions/canonical/{baseline_tests,fixed_tests}.{json,log}` |
| Compilación mediante el lanzador canónico | Dos paquetes ROS 2 compilados correctamente, 6,72 s | `outputs/physalisharvest_validation/fix_ros_launcher/log/` |
| Consulta de estado mediante esa misma instalación | PASS; `estado -- --once` recibió el mensaje de prueba y terminó con código 0 | `outputs/physalisharvest_validation/fix_ros_launcher/{launcher_smoke.json,launcher_smoke.log,smoke_launcher.py}` |
| Integridad del aporte | PASS, 107 archivos originales | `python scripts/verify_physalisharvest_snapshot.py` |
| Mapa de contexto | VALID, 160 nodos y 268 relaciones | `python scripts/validate_repository_context_graph.py` |

El ensayo ROS usó un publicador de texto sintético en localhost, dominio 97.
No accionó la cámara, serie, servicio de armado ni motores. Los resultados
previos de dinámica V8 y de compilación C++ no se presentan como ejecuciones
nuevas de esta corrección. Las tres revisiones cruzadas de código confirmaron
la corrección de los hallazgos sin añadir bloqueos técnicos en estos cambios.

La [guía de integración](../guides/integracion_physalisharvest.md) describe el
lanzador, `--output-root`, la inspección sin procesos y las aplicaciones
históricas que mantienen sus rutas originales. Los logs, binarios y fuentes
de reproducción temporales permanecen en `outputs/`, fuera de Git.
