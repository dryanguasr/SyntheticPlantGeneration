# Contributing to PhysalisHarvest

> **Guía de colaboración, integración y calidad.** Este es un macroproyecto de investigación: un PR no se acepta por lucir terminado, sino por respetar su alcance, contratos, seguridad y evidencia verificable.

**Lee primero:** [README](README.md) · [Política para agentes](AGENTS.md) · [Contratos ROS 2 propuestos](docs/interfaces/contratos-ros2.md) · [Verificación local](docs/pruebas/verificacion-local.md) · [CI](docs/pruebas/ci.md).

## 1. Modelo de colaboración

La rama `main` es la línea integrada. Las cuatro ramas `feat/*` son **permanentes** y tienen responsables funcionales distintos, aunque compartan nomenclatura con funcionalidades:

| Base y destino habitual | Área | Trabajo propio |
|---|---|---|
| `feat/vision` | Percepción y decisión | RGB-D, detección de cáliz, XYZ superficial, accesibilidad, selección, trayectorias candidatas |
| `feat/arm` | Manipulador | Cinemática, límites, aceptación/rechazo y control supervisado |
| `feat/locomotion` | Locomoción | Plataforma principal, estado, control, localización y navegación futura |
| `feat/2WD` | Banco experimental | Comunicaciones, motores, protocolo, seguridad y pruebas del chasis 2WD |
| `main` | Integración compartida | Contratos, TF, CI, gobernanza, documentación principal, integración aceptada |

El experimento 2WD **no es sinónimo** de locomoción definitiva. Su integración hacia `feat/locomotion` requiere un PR específico, revisión y pruebas. Una orden aceptada por el controlador no prueba desplazamiento físico ni navegación.

### Nombres de ramas temporales

Crea ramas cortas a partir de la **rama destino** y expresa el cambio en su nombre:

| Rama temporal | Base y PR destino |
|---|---|
| `feature/vision-depth-validity` | `feat/vision` |
| `fix/arm-reject-stale-targets` | `feat/arm` |
| `test/locomotion-feedback` | `feat/locomotion` |
| `experiment/2WD-serial-protocol` | `feat/2WD` |
| `chore/core-documentation-v2` | `main` |

Prefijos permitidos por el verificador actual: `feature/`, `fix/`, `experiment/`, `test/`, `chore/`. **No** crees una rama temporal denominada `feat/otro-modulo` ni asumas que `docs/` es válido. El nombre de rama no determina automáticamente la propiedad de los archivos: revisa el impacto real.

## 2. Flujo local — contribución normal

Los ejemplos siguientes usan Git desde la raíz del repositorio, tanto en Git Bash/Ubuntu como en PowerShell, salvo donde se indique. Cambia rama, nombre y área según la tarea.

**Antes de empezar:** preserva cualquier trabajo en curso. No ejecutes `git switch` si puede sobrescribir cambios locales.

```bash
# 1. Comprobar dónde estás y qué tienes sin confirmar.
git remote -v
git status --short --branch
git branch -vv

# 2. Actualizar referencias solo con autorización y acceso a red.
git fetch origin

# 3. Crear una rama de trabajo 2WD desde su base correcta.
git switch -c experiment/2WD-serial-protocol origin/feat/2WD

# 4. Inspeccionar contexto; los SKIP son informativos, no PASS.
python scripts/check_git_context.py --target feat/2WD --subsystem locomocion
```

Implementa cambios pequeños y revisa su alcance. No instales dependencias ni conectes hardware si la tarea es solo documental o estática.

```bash
# 5. Comprobar la modificación y ejecutar las pruebas disponibles.
git diff --check
python scripts/check_repository.py
python -m unittest discover -s tests -p 'test_*.py' -v

# 6. Revisar antes de hacer staging.
git status --short
git diff
```

Los comandos asumen que `python` corresponde al intérprete utilizable; en Ubuntu puede ser `python3`. **No declares aprobado lo que no pudiste ejecutar.** Los módulos ROS todavía deben incorporarse como paquetes reales; `colcon` solo aplica si se dispone del entorno y de manifiestos correspondientes.

Después de inspeccionar los archivos, prepara commits atómicos:

```bash
git add -- "ruta/al/archivo-verificado"
git diff --cached --check
git diff --cached --stat
git commit -m "test(2wd): cover serial command validation"

# Publicación únicamente cuando el responsable la autorice.
git push -u origin experiment/2WD-serial-protocol
```

Abre un PR con **base `feat/2WD`** para este ejemplo, no `main`. El PR debe relacionar implementación y pruebas, mostrar el efecto en interfaces y describir fallos sin maquillarlos. La fusión final siempre requiere revisión humana.

## 3. Flujo especial — documentación y políticas globales

`AGENTS.md`, `CONTRIBUTING.md`, el README principal, workflows, verificadores Git y contratos comunes se trabajan **desde `main`**, no como modificaciones particulares del banco 2WD.

