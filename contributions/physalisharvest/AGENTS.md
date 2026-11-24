# AGENTS.md — PhysalisHarvest

> **Política operativa para agentes de desarrollo y revisión.** Repositorio: [`amayadiegoalejandro05/PhysalisHarvest`](https://github.com/amayadiegoalejandro05/PhysalisHarvest).\
> **Objetivo:** proteger la seguridad física, los contratos ROS 2, la evidencia científica y el trabajo de los cuatro frentes del macroproyecto.\
> **Estado de referencia:** el árbol común inicial contiene documentación, verificadores y CI; la existencia de carpetas de ROS 2, Gazebo o firmware **no** demuestra una implementación funcional.

## 0. Cómo interpretar estas instrucciones

Estas reglas aplican a Codex y a cualquier agente que analice, cree, edite o revise archivos de PhysalisHarvest. Están orientadas al macroproyecto de robot cosechador de uchuva (*Physalis peruviana* L.) del semillero SEIMA de la Universitaria Agustiniana. **No sustituyen las decisiones de los estudiantes, los responsables de cada subsistema, la institución, las licencias ni los controles de seguridad.**

Orden práctico ante una discrepancia:

1. Seguridad de personas/equipos, derechos de terceros y obligaciones institucionales o legales.
2. Instrucciones expresas y autorizaciones actuales de las personas responsables.
3. Contratos técnicos y decisiones de integración **aprobados** por los equipos afectados.
4. Este `AGENTS.md` y las instrucciones especializadas de la ruta afectada.
5. Documentación, convenciones y comportamiento observado en el código.

Si dos niveles son incompatibles, **no elijas silenciosamente**: identifica el conflicto, evita operaciones irreversibles y solicita una decisión humana. Una documentación antigua, un PR abierto, un comentario o un informe de agente no sustituyen evidencia independiente. Si código y documentación discrepan, investiga y reporta la diferencia; no declares que alguno está validado por defecto.

**Idioma:** trabajo, informes, PR y documentación del equipo en español. Identificadores de software, nombres convencionales de ROS/Git y asuntos de commit en inglés técnico. Evita textos publicitarios sobre capacidades no demostradas.

## 1. Preparación obligatoria antes de modificar

1. Identifica el entorno real: Windows/PowerShell, Ubuntu nativo, WSL 2, contenedor o runner; confirma si hay acceso a hardware. No asumas instalación de ROS 2 o Gazebo.
2. Confirma el repositorio y los remotos de lectura/escritura: deben corresponder a `amayadiegoalejandro05/PhysalisHarvest`. Comprueba rama, `HEAD`, upstream, `git status`, diff y trabajos sin confirmar; no alteres trabajo ajeno.
3. Lee `README.md`, `CONTRIBUTING.md`, las instrucciones de esta raíz y los documentos relevantes de `docs/`. Si editas un paquete bajo `ros2_ws/src/`, lee también su `AGENTS.md` local.
4. Consulta las fuentes **existentes**: `package.xml`, scripts, pruebas, configuración, interfaces y consumidores. No inventes archivos, drivers, versiones, tópicos, sensores o resultados.
5. Define un plan corto: propósito, archivos alcanzados, riesgo de interfaces/hardware/datos, pruebas y criterio de aceptación. No expandas la tarea por conveniencia.
6. Consulta referencias remotas actualizadas cuando esté permitido; si no puedes, informa que la comparación es **solo local**. `scripts/check_git_context.py` no ejecuta `fetch` por sí mismo.

Antes de cada commit/PR, usa el verificador existente con el destino real, por ejemplo:

```bash
python scripts/check_git_context.py --target feat/2WD --subsystem locomocion
python scripts/check_repository.py
python -m unittest discover -s tests -p 'test_*.py' -v
```

Estos comandos son para el **entorno Python disponible** y desde la raíz; en Linux puede corresponder `python3`. Un `SKIP` debe leerse, no confundirse con una prueba superada. Verifica permisos y conectividad antes de cualquier acción remota.

## 2. Identidad y límites del proyecto

**PhysalisHarvest** es una plataforma de investigación para **cosecha robótica selectiva de uchuva**, organizada en percepción/decisión, manipulador, locomoción e integración. `feat/2WD` es un **banco experimental** de locomoción, no un cuarto sistema autónomo validado.

| Área | Rama permanente | Responsabilidad principal | Lo que no debe declarar sin evidencia |
|---|---|---|---|
| Visión y decisión | `feat/vision` | RGB-D, detección de cáliz, recuperación XYZ, accesibilidad, selección, ruta cartesiana candidata y publicación ROS 2 | Centro de la baya, madurez, corte, cinemática del brazo o cosecha ejecutada |
| Brazo/manipulación | `feat/arm` | Modelo, cinemática, límites, factibilidad, control y efector cuando se implementen | Que una ruta propuesta por visión es ejecutable o físicamente completada |
| Locomoción | `feat/locomotion` | Plataforma móvil, control, localización y navegación según decisiones del equipo | Movimiento, odometría o autonomía todavía no observados |
| Banco 2WD | `feat/2WD` | Ensayos incrementales de comunicación, comandos, control básico y parada de un chasis de dos ruedas motrices | Navegación autónoma, localización métrica o integración definitiva con la base del robot |
| Integración transversal | Cambios coordinados hacia `main` | Interfaces ROS 2, marcos TF, launch conjunto, observabilidad, CI y ensayos productor/consumidor | Que recibir datos autoriza actuadores o verifica una cadena completa |

**Límite del trabajo de grado de visión/decisión:** producir y caracterizar objetivos 3D a partir de percepción, evaluar accesibilidad, escoger objetivos, proponer trayectorias cartesianas y comunicarlas por ROS 2. No exige construir un brazo, cortar frutos ni lograr una cosecha real. No traslades estas obligaciones a visión por defecto ni desplaces el alcance de los otros equipos.

La etiqueta YOLO `calyx` identifica el **cáliz visible**; no prueba por sí misma madurez, centro de fruta ni ubicación de pedúnculo. XYZ designa inicialmente un **punto superficial**. No mezcles campañas experimentales de modelos diferentes ni metas opcionales de Gazebo con criterios obligatorios de grado.

Los experimentos independientes de [`astra-rgbd-ros2-integration`](https://github.com/amayadiegoalejandro05/astra-rgbd-ros2-integration) pueden servir de antecedente **externo**, pero sus métricas y paquetes no constituyen resultados ni dependencias incorporadas automáticamente a PhysalisHarvest. El historial experimental descartado de antiguas ramas de visión **no** es evidencia activa de `feat/vision`.

## 3. Fronteras de software y propiedad de rutas

- `ros2_ws/src/robot_percepcion_decision/`: lógica propia de percepción/decisión.
- `ros2_ws/src/robot_brazo/`: lógica propia del brazo.
- `ros2_ws/src/robot_locomocion/`: locomoción, incluidos ensayos 2WD que después se integren explícitamente.
- `ros2_ws/src/robot_interfaces/`: contratos **compartidos**, no propiedad unilateral de un subsistema.
- `simulacion/`, `hardware/`, `firmware/`: modelos, diseño y código únicamente cuando existan versiones y condiciones comprobables.
- `.github/`, `scripts/`, `docs/interfaces/`, `docs/integracion/`, archivos raíz: impacto transversal; requieren revisión de los equipos pertinentes.

Las carpetas reservadas **no son paquetes ROS 2** hasta contener manifiestos y estructura válida. No dupliques software de otros equipos ni uses dependencias circulares para evitar una interfaz. Separa algoritmos puros de IO/cámara, red, serial, motores y simulador para permitir pruebas aisladas.

**Regla 2WD:** se desarrolla como experimento aislado de locomoción. No conviertas comandos de banco, calibraciones del vehículo o pines de un montaje provisional en contrato obligatorio del robot completo. Cualquier promoción desde `feat/2WD` hacia `feat/locomotion` o `main` necesita demostración, revisión y decisión explícita.

## 4. Ramas, PR y operaciones Git

Ramas permanentes autorizadas: `main`, `feat/vision`, `feat/arm`, `feat/locomotion`, `feat/2WD`. Aunque comiencen por `feat/`, **son ramas permanentes de área**, no ramas temporales descartables.

- Trabajo local de área: rama temporal corta nacida de su rama permanente, por ejemplo `experiment/2WD-serial-link` → PR a `feat/2WD`, o `feature/vision-targets` → PR a `feat/vision`.
- Documentación global, políticas, CI, contratos compartidos: rama temporal nacida de `main`, por ejemplo `chore/core-documentation-v2` → PR a `main`.
- Prefijos temporales reconocidos por el verificador actual: `feature/`, `fix/`, `experiment/`, `test/`, `chore/`. Usa nombres que expresen el área y el cambio. No asumas que `docs/` o `feat/otra-rama` sean válidos.
- Ramas de subsistema → `main` por PR revisado cuando corresponda integrar. Sincronización de `main` hacia áreas también por el procedimiento de `CONTRIBUTING.md`.
- Antes de PR: identifica destino, SHA fuente/base, diferencias, cambios compartidos, compatibilidad y resultados. Un merge temporal en CI no siempre representa el SHA de la rama fuente.

**Prohibido sin autorización expresa de la persona responsable:** `push`, merge, borrado remoto, cambios de protección, releases, instalación invasiva, movimientos físicos y operaciones equivalentes. Nunca uses `git push --force`, reescrituras de historial compartido, bypass de hooks, `git reset --hard` sobre trabajo ajeno ni sobrescribas cambios locales. Un agente no aprueba ni fusiona unilateralmente su propio PR.

Commits en inglés técnico, imperativo, usando Conventional Commits `type(scope): description`: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`, `ci`, `build`, `perf`, `style`, `revert`. Scopes sugeridos: `vision`, `arm`, `locomotion`, `2wd`, `interfaces`, `gazebo`, `firmware`, `docs`, `repo`, `ci`. Commits pequeños, verificables y sin cambios laterales. No cambies la identidad del autor Git.

## 5. Contratos ROS 2 antes de acoplar subsistemas

**Fuente actual:** [`docs/interfaces/contratos-ros2.md`](docs/interfaces/contratos-ros2.md) contiene una **propuesta**, no mensajes definitivos implementados. Antes de crear o cambiar `.msg`, `.srv`, `.action`, tópicos comunes o TF, acuerda y registra como mínimo:

| Dimensión | Pregunta obligatoria |
|---|---|
| Semántica | ¿Observación, objetivo aceptado, ruta candidata, solicitud de ejecución o confirmación? |
| Tipo y extremos | ¿Mensaje/servicio/action, productor, consumidor, nombre y versión? |
| Geometría | ¿Metros, radianes, ejes ópticos, `frame_id`, cadena TF y calibración? |
| Tiempo | ¿Sello de adquisición o recepción, reloj, validez máxima, sincronización y caducidad? |
| Entrega | ¿Frecuencia, QoS, profundidad de cola, pérdidas, reintentos y desconexión? |
| Calidad | ¿Datos inválidos, `NaN`, profundidad cero, incertidumbre, rechazo e indeterminación? |
| Control | ¿ID de correlación, aceptación, cancelación, timeout, feedback, parada y terminalidad? |
| Verificación | ¿Pruebas productor/consumidor, ejemplos y compatibilidad hacia atrás? |

Por defecto, posiciones en **metros** y ángulos en **radianes**. `camera_*_optical_frame`, `base_link`, `odom`, `map` y `world` **no son intercambiables**; transforma mediante TF válido, con tiempos y convenciones explícitas. Diferencia profundidad **Z axial** de distancia euclidiana. No fabriques transformaciones ausentes ni timestamps de captura: sellar un mensaje al publicarlo no equivale a adquirirlo en ese instante.

Un `geometry_msgs/msg/PointStamped` con XYZ ficticio puede ser una **prueba preliminar F0**; no es por sí solo el contrato definitivo de cosecha. Un receptor de mensajes no autoriza motores. Los consumidores deben poder rechazar datos inválidos, vencidos, fuera de marco o fuera de límites.

Cambios incompatibles: propuesta documentada, revisión de productores y consumidores, estrategia de versión/migración, actualización de pruebas y aprobación antes de integrar. No adaptes silenciosamente el consumidor para ocultar un cambio de contrato.

## 6. Ingeniería experimental y simulación

Emplea estados inequívocos y respaldados por evidencia: `PROYECTADO`, `IMPLEMENTADO`, `OBSERVADO_EN_SIMULACIÓN`, `MEDIDO_FÍSICAMENTE`, `VALIDADO`, `PENDIENTE`. `VALIDADO` requiere criterio previo, procedimiento reproducible y evidencia que cumpla el criterio; no es sinónimo de compilar, mostrar una interfaz o superar un mock.

Para cada experimento registra: objetivo e hipótesis; unidad experimental; entradas y versión; hardware/firmware/SDK/ROS/Gazebo; procedimiento; referencia **independiente**; configuración/semillas; repeticiones; métricas y unidades; incertidumbre y fallos; logs/artefactos; SHA y limitaciones. Conserva resultados desfavorables y rechazos válidos. Separa ajuste y evaluación cuando se calibra o entrena.

**Percepción RGB-D:** identifica cámara real, resoluciones, intrínsecos y registro RGB-depth; prueba profundidad válida y escala; estima sesgo, dispersión, error 3D y latencia frente a una referencia externa. No adoptes exactitud comercial como medición propia. Controla iluminación, distancia, oclusión y agrupación mediante escenas repetibles. En selección de objetivos, la **escena** es la unidad experimental principal; varios frutos en la misma escena no son réplicas independientes.

**Decisión:** compara una política de accesibilidad explícita con un baseline definido (p. ej. objetivo más cercano en 3D). Conserva tres resultados cuando proceda: `accesible`, `inaccesible`, `indeterminado`. No etiquetes éxito por seleccionar un objetivo sin demostrar el criterio geométrico.

**Planificación:** distingue propuesta cartesiana, evaluación de factibilidad del brazo y movimiento realmente observado. Un servo que responde a XYZ no demuestra que exista una trayectoria viable.

**Gazebo:** identifica sensores sintéticos, geometría de colisión, motores ideales, reloj y fuentes de verdad. No permitas que el algoritmo use mallas/poses internas del simulador y luego presentes ese resultado como percepción autónoma. Distingue mock, replay, ejecución simulada y medición real. Conservar una escena histórica no valida transferencia Sim2Real.

## 7. Seguridad y autorización de actuadores

**Política predeterminada: ningún agente debe producir movimiento físico como efecto colateral de instalar, compilar, auditar o ejecutar tests.** La habilitación de hardware es una acción explícita, supervisada y separada del modo de pruebas.

En el banco `feat/2WD` adopta una progresión de ensayo **propuesta**, no una lista de acciones ya realizadas:

1. Inventario y verificación de alimentación, controlador de motores, pinout, sentidos, conexión de masas y método de desconexión; no asumas componentes o parámetros concretos.
2. Verificación de protocolo y validación con motores desconectados, mock o cargas seguras.
3. Prueba supervisada con el vehículo inmovilizado/ruedas libres cuando el montaje permita hacerlo con seguridad.
4. Movimiento de corta duración, límites conservadores, área despejada y operador con parada física disponible, solo mediante autorización.
5. Pérdida de enlace, comando mal formado, watchdog, expiración, parada, recuperación y prevención de reactivación inesperada.

Antes de energizar motores exige: alimentación y protecciones adecuadas, driver compatible, paro/desconexión accesible, límites de velocidad/aceleración acordados, timeout/fail-safe definido, activación intencional y procedimiento de emergencia. No fija valores arbitrarios de PWM, pines, velocidad o corriente. En un fallo de comunicación, el sistema debe inhibir nuevas órdenes y tender a estado seguro conforme al diseño **efectivamente probado**; no declares paro instantáneo si no está instrumentado.

Para brazo/efector aplica la misma disciplina: límites de movimiento, colisión, supervisión, autorización explícita, parada, feedback real y rechazo de comandos. Ninguna detección visual debe accionar directamente motores sin un contrato y una validación de seguridad.

## 8. Pruebas y GitHub Actions

La CI existente en [`.github/workflows/ci.yml`](.github/workflows/ci.yml) se ejecuta en push a `main` y en PR dirigidos a `main` o a las ramas permanentes. Comprende:

- **Verificación estática y pruebas:** scripts de repositorio, contexto Git y unit tests existentes.
- **Detectar paquetes ROS:** busca `package.xml` bajo `ros2_ws/src/`; si no los encuentra, declara **SKIP**, no compilación exitosa del robot.
- **ROS 2 Jazzy:** compila y prueba los paquetes; solo se ejecuta cuando existen manifiestos.
- **Resumen y trazabilidad:** SHA, ramas, estado de jobs y limitaciones declaradas.

La **prueba controlada de puerta ROS** está en [`.github/workflows/ros-gate.yml`](.github/workflows/ros-gate.yml): ejercita la infraestructura de detección de fallos con un paquete **temporal y aislado**, no con paquetes de PhysalisHarvest, y solo se ejecuta cuando cambian sus scripts o de forma manual.

Cuando existan paquetes reales, ejecuta `colcon build`, `colcon test` y `colcon test-result --verbose` desde el entorno adecuado, además de pruebas unitarias, integración/launch y contrato que correspondan. No agregues paquetes de muestra permanentes para hacer verde la CI. Una prueba que no pudo ejecutarse es `NOT RUN`/`SKIP`, nunca `PASS`. Revisa logs y artefactos antes de afirmar la causa de un fallo.

**Punto de salida de una tarea:** tests relevantes ejecutados y registrados; cambios verificados respecto a base; no hay secretos ni binarios accidentales; interfaces y documentación coherentes; riesgos y bloqueos explícitos. `main` sin protección GitHub o una check no obligatoria son riesgos de gobernanza, no medidas de seguridad implementadas por escribir este archivo.

## 9. Datos, dependencias, licencias y uso de IA

- No introduzcas contraseñas, tokens, números de serie sensibles, datos privados o archivos `.env` reales. Revisa el diff **antes** de confirmar; `.gitignore` no elimina secretos ya rastreados.
- No subas automáticamente datasets, rosbag2, vídeos crudos, capturas no autorizadas, pesos grandes, ejecutables, modelos CAD o calibraciones específicas del dispositivo. Define primero procedencia, permiso, almacenamiento, hash, formato y política de acceso.
- No entrenes un modelo nuevo ni sustituyas YOLO/SDK/firmware sin objetivo, baseline, control experimental y aprobación. Revisa compatibilidad de versiones y licencias antes de añadir dependencias.
- La licencia general del macroproyecto permanece **pendiente de decisión sobre titularidad y terceros**. No crees `LICENSE` ni declares MIT/Apache-2.0 por inferencia. Examina especialmente obligaciones de Ultralytics (AGPL/comercial) y licencias de modelos, datos y hardware sin asumir que un monorepo pueda distribuirse íntegramente bajo una única licencia.
- Mantén la trazabilidad real de asistencia de IA en [`docs/AI_USAGE.md`](docs/AI_USAGE.md) y [`docs/ai_usage.json`](docs/ai_usage.json), con archivos afectados, intervención humana y verificaciones. No registres trabajo no realizado.
- No atribuyas autoría Git a un agente ni añadas `Co-authored-by` de IA o créditos promocionales opcionales. **Sí** conserva declaraciones institucionales, atribuciones y licencias obligatorias; no ocultes intervención de IA.
- Identifica los datos sintéticos y el contenido multimedia generado con IA conforme a la política vigente del proyecto; no hagas pasar material generado por captura experimental.

## 10. Protocolo de entrega del agente

Cada tarea debe concluir con un resumen comprobable, proporcional al tamaño del cambio:

```text
Objetivo y alcance:
Rama / HEAD / destino / base comprobada:
Archivos afectados y por qué:
Contrato o dependencia impactada:
Entorno y comandos ejecutados:
Resultados: PASS / FAIL / SKIP / NOT RUN / MOCK ONLY:
Evidencia (logs, PR, artefactos, SHA):
Seguridad y datos: medidas, límites, autorizaciones:
Riesgos, discrepancias y decisiones pendientes:
Siguiente paso recomendado:
```

Si algo no fue probado o no tienes acceso al equipo, indícalo literalmente. No prometas validaciones futuras como si ya hubieran ocurrido. Para resultados críticos, solicita revisión humana e idealmente reproducción independiente. Un informe de Codex no es una auditoría externa.

**Principio rector:** *una cadena demostrable, segura y reproducible vale más que una demo vistosa sin separación entre propuesta, simulación y medición.*
