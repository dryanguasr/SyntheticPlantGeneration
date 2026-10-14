# Frondosidad individual de uchuvas — 2 de octubre de 2026

## Resultado morfológico y visual

Se regeneraron las 36 plantas con el preset `individual_dense_crown_v3`,
semilla de escena 230926 y las mismas semillas individuales del campo anterior.
Se conservaron las posiciones de plantación, los 72 ArUcos, los postes y los
cables superiores. Las cuerdas se reconectaron a nodos de las nuevas plantas.
No se añadieron plántulas triangulares.

| Medida | Anterior | Nueva |
|---|---:|---:|
| Mediana de ejes por arbusto | 50,5 | 124 |
| Mediana de hojas por arbusto | 255,5 | 650 |
| Ejes en el campo | 1.805 | 4.503 |
| Hojas en el campo | 9.034 | 23.385 |
| Capachos en el campo | 2.280 | 2.340 |

Las medianas aumentaron **2,46 veces en ejes** y **2,54 veces en hojas**.
Se mantuvieron los rangos de tamaño foliar y la política reproductiva de
40–65 unidades objetivo. La regeneración produjo 65 capachos por planta;
el pasillo objetivo contiene ahora 780. No se conserva el inventario de 747
del piloto anterior.

Se eligieron `plant_13` (escasa), `plant_03` (mediana) y `plant_27` (densa)
por su número de hojas anterior. Sus morfologías revisadas son idénticas a las
usadas en el campo final. Se renderizaron frente y reverso con cámaras
ortográficas, luces, resolución y encuadre idénticos entre versiones.

| Arbusto | Aumento de cobertura frontal | Superficie foliar de malla anterior / nueva |
|---|---:|---:|
| plant_13 | 82,2 % | 1,59 / 6,73 m² |
| plant_03 | 63,8 % | 2,85 / 7,50 m² |
| plant_27 | 31,3 % | 3,56 / 5,43 m² |

La mediana de las seis razones de cobertura es **1,638**: supera el objetivo
heurístico de 1,30. La cobertura se calcula con alfa foliar sobre el encuadre
completo fijo; no mide oclusión de capachos. La superficie suma las caras de
la malla, no representa una medición botánica unilateral.

La altura de las tres copas pasó de aproximadamente 1,25–1,30 m a
1,32–1,55 m según sus máximos Z medidos (consultar los valores exactos en
`review/summary.json`). Esto es una variación sintética; no una calibración
de la altura real. La apariencia sigue siendo más simplificada que el video
real, especialmente por orientación foliar, forma de la copa y materiales.

## Decisiones y desarrollo

Se aumentaron nodos laterales, probabilidades de ramificación y persistencia
del vigor hasta tercer orden. Se acortaron relativamente los entrenudos
laterales, manteniendo el factor de crecimiento del eje principal. Se
conservó la asociación nodal de hojas y unidades reproductivas.

La primera variante renderizada resultó contraproducente: más hojas, pero
menor cobertura por compactación excesiva y orientaciones casi de canto.
Se conserva como variante descartada en `outputs/dense_crowns_v3/`.
La segunda variante relajó esa compactación y recuperó las orientaciones
colgantes de 110–155°. Sus pruebas están en
`outputs/dense_crowns_v3_r2_preview/` y el campo final en
`outputs/dense_crowns_v3_final/`. No hubo una tercera revisión del preset.

Las referencias se usan cualitativamente y no como mediciones de número de
hojas, densidad volumétrica o escala. La observación del usuario de unos
3 m o más entre plantas reales queda registrada; no se aplica en esta
comparación. El campo mantiene sus separaciones históricas de 1,4 y 1,8 m.

## Contactos: mejora visual, no geometría física validada

La resolución ejecutó ocho iteraciones por planta conservando todos los
órganos. No modificó hojas por conflictos exclusivamente hoja/hoja, pero
siguió intentando corregir otros pares. La auditoría de malla posterior
separó las intersecciones foliares permitidas del resto:

| Arbusto | Intersecciones hoja/hoja toleradas | Otros pares intersectados pendientes | Violaciones de separación |
|---|---:|---:|---:|
| plant_03 | 399 | 988 | 151 |
| plant_13 | 268 | 622 | 118 |
| plant_27 | 220 | 515 | 98 |

Son pares de objetos, no conteos de órganos únicos. Los listados de ejemplos
pueden truncarse a 500; los totales no. Incluyen conflictos hoja/capacho,
hoja/tallo y entre estructuras. **La validación interna de contactos sigue
inválida**: no se presentan esas penetraciones como oclusiones visuales ni
como contactos físicos aceptables. La corrección geométrica completa queda
pendiente y es una limitación del resultado solicitado.

La auditoría detallada cubre tres arbustos aislados; no certifica todos los
contactos con tutorado o entre plantas del campo. El mundo Gazebo conserva
el LOD físico de ejes primarios y soportes. Las hojas visuales no demuestran
interacción mecánica ni seguridad de navegación dentro de las copas.

