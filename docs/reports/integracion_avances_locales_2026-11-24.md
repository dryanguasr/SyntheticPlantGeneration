# Integración de los avances locales de todos los frentes

El usuario autorizó revisar y fusionar el trabajo local y confirmó expresamente
el alcance: **todos los frentes del proyecto**. El
[PR 1](https://github.com/dryanguasr/SyntheticPlantGeneration/pull/1) reúne la
integración, preparada sobre `codex/integracion-physalisharvest-20261124` para `main`.
Este registro distingue cambios de software, comprobaciones nuevas y evidencia
experimental recuperada; no equivale a validación humana de resultados.

## Fuentes conciliadas y conservación

| Fuente | Corte | Tratamiento |
| --- | --- | --- |
| Integración revisada del PR 1 | `17fe68798473fa7f3289385b81983fcd4c942ef1` | Conserva las cinco correcciones de API, IK, mordaza, unidades y lanzamiento ROS |
| Cosechador local | `4deb16693065e6c044d353112b0419816ebe9183` | Incorpora cuatro commits nuevos desde `0bcb8a8`, con historial preservado en el merge local `5b365f8` |
| Generación, percepción, anotación y documentación locales | HEAD `451ddd2c9070e67759b8e0b65c5ef3254d78814f`, más cambios sin commit | Snapshot estable de 15 archivos modificados y 346 archivos nuevos publicables; conciliación con la arquitectura actual |
| Aporte de Diego | PhysalisHarvest `114ce5690e7bf024d57ce2c815b7f3afd1d82e38` | Los 107 archivos originales y sus términos se conservan íntegros |

Antes de incorporar el trabajo sin commit se guardaron manifiesto de hashes,
patch binario, versiones base y copias de trabajo bajo
`outputs/all_fronts_merge_20261124/local_snapshot/`. El manifiesto tiene SHA-256
`06d5bcff3444f8a03f7e8e338c704a26e1e12728e0c8018e0cdc1ec9c285ba53`.
Se verificó estabilidad de HEAD, listas, status, bytes y fechas antes/después.

Los 361 candidatos están presentes: 318 archivos nuevos se incorporaron, 28 ya
eran idénticos y los 15 archivos modificados se conciliaron. Trece patches se
aplicaron sin conflicto; README y grafo se conciliaron con el trabajo del robot.
Se mantuvo la documentación técnica y se eliminaron blancos finales
en un test de follaje y un script de auditoría. La revisión de cobertura no encontró archivos faltantes,
symlinks externos ni patrones de credenciales de alta confianza. No fue una
auditoría exhaustiva de secretos.

El checkout original conserva su HEAD, rama, cambios y archivos sin seguimiento.
No se hizo stash, reset ni limpieza. Una fotografía local de referencia quedó
excluida de publicación y permanece en su origen. Datasets, pesos, máscaras
individuales, renders, vídeos, borradores y artículos descargados siguen fuera
de Git. El manual PDF incluido es documentación original del proyecto, no un
artículo de terceros. Ninguna rama local tenía commits fuera del HEAD integrado
al terminar la inspección.

## Compatibilidad de los frentes

La morfología serializable permanece como autoridad botánica. Los nuevos
módulos de apariencia y captura interpretan sus órganos; las clases de capacho
siguen siendo etiquetas de apariencia con incertidumbre explícita. Los pilotos
de segmentación mantienen la separación entre máscaras provisionales,
adjudicación humana pendiente y evaluación histórica consultada durante
desarrollo. No se convierte ese conjunto en holdout externo por renombrarlo.

Se incorporan utilidades de apariencia, captura optimizada, continuidad de
datasets, aumentación, evaluación, revisión privada de máscaras y fusión de
movimiento/localización. README y README técnico reúnen los resultados y límites
de esos frentes. El grafo descriptivo concilia ambas líneas sin dar autoridad
botánica a Gazebo, al código legado o al snapshot externo.

`RobotSpec`/`ResolvedRobot` siguen describiendo el robot canónico. Las
observaciones ópticas de PhysalisHarvest no pasan a ser objetivos botánicos ni
órdenes de actuadores. Continúan pendientes TF calibrada, sincronización,
odometría observada, adaptación de control, puente ROS/Gazebo y ejecución física
del brazo. El banco 2WD y el robot virtual de cuatro ruedas siguen identificados
como plataformas distintas. La licencia institucional del aporte continúa
pendiente y no se sustituye por MIT.

## Avances del cosechador y defectos corregidos

Los cuatro commits nuevos documentan tomas continuas de nueve depósitos con
movimiento cinemático prescrito. La toma de codo alto registró 9/9 depósitos,
3 por planta, y 9.640 muestras articulares nativas. La comprobación geométrica
de 183 intervalos usa un margen nominal de 4 mm respecto a chasis y canasta;
no demuestra continuidad física ni seguridad del cultivo.

La respuesta de contacto del brazo, chasis y cultivo se omitió. Gravedad,
canasta, suelo y frutos liberados permanecieron activos. Los objetivos y ejes
de corte provienen del simulador. Persisten 12 proximidades muestreadas entre
capachos retenidos y cultivo y el diagnóstico RGB histórico de 0/6 coincidencias.
Estos resultados se conservan separados del depósito aislado histórico por
actuación de fuerzas; no prueban cosecha autónoma ni admisión dinámica.

La revisión de este incremento encontró y corrigió dos defectos:

1. Repetir una toma truncaba `native_motion.tsv`. Ahora el preflight rechaza
   evidencia existente y el plugin crea el archivo de forma exclusiva y
   atómica. También se rechazan rutas del SDF que apuntan a otra toma.
2. Captura y auditoría verificaban el manifiesto, pero no los activos de origen.
   Ambas validan ahora el paquete completo antes de lanzar procesos o cargar
   geometrías.

Se añadieron nueve regresiones, incluidos lanzamientos concurrentes, symlinks,
activos alterados y controles válidos. La procedencia del build incluye las
siete bibliotecas y las dos fuentes de demostración, conservando el conjunto de
hashes consumido por las auditorías históricas.

La suite general detectó además un fallo de congelación de fuentes de apariencia
en rutas largas de Windows. La corrección mantiene los hashes de contenido y
las rutas canónicas del contrato; usa streams y el namespace extendido de Windows
para las operaciones de copia. Una regresión comprueba copia, reanudación y
rechazo de alteraciones en rutas de más de 260 caracteres.

## Comprobaciones de integración

Las verificaciones usan entornos existentes. No se instalaron dependencias,
ni se ejecutaron campañas de entrenamiento, lotes de render, nuevas misiones
Gazebo o acciones físicas. Los ensayos unitarios usan datos pequeños y mocks.
La compilación de plugins no equivale a una misión nativa con sus nuevas fuentes.

| Comprobación | Resultado | Evidencia local |
| --- | --- | --- |
| Suite general final de Windows | 1.085 casos: 1.077 PASS, ocho omisiones; cero fallos y errores, 268,88 s | `final_python_tests.{json,log}` |
| Apariencia y congelación de fuentes en Windows | 24/24 PASS, incluida la regresión de rutas largas | `followup_appearance_long_paths_windows_03.log` |
| Contratos POSIX y preservación de evidencia | 25/25 PASS, sin omisiones | `posix_tests.{json,log}` |
| Plugins Gazebo | Siete bibliotecas compiladas, con hashes de fuentes y binarios | `native_build/{configure.log,build.log,build_provenance.json}` |
| Contratos nativos C++ | 3/3 CTests PASS | `native_build/ctest.log` |
| Galería de cuatro modelos | Sintaxis Node válida y 12 controles DOM PASS sobre caché local; 94 fotos, 28 etiquetadas, cuatro modelos y tres semillas | `scripts/test_sobremadura_gallery_runtime.cjs`, caché histórica fuera de Git |
| Fixture de vídeo VFR original | PASS sin modificar el test, con FFmpeg Windows existente; código y test idénticos a `main` y al árbol integrado | `ffmpeg_fixture_windows.{json,log}` |
| Integridad PhysalisHarvest | PASS, 107 archivos | `scripts/verify_physalisharvest_snapshot.py` |
| Grafo descriptivo conciliado | VALID, 181 nodos y 298 relaciones | `scripts/validate_repository_context_graph.py` |

La primera suite general de Windows ejecutó 1.084 casos: cero fallos de
aserción, un error de ruta larga y ocho omisiones. Se preservan sus logs
`all_python_tests.{json,log}` y las dos ejecuciones intermedias negativas de
apariencia. Tras la corrección y su nueva regresión, la suite final separada
terminó con cero fallos y errores. Tres omisiones de Windows están cubiertas
por las pruebas POSIX y una por el fixture VFR original ejecutado por separado.
Las otras cuatro requieren una lámina local de coordinación, una referencia
local de dataset o el dataset privado del piloto de unión. No se publican esos
activos para hacer desaparecer las omisiones.

La revisión cruzada dirigida no encontró bloqueos adicionales en las fronteras
morfológicas, los contratos públicos de pose ni los cambios de evaluación y
anotación. El diff final pasa `git diff --cached --check`. Estas revisiones no
acreditan validación botánica, calibración del filtro de pose ni transferencia
física.

El fixture VFR no se descubrió inicialmente en este worktree porque su lookup
histórico busca FFmpeg dentro del checkout. El mismo test original pasó sin
alteraciones en el checkout de origen, con el mismo código y el entorno
Windows existente. Su ejecución diagnóstica con FFmpeg Linux sí falló, y se
conserva en `ffmpeg_fixture.{json,log}`: es una diferencia del entorno
preexistente sobre archivos idénticos a `main`, no una regresión del incremento.
No se atribuye esa diferencia a una dependencia concreta sin aislarla.

La validación ROS anterior del mismo lanzador permanece documentada en el
[registro de correcciones](correcciones_revision_pr1_2026-11-24.md): dos paquetes
compilados y recepción real de un mensaje sintético de estado en localhost,
dominio 97. No se presenta como nueva ejecución de esta integración.

Los logs, respaldos, librerías y fixtures de reproducción permanecen en
`outputs/all_fronts_merge_20261124/`, excluidos de Git. Los resultados
experimentales de noviembre se recuperaron de evidencia local existente; los
informes mantienen sus controles, resultados negativos y límites de alcance.
