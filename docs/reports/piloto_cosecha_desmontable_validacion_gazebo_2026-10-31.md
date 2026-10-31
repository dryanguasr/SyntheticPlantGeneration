# Validación nativa del piloto de cosecha desmontable en Gazebo

## Estado y alcance

Informe de las ejecuciones iniciadas el 30 de octubre de 2026, hora de Bogotá
(31 de octubre en los identificadores UTC). **Línea base C1–C5: A0, A1, A2 y A4
aprobados mediante auditorías independientes. Las tres repeticiones A3 de C5
se cancelaron antes de ejecutarse tras la revisión visual del usuario.**

Los resultados C1–C5 corresponden al escenario y al robot provisionales
anteriores a esa revisión. Se conservan como evidencia de la mecánica del
piloto, pero no validan el aspecto solicitado ni transfieren automáticamente
su aprobación al escenario con vegetación V8 y robot de acabado revisado.
Esa revisión requiere identificar sus artefactos y ejecuciones por separado.

El alcance es la mecánica idealizada de un piloto rígido con posiciones conocidas
del simulador. Las plantas, los nodos, pedicelos e identidades proceden del modelo
morfológico existente. No se validan percepción, madurez agronómica, fuerzas de
corte, daño, ramas flexibles, Springy ni transferencia al robot real.

La aceptación se recalcula a partir de `telemetry.jsonl`, `events.jsonl`,
`commands.jsonl`, la procedencia del plugin y el manifiesto congelado. Se separan
el acuse de una orden, el estado del plugin y la trayectoria física observada.
Las pruebas unitarias usan datos artificiales y no cuentan como ejecuciones de
Gazebo. Las imágenes de la GUI y las gráficas de telemetría se identifican por
separado.

## Entorno y código

| Componente | Entorno observado |
| --- | --- |
| Host | Windows, WSL2 |
| Distribución | Ubuntu 24.04.4 LTS |
| Kernel | 6.18.33.2-microsoft-standard-WSL2, x86_64 |
| Gazebo | Gazebo Sim 8.14.0 / Harmonic, seleccionado con `--force-version 8` |
| Física | DART, paso de integración de 1 ms |
| Python | `/usr/bin/python3`, 3.12.3 |
| Compilación | CMake 3.28.3, g++ 13.3.0 |
| Bibliotecas | sim8 8.14.0, transport13 13.5.0, msgs10 10.3.2, plugin2 2.0.4 |
| GUI | WSLg y Ogre2; captura nativa mediante `/gui/screenshot` |
| Posprocesamiento | NumPy, Matplotlib y FFmpeg ya instalados |

No fue necesario instalar dependencias. Se habilitó `core.longpaths=true` en la
configuración local de Git para crear el worktree. Los scripts Bash se conservan
con LF mediante `.gitattributes`. Los parámetros físicos y de control mantienen
su categoría `engineering_heuristic`; no son mediciones agronómicas.

- Rama: `feat/gazebo-detachable-harvest-pilot`.
- Commit inicial publicado: `3967a5b741e59d4b9370c2d872aa3b391d9380cf`.
- Commit de las correcciones evaluadas en C5:
  `d42412506a92ff719e1306dc99c4c6fba1a46ac1`.
- Commit final: pendiente de cerrar el informe y publicar los cambios.
- Worktree aislado:
  `C:\Users\User\.codex\worktrees\harvest-pilot\SyntheticPlantGeneration`.
- El checkout original y sus cambios ajenos a este piloto se conservaron.

El paquete C5 se preparó con el árbol de trabajo limpio. Su mundo es idéntico
byte a byte al de C4 que aprobó A1: SHA-256
`c681e49daf855287bc7aa6479a333e2cb87ea1a6ea2b597814d1f426a3c9ab82`.
Las copias para repetición y GUI conservan los mismos artefactos y manifiesto.
Cada ejecución usa un proceso, una partición de transporte y una salida propios.

El plugin compilado mide 6 359 760 bytes; SHA-256
`dd27d6cf50882c8fd4858f7d1273a93d0bee87c38fc2f72e309b0d40de57d427`.
La compilación nativa terminó correctamente sin necesitar cambios de API en
`HarvestSystem.cc`. `build_provenance.json` vincula el binario con ambos archivos
fuente nativos. `run.json` añade el hash del ejecutor; las auditorías añaden los
hashes del auditor, del módulo de aceptación y de los registros evaluados.