## Artefactos y reproducción

La exportación contiene **27.010.423 triángulos**, con 2.706.069.630 bytes
de OBJ (2,71 GB decimales). Tardó 805,1 s. La comprobación de correspondencia
entre identidades morfológicas, inventario, mallas y modelos SDF pasó para
los 2.340 capachos. Cada OBJ tiene un catálogo de un material.

La carga detallada falló antes del primer RGB. Se observó un RSS de
15.397.656 KiB en el servidor y unos 2,4 GiB de intercambio; WSL se reinició.
Esto apunta a agotamiento de recursos, pero no se recuperó un registro del
kernel que certifique OOM. Se preserva el intento en `inspection/failure.json`.

Se produjo un LOD **por objeto**, sin retirar órganos ni cambiar materiales,
ArUcos o colisiones: 12.958.639 triángulos y 1.268.567.540 bytes de OBJ.
Se verificó la conservación de las 107.159 representaciones geométricas
(incluyen láminas, nervaduras, pecíolos y otros componentes; no son 107.159
órganos botánicos independientes). Los 2.340 IDs de capachos siguen presentes.

La comparación ortográfica original/LOD dio IoU de silueta entre **0,9775 y
0,9797**, y pérdida de cobertura entre **0,24 % y 0,42 %** en las tres plantas.
Pasó el criterio heurístico previo de IoU ≥0,95 y cambio de cobertura ≤5 %.
La caja de cada objeto decimado se limitó a 2 mm de diferencia; eso no prueba
una distancia superficial máxima de 2 mm. Las mallas completas se conservan.

La primera inspección del LOD entregó 47 fotogramas, pero fue interrumpida
por el tiempo de espera de un comando de cámara. Está marcada como parcial.
El controlador de inspección se ajustó para esperar y reintentar comandos;
no cambió la morfología ni el controlador físico del dron.

La repetición **completó la inspección**: video RGB de Gazebo de 1280 × 960,
62 fotogramas a 5 fps (12,4 s), con decodificación completa aprobada.
El primer RGB llegó a los 112,5 s; la ejecución duró 182,4 s de pared.
El pico observado de RSS agregado del árbol del servidor fue 15.552.708 KiB
(14,83 GiB). Sigue siendo una escena costosa para este equipo; el LOD permite
la inspección, pero no demuestra operación en tiempo real.
El resultado está en `outputs/gazebo/dense_crowns_v3_lod/inspection_retry/`.
Es movimiento de una cámara de inspección, **no un vuelo físico**.

### Trayectoria anterior bloqueada por margen

La auditoría de las superficies completas con la esfera envolvente del Neo
y corrección continua por muestreo **no cumple el margen de 15 cm**:

| Altura | Intervalo X con cota insuficiente (Y = 0) | Cota mínima | Obstáculo más próximo |
|---|---|---:|---|
| 0,65 m | −2,16 a −1,81 m | 8,40 cm | Hoja de plant_13 |
| 0,95 m | 3,58 a 3,67 m | 14,55 cm | Nervadura foliar de plant_23 |

Los intervalos describen muestras que fallan el criterio conservador; no
prueban contacto del dron. Afectan ambas pasadas que reutilizan cada altura.
Los cambios de altura en los extremos cumplen el margen. No se retiraron
órganos ni se ejecutó un vuelo físico sobre esta trayectoria.

- `outputs/dense_crowns_v3_final/input.json`: árboles y escena regenerados.
- `outputs/dense_crowns_v3_final/comparison.json`: parámetros, semilla y conteos.
- `outputs/dense_crowns_v3_final/plants/`: morfologías, validaciones y registros de corrección por planta.
- `outputs/dense_crowns_v3_final/review/`: comparativas, métricas, máscaras foliares, auditorías y tres archivos Blender editables.
- `outputs/dense_crowns_v3_final/review/arbustos_frondosos.blend`: las tres copas editables juntas, con desplazamientos de presentación, no posiciones del campo.
- `outputs/gazebo/dense_crowns_v3/`: campo con capachos individualizados.
- `outputs/gazebo/dense_crowns_v3_lod/`: versión visual reducida, con inventario y comprobación de siluetas.

La guía reproducible es `docs/guides/copas_individuales_frondosas.md`.
No se instaló ninguna dependencia ni se modificó el detector. El piloto de
vuelo anterior y el trabajo local de reconstrucción real se conservaron.

## Validación de software

Pasaron 47 pruebas: 4 específicas de copas densas, 10 del piloto disperso,
29 de Gazebo y 4 de adaptación del cultivo. Se comprobaron determinismo,
serialización, jerarquía, política reproductiva, conservación de órganos,
compatibilidad histórica y catálogos de materiales individuales.
La semejanza visual con plantas reales permanece pendiente de revisión humana.
