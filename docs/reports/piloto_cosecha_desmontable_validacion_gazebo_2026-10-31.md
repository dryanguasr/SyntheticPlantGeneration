# Validación nativa del piloto de cosecha desmontable en Gazebo

## Estado y alcance

Informe de las ejecuciones del 30–31 de octubre de 2026, hora de Bogotá
(31 de octubre en los identificadores UTC). **La revisión V8 conserva tres
arbustos completos y un robot con acabado gráfico revisado. A0 y A1 aprobaron;
A2 depositó tres de tres frutos, y A3 repitió esa misión con éxito en tres
procesos independientes. A4 terminó con un ciclo físico auditado y video nativo
de 82,6 s**, usando la corrección visual C4 de la herramienta. La captura final
conserva las mismas plantas y física que C3, con derivación explícita y validada.

Los resultados C1–C5 corresponden al escenario y al robot provisionales
anteriores a esa revisión. Se conservan como evidencia de la mecánica del
piloto, pero no validan el aspecto solicitado ni transfieren automáticamente
su aprobación al escenario con vegetación V8 y robot de acabado revisado.
La línea base C5 conserva un A2 de seis depósitos correctos; sus tres misiones
A3 de seis frutos se cancelaron antes de ejecutarse tras la revisión visual.
La adaptación autorizada a pocos frutos utiliza uno por arbusto V8. No se
declara repetibilidad de seis frutos a partir de las nuevas misiones de tres.

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
- Commit de implementación mecánica evaluado en V8-C3:
  `7adaa35b5d83fd6c7a404b27a271be1180133e81`.
- Commit final de código, con la corrección visual de los soportes de la herramienta:
  `51bce19be3593b92bae311fdd70158390ba3681e`; su derivación C4 y ejecución se
  identifican por separado. No cambia la física validada en C3.
- La publicación posterior del informe y la guía sólo cambia documentación;
  el commit que generó el paquete físico permanece identificado arriba.
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

## Revisión V8: arbustos completos y acabado visual

**V8-C3: A0, A1, misión de tres frutos A2 y tres repeticiones A3 aprobados;
A4 aprobado físicamente, con cierre visual documentado por ejecución.** Esta revisión responde a la petición de
conservar arbustos elaborados de la versión reciente y mejorar el acabado del
robot. Es una escena distinta de C1–C5: sus tres frutos no heredan el PASS de
la misión histórica de seis frutos. El paquete `outputs/harvest_pilot_v8_c1`
superó la preparación, el examen del SDF y la inspección de identidad, unidades,
inercias y archivos congelados, pero su A0 falló por rendimiento como se detalla
más abajo. `outputs/harvest_pilot_v8_c2` se regeneró desde el árbol limpio del
commit `501cd7f20c466898cba05985e8f12d981e061ea7`, sin ejecutarse. El paquete
productivo `outputs/harvest_pilot_v8_c3` incorpora las colisiones agrupadas y se
generó desde `7adaa35b5d83fd6c7a404b27a271be1180133e81`, también con el árbol
limpio. Sus ejecuciones se registran por separado. V8-C1 conserva los
hashes del árbol de trabajo que lo produjo y no se presenta retrospectivamente
como un paquete construido desde ese commit limpio.

### Resultados nativos V8-C3

| Experimento | Ejecución | Estado | Evidencia principal |
| --- | --- | --- | --- |
| A0 | `20261031_A0_v8_c3_01` | PASS | 20/20 comprobaciones; tres frutos unidos; rechazos negativos |
| A1 | `20261031_A1_v8_c3_01` | PASS | 29/29 comprobaciones; corte, retención, liberación y depósito de una unidad |
| A2 adaptado, tres frutos | `20261031_A2_v8_c3_01` | PASS | 45/45 comprobaciones; tres depósitos finales estables |
| A3 adaptado, tres misiones de tres frutos | `20261031T054851Z_A3_{1,2,3}` | PASS | 45/45 comprobaciones y tres depósitos finales estables en cada repetición |
| A4 final, derivación visual C4 | `20261031_A4_v8_c4_04` | PASS | 29/29; caída y depósito inspeccionados; 826 PNG y video nativo de 82,6 s |

Los directorios de A0–A2 están bajo
`outputs/harvest_pilot_v8_c3/runs/`; contienen las poses, comandos, eventos,
resultado nativo y `audit.json` recalculado mediante el CLI independiente.
Las métricas y figuras complementarias no controlan al robot.

A0 registró 251 muestras, 12,473 s simulados y 18,713 s de pared. El tramo
inicial sin comandos duró 2,475 s; deriva máxima de los frutos 4,045 nm,
intervalo máximo de muestras 51 ms y tres órdenes negativas con tres acuses.

A1 registró 3.758 muestras hasta 188,199 s simulados, 194,564 s de pared y
5,594 m de recorrido de la base. La unidad de `plant_000` permaneció retenida
117,967 s, se desplazó 3,222 m y mostró error de retención/deslizamiento máximo
de 1,629 µm. La holgura mínima observada respecto a los cilindros que contienen
los prismas fue 5,849 mm. Tras liberarse cayó 0,401838 m y terminó en
(-2,000016; -1,000017; 0,058076) m, dentro de la cesta, con velocidad final
0,0000442 m/s y tramo final estable de 5,855 s. Las otras dos unidades
permanecieron unidas; no se contabilizan como intentos de cosecha en A1.