Si tu clon fue abierto originalmente en `feat/2WD`, crea primero una rama temporal desde `main`:

```powershell
# PowerShell, desde la carpeta raíz del clon de PhysalisHarvest.
git status --short --branch
git fetch origin
git switch -c chore/core-documentation-v2 origin/main
```

**Solo después** sustituye los tres Markdown de la raíz. A continuación revisa `git diff` y ejecuta los verificadores. Documenta el uso de IA realmente realizado en `docs/AI_USAGE.md` y `docs/ai_usage.json`, según la política vigente. No se atribuye coautoría Git a la IA.

```powershell
python scripts/check_repository.py
python scripts/check_git_context.py --target main
python -m unittest discover -s tests -p "test_*.py" -v
git diff --check
git status --short
```

Antes del commit revisa todos los cambios; incorpora exclusivamente los archivos intencionales. Mensaje sugerido:

```bash
git commit -m "docs(repo): establish engineering documentation"
```

Tras autorización, publica la rama y abre PR **hacia `main`**. Luego de su revisión y merge, sincroniza cada rama permanente por el flujo documentado en [verificación local](docs/pruebas/verificacion-local.md). No hagas merges directos a todas las ramas por comodidad: evita pisar avances de otros equipos.

## 4. Commits y alcance del PR

Usa el formato **Conventional Commits** en inglés técnico: `type(scope): imperative summary`. Tipos habituales: `feat`, `fix`, `test`, `docs`, `refactor`, `ci`, `chore`, `build`, `perf`, `style`, `revert`. El asunto debe ser conciso y sin punto final; añade cuerpo cuando haya una decisión o ruptura de compatibilidad.

Ejemplos:

```text
feat(vision): publish stamped surface points
test(interfaces): reject unknown coordinate frames
fix(arm): reject expired target proposals
test(2wd): verify watchdog timeout handling
docs(repo): explain research validation boundaries
ci(repo): report ROS package coverage by area
```

No cambies `git config user.name` o `user.email` para simular autoría. No añadas `Co-authored-by` de IA. Respeta licencias y atribuciones obligatorias.

Un PR debe tener **un propósito principal**. Si cambia un contrato transversal, no escondas esa modificación dentro de una mejora local. Coordina definición, productores, consumidores, tests, ejemplos y documentación en uno o varios PR planificados explícitamente.

## 5. Plantilla de evidencia para PR

Completa la [plantilla del repositorio](.github/PULL_REQUEST_TEMPLATE.md) e incluye, según el alcance:

| Campo | Qué registrar |
|---|---|
| Fuente y destino | Ramas, SHA y versión de `main` usada como referencia |
| Propósito | Problema, alcance, criterio verificable de aceptación |
| Cambios | Archivos, paquetes y comportamiento modificado |
| Interfaces | Tópicos, tipos, TF, unidades, tiempo, QoS, consumidores afectados |
| Entorno | SO, Python, ROS 2, Gazebo, firmware, hardware y dependencias realmente disponibles |
| Pruebas | Comandos, `PASS`, `FAIL`, `SKIP`, `NOT RUN`, `MOCK ONLY` y logs |
| Evidencia | Datos de referencia, artefactos, método, incertidumbre y versión del código |
| Riesgos | Seguridad física, fallos de enlace, regresión, licencias, datos y bloqueos |
| Revisión | Equipos afectados y decisión humana sobre integración |

Para documentación pura no inventes mediciones físicas ni ejecutes motores. Para firmware, drivers o actuadores, explica qué comprobaciones se hicieron **sin energía** y cuáles requirieron supervisión.

## 6. Política de contratos ROS 2

Los intercambios entre visión, brazo y locomoción permanecen en estado **propuesto** en [contratos ROS 2](docs/interfaces/contratos-ros2.md). **No** elijas nombres o mensajes globales por cuenta propia. Para cada intercambio acuerda:

- Productor y consumidor; mensaje, tópico/servicio/action y semántica.
- Posiciones en metros; ángulos en radianes; `frame_id`, ejes, TF y calibración.
- Timestamp de **adquisición** frente a recepción/publicación, sincronización y vigencia.
- Frecuencia, QoS, durabilidad, pérdidas, reintentos y comportamiento ante desconexión.
- Estados: observado, seleccionado, candidato, aceptado/rechazado, ejecutando, completado, fallido y cancelado.
- ID de correlación, feedback y criterios de rechazo verificables.
- Ejemplos, pruebas productor/consumidor y plan de compatibilidad.

Una ruta cartesiana candidata de visión **no es una orden ejecutable**. Una prueba `PointStamped` con XYZ ficticias es prueba de transporte, no localización 3D de una uchuva. La recepción por un nodo no valida seguridad ni movimiento.