Las once auditorías previas conservadas de C2–C5 y A4 registran los mismos hashes de
auditor y módulo de aceptación, cotejados con los archivos actuales antes de
cerrar A2. La nueva auditoría independiente de A2 coincide con esas huellas.
El análisis auxiliar de posiciones también se identifica; sus
gráficas y distancias muestreadas no cambian los criterios de aceptación.

| Fuente de la evaluación | SHA-256 |
| --- | --- |
| `scripts/audit_harvest_pilot.py` | `55470814742378761682f446fe8d10378a5eac7863649d6d0ac0c6eef7fee433` |
| `src/uchuva_gazebo/harvest_validation.py` | `41040bebb180acd615322ecd1aa695ba755c993b57a7ae4a1773d8b575fe42a4` |
| `outputs/harvest_validation_evidence/analyze_positions.py` | `bde586bf0f84b2159bbeb798eb338e774a09703345983f69de84a9dbcf654f31` |

El resumen inicial de A1 C1, `A1_initial_audit_stdout.json`, no incluía las
huellas del auditor. Se conserva como evidencia histórica sin atribuirle
retrospectivamente la procedencia de las auditorías posteriores.

## Escenario de la línea base C1–C5

Tres plantas con semillas 1031, 1032 y 1033; seis unidades dinámicas, dos por
planta; tres morfologías JSON; 21 mallas visuales; 713 colliders cilíndricos de
las plantas. La conversión declarada es 8 unidades morfológicas por metro.
Las masas de los frutos son 0,006 kg y sus inercias son positivas: son valores
heurísticos del piloto. Se verificaron identidades, referencia a nodos y
pedicelos, transformaciones del punto de corte, nueve articulaciones del robot
(cuatro ruedas y cinco del brazo), cinco paredes/suelo de la cesta y hashes.
Las unidades no seleccionadas para cosecha permanecen como visuales estáticos;
ver más capachos en una captura no significa que haya más de seis cuerpos
cosechables en este experimento.

El interior de la cesta está definido por X = [-2,16; -1,84] m,
Y = [-1,16; -0,84] m y Z = [0,045; 0,27] m. La aceptación exige la esfera
completa del fruto dentro del volumen, con la tolerancia de contacto original
de 4 mm. No basta con que su centro esté dentro del rectángulo.

## Defectos reproducidos y correcciones

| Defecto observado | Evidencia y causa | Corrección |
| --- | --- | --- |
| El script de compilación fallaba antes de CMake | `pipefail\r: invalid option name`; checkout con CRLF | LF obligatorio para `*.sh` |
| Las ruedas giraban, pero el carro no seguía el giro previsto | A1 C1 agotó `drive_pickup`; la odometría de ruedas no coincidía con la pose física | Dirección lateral explícita de fricción y `slip1=0.035`, con `slip2=0`; permanecen las colisiones cilíndricas |
| Alternancia entre avanzar y orientar al llegar | A1 C2 retenía el fruto, pero perseguía el error milimétrico de posición durante el pivote | Llegada interior de 1 mm e histéresis hasta el límite final original de 3 mm |
| Muñeca oscilante aunque la posición pareciera próxima | A1 C3 rechazó `arm` por velocidad relativa; la espera adicional mostró oscilación persistente de aproximadamente 0,144 m/s | Ganancias derivativas de muñeca reducidas de 3 a 0,20 y 0,03; PID por fuerzas conservado |
| La posición próxima no aseguraba reposo antes del corte | Rechazo nativo `relative_speed_too_high` | Espera consecutiva de velocidad observada ≤0,06 m/s durante 0,2 s, por debajo de la guarda nativa intacta de 0,12 m/s |
| Error de posición sobre la cesta | A1 C4 agotó el tiempo: asentamiento lento por gravedad y retroceso de la base de unos 6,3 mm al extender el brazo | Recalcular IK con la pose observada de la base; mantener órdenes articulares ≤0,35 rad/s; permitir 35 s de asentamiento |
| El auditor aceptaba un depósito histórico aunque el fruto saliera después | Prueba artificial que reproduce estabilidad seguida de salida | Exigir estabilidad en el tramo final, conservando duración y velocidad originales |
| Faltaba cotejo independiente de comandos y acuses | Inspección y pruebas adversariales | Correspondencia ordenada uno a uno, secuencia temporal y rechazo de duplicados |
| Faltaba una comprobación explícita entre cuerpos de fruto | Riesgo de aceptar solapamientos en la cesta | Distancia entre esferas observadas en todas las muestras; no sustituye una medición de fuerzas |