A2 registró 13.779 muestras hasta 691,695 s simulados, 698,826 s de pared y
34,028 m de recorrido de la base. Los tres ciclos completaron corte, retención,
liberación y depósito. El intervalo máximo entre muestras fue 51 ms; la menor
separación entre las esferas fue **+3,980 mm** en las muestras observadas.
El análisis geométrico auxiliar no detectó penetración con las envolventes de
los tallos; no constituye una certificación continua ni una medida de fuerzas.

| Planta | Retención (s) | Desplazamiento retenido (m) | Residual máximo (µm) | Holgura mínima planta (mm) | Tramo final estable (s) | Velocidad final (mm/s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `plant_000` | 118,068 | 3,222 | 1,485 | 5,879 | 275,292 | 1,230 |
| `plant_001` | 130,495 | 4,302 | 1,848 | 7,576 | 274,989 | 0,407 |
| `plant_002` | 146,203 | 6,261 | 1,602 | 6,613 | 5,950 | 0,045 |

«Estable» conserva la definición previa: esfera dentro de la cesta y velocidad
menor o igual a 35 mm/s durante el tramo final, mínimo 0,7 s. No significa
inmovilidad exacta. Las dos primeras unidades se desplazaron dentro de la cesta
después de su liberación y mantienen velocidades finales pequeñas pero no
nulas; los modelos esféricos y el contacto ideal no calibran la resistencia a
la rodadura del fruto real. Sus posiciones finales están en
`observed_metrics.json`; la estabilidad se comprobó de nuevo al final de toda
la misión, no sólo después de cada depósito individual.

### A3 adaptado confirmado: tres repeticiones de tres frutos

Las ejecuciones `20261031T054851Z_A3_1`, `20261031T054851Z_A3_2` y
`20261031T054851Z_A3_3` completaron **PASS independiente, 45/45 comprobaciones
cada una**. Corresponden a los paquetes `outputs/harvest_pilot_v8_c3_a3_1`,
`harvest_pilot_v8_c3_a3_2` y `harvest_pilot_v8_c3_a3_3`, con procesos y
particiones distintos. Se ejecutaron en paralelo sólo después de repetir
independientemente la auditoría de A2. Las tres copias conservan el manifiesto
C3 de SHA-256
`359d0a8453c028924bea1df4a59fdd70efa8ee9ac516e92cd44c8c4c834eec63`.

Esta es la adaptación V8 de **tres frutos por misión**, uno por arbusto completo.
Son nueve ciclos observados sobre las mismas tres identidades botánicas en
procesos nuevos. No completa retrospectivamente la tanda histórica C5 de
tres misiones de seis frutos: aquella fue cancelada antes de ejecutarse y
conserva su estado **NO EJECUTADO**.

Cada repetición contiene 13.780 muestras desde t = 0,052 s, sin intervalos
mayores de 51 ms. Los tres frutos están liberados y estables en la cesta al
final de cada misión. El tiempo de pared de la tabla procede de `outcome.json`;
no incluye el análisis auxiliar posterior ni se interpreta como productividad
del robot real.

| Repetición | Auditoría | Frutos finales estables | Tiempo simulado final (s) | Pared (s) | Residual máximo de retención (µm) | Holgura mínima planta (mm) | Separación mínima entre frutos (mm) | Menor tramo final estable (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A3-1 | 45/45 | 3/3 | 691,719 | 698,001 | 1,999 | 5,882 | +3,478 | 6,000 |
| A3-2 | 45/45 | 3/3 | 691,719 | 697,981 | 1,647 | 5,884 | +3,475 | 6,000 |
| A3-3 | 45/45 | 3/3 | 691,722 | 698,016 | 2,213 | 5,871 | +3,962 | 6,050 |

Las mayores duraciones de retención por repetición fueron 146,254, 146,203 y
146,203 s; el mayor deslizamiento relativo al TCP de toda la tanda fue
1,649 µm. Los residuos micrométricos corresponden a la unión ideal. Las
holguras de planta se calculan contra los cilindros exteriores que contienen
los prismas; son comprobaciones muestreadas, no medidas de fuerza ni una
certificación continua. El criterio de estabilidad conserva los 35 mm/s,
0,7 s y tolerancia de contacto originales. En particular, el valor mínimo
de la tabla usa el **tramo final**, no un reposo histórico anterior.

La siguiente dispersión compara las posiciones finales de cada identidad
entre las tres repeticiones. Cada rango XYZ es máximo menos mínimo por
coordenada; la última columna es la mayor distancia euclídea entre dos
posiciones finales del mismo fruto.

| Identidad por planta | Rango X (mm) | Rango Y (mm) | Rango Z (mm) | Mayor distancia final entre repeticiones (mm) |
| --- | ---: | ---: | ---: | ---: |
| `plant_000` | 7,793 | 48,453 | 0,000 | 49,075 |
| `plant_001` | 0,290 | 11,585 | 0,000 | 11,589 |
| `plant_002` | 0,005271 | 0,003856 | 0,000 | 0,005291 |

Las duraciones simuladas difieren hasta 0,003 s y las posiciones finales
también difieren: no se afirma igualdad de trayectorias bit a bit. La
dispersión de las primeras unidades es compatible con su movimiento dentro
de la cesta después de liberarse; «estable» no significa una posición final
única ni inmovilidad exacta. Tres repeticiones de esta configuración no
establecen una tasa general de fiabilidad ni validan precisión de depósito
en el robot real.

El cierre del coordinador y sus auditorías/análisis individuales están en
`outputs/harvest_validation_evidence/A3_v8_c3_parallel_01/`. El resumen
`V8_C3_summary_before_gui_01.json` cotejó los seis registros crudos de cada
auditoría y su vínculo al manifiesto; los 19 hashes fuente de cada paquete
coincidían con el código registrado. `A3_v8_c3_table_metrics_01.json` conserva
los valores sin redondear y las diferencias XYZ. Estos dos archivos están
en `outputs/harvest_validation_evidence/`. Los análisis auxiliares terminaron
sin error y no intervienen en la aceptación. Las auditorías de A4 se registran
en su propia sección; los resultados de A3 no se les transfieren.

### A4: ciclos físicos, adquisición visual y revisión de la herramienta

La ejecución `outputs/harvest_pilot_v8_c3/runs/20261031_A4_v8_c3_01`
completó el ciclo nativo de una unidad sin error y obtuvo **PASS físico
independiente, 29/29 comprobaciones**. Registró 3.760 muestras entre 0,052 y
188,302 s simulados, 198,624 s de pared e intervalo máximo de 51 ms. El fruto
de `plant_000` permaneció retenido 118,068 s, con desplazamiento máximo de
3,221857 m y residual/deslizamiento máximo de aproximadamente 1,244 µm. La
holgura mínima observada respecto a las envolventes de planta fue 5,861 mm.
Terminó en (-2,000016; -1,000004; 0,058076) m, dentro de la cesta, con
velocidad final 0,0000442 m/s y tramo final estable de 5,856 s. Las otras
dos unidades permanecieron unidas. Estos resultados pertenecen al mecanismo
ideal y no constituyen una calibración de pinza real.

La evidencia visual de este intento es **parcial**: `gui_frames.jsonl`
contiene 75 capturas PNG indexadas y 78 solicitudes con
`no_png_after_ack`. Las capturas indexadas abarcan solicitudes desde
t = 14,492 hasta 188,302 s; el índice no contiene fotogramas etiquetados
`release` o `settle_in_bin`. El capturador cambiaba el directorio de destino
en cada solicitud, esperaba hasta dos segundos por el PNG tras el acuse y
lo recogía al aparecer, sin comprobar aún su cierre `IEND` ni estabilidad
de tamaño. El acuse del servicio no garantizaba que el archivo estuviera
disponible y completo en ese intervalo. Se conservan los PNG, el índice,
`capture_driver.py`, los avisos y `gazebo_cycle_native.mp4`; este último
presenta saltos de tiempo simulado y no se ofrece como registro visual
continuo de todo el ciclo. Los errores de captura no se atribuyen al motor
físico ni se ocultan mediante la repetición.

La auditoría y el análisis auxiliar de `_01` se conservaron en
`outputs/harvest_validation_evidence/A4_v8_c3_01_independent_audit_stdout.json`
y `A4_v8_c3_01_position_analysis_stdout.json`, junto con sus archivos stderr.
`audit.json`, `observed_metrics.json` y la gráfica de telemetría quedan en el
directorio de la ejecución. La gráfica no es una captura de Gazebo.

La repetición `20261031_A4_v8_c3_02` corrigió la adquisición con directorio
fijo, una solicitud pendiente a la vez y comprobación de cierre `IEND` y
tamaño estable del PNG. Terminó sin error y obtuvo su propio **PASS físico
independiente, 29/29 comprobaciones**: 3.761 muestras entre 0,052 y 188,352 s
simulados, 198,118 s de pared e intervalo máximo de 51 ms. La unidad de
`plant_000` permaneció retenida 118,119 s, se alejó hasta 3,221880 m de su
posición inicial retenida y presentó residual/deslizamiento máximo de aproximadamente
1,675 µm. La holgura mínima observada respecto a las envolventes de planta
fue 5,863 mm. Terminó en (-2,000016; -1,000019; 0,058076) m, dentro de la
cesta, con velocidad final 0,0000443 m/s y tramo final estable de 5,856 s.
Las otras dos unidades permanecieron unidas. El análisis auxiliar terminó
con código cero y no modifica los criterios de aceptación.

`_02` conserva **218 PNG y cero registros `no_png_after_ack`**. Su vídeo
nativo tiene 218 fotogramas, 10 fps de reproducción y 21,8 s de duración,
según `ffprobe`. La separación media entre archivos observados después del
primero fue 0,816 s de pared (mínimo 0,645; máximo 0,898); los intervalos
solicitados de 0,05/0,2 s simulados no equivalen a esa cadencia efectiva.
La primera solicitud se registró a t = 0,052 s, pero el primer PNG se
observó cuando la telemetría ya indicaba 14,239 s; la última solicitud y
observación corresponden a 188,352 s. Se preservan tanto
`sim_time_at_request` como `sim_time_at_file_observed`: son referencias
asíncronas anteriores y posteriores a la disponibilidad del archivo, no
el instante exacto de exposición de la imagen. La fase registrada procede
de la muestra usada para solicitar la captura; no prueba que el PNG
muestre ese mismo estado. Hay dos solicitudes etiquetadas `settle_in_bin`
y ninguna `release`. Por ello, eliminar los timeouts no acredita una
captura fluida ni una representación visual continua de cada transición;
esa ejecución no cerraba todavía la inspección visual de A4.

La evidencia independiente de `_02` se conserva en
`outputs/harvest_validation_evidence/A4_v8_c3_02_independent_audit_stdout.json`
y `A4_v8_c3_02_position_analysis_stdout.json`, con sus archivos stderr
vacíos; los artefactos completos quedan en su directorio de ejecución.
El resumidor admite `--a4-run-id 20261031_A4_v8_c3_02`; al seleccionarla
mantiene `_01` en `additional_a4_runs` y deriva la aceptación de `_02`
exclusivamente de su propia auditoría independiente. Ambas ejecuciones y
sus limitaciones visuales permanecen conservadas.

#### Preparación de la captura final con GPU

Los registros de Ogre2 identificaron `llvmpipe` en las capturas anteriores.
La prueba aislada `outputs/harvest_validation_evidence/v8_gpu_probe_01/`
confirmó el backend ya instalado **D3D12 (NVIDIA GeForce RTX 4050 Laptop GPU)**.
Sólo se fijaron `GALLIUM_DRIVER=d3d12` y
`MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA` en el proceso de captura y sus hijos;
no se instalaron dependencias ni se alteró la configuración global. La selección
del adaptador sigue la [documentación de Mesa](https://docs.mesa3d.org/drivers/d3d12.html).

Para dar más tiempo a cada captura, se preparó
`outputs/harvest_pilot_v8_c3_gui_slow`. Su único cambio XML respecto a C3 es
`real_time_factor: 1 → 0.25`. Se conserva `max_step_size=0.001`, geometría,
masa, control y guardas. El factor relaciona tiempo simulado y tiempo real;
no es el paso del integrador, según la
[documentación de Harmonic](https://gazebosim.org/docs/harmonic/sdf_worlds/).

La copia es un **artefacto derivado explícito**, no otra generación desde un
commit limpio. El manifiesto actualiza el hash del SDF e incorpora la derivación;
los otros 55 archivos permanecen idénticos y C3 no se modifica. La prueba
`outputs/harvest_validation_evidence/v8_gui_slow_derivation.json` verifica el
único reemplazo XML, su reversión byte a byte, el cargador y el SDF nativo.
Su estado «no ejecutado» describe el momento de preparación; la ejecución
posterior se identifica separadamente. SHA-256 del manifiesto derivado:
`76f9693cdb5ad6db5da1717d9689527f9d6f56f08a745e1029a5bcf8d6e3cfd9`.

#### A4-03: ciclo completo con captura más densa

La ejecución `20261031_A4_v8_c3_03`, bajo el paquete derivado lento, obtuvo
**PASS independiente, 29/29 comprobaciones**. Registró 3.761 muestras hasta
188,327 s simulados y empleó 759,984 s de pared. La retención duró 118,116 s;
desplazamiento máximo desde la posición inicial retenida 3,221872 m;
residual/deslizamiento máximo 1,658 µm; holgura mínima a las envolventes de
planta 5,891 mm. Tras caer 0,401839 m, el fruto acabó en
(-2,000017375; -1,000016879; 0,058076150) m, con velocidad final
0,000044198 m/s y tramo final estable de 5,856 s. Las otras unidades siguieron
unidas. Auditoría y análisis terminaron sin error.

Se conservaron **858 PNG, sin errores de captura**, y video de 85,8 s a
10 fps. La primera solicitud corresponde a t = 0,052 s y su archivo se observó
a 3,013 s; la última, a 188,175/188,276 s. Los rótulos muestran ambas referencias
asíncronas y el estado previo, no una hora exacta de exposición. La cadencia
de reproducción es variable, con factor medio de las marcas de solicitud
aproximadamente 2,19×. Hay capturas solicitadas durante `release` y
`settle_in_bin`; la inspección muestra retirada, transporte y depósito.

Los archivos `gazebo_cycle_native.mp4`, `gazebo_cycle_captioned.mp4`,
`gui_frames.jsonl`, `gui_media_provenance.json` y `ogre2.log` quedan en el
directorio de `_03`. El índice de medios vincula sus hashes con `run.json`,
telemetría y manifiesto. El resumen `V8_C3_summary_final_01.json` conserva
el cierre C3 con esta ejecución, sin atribuirlo a revisiones posteriores.

La vista próxima de depósito permitió detectar un defecto gráfico real:
faltaban soportes entre la carcasa y las mordazas (separación vertical de
33 mm), y entre mordazas y cuchillas (16 mm). Todas pertenecían al mismo
`tool_link`, por lo que no era una desconexión dinámica. El PASS físico se
conserva; la apariencia de elementos flotantes necesitaba corrección.

#### C4: soportes visuales de la herramienta

El commit `51bce19` añade dos soportes laterales redondeados, seis primitivas
visuales, dentro de la envolvente visual existente. Las 12 pruebas del robot
aprobaron, incluida la igualdad completa del SDF al retirar sus visuales.
El stdout original se conserva en `tests_robot_visual_supports.log`
(12 pruebas, 0,040 s); su metadata distingue los hashes calculados al archivar
el registro de los datos observados durante la ejecución de las pruebas.
No se cambian masa, inercia, colisiones, articulaciones, TCP ni controles.

`outputs/harvest_pilot_v8_c4_gui` es una derivación explícita de C3: sustituye
los visuales del robot con el exportador canónico corregido y fija el factor
de tiempo real a 0,4, manteniendo el paso de 1 ms. Pasa de 252 a 258 visuales.
Los otros 55 archivos son idénticos. La prueba
`outputs/harvest_validation_evidence/v8_c4_gui_derivation.json` comprueba
igualdad byte a byte del XML no visual, la reversión exacta a C3, el cargador
y el SDF nativo. El manifiesto conserva la fuente C3 como base y declara
el hash y commit del exportador visual nuevo; no se presenta como una nueva
generación limpia ni se exige que su fuente heredada antigua coincida con
el archivo del robot ya corregido. SHA-256 del manifiesto C4:
`ad65106548f01cc5a389e2ca2f6c33a7c27811746cd895775ee3cacc819e4254`.

#### A4-04 final: inspección y auditoría aprobadas

La ejecución `20261031_A4_v8_c4_04` terminó con **PASS independiente, 29/29**.
Sus 3.759 muestras abarcan 0,052–188,234 s simulados; tiempo de pared
477,382 s. Retención de 118,067 s, desplazamiento máximo retenido 3,221868 m,
residual/deslizamiento máximo 1,478 µm y holgura mínima a planta 5,905 mm.
La caída observada fue 0,401843 m. El centro final quedó en
(-2,000017100; -1,000017720; 0,058076150) m, con velocidad final
0,000044198 m/s y tramo final estable de 5,855 s. Las otras dos unidades
permanecieron unidas. El análisis auxiliar también terminó con código cero.

La captura conserva **826 PNG sin errores registrados**. El video final es
H.264, 1278×772, 10 fps y **82,6 s**, comprobado con `ffprobe`. Su reproducción
tiene cadencia variable y factor medio aproximado 2,28× de las marcas de
solicitud. La primera solicitud fue a t = 0,052 s y su archivo se observó
a 5,363 s; la última corresponde a 188,234 s. Las marcas anteriores y
posteriores, la fase y el estado previo permanecen visibles en los rótulos.
No se adjudica a cada PNG una exposición sincronizada exactamente con la
telemetría, ni se interpreta el tiempo de pared como productividad real.

Se inspeccionaron las vistas de aproximación y retirada, los soportes ya
conectados y la secuencia final `frame_000793.png` a `frame_000796.png`:
fruto junto a la herramienta, separado durante la caída y dentro de la cesta.
La retirada física de la restricción está registrada a t = 182,025 s. Ninguna
solicitud del índice lleva la fase transitoria `release`; seis llevan
`settle_in_bin`. Eso no se usa para inferir ausencia de liberación: el evento,
las posiciones y las imágenes de caída se conservan por separado. Los
fotogramas con rótulos también se revisaron para asegurar legibilidad sin
ocultar el fruto ni la zona de depósito. Es inspección visual asistida del
piloto, no aprobación botánica humana.

Directorio final:
`outputs/harvest_pilot_v8_c4_gui/runs/20261031_A4_v8_c4_04/`.

- `gazebo_cycle_captioned.mp4`: video entregable con referencias temporales.
- `gazebo_cycle_native.mp4`: secuencia sin rótulos añadidos.
- `gui_frames/` y `gui_frames.jsonl`: PNG originales e índice asíncrono.
- `gui_media_provenance.json`: hashes del video, subtítulos, índice, cada PNG,
  `run.json`, telemetría, manifiesto y scripts de captura/rotulación.
- `capture_driver.py` y `caption_driver.py`: scripts exactos utilizados.
- `captioned_pickup_preview.png` y `captioned_drop_preview.png`: revisión del
  video rotulado; no sustituyen los PNG nativos.
- `audit.json`, `observed_metrics.json`, `observed_trajectories.png` y registros
  crudos: evidencia independiente y análisis auxiliar.
- `renderer_observed.json` y `ogre2.log`: confirmación del renderer D3D12/NVIDIA.

SHA-256 del video rotulado final:
`0d75d7f7a80a7ccd51591a89ca67fd2398d28110cc6378d57d8ad575146fdb2c`.
Los stdout independientes están bajo `outputs/harvest_validation_evidence/`
con prefijo `A4_v8_c4_04_`. `V8_C4_summary_final_01.json` vincula **A0–A3 de
C3 y A4 de C4** con sus auditorías y hashes, sin fingir una repetición íntegra
de A0–A3 en C4. El inventario histórico coincide en 18/19 fuentes actuales;
la diferencia es el archivo del robot corregido. Los dos hashes del exportador
visual de C4 coinciden. El resumen C3 previo permanece intacto.

### Fuente morfológica, unidades y conservación

Se reutilizan los árboles **ya admitidos**, con preset
`trained_trellis_nodal_repulsion_v8` y fenología `literature_cohort_v1`, del banco
`C:/dev/SyntheticPlantGeneration/outputs/spatial_plant_pool_20261028/plants/`.
El checkout original se consulta en modo de lectura. No se regeneran árboles,
no se impone la antigua cuota de cuatro a seis frutos y no se cambia su
arquitectura para facilitar el movimiento del robot.

| Instancia | Semilla | Hojas conservadas | Frutos/capachos conservados | Segmentos rígidos conservados | Unidades dinámicas |
| --- | ---: | ---: | ---: | ---: | ---: |
| `plant_000` | 2026102702 | 1045 | 370 | 5647 | 1 |
| `plant_001` | 2026102703 | 1055 | 371 | 5734 | 1 |
| `plant_002` | 2026102708 | 808 | 286 | 4461 | 1 |
| Total | — | 2908 | 1027 | 15842 | 3 |

La admisión de origen declara cero cruces duros bajo su alcance estático,
suelo y orientación válidos, con intersecciones hoja–hoja toleradas como
ocupación blanda y advertencias de proximidad conservadas. No certifica la
dinámica de cosecha ni todas las flores y objetos de contexto. Los recuentos
de la tabla son los órganos retenidos en esos árboles admitidos; las pérdidas
anteriores y sus planes reversibles permanecen en la procedencia de origen.

La conversión explícita es **10 unidades de escena por metro**, es decir,
0,1 m por unidad, coherente con la auditoría de suelo de origen. Es una
convención declarada de esta escena, no una calibración botánica. El intérprete
histórico del piloto usa 8 unidades por metro y no sabe reconstruir las
posturas nodales V8. Por ello `export_admitted_harvest_sources.py`, con
`--source-repo` explícito, evalúa los proxies mediante el intérprete de origen
y congela sus posiciones. El consumidor aplica el factor 8/10 a coordenadas
y radios para su representación interna, seguido de la conversión a SI;
no vuelve a ejecutar el intérprete histórico sobre el árbol V8. Las tres
instancias conservan giro 0° y posiciones (0,0,0), (0,2,0), (0,4,0) m.

`outputs/harvest_v8_sources/` conserva el JSON original byte a byte, el catálogo
de cada planta y su admisión. Los catálogos registran hashes de morfología,
fuentes, exportador y auditorías de origen. El paquete añade copias portables
en `sources/plant_000/`, `sources/plant_001/` y `sources/plant_002/`, verificadas
contra los hashes previos a la interpretación. El JSON completo se conserva
también como procedencia, incluidos campos adicionales desconocidos por las
dataclasses históricas. La prueba de congelado rechaza una fuente que cambia
entre interpretación y empaquetado.

### Selección acotada y movimiento nominal

Se intentaron primero dos unidades por arbusto. La separación inicial de la
esfera del fruto no bastaba para aprobar el abordaje: el primer plan con
prefiltro de 5 mm dejó la herramienta a **1,739 mm** de un cilindro al llegar
al corte, por debajo de la guarda intacta de 4 mm. En la búsqueda acotada del
primer arbusto, sólo uno de sus cinco candidatos del prefiltro pasó abordaje
y retirada; los otros cuatro fallaron la postura de corte. Esto no demuestra
que sea imposible cosechar dos unidades con otra planificación, pero no
justifica declarar seis trayectorias válidas en esta revisión.

Se eligió una unidad por arbusto, manteniendo todas las hojas, capachos y
colisiones existentes. `configs/harvest_pilot_v8.json` fija los tres IDs
explícitos; no traslada frutos a posiciones convenientes. El prefiltro exige
5 mm de holgura inicial, lado X negativo y altura de centro entre 0,45 y
0,90 m. La auditoría del movimiento conserva su guarda de 4 mm, muestreo,
límites articulares y pruebas de la herramienta y del fruto sostenido.

La siguiente tabla conserva el cribado original de V8-C1 con cilindros analíticos.
En ella, cada nodo lleva el prefijo `axis_0_0_`; el ID reproductivo completo
es `planta:nodo_reproductive_unit`. Las holguras son mínimas **calculadas en
trayectorias nominales muestreadas**, no mediciones de Gazebo.

| Planta / nodo | Altura del centro (m) | Holgura robot (mm) | Holgura fruto sostenido (mm) | Retirada desde el corte (m) |
| --- | ---: | ---: | ---: | --- |
| `000 / branch_6_branch_2_branch_0_node_3` | 0,744472 | 31,361 | 4,380 | (-0,12; 0; 0) |
| `001 / branch_10_branch_5_branch_0_node_3` | 0,893233 | 48,604 | 6,440 | (-0,08; 0; 0,03) |
| `002 / branch_5_branch_8_branch_1_node_1` | 0,466381 | 43,422 | 5,882 | (-0,12; 0; 0) |

En V8-C3, tras incorporar los prismas conservadores, el manifiesto vuelve a
evaluar esas mismas trayectorias. Las holguras mínimas nominales robot/fruto
sostenido son, respectivamente, **31,297/4,317 mm**, **48,604/6,376 mm** y
**43,394/5,818 mm**. Las tres permanecen por encima de los 4 mm exigidos.
Estos valores tampoco se presentan como distancias dinámicas observadas;
las tablas A1–A3 contienen el análisis posterior de posiciones reales.

Se conservan `motion_probe_5mm.json`, `candidate_motion_search.json` y
`candidate_motion_search_one_per_plant.json` bajo `outputs/harvest_v8_sources/`.
El último contiene el cribado satisfactorio de los tres IDs; los anteriores
preservan los rechazos. Después, la preparación de V8-C1 vuelve a comprobar
el movimiento contra los cilindros del SDF exportado, con los demás frutos
presentes. `outputs/harvest_validation_evidence/harvest_pilot_v8_c1_inspection.json`
y `v8_inspection.log` registran 3 plantas, 3 frutos, 15842 cilindros y 22 mallas,
además de la integridad de los archivos y la conversión a SI. Los índices
espaciales sólo aceleran la búsqueda de pares: no retiran colisionadores ni
relajan las distancias, y sus resultados se comparan con recorridos exhaustivos.

### Interpretación visual y comprobaciones

Las hojas curvas conservan sus identidades y posturas nodales; el cáliz añade
un perfil de cinco sépalos, subdivisiones, normales suaves y UV. Se reutilizan
las texturas actuales del proyecto y se agrupan las superficies estáticas
para reducir las llamadas de dibujo. Las unidades seleccionadas mantienen
sus cuerpos y visuales independientes. Es una interpretación Gazebo detallada
a partir de los proxies y perfiles existentes: **no es una copia exacta de las
mallas, los shaders o el render de Blender de la referencia**. Las texturas y
el relieve son hipótesis visuales; no validan madurez agronómica.

El robot incorpora carcasas redondeadas, tapas de articulación, llantas y
banda de rodadura, respiraderos, luces y detalles de la herramienta. Esos
elementos son visuales: permanecen las masas, inercias, articulaciones,
colisiones y unión ideal del robot provisional. El suelo añade mapas
procedurales propios de color y rugosidad; su colisión sigue siendo plana.
El acabado gráfico no añade agarre por contacto, suelo deformable ni una
réplica del robot definitivo.

Los registros de desarrollo contienen **85 pruebas específicas aprobadas**:
84 en `tests_v8_final.log` y una prueba adicional de congelado de fuentes en
`test_v8_source_freeze.log`. Las 17 regresiones de contratos Gazebo y estructura
del repositorio están en `tests_regression_v8.log`, también aprobadas. No se
presentan como una única ejecución de las 85 pruebas sobre el último estado:
tras la corrección final del congelado se ejecutó la prueba dirigida pertinente;
no se repitió íntegramente la batería anterior de 84. Ninguna de estas pruebas
unitarias o inspecciones estáticas constituye A0, A1, A2, A3 o A4 nativos de V8.
Después de incorporar las colisiones agrupadas se ejecutó la batería completa:
**90 pruebas específicas aprobadas en 72,130 s**, bajo el commit 7adaa35,
registradas en `tests_v8_prism_final.log`. Se volvieron a ejecutar las **17
regresiones sobre esa implementación final**, todas aprobadas en 0,145 s;
registro `tests_regression_v8_c3_final.log`.
El validador final del contexto confirmó **152 nodos y 262 relaciones válidos**;
salida en `repository_context_graph_final.log`.

### Coste físico de V8 y colisiones agrupadas

V8-C1, con 15.842 entidades de colisión cilíndricas, **falló A0** en
`20261031T051258Z-505`: `TimeoutError: Wall-clock timeout in stow`, tras
277,717 s de pared y 3,763 s simulados. El plugin estaba listo y los frutos
seguían unidos, pero la fase inicial no terminó. No fue una cancelación manual
ni un PASS de reposo. La auditoría independiente conserva los criterios no
observados en `v8_c1_smoke_audit.json`. V8-C2 conserva el mismo escenario
analítico, regenerado desde el commit 501cd7f, sin ejecución nativa adicional.

La corrección incorpora `harvest_collision_mesh.py`: cada segmento original
queda contenido en un prisma cerrado de doce caras con los mismos extremos.
El radio de los vértices es `r/cos(pi/12)`, +3,53 %, y el auditor utiliza ese
cilindro envolvente mayor. Se mantienen el margen de 4 mm y el muestreo; no se
retiran tallos ni se reemplaza el arbusto por una envolvente convexa. Los 15.842
segmentos forman tres mallas estáticas. Esto cambia explícitamente la
aproximación del contacto, aunque conserva de forma conservadora su volumen.
El perfil histórico sigue usando cilindros analíticos.

Los OBJ guardan cada ID, extremo y radio original. Su lector reconstruye y
compara íntegramente la geometría antes de usarla; rechaza caras, tapas,
coordenadas o identidades alteradas. La revisión detectó que el exportador
también necesitaba normales explícitas antes de preparar la versión productiva:
[OBJLoader de gz-common5](https://raw.githubusercontent.com/gazebosim/gz-common/gz-common5/graphics/src/OBJLoader.cc)
y [CustomMeshShape de gz-physics7/DART](https://raw.githubusercontent.com/gazebosim/gz-physics/gz-physics7/dartsim/src/CustomMeshShape.cc)
explican este requisito. Se añadieron `vn` y referencias por vértice, sin cambiar
los puntos ni las caras.

El benchmark independiente `harvest_pilot_v8_mesh_bench_01` alcanzó un factor
de tiempo real de 0,998 en una ventana activa de 11,349 s simulados / 11,372 s
de pared. El factor de 0,759 del registro completo incluye la finalización y
la auditoría; no se confunden ambas ventanas. Su smoke terminó sin error con
los tres frutos unidos; sigue identificado como benchmark, no aceptación de
cosecha del paquete productivo.

`harvest_pilot_v8_mesh_contact_probe_03` prueba el exportador canónico corregido:
una malla con tres prismas desconectados, una esfera sobre una columna, otra en
un hueco interior y un control exterior. En 302 poses por esfera hasta 3,020 s,
la primera quedó a z=1,024972498 m y las otras dos a z=0,024999895 m. Hay contacto
efectivo y el hueco permanece abierto. El ensayo `_01` conserva su limitación
de timestamps; `_02` comprobó el helper del benchmark; `_03` usa el módulo
productivo. Estos ensayos no sustituyen A0–A4 de cosecha.

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

Los siguientes comandos reproducen el perfil histórico de seis objetivos:

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

Para la revisión V8, primero exportar las tres fuentes admitidas mediante los
comandos de [la guía](../guides/piloto_cosecha_desmontable.md#arbustos-v8-completos-y-acabado-visual).
Se requieren esos artefactos locales o sus catálogos congelados: no están
incluidos en el clon de Git. Después, con un destino nuevo:

```bash
python3 scripts/prepare_harvest_pilot.py --config configs/harvest_pilot_v8.json --output outputs/harvest_pilot_v8_new
python3 scripts/run_harvest_pilot.py outputs/harvest_pilot_v8_new --plugin-dir outputs/harvest_plugin_build --mode smoke
python3 scripts/audit_harvest_pilot.py outputs/harvest_pilot_v8_new outputs/harvest_pilot_v8_new/runs/ID_A0
python3 scripts/run_harvest_pilot.py outputs/harvest_pilot_v8_new --plugin-dir outputs/harvest_plugin_build --mode harvest --max-targets 1
python3 scripts/audit_harvest_pilot.py outputs/harvest_pilot_v8_new outputs/harvest_pilot_v8_new/runs/ID_A1
python3 scripts/run_harvest_pilot.py outputs/harvest_pilot_v8_new --plugin-dir outputs/harvest_plugin_build --mode harvest --max-targets 3
python3 scripts/audit_harvest_pilot.py outputs/harvest_pilot_v8_new outputs/harvest_pilot_v8_new/runs/ID_A2
```

Avanzar entre fases sólo después de su auditoría independiente satisfactoria.
A3 repite tres veces el último ciclo de tres objetivos, cada vez con proceso
y salida nuevos, auditados individualmente. La captura A4 usa un objetivo.

## Limitaciones y decisiones antes del robot definitivo

1. La unión fija ideal prueba transferencia y transporte de cuerpos en Gazebo;
   no valida fuerzas de corte, agarre por contacto, presión ni daño del fruto.
2. Las masas, dimensiones, fricciones y ganancias requieren medición y ajuste
   con el robot definitivo. Las plantas son rígidas y sus dimensiones no están
   calibradas con un cultivo real. V8 conserva los árboles completos admitidos;
   la geometría pequeña de la línea base no define esta revisión.
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

La revisión V8 constituye una base mecánica reproducible para sustituir el
robot provisional respetando su contrato: tres depósitos en A2 y tres misiones
independientes de tres depósitos en A3, además de ciclos individuales auditados.
La línea base C5 conserva una misión de seis depósitos; su A3 de seis no se
ejecutó y no se completa mediante los ensayos de tres. La aceptación es de
este piloto rígido e idealizado. Integrar el robot definitivo exige volver a
verificar sus alcances, contactos, controles y herramienta; estos resultados
no validan todavía cosecha autónoma de campo ni una tasa general de fiabilidad.