Acordar contratos requiere revisión de productores, consumidores e integración. Después de aprobarlos, agregar interfaces reales bajo `ros2_ws/src/robot_interfaces/` y pruebas correspondientes. Hasta entonces, no declarar interfaces definitivas ni inventar `package.xml`.

## 7. Estrategia de pruebas por nivel

| Nivel | Ejecución esperada | Límite de la conclusión |
|---|---|---|
| Estático | Sintaxis, archivos, YAML, documentación y contexto Git | No prueba nodos ROS ni hardware |
| Unitario | Algoritmos puros, entradas válidas/inválidas, mocks | No implica medición física |
| ROS 2 | `colcon build`, `colcon test`, productor/consumidor y tipos, cuando existan paquetes | No demuestra movilidad o cosecha |
| Integración | Nodos reales, datos, tiempo, TF, fallo de red y rechazo | Un actuador mock no es un motor real |
| Gazebo | Escenas versionadas, seeds, logs y obstáculos | Físicas idealizadas y/o sensores sintéticos |
| Físico | Sensor/driver/motores instrumentados bajo protocolo seguro y referencia independiente | Generalización limitada a condiciones ensayadas |

**CI existente:** `.github/workflows/ci.yml` contiene cuatro jobs: verificación estática, detección de paquetes ROS, ROS 2 Jazzy y resumen. Si `ros2_ws/src` no tiene `package.xml`, el job ROS 2 Jazzy se omite y la compilación y las pruebas del robot son **SKIP**, aunque el workflow termine en verde. La puerta ROS aislada está en `.github/workflows/ros-gate.yml` y solo se ejecuta cuando cambian sus scripts o de forma manual. El paquete temporal de la puerta solo prueba que la infraestructura puede detectar un fallo y una corrección. No usar este resultado como evidencia de un subsistema funcional.

En un PR revisa **Checks**, las salidas de cada job, artefactos y SHA evaluados. Un `PASS` no basta si las pruebas eran irrelevantes para el cambio. No omitas ni borres fallos válidos.

## 8. Reglas específicas para el carrito 2WD

`feat/2WD` se inicia como **banco experimental**. No asumir placa, driver, tensión, pines, encoders, protocolo serial, radios, microcontrolador ni límites PWM hasta inspeccionar y documentar el montaje.

Secuencia sugerida de contribuciones pequeñas:

1. Inventario del kit, hoja de conexiones, alimentación y método de desconexión física.
2. Contrato de comando y estado **provisional**, probado con mock y motores desconectados.
3. Comunicación desde ROS 2 hacia un receptor independiente, con secuencia, timeout y rechazo.
4. Pruebas supervisadas de motor con chasis inmovilizado y medidas de seguridad.
5. Pruebas de desplazamiento corto, parada manual, pérdida de comunicación y recuperación sin reactivación inadvertida.
6. Caracterización de repetibilidad/deriva/odometría **solo si** existen instrumentos o referencias externas adecuadas.

Cada fase necesita criterios de salida, resultados y fallos. Antes de movimiento real, exige autorización, alimentación apropiada, driver compatible, límites y paro accesible. No uses el kit para declarar navegación autónoma o locomoción del robot final.

## 9. Seguridad, datos y licencias

- No publiques credenciales, datos personales, matrices privadas de calibración ni binarios no autorizados. Revisa `git diff --cached` antes de cualquier commit.
- Datasets, imágenes, vídeos, pesos YOLO, bolsas ROS y CAD requieren política de tamaño, permisos, licencia, procedencia, hash y almacenamiento.
- La decisión de licencia global y titularidad **no está cerrada**. No agregues un `LICENSE` supuesto; revisa materiales de terceros y obligaciones de Ultralytics antes de incorporar dependencias o pesos.
- Actualiza registros de IA según uso real en [documentación](docs/AI_USAGE.md) y [registro estructurado](docs/ai_usage.json). El equipo humano conserva responsabilidad por contenido, evidencia y decisiones.
- No se autorizan movimientos automáticos durante auditorías, CI o pruebas generales. Cualquier acción física necesita un procedimiento y aprobación específicos.

## 10. Revisión y decisión de merge

El responsable del PR solicita revisión, resuelve hallazgos y aporta evidencia. El revisor debe bloquear la integración ante: interfaz incompatible no acordada, motor sin límites/paro, secreto filtrado, resultado experimental inventado, violación de licencia o regresión crítica sin tratar.

Un job verde es **necesario cuando aplica, no suficiente**. El repositorio puede no tener protecciones obligatorias configuradas: la existencia de esta guía no reemplaza reglas administrativas de GitHub. Nunca supongas aprobación por ausencia de comentarios. No hagas merge sin autorización expresa.

**Definición de terminado:** cambio acotado, interfaces compatibles, pruebas pertinentes y resultados trazables, seguridad comprobada para su alcance, documentación actualizada y revisión humana de la integración.