La mayor espera del brazo por sí sola **no resolvió** el depósito: el intento
`20261031T040606Z-646` también falló. La pose de la base había cambiado; la
corrección de la referencia mundial fue necesaria. No se aumentaron las
tolerancias de corte, captura, retención, posición del TCP, velocidad de depósito
ni estabilidad del auditor. No se teletransportaron frutos ni se desactivó la
gravedad. El plugin y sus restricciones ideales no se cambiaron para obtener
un resultado positivo.

La convención de deslizamiento lateral se contrastó con el
[ejemplo oficial de skid steering de Harmonic](https://raw.githubusercontent.com/gazebosim/gz-sim/gz-sim8/examples/worlds/diff_drive_skid.sdf).
Se adaptó como heurística, sin atribuirle calibración de neumáticos. Se mantuvo
el control por fuerzas del
[JointPositionController oficial](https://raw.githubusercontent.com/gazebosim/gz-sim/gz-sim8/src/systems/joint_position_controller/JointPositionController.cc).

## Resultados por experimento

Los estados siguientes pertenecen exclusivamente a la línea base C1–C5.

### A0 confirmado

Paquete `outputs/harvest_pilot_c5`, ejecución `20261031T042344Z-395`:
**PASS** independiente. 251 muestras; reposo inicial observado durante 2,475 s;
deriva máxima de los seis frutos unidos: 4,777 nm numéricos. Intervalo máximo
entre muestras: 0,051 s. No hubo desprendimientos. Las órdenes de identificación
desconocida y las órdenes distantes se rechazaron. Los smokes previos de C1–C4
también se conservan, sin reemplazar la evidencia de C5.

### A1 confirmado

Paquete `outputs/harvest_pilot_c4`, ejecución `20261031T041508Z-512`:
**PASS**, tanto en el resumen del ejecutor como al invocar el auditor por separado.
4008 muestras, intervalo simulado 0,052–200,816 s, salto temporal máximo 0,051 s.
Tiempo de pared 356,706 s. La base recorrió una longitud muestreada de 6,156 m.

El primer fruto estuvo retenido 123,487 s y se alejó hasta 3,409286 m de su
posición inicial de retención. Residuo máximo de restricción: 1,289 µm;
deslizamiento relativo al TCP: 1,054 µm. Son residuos numéricos de una unión
ideal, no precisión validada de una pinza real. Después de liberarse cayó
0,391719 m. Posición final: (-1,9995295; -1,0000366; 0,0676098) m;
velocidad final muestreada: 0,0001025 m/s. El tramo final estable duró 5,805 s,
frente a los 0,7 s exigidos.

La separación mínima observada entre ese fruto y los cilindros rígidos de las
plantas fue 10,235 mm. Este cálculo posterior usa las posiciones registradas y
la geometría del SDF; no es una garantía continua entre muestras ni evidencia
de fuerzas de contacto.

### A2 confirmado: seis frutos en tres plantas

Paquete `outputs/harvest_pilot_c5`, ejecución `20261031T042426Z-695`:
**PASS independiente, 69 de 69 comprobaciones**. El proceso finalizó sin error;
el auditor se invocó después sobre los registros completos, sin usar el PASS
del ejecutor como criterio. Se observaron 29 575 muestras entre 0,052 y
1480,496 s simulados, con salto máximo de 0,051 s. El tiempo de pared fue
2466,844 s y el recorrido muestreado de la base, 76,265 m. Estos tiempos
incluyen la ejecución en WSL y no estiman productividad de un robot real.

Cada unidad registró una secuencia `ATTACHED → ARMED → CUT_PENDING → HELD →
RELEASE_PENDING → RELEASED`, un armado, un corte y una liberación aceptados.
Las 33 órdenes de interacción corresponden una a una y en orden a 33 acuses;
incluyen las pruebas negativas previstas. Los seis cuerpos acabaron dentro de
la cesta bajo la tolerancia original y estables en el tramo final. No se
observaron desprendimientos no solicitados; la deriva máxima mientras
permanecían unidos fue 4,777 nm numéricos.

En la tabla, `000`, `001` y `002` identifican `plant_000`, `plant_001` y
`plant_002`; todos los nodos llevan el prefijo `axis_0_0_`. Desplazamiento es
la máxima distancia desde la primera posición retenida, no la longitud del
trayecto. Residual y holgura se calculan a partir de las posiciones observadas.

| Fruto: planta / nodo | Retenido (s) | Desplazamiento (m) | Residual máximo (µm) | Holgura mínima a cilindros de planta (mm) | Estabilidad final (s) | Velocidad final (mm/s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1: `000 / branch_5_node_1` | 123,589 | 3,409318 | 1,719 | 10,232 | 1059,511 | 0,004 |
| 2: `000 / branch_5_node_2` | 123,226 | 3,446802 | 1,444 | 8,015 | 1056,836 | 0,280 |
| 3: `001 / branch_5_node_2` | 139,053 | 4,801304 | 1,565 | 8,069 | 549,151 | 3,596 |
| 4: `001 / node_10` | 138,103 | 4,849861 | 1,674 | 7,715 | 548,701 | 1,217 |
| 5: `002 / branch_3_node_2` | 149,003 | 6,344128 | 1,208 | 11,325 | 4,750 | 2,819 |
| 6: `002 / node_10` | 145,503 | 6,499192 | 1,076 | 6,651 | 5,650 | 7,347 |

El mayor deslizamiento relativo al TCP fue 1,674 µm. Las caídas tras la
liberación fueron de 0,386 a 0,392 m. Son resultados de la unión ideal y de
la dinámica simulada; no miden precisión de agarre ni fuerzas. El ajuste
cuadrático de las primeras 3–4 muestras liberadas, durante 0,100–0,150 s,
resultó consistente con -9,81 m/s² para las seis unidades, como diagnóstico
auxiliar sin participación en la aceptación.

La menor separación observada entre dos esferas fue **-1,713 mm** entre los
frutos 5 y 6 en t = 1474,296 s: solapamiento numérico dentro de los 4 mm de
tolerancia de contacto originales. El PASS no significa penetración cero.
La holgura mínima fruto–cilindro de planta fue positiva, 6,651 mm; sigue
siendo una comprobación muestreada y no un certificado continuo. Durante el
depósito final del fruto 6 volvió a moverse el fruto 5: para este último se exigen
y se observan 4,750 s estables **al final**, sin sustituirlos por su tramo
histórico más largo de 269,726 s.

En el directorio de la ejecución se conservan `audit.json`,
`observed_metrics.json` y `observed_trajectories.png`, además de los registros
crudos. La imagen es una gráfica de telemetría inspeccionada, no una captura
de Gazebo. Las salidas independientes del auditor y del análisis están en
`outputs/harvest_validation_evidence/A2_c5_independent_audit_stdout.json` y
`A2_c5_metrics_stdout.json`. El SHA-256 de `telemetry.jsonl` es
`d68e454d71dca77ed6092632bc20dffd5deac7be41be737186d5f156cdb79eea`;
los hashes de los demás registros están en la auditoría. El análisis auxiliar
`observed_metrics.json` tiene SHA-256
`9ebac2146cc4de8b6a4f6e744434d2ea9ce171eca431afaad135cf1381641b68`.

### A4 confirmado y repetición del ciclo individual

Paquete `outputs/harvest_pilot_c5_gui`, ejecución `20261031_A4_visual_01`:
**PASS** independiente y visualización nativa disponible. El proceso nuevo
completó el ciclo del mismo fruto: 4009 muestras, 200,869 s simulados, 613,200 s
de pared. Retención durante 123,488 s, desplazamiento máximo 3,409317 m,
residuo máximo 1,348 µm y deslizamiento relativo 1,263 µm. Caída observada
de 0,391722 m; estabilidad final durante 5,805 s. Centro final
(-1,9996616; -1,0002746; 0,0676098) m y velocidad final 0,0001461 m/s.

Un ajuste cuadrático diagnóstico de las tres primeras muestras liberadas,
en 0,101 s, da aceleración vertical de aproximadamente -9,81 m/s². Es
consistente con la caída por gravedad y no se usa como criterio adicional de
aceptación ni como medición de fuerzas de contacto.

A1 y A4 son dos ciclos completos independientes de un fruto. Sus duraciones
simuladas difieren 0,053 s; sus posiciones finales difieren aproximadamente
0,272 mm. No son trayectorias idénticas bit a bit. La mayor duración de pared
de A4 incluye renderizado, captura y ejecución simultánea de A2; no debe
interpretarse como rendimiento del robot real.

Se guardaron 893 PNG de la cámara nativa, desde la telemetría previa de
0,052 hasta 200,768 s. El video H.264 tiene 1278×772 píxeles, 10 imágenes/s
y 89,3 s: aceleración media aproximada de 2,25×. La captura y los servicios
de cámara son asíncronos; las marcas de tiempo identifican la muestra previa
a cada solicitud, sin prometer sincronización exacta de render y física.

Dentro de la salida de esta ejecución:

- `gazebo_cycle_captioned.mp4`: video con ejecución, fase, estado y tiempo.
- `gazebo_cycle_approx_2x.mp4`: secuencia sin rótulos añadidos.
- `gui_frames/`: capturas PNG nativas sin modificar.
- `gui_frames.jsonl`: índice temporal, fase y solicitudes de vista.
- `gui_media_provenance.json`: hashes de videos, subtítulos, índice y cada PNG.
- `captioned_cut_preview.png`: vista de comprobación extraída del video.
- `observed_trajectories.png`: gráfica de telemetría, explícitamente rotulada.

La vista de retirada muestra el conjunto fruto-capacho junto a la herramienta;
la vista final muestra la unidad en el fondo de la cesta y la herramienta
retirada. Se verificaron también los fotogramas de aproximación al pedicelo y
de posicionamiento sobre la cesta. La GUI emite avisos de materiales OBJ
ausentes; el SDF aporta la apariencia de los proxies y las mallas se renderizan.
Esos avisos no se interpretan como validación del aspecto botánico.

### A3 de C5 cancelado antes de ejecutarse

Los paquetes `outputs/harvest_pilot_c5_a3_1`, `harvest_pilot_c5_a3_2` y
`harvest_pilot_c5_a3_3` se prepararon como copias para tres procesos nuevos,
condicionados a un PASS independiente de A2. No tienen ejecuciones nativas:
estado **NO EJECUTADO**. La tanda pendiente se canceló al solicitar el usuario
plantas elaboradas de la versión reciente y un acabado gráfico mayor del
robot. La cancelación no constituye un fallo del motor físico ni una
repetición satisfactoria. A1 y A4 prueban dos ciclos de un solo fruto; no
sustituyen las tres repeticiones de la misión completa A3.

## Historial negativo conservado

Todos los directorios están bajo `outputs/`; no se sustituyeron por los intentos
posteriores. Un intento interrumpido no se presenta como un fallo espontáneo
del motor físico.

| Paquete / ejecución | Resultado observado |
| --- | --- |
| C1 / `20261031T033616Z-1004` | FAIL: timeout al conducir hacia la planta; sin corte |
| C2 / `20261031T034346Z-545` | FAIL, incompleto: interrupción explícita ante la oscilación de conducción; retención observada 82,942 s y 1,589 m, sin liberación |
| C3 / `20261031T035057Z-469` | FAIL: `arm` rechazado por velocidad relativa |
| C3 / `20261031T035511Z-393` | FAIL: espera de reposo agotada; oscilación de muñeca persistente |
| C4 / `20261031T040001Z-549` | FAIL: timeout de posición sobre la cesta; sin liberación |
| C4 / `20261031T040606Z-646` | FAIL: ampliar la espera no compensó el desplazamiento de la base |

El registro `operator_intervention.json` de C2 documenta la interrupción. Los
estados que nunca llegaron a liberación o depósito quedan **NO OBSERVADO** en
sus comprobaciones específicas; la misión incompleta permanece **FAIL**.

## Pruebas negativas y reset

Se observó rechazo de identificador inexistente, armado distante, corte sin
armado, corte distante después de armar y segundo corte del mismo fruto.
La estabilidad de las unidades aún unidas se comprueba durante toda la misión.

El ensayo aislado `outputs/harvest_reset_probe/reset_evidence/result.json`
obtuvo aceptación del servicio de reset y después `ready=false` con
`reset_not_supported_restart_gazebo_process_required`: **PASS del bloqueo
previsto**. No es una cosecha aprobada. El registro crudo del ensayo permanece
en `states.jsonl`. Todas las repeticiones de cosecha arrancan procesos nuevos.

## Evidencia y reproducción

Raíz local de los artefactos: `outputs/`, dentro del worktree indicado arriba.
Los paquetes C1–C4 conservan los pasos de diagnóstico; C5 congela el código
corregido. `outputs/harvest_validation_evidence/` contiene inventario del entorno,
registros de pruebas, auditorías independientes, análisis auxiliares y el parche
de trabajo. Los archivos voluminosos no se incorporan a Git.

La captura de la ventana WSLg mediante el puente de Windows no fue fiable.
La alternativa comprobada es el
[servicio Screenshot de Gazebo GUI](https://raw.githubusercontent.com/gazebosim/gz-gui/gz-gui8/src/plugins/screenshot/Screenshot.cc),
que guarda el búfer renderizado de su cámara. No se reconstruyen escenas a
partir de comandos ni se generan imágenes ilustrativas para presentarlas como
simulación. Los cambios de vista usan únicamente `/gui/move_to/pose`.

```bash
export PYTHONPATH=src
python3 -m unittest discover -s tests -p 'test_harvest*.py'
python3 scripts/validate_repository_context_graph.py
bash scripts/build_harvest_plugin.sh outputs/harvest_plugin_build
python3 scripts/prepare_harvest_pilot.py --output outputs/harvest_pilot
python3 scripts/run_harvest_pilot.py outputs/harvest_pilot --plugin-dir outputs/harvest_plugin_build --mode smoke
python3 scripts/run_harvest_pilot.py outputs/harvest_pilot --plugin-dir outputs/harvest_plugin_build --mode harvest --max-targets 1
python3 scripts/run_harvest_pilot.py outputs/harvest_pilot --plugin-dir outputs/harvest_plugin_build --mode harvest --max-targets 6 --wall-timeout 10800
python3 scripts/audit_harvest_pilot.py outputs/harvest_pilot outputs/harvest_pilot/runs/ID_REAL
```

Para GUI, añadir `--gui --gui-config configs/harvest_pilot_gui.config`. El
ejecutor copia esa configuración y registra su hash. Las tres repeticiones
deben usar salidas y procesos nuevos. La ampliación del límite de tiempo de
pared de la misión permite ejecución lenta en WSL; no cambia el paso físico
ni los criterios geométricos o temporales de aceptación.

## Limitaciones y decisiones antes del robot definitivo

1. La unión fija ideal prueba transferencia y transporte de cuerpos en Gazebo;
   no valida fuerzas de corte, agarre por contacto, presión ni daño del fruto.
2. Las masas, dimensiones, fricciones y ganancias requieren medición y ajuste
   con el robot definitivo. Las plantas son pequeñas y rígidas; no representan
   un cultivo adulto calibrado.
3. Las hojas, las unidades no seleccionadas y las mordazas son visuales. La política original de bitmasks evita
   autocontactos del robot provisional; no se puede extrapolar esta aceptación
   a autocollision del manipulador final. Permanecen los contactos con el
   entorno, la cesta y los cuerpos de fruto.
4. La continuidad se observa a 20 Hz y se complementa con los estados de
   transferencia publicados. No se dispone de un certificado continuo de
   ausencia de penetración ni de una auditoría de fuerzas del solver.
5. Las rutas e IK corresponden al escenario conocido. Deben comprobarse de
   nuevo alcance, límites, márgenes y colisiones al cambiar base, brazo o TCP.
6. La madurez agronómica sigue sin validar; la apariencia del capacho no se
   convierte en verdad de terreno. No se introdujo percepción ni aprendizaje.
   La inspección visual asistida de este informe no sustituye revisión botánica
   humana; `human_validation` sigue pendiente en el manifiesto.
7. Antes de integrar el robot definitivo: mantener IDs botánicos e interfaces;
   sustituir únicamente el intérprete del robot; medir inercias y contactos;
   repetir A0–A4 con restricciones reales; después estudiar corte por fuerza,
   agarre físico y, en una fase posterior, ramas flexibles/Springy.
8. Repetir una única configuración no establece una tasa general de fiabilidad.
   Las variaciones de morfología, carga, fricción, suelo y perturbaciones quedan
   fuera de esta matriz de experimentos.

La línea base C5 completa una misión observada de seis frutos (A2), además de
los ciclos individuales A1 y A4 y el smoke A0. Las tres repeticiones A3
previstas no se ejecutaron; por ello no se declara cerrada la matriz completa
ni se estima fiabilidad general. Esta aceptación mecánica no aprueba por sí
sola la revisión visual V8 ni la integración de un robot definitivo.
